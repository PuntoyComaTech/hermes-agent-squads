"""Tests for the analysis stage: seen_state.py, salary_lookup.py, score_analysis.py and triage_merge.py.

Covers the scoring maths and bands, the gates and deal-breakers, the decision rules, employer-call advice, the
company cache window, the salary benchmark, the batch write-back to seen.json, and the CLI contract (--help,
exit codes, JSON on stdout). Every test runs on fixtures in a temporary folder. Nothing touches the network.
"""
from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "squads" / "jobs" / "skills"
CONTRACT = SKILLS / "jobs-contract" / "scripts"
ANALYZE = SKILLS / "analyzing-jobs" / "scripts"
RANK = SKILLS / "ranking-openings" / "scripts"
SEEN = CONTRACT / "seen_state.py"
SALARY = CONTRACT / "salary_lookup.py"
SCORE = ANALYZE / "score_analysis.py"
MERGE = RANK / "triage_merge.py"

for folder in (CONTRACT, ANALYZE):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import jobs_common as jc  # noqa: E402
import salary_lookup as sl  # noqa: E402
import score_analysis as sa  # noqa: E402
import seen_state as ss  # noqa: E402

TODAY = "2026-10-20"
NOW = "2026-10-20T10:00:00Z"
OPENING = "JOB-20261001-example-co-data-analyst"

PROFILE = """---
occupation: "Data analyst"
target_roles: ["Data analyst", "BI analyst"]
years_experience: {total: 4, in_role: 3}
seniority: mid-level
search_keywords: {en: ["data analyst"]}
max_required_language: {english: B2}
work_mode: [remote_region, hybrid]
cities: [Lima]
market: {country: PE, cv_page_limit: 2}
eligibility:
  - {country: PE, status: citizen}
  - {country: US, status: needs_sponsorship, notes: ""}
languages_policy: {flag_gap_steps: 1, discard_gap_steps: 2}
scoring:
  weights: {technical: 30, experience: 25, behavioral: 15, career: 30}
  bands: {strong: 75, good: 60, moderate: 45, weak: 30}
deal_breakers: ["on-call weekends"]
career_goals: ["analytics lead"]
energizers: ["dashboards"]
drains: ["manual reporting"]
salary_data: salary.csv
apply_threshold: 70
---
Notes for the candidate.
"""

ACHIEVEMENTS = """languages:
  - {language: english, level: B2, verified: true}
achievements:
  - id: ACH-007
    experience: EXP-001
    proficiency: led
    en: "Automated the weekly sales report with Python."
    tags: [automation, python]
    verified: true
  - id: ACH-009
    experience: EXP-001
    proficiency: did
    en: "An unconfirmed claim."
    verified: false
"""

SALARY_CSV = """company,city,all_employees_count,all_employees_index
Example Co S.A.C.,Lima,120,108.5
Sample Works Ltd,Cusco,40,101
"""

OPENING_BODY = "Data analyst. Python and SQL required. Dashboards and reporting. Some travel to Lima."


# --- helpers ------------------------------------------------------------------------------------------------------

def make_project(tmp_path: Path, profile: str = PROFILE, achievements: str = ACHIEVEMENTS,
                 salary: bool = True, seen: dict | None = None) -> Path:
    root = tmp_path / "P"
    for sub in ("searches", "openings", "companies"):
        (root / sub).mkdir(parents=True)
    (root / "profile.md").write_text(profile, encoding="utf-8")
    (root / "achievements.yaml").write_text(achievements, encoding="utf-8")
    if salary:
        (root / "salary.csv").write_text(SALARY_CSV, encoding="utf-8")
    if seen is not None:
        jc.write_json(root / "searches" / "seen.json", {"schema": 1, "seen": seen})
    return root


def make_opening(root: Path, opening_id: str = OPENING, body: str = OPENING_BODY, front: list | None = None) -> Path:
    lines = front if front is not None else [
        f"id: {opening_id}", "company: Example Co", "role: Data analyst", "url: https://example.com/jobs/1",
        "posted_at: 2026-10-05", "deadline: 2026-11-30", "work_mode: remote_region:latam",
        "required_language: {english: B2}",
    ]
    folder = root / "openings" / opening_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "opening.md").write_text("---\n" + "\n".join(lines) + "\n---\n" + body + "\n", encoding="utf-8")
    return folder


def analysis_doc(**over) -> dict:
    doc = {
        "id": OPENING,
        "requirements": {
            "must_have": ["SQL"], "nice_to_have": ["Power BI"],
            "responsibilities": ["build dashboards", "maintain reports"], "tools": ["Python"],
            "keywords": ["SQL", "dashboards"], "disqualifiers": [], "priorities": ["SQL"],
        },
        "company": {"name": "Example Co", "summary": "Retail analytics", "sector": "retail"},
        "evidence": [{"requirement": "SQL", "achievements": ["ACH-007"], "confidence": 0.8, "note": ""}],
        "fit": {
            "dimensions": {
                "technical": {"score": 80, "note": "SQL and Python"},
                "experience": {"score": 70, "note": "reporting"},
                "behavioral": {"score": 60, "note": "neutral"},
                "career": {"score": 75, "note": "dashboards"},
            },
            "decision": "PURSUE", "strengths": ["SQL"], "gaps": ["Kubernetes"], "hard_gaps": [],
            "transferable": [], "overselling_risk": "low", "reason": "fits the stated skills",
        },
    }
    doc.update(over)
    return doc


def write_analysis(folder: Path, doc: dict) -> None:
    (folder / "analysis.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")


