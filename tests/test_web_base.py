"""The web squad's project base, live tab, progress saves and logins, exercised the way the bots use them.

Fast tests drive the real scripts against temp git repos and fake CLIs on PATH. The `real_toolchain` tests run each
stack's official create CLI and pnpm (network) and prove the gate rejects the bad practices it promises to block.
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


# ---------------------------------------------------------------- strict base: official installers first

def fake_create_cli(bin_dir: Path, log: Path, exit_code: int = 0) -> None:
    """A pnpm whose `dlx <create-cli>` behaves like the real create CLIs: it writes the template into the target
    folder (the argument ending in the project name) and logs how it was called."""
    fake_bin(bin_dir, "pnpm", f'echo "$@" >> "{log}"\n'
                              f'[ {exit_code} = 0 ] || {{ echo "create failed: network"; exit {exit_code}; }}\n'
                              'for a in "$@"; do case "$a" in */.create-*/*)\n'
                              '  mkdir -p "$a/src/pages"; echo "# from the template" > "$a/README.md"\n'
                              '  echo "---\\n---\\n<h1>template</h1>" > "$a/src/pages/index.astro"\n'
                              "  printf '{\"name\":\"acme\",\"dependencies\":{\"astro\":\"^7.4.2\"},"
                              "\"scripts\":{\"dev\":\"astro dev\"}}' > \"$a/package.json\";; esac; done\n")


def test_a_new_site_starts_from_the_stacks_official_create_cli(tmp_path):
    """The skeleton is the framework's own: its create CLI runs under the 3-day rule, without installing, and the
    squad only lays its gate on top. Nothing the template owns is written by the squad."""
    repo, log = tmp_path / "acme" / "repo", tmp_path / "pnpm.log"
    repo.mkdir(parents=True)
    fake_create_cli(tmp_path / "bin", log)
    done = run("site_base.py", "--repo", str(repo), "--stack", "astro", "--name", "acme", "--json",
               env=env_with(tmp_path / "bin", tmp_path))
    result = json.loads(done.stdout)
    assert done.returncode == 0 and result["steps"][0]["step"] == "create (official CLI)", done.stdout
    call = log.read_text().split()
    assert call[:3] == ["--config.minimum-release-age=4320", "dlx", "create-astro@latest"]
    assert {"--no-install", "--no-git", "--yes"} <= set(call) and call[3].endswith("/acme")
    assert (repo / "README.md").read_text() == "# from the template\n"  # the CLI's file, untouched
    assert "<h1>template</h1>" in (repo / "src" / "pages" / "index.astro").read_text()
    pkg = json.loads((repo / "package.json").read_text())
    assert pkg["dependencies"] == {"astro": "^7.4.2"} and pkg["scripts"]["dev"] == "astro dev"
    assert pkg["scripts"]["quality"].startswith("pnpm run quality:types") and "devDependencies" not in pkg
    for squad_file in ("tools/quality/biome.strict.jsonc", "tools/quality/eslint.config.mjs", "knip.json",
                       "lefthook.yml", "pnpm-workspace.yaml", "src/lib/slug.test.ts", "public/_headers"):
        assert (repo / squad_file).is_file(), squad_file
    assert not [p.name for p in repo.parent.iterdir() if p.name.startswith(".create-")], "no leftover work folder"


def test_a_failed_create_cli_leaves_the_repo_empty(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    fake_create_cli(tmp_path / "bin", tmp_path / "pnpm.log", exit_code=1)
    done = run("site_base.py", "--repo", str(repo), "--stack", "nextjs", "--name", "acme", "--json",
               env=env_with(tmp_path / "bin", tmp_path))
    step = json.loads(done.stdout)["steps"][0]
    assert done.returncode == 1 and step["ok"] is False and "create failed: network" in step["tail"]
    assert list(repo.iterdir()) == [], "no gate laid over a missing template"


def test_each_stack_names_its_official_create_cli():
    stacks = site_base.sc.load_stacks()
    argv = {s: site_base.sc.create_argv(stacks, s, "/x/acme", "acme", "cloudflare") for s in stacks["stacks"]}
    assert argv["astro"][3] == "create-astro@latest" and argv["nextjs"][3] == "create-next-app@latest"
    assert argv["tanstack"][3:5] == ["@tanstack/cli@latest", "create"] and "cloudflare" in argv["tanstack"]
    for stack, call in argv.items():
        assert call[:3] == ["pnpm", "--config.minimum-release-age=4320", "dlx"], stack
        assert "/x/acme" in call and not any("{" in part for part in call), stack


def test_no_dependency_version_is_typed_by_the_squad():
    """Every package arrives through `pnpm add <name>`: a version in stacks.json is either a declared constraint
    with its reason or an advisory fix, never a pin someone has to keep updating."""
    stacks = site_base.sc.load_stacks()
    names = [*stacks["devDependencies"], *stacks["cloudflare"]["devDependencies"], *stacks["motion"]["packages"],
             *stacks["quality_tools"]["packages"],
             *(n for s in stacks["stacks"].values() for n in s.get("devDependencies", []))]
    versioned = {n for n in names if "@" in n.lstrip("@")}
    assert versioned <= set(stacks["constraints"]), versioned - set(stacks["constraints"])
    assert all(reason.strip() for reason in stacks["constraints"].values())


def test_template_packages_keep_the_major_the_framework_chose(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "dependencies": {"astro": "^7.4.2", "next": "16.4.2", "@tanstack/react-devtools": "0.10.13",
                         "ui": "workspace:*", "lib": "github:o/r"},
        "devDependencies": {"typescript": "~5.9.3", "@types/node": ">=20"}}))
    assert site_base.template_majors(tmp_path) == {
        "dependencies": ["astro@7", "next@16", "@tanstack/react-devtools@0.10"],  # a 0.x line breaks on minors
        "devDependencies": ["typescript@5", "@types/node@20"]}


def test_pnpm_is_pinned_to_its_newest_release_at_least_3_days_old():
    day = 86400
    now = 1_800_000_000
    iso = lambda days_ago: __import__("datetime").datetime.fromtimestamp(  # noqa: E731
        now - days_ago * day, __import__("datetime").timezone.utc).isoformat().replace("+00:00", "Z")
    times = {"created": iso(900), "modified": iso(0), "10.34.6": iso(60), "12.14.0": iso(4), "12.13.0": iso(9),
             "12.15.0": iso(1), "13.0.0-rc.1": iso(30), "9.15.9": iso(400)}
    assert site_base.newest_mature(times, 4320, now=now) == "12.14.0"
    assert site_base.newest_mature({"12.15.0": iso(1)}, 4320, now=now) is None


def test_pnpm_11_and_later_get_allow_builds_and_lose_the_dead_pnpm_field(tmp_path):
    """pnpm 11 stopped reading package.json's `pnpm` field and pnpm 12 fails on a setting it does not know: the
    template's build approvals must move into allowBuilds, or esbuild and workerd never build."""
    (tmp_path / "package.json").write_text(json.dumps(
        {"name": "acme", "pnpm": {"onlyBuiltDependencies": ["esbuild", "msw"]}}))
    report: dict = {}
    files, _ = site_base.plan_files(tmp_path, site_base.sc.load_stacks(), "tanstack", "acme", "cloudflare", report,
                                    pnpm_major=12)
    assert "pnpm" not in json.loads(files["package.json"])
    ws = files["pnpm-workspace.yaml"].splitlines()
    assert "allowBuilds:" in ws and "  'msw': true" in ws and "  'lefthook': true" in ws
    assert "onlyBuiltDependencies:" not in ws and any("allowBuilds" in n for n in report["notes"])
    old, _ = site_base.plan_files(tmp_path, site_base.sc.load_stacks(), "tanstack", "acme", "cloudflare", {},
                                  pnpm_major=10)
    assert "onlyBuiltDependencies:" in old["pnpm-workspace.yaml"] and "allowBuilds" not in old["pnpm-workspace.yaml"]


