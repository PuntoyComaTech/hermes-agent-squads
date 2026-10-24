"""Confidential work and readable length: the two leaks a real search hit.

The scenario: a technical lead employed at an agency searches in parallel. Their current employer's clients (global
retail brands), an internal order-management project and the size of their team must never reach a CV, a letter, a
form answer, a recruiter message or the LinkedIn copy. And every outward text must be readable by a person in seconds,
not only by an ATS: a 75-word summary, ten bullets under one role, a 360-word letter and a 2,000-character About were
all produced and all have to be refused.

Every check runs the real scripts with fictional names (Ana Example, Acme Agency, the brands Northwind and Contoso).
"""
from __future__ import annotations

import json
import subprocess
import sys

from test_jobs_documents import LETTER, cv_content, codes, no_engine, render, render_cv_case, write  # noqa: F401
from test_jobs_documents import PROFILE as DOC_PROFILE
from test_jobs_linkedin import check_copy, good_copy
from test_jobs_review import AGG, LENSES, passing_blocks
from test_jobs_submit_gate import gate, make_opening

SECRET = ["Northwind", "Contoso", "Project Falcon", "segundo trabajo"]
PROFILE = DOC_PROFILE.replace("writing_style:", f"confidential_terms: {json.dumps(SECRET)}\nwriting_style:")


def leak_cv():
    content = cv_content()
    content["experience"][0]["bullets"][0]["text"] = ("Led delivery of the Northwind and Contoso storefronts with Python and "
                                                     "Power BI, cutting run time from six hours to twenty minutes.")
    return content


# --- CV and letter -------------------------------------------------------------------------------------------------

def test_a_cv_naming_a_confidential_client_is_refused(tmp_path, no_engine):
    code, report, _ = render_cv_case(tmp_path, leak_cv(), profile=PROFILE)
    assert code == 1
    msgs = [d["message"] for d in report["defects"] if d["code"] == "confidential_term"]
    assert any("Northwind" in m for m in msgs) and any("Contoso" in m for m in msgs)
    # the same CV described by sector passes the privacy check
    clean = leak_cv()
    clean["experience"][0]["bullets"][0]["text"] = ("Led delivery of storefronts for global retail brands with Python "
                                                   "and Power BI, cutting run time from six hours to twenty minutes.")
    _, report, _ = render_cv_case(tmp_path / "clean", clean, profile=PROFILE)
    assert "confidential_term" not in codes(report)


def test_matching_is_whole_word_and_accent_insensitive(tmp_path, no_engine):
    content = cv_content()
    content["summary"]["text"] = "Data analyst with reporting automation; open to a SEGUNDO TRABAJO in Lima."
    _, report, _ = render_cv_case(tmp_path, content, profile=PROFILE)
    assert "confidential_term" in codes(report)
    content["summary"]["text"] = "Data analyst with reporting automation for Northwindows clients in Lima."
    _, report, _ = render_cv_case(tmp_path / "b", content, profile=PROFILE)
    assert "confidential_term" not in codes(report)  # a longer word is not the term


def test_a_profile_without_confidential_terms_changes_nothing(tmp_path, no_engine):
    _, report, _ = render_cv_case(tmp_path, leak_cv())
    assert "confidential_term" not in codes(report)


def test_a_letter_naming_an_internal_project_is_refused(tmp_path, no_engine):
    letter = write(tmp_path / "letter.md", LETTER.replace("I have automated that report already.",
                                                          "I automated that report inside Project Falcon."))
    out = tmp_path / "out"
    render.main(["--kind", "letter", "--content", str(letter), "--output", str(out), "--template", "compact",
                 "--profile", str(write(tmp_path / "profile.md", PROFILE)), "--json"])
    report = json.loads((out / "render_report_letter.json").read_text(encoding="utf-8"))
    assert any(d["code"] == "confidential_term" and "Project Falcon" in d["message"] for d in report["defects"])


# --- readable length -----------------------------------------------------------------------------------------------

def test_a_summary_over_fifty_words_is_too_long(tmp_path, no_engine):
    content = cv_content()
    content["summary"]["text"] = " ".join(["Data analyst automating weekly reporting in Python and Power BI."] * 6)
    _, report, _ = render_cv_case(tmp_path, content)
    assert any(d["code"] == "too_long" and "summary" in d["message"] for d in report["defects"])