def profile_dict() -> dict:
    return jc.split_front_matter(PROFILE)[0]


def run(script: Path, *args) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True,
                          timeout=120)


def run_json(script: Path, *args):
    proc = run(script, *args)
    payload = json.loads(proc.stdout) if proc.stdout.strip().startswith(("{", "[")) else None
    return proc, payload


def seen_entry(**over) -> dict:
    entry = {
        "company": "Acme", "title": "Data analyst", "url": "https://acme.example/1", "status": "new",
        "first_seen": "2026-10-18", "portal": "freehire",
    }
    entry.update(over)
    return entry


def load_seen(root: Path) -> dict:
    return json.loads((root / "searches" / "seen.json").read_text(encoding="utf-8"))["seen"]


def scored(key: str, **over) -> dict:
    row = {"key": key, "status": "scored",
           "scores": {"technical": 80, "experience": 70, "behavioral": 60, "career": 75},
           "location_verdict": "PASS", "language_gate": "PASS", "strengths": ["SQL"], "gaps": ["Kubernetes"]}
    row.update(over)
    return row


def apply_results(root: Path, results: list, *extra) -> tuple:
    results_file = root / "results.json"
    results_file.write_text(json.dumps(results), encoding="utf-8")
    return run_json(SEEN, "apply", "--project", root, "--results", results_file, "--today", TODAY,
                    "--now", NOW, *extra)


# --- scoring maths and bands ---------------------------------------------------------------------------------------

def test_default_weights_bands_and_threshold_match_the_spec():
    cfg = ss.scoring_config({})
    assert cfg["weights"] == {"technical": 30, "experience": 25, "behavioral": 15, "career": 30}
    assert cfg["bands"] == {"strong": 75, "good": 60, "moderate": 45, "weak": 30}
    assert cfg["apply_threshold"] == 70


def test_overall_score_is_the_weighted_mean_rounded_half_up():
    scores = {"technical": 80, "experience": 70, "behavioral": 60, "career": 75}
    assert ss.overall_score(scores, ss.DEFAULT_WEIGHTS) == 73
    # 30 + 1.5 = 31.5 rounds half up to 32
    assert ss.overall_score({"technical": 100, "experience": 0, "behavioral": 0, "career": 5},
                            ss.DEFAULT_WEIGHTS) == 32


def test_band_boundaries_follow_the_profile_floors():
    bands = ss.DEFAULT_BANDS
    expected = {75: "strong", 74: "good", 60: "good", 59: "moderate", 45: "moderate", 44: "weak", 30: "weak",
                29: "poor"}
    for score, band in expected.items():
        assert ss.band_for(score, bands) == band, score


def test_custom_weights_from_profile_are_used():
    cfg = ss.scoring_config({"scoring": {"weights": {"technical": 40, "experience": 20, "behavioral": 20,
                                                     "career": 20}}})
    assert ss.overall_score({"technical": 100, "experience": 0, "behavioral": 0, "career": 0},
                            cfg["weights"]) == 40


@pytest.mark.parametrize("block, message", [
    ({"weights": {"technical": 40, "experience": 25, "behavioral": 15, "career": 30}}, "sum to 100"),
    ({"bands": {"strong": 60, "good": 75, "moderate": 45, "weak": 30}}, "must not increase"),
    ({"weights": {"technical": 30, "experience": 25, "behavioral": 15}}, "missing"),
])
def test_bad_scoring_config_is_refused(block, message):
    with pytest.raises(ValueError, match=message):
        ss.scoring_config({"scoring": block})


def test_out_of_range_or_boolean_scores_are_refused():
    with pytest.raises(ValueError):
        ss.overall_score({"technical": 101, "experience": 0, "behavioral": 0, "career": 0}, ss.DEFAULT_WEIGHTS)
    with pytest.raises(ValueError):
        ss.overall_score({"technical": True, "experience": 0, "behavioral": 0, "career": 0}, ss.DEFAULT_WEIGHTS)


# --- seen_state: candidates, sweep, add, audit, stats --------------------------------------------------------------

def test_candidates_select_new_and_unreachable_and_exclude_tracker_pairs(tmp_path):
    root = make_project(tmp_path, seen={
        "acme|data-analyst": seen_entry(),
        "beta|bi-analyst": seen_entry(company="Beta", title="BI analyst"),
        "gamma|data-analyst": seen_entry(company="Gamma", status="unreachable", fetch_attempts=1),
        "delta|data-analyst": seen_entry(company="Delta", status="skipped"),
        "eps|data-analyst": seen_entry(company="Eps", status="ranked", rank_score=50),
    })
    (root / "tracker.csv").write_text("date,company,role,status\n2026-10-01,Beta,BI analyst,applied\n", encoding="utf-8")
    proc, out = run_json(SEEN, "candidates", "--project", root, "--today", TODAY)
    assert proc.returncode == 0
    keys = {row["key"] for row in out["selected"]}
    assert keys == {"acme|data-analyst", "gamma|data-analyst"}
    assert out["excluded_by_tracker"] == 1
    assert out["eligible"] == 2 and out["deferred"] == 0


def test_candidates_limit_reports_deferred_and_focus_filters(tmp_path):
    root = make_project(tmp_path, seen={
        "a|data-analyst": seen_entry(company="A"),
        "b|bi-analyst": seen_entry(company="B", title="BI analyst"),
        "c|data-analyst": seen_entry(company="C"),
    })
    _, out = run_json(SEEN, "candidates", "--project", root, "--limit", "1")
    assert len(out["selected"]) == 1 and out["deferred"] == 2
    _, focused = run_json(SEEN, "candidates", "--project", root, "--focus", "bi analyst")
    assert [row["key"] for row in focused["selected"]] == ["b|bi-analyst"]


