"""validate_profile.py as the manager runs it: the real script on a fictional profile folder, --json output.

Each test changes one line of a valid fixture and checks the finding the validator gives for that line.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
VALIDATE = REPO / "squads" / "jobs" / "skills" / "jobs-contract" / "scripts" / "validate_profile.py"
SYSTEM_PY = "/usr/bin/python3"  # the built-in YAML reader runs here (no PyYAML); the .venv run uses PyYAML
INTERPRETERS = [sys.executable] + ([SYSTEM_PY] if Path(SYSTEM_PY).is_file() else [])
TODAY = "2026-10-21"

PROFILE = """---
updated: 2026-10-01
search: active
occupation: "Data analyst, business reporting"
target_roles: ["Data analyst", "BI analyst"]
seniority: mid-level
years_experience: {total: 4.7, in_role: 2.3}
work_mode: [remote_region, hybrid]
key_skills: [SQL, Python]
search_keywords: {en: ["data analyst"], es: ["analista de datos"]}
application_languages: [es, en]
user_language: es
timezone: America/Lima
auto_apply: try
apply_consent: per_opening
review_before_submit: false
candidate: {stage: mid, situation: employed, include_age_in_cv: false, photo_in_cv: false}
market: {country: PE, cv_page_limit: 2}
eligibility:
  - {country: PE, status: citizen}
  - {country: US, status: needs_sponsorship, notes: ""}
languages_policy: {flag_gap_steps: 1, discard_gap_steps: 2}
scoring:
  weights: {technical: 30, experience: 25, behavioral: 15, career: 30}
  bands: {strong: 75, good: 60, moderate: 45, weak: 30}
deal_breakers: ["on-call weekends"]
apply_threshold: 70
follow_up_days: 10
stale_days: 60
---
Notes for the fictional profile.
"""

ACHIEVEMENTS = """experiences:
  - {id: EXP-001, title: "Data analyst", company: "Example Co", from: 2022-03, to: 2024-06}
  - {id: EXP-002, title: "Tech lead, data platform", company: "Example Labs", from: 2024-07, to: current}
achievements:
  - id: ACH-001
    experience: EXP-002
    proficiency: led
    en: "Led the move of the weekly report to a SQL pipeline."
    es: "Lideré el paso del reporte semanal a un flujo SQL."
    source: "documents/cv/cv-2026.pdf"
    verified: true
skills:
  - {name: SQL, proficiency: did, years: 4, achievements: [ACH-001]}
education:
  - {id: EDU-001, degree: "Statistics", institution: "Example U", year: 2021, verified: true}
certifications: []
languages:
  - {language: spanish, level: C2, verified: true}
  - {language: english, level: B2, verified: true}
public_evidence: []
star_stories: []
"""

CONTACT = """name: "Ana Example"
email: "ana@example.com"
phone: "+51 900 000 000"
location: "Lima, Peru"
links: ["https://example.com/ana"]
"""

APPLICATION = """work_authorization:
  - {country: PE, authorized: true, needs_sponsorship: false}
  - {country: US, authorized: false, needs_sponsorship: true}