def test_the_projects_biome_config_extends_the_squad_rules(tmp_path):
    """Biome's own config (from the create CLI or `biome init`) stays, so its schema matches the installed Biome;
    it extends the squad's rules, and its own file list keeps the squad's exclusions."""
    theirs = {"$schema": "https://biomejs.dev/schemas/2.4.2/schema.json",
              "files": {"includes": ["**", "!node_modules"]}, "formatter": {"indentStyle": "tab"}}
    out = json.loads(site_base.biome_extends(json.dumps(theirs)))
    assert out["extends"] == [site_base.BIOME_POLICY] and out["formatter"] == {"indentStyle": "tab"}
    assert out["$schema"] == theirs["$schema"] and "!!**/public" in out["files"]["includes"]
    assert out["files"]["includes"][:2] == ["**", "!node_modules"]
    assert site_base.biome_extends(json.dumps(out)) is None, "already extended: left alone"
    assert (site_base.TEMPLATES / site_base.BIOME_POLICY).is_file()


def test_type_coverage_receives_its_ignore_globs_unexpanded(tmp_path):
    """The gate scripts run in sh, which expands an unquoted `.next/**` into folder names before type-coverage
    sees it; the generated route types would then count against the 100 %."""
    (tmp_path / ".next" / "types").mkdir(parents=True)
    (tmp_path / ".next" / "types" / "validator.ts").write_text("export {};\n")
    fake_bin(tmp_path / "tools" / "quality" / "node_modules" / ".bin", "type-coverage",
             'for a in "$@"; do echo "$a"; done\n')
    cmd = site_base.typecov_command(site_base.sc.load_stacks()["stacks"]["nextjs"])
    args = subprocess.run(["sh", "-c", cmd], cwd=tmp_path, capture_output=True, text=True).stdout.splitlines()
    assert ".next/**" in args and ".next/types" not in args


