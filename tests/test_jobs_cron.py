"""start_search.py as the cron runs it: the real script, real argv, a fake hermes binary (tests/fakes/hermes.py).

Each test runs one real use (a project list, a pause line, a catch-up run) and asserts what the user or the board sees.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FAKES = REPO / "tests" / "fakes"
START = REPO / "squads" / "jobs" / "scripts" / "start_search.py"
SYSTEM_PY = "/usr/bin/python3"  # no PyYAML on a stock Mac: the squad's built-in YAML reader is the one that runs
INTERPRETERS = [sys.executable] + ([SYSTEM_PY] if Path(SYSTEM_PY).is_file() else [])

ACTIVE = "---\nsearch: active\nuser_language: en\ntimezone: America/Lima\n---\nNotes\n"


def make_env(tmp: Path, wrapper: str | None = None):
    """A HERMES_HOME with the jobs manager, and a `hermes` on PATH: the fake, or a shell wrapper around it."""
    root = tmp / "hermes"
    (root / "profiles" / "jobs").mkdir(parents=True)
    bindir = tmp / "bin"
    bindir.mkdir()
    body = wrapper if wrapper is not None else f'exec "{sys.executable}" "{FAKES / "hermes.py"}" "$@"'
    (bindir / "hermes").write_text(f"#!/bin/sh\n{body}\n")
    (bindir / "hermes").chmod(0o755)
    # A delegated child cannot mutate kanban (the fake refuses); the test runs as the manager, so drop the flag.
    env = {k: v for k, v in os.environ.items() if k != "HERMES_DELEGATED_CHILD_CONTEXT"}
    # The host clock is pinned to UTC so a project zone can only come from profile.md, never from the machine.
    env.update({"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "HERMES_HOME": str(root), "TZ": "UTC"})
    return env, root


def hermes(env, *args):
    done = subprocess.run(["hermes", *args], capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
    return done.stdout


def board(env):
    hermes(env, "-p", "jobs", "kanban", "boards", "create", "jobs")


def add_project(env, tmp: Path, slug: str, profile: str, use: bool = False) -> Path:
    folder = tmp / slug
    folder.mkdir()
    (folder / "profile.md").write_text(profile)
    args = ["-p", "jobs", "project", "create", slug.title(), str(folder), "--slug", slug]
    hermes(env, *(args + (["--use"] if use else [])))
    return folder


def run_gate(env, interp: str, *extra: str):
    return subprocess.run([interp, "-I", str(START), *extra], capture_output=True, text=True, env=env, timeout=120)


def cards(root: Path) -> dict:
    store = root / "cards-jobs.json"
    return json.loads(store.read_text()) if store.is_file() else {}


def first_result(proc) -> dict:
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)["results"][0]


@pytest.mark.parametrize("interp", INTERPRETERS)
def test_two_active_projects_each_get_their_own_card(tmp_path, interp):
    # Every active project gets its own card for the slot; a second project is never skipped.
    env, root = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", ACTIVE)
    add_project(env, tmp_path, "luis-search", ACTIVE, use=True)
    p = run_gate(env, interp, "--now", "2026-10-21 08:05")
    assert p.returncode == 0, p.stderr
    assert sorted(cards(root)) == ["jobs:search:ana-search:2026-10-21-08", "jobs:search:luis-search:2026-10-21-08"]


def test_a_failing_hermes_is_an_error_not_a_silent_no_project(tmp_path):
    # A failed hermes call is an error for the cron alert, never the same answer as "no project".
    env, _ = make_env(tmp_path, wrapper='echo "gateway down" >&2\nexit 1')
    p = run_gate(env, sys.executable, "--now", "2026-10-21 08:05")
    assert p.returncode == 1, (p.stdout, p.stderr)
    assert "jobs-search:" in p.stdout and "gateway down" in p.stdout


def test_a_failing_kanban_create_is_an_error(tmp_path):
    # argv is -p jobs kanban --board jobs create ...: refuse only the card creation, not the board setup
    body = 'if [ "$3" = "kanban" ] && [ "$6" = "create" ]; then echo "kanban refused" >&2; exit 1; fi\n' \
           f'exec "{sys.executable}" "{FAKES / "hermes.py"}" "$@"'
    env, _ = make_env(tmp_path, wrapper=body)
    board(env)
    add_project(env, tmp_path, "ana-search", ACTIVE, use=True)
    p = run_gate(env, sys.executable, "--now", "2026-10-21 08:05")
    assert p.returncode == 1 and "kanban refused" in p.stdout, (p.stdout, p.stderr)


PAUSE_FORMS = ["search: paused", 'search: "paused"', "search: 'paused'", "search: PAUSED",
               "search: pausada", 'search: "pausada"']


@pytest.mark.parametrize("interp", INTERPRETERS)
@pytest.mark.parametrize("line", PAUSE_FORMS)
def test_every_spelling_of_pause_stops_the_card(tmp_path, interp, line):
    # Pause is read the same way under PyYAML and under the built-in reader: quoted, uppercase and Spanish forms.
    env, root = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", f"---\n{line}\nuser_language: en\n---\n", use=True)
    result = first_result(run_gate(env, interp, "--json", "--now", "2026-10-21 08:05"))
    assert result["filed"] is False and result["reason"] == "paused", result
    assert cards(root) == {}


@pytest.mark.parametrize("interp", INTERPRETERS)
@pytest.mark.parametrize("language, words", [("en", "must be active or paused"), ("es", "debe ser active o paused")])
def test_an_unknown_search_value_is_reported_and_does_not_run(tmp_path, interp, language, words):
    env, root = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", f"---\nsearch: maybe\nuser_language: {language}\n---\n", use=True)
    p = run_gate(env, interp, "--now", "2026-10-21 08:05")
    assert p.returncode == 1 and words in p.stdout, (p.stdout, p.stderr)
    assert cards(root) == {}


def test_a_profile_without_front_matter_is_an_error(tmp_path):
    env, root = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", "search: paused\n", use=True)
    p = run_gate(env, sys.executable, "--now", "2026-10-21 08:05")
    assert p.returncode == 1 and "no front matter" in p.stdout, (p.stdout, p.stderr)
    assert cards(root) == {}


@pytest.mark.parametrize("now, expected", [
    ("2026-10-21 08:59", "2026-10-21-08"),   # the scheduled run
    ("2026-10-21 10:00", "2026-10-21-08"),   # catch-up after a missed 08:00 run: the 08 slot, not a new one
    ("2026-10-21 15:00", None),              # the old second daily slot is gone
    ("2026-10-21 07:30", None),              # before the first slot
    ("2026-10-24 08:00", None),              # Saturday
])
def test_the_slot_comes_from_the_schedule(tmp_path, now, expected):
    # The key is the scheduled slot, so a late run in the catch-up window reuses the slot's card.
    env, _ = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", ACTIVE, use=True)
    result = first_result(run_gate(env, sys.executable, "--json", "--dry-run", "--now", now))
    if expected is None:
        assert result["filed"] is False and result["reason"] == "outside schedule hours", result
    else:
        assert result["filed"] is True and result["key"] == f"jobs:search:ana-search:{expected}", result


def test_a_catch_up_run_reuses_the_card_of_its_slot(tmp_path):
    env, root = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", ACTIVE, use=True)
    assert first_result(run_gate(env, sys.executable, "--json", "--now", "2026-10-21 08:05"))["filed"] is True
    assert first_result(run_gate(env, sys.executable, "--json", "--now", "2026-10-21 10:00"))["filed"] is True
    assert list(cards(root)) == ["jobs:search:ana-search:2026-10-21-08"]


@pytest.mark.parametrize("interp", INTERPRETERS)
def test_the_project_timezone_decides_the_slot_across_daylight_saving(tmp_path, interp):
    # 2026-03-09 is the first Monday after US daylight time starts. 08:05 in New York is 12:05 UTC that day, so the
    # slot is 08 at 12:05 UTC and not at 11:05 UTC (07:05 local): the project zone decides, not a fixed offset.
    env, _ = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", "---\nsearch: active\ntimezone: America/New_York\nuser_language: en\n---\n",
                use=True)
    on = first_result(run_gate(env, interp, "--json", "--dry-run", "--now", "2026-03-09T12:05:00+00:00"))
    assert on["filed"] is True and on["key"].endswith("2026-03-09-08"), on
    off = first_result(run_gate(env, interp, "--json", "--dry-run", "--now", "2026-03-09T11:05:00+00:00"))
    assert off["filed"] is False, off


def test_the_card_names_the_user_language(tmp_path):
    env, _ = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", "---\nsearch: active\nuser_language: es\n---\n", use=True)
    result = first_result(run_gate(env, sys.executable, "--json", "--dry-run", "--now", "2026-10-21 08:05"))
    body = result["command"][result["command"].index("--body") + 1]
    assert "User language: es" in body


def test_an_unknown_explicit_project_is_reported(tmp_path):
    env, _ = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", ACTIVE, use=True)
    result = first_result(run_gate(env, sys.executable, "--json", "--project", "nope", "--now", "2026-10-21 08:05"))
    assert result["filed"] is False and result["reason"] == "no project", result


def test_no_project_and_no_profile_stay_silent(tmp_path):
    env, _ = make_env(tmp_path)
    p = run_gate(env, sys.executable, "--now", "2026-10-21 08:05")
    assert (p.returncode, p.stdout) == (0, ""), p.stderr