salary_expectation: [{currency: PEN, amount: 7000, period: month}]
start_availability: "2 weeks"
willing_to_relocate: false
voluntary_questions: "prefer not to answer"
authorize_consents: true
saved_answers: []
"""


def edit(text: str, old: str, new: str) -> str:
    assert old in text, f"fixture has no {old!r}: the test would not change anything"
    return text.replace(old, new)


def write_project(tmp: Path, profile: str = PROFILE, achievements: str = ACHIEVEMENTS, contact: str = CONTACT,
                  application: str | None = APPLICATION) -> Path:
    folder = tmp / "ana"
    folder.mkdir(exist_ok=True)
    files = {"profile.md": profile, "achievements.yaml": achievements, "contact.yaml": contact,
             "application-data.yaml": application}
    for name, text in files.items():
        path = folder / name
        if text is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(text, encoding="utf-8")
    return folder


def check(folder: Path, interp: str = sys.executable):
    p = subprocess.run([interp, "-I", str(VALIDATE), "--project", str(folder), "--today", TODAY, "--json"],
                       capture_output=True, text=True, timeout=120)
    data = json.loads(p.stdout) if p.stdout.strip().startswith("{") else None
    return p.returncode, data, p


def findings(folder: Path, interp: str = sys.executable):
    code, data, p = check(folder, interp)
    assert data is not None, (p.stdout, p.stderr)
    return [(f["file"], f["key"], f["message"]) for f in data["findings"]]


def keyed(found, file, key):
    return [msg for f, k, msg in found if f == file and k == key]


@pytest.mark.parametrize("interp", INTERPRETERS)
def test_the_fictional_profile_passes_and_years_come_from_the_dates(tmp_path, interp):
    code, data, p = check(write_project(tmp_path), interp)
    assert code == 0, p.stdout + p.stderr
    assert data["ok"] is True
    assert data["computed_years"]["total"] == 4.7 and data["computed_years"]["by_title"]["data analyst"] == 2.3


def test_a_missing_file_and_a_usage_error_have_their_own_exit_codes(tmp_path):
    folder = write_project(tmp_path, application=None)
    code, data, _ = check(folder)
    assert code == 1 and ("application-data.yaml", "", "file is missing") in findings(folder)
    p = subprocess.run([sys.executable, "-I", str(VALIDATE), "--project", str(tmp_path / "nope")],
                       capture_output=True, text=True)
    assert p.returncode == 2


def test_a_tech_lead_for_four_months_cannot_claim_four_years_in_role(tmp_path):
    # in_role is time in the current role: a tech lead of four months cannot declare four years in role.
    dates = edit(ACHIEVEMENTS, "from: 2024-07, to: current", "from: 2026-07, to: current")
    folder = write_project(tmp_path, profile=edit(PROFILE, "years_experience: {total: 4.7, in_role: 2.3}",
                                                  "years_experience: {total: 2.7, in_role: 4}"),
                           achievements=dates)
    found = findings(folder)
    msgs = keyed(found, "profile.md", "years_experience.in_role")
    assert msgs and "is 4" in msgs[0] and "0.3" in msgs[0], found
    fixed = write_project(tmp_path, profile=edit(PROFILE, "years_experience: {total: 4.7, in_role: 2.3}",
                                                 "years_experience: {total: 2.7, in_role: 0.3}"),
                          achievements=dates)
    assert keyed(findings(fixed), "profile.md", "years_experience.in_role") == []


def test_a_total_that_the_dates_do_not_support_is_reported(tmp_path):
    folder = write_project(tmp_path, profile=edit(PROFILE, "total: 4.7", "total: 8"))
    assert keyed(findings(folder), "profile.md", "years_experience.total")


def test_hybrid_in_deal_breakers_of_a_remote_search_is_reported(tmp_path):
    # A work mode the user accepts belongs in work_mode, not in deal_breakers.
    profile = edit(PROFILE, "work_mode: [remote_region, hybrid]", "work_mode: [remote_global]")
    profile = edit(profile, 'deal_breakers: ["on-call weekends"]', 'deal_breakers: ["on-call weekends", "hybrid"]')
    msgs = keyed(findings(write_project(tmp_path, profile=profile)), "profile.md", "deal_breakers")
    assert msgs and "work_mode" in msgs[0]


def test_a_deal_breaker_about_duties_is_not_a_work_mode_finding(tmp_path):
    assert keyed(findings(write_project(tmp_path)), "profile.md", "deal_breakers") == []


@pytest.mark.parametrize("interp", INTERPRETERS)
def test_an_unquoted_NO_country_is_reported_as_false(tmp_path, interp):
    # `country: NO` (Norway) reads as false in YAML 1.1; the code is valid only when quoted.
    unquoted = edit(PROFILE, "- {country: US, status: needs_sponsorship, notes: \"\"}",
                    "- {country: NO, status: resident}")
    msgs = keyed(findings(write_project(tmp_path, profile=unquoted), interp), "profile.md", "eligibility[1].country")
    assert msgs and "reads as false" in msgs[0], msgs
    quoted = edit(PROFILE, "- {country: US, status: needs_sponsorship, notes: \"\"}",
                  "- {country: \"NO\", status: resident}")
    assert keyed(findings(write_project(tmp_path, profile=quoted), interp), "profile.md",
                 "eligibility[1].country") == []


def test_weights_must_sum_to_one_hundred(tmp_path):
    folder = write_project(tmp_path, profile=edit(PROFILE, "technical: 30", "technical: 29"))
    assert keyed(findings(folder), "profile.md", "scoring.weights")


def test_references_to_unknown_ids_are_reported(tmp_path):
    folder = write_project(tmp_path, achievements=edit(ACHIEVEMENTS, "experience: EXP-002", "experience: EXP-009"))
    assert keyed(findings(folder), "achievements.yaml", "achievements[0].experience")
    folder = write_project(tmp_path, achievements=edit(ACHIEVEMENTS, "achievements: [ACH-001]",
                                                       "achievements: [ACH-404]"))
    assert keyed(findings(folder), "achievements.yaml", "skills[0].achievements")


def test_required_language_and_timezone_keys_are_checked(tmp_path):
    no_lang = write_project(tmp_path, profile=edit(PROFILE, "user_language: es\n", ""))
    assert keyed(findings(no_lang), "profile.md", "user_language")
    bad_zone = write_project(tmp_path, profile=edit(PROFILE, "timezone: America/Lima", "timezone: America/Lim"))
    assert keyed(findings(bad_zone), "profile.md", "timezone")


def test_auto_apply_ask_needs_the_screenshot_review(tmp_path):
    profile = edit(PROFILE, "auto_apply: try", "auto_apply: ask")
    assert keyed(findings(write_project(tmp_path, profile=profile)), "profile.md", "review_before_submit")
    ok = edit(profile, "review_before_submit: false", "review_before_submit: true")
    assert keyed(findings(write_project(tmp_path, profile=ok)), "profile.md", "review_before_submit") == []


def test_the_apply_consent_field_is_required_and_checked(tmp_path):
    missing = write_project(tmp_path, profile=edit(PROFILE, "apply_consent: per_opening\n", ""))
    assert keyed(findings(missing), "profile.md", "apply_consent")
    wrong = write_project(tmp_path, profile=edit(PROFILE, "apply_consent: per_opening", "apply_consent: sometimes"))
    assert keyed(findings(wrong), "profile.md", "apply_consent")


def test_an_impossible_date_is_reported(tmp_path):
    folder = write_project(tmp_path, achievements=edit(ACHIEVEMENTS, "from: 2022-03", "from: 2022-13"))
    assert keyed(findings(folder), "achievements.yaml", "experiences[0].from")


def test_a_contact_value_is_never_printed(tmp_path):
    folder = write_project(tmp_path, contact=edit(CONTACT, 'email: "ana@example.com"', 'email: "ana at example"'))
    code, data, p = check(folder)
    assert keyed(findings(folder), "contact.yaml", "email"), code
    assert "ana at example" not in p.stdout and "ana at example" not in p.stderr


def test_a_phone_left_out_of_the_chat_does_not_block_the_profile(tmp_path):
    # Real onboarding: the user would not type the phone in the chat and left `phone: ""` to fill in later. The
    # manager then refused to call the profile saved and the search never started. An empty phone is pending, not
    # an error; a phone that is present but not text still is.
    folder = write_project(tmp_path, contact=edit(CONTACT, 'phone: "+51 900 000 000"', 'phone: ""'))
    code, data, p = check(folder)
    assert code == 0, p.stdout
    (tmp_path / "b").mkdir()
    broken = write_project(tmp_path / "b", contact=edit(CONTACT, 'phone: "+51 900 000 000"', "phone: true"))
    assert keyed(findings(broken), "contact.yaml", "phone")



def test_plans_to_relocate_must_be_yes_or_no(tmp_path):
    # The residence gate reads plans_to_relocate as a boolean; a typed "maybe" would silently mean no.
    folder = write_project(tmp_path, profile=edit(PROFILE, "search: active", "search: active\nplans_to_relocate: maybe"))
    assert keyed(findings(folder), "profile.md", "plans_to_relocate")


def test_check_times_the_search_gate_cannot_read_are_caught_at_onboarding(tmp_path):
    # The cron gate stops on a bad search_times; the profile check must catch it first, while the user is there.
    for sub in ("ok", "a", "b", "c"):
        (tmp_path / sub).mkdir()
    ok = write_project(tmp_path / "ok", profile=edit(PROFILE, "search: active", 'search: active\nsearch_times: ["09:00", "15:00"]'))
    assert not keyed(findings(ok), "profile.md", "search_times")
    for sub, bad in zip("abc", ('["noon"]', '["09:00", "09:30"]', '["25:00"]')):
        folder = write_project(tmp_path / sub,
                               profile=edit(PROFILE, "search: active", f"search: active\nsearch_times: {bad}"))
        assert keyed(findings(folder), "profile.md", "search_times"), bad