def test_the_gate_tools_and_its_reports_are_not_type_checked_as_project_code():
    text, _ = site_base.strict_tsconfig('{"extends": "astro/tsconfigs/strict", "include": ["**/*"], '
                                        '"exclude": ["dist"]}')
    exclude = json.loads(text)["exclude"]
    assert exclude[0] == "dist" and {"tools/quality", "coverage", "playwright-report"} <= set(exclude)
    bare, _ = site_base.strict_tsconfig('{"compilerOptions": {}}')
    assert json.loads(bare)["exclude"][0] == "node_modules"  # an explicit exclude replaces TypeScript's default


def test_one_command_reads_the_users_choice_from_site_yaml(tmp_path):
    """The manager runs one command; stack, name, provider and repo folder come from what the user chose."""
    site = tmp_path / "acme"
    site.mkdir()
    (site / "site.yaml").write_text("slug: acme\nstack: tanstack   # saas -> tanstack\nprovider: vercel\n"
                                    "design:\n  path: ignored\nrepo:\n  path: web\n")
    done = run("site_base.py", "--site", str(site), "--dry-run", "--json")
    out = json.loads(done.stdout)
    assert done.returncode == 0 and out["stack"] == "tanstack" and out["repo"] == str((site / "web").resolve())
    assert "@tanstack/cli@latest" in out["create"] and "vercel" in out["create"] and "acme" in out["create"]
    (site / "site.yaml").write_text("stack: astro\n")
    missing = run("site_base.py", "--site", str(site), "--json")
    assert missing.returncode == 2 and "no slug" in missing.stderr


def test_a_release_that_lost_its_publisher_trust_is_held_back_not_installed(tmp_path):
    """lefthook 2.2.2 was published by hand without the provenance 2.2.1 had: pnpm calls it a possible takeover.
    The base adds 2.2.1 instead, says so, and never lets 2.2.2 in."""
    log = tmp_path / "pnpm.log"
    fake_bin(tmp_path / "bin", "pnpm", f'echo "$@" >> "{log}"\ncase " $* " in *" lefthook@2.2.1 "*) exit 0;; esac\n'
                                       "echo 'Error:   x adding a new package'\n"
                                       "echo '  |-> Failed to resolve dependency: High-'\n"
                                       "echo '  │   risk trust downgrade for \"lefthook@2.2.2\" (possible package takeover)'\n"
                                       "exit 1\n")
    fake_bin(tmp_path / "bin", "npm", "echo '{\"2.2.0\": \"2026-10-07T19:12:00Z\", \"2.2.1\": \"2026-10-08T10:39:00Z\", "
                                      "\"2.2.2\": \"2026-10-13T09:47:00Z\", \"2.3.0-rc.1\": \"2026-10-01T00:00:00Z\"}'\n")
    old = os.environ["PATH"]
    os.environ["PATH"] = f"{tmp_path / 'bin'}{os.pathsep}{old}"
    try:
        out = site_base.add_holding_untrusted(["pnpm", "add", "-D", "vitest", "lefthook"], tmp_path, "squad tools", 4320)
        transitive = site_base.add_holding_untrusted(["pnpm", "add", "-D", "vitest"], tmp_path, "squad tools", 4320)
    finally:
        os.environ["PATH"] = old
    assert out["ok"] and out["argv"] == ["pnpm", "add", "-D", "vitest", "lefthook@2.2.1"], out
    assert out["held"] == ["lefthook@2.2.1 (pnpm trustPolicy flagged 2.2.2: published without the provenance of "
                           "earlier releases)"]
    assert "lefthook@2.2.2" not in log.read_text().replace("trust", "")
    assert not transitive["ok"] and "a manager decision" in transitive["tail"]


