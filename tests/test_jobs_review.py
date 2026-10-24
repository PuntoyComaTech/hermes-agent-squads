"""Review and submission guards for the jobs squad.

Pins the aggregation rules of reviewing-applications/scripts/aggregate_review.py (verdicts, corrections, company
claims, status), the submission.json contract of submitting-applications/scripts/check_submission.py, and the hygiene
of the three skills this area owns (no foreign traces, stdlib only, skill lint). Local fixtures only: no network, no
browser, nothing under ~/.hermes.
"""
import ast
import copy
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "squads" / "jobs" / "skills"
AGG = SKILLS / "reviewing-applications" / "scripts" / "aggregate_review.py"
CHECK = SKILLS / "submitting-applications" / "scripts" / "check_submission.py"
SKILL_LINT = REPO / "scripts" / "skill_lint.py"
OWNED_SKILLS = ("reviewing-applications", "submitting-applications", "triaging-inbox")
LENSES = ("truthfulness", "ats", "recruiter", "hiring_manager", "writing")
OPENING_ID = "JOB-20260925-acme-data-analyst"
COVER = "The weekly report fell from 6 hours to 2 hours.\n"
OPENING = f"---\nid: {OPENING_ID}\nlanguage: en\n---\nApply at https://jobs.acme.example/req/1\n"


# --- aggregate_review.py helpers -----------------------------------------------------------------------------------

def passing_blocks():
    return {
        "truthfulness": {
            "verdict": "PASS",
            "grounding": {"sources": ["application/cover_letter.md", "achievements.yaml", "profile.md"]},
            "findings": [],
            "company_claims": [],
        },
        "ats": {"verdict": "PASS", "keyword_coverage": 0.9, "missing": [], "defects": [],
                "pages": {"expected": 2, "actual": 2}},
        "recruiter": {
            "verdict": "PASS", "seconds_to_understand": 20, "would_open_evidence": True, "blockers": [],
            "market": {"checked": ["photo", "age", "marital_status", "references_line", "page_limit"],
                       "pages": 2, "page_limit": 2, "violations": []},
        },
        "hiring_manager": {"verdict": "PASS", "can_do_the_job": True, "concerns": [],
                           "interview_questions": [], "stretches": []},
        "writing": {
            "verdict": "PASS", "findings": [],
            "language": {"document_language": "en", "opening_language": "en", "declared_level": "B2",
                         "implied_level": None, "location": "cover_letter.md", "correction": None},
        },
    }


def render_report(**changes):
    """A clean render_report.json as rendering-cv writes it; changes override keys."""
    report = {"kind": "cv", "template": "classic", "keyword_coverage": 0.9, "missing_keywords": [],
              "keywords_total": 10, "defects": [], "warnings": [], "files": []}
    report.update(changes)
    return report


def set_render(folder, **changes):
    app = folder / "application"
    app.mkdir(parents=True, exist_ok=True)
    (app / "render_report.json").write_text(json.dumps(render_report(**changes)), encoding="utf-8")


def setup_case(folder, render=True):
    app = folder / "application"
    app.mkdir(exist_ok=True)
    (app / "cover_letter.md").write_text(COVER, encoding="utf-8")
    (folder / "opening.md").write_text(OPENING, encoding="utf-8")
    if render and not (app / "render_report.json").exists():
        set_render(folder)
    return app


def aggregate(folder, blocks, round_no=1, *extra, drop=(), render=True):
    setup_case(folder, render=render)
    paths = []
    for lens in LENSES:
        if lens in drop:
            continue
        path = folder / f"{lens}.json"
        path.write_text(json.dumps(blocks[lens]), encoding="utf-8")
        paths.append(str(path))
    cmd = [sys.executable, str(AGG), "--lenses", *paths, "--round", str(round_no),
           "--application-dir", str(folder / "application"), "--opening", str(folder / "opening.md"), *extra]
    return subprocess.run(cmd, capture_output=True, text=True)


def review_json(folder, blocks, round_no=1, *extra):
    proc = aggregate(folder, blocks, round_no, "--json", *extra)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def fix_correction(file="cover_letter.md", old="6 hours to 2 hours", new="6 hours to 20 minutes"):
    return {"type": "content", "mode": "replace", "file": file, "old": old, "new": new}


def draft_fail(blocks):
    blocks["truthfulness"]["verdict"] = "FAIL"
    blocks["truthfulness"]["findings"] = [{
        "kind": "draft", "check": "numbers", "location": "cover_letter.md, paragraph 1",
        "text": "from 6 hours to 2 hours", "problem": "achievements.yaml records 20 minutes",
        "correction": fix_correction(),
    }]
    return blocks


# --- aggregate_review.py: verdicts and status ----------------------------------------------------------------------

def test_all_pass_is_approved_and_ready(tmp_path):
    rev = review_json(tmp_path, passing_blocks())
    assert rev["verdict"] == "APPROVED"
    assert rev["status"] == "ready"
    assert rev["corrections"] == []
    assert rev["summary_for_user"]


