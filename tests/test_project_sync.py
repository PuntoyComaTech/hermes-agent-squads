"""project_sync: the manager's Projects reach every worker of the squad, bound to the squad board (fake hermes)."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "project_sync.py"
FAKE = REPO / "tests" / "fakes" / "hermes.py"
WORKERS = ["web-frontend", "web-qa"]


@pytest.fixture
def env(tmp_path):
    root = tmp_path / "hermes"
    for bot in ["web", *WORKERS]:
        (root / "profiles" / bot / "skills" / "squad-web").mkdir(parents=True)
    (root / "profiles" / "other").mkdir()  # not in the squad
    (root / "boards.json").write_text(json.dumps([{"slug": "web", "name": "Web", "archived": False}]))
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "hermes").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    (bindir / "hermes").chmod(0o755)
    log = tmp_path / "calls.jsonl"
    e = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "FAKE_HERMES_LOG": str(log),
         "HERMES_HOME": str(root / "profiles" / "web"), "HERMES_REAL_HOME": str(tmp_path / "home")}
    (tmp_path / "home").mkdir()
    return {"root": root, "env": e, "tmp": tmp_path, "log": log}


def hermes(env, *args):
    p = subprocess.run(["hermes", *args], capture_output=True, text=True,
                       env={**env["env"], "HERMES_HOME": str(env["root"])})
    assert p.returncode == 0, p.stderr
    return p.stdout


def sync(env, *args, code=0):
    p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env["env"])
    assert p.returncode == code, p.stderr + p.stdout
    return p.stdout


def projects(env, bot):
    return hermes(env, "-p", bot, "project", "list")


def site(env, name="acme"):
    folder = env["tmp"] / "Projects" / "web" / name
    folder.mkdir(parents=True)
    return folder


def calls(env, *prefix):
    rows = [json.loads(ln) for ln in env["log"].read_text().splitlines()] if env["log"].is_file() else []
    return [r for r in rows if r["args"][:len(prefix)] == list(prefix)]


def test_copies_manager_projects_to_every_worker_and_binds_the_board(env):
    folder = site(env)
    hermes(env, "-p", "web", "project", "create", "Acme Site", str(folder), "--slug", "acme")
    out = sync(env)
    assert "web-frontend create" in out and "web-qa create" in out and "web bind-board web" in out
    for bot in WORKERS:
        show = hermes(env, "-p", bot, "project", "show", "acme")
        assert "name:    Acme Site" in show and "board:   web" in show and f"primary: {folder}" in show
    assert "board:   web" in hermes(env, "-p", "web", "project", "show", "acme")
    assert "acme" not in (env["root"] / "profiles" / "other" / "projects.txt").read_text() \
        if (env["root"] / "profiles" / "other" / "projects.txt").exists() else True


def test_second_run_changes_nothing_and_prints_nothing(env):
    hermes(env, "-p", "web", "project", "create", "Acme", str(site(env)), "--slug", "acme")
    sync(env)
    before = len(calls(env, "project", "create")) + len(calls(env, "project", "bind-board"))
    assert sync(env) == ""
    assert len(calls(env, "project", "create")) + len(calls(env, "project", "bind-board")) == before


def test_dry_run_reports_and_writes_nothing(env):
    hermes(env, "-p", "web", "project", "create", "Acme", str(site(env)), "--slug", "acme")
    report = json.loads(sync(env, "--dry-run", "--json"))
    assert report["dry_run"] and report["workers"] == WORKERS
    acts = report["projects"][0]["actions"]
    assert {(a["bot"], a["action"]) for a in acts} == {("web", "bind-board web"), ("web-frontend", "create"),
                                                       ("web-qa", "create")}
    assert all("acme" not in projects(env, bot) for bot in WORKERS)
    assert not calls(env, "project", "bind-board") and len(calls(env, "project", "create")) == 1


def test_multi_folder_project_keeps_its_folders_and_primary(env):
    a, b = site(env, "app"), site(env, "api")
    hermes(env, "-p", "web", "project", "create", "App", str(a), str(b), "--slug", "app", "--board", "web")
    sync(env)
    show = hermes(env, "-p", "web-qa", "project", "show", "app")
    assert f"primary: {a}" in show and str(b) in show
    assert not calls(env, "project", "bind-board")  # already bound in the manager


def test_home_root_and_profile_folders_are_skipped_once(env):
    hermes(env, "-p", "web", "project", "create", "Home", str(env["tmp"] / "home"), "--slug", "home")
    hermes(env, "-p", "web", "project", "create", "Prof", str(env["root"] / "profiles" / "web"), "--slug", "prof")
    out = sync(env)
    assert "home: skipped, primary folder is the home folder" in out
    assert "prof: skipped, primary folder is a Hermes profile folder" in out
    assert all("home" not in projects(env, bot) and "prof" not in projects(env, bot) for bot in WORKERS)
    assert sync(env) == ""  # reported once


def test_missing_board_creates_without_one(env):
    (env["root"] / "boards.json").write_text("[]")
    hermes(env, "-p", "web", "project", "create", "Acme", str(site(env)), "--slug", "acme")
    out = sync(env)
    assert "board web does not exist" in out
    assert "board:" not in hermes(env, "-p", "web-qa", "project", "show", "acme")


def test_explicit_manager_and_workers(env):
    hermes(env, "-p", "web", "project", "create", "Acme", str(site(env)), "--slug", "acme")
    e = {**env["env"]}
    e.pop("HERMES_HOME")
    p = subprocess.run([sys.executable, str(SCRIPT), "--manager", "web", "--workers", "web-qa", "--hermes-root",
                        str(env["root"]), "--json"], capture_output=True, text=True, env=e)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["workers"] == ["web-qa"]
    assert "acme" in projects(env, "web-qa") and "acme" not in projects(env, "web-frontend")


def test_unreadable_worker_fails(env):
    hermes(env, "-p", "web", "project", "create", "Acme", str(site(env)), "--slug", "acme")
    report = json.loads(sync(env, "--workers", "web-qa,ghost", "--json", code=1))
    assert not report["ok"] and any("ghost" in n for n in report["notes"])
    assert "acme" in projects(env, "web-qa")


def test_setup_points_the_desktop_repo_scan_at_the_squad_folder(env):
    custom = env["root"] / "profiles" / "web-qa" / "config.yaml"
    custom.write_text("desktop:\n  repo_scan_roots:\n  - ~/code\n")
    dry = json.loads(sync(env, "--setup", "--dry-run", "--json"))
    assert dry["created_folder"] and not (env["tmp"] / "home" / "Projects" / "web").exists()
    out = sync(env, "--setup")
    assert (env["tmp"] / "home" / "Projects" / "web").is_dir()
    assert "web: set" in out and "web-frontend: set" in out and "web-qa: custom repo_scan_roots kept" in out
    for bot in ("web", "web-frontend"):
        assert hermes(env, "-p", bot, "config", "get", "desktop.repo_scan_roots").strip() == "- ~/Projects/web"
    assert "~/code" in custom.read_text()
    assert sync(env, "--setup") == "web-qa: custom repo_scan_roots kept: ['~/code']\n"


def test_help_runs_without_hermes():
    p = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert p.returncode == 0 and "--dry-run" in p.stdout