def test_ten_bullets_under_the_latest_role_is_too_long(tmp_path, no_engine):
    content = cv_content()
    bullet = content["experience"][0]["bullets"][0]
    content["experience"][0]["bullets"] = [dict(bullet) for _ in range(10)]
    _, report, _ = render_cv_case(tmp_path, content)
    assert any(d["code"] == "too_long" and "10 bullets" in d["message"] for d in report["defects"])
    content["experience"][0]["bullets"] = [dict(bullet) for _ in range(5)]
    content["experience"][1]["bullets"] = [dict(content["experience"][1]["bullets"][0]) for _ in range(4)]
    _, report, _ = render_cv_case(tmp_path / "b", content)
    too_long = [d["message"] for d in report["defects"] if d["code"] == "too_long"]
    assert len(too_long) == 1 and "'Analyst'" in too_long[0]  # 5 in the latest role is fine, 4 in an older one is not


def test_the_shipped_fixture_cv_is_not_too_long(tmp_path, no_engine):
    _, report, _ = render_cv_case(tmp_path)
    assert "too_long" not in codes(report)


def test_a_letter_over_250_words_is_a_defect_not_a_warning(tmp_path, no_engine):
    padding = " ".join(["I would move the monthly close onto the SQL views I built for finance."] * 20)
    letter = write(tmp_path / "letter.md", LETTER.replace("Motivation:", padding + " <!-- achievements: ACH-008 -->\n\nMotivation:"))
    out = tmp_path / "out"
    code = render.main(["--kind", "letter", "--content", str(letter), "--output", str(out), "--template", "compact",
                        "--json"])
    report = json.loads((out / "render_report_letter.json").read_text(encoding="utf-8"))
    assert code == 1 and "too_long" in codes(report)


# --- LinkedIn copy -------------------------------------------------------------------------------------------------

def linkedin_project(tmp_path):
    copy = good_copy()
    check_copy(tmp_path, copy)  # creates the project folder
    profile = tmp_path / "ana" / "profile.md"
    profile.write_text(profile.read_text().replace("---\n", f"---\nconfidential_terms: {json.dumps(SECRET)}\n", 1))
    return copy


def test_linkedin_copy_naming_a_client_is_refused(tmp_path):
    copy = linkedin_project(tmp_path)
    copy["blocks"][1]["text"] += " Today I lead the Northwind storefront team."
    code, report = check_copy(tmp_path, copy)
    assert code == 1 and {d["defect"] for d in report["defects"]} == {"confidential_term"}


def test_a_long_about_is_too_long_even_under_the_platform_limit(tmp_path):
    copy = good_copy()
    copy["blocks"][1]["text"] = "I automated the weekly sales report with Python and Power BI. " * 30  # ~1,900 chars
    code, report = check_copy(tmp_path, copy)
    kinds = {d["defect"] for d in report["defects"]}
    assert code == 1 and "too_long" in kinds and "over_limit" not in kinds
    assert check_copy(tmp_path, good_copy())[0] == 0


def test_a_long_experience_description_is_too_long(tmp_path):
    copy = good_copy()
    copy["blocks"].append({"section": "experience", "label": "Data analyst at Example Co", "achievements": ["ACH-001"],
                           "text": "- Automated the weekly sales report with Python and Power BI.\n" * 12})
    code, report = check_copy(tmp_path, copy)
    assert code == 1 and any(d["defect"] == "too_long" and d["where"] == "Data analyst at Example Co"
                             for d in report["defects"])


# --- review and submit ---------------------------------------------------------------------------------------------

