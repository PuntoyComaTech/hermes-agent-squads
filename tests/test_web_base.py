"""The web squad's project base, live tab, progress saves and logins, exercised the way the bots use them.

Fast tests drive the real scripts against temp git repos and fake CLIs on PATH. The `real_toolchain` tests install
the pinned toolchain with pnpm (network) and prove the gate rejects the bad practices it promises to block.
"""
import json
import os
import shutil
import socket
import stat
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "squads" / "web" / "skills" / "site-contract" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import site_base  # noqa: E402

WORK_ID = "acme-20261022-build-01"


def run(script: str, *args: str, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *args], capture_output=True, text=True,
                          timeout=600, env=env, cwd=cwd)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=True).stdout


def fake_bin(folder: Path, name: str, body: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def env_with(bin_dir: Path, tmp: Path) -> dict:
    return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}", "HERMES_HOME": str(tmp / "hh")}


# ---------------------------------------------------------------- strict base: what it writes

def test_a_new_site_gets_the_whole_quality_gate(tmp_path):
    stacks = site_base.sc.load_stacks()
    files, kept, fresh = site_base.plan_files(tmp_path, stacks, "astro", "acme", "cloudflare")
    assert fresh and not kept
    for config in ("biome.jsonc", "tools/quality/eslint.config.mjs", "tools/quality/dependency-cruiser.cjs",
                   ".jscpd.json", "knip.json", "lefthook.yml", "vitest.config.ts", "tools/quality/package.json"):
        assert config in files, config
    pkg = json.loads(files["package.json"])
    s = pkg["scripts"]
    assert s["quality"].split(" && ") == [f"pnpm run quality:{x}" for x in
                                          ("types", "lint", "sonar", "arch", "dupes", "unused", "typecov", "secrets",
                                           "licenses", "deps", "test")]
    assert s["quality:types"] == "astro check"
    assert s["quality:lint"].startswith("biome ci") and "--error-on-warnings" in s["quality:lint"]
    assert "eslint" in s["quality:sonar"] and "eslint.config.mjs" in s["quality:sonar"]
    assert "--max-warnings=0" in s["quality:sonar"]
    assert "depcruise" in s["quality:arch"] and "dependency-cruiser.cjs" in s["quality:arch"]
    assert s["quality:dupes"].startswith("jscpd") and s["quality:unused"] == "knip"
    assert s["quality:test"] == "vitest run --coverage"
    assert "src/lib/slug.test.ts" in files and "passWithNoTests: false" in files["vitest.config.ts"]
    assert "wrangler" in pkg["devDependencies"]  # provider cloudflare: wrangler runs from the repo, not global
    assert pkg["packageManager"].startswith("pnpm@")
    biome = files["biome.jsonc"]
    assert '"noExplicitAny": "error"' in biome and "noExcessiveCognitiveComplexity" in biome
    tsconfig = json.loads(files["tsconfig.json"])["compilerOptions"]
    assert tsconfig["strict"] and tsconfig["noUncheckedIndexedAccess"] and tsconfig["exactOptionalPropertyTypes"]
    assert "biome.json" not in files  # the scaffold's loose config never lands beside the strict one
    assert '"$schema"' in files["biome.jsonc"] and "\t" not in files["biome.jsonc"]  # shipped in its own format


