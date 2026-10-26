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

ACTIVE = "---\nsearch: active\nuser_language: en\ntimezone: America/Lima\nsearch_times: [\"08:00\"]\n---\nNotes\n"


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
    ("2026-10-24 08:00", "weekend"),         # Saturday: said once that day, never a card
])
def test_the_slot_comes_from_the_schedule(tmp_path, now, expected):
    # The key is the scheduled slot, so a late run in the catch-up window reuses the slot's card.
    env, _ = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", ACTIVE, use=True)
    result = first_result(run_gate(env, sys.executable, "--json", "--dry-run", "--now", now))
    if expected == "weekend":
        assert result["filed"] is False and result["reason"] == "weekend", result
    elif expected is None:
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
    # 2026-03-09 is the first Monday after US daylight time starts. With no search_times the check is 12:00 local:
    # 12:05 in New York is 16:05 UTC that day, and 15:05 UTC is 11:05 local: the project zone decides, not an offset.
    env, _ = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", "---\nsearch: active\ntimezone: America/New_York\nuser_language: en\n---\n",
                use=True)
    on = first_result(run_gate(env, interp, "--json", "--dry-run", "--now", "2026-03-09T16:05:00+00:00"))
    assert on["filed"] is True and on["key"].endswith("2026-03-09-12"), on
    off = first_result(run_gate(env, interp, "--json", "--dry-run", "--now", "2026-03-09T15:05:00+00:00"))
    assert off["filed"] is False, off


def test_the_card_names_the_user_language(tmp_path):
    env, _ = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", "---\nsearch: active\nuser_language: es\n---\n", use=True)
    result = first_result(run_gate(env, sys.executable, "--json", "--dry-run", "--now", "2026-10-21 12:05"))
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


# --- freshness: each check reads only what appeared since the previous one ---------------------------------------

def profile_with(times: str | None) -> str:
    line = f"search_times: {times}\n" if times is not None else ""
    return f"---\nsearch: active\nuser_language: es\ntimezone: America/Bogota\n{line}---\n"


def test_without_search_times_one_midday_check_reads_the_last_day(tmp_path):
    # A posting loses most of its chance within a day: the default is one check at 12:00 that reads the 24 h since
    # yesterday's check, not two weeks of postings.
    env, _ = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", profile_with(None), use=True)
    assert first_result(run_gate(env, sys.executable, "--json", "--dry-run", "--now", "2026-10-21 08:05"))[
        "filed"] is False
    noon = first_result(run_gate(env, sys.executable, "--json", "--dry-run", "--now", "2026-10-21 12:10"))
    assert noon["key"] == "jobs:search:ana-search:2026-10-21-12", noon
    assert (noon["since"], noon["window_hours"]) == ("2026-10-20 12:00", 24), noon


def test_two_checks_split_the_day_and_the_card_tells_the_scout_the_window(tmp_path):
    # A person who wants a morning and an afternoon look: 09:00 reads since yesterday 15:00 (18 h), 15:00 reads the
    # 6 h since the morning. The card body carries the window the scout must pass to the portals.
    env, root = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", profile_with('["09:00", "15:00"]'), use=True)
    morning = first_result(run_gate(env, sys.executable, "--json", "--now", "2026-10-21 09:20"))
    afternoon = first_result(run_gate(env, sys.executable, "--json", "--now", "2026-10-21 15:05"))
    assert (morning["since"], morning["window_hours"]) == ("2026-10-20 15:00", 18), morning
    assert (afternoon["since"], afternoon["window_hours"]) == ("2026-10-21 09:00", 6), afternoon
    assert sorted(cards(root)) == ["jobs:search:ana-search:2026-10-21-09", "jobs:search:ana-search:2026-10-21-15"]
    body = afternoon["command"][afternoon["command"].index("--body") + 1]
    assert "--max-age-hours 6" in body and "--since 2026-10-21" in body, body


def test_monday_reaches_back_over_the_weekend_but_never_further(tmp_path):
    # Monday 2026-10-26 12:00: the previous check was Friday 12:00, 72 h back; the weekend's postings are read once.
    env, _ = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", profile_with('["12:00"]'), use=True)
    monday = first_result(run_gate(env, sys.executable, "--json", "--dry-run", "--now", "2026-10-26 12:05"))
    assert (monday["since"], monday["window_hours"]) == ("2026-10-23 12:00", 72), monday


@pytest.mark.parametrize("times", ['["25:00"]', '["09:00", "09:30"]', '["7", "9", "11", "13", "15"]', '"noon"'])
def test_bad_search_times_stop_the_search_with_a_message(tmp_path, times):
    env, _ = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", profile_with(times), use=True)
    p = run_gate(env, sys.executable, "--now", "2026-10-21 12:05")
    assert p.returncode == 1 and "search_times" in p.stdout and "no se ejecutó" in p.stdout, p.stdout + p.stderr


def test_the_owner_hears_once_a_day_what_the_search_decided(tmp_path):
    """2026-10-25: every run printed nothing, a weekend included, and the owner thought searches had stopped Friday."""
    env, root = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", profile_with('["09:00", "15:00"]'), use=True)
    said = {now: run_gate(env, SYSTEM_PY if Path(SYSTEM_PY).is_file() else sys.executable, "--now", now).stdout.strip()
            for now in ("2026-10-24 09:05", "2026-10-24 10:05", "2026-10-26 08:05", "2026-10-26 09:05",
                        "2026-10-26 10:05", "2026-10-26 15:05")}
    assert said["2026-10-24 09:05"].startswith("Hoy no hay búsqueda (sábado 2026-10-24)"), said
    assert "Próxima: lunes 09:00" in said["2026-10-24 09:05"]
    assert said["2026-10-24 10:05"] == said["2026-10-26 08:05"] == said["2026-10-26 10:05"] == "", said
    assert said["2026-10-26 09:05"].startswith("Búsqueda 2026-10-26-09 lanzada para ana-search"), said
    assert said["2026-10-26 15:05"].startswith("Búsqueda 2026-10-26-15 lanzada"), said


def test_a_paused_search_says_so_on_weekdays(tmp_path):
    env, _ = make_env(tmp_path)
    board(env)
    add_project(env, tmp_path, "ana-search", "---\nsearch: paused\nuser_language: en\ntimezone: America/Lima\n---\n",
                use=True)
    assert "Search paused for ana-search" in run_gate(env, sys.executable, "--now", "2026-10-21 12:05").stdout
    assert run_gate(env, sys.executable, "--now", "2026-10-21 13:05").stdout == ""