def test_candidates_saved_only_and_analysed_entries_are_left_out_unless_all(tmp_path):
    root = make_project(tmp_path, seen={
        "saved|data-analyst": seen_entry(company="Saved", opening_id="JOB-x"),
        "unsaved|data-analyst": seen_entry(company="Unsaved"),
        "analysed|data-analyst": seen_entry(company="Analysed", opening_id="JOB-y", analysis_decision="PURSUE"),
    })
    _, saved = run_json(SEEN, "candidates", "--project", root, "--saved")
    assert [row["key"] for row in saved["selected"]] == ["saved|data-analyst"]
    _, default = run_json(SEEN, "candidates", "--project", root)
    assert {row["key"] for row in default["selected"]} == {"saved|data-analyst", "unsaved|data-analyst"}
    _, everything = run_json(SEEN, "candidates", "--project", root, "--all")
    assert "analysed|data-analyst" in {row["key"] for row in everything["selected"]}


def test_missing_profile_is_a_clear_error(tmp_path):
    proc = run(SEEN, "candidates", "--project", tmp_path)
    assert proc.returncode != 0
    assert "profile.md" in proc.stderr


def test_sweep_expires_passed_deadlines_and_lists_closing_ones(tmp_path):
    root = make_project(tmp_path, seen={
        "passed|a": seen_entry(company="Passed", status="ranked", deadline="2026-10-10", rank_score=60),
        "closing|a": seen_entry(company="Closing", deadline="2026-10-25"),
        "later|a": seen_entry(company="Later", deadline="2026-12-01"),
        "odd|a": seen_entry(company="Odd", deadline="ASAP"),
        "none|a": seen_entry(company="None"),
        "skipped|a": seen_entry(company="Skip", status="skipped", deadline="2026-01-01"),
    })
    before = (root / "searches" / "seen.json").read_bytes()
    _, dry = run_json(SEEN, "sweep", "--project", root, "--today", TODAY)
    assert [r["key"] for r in dry["newly_expired"]] == ["passed|a"]
    assert [r["key"] for r in dry["closing_soon"]] == ["closing|a"]  # 2026-10-25 is 5 days out
    assert [r["key"] for r in dry["unparseable_deadlines"]] == ["odd|a"]
    assert dry["written"] is False
    assert (root / "searches" / "seen.json").read_bytes() == before

    _, written = run_json(SEEN, "sweep", "--project", root, "--today", TODAY, "--write")
    assert written["written"] is True
    assert load_seen(root)["passed|a"]["status"] == "expired"
    assert load_seen(root)["passed|a"]["expired_reason"] == "deadline_passed"
    assert load_seen(root)["later|a"]["status"] == "new"


def test_sweep_exclude_leaves_keys_alone(tmp_path):
    root = make_project(tmp_path, seen={"passed|a": seen_entry(deadline="2026-10-10", status="ranked")})
    _, out = run_json(SEEN, "sweep", "--project", root, "--today", TODAY, "--write", "--exclude", "passed|a")
    assert out["newly_expired"] == [] and out["written"] is False


def test_add_registers_entries_and_keeps_existing_status(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry(status="ranked", rank_score=55)})
    items = root / "items.json"
    items.write_text(json.dumps([
        {"key": "acme|data-analyst", "company": "Acme", "title": "Data analyst", "url": "https://acme.example/1",
         "posted_at": "2026-10-19"},
        {"key": "zeta|sales-analyst", "company": "Zeta", "title": "Sales analyst", "posted_at": "unknown"},
        {"key": "bad|date", "company": "Bad", "title": "Date", "posted_at": "19/10/2026"},
        {"key": "", "company": "No", "title": "Key"},
    ]), encoding="utf-8")
    proc, out = run_json(SEEN, "add", "--project", root, "--file", items, "--today", TODAY)
    assert proc.returncode == 1
    assert out["added"] == ["zeta|sales-analyst"]
    assert out["updated"][0]["key"] == "acme|data-analyst"
    assert "posted_at" in out["updated"][0]["filled"]
    assert len(out["errors"]) == 2
    seen = load_seen(root)
    assert seen["acme|data-analyst"]["status"] == "ranked"
    assert seen["zeta|sales-analyst"]["status"] == "new"
    assert seen["zeta|sales-analyst"].get("posted_at") is None


def test_audit_flags_bad_state_and_stats_count_by_status(tmp_path):
    root = make_project(tmp_path, seen={
        "good|a": seen_entry(company="Good", status="ranked", rank_score=70, rank_band="good"),
        "weird|a": seen_entry(company="Weird", status="maybe"),
        "dup|a": seen_entry(company="Good", title="Data analyst"),
        "loc|a": seen_entry(company="Loc", location="PASS"),
    })
    proc, audit = run_json(SEEN, "audit", "--project", root, "--strict")
    assert proc.returncode == 1 and audit["ok"] is False
    issues = {p["key"]: p["issue"] for p in audit["problems"]}
    assert "unknown status" in issues["weird|a"]
    assert "location" in issues["loc|a"]
    assert any("good|a" in d["keys"] for d in audit["possible_duplicates"])
    _, stats = run_json(SEEN, "stats", "--project", root, "--today", TODAY)
    assert stats["total"] == 4 and stats["by_status"]["ranked"] == 1 and stats["ranked_by_band"] == {"good": 1}