def review_case(tmp_path, answers_text):
    project = tmp_path / "proj"
    folder = project / "openings" / "JOB-20260925-acme-data-analyst"
    app = folder / "application"
    app.mkdir(parents=True)
    (project / "profile.md").write_text(f"---\nconfidential_terms: {json.dumps(SECRET)}\n---\n", encoding="utf-8")
    (app / "cover_letter.md").write_text("The weekly report fell from 6 hours to 2 hours.\n", encoding="utf-8")
    (app / "answers.md").write_text(answers_text, encoding="utf-8")
    (app / "render_report.json").write_text(json.dumps({"kind": "cv", "keyword_coverage": 0.9, "missing_keywords": [],
                                                        "defects": [], "warnings": []}), encoding="utf-8")
    (folder / "opening.md").write_text("---\nid: JOB-20260925-acme-data-analyst\n---\n", encoding="utf-8")
    paths = []
    for lens, block in passing_blocks().items():
        path = tmp_path / f"{lens}.json"
        path.write_text(json.dumps(block), encoding="utf-8")
        paths.append(str(path))
    assert len(paths) == len(LENSES)
    proc = subprocess.run([sys.executable, str(AGG), "--lenses", *paths, "--round", "1", "--application-dir", str(app),
                           "--opening", str(folder / "opening.md"), "--json"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_review_blocks_a_leak_every_lens_missed(tmp_path):
    review = review_case(tmp_path, "Why us? I currently build the Contoso checkout and want a second role.\n")
    assert review["verdict"] == "FIX"
    (fix,) = [c for c in review["corrections"] if c["lens"] == "privacy"]
    assert fix["location"] == "answers.md" and "Contoso" in fix["instructions"]


def test_review_of_a_clean_kit_is_approved(tmp_path):
    review = review_case(tmp_path, "Why us? I build checkouts for global retail brands.\n")
    assert review["verdict"] == "APPROVED" and not review["corrections"]


def test_the_submit_gate_stays_closed_on_a_leaking_kit(tmp_path):
    app = make_opening(tmp_path)
    profile = tmp_path / "profile.md"
    profile.write_text(profile.read_text().replace("---\n", f"---\nconfidential_terms: {json.dumps(SECRET)}\n", 1))
    (app / "answers.md").write_text("Current work: the Northwind storefront.\n", encoding="utf-8")
    proc = gate(app)
    assert proc.returncode == 1 and "confidential" in proc.stderr and "Northwind" in proc.stderr
    (app / "answers.md").write_text("Current work: storefronts for global retail brands.\n", encoding="utf-8")
    assert gate(app).returncode == 0, gate(app).stderr


def test_the_validator_accepts_a_list_and_refuses_a_string(tmp_path):
    from test_jobs_profile import PROFILE as FULL, findings, keyed, write_project
    folder = write_project(tmp_path, profile=FULL.replace("---\n", f"---\nconfidential_terms: {json.dumps(SECRET)}\n", 1))
    assert not keyed(findings(folder), "profile.md", "confidential_terms")
    (tmp_path / "b").mkdir()
    folder = write_project(tmp_path / "b", profile=FULL.replace("---\n", "---\nconfidential_terms: Northwind\n", 1))
    assert keyed(findings(folder), "profile.md", "confidential_terms")


# --- friction: the skills ask only for what needs the user ---------------------------------------------------------

def test_the_manager_asks_only_for_facts_applies_and_public_writes():
    from test_jobs_documents import SKILLS
    rules = (SKILLS / "leading-job-search" / "references" / "autonomy.md").read_text(encoding="utf-8")
    assert "A correction the user gives" in rules and "is the approval" in rules
    assert 'Never ask "should I continue?"' in rules
    skill = (SKILLS / "leading-job-search" / "SKILL.md").read_text(encoding="utf-8")
    assert "references/autonomy.md" in skill
    assert 'write it after "ok"' not in skill  # a stated change is written, then shown
    writer = (SKILLS / "writing-applications" / "SKILL.md").read_text(encoding="utf-8")
    assert "Do not finalise a flagged bullet before the user answers" not in writer
    assert "never stops the card" in writer


# --- digest_fields.py: what a digest is built from ------------------------------------------------------------------

def test_digest_fields_reads_score_link_and_review_from_the_files_that_hold_them(tmp_path):
    from test_jobs_documents import SKILLS
    opening = tmp_path / "openings" / "JOB-20261020-acme-data-analyst"
    (opening / "application").mkdir(parents=True)
    (opening / "status.json").write_text(json.dumps({"status": "in_review", "history": [
        {"date": "2026-10-20T09:00", "status": "analyzed", "note": "PURSUE 81 (band strong)"}]}), encoding="utf-8")
    (opening / "analysis.json").write_text(json.dumps({
        "company": {"name": "Acme"}, "gates": {"eligibility": "PASS", "language": "PASS", "location": "PASS",
                                               "seniority": "PASS"},
        "link_resolution": {"apply_url": "https://jobs.acme.example/apply/1"}}), encoding="utf-8")
    (opening / "review-1.json").write_text(json.dumps({"round": 1, "verdict": "APPROVED"}), encoding="utf-8")
    (opening / "application" / "cv_ats.pdf").write_bytes(b"%PDF")
    out = subprocess.run([sys.executable, str(SKILLS / "leading-job-search" / "scripts" / "digest_fields.py"),
                          str(tmp_path)], capture_output=True, text=True, check=True).stdout
    assert "PURSUE 81" in out and "company: Acme" in out and "https://jobs.acme.example/apply/1" in out
    assert "review-1.json(1: APPROVED)" in out and "cv_ats.pdf@" in out
