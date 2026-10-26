"""The failures of the 2026-10-25 end-to-end round of the jobs squad, each replayed through the real scripts.

Every test reproduces one thing the owner saw on the live board (search -> analysis -> write -> review -> auto apply ->
LinkedIn profile apply) and fails if the fix is removed. Fictional people and companies; the two ATS form answers in
tests/fixtures/jobs-forms/ are the public job-board API responses of two real postings (form labels only, no people).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "squads" / "jobs" / "skills"
CONTRACT = SKILLS / "jobs-contract" / "scripts"
CHECK = SKILLS / "submitting-applications" / "scripts" / "check_submission.py"
AGG = SKILLS / "reviewing-applications" / "scripts" / "aggregate_review.py"
DIGEST = SKILLS / "leading-job-search" / "scripts" / "digest_fields.py"
PARSE = SKILLS / "optimizing-profiles" / "scripts" / "parse_profile.py"
DIFF = SKILLS / "optimizing-profiles" / "scripts" / "profile_diff.py"
FORMS = REPO / "tests" / "fixtures" / "jobs-forms"
ID = "JOB-20261023-acme-senior-software-engineer"
ASHBY = "https://jobs.ashbyhq.com/acme/2e9f600f-1344-4bab-b0e1-191a6af5465f"
GREENHOUSE = "https://job-boards.greenhouse.io/acme/jobs/4514946008"
AUTO = ("---\nname: Example\nauto_apply: auto\nauto_apply_since: 2026-10-01\napply_consent: standing\n"
        "daily_apply_cap: 10\ndaily_easy_apply_cap: 5\nreview_before_submit: false\n---\n")


def run(*argv, cwd=None):
    return subprocess.run([sys.executable, *map(str, argv)], capture_output=True, text=True, timeout=120, cwd=cwd)


def opening(root: Path, apply_url: str, url: str = "https://www.linkedin.com/jobs/view/4483184903") -> Path:
    folder = root / "openings" / ID
    (folder / "application").mkdir(parents=True)
    (folder / "opening.md").write_text(f"---\nid: {ID}\ncompany: Acme\nrole: Senior Software Engineer\nurl: {url}\n"
                                       f"apply_url: {apply_url}\nlanguage: en\n---\nPosting text.\n", encoding="utf-8")
    (folder / "status.json").write_text(json.dumps({"id": ID, "status": "in_review", "history": [
        {"date": "2026-10-24T10:00", "status": "in_review", "by": "jobs-writer"}]}), encoding="utf-8")
    (root / "profile.md").write_text(AUTO, encoding="utf-8")
    return folder


# --- 1. the applier's gate needs no skill the applier does not hold ------------------------------------------------

def test_the_submit_gate_runs_on_a_profile_that_holds_only_the_appliers_skills(tmp_path):
    """jobs-applier holds submitting-applications and jobs-contract only; the gate crashed on analyzing-jobs."""
    skills = tmp_path / "skills" / "squad-jobs"
    for name in ("submitting-applications", "jobs-contract"):
        shutil.copytree(SKILLS / name, skills / name, ignore=shutil.ignore_patterns("__pycache__"))
    project = tmp_path / "project"
    app = opening(project, ASHBY) / "application"
    (app.parent / "review-1.json").write_text(json.dumps({"verdict": "APPROVED"}))
    (app.parent / "status.json").write_text(json.dumps({"history": [
        {"date": "2026-10-24T10:00", "status": "ready", "by": "jobs-reviewer"}], "status": "ready"}))
    (app.parent / "analysis.json").write_text(json.dumps({
        "id": ID, "gates": {"eligibility": "PASS", "language": "PASS", "location": "PASS", "seniority": "FAIL"},
        "fit": {"score": 90, "decision": "PURSUE"}}))
    proc = run(skills / "submitting-applications" / "scripts" / "check_submission.py", app / "submission.json",
               "--gate", "--method", "no_login_form")
    assert "Traceback" not in proc.stderr and "FileNotFoundError" not in proc.stderr, proc.stderr
    # the gate list still decides: a failed seniority gate closes it, read from jobs-contract
    assert proc.returncode == 1 and "gate FAIL: seniority" in proc.stderr, proc.stderr


def test_the_applier_does_not_install_the_scouts_analysis_skill():
    import yaml
    squad = yaml.safe_load((REPO / "squads" / "jobs" / "squad.yaml").read_text())
    assert squad["bots"]["jobs-applier"]["skills"]["squad"] == ["submitting-applications", "jobs-contract"]


# --- 3. an ATS name is a form class the gate understands ----------------------------------------------------------

def approved(folder: Path):
    (folder / "review-1.json").write_text(json.dumps({"verdict": "APPROVED"}))
    (folder / "status.json").write_text(json.dumps({"history": [
        {"date": "2026-10-24T10:00", "status": "ready", "by": "jobs-reviewer"}], "status": "ready"}))
    (folder / "analysis.json").write_text(json.dumps({
        "id": ID, "gates": {"eligibility": "PASS", "language": "PASS", "location": "PASS", "seniority": "PASS"},
        "fit": {"score": 90, "decision": "PURSUE"}}))


@pytest.mark.parametrize("method", ["ashby", "Ashby"])
def test_method_ashby_opens_the_gate_on_an_ashby_link(tmp_path, method):
    folder = opening(tmp_path, ASHBY)
    approved(folder)
    proc = run(CHECK, folder / "application" / "submission.json", "--gate", "--method", method)
    assert proc.returncode == 0 and "gate: open" in proc.stdout, proc.stderr
    assert json.loads((folder / "application" / "gate.json").read_text())["method"] == "no_login_form"


def test_an_ats_name_that_is_not_the_links_ats_closes_the_gate(tmp_path):
    folder = opening(tmp_path, ASHBY)
    approved(folder)
    proc = run(CHECK, folder / "application" / "submission.json", "--gate", "--method", "greenhouse")
    assert proc.returncode == 1 and "names an ATS the apply link is not on" in proc.stderr, proc.stderr


def test_an_unknown_method_names_the_ats_ids_it_accepts(tmp_path):
    folder = opening(tmp_path, ASHBY)
    approved(folder)
    proc = run(CHECK, folder / "application" / "submission.json", "--gate", "--method", "webform")
    assert proc.returncode == 1 and "ashby" in proc.stderr and "greenhouse" in proc.stderr, proc.stderr


# --- review: helpers ------------------------------------------------------------------------------------------------

def blocks(**over):
    base = {
        "truthfulness": {"verdict": "PASS", "grounding": {"sources": ["achievements.yaml", "profile.md"]},
                         "findings": [], "company_claims": []},
        "ats": {"verdict": "PASS", "keyword_coverage": 0.9, "missing": [], "defects": []},
        "recruiter": {"verdict": "PASS", "seconds_to_understand": 20, "would_open_evidence": True, "blockers": [],
                      "market": {"checked": ["photo"], "violations": []}},
        "hiring_manager": {"verdict": "PASS", "can_do_the_job": True, "concerns": [], "interview_questions": [],
                           "stretches": []},
        "writing": {"verdict": "PASS", "findings": [],
                    "language": {"document_language": "en", "opening_language": "en"}},
    }
    base.update(over)
    return base


def review(folder: Path, lens_blocks: dict, *extra, round_no=2):
    paths = []
    for lens, block in lens_blocks.items():
        path = folder.parent / f"{lens}.json"
        path.write_text(json.dumps(block), encoding="utf-8")
        paths.append(path)
    app = folder / "application"
    if not (app / "render_report.json").exists():
        (app / "render_report.json").write_text(json.dumps({"defects": [], "keyword_coverage": 0.9,
                                                            "missing_keywords": []}))
    return run(AGG, "--lenses", *paths, "--round", round_no, "--id", ID, "--application-dir", app,
               "--opening", folder / "opening.md", "--apply", *extra)


ANSWERS = """# Form answers: Acme