def test_stale_flag_follows_posted_at_and_is_never_inferred(tmp_path):
    root = make_project(tmp_path, seen={
        "old|a": seen_entry(company="Old", posted_at="2026-08-01"),
        "undated|a": seen_entry(company="Undated", first_seen="2026-01-01"),
    })
    _, stats = run_json(SEEN, "stats", "--project", root, "--today", TODAY)
    assert stats["stale_over_30_days"] == 1


# --- seen_state: apply (write-back) --------------------------------------------------------------------------------

def test_apply_writes_ranked_entry_with_its_gates_and_bookkeeping(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry(
        location="Lima, Peru", opening_id=None)})
    proc, out = apply_results(root, [scored("acme|data-analyst", deadline="2026-11-30",
                                            posted_at="2026-10-05", guard="posting_guard: clean (no findings)")])
    assert proc.returncode == 0, proc.stderr
    row = out["ranked"][0]
    assert row["score"] == 73 and row["band"] == "good"
    entry = load_seen(root)["acme|data-analyst"]
    assert entry["status"] == "ranked"
    assert entry["rank_score"] == 73 and entry["rank_band"] == "good"
    assert entry["rank_scores"] == {"technical": 80, "experience": 70, "behavioral": 60, "career": 75}
    assert entry["location"] == "Lima, Peru"  # the place string is never replaced by a verdict
    assert entry["location_verdict"] == "PASS"
    assert entry["guard"] == "clean"
    assert entry["deadline"] == "2026-11-30" and entry["posted_at"] == "2026-10-05"


def test_apply_migrates_a_legacy_verdict_stored_in_location(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry(location="FLAG")})
    proc, _ = apply_results(root, [scored("acme|data-analyst", location_verdict=None)])
    assert proc.returncode == 0
    entry = load_seen(root)["acme|data-analyst"]
    assert entry["location_verdict"] == "FLAG"
    assert "location" not in entry


def test_apply_never_overwrites_a_stored_deadline_with_null(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry(deadline="2026-11-15")})
    apply_results(root, [scored("acme|data-analyst", deadline=None)])
    assert load_seen(root)["acme|data-analyst"]["deadline"] == "2026-11-15"


def test_apply_expires_when_the_fresh_deadline_has_passed(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry(
        fetch_attempts=2, first_unreachable="2026-10-16T08:00:00Z")})
    _, out = apply_results(root, [scored("acme|data-analyst", deadline="2026-10-10")])
    assert [r["key"] for r in out["expired"]] == ["acme|data-analyst"]
    entry = load_seen(root)["acme|data-analyst"]
    assert entry["status"] == "expired" and "fetch_attempts" not in entry


def test_apply_keeps_strengths_and_gaps_verbatim_and_capped(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry()})
    strengths = ["  Ships SQL dashboards weekly.  ", "b", "c", "d"]
    apply_results(root, [scored("acme|data-analyst", strengths=strengths, gaps=["Kubernetes: none"])])
    entry = load_seen(root)["acme|data-analyst"]
    assert entry["strengths"] == ["Ships SQL dashboards weekly.", "b", "c"]
    assert entry["gaps"] == ["Kubernetes: none"]


def test_apply_drops_a_stale_guard_when_the_fetch_has_none(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry(guard="hidden text found")})
    apply_results(root, [scored("acme|data-analyst")])
    assert "guard" not in load_seen(root)["acme|data-analyst"]


def test_apply_normalises_the_guard_verdict(tmp_path):
    root = make_project(tmp_path, seen={"a|x": seen_entry(company="A"), "b|x": seen_entry(company="B")})
    apply_results(root, [scored("a|x", guard="clean"),
                         scored("b|x", guard="posting_guard: hidden text in a footer")])
    seen = load_seen(root)
    assert seen["a|x"]["guard"] == "clean"
    assert seen["b|x"]["guard"] == "hidden text in a footer"


def test_apply_retires_a_vetoed_row_to_the_vetoed_list_with_reasons(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry()})
    _, out = apply_results(root, [scored("acme|data-analyst", location_verdict="FAIL")])
    assert out["ranked"] == []
    assert out["vetoed"][0]["vetoed_by"] == ["location"]


def test_apply_records_the_eligibility_gate_and_deal_breaker_flag(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry()})
    _, out = apply_results(root, [scored("acme|data-analyst", eligibility_gate="FAIL", deal_breaker=True)])
    assert out["ranked"] == []
    assert set(out["vetoed"][0]["vetoed_by"]) == {"eligibility", "deal_breaker"}


def test_apply_reports_bad_results_without_touching_the_entry(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry()})
    before = load_seen(root)["acme|data-analyst"]
    proc, out = apply_results(root, [
        {"key": "acme|data-analyst", "status": "scored", "scores": {"technical": 120, "experience": 1,
                                                                   "behavioral": 1, "career": 1}},
        {"key": "acme|data-analyst", "status": "bogus"},
        {"key": "nope|x", "status": "scored", "scores": {}},
    ])
    assert proc.returncode == 1
    assert len(out["errors"]) == 3
    assert load_seen(root)["acme|data-analyst"] == before


def test_apply_dry_run_writes_nothing(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry()})
    before = (root / "searches" / "seen.json").read_bytes()
    proc, out = apply_results(root, [scored("acme|data-analyst")], "--dry-run")
    assert proc.returncode == 0 and out["written"] is False and out["ranked"]
    assert (root / "searches" / "seen.json").read_bytes() == before


