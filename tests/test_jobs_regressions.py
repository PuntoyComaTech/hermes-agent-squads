"""Field regressions: each test replays a failure a real job search hit, against the scripts the bots run."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
JOBS = REPO / "squads" / "jobs"
SCRIPTS = JOBS / "skills" / "jobs-contract" / "scripts"
JOB_KEY = SCRIPTS / "job_key.py"
STATUS = SCRIPTS / "status.py"
TRACKER = SCRIPTS / "tracker.py"
SEEN = SCRIPTS / "seen_state.py"
PORTALS = JOBS / "skills" / "searching-portals" / "scripts"


def key(company, title, url=""):
    argv = [sys.executable, str(JOB_KEY), "--company", company, "--title", title] + (["--url", url] if url else [])
    done = subprocess.run(argv, capture_output=True, text=True, check=True)
    return done.stdout.strip()


# --- dedupe keys: a search across European employers ----------------------------------------------------------

def test_nordic_and_central_european_names_keep_their_letters():
    # Before the fold table, "Ørsted" keyed as "rsted" and "Łódź" lost its first letter: the opening folder the
    # user sees was unreadable.
    assert key("Ørsted A/S", "Data Engineer") == "orsted-a-s_data-engineer"
    assert key("Łódź Tech", "Analityk danych") == "lodz-tech_analityk-danych"
    assert key("Straße GmbH", "Analyst") == "strasse-gmbh_analyst"
    assert key("Peña y Asociados", "Analista de datos") == "pena-y-asociados_analista-de-datos"


def test_two_different_employers_never_share_a_key():
    # "Ærø" and "Rø" both folded to "r": the second company's opening was dropped as a duplicate of the first.
    assert key("Ærø Bank", "Analyst") != key("Rø Bank", "Analyst")
    # Same story for partly non-Latin names: only the Latin fragment used to survive.
    assert key("Яндекс", "Программист 1С") != key("Яндекс", "Аналитик 1С")
    assert key("Сбер AI", "ML Engineer") != key("Яндекс AI", "ML Engineer")


def test_the_same_posting_found_twice_keeps_one_key():
    # A run on Monday and one on Tuesday must agree, or seen.json grows a duplicate per run.
    first = key("Ørsted A/S", "Senior Data Engineer (m/f/d)", "https://jobs.example.com/view/123456?utm_source=x")
    second = key("Ørsted A/S", "Senior Data Engineer (m/f/d)", "https://jobs.example.com/view/123456")
    assert first == second


def test_seen_state_treats_a_repeat_as_known(tmp_path):
    (tmp_path / "profile.md").write_text("---\nsearch: active\n---\n")
    entry = {"key": key("Ørsted A/S", "Data Engineer"), "company": "Ørsted A/S", "title": "Data Engineer",
             "url": "https://jobs.example.com/view/123456", "portal": "linkedin", "posted_at": "2026-10-18",
             "deadline": None, "opening_id": "JOB-20261020-orsted-a-s-data-engineer"}
    batch = tmp_path / "batch.json"
    batch.write_text(json.dumps([entry]))
    argv = [sys.executable, str(SEEN), "add", "--project", str(tmp_path), "--file", str(batch), "--today", "2026-10-20"]
    first = json.loads(subprocess.run(argv, capture_output=True, text=True, check=True).stdout)
    second = json.loads(subprocess.run(argv, capture_output=True, text=True, check=True).stdout)
    assert first["added"] == [entry["key"]] and second["added"] == []


# --- one status vocabulary ----------------------------------------------------------------------------------------

def test_status_history_and_tracker_accept_exactly_the_same_statuses(tmp_path):
    sys.path.insert(0, str(SCRIPTS))
    import jobs_common
    # Every status the history accepts must also be a valid tracker row (a fresh row per status, because the
    # tracker rightly refuses to move a submitted application backwards).
    for n, status in enumerate(jobs_common.STATUSES):
        project = tmp_path / status
        opening = project / "openings" / "JOB-20261020-acme-data-analyst"
        opening.mkdir(parents=True)
        (project / "profile.md").write_text("---\nsearch: active\n---\n")
        hist = subprocess.run([sys.executable, str(STATUS), "append", str(opening), status, "--by", "jobs"],
                              capture_output=True, text=True)
        row = subprocess.run([sys.executable, str(TRACKER), "add", "--project", str(project), "--id",
                              "JOB-20261020-acme-data-analyst", "--company", "Acme", "--role", "Data analyst",
                              "--status", status], capture_output=True, text=True)
        assert hist.returncode == 0, (status, hist.stderr)
        assert row.returncode == 0, (status, row.stderr)
    bogus = subprocess.run([sys.executable, str(STATUS), "append", str(opening), "sent", "--by", "jobs"],
                           capture_output=True, text=True)
    assert bogus.returncode != 0


def test_contract_reference_lists_the_same_statuses():
    sys.path.insert(0, str(SCRIPTS))
    import jobs_common
    text = (JOBS / "skills" / "jobs-contract" / "references" / "opening-files.md").read_text()
    listed = re.search(r"Statuses, lowercase snake_case: (.*?)\. Written", text, re.S).group(1)
    assert [s.strip() for s in listed.replace("\n", " ").split(",")] == list(jobs_common.STATUSES)


# --- portals: install safety and query syntax ---------------------------------------------------------------------

@pytest.mark.parametrize("pkg", sorted(PORTALS.glob("*/package.json")), ids=lambda p: p.parent.name)
def test_portal_install_runs_no_code(pkg):
    # A lifecycle script runs on `bun install` with the user's rights; a portal never needs one.
    data = json.loads(pkg.read_text())
    lifecycle = {"preinstall", "install", "postinstall", "prepare", "prepack", "prepublish", "preprepare"}
    assert not lifecycle & set(data.get("scripts") or {}), pkg
    assert "trustedDependencies" not in data
    assert not data.get("dependencies"), "shipped portals have zero runtime dependencies"


def test_adding_portals_template_runs_no_code():
    for pkg in (JOBS / "skills" / "adding-portals" / "templates").rglob("package.json"):
        data = json.loads(pkg.read_text())
        assert not {"preinstall", "install", "postinstall", "prepare"} & set(data.get("scripts") or {}), pkg


def test_portal_search_rules_forbid_boolean_query_strings():
    # Boards do not read OR or quoted phrases; a combined query silently returns a different set.
    text = (JOBS / "skills" / "searching-portals" / "SKILL.md").read_text()
    assert re.search(r"one (plain )?(term|phrase|keyword)[^.\n]*per (call|search)", text, re.I), text
    assert "OR" in text