## 3. "What is the most complex backend feature you have deployed?"

[FIELD]
An order assistant inside the order management system I built, used by repair-shop staff every day.
[/FIELD]

NOTE TO SELF (not for pasting): the interviewer will ask the stack. True answer: the AI workflow layer used Python,
FastAPI and LangGraph.
"""


# --- 7. a correction inside a note no employer reads never costs a round --------------------------------------------

def test_a_note_to_self_correction_is_applied_and_the_round_is_approved(tmp_path):
    """Factored review-8: one truthfulness correction inside a NOTE TO SELF of answers.md made round 8 NOT_APPROVED."""
    folder = opening(tmp_path, GREENHOUSE)
    (folder / "application" / "answers.md").write_text(ANSWERS, encoding="utf-8")
    old = "the AI workflow layer used Python,\nFastAPI and LangGraph."
    new = "the assistants ran on Azure AI Foundry (ACH-018)."
    fix = {"type": "content", "mode": "replace", "file": "answers.md", "old": old, "new": new}
    lens = blocks(truthfulness={**blocks()["truthfulness"], "verdict": "FAIL", "findings": [{
        "kind": "draft", "check": "tools", "location": "answers.md, field 3 NOTE TO SELF", "text": old,
        "problem": "the record ties Azure AI Foundry to this system", "correction": fix}]})
    proc = review(folder, lens, "--json", round_no=8)
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["verdict"] == "APPROVED" and doc["corrections"] == [], doc
    assert [a.get("internal") for a in doc["applied"]] == [True]
    proc = review(folder, lens, "--summary", "ok", "--out", folder / "review-8.json", round_no=8)
    assert proc.returncode == 0, proc.stderr
    assert new in (folder / "application" / "answers.md").read_text()


def test_the_same_correction_inside_a_field_still_blocks(tmp_path):
    folder = opening(tmp_path, GREENHOUSE)
    (folder / "application" / "answers.md").write_text(ANSWERS, encoding="utf-8")
    old = "used by repair-shop staff every day"
    fix = {"type": "content", "mode": "replace", "file": "answers.md", "old": old, "new": "used by repair shops"}
    lens = blocks(truthfulness={**blocks()["truthfulness"], "verdict": "FAIL", "findings": [{
        "kind": "draft", "check": "numbers", "location": "answers.md, field 3 NOTE TO SELF", "text": old,
        "problem": "no record of daily use", "correction": fix}]})
    doc = json.loads(review(folder, lens, "--json", round_no=8).stdout)
    assert doc["verdict"] == "NOT_APPROVED" and len(doc["corrections"]) == 1, doc


# --- 2, 9, 10. the reviewed posting is the link the applier gets ----------------------------------------------------

def test_an_aggregator_apply_url_is_never_approved_without_the_reviewed_posting(tmp_path):
    """Canals: apply_url was an aggregator page (echojobs.io) while review-4 verified the Ashby requisition."""
    folder = opening(tmp_path, "https://echojobs.io/job/acme-senior-software-engineer-za5hv")
    proc = review(folder, blocks())
    assert proc.returncode == 1 and "posting_url" in proc.stderr and "--posting-url" in proc.stderr, proc.stderr


def test_the_reviewed_posting_becomes_apply_url_and_the_digest_hands_it_to_the_applier(tmp_path):
    """Mineo: apply_url was another city's requisition; the digest card gave the applier that link."""
    other_city = "https://www.careers-page.com/acme/job/L4W9WY75"
    reviewed = "https://www.careers-page.com/acme/job/L3VYV97V"
    folder = opening(tmp_path, other_city, url=other_city)
    proc = review(folder, blocks(), "--posting-url", reviewed, "--summary", "ok", "--out", folder / "review-c3.json")
    assert proc.returncode == 0, proc.stderr
    assert f"apply_url: {reviewed}" in (folder / "opening.md").read_text()
    assert json.loads((folder / "review-c3.json").read_text())["apply_url"] == reviewed
    digest = run(DIGEST, tmp_path)
    assert f"apply:   {reviewed}" in digest.stdout, digest.stdout
    # the next round may cite the posting the reviewer located: it is not a URL the opening gave
    claim = {"claim": "Acme sells parts", "location": "cover_letter.md", "source_url": reviewed,
             "source_located_by_reviewer": True, "source_excerpt": "Acme sells aviation parts to repair shops across "
             "the Americas.", "reason": "page states it", "verdict": "kept"}
    lens = blocks(truthfulness={**blocks()["truthfulness"], "company_claims": [claim]})
    assert review(folder, lens, round_no=4).returncode == 0