def test_unreachable_is_retried_then_given_up_only_after_the_span_floor(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry(
        fetch_attempts=2, first_unreachable="2026-10-16T08:00:00Z", last_fetch_error="timeout")})
    proc, out = apply_results(root, [{"key": "acme|data-analyst", "status": "unreachable",
                                      "fetch_error": "403 after retry"}])
    assert proc.returncode == 0
    assert out["gave_up"][0]["fetch_attempts"] == 3
    entry = load_seen(root)["acme|data-analyst"]
    assert entry["status"] == "expired" and entry["expired_reason"] == "unreachable"
    assert entry["last_fetch_error"] == "403 after retry"


def test_unreachable_stays_retryable_when_the_attempts_are_too_close_together(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry(
        fetch_attempts=2, first_unreachable="2026-10-20T08:00:00Z")})
    _, out = apply_results(root, [{"key": "acme|data-analyst", "status": "unreachable", "fetch_error": "504"}])
    assert out["gave_up"] == [] and out["unreachable"][0]["fetch_attempts"] == 3
    entry = load_seen(root)["acme|data-analyst"]
    assert entry["status"] == "unreachable"


def test_unreachable_with_a_passed_stored_deadline_expires_at_once(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry(deadline="2026-10-01")})
    _, out = apply_results(root, [{"key": "acme|data-analyst", "status": "unreachable", "fetch_error": "404"}])
    assert [r["key"] for r in out["expired"]] == ["acme|data-analyst"]
    assert load_seen(root)["acme|data-analyst"]["status"] == "expired"


def test_agent_expired_status_retires_the_entry(tmp_path):
    root = make_project(tmp_path, seen={"acme|data-analyst": seen_entry()})
    _, out = apply_results(root, [{"key": "acme|data-analyst", "status": "expired"}])
    assert [r["key"] for r in out["expired"]] == ["acme|data-analyst"]
    assert load_seen(root)["acme|data-analyst"]["status"] == "expired"


# --- salary_lookup -------------------------------------------------------------------------------------------------

def test_salary_lookup_matches_accent_case_and_legal_suffix_insensitively(tmp_path):
    root = make_project(tmp_path)
    proc = run(SALARY, "EXAMPLE co", "--project", root, "--json")
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["available"] is True
    assert data["matches"][0]["company"] == "Example Co S.A.C."
    assert data["matches"][0]["categories"]["all_employees"]["vs_baseline_pct"] == 8.5


def test_salary_lookup_city_filter_and_no_match(tmp_path):
    root = make_project(tmp_path)
    by_city = json.loads(run(SALARY, "Sample Works", "--project", root, "--city", "cusco", "--json").stdout)
    assert [m["company"] for m in by_city["matches"]] == ["Sample Works Ltd"]
    wrong_city = run(SALARY, "Sample Works", "--project", root, "--city", "Lima")
    assert wrong_city.returncode == 0 and "No match" in wrong_city.stdout
    nothing = run(SALARY, "Unknown Widgets Ltd", "--project", root)
    assert "No match" in nothing.stdout


def test_salary_lookup_skips_gracefully_without_a_data_file(tmp_path):
    root = make_project(tmp_path, salary=False)
    proc = run(SALARY, "Example Co", "--project", root, "--json")
    assert proc.returncode == 0
    assert json.loads(proc.stdout)["available"] is False
    unset = make_project(tmp_path / "other", profile=PROFILE.replace("salary_data: salary.csv",
                                                                     "salary_data: null"))
    skipped = run(SALARY, "Example Co", "--project", unset)
    assert skipped.returncode == 0 and "skipped" in skipped.stdout


def test_salary_lookup_refuses_a_malformed_data_file(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"companies": "not a list"}', encoding="utf-8")
    proc = run(SALARY, "Example Co", "--data", bad)
    assert proc.returncode == 1 and "companies" in proc.stderr


def test_convert_csv_handles_decimal_commas_and_thousands(tmp_path):
    source = tmp_path / "pay.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["company", "city", "all_employees_count", "all_employees_index"])
        writer.writerow(["Example Co", "Lima", "1,234", "108,5"])
    out = tmp_path / "pay.json"
    proc = run(SALARY, "--convert", source, "--out", out, "--source", "Fixture 2026")
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert doc["metadata"]["source"] == "Fixture 2026"
    slot = doc["companies"][0]["categories"]["all_employees"]
    assert slot == {"count": 1234, "index": 108.5}
    looked = json.loads(run(SALARY, "Example Co", "--data", out, "--json").stdout)
    assert looked["matches"][0]["categories"]["all_employees"]["index"] == 108.5


def test_convert_refuses_an_ambiguous_number(tmp_path):
    source = tmp_path / "pay.csv"
    source.write_text("company,all_employees_index\nExample Co,\"12,34.5\"\n", encoding="utf-8")
    proc = run(SALARY, "--convert", source)
    assert proc.returncode == 1 and "ambiguous" in proc.stderr


def test_list_all_prints_every_company(tmp_path):
    root = make_project(tmp_path)
    proc = run(SALARY, "--list-all", "--project", root)
    assert proc.returncode == 0
    assert "Example Co S.A.C. (Lima)" in proc.stdout and "Sample Works Ltd (Cusco)" in proc.stdout


# --- score_analysis: gates ----------------------------------------------------------------------------------------

def test_eligibility_is_unverified_when_the_posting_is_silent():
    gate, note = sa.eligibility_gate(profile_dict(), {}, OPENING_BODY)
    assert gate == "PASS" and note.startswith("eligibility_unverified")


