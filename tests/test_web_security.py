"""The web squad's security layer, exercised the way the bots use it: scanners from Homebrew, the repo's three
security gates, the headers every site ships, and QA's code audit.

Each test describes what must hold when a bot uses the feature, and fails when the feature breaks. Fake scanners
reproduce the real tools' exit codes and output shapes (checked against osv-scanner 2.6, gitleaks 8.30, nuclei 3.11
and semgrep 1.180); the real binaries run in the `real_toolchain` tests of test_web_base.py.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
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


# ---------------------------------------------------------------- scanners from their official installer

@pytest.fixture
def only(tmp_path, monkeypatch):
    """security_tools sees only the folder this test fills: no real Homebrew or scanner of this machine leaks in."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("HERMES_WEB_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setattr(security_tools, "which", lambda tool: shutil.which(tool, path=str(bin_dir)))
    return bin_dir


def fake_brew(bin_dir: Path, log: Path, installs: dict[str, str]) -> None:
    """A Homebrew that records each call and, for `install <formula>`, drops that formula's binary next to it."""
    cases = "".join(f'  {formula}) printf \'#!/bin/sh\\necho "{tool} 1.2.3"\\n\' > "{bin_dir}/{tool}"; '
                    f'chmod +x "{bin_dir}/{tool}";;\n' for formula, tool in installs.items())
    fake_bin(bin_dir, "brew", f'echo "$@" >> "{log}"\n[ "$1" = install ] || exit 1\n'
                              f'case "$2" in\n{cases}  *) echo "Error: No formula $2"; exit 1;;\nesac\n')


def test_a_missing_scanner_is_installed_by_homebrew_and_reused_after(only, tmp_path):
    """The bots install scanners the way a person would: `brew install`, which also keeps them current. A second
    run finds the installed tool and never calls Homebrew again."""
    log = tmp_path / "brew.log"
    fake_brew(only, log, {"gitleaks": "gitleaks", "osv-scanner": "osv-scanner"})
    rows = [security_tools.ensure(t) for t in ("gitleaks", "osv-scanner")]
    assert all(r["ready"] for r in rows), rows
    assert log.read_text().splitlines() == ["install gitleaks", "install osv-scanner"]
    assert rows[0]["version"] == "gitleaks 1.2.3"
    again = security_tools.ensure("gitleaks")
    assert again["ready"] and again["detail"] == "already installed"
    assert log.read_text().count("install") == 2, "an installed scanner is never reinstalled"


def test_without_homebrew_nothing_is_downloaded_and_the_bot_is_told_how(only, tmp_path):
    row = security_tools.ensure("gitleaks")
    assert row["ready"] is False and "https://brew.sh" in row["detail"] and "brew install gitleaks" in row["detail"]
    assert not any(only.iterdir()) and not (tmp_path / "tools").exists(), "no binary fetched by the squad itself"


def test_a_failed_homebrew_install_is_not_ready(only, tmp_path):
    log = tmp_path / "brew.log"
    fake_brew(only, log, {})  # Homebrew answers, but has no such formula: the scanner never appears
    row = security_tools.ensure("osv-scanner")
    assert row["ready"] is False and "No formula osv-scanner" in row["detail"]


def test_nuclei_templates_come_from_nuclei_else_the_official_repository(only, tmp_path):
    """nuclei's own updater gives up after 60 s on a slow link; git has no such cap, so the squad falls back to a
    shallow clone of the official template repository, never to its own download."""
    fake_bin(only, "nuclei", 'echo "[FTL] context deadline exceeded"\nexit 1\n')  # the updater fails like it did
    calls = tmp_path / "git.log"
    fake_bin(only, "git", f'echo "$@" >> "{calls}"\nfor last; do :; done\n'
                          'mkdir -p "$last/http/exposures" && echo "id: env" > "$last/http/exposures/env.yaml"\n')
    assert security_tools.templates_ready() is False
    row = security_tools.ensure_templates()
    assert row.get("ready") is not False and security_tools.templates_ready() is True, row
    argv = calls.read_text().split()
    assert argv[:3] == ["clone", "--depth", "1"] and security_tools.CONFIG["nuclei_templates"] in argv
    assert security_tools.ensure_templates() == {}, "fresh templates are not fetched again"


