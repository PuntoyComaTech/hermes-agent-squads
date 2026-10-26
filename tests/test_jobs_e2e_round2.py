"""The failures of the 2026-10-26 end-to-end round of the jobs squad (bugs 15 to 19), replayed through the real scripts.

Each test reproduces what the owner saw on the board and fails when its fix is removed. Fictional people and
companies; the wording of the claims, the form options and the malformed lens block are the ones the live run produced.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real import HERMES, env_for, needs_hermes, temp_root  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "squads" / "jobs" / "skills"
CONTRACT = SKILLS / "jobs-contract" / "scripts"
AGG = SKILLS / "reviewing-applications" / "scripts" / "aggregate_review.py"
CHECK = SKILLS / "submitting-applications" / "scripts" / "check_submission.py"
CODE_WAIT = SKILLS / "submitting-applications" / "scripts" / "code_wait.py"
EXTRACT = SKILLS / "triaging-inbox" / "scripts" / "extract_code.py"
RENDER = SKILLS / "rendering-cv" / "scripts" / "render_cv.py"
FORM_ANSWER = CONTRACT / "form_answer.py"
SWEEP = CONTRACT / "claim_sweep.py"
ID = "JOB-20261023-acme-senior-ai-engineer"
LENSES = ("truthfulness", "ats", "recruiter", "hiring_manager", "writing")
GREENHOUSE = "https://job-boards.greenhouse.io/acme/jobs/4514946008"
ACHIEVEMENTS = """experiences:
  - {id: EXP-001, title: "Technical Lead", company: "Example Labs", from: 2026-06, to: current}
  - {id: EXP-002, title: "Senior Software Engineer", company: "Example Labs", from: 2025-04, to: 2026-06}
achievements:
  - id: ACH-001
    experience: EXP-002
    proficiency: did
    en: "Built the order management system that centralises quotes and orders for a parts distributor."
    verified: true
  - id: ACH-018
    experience: EXP-002
    proficiency: did
    en: "Built the OMS assistants and agents on Azure AI Foundry."
    verified: true
  - id: ACH-008
    experience: EXP-002
    proficiency: did
    en: "Built AI workflows with Python and FastAPI in the same role."
    verified: true
languages:
  - {language: spanish, level: C2, verified: true}
  - {language: english, level: B2, verified: true}