def test_draft_error_gives_fix_in_round_one(tmp_path):
    rev = review_json(tmp_path, draft_fail(passing_blocks()))
    assert rev["verdict"] == "FIX"
    assert rev["status"] == "in_review"
    assert rev["corrections"] == [{"lens": "truthfulness", "type": "content", "location": "cover_letter.md, paragraph 1",
                                   "mode": "replace", "file": "cover_letter.md", "old": "6 hours to 2 hours",
                                   "new": "6 hours to 20 minutes"}]


def test_second_round_still_blocked_is_not_approved(tmp_path):
    rev = review_json(tmp_path, draft_fail(passing_blocks()), 2)
    assert rev["verdict"] == "NOT_APPROVED"
    assert rev["status"] == "not_approved"


def test_truthfulness_fail_is_never_approved(tmp_path):
    rev = review_json(tmp_path, draft_fail(passing_blocks()), 3)
    assert rev["verdict"] != "APPROVED"


def test_pass_verdict_with_a_blocking_item_is_refused(tmp_path):
    blocks = draft_fail(passing_blocks())
    blocks["truthfulness"]["verdict"] = "PASS"
    proc = aggregate(tmp_path, blocks, 1, "--out", str(tmp_path / "review-1.json"))
    assert proc.returncode == 1
    assert "verdict PASS with 1 blocking item" in proc.stderr
    assert not (tmp_path / "review-1.json").exists()


def test_fail_verdict_without_a_blocking_item_is_refused(tmp_path):
    blocks = passing_blocks()
    blocks["truthfulness"]["verdict"] = "FAIL"
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "needs a blocking item" in proc.stderr


def test_fix_verdict_is_not_allowed_on_truthfulness(tmp_path):
    blocks = passing_blocks()
    blocks["truthfulness"]["verdict"] = "FIX"
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "verdict must be PASS or FAIL" in proc.stderr


def test_out_file_is_written_only_when_every_rule_passes(tmp_path):
    out = tmp_path / "review-1.json"
    proc = aggregate(tmp_path, draft_fail(passing_blocks()), 1, "--out", str(out))
    assert proc.returncode == 0, proc.stderr
    assert json.loads(out.read_text(encoding="utf-8"))["verdict"] == "FIX"


def test_default_summary_is_written_when_none_is_given(tmp_path):
    rev = review_json(tmp_path, draft_fail(passing_blocks()))
    assert "truthfulness 1" in rev["summary_for_user"]


def test_summary_longer_than_five_lines_is_refused(tmp_path):
    proc = aggregate(tmp_path, passing_blocks(), 1, "--summary", "\n".join(["line"] * 6))
    assert proc.returncode == 1
    assert "1 to 5 lines" in proc.stderr


def test_contact_data_is_refused_in_the_summary(tmp_path):
    proc = aggregate(tmp_path, passing_blocks(), 1, "--summary", "Reach the candidate at ana@example.com")
    assert proc.returncode == 1
    assert "contact data" in proc.stderr


# --- aggregate_review.py: corrections --------------------------------------------------------------------------------

def test_replace_must_quote_text_that_occurs_exactly_once(tmp_path):
    blocks = draft_fail(passing_blocks())
    blocks["truthfulness"]["findings"][0]["correction"]["old"] = "hours"
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "'old' occurs 2 times in cover_letter.md" in proc.stderr


def test_replace_must_name_a_file_in_the_application_folder(tmp_path):
    blocks = draft_fail(passing_blocks())
    blocks["truthfulness"]["findings"][0]["correction"]["file"] = "missing.md"
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "not in the application folder" in proc.stderr


def test_instruction_correction_needs_instructions(tmp_path):
    blocks = draft_fail(passing_blocks())
    blocks["truthfulness"]["findings"][0]["correction"] = {"type": "format", "mode": "instruction", "instructions": " "}
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "needs 'instructions'" in proc.stderr


def test_correction_type_must_be_known(tmp_path):
    blocks = draft_fail(passing_blocks())
    blocks["truthfulness"]["findings"][0]["correction"]["type"] = "style"
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "content, format or strategy" in proc.stderr


def test_blocking_item_without_correction_is_refused(tmp_path):
    blocks = draft_fail(passing_blocks())
    del blocks["truthfulness"]["findings"][0]["correction"]
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "needs a correction object" in proc.stderr


def test_identical_old_and_new_text_is_refused(tmp_path):
    blocks = draft_fail(passing_blocks())
    blocks["truthfulness"]["findings"][0]["correction"]["new"] = "6 hours to 2 hours"
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "identical" in proc.stderr


# --- aggregate_review.py: truthfulness, company claims, grounding --------------------------------------------------

def test_grounding_must_cover_achievements_and_profile(tmp_path):
    blocks = passing_blocks()
    blocks["truthfulness"]["grounding"]["sources"] = ["application/cover_letter.md"]
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "achievements.yaml as well as" in proc.stderr