def test_versions_left_behind_are_only_the_installers_choice_or_a_stated_reason(tmp_path):
    """The versions gate's exceptions come from the official installer (a major its template chose), a stated
    constraint or a trust hold, and a second run keeps the first run's list. A package the bot added and left behind
    gets no exception."""
    (tmp_path / "tools" / "quality").mkdir(parents=True)
    findings = [{"name": "typescript", "kind": "behind", "current": "5", "mature": "7"},
                {"name": "react", "kind": "behind", "current": "17", "mature": "19"}]
    (tmp_path / "tools" / "quality" / "fresh.mjs").write_text(f"process.stdout.write({json.dumps(json.dumps(findings))});\n")
    stacks = site_base.sc.load_stacks()
    template = {"devDependencies": ["typescript@5", "@types/node@20"]}
    held = ["lefthook@2.2.1 (pnpm trustPolicy flagged 2.2.2: published without the provenance of earlier releases)"]
    row = site_base.fresh_allow(tmp_path, stacks, "nextjs", template, held)
    allow = json.loads((tmp_path / "tools" / "quality" / "fresh-allow.json").read_text())
    assert row["ok"] and allow["typescript"] == "create-next-app chose typescript@5 for this stack"
    assert "react" not in allow and allow["lefthook"].startswith("held at lefthook@2.2.1")
    assert set(allow) == {"typescript", "lefthook", "@types/node"}
    site_base.fresh_allow(tmp_path, stacks, "nextjs", {}, [])  # the second run, after the template's code was fixed
    assert json.loads((tmp_path / "tools" / "quality" / "fresh-allow.json").read_text()) == allow


def test_an_existing_repo_keeps_its_files_and_gains_the_gate(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps(
        {"name": "theirs", "scripts": {"lint": "their-lint", "dev": "vite", "quality": "echo ok"},
         "devDependencies": {"vitest": "4.0.0"}}))
    (tmp_path / "biome.json").write_text("{}")
    (tmp_path / "tsconfig.json").write_text('{\n  // a comment\n  "compilerOptions": {}\n}\n')
    report: dict = {}
    files, kept = site_base.plan_files(tmp_path, site_base.sc.load_stacks(), "tanstack", "theirs", "vercel", report)
    assert "biome.json" not in files and "src/router.tsx" not in files and "src/lib/slug.ts" not in files
    opts = json.loads(files["tsconfig.json"])["compilerOptions"]  # a tsconfig with comments is still made strict
    assert opts["strict"] is True and opts["exactOptionalPropertyTypes"] is True and not report.get("manual")
    pkg = json.loads(files["package.json"])
    assert pkg["scripts"]["lint"] == "their-lint"  # theirs wins outside the gate
    assert pkg["scripts"]["quality"].startswith("pnpm run quality:types")  # a weak old gate never survives
    assert report["replaced_scripts"] == ["quality"]
    assert pkg["devDependencies"] == {"vitest": "4.0.0"}, "dependencies change only through pnpm add"


def test_a_plain_tsconfig_is_made_strict(tmp_path):
    (tmp_path / "package.json").write_text('{"name": "x"}')
    (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {"strict": false, "target": "ES2020"}}')
    files, _ = site_base.plan_files(tmp_path, site_base.sc.load_stacks(), "nextjs", "x", "cloudflare")
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