def test_an_existing_repo_keeps_its_files_and_gains_the_gate(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps(
        {"name": "theirs", "scripts": {"lint": "their-lint", "dev": "vite", "quality": "echo ok"},
         "devDependencies": {"vitest": "4.0.0"}}))
    (tmp_path / "biome.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text('{\n  // a comment\n  "compilerOptions": {}\n}\n')
    stacks = site_base.sc.load_stacks()
    report: dict = {}
    files, kept, fresh = site_base.plan_files(tmp_path, stacks, "tanstack", "theirs", "vercel", report)
    assert not fresh
    assert "biome.json" in kept and "biome.jsonc" not in files and "src/router.tsx" not in files
    opts = json.loads(files["tsconfig.json"])["compilerOptions"]  # a tsconfig with comments is still made strict
    assert opts["strict"] is True and opts["exactOptionalPropertyTypes"] is True and not report.get("manual")
    pkg = json.loads(files["package.json"])
    assert pkg["scripts"]["lint"] == "their-lint"  # theirs wins outside the gate
    assert pkg["scripts"]["quality"].startswith("pnpm run quality:types")  # a weak old gate never survives
    assert report["replaced_scripts"] == ["quality"]
    assert pkg["devDependencies"]["vitest"] == "4.0.0"
    assert "quality" in pkg["scripts"] and "wrangler" not in pkg["devDependencies"]


def test_a_plain_tsconfig_is_made_strict(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "x"}')
    (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {"strict": false, "target": "ES2020"}}')
    files, _, _ = site_base.plan_files(tmp_path, site_base.sc.load_stacks(), "nextjs", "x", "cloudflare")
    opts = json.loads(files["tsconfig.json"])["compilerOptions"]
    assert opts["strict"] is True and opts["noUncheckedIndexedAccess"] is True and opts["target"] == "ES2020"


# ---------------------------------------------------------------- progress saves

@pytest.fixture
def site(tmp_path):
    site = tmp_path / "acme"
    repo = site / "repo"
    repo.mkdir(parents=True)
    (site / "site.yaml").write_text("slug: acme\n")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.email", "bot@example.invalid")
    git(repo, "config", "user.name", "bot")
    (repo / "README.md").write_text("acme\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "base")
    return site, repo


def test_each_finished_piece_is_a_commit_the_manager_can_see(site):
    site_dir, repo = site
    git(repo, "switch", "-q", "-c", f"web/{WORK_ID}")
    (repo / "hero.ts").write_text("export const hero = 1;\n")
    first = run("save_progress.py", "--repo", str(repo), "--id", WORK_ID, "--what", "hero section",
                "--paths", "hero.ts")
    assert first.returncode == 0, first.stdout + first.stderr
    (repo / "menu.ts").write_text("export const menu = 2;\n")
    second = run("save_progress.py", "--repo", str(repo), "--id", WORK_ID, "--what", "menu page", "--paths", "menu.ts")
    assert second.returncode == 0
    log = git(repo, "log", "--format=%s", f"main..web/{WORK_ID}").splitlines()
    assert log == [f"wip({WORK_ID}): menu page", f"wip({WORK_ID}): hero section"]
    progress = (site_dir / "milestones" / f"{WORK_ID}.progress.log").read_text().splitlines()
    assert [line.split(" ", 2)[2] for line in progress] == ["hero section", "menu page"]
    again = json.loads(run("save_progress.py", "--repo", str(repo), "--id", WORK_ID, "--what", "x",
                           "--paths", "hero.ts").stdout)
    assert again["saved"] is False and again["ok"] is True


def test_a_progress_save_never_lands_on_main(site):
    _, repo = site
    (repo / "x.ts").write_text("export const x = 1;\n")
    done = run("save_progress.py", "--repo", str(repo), "--id", WORK_ID, "--what", "x", "--paths", "x.ts")
    assert done.returncode == 1 and "never main" in done.stdout
    assert git(repo, "log", "--format=%s").splitlines() == ["base"]


def test_a_failing_hook_blocks_the_save_and_shows_why(site):
    _, repo = site
    git(repo, "switch", "-q", "-c", f"web/{WORK_ID}")
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'lint/suspicious/noExplicitAny: any is not allowed'\nexit 1\n")
    hook.chmod(0o755)
    (repo / "bad.ts").write_text("export const bad: any = 1;\n")
    done = run("save_progress.py", "--repo", str(repo), "--id", WORK_ID, "--what", "bad", "--paths", "bad.ts")
    out = json.loads(done.stdout)
    assert done.returncode == 1 and out["saved"] is False and "noExplicitAny" in out["tail"]
    assert git(repo, "log", "--format=%s").splitlines() == ["base"]


def test_a_save_commits_only_the_builders_own_files(site):
    """Two bots share the tree: the frontend's save must not sweep the backend's half-written route into its commit."""
    _, repo = site
    git(repo, "switch", "-q", "-c", f"web/{WORK_ID}")
    (repo / "src").mkdir()
    (repo / "src" / "Hero.tsx").write_text("export const Hero = 1;\n")
    (repo / "api.ts").write_text("export const half = \n")  # another bot, mid-edit
    done = run("save_progress.py", "--repo", str(repo), "--id", WORK_ID, "--what", "hero", "--paths", "src")
    assert done.returncode == 0, done.stdout
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == ["src/Hero.tsx"]
    assert "?? api.ts" in git(repo, "status", "--porcelain")


# ---------------------------------------------------------------- logins

def test_a_cf_that_says_logged_out_with_exit_0_is_not_a_login(tmp_path):
    """`cf auth whoami` and `wrangler whoami` exit 0 when logged out: the exit code alone would skip the login."""
    bin_dir = tmp_path / "bin"
    fake_bin(bin_dir, "cf", 'echo \'{"authenticated": false, "error": "Not logged in"}\'\nexit 0\n')
    fake_bin(bin_dir, "wrangler", "echo 'You are not authenticated. Please run `wrangler login`.'\nexit 0\n")
    fake_bin(bin_dir, "gh", "exit 1\n")
    done = run("web_access.py", "status", "gh", "cf", "wrangler", env=env_with(bin_dir, tmp_path))
    rows = {r["tool"]: r for r in json.loads(done.stdout)["tools"]}
    assert done.returncode == 1
    assert [rows[t]["logged_in"] for t in ("gh", "cf", "wrangler")] == [False, False, False]


def test_an_unknown_tool_is_a_usage_error_not_all_ready(tmp_path):
    done = run("web_access.py", "status", "bogus", env=env_with(tmp_path / "bin", tmp_path))
    assert done.returncode == 2 and "known:" in done.stderr


def test_a_cli_outside_the_bots_path_is_still_found(tmp_path):
    """A gateway or cron run has a bare PATH: gh in ~/.local/bin (like Homebrew or nvm) must not read as missing,
    or the bot would tell the user to install what they already have."""
    home = tmp_path / "home"
    fake_bin(home / ".local" / "bin", "gh", "exit 0\n")
    env = {"PATH": "/usr/bin:/bin", "HOME": str(home), "HERMES_REAL_HOME": str(home), "HERMES_HOME": str(tmp_path)}
    done = run("web_access.py", "status", "gh", env=env)
    row = json.loads(done.stdout)["tools"][0]
    assert row["installed"] is True  # on a bare PATH this is only true through the added install folders
    sys.path.insert(0, str(SCRIPTS))
    import toolpath
    old = os.environ.copy()
    try:
        os.environ.update({"PATH": "/usr/bin:/bin", "HERMES_REAL_HOME": str(home)})
        assert str(home / ".local" / "bin") in toolpath.augment_path().split(os.pathsep)
    finally:
        os.environ.clear()
        os.environ.update(old)


def test_an_existing_login_is_reused_without_starting_another(tmp_path):
    bin_dir = tmp_path / "bin"
    fake_bin(bin_dir, "cf", 'echo \'{"authenticated": true, "account": "x"}\'\n')
    fake_bin(bin_dir, "wrangler", "echo 'You are logged in with an OAuth Token.'\n")
    fake_bin(bin_dir, "gh", "exit 0\n")
    env = env_with(bin_dir, tmp_path)
    assert run("web_access.py", "status", env=env).returncode == 0
    done = run("web_access.py", "ensure", "cf", env=env)
    row = json.loads(done.stdout)
    assert done.returncode == 0 and row["ready"] is True and "login" not in row


def test_a_missing_login_is_started_and_its_page_handed_over(tmp_path):
    """The user gets one URL to open in the side tab, with the device code; the bot types nothing."""
    bin_dir = tmp_path / "bin"
    fake_bin(bin_dir, "cf", 'if [ "$2" = whoami ]; then echo \'{"authenticated": false}\'; exit 0; fi\n'
                            "printf 'To authorize cf, please visit:\\n\\n  https://dash.cloudflare.com/oauth2/device/"
                            "verify\\n\\nand enter the code:\\n\\n  Y7maNcRE\\n'\nsleep 30\n")
    fake_bin(bin_dir, "gh", 'if [ "$2" = status ]; then exit 1; fi\n'
                            "echo '! First copy your one-time code: AB12-CD34'\n"
                            "echo 'Open this URL to continue in your web browser: https://github.com/login/device'\n"
                            "sleep 30\n")
    env = env_with(bin_dir, tmp_path)
    try:
        cf = json.loads(run("web_access.py", "ensure", "cf", env=env).stdout)
        gh = json.loads(run("web_access.py", "ensure", "gh", env=env).stdout)
    finally:
        subprocess.run(["pkill", "-f", str(bin_dir)], check=False)
    assert cf["ready"] is False and cf["login"]["code"] == "Y7maNcRE"
    assert cf["login"]["url"] == "https://dash.cloudflare.com/oauth2/device/verify?user_code=Y7maNcRE"
    assert gh["login"]["url"] == "https://github.com/login/device" and gh["login"]["code"] == "AB12-CD34"


def test_asking_again_returns_the_waiting_login_instead_of_a_second_one(tmp_path):
    bin_dir = tmp_path / "bin"
    counter = tmp_path / "starts"
    fake_bin(bin_dir, "gh", f'if [ "$2" = status ]; then exit 1; fi\necho x >> "{counter}"\n'
                            "echo '! First copy your one-time code: AB12-CD34'\n"
                            "echo 'Open this URL to continue in your web browser: https://github.com/login/device'\n"
                            "sleep 30\n")
    env = env_with(bin_dir, tmp_path)
    try:
        first = json.loads(run("web_access.py", "ensure", "gh", env=env).stdout)
        second = json.loads(run("web_access.py", "ensure", "gh", env=env).stdout)
    finally:
        subprocess.run(["pkill", "-f", str(bin_dir)], check=False)
    assert first["login"]["code"] == second["login"]["code"] == "AB12-CD34"
    assert counter.read_text().count("x") == 1


# ---------------------------------------------------------------- live tab server

def test_the_live_server_starts_once_follows_saved_files_and_stops(tmp_path):
    """A fake pnpm serves the repo folder like a dev server; the tab URL must show a file the moment it is saved."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"scripts": {"dev": "astro dev"}}')
    (repo / "index.html").write_text("<h1>first</h1>")
    bin_dir = tmp_path / "bin"
    fake_bin(bin_dir, "pnpm", f'exec "{sys.executable}" -m http.server "$4" --bind 127.0.0.1 --directory "{repo}"\n')
    env = env_with(bin_dir, tmp_path)
    with socket.socket() as busy:  # the stack's port is taken: the next free one is used
        busy.bind(("127.0.0.1", 0))
        port = busy.getsockname()[1]
        busy.listen()
        started = json.loads(run("live_view.py", "start", "--repo", str(repo), "--port", str(port), env=env).stdout)
    try:
        assert started["running"] is True and started["port"] != port
        url = started["url"]
        assert b"first" in urllib.request.urlopen(url, timeout=5).read()
        (repo / "index.html").write_text("<h1>second</h1>")
        assert b"second" in urllib.request.urlopen(url, timeout=5).read()
        reused = json.loads(run("live_view.py", "start", "--repo", str(repo), env=env).stdout)
        assert reused["reused"] is True and reused["url"] == url
    finally:
        stopped = json.loads(run("live_view.py", "stop", "--repo", str(repo), env=env).stdout)
    assert stopped["stopped"] is True
    with pytest.raises(OSError):
        urllib.request.urlopen(url, timeout=3)


def test_a_dev_server_showing_an_error_is_reused_not_doubled(tmp_path):
    """A compile error makes the dev server answer 500: that is the same live server, never a reason for a second."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"scripts": {"dev": "astro dev"}}')
    server = tmp_path / "srv.py"
    server.write_text("import http.server, sys\n"
                      "class H(http.server.BaseHTTPRequestHandler):\n"
                      "    def do_GET(self):\n        self.send_response(500); self.end_headers()\n"
                      "    def log_message(self, *a): pass\n"
                      "http.server.HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n")
    bin_dir = tmp_path / "bin"
    fake_bin(bin_dir, "pnpm", f'exec "{sys.executable}" "{server}" "$4"\n')
    env = env_with(bin_dir, tmp_path)
    try:
        first = json.loads(run("live_view.py", "start", "--repo", str(repo), env=env).stdout)
        again = json.loads(run("live_view.py", "start", "--repo", str(repo), env=env).stdout)
        assert first["running"] and again["reused"] is True and again["url"] == first["url"]
    finally:
        run("live_view.py", "stop", "--repo", str(repo), env=env)


def test_a_server_that_never_answers_is_stopped_not_orphaned(tmp_path, monkeypatch):
    """A dev server that never comes up is killed and forgotten: no orphan the next `stop` could not reach."""
    import time

    import live_view
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "package.json").write_text('{"scripts": {"dev": "astro dev"}}')
    bin_dir = tmp_path / "bin"
    fake_bin(bin_dir, "pnpm", "exec sleep 300\n")
    monkeypatch.setattr(live_view, "WAIT_S", 2)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    seen: list[int] = []
    real_popen = live_view.subprocess.Popen

    def spy(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        seen.append(proc.pid)
        return proc

    monkeypatch.setattr(live_view.subprocess, "Popen", spy)
    row = live_view.start(repo, 4399)
    assert row["running"] is False and seen
    time.sleep(1)
    assert not live_view.alive(seen[0]) or os.waitpid(seen[0], os.WNOHANG) != (0, 0)
    assert not (repo / ".hermes-live" / "server.json").exists()


def test_a_repo_without_the_base_is_reported_not_a_usage_error(tmp_path):
    (tmp_path / "repo").mkdir()
    done = run("live_view.py", "start", "--repo", str(tmp_path / "repo"))
    assert done.returncode == 1 and "site_base.py" in done.stdout


# ---------------------------------------------------------------- the real gate

def _toolchain_ready() -> bool:
    if not (shutil.which("node") and shutil.which("npm") and (shutil.which("pnpm") or shutil.which("corepack"))):
        return False
    try:
        probe = subprocess.run(["npm", "view", "@biomejs/biome", "version"], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


real_toolchain = pytest.mark.skipif(not _toolchain_ready(), reason="needs node, pnpm/corepack and the npm registry")

VIOLATIONS = {
    # two ways a library's `any` leaks in: held in a variable (type-coverage counts it) and handed straight back
    # (no identifier is `any`, so only the typed lint rule sees it)
    "src/lib/parse.ts": 'export function parse(text: string): string {\n  const data = JSON.parse(text);\n  return String(data);\n}\n',
    "src/lib/raw.ts": 'export function raw(text: string) {\n  return JSON.parse(text);\n}\n',
    "src/server/shell.ts": 'import { exec } from "node:child_process";\n\nexport function run(userInput: string): void {\n'
                           '  exec("ls " + userInput);\n}\n',
    "src/components/Card.ts": 'export function cardTitle(name: string): string {\n  return `Card ${name}`;\n}\n',
    "src/lib/price.ts": (
        'import { cardTitle } from "../components/Card";\n\n'
        "export function total(items: any): number {\n  let sum = 0;\n  for (const item of items) {\n"
        "    if (item.a) { if (item.b) { if (item.c) { if (item.d) { sum += 1; } else { sum += 2; } } } }\n"
        "  }\n  return sum + cardTitle(\"x\").length;\n}\n\n"
        "export function totalCopy(items: any): number {\n  let sum = 0;\n  for (const item of items) {\n"
        "    if (item.a) { if (item.b) { if (item.c) { if (item.d) { sum += 1; } else { sum += 2; } } } }\n"
        "  }\n  return sum;\n}\n"),
}


@pytest.fixture(scope="session")
def scanner_env(tmp_path_factory):
    """One scanner folder shared by the real tests: osv-scanner and gitleaks download once, not per test."""
    return {**os.environ, "HERMES_WEB_TOOLS_DIR": str(tmp_path_factory.getbasetemp() / "web-tools")}




@pytest.mark.real_toolchain
@real_toolchain
def test_the_gate_passes_a_fresh_base_and_rejects_each_bad_practice(tmp_path, scanner_env):
    repo = tmp_path / "repo"
    repo.mkdir()
    done = run("site_base.py", "--repo", str(repo), "--stack", "astro", "--name", "gate-demo", "--install", "--json", env=scanner_env)
    result = json.loads(done.stdout)
    assert done.returncode == 0, [s for s in result["steps"] if not s["ok"]]
    assert git(repo, "log", "--format=%s").splitlines() == ["chore: strict project base"]
    assert (repo / ".git" / "hooks" / "pre-commit").is_file()  # lefthook installed

    for rel, text in VIOLATIONS.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    caught = {}
    for step in ("lint", "sonar", "arch", "dupes", "typecov"):
        out = subprocess.run(["pnpm", "run", "-s", f"quality:{step}"], cwd=repo, capture_output=True, text=True,
                             timeout=600, env=scanner_env)
        caught[step] = (out.returncode, out.stdout + out.stderr)
    assert caught["lint"][0] and "noExplicitAny" in caught["lint"][1]
    assert "noExcessiveCognitiveComplexity" in caught["lint"][1]
    assert caught["sonar"][0] and "sonarjs/cognitive-complexity" in caught["sonar"][1]
    assert "no-unsafe-member-access" in caught["sonar"][1]
    assert caught["arch"][0] and "logic-never-imports-ui" in caught["arch"][1]
    assert caught["dupes"][0] and "clone" in caught["dupes"][1].lower()
    assert "security/detect-child-process" in caught["sonar"][1]  # command injection, from eslint-plugin-security
    assert caught["typecov"][0] and "src/lib/parse.ts" in caught["typecov"][1]  # an `any` held in a variable
    assert "src/lib/raw.ts" in caught["sonar"][1] and "no-unsafe-return" in caught["sonar"][1]  # an `any` returned


@pytest.mark.real_toolchain
@real_toolchain
@pytest.mark.parametrize("stack", ["nextjs", "tanstack"])
def test_every_stack_starts_green(tmp_path, stack, scanner_env):
    repo = tmp_path / "repo"
    repo.mkdir()
    done = run("site_base.py", "--repo", str(repo), "--stack", stack, "--name", f"{stack}-demo", "--install", "--json", env=scanner_env)
    result = json.loads(done.stdout)
    assert done.returncode == 0, [(s["step"], s["tail"][-800:]) for s in result["steps"] if not s["ok"]]


@pytest.mark.real_toolchain
@real_toolchain
def test_the_dependency_gate_catches_a_package_with_a_known_vulnerability(tmp_path, scanner_env):
    """A site depending on an old lodash must not pass: osv-scanner reads the real lockfile against real advisories."""
    repo = tmp_path / "repo"
    repo.mkdir()
    done = run("site_base.py", "--repo", str(repo), "--stack", "astro", "--name", "dep-demo", "--install", "--json",
               env=scanner_env)
    assert done.returncode == 0, done.stdout[-800:]
    clean = subprocess.run(["pnpm", "run", "-s", "quality:deps"], cwd=repo, capture_output=True, text=True, timeout=300,
                           env=scanner_env)
    assert clean.returncode == 0, clean.stderr[-600:]
    added = subprocess.run(["pnpm", "add", "lodash@4.17.20"], cwd=repo, capture_output=True, text=True, timeout=300,
                           env=scanner_env)
    assert added.returncode == 0, added.stderr[-600:]
    bad = subprocess.run(["pnpm", "run", "-s", "quality:deps"], cwd=repo, capture_output=True, text=True, timeout=300,
                         env=scanner_env)
    assert bad.returncode == 1 and "lodash" in (bad.stdout + bad.stderr), (bad.stdout + bad.stderr)[-600:]