def test_profile_consistency_is_a_warning_not_a_block(tmp_path):
    blocks = passing_blocks()
    blocks["truthfulness"]["findings"] = [{
        "kind": "profile_consistency", "check": "dates", "location": "profile.md vs achievements.yaml",
        "text": "2022-03", "problem": "start dates differ", "conflicting_sources": ["achievements.yaml", "profile.md"],
    }]
    rev = review_json(tmp_path, blocks)
    assert rev["verdict"] == "APPROVED"
    assert any("profile consistency" in w for w in rev["warnings"])
    assert rev["corrections"] == []


def test_profile_consistency_must_name_both_sources(tmp_path):
    blocks = passing_blocks()
    blocks["truthfulness"]["findings"] = [{
        "kind": "profile_consistency", "check": "dates", "location": "x", "text": "y", "problem": "z",
        "conflicting_sources": ["profile.md"],
    }]
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "naming achievements.yaml and profile.md" in proc.stderr


def test_company_claim_from_the_opening_url_is_refused(tmp_path):
    blocks = passing_blocks()
    blocks["truthfulness"]["company_claims"] = [{
        "claim": "Acme runs a data platform", "location": "cover_letter.md, paragraph 1",
        "source_url": "https://jobs.acme.example/req/1/", "source_located_by_reviewer": True,
        "reason": "page states it", "verdict": "kept",
    }]
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "comes from the opening body" in proc.stderr


def test_company_claim_needs_a_source_the_reviewer_located(tmp_path):
    blocks = passing_blocks()
    blocks["truthfulness"]["company_claims"] = [{
        "claim": "Acme runs a data platform", "location": "cover_letter.md, paragraph 1",
        "source_url": "https://acme.example/platform", "source_located_by_reviewer": False,
        "reason": "page states it", "verdict": "kept",
    }]
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "source_located_by_reviewer must be true" in proc.stderr


def test_dropped_company_claim_blocks_and_is_listed_for_the_writer(tmp_path):
    blocks = passing_blocks()
    blocks["truthfulness"]["verdict"] = "FAIL"
    blocks["truthfulness"]["company_claims"] = [{
        "claim": "Acme won a national award", "location": "cover_letter.md, paragraph 2",
        "source_url": "https://acme.example/news", "source_located_by_reviewer": True,
        "reason": "no page found", "verdict": "dropped",
        "correction": {"type": "content", "mode": "instruction", "instructions": "remove the award sentence"},
    }]
    rev = review_json(tmp_path, blocks)
    assert rev["verdict"] == "FIX"
    assert rev["dropped_claims"] == [{"claim": "Acme won a national award", "location": "cover_letter.md, paragraph 2",
                                      "reason": "no page found"}]


def test_kept_company_claim_with_fetched_text_passes(tmp_path):
    blocks = passing_blocks()
    blocks["truthfulness"]["company_claims"] = [{
        "claim": "Acme runs a data platform", "location": "cover_letter.md, paragraph 1",
        "source_url": "https://acme.example/platform", "source_located_by_reviewer": True,
        "source_excerpt": "Acme Data runs a reporting platform for regional retailers.",
        "reason": "page states it", "verdict": "kept",
    }]
    rev = review_json(tmp_path, blocks)
    assert rev["verdict"] == "APPROVED"
    assert rev["dropped_claims"] == []


def test_kept_company_claim_citing_a_captured_page_passes(tmp_path):
    (tmp_path / "application").mkdir()
    (tmp_path / "application" / "source_about.html").write_text("<p>Acme runs a reporting platform.</p>",
                                                               encoding="utf-8")
    blocks = passing_blocks()
    blocks["truthfulness"]["company_claims"] = [{
        "claim": "Acme runs a data platform", "location": "cover_letter.md, paragraph 1",
        "source_url": "https://acme.example/platform", "source_located_by_reviewer": True,
        "source_file": "source_about.html", "reason": "page states it", "verdict": "kept",
    }]
    assert review_json(tmp_path, blocks)["verdict"] == "APPROVED"


def test_a_located_flag_alone_is_not_evidence_for_a_kept_claim(tmp_path):
    # The located flag is the lens's own word: a kept claim with an invented source and no fetched text is refused.
    blocks = passing_blocks()
    blocks["truthfulness"]["company_claims"] = [{
        "claim": "Acme won a national data award", "location": "cover_letter.md, paragraph 2",
        "source_url": "https://acme-awards.example/2026", "source_located_by_reviewer": True,
        "reason": "page states it", "verdict": "kept",
    }]
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1 and "needs source_excerpt" in proc.stderr


# --- aggregate_review.py: ats, recruiter, hiring manager, writing ----------------------------------------------------

def test_keyword_without_evidence_is_a_gap_not_a_block(tmp_path):
    blocks = passing_blocks()
    blocks["ats"]["missing"] = [{"keyword": "Kubernetes", "evidence": ""}, "Terraform"]
    rev = review_json(tmp_path, blocks)
    assert rev["verdict"] == "APPROVED"
    assert sum("gap, not written" in w for w in rev["warnings"]) == 2