def test_a_failed_refresh_keeps_the_templates_already_there(only, tmp_path):
    folder = tmp_path / "tools" / "nuclei-templates"
    (folder / "http").mkdir(parents=True)
    (folder / "http" / "a.yaml").write_text("id: a")
    stamp = folder / ".fetched"
    stamp.write_text("old")
    os.utime(stamp, (0, 0))  # a week old: due for a refresh
    fake_bin(only, "nuclei", "exit 1\n")
    fake_bin(only, "git", "exit 128\n")  # offline
    row = security_tools.ensure_templates()
    assert row.get("ready") is not False and (folder / "http" / "a.yaml").is_file()


def test_status_does_not_call_nuclei_ready_without_its_templates(only):
    fake_bin(only, "nuclei", 'echo "Nuclei Engine Version: v3.11.1"\n')
    done = subprocess.run([sys.executable, "-I", str(SCRIPTS / "security_tools.py"), "status"], capture_output=True,
                          text=True, env={**os.environ, "PATH": f"{only}{os.pathsep}/usr/bin:/bin",
                                          "HERMES_WEB_TOOLS_DIR": str(only.parent / "tools")})
    row = next(r for r in json.loads(done.stdout)["tools"] if r["tool"] == "nuclei")
    assert row["path"] == str(only / "nuclei") and row["ready"] is False and done.returncode == 1


def test_every_scanner_has_an_official_formula_and_no_pinned_binary():
    """The squad holds no scanner version, digest or download URL of its own: Homebrew installs and updates them."""
    assert set(security_tools.FORMULAE) == set(security_tools.TOOLS)
    source = (SCRIPTS / "security_tools.py").read_text()
    for gone in ("urlopen", "sha256", "tarfile", "zipfile"):
        assert gone not in source, gone


# ---------------------------------------------------------------- the repo's security gates

