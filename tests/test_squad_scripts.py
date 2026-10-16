"""Squad-side scripts that cron or workers run: smoke runs against the fake hermes in a temp root."""
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FAKES = REPO / "tests" / "fakes"
START_SEARCH = REPO / "squads" / "jobs" / "scripts" / "start_search.py"


def fake_env(tmp: Path) -> dict:
    root = tmp / "hermes"
    (root / "profiles" / "jobs").mkdir(parents=True)
    bindir = tmp / "bin"
    bindir.mkdir()
    (bindir / "hermes").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKES / "hermes.py"}" "$@"\n')
    (bindir / "hermes").chmod(0o755)
    return {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "HERMES_HOME": str(root)}


def run(argv, env):
    return subprocess.run([sys.executable, *map(str, argv)], capture_output=True, text=True, env=env, timeout=120)


def test_start_search_is_silent_without_a_project(tmp_path):
    p = run([START_SEARCH], fake_env(tmp_path))
    assert (p.returncode, p.stdout) == (0, ""), p.stderr


def test_start_search_is_silent_without_profile_md(tmp_path):
    env = fake_env(tmp_path)
    folder = tmp_path / "search"
    folder.mkdir()
    created = subprocess.run(["hermes", "-p", "jobs", "project", "create", "Search", str(folder), "--slug", "search"],
                             capture_output=True, text=True, env=env)
    assert created.returncode == 0, created.stderr
    p = run([START_SEARCH, "--json"], env)
    assert p.returncode == 0 and '"no profile.md"' in p.stdout  # the project resolved; the gap is profile.md
    p = run([START_SEARCH], env)
    assert (p.returncode, p.stdout) == (0, ""), p.stderr