def test_keyword_with_evidence_blocks_with_a_correction(tmp_path):
    blocks = passing_blocks()
    blocks["ats"]["verdict"] = "FIX"
    blocks["ats"]["missing"] = [{"keyword": "data pipeline", "evidence": "ACH-007", "location": "cv_content.json",
                                 "correction": {"type": "content", "mode": "instruction",
                                                "instructions": "add 'data pipeline' to the ACH-007 bullet"}}]
    rev = review_json(tmp_path, blocks)
    assert rev["verdict"] == "FIX"
    assert rev["corrections"][0]["lens"] == "ats"


def test_environment_defect_never_blocks(tmp_path):
    blocks = passing_blocks()
    blocks["ats"]["defects"] = [{"location": "render", "problem": "no PDF engine installed", "hard": True,
                                 "environment": True}]
    rev = review_json(tmp_path, blocks)
    assert rev["verdict"] == "APPROVED"
    assert any("no PDF engine" in w for w in rev["warnings"])


def test_hard_defect_blocks_with_a_correction(tmp_path):
    blocks = passing_blocks()
    blocks["ats"]["verdict"] = "FIX"
    blocks["ats"]["defects"] = [{"location": "cv_ats.pdf, page 2", "problem": "heading split", "hard": True,
                                 "environment": False,
                                 "correction": {"type": "format", "mode": "instruction",
                                                "instructions": "keep the heading with its bullet"}}]
    assert review_json(tmp_path, blocks)["verdict"] == "FIX"


# The review reads application/render_report.json and blocks on what the render measures.

def render_defect_blocks(defect_code="unverified_achievement"):
    """The ats lens as a finished child reads a render with one hard defect: FIX, with the correction it names."""
    blocks = passing_blocks()
    blocks["ats"]["verdict"] = "FIX"
    blocks["ats"]["defects"] = []  # the defect is read from render_report.json, not repeated by the child
    return blocks


def test_render_hard_defect_blocks_the_review(tmp_path):
    set_render(tmp_path, defects=[{"code": "unverified_achievement", "message": "ACH-099 is not in achievements.yaml"}])
    rev = review_json(tmp_path, render_defect_blocks())
    assert rev["verdict"] == "FIX" and rev["status"] == "in_review"
    assert any("unverified_achievement" in c["instructions"] for c in rev["corrections"])


def test_a_pass_ignoring_a_render_hard_defect_is_refused(tmp_path):
    # A render hard defect is a blocking item: a lens PASS beside it is refused.
    set_render(tmp_path, defects=[{"code": "unverified_achievement", "message": "ACH-099 is not in achievements.yaml"}])
    out = tmp_path / "review-1.json"
    proc = aggregate(tmp_path, passing_blocks(), 1, "--out", str(out))
    assert proc.returncode == 1
    assert "verdict PASS with 1 blocking item" in proc.stderr
    assert not out.exists()


def test_render_environment_defect_is_only_a_warning(tmp_path):
    set_render(tmp_path, defects=[{"code": "docx_missing", "message": "pip install python-docx"}])
    rev = review_json(tmp_path, passing_blocks())
    assert rev["verdict"] == "APPROVED"
    assert any("docx_missing" in w for w in rev["warnings"])


def test_keyword_coverage_zero_blocks_even_when_every_keyword_is_declared_a_gap(tmp_path):
    # Declared keyword gaps do not excuse a measured coverage of 0.0.
    set_render(tmp_path, keyword_coverage=0.0, missing_keywords=["Kubernetes", "Airflow", "dbt"])
    blocks = passing_blocks()
    blocks["ats"]["verdict"] = "FIX"
    blocks["ats"]["missing"] = [{"keyword": "Kubernetes", "evidence": ""}, {"keyword": "Airflow", "evidence": ""},
                                {"keyword": "dbt", "evidence": ""}]
    rev = review_json(tmp_path, blocks)
    assert rev["verdict"] == "FIX"
    assert any("keyword coverage is 0.0" in c["instructions"] for c in rev["corrections"])


def test_coverage_made_only_of_unbackable_keywords_does_not_loop_forever(tmp_path):
    # Real run: coverage 0.42, and every missing keyword (AI agents, voice AI, healthcare) was one the user could not
    # truthfully claim. Three writer and three reviewer rounds later it was still FIX. Declared gaps above the floor
    # are a warning for the user; an unbacked miss still blocks.
    set_render(tmp_path, keyword_coverage=0.42, missing_keywords=["voice AI", "healthcare"])
    blocks = passing_blocks()
    blocks["ats"]["missing"] = [{"keyword": "voice AI", "evidence": ""}, "healthcare"]
    rev = review_json(tmp_path, blocks)
    assert rev["verdict"] == "APPROVED", rev
    assert any("every missing keyword is a declared gap" in w for w in rev["warnings"])
    set_render(tmp_path, keyword_coverage=0.42, missing_keywords=["voice AI", "healthcare", "data pipeline"])
    blocks["ats"]["verdict"] = "FIX"
    assert review_json(tmp_path, blocks)["verdict"] == "FIX"