def test_a_posting_url_that_is_not_an_employer_ats_is_refused(tmp_path):
    folder = opening(tmp_path, "https://echojobs.io/job/x")
    proc = review(folder, blocks(), "--posting-url", "https://echojobs.io/job/x")
    assert proc.returncode == 1 and "only an employer ATS posting" in proc.stderr, proc.stderr


# --- 11. the real form's required questions are answered before review approves ------------------------------------

def test_the_ashby_form_questions_are_read_from_the_public_api_answer():
    proc = run(CONTRACT / "form_questions.py", "--from-file", FORMS / "ashby_canals.json", "--ats", "ashby", "--json")
    doc = json.loads(proc.stdout)
    assert proc.returncode == 0 and len(doc["required_text"]) == 5, doc
    assert any("first 90 days" in q for q in doc["required_text"])
    kinds = {q["label"]: q["kind"] for q in doc["questions"]}
    assert kinds["Resume"] == "file" and kinds["Email"] == "contact"


def test_the_greenhouse_form_questions_are_read_from_the_public_api_answer():
    proc = run(CONTRACT / "form_questions.py", "--from-file", FORMS / "greenhouse_factored.json", "--ats",
               "greenhouse", "--json")
    doc = json.loads(proc.stdout)
    assert doc["required_text"] == ["In 1-2 sentences, what is the most complex backend GenAI feature you have "
                                    "deployed to actual end-users?"]
    assert {q["kind"] for q in doc["questions"] if "level" in q["label"]} == {"choice"}