def test_eligibility_fails_a_sponsorship_refusal_for_a_candidate_who_needs_it():
    gate, note = sa.eligibility_gate(profile_dict(), {"work_mode": "remote_country:US"},
                                     "Remote role. We do not offer visa sponsorship.")
    assert gate == "FAIL" and "sponsorship" in note


def test_eligibility_flags_citizen_wording_for_a_citizen_rather_than_passing_it():
    gate, _ = sa.eligibility_gate(profile_dict(), {}, "Citizens of Peru only for this role.")
    assert gate == "FLAG"


@pytest.mark.parametrize("required, declared, expected", [
    ({"english": "B2"}, "B2", "PASS"),
    ({"english": "C1"}, "B2", "FLAG"),
    ({"english": "C2"}, "B1", "FAIL"),
    ({"spanish": "B1"}, "B2", "FAIL"),
    ({"english": "fluent"}, "B2", "FLAG"),
    ({"english": "not_required"}, "B2", "PASS"),
])
def test_language_gate_follows_the_cefr_gap_rules(required, declared, expected):
    achievements = {"languages": [{"language": "english", "level": declared}]}
    verdict, _ = sa.language_gate({"required_language": required}, achievements, None)
    assert verdict == expected


def test_location_gate_checks_work_mode_and_cities():
    profile = {**profile_dict(), "work_mode": ["remote_region", "remote_country", "hybrid"]}
    cases = {
        "remote_region:latam": "PASS",
        "hybrid:Lima": "PASS",
        "onsite:Bogota": "FAIL",
        "remote_global": "FAIL",
        "remote_country:PE": "PASS",     # the market country
        "remote_country:US": "FAIL",     # listed as needs_sponsorship: not a country the candidate can work in
        "remote_country:MX": "FAIL",     # not in the eligibility table
        "unknown": "FLAG",
    }
    for mode, expected in cases.items():
        assert sa.location_gate(profile, {"work_mode": mode})[0] == expected, mode


def test_location_gate_accepts_a_remote_country_where_the_candidate_is_resident():
    profile = {**profile_dict(), "work_mode": ["remote_country"],
               "eligibility": [{"country": "PE", "status": "citizen"}, {"country": "ES", "status": "resident"}]}
    assert sa.location_gate(profile, {"work_mode": "remote_country:ES"})[0] == "PASS"


def test_deal_breakers_match_verbatim_text_and_scout_disqualifiers_reject(tmp_path):
    hits = sa.deal_breaker_hits(profile_dict(), "Some ON-CALL WEEKENDS are expected.", {"company": {}})
    assert hits == ["on-call weekends"]


def test_decision_rules_run_in_the_documented_order():
    ok = {"eligibility": "PASS", "language": "PASS", "location": "PASS"}
    assert sa.decide({**ok, "eligibility": "FAIL"}, [], [], [], 90, 70)[0] == "REJECT"
    assert sa.decide(ok, ["on-call weekends"], [], [], 90, 70)[0] == "REJECT"
    assert sa.decide(ok, [], ["SQL"], ["SQL"], 90, 70)[0] == "REJECT"
    assert sa.decide(ok, [], ["Kubernetes"], ["SQL"], 90, 70)[0] == "PURSUE"  # a non-core gap only lowers the score
    assert sa.decide(ok, [], [], [], 65, 70)[0] == "WATCH"
    assert sa.decide(ok, [], [], [], 70, 70) == ("PURSUE", "score 70 is at or above apply_threshold 70")


def test_core_must_haves_fall_back_to_all_must_haves_when_no_priorities():
    assert sa.core_must_haves({"must_have": ["SQL"], "priorities": []}) == ["SQL"]
    assert sa.core_must_haves({"must_have": ["SQL", "Go"], "priorities": ["Go"]}) == ["Go"]


def test_employer_call_is_advised_only_for_substantive_questions():
    clear = analysis_doc()
    assert sa.employer_call(clear, OPENING_BODY, "PURSUE")["advised"] is False
    vague = analysis_doc(requirements={**clear["requirements"], "responsibilities": []})
    advice = sa.employer_call(vague, OPENING_BODY, "PURSUE")
    assert advice["advised"] is True and "tasks are vague" in advice["why"]
    assert len(advice["questions"]) == 4
    assert sa.employer_call(clear, "Feel free to contact the hiring manager.", "PURSUE")["advised"] is True
    assert sa.employer_call(vague, OPENING_BODY, "REJECT") == {"advised": False, "why": "rejected; no call",
                                                              "questions": []}


# --- score_analysis: check, finalize, cache, screen, rubric ---------------------------------------------------------

def test_finalize_writes_the_derived_fields_and_keeps_scout_keys(tmp_path):
    root = make_project(tmp_path)
    folder = make_opening(root)
    doc = analysis_doc(scout_extra="kept")
    write_analysis(folder, doc)
    proc, out = run_json(SCORE, "finalize", folder, "--project", root)
    assert proc.returncode == 0, proc.stderr
    assert out["written"] is True and out["summary"]["score"] == 73
    written = json.loads((folder / "analysis.json").read_text(encoding="utf-8"))
    assert written["scout_extra"] == "kept"
    assert written["fit"]["score"] == 73 and written["fit"]["band"] == "good"
    assert written["fit"]["decision"] == "PURSUE" and written["fit"]["reason"].startswith("PURSUE:")
    assert written["gates"]["eligibility"] == "PASS" and written["gates"]["language"] == "PASS"
    assert written["guard"] == "not_checked"
    assert written["posted_at"] == "2026-10-05" and written["deadline"] == "2026-11-30"
    assert written["employer_call_advised"]["advised"] is False
    assert written["salary_benchmark"]["company"] == "Example Co S.A.C."
    assert written["salary_benchmark"]["categories"]["all_employees"]["vs_baseline_pct"] == 8.5