def test_keyword_coverage_zero_is_refused_as_approved(tmp_path):
    set_render(tmp_path, keyword_coverage=0.0, missing_keywords=["Kubernetes", "Airflow", "dbt"])
    proc = aggregate(tmp_path, passing_blocks())
    assert proc.returncode == 1 and "verdict PASS with 1 blocking item" in proc.stderr


def test_missing_render_report_refuses_the_review(tmp_path):
    proc = aggregate(tmp_path, passing_blocks(), render=False)
    assert proc.returncode == 1 and "render_report.json is missing" in proc.stderr


def test_review_id_with_a_path_is_refused(tmp_path):
    # The review id is written into the JSON, so a path must never pass as an id.
    proc = aggregate(tmp_path, passing_blocks(), 1, "--id", "../../../../etc/x")
    assert proc.returncode == 2 and "opening id" in proc.stderr


def test_page_count_off_target_needs_a_hard_defect(tmp_path):
    blocks = passing_blocks()
    blocks["ats"]["pages"] = {"expected": 2, "actual": 3}
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "page count differs" in proc.stderr


def test_market_violation_blocks(tmp_path):
    blocks = passing_blocks()
    blocks["recruiter"]["verdict"] = "FIX"
    blocks["recruiter"]["market"]["violations"] = [{
        "convention": "photo", "location": "cv_ats.html, header", "problem": "a photo is printed",
        "correction": {"type": "format", "mode": "instruction", "instructions": "remove the photo"},
    }]
    rev = review_json(tmp_path, blocks)
    assert rev["verdict"] == "FIX"
    assert rev["corrections"][0]["lens"] == "recruiter"


def test_unknown_market_check_is_refused(tmp_path):
    blocks = passing_blocks()
    blocks["recruiter"]["market"]["checked"] = ["religion"]
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "unknown market check" in proc.stderr


def test_pages_over_the_limit_need_a_page_limit_violation(tmp_path):
    blocks = passing_blocks()
    blocks["recruiter"]["market"]["pages"] = 3
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "add a page_limit violation" in proc.stderr


def test_stretch_not_answerable_from_sources_blocks(tmp_path):
    blocks = passing_blocks()
    blocks["hiring_manager"]["verdict"] = "FIX"
    blocks["hiring_manager"]["stretches"] = [{
        "location": "cover_letter.md, paragraph 2", "claim": "led the migration",
        "backtrack_question": "What did you own?", "answerable_from_sources": False,
        "correction": fix_correction(old="6 hours to 2 hours", new="cut from 6 hours to 2 hours"),
    }]
    assert review_json(tmp_path, blocks)["verdict"] == "FIX"


def test_stretch_answerable_from_sources_does_not_block(tmp_path):
    blocks = passing_blocks()
    blocks["hiring_manager"]["stretches"] = [{
        "location": "cover_letter.md, paragraph 2", "claim": "cut the report time",
        "backtrack_question": "How did you do it?", "answerable_from_sources": True,
    }]
    assert review_json(tmp_path, blocks)["verdict"] == "APPROVED"


def test_language_mismatch_blocks(tmp_path):
    blocks = passing_blocks()
    blocks["writing"]["verdict"] = "FIX"
    blocks["writing"]["language"]["document_language"] = "es"
    blocks["writing"]["language"]["correction"] = {"type": "format", "mode": "instruction",
                                                   "instructions": "rewrite the letter in English"}
    rev = review_json(tmp_path, blocks)
    assert rev["verdict"] == "FIX"
    assert rev["corrections"][0]["lens"] == "writing"


def test_declared_and_implied_level_must_agree(tmp_path):
    blocks = passing_blocks()
    blocks["writing"]["verdict"] = "FIX"
    blocks["writing"]["language"]["implied_level"] = "C1"
    blocks["writing"]["language"]["correction"] = {"type": "content", "mode": "instruction",
                                                   "instructions": "state B2 or drop the level claim"}
    assert review_json(tmp_path, blocks)["verdict"] == "FIX"


def test_writing_finding_needs_a_correction(tmp_path):
    blocks = passing_blocks()
    blocks["writing"]["verdict"] = "FIX"
    blocks["writing"]["findings"] = [{"location": "cover_letter.md, paragraph 3", "text": "a comma splice",
                                      "fix": "split the sentence"}]
    proc = aggregate(tmp_path, blocks)
    assert proc.returncode == 1
    assert "needs a correction object" in proc.stderr


# --- aggregate_review.py: input and exit codes ----------------------------------------------------------------------

def test_missing_lens_block_exits_two(tmp_path):
    proc = aggregate(tmp_path, passing_blocks(), 1, drop=("writing",))
    assert proc.returncode == 2
    assert "missing lens block(s): writing" in proc.stderr