def test_files_another_bot_staged_never_block_a_save_nor_ride_along(site):
    """Parallel cards share one index: one bot's staged-but-uncommitted files used to refuse every other bot's save,
    so a finished card sat blocked for an hour. The save must commit its own piece and leave the other bot's staging."""
    _, repo = site
    git(repo, "switch", "-q", "-c", f"web/{WORK_ID}")
    hook = repo / ".git" / "hooks" / "pre-commit"
    seen = repo.parent / "hook-saw.txt"
    hook.write_text(f"#!/bin/sh\ngit diff --cached --name-only >> '{seen}'\n")
    hook.chmod(0o755)
    (repo / "atmosphere.ts").write_text("export const half = 1;\n")
    git(repo, "add", "atmosphere.ts")  # the atmosphere bot, mid-piece
    (repo / "sound.ts").write_text("export const sound = 1;\n")
    done = run("save_progress.py", "--repo", str(repo), "--id", WORK_ID, "--what", "sound", "--paths", "sound.ts")
    assert done.returncode == 0, done.stdout
    assert git(repo, "show", "--name-only", "--format=", "HEAD").split() == ["sound.ts"]
    assert seen.read_text().split() == ["sound.ts"], "the hook must lint only this piece"
    assert "A  atmosphere.ts" in git(repo, "status", "--porcelain"), "the other bot's staging stays as it was"


def test_two_builders_saving_at_the_same_moment_both_land(site):
    """The pre-commit hook holds index.lock while it runs (Biome takes seconds); the second save waits, never fails."""
    _, repo = site
    git(repo, "switch", "-q", "-c", f"web/{WORK_ID}")
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nsleep 2\n")
    hook.chmod(0o755)
    (repo / "neurons.ts").write_text("export const n = 1;\n")
    (repo / "ground.ts").write_text("export const g = 1;\n")
    cmd = [sys.executable, "-I", str(SCRIPTS / "save_progress.py"), "--repo", str(repo), "--id", WORK_ID]
    procs = [subprocess.Popen([*cmd, "--what", w, "--paths", f"{w}.ts"], stdout=subprocess.PIPE, text=True)
             for w in ("neurons", "ground")]
    outs = [json.loads(p.communicate(timeout=120)[0]) for p in procs]
    assert all(o["saved"] for o in outs), outs
    log = git(repo, "log", "--format=%s", f"main..web/{WORK_ID}").splitlines()
    assert sorted(log) == [f"wip({WORK_ID}): ground", f"wip({WORK_ID}): neurons"]
    assert git(repo, "status", "--porcelain").strip() == ""


# ---------------------------------------------------------------- live renders

