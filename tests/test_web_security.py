"""The web squad's security layer, exercised the way the bots use it: pinned downloads, the repo's three security
gates, the headers every site ships, and QA's code audit.

Each test describes what must hold when a bot uses the feature, and fails when the feature breaks. Fake scanners
reproduce the real tools' exit codes and output shapes (checked against osv-scanner 2.6, gitleaks 8.30, nuclei 3.11
and semgrep 1.180); the real binaries run in the `real_toolchain` tests of test_web_base.py.
"""
import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "squads" / "web" / "skills" / "site-contract"
SCRIPTS = CONTRACT / "scripts"
SECURITY_MJS = CONTRACT / "templates" / "quality" / "tools" / "quality" / "security.mjs"
sys.path.insert(0, str(SCRIPTS))
import scaffold_site  # noqa: E402
import security_tools  # noqa: E402
import site_base  # noqa: E402

needs_node = pytest.mark.skipif(not shutil.which("node"), reason="needs node")
WORK_ID = "acme-20261022-build-01"


def fake_bin(folder: Path, name: str, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- pinned, verified downloads

def release(mirror: Path, tool: str, payload: bytes) -> tuple[str, bytes]:
    """Lay out one release asset the way the project publishes it; returns (asset name, asset bytes)."""
    pin = security_tools.PINS[tool]["version"]
    asset, sums, kind = security_tools.asset_for(tool, pin)
    if kind == "tar":
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            info = tarfile.TarInfo(tool)
            info.size = len(payload)
            tf.addfile(info, io.BytesIO(payload))
        data = buf.getvalue()
    else:
        data = payload
    folder = mirror / tool / pin
    folder.mkdir(parents=True, exist_ok=True)
    (folder / asset).write_bytes(data)
    (folder / sums).write_text(f"{sha(data)}  {asset}\n")  # a compromised release ships a matching checksum file
    return asset, data


@pytest.fixture
def tools_home(tmp_path, monkeypatch):
    tools, mirror = tmp_path / "tools", tmp_path / "mirror"
    monkeypatch.setenv("HERMES_WEB_TOOLS_DIR", str(tools))
    monkeypatch.setenv(security_tools.MIRROR, f"file://{mirror}")
    return tools, mirror


def pin_digest(monkeypatch, tool: str, asset: str, digest: str) -> None:
    monkeypatch.setitem(security_tools.PINS[tool], "sha256", {asset: digest})


def test_a_scanner_installs_only_when_it_matches_the_digest_this_repo_pins(tools_home, monkeypatch):
    """The bots download scanners that then run on the user's code. A release (or mirror) that swaps the binary
    also swaps its own checksum file, so only a digest held in this repo can catch it."""
    tools, mirror = tools_home
    good = b"#!/bin/sh\necho scanner-ok\n"
    for tool in ("gitleaks", "osv-scanner"):  # a tar.gz release and a raw-binary release
        asset, data = release(mirror, tool, good)
        pin_digest(monkeypatch, tool, asset, sha(data))
    rows = [security_tools.ensure(t) for t in ("gitleaks", "osv-scanner")]
    assert all(r["ready"] for r in rows), rows
    out = subprocess.run([str(security_tools.bin_dir() / "gitleaks")], capture_output=True, text=True)
    assert out.stdout.strip() == "scanner-ok"
    assert security_tools.ensure("gitleaks")["detail"] == "already installed"

    shutil.rmtree(tools)
    shutil.rmtree(mirror)
    release(mirror, "gitleaks", b"#!/bin/sh\necho evil\n")  # its own checksum file agrees with the swap
    refused = security_tools.ensure("gitleaks")  # the pinned digest is still the good one
    assert refused["ready"] is False and "pinned digest" in refused["detail"]
    assert not (security_tools.bin_dir() / "gitleaks").exists(), "a refused download leaves nothing behind"


def test_a_binary_changed_after_install_is_reinstalled(tools_home, monkeypatch):
    tools, mirror = tools_home
    asset, data = release(mirror, "gitleaks", b"#!/bin/sh\necho scanner-ok\n")
    pin_digest(monkeypatch, "gitleaks", asset, sha(data))
    assert security_tools.ensure("gitleaks")["ready"]
    (security_tools.bin_dir() / "gitleaks").write_text("#!/bin/sh\necho swapped\n")  # replaced or half-written
    assert security_tools.installed_version("gitleaks") is None
    again = security_tools.ensure("gitleaks")
    assert again["ready"] and again["detail"].startswith("installed")
    out = subprocess.run([str(security_tools.bin_dir() / "gitleaks")], capture_output=True, text=True)
    assert out.stdout.strip() == "scanner-ok"


def test_downloads_refuse_plain_http(tools_home, monkeypatch):
    monkeypatch.setenv(security_tools.MIRROR, "http://mirror.example")
    row = security_tools.ensure("gitleaks")
    assert row["ready"] is False and "non-https" in row["detail"]
    with pytest.raises(ValueError, match="non-https"):
        security_tools.fetch("http://github.com/x")


def test_every_binary_pin_carries_a_digest_for_each_supported_host():
    """A pin without the digest of a host's asset would refuse to install there: the bots on that machine would run
    without scanners. Darwin and Linux on arm64 and x86_64 are the hosts Hermes runs on."""
    for tool in security_tools.LAYOUT:
        pin = security_tools.PINS[tool]["version"]
        names = security_tools.PLATFORM_NAMES[tool]
        wanted = {security_tools.LAYOUT[tool][0].format(v=pin, os=names["os"][o], arch=names["arch"][a])
                  for o in ("darwin", "linux") for a in ("arm64", "x86_64")}
        digests = security_tools.PINS[tool]["sha256"]
        assert wanted <= set(digests), (tool, wanted - set(digests))
        assert all(len(d) == 64 and int(d, 16) >= 0 for d in digests.values())
    assert len(security_tools.PINS["nuclei"]["templates_sha256"]) == 64
    assert "semgrep" not in security_tools.LAYOUT  # it installs through uv, never as an unchecked binary


def templates_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, body in files.items():
            zf.writestr(name, body)
    return buf.getvalue()


def template_release(mirror: Path, data: bytes) -> None:
    pin = security_tools.PINS["nuclei"]["templates"]
    folder = mirror / "nuclei-templates" / pin
    folder.mkdir(parents=True)
    (folder / f"nuclei-templates-{pin}.zip").write_bytes(data)


def test_nuclei_templates_are_fetched_verified_and_trimmed_to_http(tools_home, monkeypatch):
    """A slow link kills nuclei's own 60 s downloader; the squad fetches the pinned release itself and keeps only
    the http templates, so no code or file protocol template ever lands on the user's disk."""
    tools, mirror = tools_home
    data = templates_zip({"nuclei-templates-x/http/exposures/env.yaml": "id: env",
                          "nuclei-templates-x/code/run.yaml": "id: code", "nuclei-templates-x/http/notes.md": "doc",
                          "nuclei-templates-x/http/../../../escape.yaml": "id: out"})
    template_release(mirror, data)
    monkeypatch.setitem(security_tools.PINS["nuclei"], "templates_sha256", sha(data))
    assert security_tools.templates_ready() is False
    assert security_tools.ensure_templates().get("ready") is not False
    folder = tools / "nuclei-templates"
    assert (folder / "http" / "exposures" / "env.yaml").is_file()
    assert not (folder / "code").exists() and not (folder / "http" / "notes.md").exists()
    assert not (tools.parent / "escape.yaml").exists() and not (tools / "escape.yaml").exists()
    assert security_tools.templates_ready() is True


def test_tampered_nuclei_templates_are_refused_and_leave_nuclei_not_ready(tools_home):
    tools, mirror = tools_home
    template_release(mirror, templates_zip({"x/http/a.yaml": "id: a"}))  # not the pinned release's bytes
    refused = security_tools.ensure_templates()
    assert refused["ready"] is False and "pinned digest" in refused["detail"]
    assert not (tools / "nuclei-templates").exists() and security_tools.templates_ready() is False


def test_status_does_not_call_nuclei_ready_without_its_templates(tmp_path):
    tools = tmp_path / "tools"
    pin = security_tools.PINS["nuclei"]["version"]
    binary = fake_bin(tools / "bin", "nuclei", "exit 0\n")
    (tools / "bin" / "nuclei.version").write_text(f"{pin} {sha(binary.read_bytes())}")
    done = subprocess.run([sys.executable, "-I", str(SCRIPTS / "security_tools.py"), "status"], capture_output=True,
                          text=True, env={**os.environ, "HERMES_WEB_TOOLS_DIR": str(tools)})
    row = next(r for r in json.loads(done.stdout)["tools"] if r["tool"] == "nuclei")
    assert row["installed"] == pin and row["ready"] is False


# ---------------------------------------------------------------- the repo's security gates

def gate(cwd: Path, bin_dir: Path, name: str, path: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": path or f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           "HERMES_WEB_TOOLS_DIR": str(cwd / "no-tools"), "HERMES_REAL_HOME": str(cwd / "no-home")}
    return subprocess.run([shutil.which("node"), str(SECURITY_MJS), name], cwd=cwd, capture_output=True, text=True,
                          env=env, timeout=60)


@needs_node
def test_the_license_gate_lets_only_permissive_licenses_ship(tmp_path):
    bin_dir = tmp_path / "bin"
    licenses = {"MIT": [{"name": "react"}], "LGPL-3.0-or-later": [{"name": "sharp-libvips"}], "MPL-2.0": [{"name": "y"}],
                "(MIT OR GPL-3.0)": [{"name": "dual"}], "GPL-3.0-only": [{"name": "leftpad-gpl"}],
                "(MIT AND GPL-3.0)": [{"name": "both"}], "UNKNOWN": [{"name": "mystery"}],
                "SEE LICENSE IN LICENSE": [{"name": "custom"}], "Elastic-2.0": [{"name": "elastic"}],
                "CC-BY-ND-4.0": [{"name": "nd"}], "(MIT AND Zlib)": [{"name": "pako"}]}
    fake_bin(bin_dir, "pnpm", f"cat <<'EOF'\n{json.dumps(licenses)}\nEOF\n")
    done = gate(tmp_path, bin_dir, "licenses")
    assert done.returncode == 1
    blocked = {"leftpad-gpl", "both", "mystery", "custom", "elastic", "nd"}
    reported = {line.split(":", 1)[0] for line in done.stderr.splitlines() if ": license " in line}
    assert reported == blocked, done.stderr  # LGPL, MPL, a permissive OR branch and MIT AND Zlib ship
    (tmp_path / "tools" / "quality").mkdir(parents=True)
    (tmp_path / "tools" / "quality" / "license-allow.json").write_text(json.dumps(sorted(blocked)))
    assert gate(tmp_path, bin_dir, "licenses").returncode == 0


@needs_node
def test_the_dependency_gate_fails_on_a_vulnerability_and_never_passes_when_it_could_not_scan(tmp_path):
    bin_dir = tmp_path / "bin"
    fake_bin(bin_dir, "pnpm", "exit 0\n")
    fake_bin(bin_dir, "osv-scanner", "echo 'GHSA-wq5f-xc86-pv6w sharp 0.35.4'\nexit 1\n")
    missing = gate(tmp_path, bin_dir, "deps")
    assert missing.returncode == 2 and "pnpm-lock.yaml is missing" in missing.stderr
    (tmp_path / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    done = gate(tmp_path, bin_dir, "deps")
    assert done.returncode == 1 and "GHSA-wq5f-xc86-pv6w" in done.stderr
    fake_bin(bin_dir, "osv-scanner", "echo 'failed to parse lockfile'\nexit 127\n")  # osv-scanner's own code
    unreadable = gate(tmp_path, bin_dir, "deps")
    assert unreadable.returncode == 2 and "could not read the lockfile" in unreadable.stderr
    fake_bin(bin_dir, "osv-scanner", "exit 0\n")
    fake_bin(bin_dir, "pnpm", "echo 'ERR_PNPM_AUDIT_BAD_RESPONSE request failed'\nexit 1\n")
    offline = gate(tmp_path, bin_dir, "deps")
    assert offline.returncode == 2 and "could not reach the advisory database" in offline.stderr
    # pnpm audit as it behaves: one moderate advisory fails at --audit-level moderate or low, passes at high
    moderate = ('level=low; prev=; for a in "$@"; do [ "$prev" = "--audit-level" ] && level=$a; prev=$a; done\n'
                'echo "1 vulnerabilities found"; echo "Severity: 1 moderate"\n'
                'case $level in high|critical) exit 0;; *) exit 1;; esac\n')
    fake_bin(bin_dir, "pnpm", moderate)
    assert gate(tmp_path, bin_dir, "deps").returncode == 1  # moderate fails too, as project-base.md says
    fake_bin(bin_dir, "pnpm", "exit 0\n")
    assert gate(tmp_path, bin_dir, "deps").returncode == 0
    (bin_dir / "osv-scanner").unlink()
    gone = gate(tmp_path, bin_dir, "deps", path=f"{bin_dir}:/usr/bin:/bin")
    assert gone.returncode == 2 and "osv-scanner is not installed" in gone.stderr, "a missing scanner is not a pass"


@needs_node
def test_the_secrets_gate_tells_a_leak_from_a_scanner_error_and_an_empty_history(tmp_path):
    """gitleaks exits 1 on a fatal error too, so the gate asks it for its own leak code: a broken config must never
    read as a leak, and a leak never as a broken scanner."""
    bin_dir = tmp_path / "bin"
    leak_code = 'for a in "$@"; do [ "$prev" = "--exit-code" ] && code=$a; prev=$a; done\n'
    fake_bin(bin_dir, "gitleaks", leak_code + "echo 'Finding: REDACTED  RuleID: stripe-access-token'\nexit ${code:-1}\n")
    leak = gate(tmp_path, bin_dir, "secrets")
    assert leak.returncode == 1 and "stripe-access-token" in leak.stderr
    fake_bin(bin_dir, "gitleaks", "echo 'fatal: could not read config'\nexit 1\n")
    broken = gate(tmp_path, bin_dir, "secrets")
    assert broken.returncode == 2 and "could not scan" in broken.stderr
    fake_bin(bin_dir, "gitleaks", "exit 0\n")
    assert gate(tmp_path, bin_dir, "secrets").returncode == 0
    # a fresh repo: the base runs the gate before its first commit, so an empty history must not block it,
    # while a leak in the not-yet-committed files must still be caught
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    empty = gate(tmp_path, bin_dir, "secrets")
    assert empty.returncode == 0 and "no commit yet" in empty.stderr
    fake_bin(bin_dir, "gitleaks", leak_code + 'if [ "$1" = dir ]; then echo "RuleID: stripe-access-token"; '
             'exit ${code:-1}; fi\nexit 0\n')
    assert gate(tmp_path, bin_dir, "secrets").returncode == 1
    (tmp_path / ".git" / "HEAD").write_text("garbage\n")  # a broken repo is not an empty one
    assert gate(tmp_path, bin_dir, "secrets").returncode == 2


@needs_node
def test_a_scanner_named_file_committed_in_the_repo_is_never_run(tmp_path):
    """An empty PATH entry means 'current directory': the site repo. A committed `gitleaks` must not run."""
    fake_bin(tmp_path, "gitleaks", "echo planted > planted.txt\nexit 0\n")
    done = gate(tmp_path, tmp_path / "bin", "secrets", path=":/usr/bin:/bin")
    assert done.returncode == 2 and "gitleaks is not installed" in done.stderr
    assert not (tmp_path / "planted.txt").exists()


# ---------------------------------------------------------------- what the base writes

def test_the_base_carries_every_security_setting_and_header(tmp_path):
    stacks = scaffold_site.load_stacks()
    files, _, _ = site_base.plan_files(tmp_path, stacks, "astro", "acme", "cloudflare")
    pkg = json.loads(files["package.json"])["scripts"]
    assert pkg["quality"].split(" && ") == [f"pnpm run quality:{s}" for s in site_base.GATE]
    assert pkg["quality:deps"] == "node tools/quality/security.mjs deps"
    assert pkg["quality:typecov"].startswith("tools/quality/node_modules/.bin/type-coverage")
    assert "--strict" in pkg["quality:typecov"] and pkg["format"] == "biome check --write ."
    for name in ("pnpm-workspace.yaml", "tools/quality/pnpm-workspace.yaml"):
        yaml = files[name]
        for line in ("minimumReleaseAge: 20160", "trustPolicy: no-downgrade", "strictDepBuilds: true",
                     "blockExoticSubdeps: true", "  - chromium-bidi", '  sharp: ">=0.35.5"',
                     "minimumReleaseAgeExclude:"):
            assert line in yaml.splitlines(), (name, line)
    quality = json.loads(files["tools/quality/package.json"])["devDependencies"]
    assert {"eslint-plugin-security", "eslint-plugin-no-unsanitized", "type-coverage"} <= set(quality)
    assert "domain-is-framework-free" in files["tools/quality/dependency-cruiser.cjs"]
    headers = files["public/_headers"]
    for header in ("Strict-Transport-Security", "Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options",
                   "Referrer-Policy", "Permissions-Policy", "Cross-Origin-Opener-Policy"):
        assert f"  {header}: " in headers, header
    vercel, _, _ = site_base.plan_files(tmp_path / "v", stacks, "astro", "acme", "vercel")
    assert "public/_headers" not in vercel and "frame-ancestors 'none'" in vercel["vercel.json"]
    nxt, _, _ = site_base.plan_files(tmp_path / "n", stacks, "nextjs", "acme", "cloudflare")
    assert "async headers()" in nxt["next.config.ts"] and "Content-Security-Policy" in nxt["next.config.ts"]


def test_an_existing_repo_cannot_keep_weaker_supply_chain_settings(tmp_path):
    """A repo the bots adopt keeps its own content, but never a supply-chain setting weaker than the base's."""
    (tmp_path / "package.json").write_text('{"name": "theirs"}')
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "packages:\n  - apps/*\nminimumReleaseAge: 0\ntrustPolicy: off\nstrictDepBuilds: false\n"
        "trustPolicyIgnoreAfter: 999999\noverrides:\n  left: 1.0.0\nminimumReleaseAgeExclude:\n  - 'theirs@1.0.0'\n")
    report: dict = {}
    files, _, _ = site_base.plan_files(tmp_path, scaffold_site.load_stacks(), "astro", "theirs", "cloudflare", report)
    merged = files["pnpm-workspace.yaml"].splitlines()
    assert "packages:" in merged and "  - apps/*" in merged and "  left: 1.0.0" in merged  # theirs stays
    for line in ("minimumReleaseAge: 20160", "trustPolicy: no-downgrade", "strictDepBuilds: true",
                 "blockExoticSubdeps: true", '  sharp: ">=0.35.5"'):
        assert line in merged, line
    assert "trustPolicyIgnoreAfter: 999999" in merged  # already stricter than the base: kept
    assert merged.count("overrides:") == 1 and merged.count("minimumReleaseAge: 20160") == 1
    assert "pnpm-workspace.yaml minimumReleaseAge: 0 -> 20160" in report["strengthened"]
    assert any("overrides: added sharp" in row for row in report["strengthened"])
    # a security release younger than 14 days still installs: the base's exact-version exceptions join theirs
    assert "  - 'theirs@1.0.0'" in merged and "  - 'next@16.4.1'" in merged
    assert merged.count("minimumReleaseAgeExclude:") == 1


def test_a_commented_tsconfig_is_kept_when_strict_and_reported_when_rewritten(tmp_path):
    strict = "{\n  // ours\n  \"compilerOptions\": " + json.dumps(site_base.STRICT_TS) + "\n}\n"
    assert site_base.strict_tsconfig(strict) == (strict, "already strict")
    text, note = site_base.strict_tsconfig('{\n  // why\n  "compilerOptions": {"strict": false}\n}\n')
    assert json.loads(text)["compilerOptions"]["strict"] is True and "rewritten without them" in note
    (tmp_path / "package.json").write_text('{"name": "theirs"}')
    (tmp_path / "tsconfig.json").write_text('{\n  // why\n  "compilerOptions": {}\n}\n')
    report: dict = {}
    site_base.plan_files(tmp_path, scaffold_site.load_stacks(), "astro", "theirs", "cloudflare", report)
    assert any("comments" in n for n in report["notes"])


def test_age_exceptions_name_exact_versions_and_never_a_package():
    """A security fix younger than 14 days may skip the wait, but only that release: a name alone would let every
    future release of the package skip it too, which is the attack the rule exists to stop."""
    young = scaffold_site.load_stacks()["pnpm"].get("minimumReleaseAgeExclude") or []
    for spec in young:
        name, _, version = spec.rpartition("@")
        assert name and version[:1].isdigit() and "*" not in spec and "||" not in spec, spec


# ---------------------------------------------------------------- QA's code audit

def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


NUCLEI_ROWS = [  # the shape nuclei 3.11 prints (seen live): one row per missing header, the header in `matcher-name`
    {"template-id": "http-missing-security-headers", "matcher-name": "content-security-policy",
     "info": {"severity": "info"}, "matched-at": "https://p.example"},
    {"template-id": "http-missing-security-headers", "matcher-name": "cross-origin-embedder-policy",
     "info": {"severity": "info"}, "matched-at": "https://p.example"},
]
SEMGREP = {"results": [{"check_id": "a.b.react-dangerouslysetinnerhtml", "path": "src/Bad.tsx", "start": {"line": 4},
                        "extra": {"severity": "ERROR"}},
                       {"check_id": "a.b.jsx-not-internationalized", "path": "src/a.tsx", "start": {"line": 8},
                        "extra": {"severity": "INFO"}}],
           "errors": [{"level": "warn", "type": "PartialParsing", "message": "skipped one construct"}]}


def install_fake(tools: Path, name: str, body: str) -> None:
    """A fake scanner registered at its pin, the way security_tools.py records a real install."""
    binary = fake_bin(tools / "bin", name, body)
    pin = security_tools.PINS[name]["version"]
    digest = "" if name == "semgrep" else f" {sha(binary.read_bytes())}"
    (tools / "bin" / f"{name}.version").write_text(pin + digest)


def audit_fixture(tmp: Path, failing_step: str | None, *, base_branch: str = "main") -> tuple[Path, Path, dict]:
    """A site folder holding a repo on web/<ID>, a fake pnpm that fails one gate step, semgrep and nuclei at pins."""
    site, repo, tools = tmp / "acme", tmp / "acme" / "repo", tmp / "tools"
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", base_branch)
    git(repo, "config", "user.email", "bot@example.invalid")
    git(repo, "config", "user.name", "bot")
    (repo / "package.json").write_text("{}")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    if base_branch != f"web/{WORK_ID}":
        git(repo, "switch", "-q", "-c", f"web/{WORK_ID}")
    (repo / "src").mkdir()
    (repo / "src" / "a.ts").write_text("export const a = 1;\n")
    (repo / "src" / "a.test.ts").write_text("export const t = 1;\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "feat")
    fail = (f'if [ "$3" = "quality:{failing_step}" ]; then echo "{failing_step} broke: 3 problems"; exit 1; fi\n'
            if failing_step else "")
    fake_bin(tmp / "bin", "pnpm", fail + "exit 0\n")
    install_fake(tools, "semgrep", f"cat <<'EOF'\n{json.dumps(SEMGREP)}\nEOF\n")
    install_fake(tools, "nuclei", "".join(f"echo '{json.dumps(r)}'\n" for r in NUCLEI_ROWS))
    (tools / "nuclei-templates").mkdir()
    (tools / "nuclei-templates" / ".ready").write_text(security_tools.PINS["nuclei"]["templates"])
    env = {**os.environ, "PATH": f"{tmp / 'bin'}{os.pathsep}{os.environ['PATH']}", "HERMES_WEB_TOOLS_DIR": str(tools)}
    return site, repo, env


def audit(site: Path, repo: Path, env: dict, *extra: str, root: bool = True, cwd: Path | None = None):
    argv = [sys.executable, "-I", str(SCRIPTS / "code_audit.py"), "--id", WORK_ID, "--repo", str(repo)]
    return subprocess.run(argv + (["--root", str(site)] if root else []) + list(extra), capture_output=True, text=True,
                          env=env, timeout=300, cwd=cwd)


def report_of(site: Path) -> dict:
    return json.loads((site / "reviews" / f"{WORK_ID}-r0" / "code-checks.json").read_text())


def test_the_audit_names_the_failed_step_the_sast_finding_and_the_missing_headers(tmp_path):
    site, repo, env = audit_fixture(tmp_path, "deps")
    done = audit(site, repo, env, "--url", "https://p.example")
    assert done.returncode == 0, done.stdout + done.stderr
    report = report_of(site)
    assert report["steps"]["deps"]["ok"] is False and "deps broke" in " ".join(report["steps"]["deps"]["tail"])
    assert all(report["steps"][s]["ok"] for s in report["steps"] if s != "deps")
    critical = "\n".join(report["critical"])
    assert "gate step deps failed" in critical
    assert report["sast"]["ran"] is True  # a partial-parse warning is not a failed scan
    assert "sast: src/Bad.tsx:4 react-dangerouslysetinnerhtml" in critical and "jsx-not-internationalized" not in critical
    assert "content-security-policy" in critical and "cross-origin-embedder-policy" not in critical
    assert report["diff"]["files"] == 2 and report["diff"]["tests_touched"] == 1


def test_hsts_is_required_on_https_only(tmp_path):
    """A local http preview cannot send HSTS; a deployed https preview must."""
    site, repo, env = audit_fixture(tmp_path, None)
    row = {**NUCLEI_ROWS[0], "matcher-name": "strict-transport-security"}
    install_fake(tmp_path / "tools", "nuclei", f"echo '{json.dumps(row)}'\n")
    audit(site, repo, env, "--url", "http://localhost:4321")
    assert not any("strict-transport-security" in c for c in report_of(site)["critical"])
    audit(site, repo, env, "--url", "https://p.example")
    assert any("strict-transport-security" in c for c in report_of(site)["critical"])


@pytest.mark.parametrize("scanner, body", [
    ("semgrep", "echo 'semgrep: fatal: rules could not be downloaded'\nexit 2\n"),
    ("semgrep", "cat <<'EOF'\n" + json.dumps({"results": [], "errors": [
        {"level": "error", "type": "Timeout", "message": "src/big.ts timed out"}]}) + "\nEOF\n"),
    ("semgrep", "echo '" + json.dumps({"results": []}) + "'\nexit 2\n"),
    ("nuclei", "echo '[FTL] could not read templates' >&2\nexit 1\n"),
], ids=["semgrep-crashed", "semgrep-lost-a-file", "semgrep-json-then-failed", "nuclei-errored"])
def test_a_scanner_that_failed_is_a_critical_finding_not_a_clean_pass(tmp_path, scanner, body):
    site, repo, env = audit_fixture(tmp_path, None)
    install_fake(tmp_path / "tools", scanner, body)
    done = audit(site, repo, env, "--url", "https://p.example")
    assert done.returncode == 0
    expect = "sast did not run" if scanner == "semgrep" else "dast did not run"
    assert any(c.startswith(expect) for c in json.loads(done.stdout)["critical"]), done.stdout


def test_a_scanner_that_cannot_be_installed_is_a_critical_finding(tmp_path):
    site, repo, env = audit_fixture(tmp_path, None)
    (tmp_path / "tools" / "bin" / "semgrep.version").write_text("0.0.0")  # not the pin: it must reinstall, and cannot
    env["PATH"] = f"{tmp_path / 'bin'}:/usr/bin:/bin"  # no uv here
    done = audit(site, repo, env)
    assert done.returncode == 0
    assert any(c.startswith("sast did not run") for c in json.loads(done.stdout)["critical"])


def test_a_diff_that_cannot_be_read_is_a_critical_finding(tmp_path):
    """A repo pushed only as web/<ID> has no main to compare with: the code lens would have nothing to judge."""
    site, repo, env = audit_fixture(tmp_path, None, base_branch=f"web/{WORK_ID}")
    done = audit(site, repo, env)
    assert done.returncode == 0
    assert any(c.startswith("diff could not be read") for c in json.loads(done.stdout)["critical"])


def test_the_report_lands_in_the_site_folder_and_never_beside_another_tree(tmp_path):
    site, repo, env = audit_fixture(tmp_path, None)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    assert audit(site, repo, env, root=False, cwd=elsewhere).returncode == 0
    assert report_of(site)["id"] == WORK_ID and not (elsewhere / "reviews").exists()  # the repo's parent is the site
    refused = audit(elsewhere, repo, env)
    assert refused.returncode == 1 and "does not hold the repo" in refused.stdout


def test_the_audit_refuses_a_repo_on_the_wrong_branch(tmp_path):
    site, repo, env = audit_fixture(tmp_path, None)
    git(repo, "switch", "-q", "main")
    done = audit(site, repo, env)
    assert done.returncode == 1 and "expected web/" in done.stdout
    assert not (site / "reviews").exists()