def test_a_host_without_a_form_api_says_so_instead_of_an_empty_form():
    proc = run(CONTRACT / "form_questions.py", "https://echojobs.io/job/x")
    assert proc.returncode == 1 and "list the questions from the form page" in proc.stderr


def test_a_kit_missing_required_form_answers_is_not_approved(tmp_path):
    """Canals: four review rounds passed, then the Ashby form showed four required questions answers.md lacked."""
    folder = opening(tmp_path, ASHBY)
    app = folder / "application"
    (app / "answers.md").write_text(ANSWERS, encoding="utf-8")
    assert run(CONTRACT / "form_questions.py", "--from-file", FORMS / "ashby_canals.json", "--ats", "ashby",
               "--out", app / "form_questions.json").returncode == 0
    doc = json.loads(review(folder, blocks(), "--json").stdout)
    assert doc["verdict"] == "NOT_APPROVED", doc
    assert "first 90 days" in doc["corrections"][0]["instructions"]
    questions = json.loads((app / "form_questions.json").read_text())["required_text"]
    (app / "answers.md").write_text(ANSWERS + "".join(f"\n## {i}. {q}\n\n[FIELD]\nA true answer.\n[/FIELD]\n"
                                                      for i, q in enumerate(questions, 10)), encoding="utf-8")
    assert json.loads(review(folder, blocks(), "--json").stdout)["verdict"] == "APPROVED"


# --- 12. salary and notice period come from stored values, not a question mid-submit -------------------------------

def data(tmp_path: Path, extra: str = "") -> Path:
    (tmp_path / "application-data.yaml").write_text(
        "salary_expectation:\n  - {currency: USD, amount: 3500, period: month}\n"
        "  - {currency: COP, amount: 10000000, period: month}\nstart_availability: \"1 week\"\n" + extra,
        encoding="utf-8")
    return tmp_path


def answer(project, *args):
    return run(CONTRACT / "form_answer.py", *args, "--project", project, "--json")


def test_a_notice_dropdown_without_a_one_week_option_gets_the_next_longer_one(tmp_path):
    """Mineo: the dropdown offered Immediately / 10 days / 20 days and the stored answer was 'one week'."""
    proc = answer(data(tmp_path), "notice", "--options", "Immediately|10 days|20 days|1 month")
    assert proc.returncode == 0 and json.loads(proc.stdout)["answer"] == "10 days", proc.stderr


def test_a_salary_field_without_a_posted_range_needs_one_stored_value_then_never_asks(tmp_path):
    """Mineo: 'Expected Salary' with no posted range; the data held only floors, so the owner was asked mid-submit."""
    project = data(tmp_path)
    proc = answer(project, "salary", "--period", "month")
    assert proc.returncode == 1 and "salary_answer" in proc.stderr
    data(tmp_path, "salary_answer: {amount: 4500, currency: USD, period: month}\n")
    assert json.loads(answer(project, "salary", "--period", "year").stdout)["amount"] == 54000
    assert json.loads(answer(project, "salary", "--range", "3000-3800 USD").stdout)["amount"] == 3500  # floor
    assert json.loads(answer(project, "salary", "--currency", "COP").stdout)["amount"] == 10000000