def test_check_validates_without_writing(tmp_path):
    root = make_project(tmp_path)
    folder = make_opening(root)
    doc = analysis_doc()
    write_analysis(folder, doc)
    before = (folder / "analysis.json").read_bytes()
    proc, out = run_json(SCORE, "check", folder, "--project", root)
    assert proc.returncode == 0 and out["written"] is False
    assert (folder / "analysis.json").read_bytes() == before


def test_finalize_overrides_a_scout_decision_the_rules_do_not_support(tmp_path):
    root = make_project(tmp_path)
    folder = make_opening(root, body=OPENING_BODY + " Some on-call weekends.")
    write_analysis(folder, analysis_doc())
    _, out = run_json(SCORE, "finalize", folder, "--project", root)
    written = json.loads((folder / "analysis.json").read_text(encoding="utf-8"))
    assert written["fit"]["decision"] == "REJECT"
    assert written["fit"]["scout_reason"] == "fits the stated skills"
    assert any("decision set by the rules" in w for w in out["warnings"])


def test_a_must_have_without_verified_evidence_becomes_a_hard_gap(tmp_path):
    root = make_project(tmp_path)
    folder = make_opening(root)
    doc = analysis_doc(requirements={**analysis_doc()["requirements"], "must_have": ["SQL", "Kubernetes"],
                                     "priorities": ["Kubernetes"]})
    write_analysis(folder, doc)
    proc, out = run_json(SCORE, "finalize", folder, "--project", root)
    written = json.loads((folder / "analysis.json").read_text(encoding="utf-8"))
    # A tool without evidence is learnable: listed, warned, never a rejection on its own.
    assert "Kubernetes" in written["fit"]["learnable_gaps"] and written["fit"]["hard_gaps"] == []
    assert written["fit"]["decision"] != "REJECT"
    assert any("no verified evidence: Kubernetes" in w for w in out["warnings"])


def test_unverified_achievements_are_not_evidence(tmp_path):
    root = make_project(tmp_path)
    folder = make_opening(root)
    doc = analysis_doc(
        requirements={**analysis_doc()["requirements"], "must_have": ["Power BI"], "priorities": []},
        evidence=[{"requirement": "Power BI", "achievements": ["ACH-009"], "confidence": 0.9, "note": ""}],
    )
    write_analysis(folder, doc)
    _, out = run_json(SCORE, "finalize", folder, "--project", root)
    written = json.loads((folder / "analysis.json").read_text(encoding="utf-8"))
    assert "Power BI" in written["fit"]["learnable_gaps"]
    assert any("ACH-009 is not verified" in w for w in out["warnings"])


def test_problems_block_the_write(tmp_path):
    root = make_project(tmp_path)
    folder = make_opening(root)
    doc = analysis_doc()
    doc["fit"]["dimensions"]["career"] = {"note": "no score given"}
    write_analysis(folder, doc)
    before = (folder / "analysis.json").read_bytes()
    proc, out = run_json(SCORE, "finalize", folder, "--project", root)
    assert proc.returncode == 1
    assert any("career" in p for p in out["problems"])
    assert (folder / "analysis.json").read_bytes() == before


def test_guard_is_taken_from_the_intake_file_and_never_read_as_clean_by_default(tmp_path):
    root = make_project(tmp_path)
    folder = make_opening(root, front=[
        "id: " + OPENING, "company: Example Co", "work_mode: remote_region:latam", "posted_at: 2026-10-05",
        'guard: "posting_guard: clean"',
    ])
    write_analysis(folder, analysis_doc())
    run_json(SCORE, "finalize", folder, "--project", root)
    assert json.loads((folder / "analysis.json").read_text(encoding="utf-8"))["guard"] == "clean"


def test_cache_reuses_a_company_profile_under_thirty_days(tmp_path):
    root = make_project(tmp_path)
    (root / "companies" / "example-co.md").write_text("---\nfetched: 2026-10-10\n---\n# Example Co\n",
                                                      encoding="utf-8")
    fresh = sa.company_cache(root, "Example Co", date(2026, 10, 20))
    assert fresh["reuse"] is True and fresh["age_days"] == 10
    assert sa.company_cache(root, "Example Co", date(2026, 11, 9))["reuse"] is False  # 30 days old
    proc, out = run_json(SCORE, "cache", "--project", root, "--company", "Example Co", "--today", TODAY)
    assert proc.returncode == 0 and out["reuse"] is True


def test_cache_misses_an_undated_or_missing_profile(tmp_path):
    root = make_project(tmp_path)
    assert sa.company_cache(root, "Nobody Inc", date(2026, 10, 20))["reuse"] is False
    (root / "companies" / "example-co.md").write_text("# no front matter\n", encoding="utf-8")
    assert sa.company_cache(root, "Example Co", date(2026, 10, 20))["reuse"] is False


def test_finalize_asks_for_the_company_profile_when_it_is_not_saved(tmp_path):
    root = make_project(tmp_path)
    folder = make_opening(root)
    write_analysis(folder, analysis_doc())
    _, out = run_json(SCORE, "finalize", folder, "--project", root)
    assert any("companies/" in w and "example-co.md" in w for w in out["warnings"])