"""
# The record of the live round: the user is searching for remote work (profile.md), which says nothing about how the
# current job is done.
PROFILE = ("---\nname: Example\nwork_mode: [remote_global, remote_country]\nauto_apply: auto\n"
           "auto_apply_since: 2026-10-01\napply_consent: standing\ndaily_apply_cap: 10\ndaily_easy_apply_cap: 5\n"
           "review_before_submit: false\n---\n- Solo remoto (global).\n")
FORM_OPTIONS = ["Native or Bilingual Proficiency", "Full Professional Proficiency", "Professional Working Proficiency",
                "Limited Working Proficiency", "Elementary Proficiency"]


def py(*argv, stdin=None, env=None, timeout=120):
    return subprocess.run([sys.executable, "-B", *map(str, argv)], capture_output=True, text=True, input=stdin,
                          timeout=timeout, env=env)


def project(root: Path, achievements: str = ACHIEVEMENTS) -> Path:
    folder = root / "openings" / ID
    app = folder / "application"
    app.mkdir(parents=True)
    (root / "profile.md").write_text(PROFILE, encoding="utf-8")
    (root / "achievements.yaml").write_text(achievements, encoding="utf-8")
    (folder / "opening.md").write_text(f"---\nid: {ID}\ncompany: Acme\nrole: Senior AI Engineer\n"
                                       f"apply_url: {GREENHOUSE}\nlanguage: en\n---\nPosting.\n", encoding="utf-8")
    (folder / "status.json").write_text(json.dumps({"id": ID, "status": "in_review", "history": []}),
                                        encoding="utf-8")
    (app / "render_report.json").write_text(json.dumps({"keyword_coverage": 0.9, "missing_keywords": [],
                                                        "defects": [], "warnings": []}), encoding="utf-8")
    return app


def passing():
    return {
        "truthfulness": {"verdict": "PASS", "findings": [], "company_claims": [],
                         "grounding": {"sources": ["achievements.yaml", "profile.md", "application/cover_letter.md"]}},
        "ats": {"verdict": "PASS", "keyword_coverage": 0.9, "missing": [], "defects": []},
        "recruiter": {"verdict": "PASS", "seconds_to_understand": 15, "would_open_evidence": True, "blockers": [],
                      "market": {"checked": ["photo", "age"], "violations": []}},
        "hiring_manager": {"verdict": "PASS", "can_do_the_job": True, "concerns": [], "interview_questions": [],
                           "stretches": []},
        "writing": {"verdict": "PASS", "findings": [],
                    "language": {"document_language": "en", "opening_language": "en", "declared_level": "B2",
                                 "implied_level": None}},
    }


def aggregate(app: Path, blocks: dict, round_no: int, *extra):
    paths = []
    for lens in LENSES:
        path = app.parent.parent.parent / f"{lens}.json"
        path.write_text(json.dumps(blocks[lens]), encoding="utf-8")
        paths.append(path)
    return py(AGG, "--lenses", *paths, "--round", round_no, "--id", ID, "--application-dir", app,
              "--opening", app.parent / "opening.md", "--apply", "--json", *extra)


# --- 15. one round names every instance of a recurring wrong claim ---------------------------------------------

LETTER = ("I built the order management system for a parts distributor.\n"
          "<!-- achievements: ACH-001 -->\n\n"
          "My production backend was NestJS; I used Python and FastAPI for the AI and automation layer.\n"
          "<!-- achievements: ACH-008 -->\n")
MESSAGE = ("My production backend work was in Node.js with NestJS, I used Python and FastAPI in the AI layer, and I "
           "have built features on AWS.\n")
ANSWERS = ("## 3. Most complex GenAI feature\n\n[FIELD]\nMCP servers and AI assistants inside the order management "
           "system.\n[/FIELD]\n\nNOTE TO SELF (not for pasting): the AI workflow layer used Python, FastAPI and "
           "LangGraph.\n")


def mixed_application(root: Path) -> Path:
    app = project(root)
    (app / "cover_letter.md").write_text(LETTER, encoding="utf-8")
    (app / "recruiter_message.md").write_text(MESSAGE, encoding="utf-8")
    (app / "answers.md").write_text(ANSWERS, encoding="utf-8")
    return app


def note_only_finding(blocks):
    """review-8 of the live round: the truthfulness lens named the mix in the answers.md note only."""
    blocks["truthfulness"]["verdict"] = "FAIL"
    blocks["truthfulness"]["findings"] = [{
        "kind": "draft", "check": "tools", "location": "answers.md, field 3 NOTE TO SELF",
        "text": "the AI workflow layer used Python, FastAPI and LangGraph.",
        "problem": "the OMS AI was built on Azure AI Foundry (ACH-018); the record does not tie Python/FastAPI to it",
        "claim_terms": ["Python", "FastAPI", "AI"],
        "correction": {"type": "content", "mode": "replace", "file": "answers.md",
                       "old": "the AI workflow layer used Python, FastAPI and LangGraph.",
                       "new": "the OMS assistants were built on Azure AI Foundry (ACH-018)."}}]
    return blocks


def test_a_wrong_claim_named_once_brings_every_outward_instance_into_the_same_round(tmp_path):
    """Live: review-8 named the Python/FastAPI-in-the-OMS-AI mix in one answers.md note; review-9 found the same mix in
    the letter and the recruiter message, one round later. The same review must now list them all."""
    app = mixed_application(tmp_path)
    p = aggregate(app, note_only_finding(passing()), 8)
    assert p.returncode == 0, p.stderr
    review = json.loads(p.stdout)
    assert review["verdict"] == "NOT_APPROVED"
    swept = [c for c in review["corrections"] if c.get("claim_terms") == ["Python", "FastAPI", "AI"]]
    assert len(swept) == 1, review["corrections"]
    files = {row["file"] for row in swept[0]["instances"]}
    assert files == {"cover_letter.md", "recruiter_message.md"}, swept[0]
    assert "Python and FastAPI for the AI and automation layer" in swept[0]["instructions"]
    assert "Python and FastAPI in the AI layer" in swept[0]["instructions"]


def test_corrections_that_cover_every_instance_add_nothing(tmp_path):
    """When the lens already names every instance, the sweep adds no correction of its own."""
    app = mixed_application(tmp_path)
    blocks = note_only_finding(passing())
    for file, old in (("cover_letter.md", "I used Python and FastAPI for the AI and automation layer."),
                      ("recruiter_message.md", "I used Python and FastAPI in the AI layer")):
        blocks["truthfulness"]["findings"].append({
            "kind": "draft", "check": "tools", "location": file, "text": old, "problem": "same mix",
            "claim_terms": ["Python", "FastAPI", "AI"],
            "correction": {"type": "content", "mode": "replace", "file": file, "old": old,
                           "new": "I also built AI workflows with Python and FastAPI in the same role."}})
    review = json.loads(aggregate(app, blocks, 8).stdout)
    assert not [c for c in review["corrections"] if c.get("mode") == "instruction" and c.get("claim_terms")]
    assert len(review["corrections"]) == 2  # the two outward ones; the note is fixed in place


def test_a_wrong_claim_without_claim_terms_still_aggregates_and_says_it_was_not_swept(tmp_path):
    """The lens schema requires claim_terms; a block that still lacks it must not stop the review (bug 18)."""
    app = mixed_application(tmp_path)
    blocks = note_only_finding(passing())
    del blocks["truthfulness"]["findings"][0]["claim_terms"]
    p = aggregate(app, blocks, 8)
    assert p.returncode == 0, p.stderr
    assert any("no claim_terms" in w for w in json.loads(p.stdout)["warnings"])


def test_a_true_sentence_with_the_same_words_never_holds_the_application_back(tmp_path):
    """The terms find candidates: the corrected sentence ("in my previous role I also built AI workflows with Python
    and FastAPI", ACH-008) holds the same words. The sweep lists it for the writer, and never makes the verdict."""
    app = project(tmp_path)
    (app / "cover_letter.md").write_text("In my previous role I also built AI workflows with Python and FastAPI.\n",
                                         encoding="utf-8")
    (app / "answers.md").write_text(ANSWERS, encoding="utf-8")
    blocks = note_only_finding(passing())  # a note correction: applied in place, never blocks
    review = json.loads(aggregate(app, blocks, 9).stdout)
    assert review["verdict"] == "NOT_APPROVED"  # unjudged: the sentence holds the claim's words
    blocks["truthfulness"]["findings"][0]["true_instances"] = [
        "In my previous role I also built AI workflows with Python and FastAPI."]
    review = json.loads(aggregate(app, blocks, 9).stdout)
    assert review["verdict"] == "APPROVED", review["corrections"]  # judged true once: never loops


def test_contact_data_in_a_swept_sentence_is_masked_not_a_review_failure(tmp_path):
    app = mixed_application(tmp_path)
    (app / "recruiter_message.md").write_text("I used Python and FastAPI in the AI layer; write to jane.doe@example.com "
                                              "for details.\n", encoding="utf-8")
    p = aggregate(app, note_only_finding(passing()), 8)
    assert p.returncode == 0, p.stderr
    assert "[contact]" in p.stdout and "jane.doe" not in p.stdout


def test_the_writer_sweep_lists_every_file_that_makes_the_claim(tmp_path):
    app = mixed_application(tmp_path)
    p = py(SWEEP, app, "--terms", "Python", "FastAPI", "AI", "--json")
    assert p.returncode == 0, p.stderr
    rows = json.loads(p.stdout)["instances"]
    assert {(r["file"], r["outward"]) for r in rows} == {
        ("cover_letter.md", True), ("recruiter_message.md", True), ("answers.md", False)}


# --- 16. an e-mailed code goes to jobs-inbox, never straight to a kit -------------------------------------------

GREENHOUSE_MAIL = ("Hi,\n\nCopy and paste this code into the security code field on your application:\n\n"
                   "X7kQ2mZp\n\nThis code expires in 10 minutes. Order reference ABC12345.\n")


def test_greenhouses_eight_character_code_is_read_from_the_mail():
    """extract_code.py read only 4-8 digit codes, so the 8-character Greenhouse code could never be returned."""
    p = py(EXTRACT, "--site", "greenhouse-mail.io", "--json", stdin=GREENHOUSE_MAIL)
    data = json.loads(p.stdout)
    assert p.returncode == 0 and data["code"] == "X7kQ2mZp" and data["source"] == "code", data
    p = py(EXTRACT, "--site", "greenhouse-mail.io", "--json", stdin="Your security code is: Hq4T9wLb")
    assert json.loads(p.stdout)["code"] == "Hq4T9wLb"


@pytest.mark.parametrize("mail", [
    "Welcome applicant, thanks for applying to the Senior AI Engineer role.",
    "Your order ABC12345 has shipped.",
    "Security code\n\nX7kQ2mZp\n\nIgnore that. Your security code is: Hq4T9wLb",
    "Your verification code is WELCOME to the team",
    "Use code: CONFIRM to proceed",
    "Verification code\nAPPLICANT",
    "Security code\n\nWelcome1",
])
def test_words_references_and_two_codes_are_never_returned(mail):
    p = py(EXTRACT, "--site", "greenhouse-mail.io", "--json", stdin=mail)
    assert json.loads(p.stdout)["code"] is None, p.stdout


@pytest.mark.parametrize("mail,code", [
    ("Security code: aBcDeFgH", "aBcDeFgH"),  # 8 letters, mixed case: Greenhouse's shape without a digit
    ("Copy and paste this code into the security code field on your application: aB3dE9fG\n\nReference: ABC12345",
     "aB3dE9fG"),
    ("Security code: aB3dE9fG\nCandidate: Gabriel9", "aB3dE9fG"),
])
def test_a_reference_line_after_the_code_does_not_make_it_ambiguous(mail, code):
    p = py(EXTRACT, "--site", "greenhouse-mail.io", "--json", stdin=mail)
    assert json.loads(p.stdout)["code"] == code, p.stdout


@pytest.mark.parametrize("reason", [
    "Apply by e-mail: include the job code ENG-42 in the subject line",
    "Application needs a source code sample sent by email",
    "Form needs a login with an email address and a promo code",
])
def test_a_kit_whose_reason_only_mentions_codes_and_email_is_not_held_for_a_code_request(tmp_path, reason):
    app = project(tmp_path)
    path = factored_record(app)
    record = json.loads(path.read_text())
    record["reason"] = reason
    path.write_text(json.dumps(record))
    p = py(CHECK, path)
    assert p.returncode == 0, p.stderr


@pytest.mark.parametrize("result", ["no code: none", "code: nothing", "code: pending", "no code yet (15 minutes)"])
def test_code_wait_never_reads_a_word_as_the_code(result):
    sys.path.insert(0, str(CODE_WAIT.parent))
    import code_wait  # noqa: E402
    assert code_wait.read_result(result)["outcome"] == "no_code"
    assert code_wait.read_result("code: X7kQ2mZp") == {"outcome": "code", "code": "X7kQ2mZp"}


def factored_record(app: Path, **extra) -> Path:
    (app / "kit.md").write_text("# Manual kit\n", encoding="utf-8")
    record = {"id": ID, "result": "NOT_POSSIBLE", "method": "captcha", "filled_fields": [],
              "pending_questions": [], "screenshots": [], "manual_kit": "application/kit.md",
              "reason": "Submit triggers an e-mail verification code (8 characters, 'confirm you're a human') that "
                        "must be typed before Greenhouse accepts the application. Not sent.", **extra}
    path = app / "submission.json"
    path.write_text(json.dumps(record), encoding="utf-8")
    return path


def test_a_kit_for_an_emailed_code_is_refused_until_jobs_inbox_was_asked(tmp_path):
    """Live: the applier wrote this exact NOT_POSSIBLE and a 10-round approved kit was not sent."""
    app = project(tmp_path)
    p = py(CHECK, factored_record(app))
    assert p.returncode == 1 and "code_request" in p.stderr, p.stderr
    p = py(CHECK, factored_record(app, code_request={"card": "t_1234abcd", "outcome": "no_code"}))
    assert p.returncode == 0, p.stderr
    p = py(CHECK, factored_record(app, code_request={"card": "t_1234abcd", "outcome": "code"}))
    assert p.returncode == 1, "a code that arrived is typed, never a kit"


@needs_hermes
def test_code_wait_files_the_inbox_card_and_returns_the_code_it_completes_with(tmp_path):
    """The real kanban: code_wait files the Mode: CODE card for jobs-inbox, and the code jobs-inbox completes it with
    comes back to the applier. Gmail is checked first, so a fake connector answers that one call."""
    root = temp_root(tmp_path)
    (root / "profiles" / "jobs-inbox").mkdir(parents=True)
    env = env_for(root)
    assert subprocess.run([HERMES, "kanban", "boards", "create", "jobs"], env=env, capture_output=True,
                          text=True, timeout=120).returncode == 0
    shim = tmp_path / "bin" / "hermes"
    shim.parent.mkdir()
    shim.write_text(f"#!/bin/sh\nif [ \"$3\" = connectors ]; then echo 'gmail  work  active'; exit 0; fi\n"
                    f"exec {HERMES} \"$@\"\n")
    shim.chmod(0o755)
    folder = tmp_path / "project"
    folder.mkdir()
    proc = subprocess.Popen([sys.executable, "-B", str(CODE_WAIT), "--project", str(folder), "--opening", ID,
                             "--site", "greenhouse-mail.io", "--timeout", "90", "--poll", "1", "--board", "jobs",
                             "--hermes-bin", str(shim), "--json"], env=env, stdout=subprocess.PIPE, text=True)
    card = ""
    for _ in range(60):
        listed = subprocess.run([HERMES, "kanban", "--board", "jobs", "list", "--json"], env=env, capture_output=True,
                                text=True, timeout=60)
        rows = json.loads(listed.stdout or "[]")
        if rows:
            card = rows[0]["id"]
            break
        subprocess.run(["sleep", "1"])
    assert card, "code_wait filed no card"
    shown = json.loads(subprocess.run([HERMES, "kanban", "--board", "jobs", "show", card, "--json"], env=env,
                                      capture_output=True, text=True, timeout=60).stdout)
    assert shown["task"]["assignee"] == "jobs-inbox" and "Mode: CODE" in shown["task"]["body"]
    assert "greenhouse-mail.io" in shown["task"]["body"]
    subprocess.run([HERMES, "kanban", "--board", "jobs", "complete", card, "--result", "code: X7kQ2mZp"], env=env,
                   capture_output=True, text=True, timeout=60)
    out, _ = proc.communicate(timeout=120)
    assert proc.returncode == 0, out
    assert json.loads(out) == {"outcome": "code", "code": "X7kQ2mZp", "card": card}


def test_code_wait_says_unavailable_at_once_when_the_inbox_bot_is_missing(tmp_path):
    root = tmp_path / "root"
    (root / "profiles").mkdir(parents=True)
    folder = tmp_path / "project"
    folder.mkdir()
    env = {**os.environ, "HERMES_HOME": str(root)}
    p = py(CODE_WAIT, "--project", folder, "--opening", ID, "--site", "greenhouse-mail.io", "--json", env=env)
    out = json.loads(p.stdout)
    assert p.returncode == 3 and out["outcome"] == "unavailable" and "jobs-inbox" in out["reason"]


# --- 17. the language option is the record's level, never a label above it -------------------------------------

def test_the_applier_gets_limited_working_proficiency_for_a_b2(tmp_path):
    """Live: the applier picked "Professional Working Proficiency" (ILR 3, about C1) for a B2 record."""
    project(tmp_path)
    p = py(FORM_ANSWER, "language", "--project", tmp_path, "--language", "English", "--options",
           "|".join(FORM_OPTIONS), "--json")
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["answer"] == "Limited Working Proficiency" and out["declared"] == "B2"
    p = py(FORM_ANSWER, "language", "--project", tmp_path, "--language", "inglés", "--options",
           "Basic|Intermediate|Upper-intermediate (B2)|Advanced|Fluent", "--json")
    assert json.loads(p.stdout)["answer"] == "Upper-intermediate (B2)"


def test_an_undeclared_language_is_a_question_not_a_guess(tmp_path):
    project(tmp_path)
    p = py(FORM_ANSWER, "language", "--project", tmp_path, "--language", "German", "--options", "|".join(FORM_OPTIONS))
    assert p.returncode == 1 and "German" in p.stderr


def test_the_review_blocks_an_overstated_language_label_even_in_a_note(tmp_path):
    """The Factored kit told the applier to pick "Professional Working Proficiency"; the Truelogic reviewer had ruled
    that label overstates B2, and nothing carried the ruling to the next application."""
    app = project(tmp_path)
    (app / "answers.md").write_text("## 6. What is your English level?\n\n[FIELD]\nB2 (upper-intermediate).\n"
                                    "[/FIELD]\n\nNOTE TO SELF: pick \"Professional Working Proficiency\".\n",
                                    encoding="utf-8")
    review = json.loads(aggregate(app, passing(), 2).stdout)
    assert review["verdict"] == "NOT_APPROVED"
    assert any("Professional Working" in c.get("instructions", "") for c in review["corrections"]), review
    (app / "answers.md").write_text("## 6. What is your English level?\n\n[FIELD]\nB2 (upper-intermediate).\n"
                                    "[/FIELD]\n\nNOTE TO SELF: pick \"Limited Working Proficiency\"; never "
                                    "\"Professional Working Proficiency\".\n", encoding="utf-8")
    assert json.loads(aggregate(app, passing(), 2).stdout)["verdict"] == "APPROVED"


# --- 18. a malformed lens block is fixed inside the child, and the run has children left to re-run it ----------

# The block the live truthfulness child returned (field names claim/issue instead of text/problem).
MALFORMED = {"verdict": "FAIL", "grounding": {"sources": ["achievements.yaml", "profile.md"]}, "company_claims": [],
             "findings": [{"kind": "draft", "check": "grounding", "location": "answers.md field 12",
                           "claim": "I live in Colombia and want to keep working remotely.",
                           "issue": "no source says how the candidate works now", "file": "answers.md",
                           "sources_checked": ["profile.md"],
                           "correction": {"type": "content", "mode": "replace", "file": "answers.md",
                                          "old": "keep working remotely", "new": "work remotely"}}]}


def test_the_lens_schema_the_reviewer_passes_rejects_the_live_malformed_block():
    """The reviewer passed a hand-written schema with `findings: {items: {type: object}}`, which accepted claim/issue;
    Hermes's one correction turn never fired. The schema printed by --schema refuses it, naming the fields."""
    jsonschema = pytest.importorskip("jsonschema")
    p = py(AGG, "--schema", "truthfulness")
    assert p.returncode == 0, p.stderr
    schema = json.loads(p.stdout)
    jsonschema.Draft202012Validator.check_schema(schema)
    errors = [e.message for e in jsonschema.Draft202012Validator(schema).iter_errors(MALFORMED)]
    assert any("'text' is a required property" in e for e in errors), errors
    assert any("'problem' is a required property" in e for e in errors), errors
    fixed = json.loads(json.dumps(MALFORMED))
    item = fixed["findings"][0]
    item["text"], item["problem"] = item.pop("claim"), item.pop("issue")
    item["claim_terms"] = ["keep", "working remotely"]
    assert not list(jsonschema.Draft202012Validator(schema).iter_errors(fixed))


def test_every_lens_schema_accepts_the_shapes_the_aggregator_accepts(tmp_path):
    """No lens block the aggregator takes is refused by its schema (a schema stricter than the script would loop)."""
    jsonschema = pytest.importorskip("jsonschema")
    blocks = passing()
    for lens in LENSES:
        schema = json.loads(py(AGG, "--schema", lens).stdout)
        assert not list(jsonschema.Draft202012Validator(schema).iter_errors(blocks[lens])), lens


def test_the_reviewer_manifest_asks_for_a_delegate_budget_for_five_lenses_and_reruns():
    """A kanban worker is a `chat -q` one-shot: Hermes allows it delegation.oneshot_max_children children in total
    (default 2). The reviewer spent both on its lenses and could not re-run the malformed one. squadctl writing the
    key into the profile is tested in test_squadctl.py (test_delegation_max_children_sets_the_one_shot_budget)."""
    spec = yaml.safe_load((REPO / "squads" / "jobs" / "squad.yaml").read_text())
    assert spec["bots"]["jobs-reviewer"]["delegation"]["max_children"] >= len(LENSES) + 2


def test_the_installed_hermes_still_caps_one_shot_children_with_that_key():
    """The key squadctl writes must be the one the installed Hermes reads."""
    if not HERMES:
        pytest.skip("hermes not on PATH")
    src = Path(subprocess.run([HERMES, "--version"], capture_output=True, text=True).stdout.split(
        "Install directory:")[-1].strip().splitlines()[0])
    text = (src / "tools" / "delegate_tool_config.py").read_text(encoding="utf-8")
    assert '"oneshot_max_children"' in text


# --- 19. "working remotely" needs the current job's work mode, not the search preference --------------------------

def test_the_review_blocks_working_remotely_when_the_record_does_not_say_so(tmp_path):
    """Live: "working remotely from Colombia" went into the CV summary in the first draft and four reviews approved
    it as a profile_consistency warning; profile.md work_mode is what the user searches for."""
    app = project(tmp_path)
    (app / "cv_content.json").write_text(json.dumps({"summary": {
        "text": "Senior Software Engineer and Technical Lead working remotely from Colombia.",
        "achievements": ["ACH-001"]}}), encoding="utf-8")
    (app / "answers.md").write_text("## 12. Priorities\n\n[FIELD]\n3. Remote work. I live in Colombia and want to "
                                    "keep working remotely.\n[/FIELD]\n", encoding="utf-8")
    review = json.loads(aggregate(app, passing(), 4).stdout)
    assert review["verdict"] == "NOT_APPROVED"
    where = {c["location"] for c in review["corrections"] if "works remotely now" in c.get("instructions", "")}
    assert where == {"cv_content.json", "answers.md"}, review["corrections"]


@pytest.mark.parametrize("text", [
    "Acme is a remote-based company hiring engineers.",
    "The team works remotely from Lisbon and Madrid, and I would love to join them.",
    "Led a team working remotely across three time zones at Example Labs (2019-2022).",
    "At my previous role I was working remotely from Bogotá until 2023.",
    "I am comfortable working remotely.",
    "Experience managing engineers working remotely.",
    "Eager to start working remotely from day one.",
    "Busco trabajar de forma remota.",
])
def test_sentences_that_are_not_about_the_current_job_are_not_claims(text):
    sys.path.insert(0, str(CONTRACT))
    import jobs_common as jc  # noqa: E402
    assert jc.remote_now_claims(text) == [], text


@pytest.mark.parametrize("text", [
    "Actualmente trabajo de forma remota desde Colombia.",
    "Sigo trabajando en remoto desde Colombia.",
    "I work remotely for a US company.",
    "I'm currently working remotely.",
])
def test_present_tense_remote_claims_in_both_languages_are_caught(text):
    sys.path.insert(0, str(CONTRACT))
    import jobs_common as jc  # noqa: E402
    assert jc.remote_now_claims(text), text


@pytest.mark.parametrize("text,flagged", [
    ("English (B2), Spanish (native)", []),
    ("Hablo inglés (B2) y español (nativo)", []),
    ("English: Limited Working Proficiency; Spanish: Native or Bilingual Proficiency", []),
    ("Spanish: Native or bilingual proficiency. English: Professional working proficiency", ["Professional working"]),
    ("Inglés: Competencia profesional", ["Competencia profesional"]),
])
def test_each_language_label_is_bound_to_its_own_language(text, flagged):
    sys.path.insert(0, str(CONTRACT))
    import jobs_common as jc  # noqa: E402
    hits = jc.language_label_overclaims(text, {"es": "C2", "en": "B2"})
    assert [h["label"] for h in hits] == flagged, hits


def test_a_wish_or_a_recorded_remote_job_passes(tmp_path):
    app = project(tmp_path, ACHIEVEMENTS.replace("from: 2026-06, to: current}",
                                                 "from: 2026-06, to: current, work_mode: remote}"))
    (app / "cv_content.json").write_text(json.dumps({"summary": {
        "text": "Technical Lead working remotely from Colombia.", "achievements": ["ACH-001"]}}), encoding="utf-8")
    assert json.loads(aggregate(app, passing(), 4).stdout)["verdict"] == "APPROVED"
    app2 = project(tmp_path / "b")
    (app2 / "answers.md").write_text("[FIELD]\nI live in Colombia and want to work remotely.\n[/FIELD]\n",
                                     encoding="utf-8")
    assert json.loads(aggregate(app2, passing(), 4).stdout)["verdict"] == "APPROVED"


def test_the_renderer_refuses_the_claim_in_the_first_draft(tmp_path):
    """The writer produced it in the first draft: the render report now blocks it before any review."""
    app = project(tmp_path)
    content = app / "cv_content.json"
    content.write_text(json.dumps({"language": "en", "summary": {
        "text": "Senior Software Engineer and Technical Lead working remotely from Colombia.",
        "achievements": ["ACH-001"]}, "experience": [], "skills": [], "education": [], "languages": []}),
        encoding="utf-8")
    out = tmp_path / "render"
    p = py(RENDER, "--content", content, "--output", out, "--achievements", tmp_path / "achievements.yaml",
           "--profile", tmp_path / "profile.md", "--engine", "auto", "--json", timeout=300)
    report = json.loads((out / "render_report.json").read_text())
    codes = [d["code"] for d in report["defects"]]
    assert "work_mode_unbacked" in codes, (p.stderr[-500:], codes)


def test_validate_profile_accepts_work_mode_on_an_experience_and_refuses_a_typo(tmp_path):
    validate = CONTRACT / "validate_profile.py"
    project(tmp_path, ACHIEVEMENTS.replace("to: current}", "to: current, work_mode: remot}"))
    p = py(validate, "--project", tmp_path, "--json")
    assert "work_mode" in p.stdout, p.stdout[-800:]