PNG = bytes.fromhex("89504e470d0a1a0a0000000d4948445200000001000000010806000000"
                    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def renders(page: Path) -> list[dict]:
    text = (page.parent / "renders.js").read_text()
    assert text.startswith("window.RENDERS = ")
    return json.loads(text[len("window.RENDERS = "):].rstrip().rstrip(";"))


def test_the_renders_viewer_lists_every_newest_render_without_reloading_the_tab(site):
    """The tab must never reload on a new render (that resets the user's zoom): only renders.js changes."""
    site_dir, _ = site
    out = site_dir / "render.png"
    out.write_bytes(PNG)
    first = run("live_renders.py", "--site", str(site_dir), "--id", WORK_ID)
    assert first.returncode == 0 and json.loads(first.stdout)["images"] == 0
    page = Path(json.loads(first.stdout)["path"])
    assert page == site_dir / "milestones" / WORK_ID / "live" / "index.html" and renders(page) == []
    viewer, stamp = page.read_text(), page.stat().st_mtime_ns
    run("live_renders.py", "--site", str(site_dir), "--id", WORK_ID, "--add", str(out), "--name", "hero-neuron")
    (page.parent / "ground.png").write_bytes(PNG)  # a modeller writing straight into live/
    done = json.loads(run("live_renders.py", "--site", str(site_dir), "--id", WORK_ID).stdout)
    assert done["images"] == 2 and {r["name"] for r in renders(page)} == {"hero-neuron.png", "ground.png"}
    assert page.stat().st_mtime_ns == stamp and page.read_text() == viewer, "the viewer file is left untouched"
    assert "setInterval(load" in viewer and "zoomAt" in viewer and "innerHTML" not in viewer
    assert not list(page.parent.glob(".*.tmp")), "writes are atomic: no half file for the tab to load"
    assert "[hidden]{display:none!important}" in viewer, "a hidden overlay must not swallow thumbnail clicks"


def test_the_renders_board_refuses_a_path_as_a_name(site):
    site_dir, _ = site
    (site_dir / "r.png").write_bytes(PNG)
    bad = run("live_renders.py", "--site", str(site_dir), "--id", WORK_ID, "--add", str(site_dir / "r.png"),
              "--name", "../../escape")
    assert bad.returncode == 2 and not (site_dir.parent / "escape.png").exists()


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
    assert result["steps"][0]["step"] == "create (official CLI)" and "create-astro@latest" in result["steps"][0]["argv"]
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


def readonly_props(repo: Path, tail: str) -> int:
    """What the manager does with a `prefer-read-only-props` finding in the template's code: mark the props
    read-only. Returns how many places it fixed."""
    import re
    fixed = 0
    for path, line in re.findall(r"^(/\S+\.tsx)$\n\s+(\d+):\d+\s+error\s+.*sonarjs/prefer-read-only-props", tail, re.M):
        src = Path(path)
        text = src.read_text()
        new = re.sub(r"\}: (\{ [^}]+ \})\)", r"}: Readonly<\1>)", text, count=1)
        if new != text:
            src.write_text(new)
            fixed += 1
    return fixed


@pytest.mark.real_toolchain
@real_toolchain
@pytest.mark.parametrize("stack", ["nextjs", "tanstack"])
def test_every_stack_starts_green(tmp_path, stack, scanner_env):
    """Each stack from its own create CLI ends on a green gate and one commit. When the template's code itself
    breaks a rule, the base stops with `next`; the code is fixed (never the rule) and the same command finishes."""
    site = tmp_path / f"{stack}-demo"
    site.mkdir()
    (site / "site.yaml").write_text(f"slug: {stack}-demo\nstack: {stack}\nprovider: cloudflare\nrepo:\n  path: repo\n")
    repo = site / "repo"
    argv = ("site_base.py", "--site", str(site), "--json")  # the manager's one command
    done = run(*argv, env=scanner_env)
    result = json.loads(done.stdout)
    failed = [s for s in result["steps"] if not s["ok"]]
    if failed:
        assert [s["step"] for s in failed] == ["pnpm quality"] and result["next"], [
            (s["step"], s["tail"][-800:]) for s in failed]
        assert readonly_props(repo, failed[0]["tail"]), failed[0]["tail"][-1500:]
        done = run(*argv, env=scanner_env)
        result = json.loads(done.stdout)
    assert done.returncode == 0, [(s["step"], s["tail"][-800:]) for s in result["steps"] if not s["ok"]]
    assert git(repo, "log", "--format=%s").splitlines() == ["chore: strict project base"]
    assert git(repo, "status", "--porcelain") == ""
    pkg = json.loads((repo / "package.json").read_text())
    assert pkg["packageManager"] == f"pnpm@{result['pnpm']}" and "pnpm" not in pkg
    fresh = subprocess.run(["pnpm", "run", "-s", "quality:fresh"], cwd=repo, capture_output=True, text=True,
                           timeout=300, env=scanner_env)
    assert fresh.returncode == 0, fresh.stderr[-600:]
    pkg["dependencies"]["react"] = "17.0.2"  # a version typed from memory
    (repo / "package.json").write_text(json.dumps(pkg, indent=2))
    stale = subprocess.run(["pnpm", "run", "-s", "quality:fresh"], cwd=repo, capture_output=True, text=True,
                           timeout=300, env=scanner_env)
    assert stale.returncode == 1 and "react: on 17" in stale.stderr, stale.stderr[-600:]


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
    assert "security_fix.py" in bad.stderr  # the failure says how to fix it
    fixed = run("security_fix.py", "--repo", str(repo), env=scanner_env)
    out = json.loads(fixed.stdout)
    assert fixed.returncode == 0 and out["fixed"][0]["name"] == "lodash", fixed.stdout[-800:]
    again = subprocess.run(["pnpm", "run", "-s", "quality:deps"], cwd=repo, capture_output=True, text=True,
                           timeout=300, env=scanner_env)
    assert again.returncode == 0, again.stderr[-600:]