def test_invalid_json_exits_two(tmp_path):
    setup_case(tmp_path)
    paths = []
    for lens in LENSES:
        path = tmp_path / f"{lens}.json"
        path.write_text("{not json" if lens == "ats" else json.dumps(passing_blocks()[lens]), encoding="utf-8")
        paths.append(str(path))
    proc = subprocess.run([sys.executable, str(AGG), "--lenses", *paths, "--round", "1",
                           "--application-dir", str(tmp_path / "application")], capture_output=True, text=True)
    assert proc.returncode == 2
    assert "not valid JSON" in proc.stderr


def test_round_must_be_positive(tmp_path):
    proc = aggregate(tmp_path, passing_blocks(), 0)
    assert proc.returncode == 2


def test_help_exits_zero_for_both_scripts():
    for script in (AGG, CHECK):
        proc = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True)
        assert proc.returncode == 0, script.name
        assert proc.stdout.strip()


# --- check_submission.py -------------------------------------------------------------------------------------------

def make_application(folder, opening_id=OPENING_ID, apply_url="https://jobs.lever.co/acme/2f1c9a7e-5b1d-4c2a-9e8f-1a2b3c4d5e6f/apply"):
    app = folder / "openings" / opening_id / "application"
    app.mkdir(parents=True)
    (app.parent / "opening.md").write_text(f"---\nid: {opening_id}\ncompany: Acme\napply_url: {apply_url}\n---\nPosting.\n",
                                           encoding="utf-8")
    for name in ("before.png", "confirmation.png"):
        (app / name).write_bytes(b"\x89PNG\r\n\x1a\n")
    (app / "kit.md").write_text("Answers ready to copy.\n", encoding="utf-8")
    (app / "cv_ats.pdf").write_bytes(b"%PDF-1.4 fictional CV\n")
    return app


PROJECT_PROFILE = "---\nname: Example\nauto_apply: try\nreview_before_submit: false\n---\nFictional project.\n"
USER_WORDS = "Yes, apply to this one."


def approve(app, day="2026-10-20"):
    """A finished review: review-1.json APPROVED and a ready line in status.json, both dated day."""
    opening = app.parent
    (opening / "review-1.json").write_text(json.dumps({"verdict": "APPROVED", "status": "ready"}), encoding="utf-8")
    (opening / "status.json").write_text(json.dumps({"history": [
        {"date": f"{day}T09:00", "status": "in_review", "by": "jobs-reviewer"},
        {"date": f"{day}T09:05", "status": "ready", "by": "jobs-reviewer"}], "status": "ready"}), encoding="utf-8")