def gate(cwd: Path, bin_dir: Path, name: str, path: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PATH": path or f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           "HOMEBREW_PREFIX": str(cwd / "no-homebrew"), "HERMES_REAL_HOME": str(cwd / "no-home")}
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

def create_cli_output(repo: Path, stack: str) -> None:
    """What each create CLI leaves in the repo (trimmed from real runs of create-astro, create-next-app and the
    TanStack CLI): the base is laid on top of it."""
    repo.mkdir(parents=True, exist_ok=True)
    pkg = {"astro": {"name": "acme", "type": "module", "dependencies": {"astro": "^7.4.2"}},
           "nextjs": {"name": "acme", "dependencies": {"next": "16.4.2", "react": "19.3.0"},
                      "devDependencies": {"typescript": "^5"}},
           "tanstack": {"name": "acme", "dependencies": {"@tanstack/react-start": "^1.168.60"},
                        "pnpm": {"onlyBuiltDependencies": ["esbuild", "workerd"]}}}[stack]
    (repo / "package.json").write_text(json.dumps(pkg))
    (repo / "tsconfig.json").write_text('{"extends": "astro/tsconfigs/strict", "include": ["**/*"]}')
    if stack == "nextjs":
        (repo / "next.config.ts").write_text('import type { NextConfig } from "next";\n\n'
                                             "const nextConfig: NextConfig = {\n  /* config options here */\n};\n\n"
                                             "export default nextConfig;\n")


def test_the_base_carries_every_security_setting_and_header(tmp_path):
    stacks = scaffold_site.load_stacks()
    create_cli_output(tmp_path, "astro")
    files, _ = site_base.plan_files(tmp_path, stacks, "astro", "acme", "cloudflare", created=True)
    pkg = json.loads(files["package.json"])["scripts"]
    assert pkg["quality"].split(" && ") == [f"pnpm run quality:{s}" for s in site_base.GATE]
    assert pkg["quality:deps"] == "node tools/quality/security.mjs deps"
    assert pkg["quality:typecov"].startswith("tools/quality/node_modules/.bin/type-coverage")
    assert "--strict" in pkg["quality:typecov"] and pkg["format"] == "biome check --write ."
    for name in ("pnpm-workspace.yaml", "tools/quality/pnpm-workspace.yaml"):
        yaml = files[name]
        for line in ("minimumReleaseAge: 4320", "trustPolicy: no-downgrade", "strictDepBuilds: true",
                     "blockExoticSubdeps: true", "  - chromium-bidi", '  sharp: ">=0.35.5"',
                     "allowBuilds:", "  'lefthook': true"):
            assert line in yaml.splitlines(), (name, line)
    assert {"eslint-plugin-security", "eslint-plugin-no-unsanitized", "type-coverage"} <= set(
        stacks["quality_tools"]["packages"])
    assert "domain-is-framework-free" in files["tools/quality/dependency-cruiser.cjs"]
    headers = files["public/_headers"]
    for header in ("Strict-Transport-Security", "Content-Security-Policy", "X-Frame-Options", "X-Content-Type-Options",
                   "Referrer-Policy", "Permissions-Policy", "Cross-Origin-Opener-Policy"):
        assert f"  {header}: " in headers, header
    create_cli_output(tmp_path / "v", "astro")
    vercel, _ = site_base.plan_files(tmp_path / "v", stacks, "astro", "acme", "vercel", created=True)
    assert "public/_headers" not in vercel and "frame-ancestors 'none'" in vercel["vercel.json"]
    create_cli_output(tmp_path / "n", "nextjs")
    nxt, _ = site_base.plan_files(tmp_path / "n", stacks, "nextjs", "acme", "cloudflare", created=True)
    config = nxt["next.config.ts"]
    assert "headers(): Promise<" in config and "Content-Security-Policy" in config
    # the CLI's file, extended; its comment goes because the zero-comments ratchet counts it
    assert "/* config options here */" not in config and config.count("const nextConfig") == 1


def test_an_existing_repo_cannot_keep_weaker_supply_chain_settings(tmp_path):
    """A repo the bots adopt keeps its own content, but never a supply-chain setting weaker than the base's."""
    (tmp_path / "package.json").write_text('{"name": "theirs"}')
    (tmp_path / "pnpm-workspace.yaml").write_text(
        "packages:\n  - apps/*\nminimumReleaseAge: 0\ntrustPolicy: off\nstrictDepBuilds: false\n"
        "trustPolicyIgnoreAfter: 999999\noverrides:\n  left: 1.0.0\nminimumReleaseAgeExclude:\n  - 'theirs@1.0.0'\n"
        "allowBuilds:\n  esbuild: true\n")
    report: dict = {}
    files, _ = site_base.plan_files(tmp_path, scaffold_site.load_stacks(), "astro", "theirs", "cloudflare", report)
    merged = files["pnpm-workspace.yaml"].splitlines()
    assert "packages:" in merged and "  - apps/*" in merged and "  left: 1.0.0" in merged  # theirs stays
    for line in ("minimumReleaseAge: 4320", "trustPolicy: no-downgrade", "strictDepBuilds: true",
                 "blockExoticSubdeps: true", '  sharp: ">=0.35.5"'):
        assert line in merged, line
    assert "trustPolicyIgnoreAfter: 999999" in merged  # already stricter than the base: kept
    assert merged.count("overrides:") == 1 and merged.count("minimumReleaseAge: 4320") == 1
    assert "pnpm-workspace.yaml minimumReleaseAge: 0 -> 4320" in report["strengthened"]
    assert any("overrides: added sharp" in row for row in report["strengthened"])
    assert "  - 'theirs@1.0.0'" in merged and merged.count("minimumReleaseAgeExclude:") == 1  # theirs stays
    # the build approvals the base needs join their allowBuilds block, in its form, never a second block
    assert merged.count("allowBuilds:") == 1 and "  esbuild: true" in merged and "  'lefthook': true" in merged
    assert "onlyBuiltDependencies:" not in merged, "pnpm 12 fails on a setting it does not know"


def test_a_commented_tsconfig_is_kept_when_strict_and_reported_when_rewritten(tmp_path):
    strict = ("{\n  // ours\n  \"compilerOptions\": " + json.dumps(site_base.STRICT_TS)
              + ',\n  "exclude": ' + json.dumps(["node_modules", *site_base.TS_EXCLUDE]) + "\n}\n")
    assert site_base.strict_tsconfig(strict) == (strict, "already strict")
    text, note = site_base.strict_tsconfig('{\n  // why\n  "compilerOptions": {"strict": false}\n}\n')
    assert json.loads(text)["compilerOptions"]["strict"] is True and "rewritten without them" in note
    (tmp_path / "package.json").write_text('{"name": "theirs"}')
    (tmp_path / "tsconfig.json").write_text('{\n  // why\n  "compilerOptions": {}\n}\n')
    report: dict = {}
    site_base.plan_files(tmp_path, scaffold_site.load_stacks(), "astro", "theirs", "cloudflare", report)
    assert any("comments" in n for n in report["notes"])


def test_the_base_waits_three_days_and_holds_no_static_exception():
    """3 days skips the attacks seen so far (pulled within hours to two days); a fix younger than that is let in
    by security_fix.py when an advisory asks for it, never by a list someone forgets to empty."""
    pnpm = scaffold_site.load_stacks()["pnpm"]
    assert pnpm["minimumReleaseAge"] == 3 * 24 * 60
    assert not pnpm.get("minimumReleaseAgeExclude") and "security_fixes" not in scaffold_site.load_stacks()


# ---------------------------------------------------------------- security fixes that never wait

import security_fix  # noqa: E402

NEXT_ADVISORY = {"id": "GHSA-2464-fhr4-w9xw", "affected": [  # the shape osv-scanner 2.6 printed for next 16.4.0
    {"package": {"name": "next", "ecosystem": "npm"},
     "ranges": [{"type": "SEMVER", "events": [{"introduced": "10.0.0"}, {"fixed": "15.5.28"}]}]},
    {"package": {"name": "next", "ecosystem": "npm"},
     "ranges": [{"type": "SEMVER", "events": [{"introduced": "16.0.0"}, {"fixed": "16.4.1"}]}]}]}


def osv_report(name: str, version: str, *vulns: dict) -> dict:
    return {"results": [{"packages": [{"package": {"name": name, "version": version, "ecosystem": "npm"},
                                       "vulnerabilities": list(vulns)}]}]}


def test_the_fix_is_the_lowest_release_clearing_every_advisory_on_the_installed_line():
    dos = {"id": "GHSA-p3m5", "affected": [{"package": {"name": "next"}, "ranges": [
        {"events": [{"introduced": "16.0.0"}, {"fixed": "16.4.2"}]}]}]}
    fixes, unfixable = security_fix.plan_fixes(osv_report("next", "16.4.0", NEXT_ADVISORY, dos))
    assert fixes == [{"name": "next", "installed": "16.4.0", "fixed": "16.4.2", "advisories": ["GHSA-2464-fhr4-w9xw", "GHSA-p3m5"]}]
    assert not unfixable
    alone, _ = security_fix.plan_fixes(osv_report("next", "16.4.0", NEXT_ADVISORY))
    assert alone[0]["fixed"] == "16.4.1", "the range that holds 16.4.0, never the 15.x fix of another range"
    old_line, _ = security_fix.plan_fixes(osv_report("next", "15.2.0", NEXT_ADVISORY))
    assert old_line[0]["fixed"] == "15.5.28", "a site on 15 gets the 15 fix, not a forced major jump"
    none = {"id": "GHSA-nofix", "affected": [{"package": {"name": "left"}, "ranges": [{"events": [{"introduced": "0"}]}]}]}
    fixes, unfixable = security_fix.plan_fixes(osv_report("left", "1.0.0", none))
    assert not fixes and unfixable[0]["advisories"] == ["GHSA-nofix"]


def test_only_the_fix_and_its_own_family_may_skip_the_wait():
    """next@16.4.1 ships with @next/env@16.4.1 and its binaries; anything else pnpm calls young stays out."""
    young = [("next", "16.4.1"), ("@next/env", "16.4.1"), ("@next/swc-darwin-arm64", "16.4.1"),
             ("@next/env", "16.4.0"), ("evil", "1.0.0"), ("nextjs-helper", "16.4.1")]
    allowed, refused = security_fix.siblings(young, "next", "16.4.1")
    assert allowed == ["next@16.4.1", "@next/env@16.4.1", "@next/swc-darwin-arm64@16.4.1"]
    assert refused == ["@next/env@16.4.0", "evil@1.0.0", "nextjs-helper@16.4.1"]
    scoped, _ = security_fix.siblings([("@astrojs/node", "9.1.2"), ("@astrojs/internal", "9.1.2")], "@astrojs/node", "9.1.2")
    assert scoped == ["@astrojs/node@9.1.2", "@astrojs/internal@9.1.2"]


def fix_fixture(tmp: Path, extra_young: str = "", direct: bool = True) -> tuple[Path, dict]:
    """A site whose next 16.4.0 is vulnerable: osv-scanner reports it until pnpm installs the fix; pnpm refuses
    the fix until next@16.4.1 and @next/env@16.4.1 are excepted (as pnpm 12 words it); npm knows publish times."""
    site, repo, bin_dir = tmp / "acme", tmp / "acme" / "repo", tmp / "bin"
    repo.mkdir(parents=True)
    (site / "site.yaml").write_text("slug: acme\n")
    deps = {"dependencies": {"next": "16.4.0"}} if direct else {}
    (repo / "package.json").write_text(json.dumps({"name": "acme", **deps}))
    (repo / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'\n")
    (repo / "pnpm-workspace.yaml").write_text("minimumReleaseAge: 4320\nminimumReleaseAgeExclude:\n  - 'aged@1.0.0'\n")
    state = tmp / "fixed"
    report = json.dumps(osv_report("next", "16.4.0", NEXT_ADVISORY))
    fake_bin(bin_dir, "osv-scanner", f'if [ -f "{state}" ]; then echo "{{}}"; exit 0; fi\n'
                                     f"cat <<'EOF'\n{report}\nEOF\necho 'Scanned 73 packages' >&2\nexit 1\n")
    fake_bin(bin_dir, "npm", 'case "$2" in aged@1.0.0) echo \'{"1.0.0": "2026-01-01T00:00:00Z"}\';; '
                             '*) echo "{}";; esac\n')
    young = ["next@16.4.1", "@next/env@16.4.1", *([extra_young] if extra_young else [])]
    lines = "".join(f'  echo "    {spec} was published at 2026-10-22T10:00:00Z, within the minimumReleaseAge cutoff"\n'
                    for spec in young)
    fake_bin(bin_dir, "pnpm", f'echo "$@" >> "{tmp}/pnpm.log"\nmissing={1 if extra_young else 0}\n'
                              "grep -q \"'next@16.4.1'\" pnpm-workspace.yaml || missing=1\n"
                              "grep -q \"'@next/env@16.4.1'\" pnpm-workspace.yaml || missing=1\n"
                              'if [ $missing = 1 ]; then\n  echo "Error: ERR_PNPM_NO_MATURE_MATCHING_VERSION"\n'
                              f'{lines}  exit 1\nfi\ntouch "{state}"\n')
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}/usr/bin:/bin", "HOMEBREW_PREFIX": str(tmp / "no-brew")}
    return repo, env


def run_fix(repo: Path, env: dict) -> tuple[int, dict]:
    done = subprocess.run([sys.executable, "-I", str(SCRIPTS / "security_fix.py"), "--repo", str(repo)],
                          capture_output=True, text=True, env=env, timeout=120)
    return done.returncode, json.loads(done.stdout)


def test_a_young_security_fix_is_installed_now_as_exact_releases_and_logged(tmp_path):
    repo, env = fix_fixture(tmp_path)
    code, out = run_fix(repo, env)
    assert code == 0 and out["ok"], out
    fix = out["fixed"][0]
    assert fix["fixed"] == "16.4.1" and fix["how"] == "direct"
    assert fix["excepted"] == ["next@16.4.1", "@next/env@16.4.1"]
    ws = (repo / "pnpm-workspace.yaml").read_text().splitlines()
    assert "  - 'next@16.4.1'" in ws and "  - 'next'" not in ws, "an exact release, never the name alone"
    assert "  - 'aged@1.0.0'" not in ws and out["pruned"] == ["aged@1.0.0"], "an exception past 3 days is removed"
    assert "add next@^16.4.1" in (tmp_path / "pnpm.log").read_text()
    log = (repo.parent / "decisions.md").read_text()
    assert "next 16.4.0 -> 16.4.1 (GHSA-2464-fhr4-w9xw)" in log and "next@16.4.1" in log


def test_an_unrelated_young_release_is_never_let_in_with_a_fix(tmp_path):
    repo, env = fix_fixture(tmp_path, extra_young="evil@9.9.9")
    code, out = run_fix(repo, env)
    assert code == 1 and not out["ok"] and "evil@9.9.9" in out["failed"][0]["refused"]
    assert "evil" not in (repo / "pnpm-workspace.yaml").read_text()


def test_a_vulnerable_transitive_package_is_fixed_with_an_override(tmp_path):
    repo, env = fix_fixture(tmp_path, direct=False)
    code, out = run_fix(repo, env)
    assert code == 0 and out["fixed"][0]["how"] == "override", out
    assert "  'next': \"^16.4.1\"" in (repo / "pnpm-workspace.yaml").read_text()
    assert "add " not in (tmp_path / "pnpm.log").read_text(), "a transitive package is never made a direct one"


def test_a_scan_that_cannot_run_is_not_clean(tmp_path):
    repo, env = fix_fixture(tmp_path)
    (tmp_path / "bin" / "osv-scanner").unlink()
    code, out = run_fix(repo, env)
    assert code == 2 and "osv-scanner is not installed" in out["error"]


# ---------------------------------------------------------------- versions typed from memory

FRESH_MJS = CONTRACT / "templates" / "quality" / "tools" / "quality" / "fresh.mjs"


def fresh_repo(tmp: Path, deps: dict, locked: dict, outdated: dict, times: dict) -> tuple[Path, dict]:
    """package.json, a pnpm 12 lockfile (two YAML documents) and a pnpm that answers `outdated` and `view time`."""
    (tmp / "package.json").write_text(json.dumps({"name": "acme", "dependencies": deps}))
    rows = "".join(f"      {n}:\n        specifier: {s}\n        version: 1.0.0\n" for n, s in locked.items())
    (tmp / "pnpm-lock.yaml").write_text("---\nlockfileVersion: '9.0'\n\nimporters:\n\n  .:\n    configDependencies: {}\n\n"
                                        "---\nlockfileVersion: '9.0'\n\nimporters:\n\n  .:\n    dependencies:\n"
                                        + rows + "\npackages:\n\n  'react@17.0.2':\n    resolution: {}\n")
    (tmp / "pnpm-workspace.yaml").write_text("minimumReleaseAge: 4320\n")
    fake_bin(tmp / "bin", "pnpm", f"if [ \"$1\" = outdated ]; then echo '{json.dumps(outdated)}'; exit 1; fi\n"
                                  f"echo '{json.dumps(times)}'\n")
    return tmp, {**os.environ, "PATH": f"{tmp / 'bin'}{os.pathsep}{os.environ['PATH']}"}


def fresh(cwd: Path, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([shutil.which("node"), str(FRESH_MJS), "--json"], cwd=cwd, capture_output=True, text=True,
                          env=env, timeout=60)


def days_ago(days: float) -> str:
    import datetime
    stamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    return stamp.strftime("%Y-%m-%dT%H:%M:%S.000Z")


@needs_node
def test_a_major_typed_from_memory_fails_the_gate(tmp_path):
    """react 17 from memory, while 19 has been installable for months: the gate names it and the command to fix."""
    repo, env = fresh_repo(tmp_path, {"react": "^17.0.2"}, {"react": "^17.0.2"},
                           {"react": {"current": "17.0.2", "latest": "19.3.1", "wanted": "17.0.2"}},
                           {"17.0.2": days_ago(1500), "19.0.0": days_ago(300), "19.3.1": days_ago(20)})
    done = fresh(repo, env)
    assert done.returncode == 1 and json.loads(done.stdout) == [
        {"name": "react", "kind": "behind", "current": "17", "mature": "19",
         "detail": "on 17, the newest line is 19: pnpm add react@19"}]


@needs_node
def test_a_major_too_new_to_install_is_not_demanded(tmp_path):
    """The gate never asks for a release pnpm itself would refuse: react 20 out yesterday is not yet installable."""
    repo, env = fresh_repo(tmp_path, {"react": "^19.3.1"}, {"react": "^19.3.1"},
                           {"react": {"current": "19.3.1", "latest": "20.0.0", "wanted": "19.3.1"}},
                           {"19.3.1": days_ago(20), "20.0.0": days_ago(1)})
    assert fresh(repo, env).returncode == 0


@needs_node
def test_a_hand_written_line_and_an_exact_pin_fail_the_gate(tmp_path):
    repo, env = fresh_repo(tmp_path, {"zod": "^3.22.0", "next": "16.4.0"}, {"next": "16.4.0"}, {}, {})
    findings = {(f["name"], f["kind"]) for f in json.loads(fresh(repo, env).stdout)}
    assert findings == {("zod", "not-resolved"), ("next", "exact-pin")}


@needs_node
def test_an_exception_needs_its_reason(tmp_path):
    repo, env = fresh_repo(tmp_path, {"next": "16.4.0"}, {"next": "16.4.0"}, {}, {})
    allow = tmp_path / "tools" / "quality" / "fresh-allow.json"
    allow.parent.mkdir(parents=True)
    allow.write_text(json.dumps({"next": "held at next@16.4.0: 16.4.1 lost its provenance"}))
    assert fresh(repo, env).returncode == 0
    allow.write_text(json.dumps({"next": " "}))
    done = fresh(repo, env)
    assert done.returncode == 2 and "needs its reason" in done.stderr


@needs_node
def test_a_registry_that_does_not_answer_is_not_current(tmp_path):
    repo, env = fresh_repo(tmp_path, {"react": "^17.0.2"}, {"react": "^17.0.2"}, {}, {})
    fake_bin(tmp_path / "bin", "pnpm", "echo 'ERR_PNPM_META_FETCH_FAIL'\nexit 1\n")
    assert fresh(repo, env).returncode == 2


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


def install_fake(bin_dir: Path, name: str, body: str) -> None:
    """A fake scanner where Homebrew would leave the real one: on PATH."""
    fake_bin(bin_dir, name, body)


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
    install_fake(tmp / "bin", "semgrep", f"cat <<'EOF'\n{json.dumps(SEMGREP)}\nEOF\n")
    install_fake(tmp / "bin", "nuclei", "".join(f"echo '{json.dumps(r)}'\n" for r in NUCLEI_ROWS))
    (tools / "nuclei-templates" / "http").mkdir(parents=True)
    (tools / "nuclei-templates" / "http" / "headers.yaml").write_text("id: http-missing-security-headers")
    (tools / "nuclei-templates" / ".fetched").write_text("today")
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
    install_fake(tmp_path / "bin", "nuclei", f"echo '{json.dumps(row)}'\n")
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
    install_fake(tmp_path / "bin", scanner, body)
    done = audit(site, repo, env, "--url", "https://p.example")
    assert done.returncode == 0
    expect = "sast did not run" if scanner == "semgrep" else "dast did not run"
    assert any(c.startswith(expect) for c in json.loads(done.stdout)["critical"]), done.stdout


def test_a_scanner_that_cannot_be_installed_is_a_critical_finding(only, tmp_path):
    """No semgrep and a Homebrew that cannot install it: the code lens must say SAST never ran, not report a clean
    scan."""
    import code_audit
    fake_brew(only, tmp_path / "brew.log", {})
    got = code_audit.sast(tmp_path, code_audit.Budget(60))
    assert got["ran"] is False and "No formula semgrep" in got["reason"]
    assert (tmp_path / "brew.log").read_text().strip() == "install semgrep"


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