def test_screen_reports_deal_breakers_and_eligibility_on_plain_text(tmp_path):
    root = make_project(tmp_path)
    text = root / "text.txt"
    text.write_text("Citizens of Peru only. We will not sponsor. Some on-call weekends.\n", encoding="utf-8")
    proc, out = run_json(SCORE, "screen", "--project", root, "--text", text, "--company", "Example Co")
    assert proc.returncode == 0
    assert out["deal_breakers_hit"] == ["on-call weekends"]
    # A PE citizen facing "we will not sponsor" is not blocked: no sponsorship is needed.
    assert out["eligibility"]["gate"] == "PASS"


def test_rubric_is_for_triage_and_never_reads_achievements(tmp_path):
    root = make_project(tmp_path)
    _, out = run_json(SCORE, "rubric", "--project", root)
    assert out["weights"]["technical"] == 30
    assert set(out["dimension_guide"]) == {"technical", "experience", "behavioral", "career"}
    assert "languages" not in out["candidate"] and "achievements" not in json.dumps(out)


# --- triage_merge -------------------------------------------------------------------------------------------------

def triage_setup(tmp_path: Path, deadline_front: bool = True) -> Path:
    front = [
        f"id: {OPENING}", "company: Example Co", "work_mode: remote_region:latam",
        "required_language: {english: B2}", "posted_at: 2026-10-05",
    ] + (["deadline: 2026-11-30"] if deadline_front else [])
    root = make_project(tmp_path, seen={
        "example-co|data-analyst": seen_entry(company="Example Co", opening_id=OPENING, portal="freehire"),
        "gamma|data-analyst": seen_entry(company="Gamma", status="unreachable", fetch_attempts=2,
                                         first_unreachable="2026-10-16T08:00:00Z"),
        "no-file|x": seen_entry(company="No File", opening_id="JOB-20261001-never-saved"),
    })
    make_opening(root, front=front)
    return root


def write_scores(root: Path, rows: list) -> Path:
    path = root / "scores.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def test_triage_merge_dry_run_ranks_with_computed_gates_and_leaves_state_alone(tmp_path):
    root = triage_setup(tmp_path)
    scores = write_scores(root, [
        {"key": "example-co|data-analyst", "status": "scored",
         "scores": {"technical": 80, "experience": 70, "behavioral": 60, "career": 75},
         "strengths": ["SQL"], "gaps": ["Kubernetes"]},
        {"key": "gamma|data-analyst", "status": "unreachable", "fetch_error": "403 after retry"},
    ])
    before = (root / "searches" / "seen.json").read_bytes()
    proc = run(MERGE, "--project", root, "--scores", scores, "--dry-run", "--today", TODAY, "--now", NOW)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["written"] is False
    assert out["ranked"][0]["score"] == 73
    assert out["ranked"][0]["language_gate"] == "PASS"
    assert out["ranked"][0]["gaps"] == ["Kubernetes"]
    assert out["gave_up"][0]["key"] == "gamma|data-analyst"
    assert (root / "searches" / "seen.json").read_bytes() == before


def test_triage_merge_writes_the_ranking_when_not_a_dry_run(tmp_path):
    root = triage_setup(tmp_path)
    scores = write_scores(root, [{"key": "example-co|data-analyst", "status": "scored",
                                  "scores": {"technical": 80, "experience": 70, "behavioral": 60, "career": 75}}])
    proc = run(MERGE, "--project", root, "--scores", scores, "--today", TODAY, "--now", NOW)
    assert proc.returncode == 0, proc.stderr
    entry = load_seen(root)["example-co|data-analyst"]
    assert entry["status"] == "ranked" and entry["rank_score"] == 73


def test_triage_merge_reports_an_opening_that_was_never_saved(tmp_path):
    root = triage_setup(tmp_path)
    scores = write_scores(root, [{"key": "no-file|x", "status": "scored",
                                  "scores": {"technical": 1, "experience": 1, "behavioral": 1, "career": 1}}])
    proc = run(MERGE, "--project", root, "--scores", scores, "--dry-run", "--today", TODAY)
    assert proc.returncode == 1
    assert "opening.md is missing" in proc.stderr


def test_triage_merge_leaves_an_absent_deadline_empty(tmp_path):
    root = triage_setup(tmp_path, deadline_front=False)
    scores = write_scores(root, [{"key": "example-co|data-analyst", "status": "scored",
                                  "scores": {"technical": 80, "experience": 70, "behavioral": 60, "career": 75}}])
    proc = run(MERGE, "--project", root, "--scores", scores, "--dry-run", "--today", TODAY)
    out = json.loads(proc.stdout)
    assert out["ranked"][0]["deadline"] is None


# --- contract checks shared by every script -----------------------------------------------------------------------

@pytest.mark.parametrize("script", [SEEN, SALARY, SCORE, MERGE])
def test_every_script_prints_help_and_exits_zero(script):
    proc = run(script, "--help")
    assert proc.returncode == 0, proc.stderr
    assert "usage" in proc.stdout.lower()


@pytest.mark.parametrize("script", [SEEN, SALARY, SCORE, MERGE])
def test_scripts_make_no_network_calls_and_never_read_contact_data(script):
    source = script.read_text(encoding="utf-8")
    for module in ("urllib", "http.client", "socket", "requests", "subprocess"):
        assert f"import {module}" not in source, (script.name, module)
    assert "contact.yaml" not in source and "application-data.yaml" not in source, script.name


def test_no_market_specific_spelling_tables_remain():
    source = SALARY.read_text(encoding="utf-8")
    assert "SPELLING_VARIANTS" not in source and "STRIP_PATTERNS" not in source