def consent(app, by="Ana Example", words=USER_WORDS, day="2026-10-20", opening_id=OPENING_ID, **extra):
    """The manager's consent.json: the user's literal words for this one opening, bound to the kit as it is now."""
    proc = subprocess.run([sys.executable, str(CHECK), "--kit-hash", str(app)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    data = {"opening_id": opening_id, "by": by, "words": words, "date": day, "kit_sha256": proc.stdout.strip(), **extra}
    (app / "consent.json").write_text(json.dumps(data), encoding="utf-8")


def project_profile(app, text):
    """profile.md of the project that owns this opening (openings/ sits under it)."""
    (app.parent.parent.parent / "profile.md").write_text(text, encoding="utf-8")


def ready_to_submit(tmp_path, **kwargs):
    """A fully approved opening with the user's consent: the only state in which a SUBMITTED record may pass."""
    app = make_application(tmp_path, **kwargs)
    project_profile(app, PROJECT_PROFILE)
    approve(app)
    consent(app)
    return app


def submitted():
    return {
        "id": OPENING_ID, "result": "SUBMITTED", "method": "no_login_form",
        "filled_fields": [
            {"field": "Email", "source": "contact.yaml"},
            {"field": "Work authorization", "source": "application-data.yaml"},
            {"field": "Why this role", "source": "answers.md"},
            {"field": "CV upload", "source": "cv"},
        ],
        "pending_questions": [], "screenshots": ["before.png", "confirmation.png"], "reason": "",
    }


def check(app, data, *extra):
    path = app / "submission.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return subprocess.run([sys.executable, str(CHECK), str(path), *extra], capture_output=True, text=True)


def test_valid_submitted_passes(tmp_path):
    app = ready_to_submit(tmp_path)
    proc = check(app, submitted())
    assert proc.returncode == 0, proc.stderr
    assert "valid: SUBMITTED" in proc.stdout


def test_submitted_needs_a_confirmation_screenshot(tmp_path):
    app = make_application(tmp_path)
    data = submitted()
    data["screenshots"] = ["before.png"]
    proc = check(app, data)
    assert proc.returncode == 1
    assert "confirmation screenshot" in proc.stderr


def test_submitted_needs_the_confirmation_file_on_disk(tmp_path):
    app = make_application(tmp_path)
    (app / "confirmation.png").unlink()
    proc = check(app, submitted())
    assert proc.returncode == 1
    assert "does not exist" in proc.stderr


def test_submitted_refuses_any_method_but_no_login_form(tmp_path):
    app = make_application(tmp_path)
    data = submitted()
    data["method"] = "requires_account"
    proc = check(app, data)
    assert proc.returncode == 1
    assert "needs method no_login_form" in proc.stderr


def test_every_filled_field_needs_a_source(tmp_path):
    app = make_application(tmp_path)
    data = submitted()
    data["filled_fields"].append({"field": "Phone"})
    proc = check(app, data)
    assert proc.returncode == 1
    assert "source must be" in proc.stderr


def test_unknown_source_is_refused(tmp_path):
    app = make_application(tmp_path)
    data = submitted()
    data["filled_fields"][0]["source"] = "linkedin profile"
    assert check(app, data).returncode == 1


def test_a_scam_lookalike_link_can_never_be_marked_submitted(tmp_path):
    # A recruiter message sent a look-alike Greenhouse host; the applier must fall back to a manual kit.
    app = make_application(tmp_path, apply_url="https://boards-greenhouse.io/acme/jobs/123")
    proc = check(app, submitted())
    assert proc.returncode == 1 and "apply link is unverified" in proc.stderr
    kit = {**submitted(), "result": "NOT_POSSIBLE", "method": "other", "filled_fields": [], "screenshots": [],
           "reason": "unverified apply link", "manual_kit": "application/kit.md"}
    assert check(app, kit).returncode == 0


def test_a_job_board_or_linkedin_link_is_kit_only_never_submitted(tmp_path):
    # The scout found the opening on a job board and on LinkedIn: the bot may never submit through those pages.
    for url in ("https://www.getonbrd.com/jobs/technical-lead-backend-acme-remote",
                "https://co.linkedin.com/jobs/view/4000000003"):
        app = make_application(tmp_path / url.split("/")[2], apply_url=url)
        proc = check(app, submitted())
        assert proc.returncode == 1 and "kit only" in proc.stderr, (url, proc.stderr)


def test_submitted_without_any_known_apply_url_is_refused(tmp_path):
    app = make_application(tmp_path)
    (app.parent / "opening.md").write_text("---\nid: x\n---\nPosting.\n", encoding="utf-8")
    proc = check(app, submitted())
    assert proc.returncode == 1 and "needs the opening's apply_url" in proc.stderr


def test_consult_source_is_accepted(tmp_path):
    app = ready_to_submit(tmp_path)
    data = submitted()
    data["filled_fields"][0]["source"] = "consult:card-42"
    assert check(app, data).returncode == 0


def test_field_values_are_refused_in_the_file(tmp_path):
    app = make_application(tmp_path)
    data = submitted()
    data["filled_fields"][0]["value"] = "a value"
    proc = check(app, data)
    assert proc.returncode == 1
    assert "keeps its name and source only" in proc.stderr


def test_contact_data_in_text_is_refused(tmp_path):
    app = make_application(tmp_path)
    data = submitted()
    data["reason"] = "Sent to ana@example.com"
    proc = check(app, data)
    assert proc.returncode == 1
    assert "contact data" in proc.stderr


def test_needs_data_needs_the_questions(tmp_path):
    app = make_application(tmp_path)
    data = {"id": OPENING_ID, "result": "NEEDS_DATA", "method": "other", "filled_fields": [],
            "pending_questions": [], "screenshots": [], "reason": ""}
    assert check(app, data).returncode == 1
    data["pending_questions"] = [{"question": "Notice period?", "options": ["2 weeks", "1 month"]}]
    proc = check(app, data)
    assert proc.returncode == 0, proc.stderr


def test_submitted_cannot_carry_open_questions(tmp_path):
    app = make_application(tmp_path)
    data = submitted()
    data["pending_questions"] = [{"question": "Notice period?"}]
    assert check(app, data).returncode == 1


def test_not_possible_needs_reason_and_kit(tmp_path):
    app = make_application(tmp_path)
    (app / "kit.md").unlink()
    data = {"id": OPENING_ID, "result": "NOT_POSSIBLE", "method": "requires_account", "filled_fields": [],
            "pending_questions": [], "screenshots": [], "reason": "the form asks for an account",
            "manual_kit": "application/kit.md"}
    proc = check(app, data)
    assert proc.returncode == 1
    assert "kit.md does not exist" in proc.stderr
    (app / "kit.md").write_text("answers\n", encoding="utf-8")
    assert check(app, data).returncode == 0
    data["reason"] = " "
    assert check(app, data).returncode == 1


def test_id_must_match_the_opening_folder(tmp_path):
    app = make_application(tmp_path)
    data = submitted()
    data["id"] = "JOB-20260925-other-role"
    proc = check(app, data)
    assert proc.returncode == 1
    assert "does not match the opening folder" in proc.stderr


def test_id_format_is_enforced(tmp_path):
    app = make_application(tmp_path)
    data = submitted()
    data["id"] = "JOB-2026-acme"
    assert check(app, data).returncode == 1


def test_result_vocabulary_is_enforced(tmp_path):
    app = make_application(tmp_path)
    data = submitted()
    data["result"] = "DONE"
    assert check(app, data).returncode == 1


def test_missing_required_key_is_refused(tmp_path):
    app = make_application(tmp_path)
    data = submitted()
    del data["screenshots"]
    proc = check(app, data)
    assert proc.returncode == 1
    assert "screenshots: missing" in proc.stderr


def test_unreadable_or_non_json_input_exits_two(tmp_path):
    proc = subprocess.run([sys.executable, str(CHECK), str(tmp_path / "absent.json")],
                          capture_output=True, text=True)
    assert proc.returncode == 2
    bad = tmp_path / "submission.json"
    bad.write_text("[1, 2]", encoding="utf-8")
    assert subprocess.run([sys.executable, str(CHECK), str(bad)], capture_output=True, text=True).returncode == 2


def test_json_output_reports_errors(tmp_path):
    app = make_application(tmp_path)
    data = submitted()
    data["method"] = "email"
    proc = check(app, data, "--json")
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report["ok"] is False and report["result"] == "SUBMITTED" and report["errors"]


# --- hygiene of the owned skills ---------------------------------------------------------------------------------

FOREIGN = re.compile(
    r"cla" r"ude|anthro" r"pic|ma" r"ds|lorent" r"zen|ai-job-search|dan" r"ish|den" r"mark|dan" r"sk|jobin" r"dex|"
    r"jobn" r"et|jobb" r"ank|jobdan" r"mark|"
    r"la" r"tex|modern" r"cv|lua" r"la" r"tex|xe" r"la" r"tex|\.cla" r"ude|CLA" r"UDE\.md|framework" r"_version|\bfork\b|no" r"tion|"
    r"(?<![\w.])/(?:apply|scrape|setup|outcome|rank|interview|gmail-sync|expand|reset|upskill|add-portal)\b|"
    r"#\d{3,}",
    re.IGNORECASE,
)


def owned_files():
    for name in OWNED_SKILLS:
        root = SKILLS / name
        for path in root.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                yield path


def test_owned_files_carry_no_foreign_traces():
    offenders = []
    for path in owned_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FOREIGN.search(line):
                offenders.append(f"{path.relative_to(REPO)}:{number}")
    assert offenders == []


def test_owned_scripts_are_stdlib_only():
    allowed = set(sys.stdlib_module_names) | {"__future__"}
    for script in (AGG, CHECK):
        tree = ast.parse(script.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            else:
                continue
            assert set(names) <= allowed, f"{script.name} imports {names}"


def test_owned_skills_pass_skill_lint():
    pytest.importorskip("yaml")
    targets = [str(SKILLS / name) for name in OWNED_SKILLS]
    proc = subprocess.run([sys.executable, str(SKILL_LINT), *targets, "--json"],
                          capture_output=True, text=True)
    report = json.loads(proc.stdout)
    assert report["findings"] == [], report["findings"]
    assert proc.returncode == 0



# --- --apply: the reviewer fixes wording itself; only hard items decide (the Factored review-7 case) --------------

def spelling_finding(old="customise", new="customize"):
    return {"location": "cover_letter.md, paragraph 1", "text": old, "fix": "US spelling",
            "correction": {"type": "format", "mode": "replace", "file": "cover_letter.md", "old": old, "new": new}}


def test_a_later_round_with_only_wording_fixes_is_approved_and_the_fix_is_written(tmp_path):
    """Round 7 of a real application: 3 spellings and 1 phrasing left; each is a quotable replace the reviewer can
    do itself. Before --apply this was NOT_APPROVED and an 8th round."""
    blocks = passing_blocks()
    blocks["writing"]["verdict"] = "FIX"
    blocks["writing"]["findings"] = [spelling_finding("6 hours", "six hours")]
    setup_case(tmp_path)
    out = tmp_path / "review-7.json"
    review = review_json(tmp_path, blocks, 7, "--apply", "--out", str(out))
    assert review["verdict"] == "APPROVED" and review["corrections"] == []
    assert (tmp_path / "application" / "cover_letter.md").read_text() == "The weekly report fell from six hours to 2 hours.\n"
    assert json.loads(out.read_text())["applied"][0]["result"] == "written"
    # a re-run after the write finds the fix already in place: still approved, nothing written twice
    again = review_json(tmp_path, blocks, 7, "--apply")
    assert again["verdict"] == "APPROVED"


def test_a_truth_problem_still_blocks_with_apply(tmp_path):
    blocks = draft_fail(passing_blocks())
    blocks["writing"]["verdict"] = "FIX"
    blocks["writing"]["findings"] = [spelling_finding("weekly", "Weekly")]
    review = review_json(tmp_path, blocks, 2, "--apply")
    assert review["verdict"] == "NOT_APPROVED"
    assert [c["lens"] for c in review["corrections"]] == ["truthfulness"], "wording is not sent back for a round"


def test_without_apply_wording_still_blocks_as_before(tmp_path):
    blocks = passing_blocks()
    blocks["writing"]["verdict"] = "FIX"
    blocks["writing"]["findings"] = [spelling_finding("6 hours", "six hours")]
    assert review_json(tmp_path, blocks, 2)["verdict"] == "NOT_APPROVED"