def test_a_prose_rule_in_application_data_is_flagged(tmp_path):
    project = tmp_path
    data(project, "salary_answer_rule: \"above the floor, a reasonable average\"\n")
    proc = run(CONTRACT / "validate_profile.py", "--project", project, "--json")
    assert "salary_answer_rule" in proc.stdout and "cannot be typed" in proc.stdout, proc.stdout


# --- 8. one key format, the project slug -----------------------------------------------------------------------------

def test_a_card_key_from_the_project_path_is_the_slug_key(tmp_path):
    by_path = run(CONTRACT / "card_key.py", "application", "/Users/someone/Documents/job-search", ID, "review-c6")
    by_slug = run(CONTRACT / "card_key.py", "application", "job-search", ID, "review-c6")
    assert by_path.stdout == by_slug.stdout == f"jobs:application:job-search:{ID}:review-c6\n"
    assert run(CONTRACT / "card_key.py", "application", "job-search", ID, "reviewed").returncode == 2


def test_no_skill_tells_a_bot_to_build_an_application_key_by_hand():
    for skill in ("writing-applications", "reviewing-applications"):
        text = (SKILLS / skill / "SKILL.md").read_text()
        assert "card_key.py" in text, skill


# --- 13. a one-role company's capture parses as LinkedIn renders it -------------------------------------------------

CAPTURE = {
    "url": "https://www.linkedin.com/in/ana-example/", "name": "Ana Example", "headline": "Engineer",
    "about": "About text.", "profile_languages": ["English"],
    "experience": {"found": True, "groups": [
        {"company": "", "roles": [], "all": [
            "Freelance Developer", "Independent · Self-employed", "Jan 2024 - Dec 2024 · 1 yr",
            "• Built and deployed a WhatsApp assistant for a client.", "Railway, Cloudflare and +1 skill"]},
        {"company": "Acme", "all": ["Acme", "Full-time · 2 yrs", "Remote"], "roles": [
            {"lines": ["Technical Lead", "Jun 2024 - Present · 1 yr", "Remote", "• Lead a squad.",
                       "Skills: Team leadership, VTEX, +3 skills"]}]},
    ]},
    "education": {"found": True, "items": []}, "skills": {"count": 2, "items": ["Railway", "Cloudflare"]},
}


def test_a_one_role_companys_bare_skills_line_is_skills_not_description(tmp_path):
    (tmp_path / "capture.json").write_text(json.dumps(CAPTURE))
    assert run(PARSE, tmp_path / "capture.json", "--output", tmp_path / "current.json").returncode == 0
    rows = {r["title"]: r for r in json.loads((tmp_path / "current.json").read_text())["experience"]}
    free = rows["Freelance Developer"]
    assert free["company"] == "Independent" and free["skills"] == ["Railway", "Cloudflare"]
    assert "skill" not in free["description"] and free["skills_hidden"] == 1


def test_verify_reads_role_skills_from_the_form_boxes_and_never_calls_a_partial_line_missing(tmp_path):
    """t_22b361ae: role_skills failed as 'field not on the profile' though the page was right."""
    (tmp_path / "capture.json").write_text(json.dumps(CAPTURE))
    approved = {"fields": [{"field": "role_skills:Independent:Freelance Developer",
                            "after": ["WhatsApp", "Railway", "Cloudflare"]}]}
    (tmp_path / "approved.json").write_text(json.dumps(approved))
    run(PARSE, tmp_path / "capture.json", "--output", tmp_path / "current.json")
    partial = run(DIFF, "verify", tmp_path / "approved.json", tmp_path / "current.json")
    assert partial.returncode == 1 and "only part of this role's skills" in partial.stdout + partial.stderr
    assert "not on the profile" not in partial.stdout + partial.stderr
    (tmp_path / "boxes.json").write_text(json.dumps({"Independent:Freelance Developer":
                                                     ["Railway", "Cloudflare", "WhatsApp"]}))
    run(PARSE, tmp_path / "capture.json", "--output", tmp_path / "current.json", "--role-skills", tmp_path / "boxes.json")
    full = run(DIFF, "verify", tmp_path / "approved.json", tmp_path / "current.json")
    assert full.returncode == 0, full.stdout + full.stderr
