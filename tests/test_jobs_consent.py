"""Consent and pre-submit gate for the jobs squad: a submit needs the user's literal words, or a standing yes.

Pins check_submission.py: a SUBMITTED record needs application/consent.json naming this opening, dated not before the
review approval — or, under `auto_apply: auto`, the standing consent in profile.md with the fit score, the eligibility
gate and the daily caps. profile.md auto_apply and review_before_submit are enforced in code, not in prose; --gate
decides before the first click. Each test runs the real script (subprocess). Fictional people only.
"""
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest
from test_jobs_profile import PROFILE as FULL_PROFILE
from test_jobs_profile import edit as edit_profile
from test_jobs_profile import findings as profile_findings
from test_jobs_profile import keyed as keyed_finding
from test_jobs_profile import write_project as write_full_project

REPO = Path(__file__).resolve().parents[1]
SUBMIT = REPO / "squads" / "jobs" / "skills" / "submitting-applications" / "scripts"
CHECK = SUBMIT / "check_submission.py"
RECORD = SUBMIT / "record_submission.py"
OPENING_ID = "JOB-20260925-acme-data-analyst"


def make_application(folder, opening_id=OPENING_ID, apply_url="https://jobs.lever.co/acme/2f1c9a7e-5b1d-4c2a-9e8f-1a2b3c4d5e6f/apply"):
    app = folder / "openings" / opening_id / "application"
    app.mkdir(parents=True)
    (app.parent / "opening.md").write_text(f"---\nid: {opening_id}\ncompany: Acme\napply_url: {apply_url}\n---\nPosting.\n",
                                           encoding="utf-8")
    for name in ("before.png", "confirmation.png"):
        (app / name).write_bytes(PNG)
    (app / "kit.md").write_text("Answers ready to copy.\n", encoding="utf-8")
    (app / "cv_ats.pdf").write_bytes(b"%PDF-1.4 fictional CV\n")
    return app


PNG = b"\x89PNG\r\n\x1a\n"
PROJECT_PROFILE = "---\nname: Example\nauto_apply: try\nreview_before_submit: false\n---\nFictional project.\n"
USER_WORDS = "Yes, apply to this one."


def approve(app, day="2026-10-20"):
    """A finished review: review-1.json APPROVED and a ready line in status.json, both dated day."""
    opening = app.parent
    (opening / "review-1.json").write_text(json.dumps({"verdict": "APPROVED", "status": "ready"}), encoding="utf-8")
    (opening / "status.json").write_text(json.dumps({"history": [
        {"date": f"{day}T09:00", "status": "in_review", "by": "jobs-reviewer"},
        {"date": f"{day}T09:05", "status": "ready", "by": "jobs-reviewer"}], "status": "ready"}), encoding="utf-8")


def kit_hash(app):
    """What the manager runs when the user says apply: check_submission.py --kit-hash on application/."""
    proc = subprocess.run([sys.executable, str(CHECK), "--kit-hash", str(app)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def consent(app, by="Ana Example", words=USER_WORDS, day="2026-10-20", opening_id=OPENING_ID, **extra):
    """The manager's consent.json: the user's literal words for this one opening, bound to the kit as it is now."""
    data = {"opening_id": opening_id, "by": by, "words": words, "date": day, "kit_sha256": kit_hash(app), **extra}
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


# A SUBMITTED record without consent.json (no literal words from the user) is refused, whatever the profile says.

def test_submit_without_the_users_words_is_refused(tmp_path):
    app = ready_to_submit(tmp_path)
    (app / "consent.json").unlink()
    proc = check(app, submitted())
    assert proc.returncode == 1
    assert "consent.json" in proc.stderr and "user's words" in proc.stderr


def test_consent_for_another_opening_does_not_cover_this_one(tmp_path):
    app = ready_to_submit(tmp_path)
    consent(app, opening_id="JOB-20260925-other-role")
    proc = check(app, submitted())
    assert proc.returncode == 1 and "consent covers one opening" in proc.stderr


def test_consent_dated_before_the_review_approval_is_refused(tmp_path):
    app = ready_to_submit(tmp_path)
    consent(app, day="2026-10-19")  # approval is 2026-10-20
    proc = check(app, submitted())
    assert proc.returncode == 1 and "before the review approval" in proc.stderr


def test_consent_with_empty_words_is_refused(tmp_path):
    app = ready_to_submit(tmp_path)
    consent(app, words="  ")
    assert check(app, submitted()).returncode == 1


def test_consent_words_with_contact_data_are_refused(tmp_path):
    app = ready_to_submit(tmp_path)
    consent(app, words="Apply, write to ana@example.com")
    proc = check(app, submitted())
    assert proc.returncode == 1 and "contact data in consent.json" in proc.stderr


def test_submit_without_an_approved_review_is_refused(tmp_path):
    app = ready_to_submit(tmp_path)
    (app.parent / "review-1.json").unlink()
    proc = check(app, submitted())
    assert proc.returncode == 1 and "approved review" in proc.stderr


def test_a_review_still_in_fix_is_not_an_approval(tmp_path):
    app = ready_to_submit(tmp_path)
    (app.parent / "review-1.json").write_text(json.dumps({"verdict": "FIX", "status": "in_review"}), encoding="utf-8")
    proc = check(app, submitted())
    assert proc.returncode == 1 and "approved review" in proc.stderr


def test_auto_apply_never_refuses_every_submit(tmp_path):
    app = ready_to_submit(tmp_path)
    project_profile(app, PROJECT_PROFILE.replace("auto_apply: try", "auto_apply: never"))
    proc = check(app, submitted())
    assert proc.returncode == 1 and "auto_apply: never" in proc.stderr
    kit = {**submitted(), "result": "NOT_POSSIBLE", "method": "other", "filled_fields": [], "screenshots": [],
           "reason": "auto_apply never", "manual_kit": "application/kit.md"}
    assert check(app, kit).returncode == 0


def test_a_misspelt_auto_apply_is_refused_not_read_as_try(tmp_path):
    app = ready_to_submit(tmp_path)
    project_profile(app, PROJECT_PROFILE.replace("auto_apply: try", "auto_apply: nevr"))
    proc = check(app, submitted())
    assert proc.returncode == 1 and "must be never, ask, try or auto" in proc.stderr


def test_a_profile_that_does_not_parse_refuses_the_submit(tmp_path):
    app = ready_to_submit(tmp_path)
    project_profile(app, "---\nauto_apply: [unclosed\n---\nBroken.\n")
    proc = check(app, submitted())
    assert proc.returncode == 1 and "does not parse" in proc.stderr


def test_review_before_submit_needs_the_screenshot_approval(tmp_path):
    app = ready_to_submit(tmp_path)
    project_profile(app, PROJECT_PROFILE.replace("review_before_submit: false", "review_before_submit: true"))
    proc = check(app, submitted())
    assert proc.returncode == 1 and "screenshot" in proc.stderr
    consent(app, screenshot_approval={"by": "Ana Example", "words": "looks right, send it",
                                      "date": "2026-10-20", "screenshot": "before.png"})
    proc = check(app, submitted())
    assert proc.returncode == 0, proc.stderr


def test_a_screenshot_approval_dated_before_the_approval_is_refused(tmp_path):
    app = ready_to_submit(tmp_path)
    project_profile(app, PROJECT_PROFILE.replace("review_before_submit: false", "review_before_submit: true"))
    consent(app, screenshot_approval={"by": "Ana Example", "words": "send it", "date": "2026-10-19",
                                      "screenshot": "before.png"})
    proc = check(app, submitted())
    assert proc.returncode == 1 and "before the review approval" in proc.stderr


def test_a_screenshot_approval_naming_a_missing_image_is_refused(tmp_path):
    app = ready_to_submit(tmp_path)
    project_profile(app, PROJECT_PROFILE.replace("review_before_submit: false", "review_before_submit: true"))
    consent(app, screenshot_approval={"by": "Ana Example", "words": "send it", "date": "2026-10-20",
                                      "screenshot": "not-taken.png"})
    proc = check(app, submitted())
    assert proc.returncode == 1 and "does not exist" in proc.stderr


def test_gate_is_open_only_with_consent_and_approval(tmp_path):
    app = ready_to_submit(tmp_path)
    gate = [sys.executable, str(CHECK), str(app / "submission.json"), "--gate"]
    proc = subprocess.run(gate, capture_output=True, text=True)
    assert proc.returncode == 0 and "gate: open" in proc.stdout, proc.stderr
    (app / "consent.json").unlink()
    proc = subprocess.run(gate, capture_output=True, text=True)
    assert proc.returncode == 1 and "consent.json" in proc.stderr


def test_gate_runs_before_submit_only_with_the_flag(tmp_path):
    app = ready_to_submit(tmp_path)
    project_profile(app, PROJECT_PROFILE.replace("review_before_submit: false", "review_before_submit: true"))
    gate = [sys.executable, str(CHECK), str(app / "submission.json"), "--gate"]
    assert subprocess.run(gate, capture_output=True, text=True).returncode == 0
    proc = subprocess.run([*gate, "--before-submit"], capture_output=True, text=True)
    assert proc.returncode == 1 and "screenshot" in proc.stderr
    consent(app, screenshot_approval={"by": "Ana Example", "words": "send it", "date": "2026-10-20",
                                      "screenshot": "before.png"})
    assert subprocess.run([*gate, "--before-submit"], capture_output=True, text=True).returncode == 0


def test_auto_apply_ask_needs_review_before_submit_true(tmp_path):
    # profile-files.md: ask fills the form, stops, and submits only after the user approves the screenshot.
    app = ready_to_submit(tmp_path)
    project_profile(app, PROJECT_PROFILE.replace("auto_apply: try", "auto_apply: ask"))
    proc = check(app, submitted())
    assert proc.returncode == 1 and "auto_apply: ask needs review_before_submit: true" in proc.stderr


def test_auto_apply_ask_submits_only_after_the_screenshot_approval(tmp_path):
    app = ready_to_submit(tmp_path)
    project_profile(app, "---\nauto_apply: ask\nreview_before_submit: true\n---\nFictional project.\n")
    gate = [sys.executable, str(CHECK), str(app / "submission.json"), "--gate", "--before-submit"]
    proc = subprocess.run(gate, capture_output=True, text=True)
    assert proc.returncode == 1 and "screenshot_approval" in proc.stderr
    consent(app, screenshot_approval={"by": "Ana Example", "words": "yes, send it", "date": "2026-10-20",
                                      "screenshot": "before.png"})
    assert subprocess.run(gate, capture_output=True, text=True).returncode == 0
    assert check(app, submitted()).returncode == 0


def test_an_unknown_auto_apply_value_is_refused_by_the_gate(tmp_path):
    app = ready_to_submit(tmp_path)
    project_profile(app, PROJECT_PROFILE.replace("auto_apply: try", "auto_apply: yes"))
    proc = subprocess.run([sys.executable, str(CHECK), str(app / "submission.json"), "--gate"],
                          capture_output=True, text=True)
    assert proc.returncode == 1 and "must be never, ask, try or auto" in proc.stderr



# --- the gate follows the latest review and status; the consent binds to the kit the user saw ---------------------

def run_gate(app):
    return subprocess.run([sys.executable, str(CHECK), str(app / "submission.json"), "--gate"],
                          capture_output=True, text=True)


def write_history(app, lines):
    (app.parent / "status.json").write_text(json.dumps({"history": lines, "status": lines[-1]["status"]}),
                                            encoding="utf-8")


def test_a_fix_round_after_an_approval_closes_the_gate(tmp_path):
    # review-1 APPROVED, then a change round: review-2 FIX and the latest line in_review. Only the latest review counts.
    app = ready_to_submit(tmp_path)
    assert run_gate(app).returncode == 0
    (app.parent / "review-2.json").write_text(json.dumps({"verdict": "FIX", "status": "in_review"}), encoding="utf-8")
    write_history(app, [{"date": "2026-10-20T09:05", "status": "ready", "by": "jobs-reviewer"},
                        {"date": "2026-10-21T09:00", "status": "in_review", "by": "jobs-reviewer",
                         "note": "review-2 FIX"}])
    proc = run_gate(app)
    assert proc.returncode == 1 and "latest review-2.json is 'FIX'" in proc.stderr, proc.stderr
    record = check(app, submitted())
    assert record.returncode == 1 and "approved review" in record.stderr, record.stderr


def test_a_change_review_with_another_file_name_still_closes_the_gate(tmp_path):
    # Real run: the change round was saved as review-c1.json, beside an older review-2.json. The gate must judge the
    # newest review on disk, whatever its name, so a NOT_APPROVED change review can never hide behind an approval.
    import os
    app = ready_to_submit(tmp_path)
    assert run_gate(app).returncode == 0
    newer = app.parent / "review-c1.json"
    newer.write_text(json.dumps({"verdict": "NOT_APPROVED", "status": "not_approved"}), encoding="utf-8")
    later = max(p.stat().st_mtime for p in app.parent.glob("review-*.json")) + 60
    os.utime(newer, (later, later))
    proc = run_gate(app)
    assert proc.returncode == 1 and "latest review-c1.json is 'NOT_APPROVED'" in proc.stderr, proc.stderr


def test_a_skipped_opening_closes_the_gate_whatever_the_older_consent_says(tmp_path):
    # The user declined: the latest line is skipped. A consent.json from an earlier apply does not open the gate.
    app = ready_to_submit(tmp_path)
    write_history(app, [{"date": "2026-10-20T09:05", "status": "ready", "by": "jobs-reviewer"},
                        {"date": "2026-10-20T10:00", "status": "delivered", "by": "jobs"},
                        {"date": "2026-10-22T10:00", "status": "skipped", "by": "jobs"}])
    proc = run_gate(app)
    assert proc.returncode == 1 and "'skipped'" in proc.stderr, proc.stderr


def test_a_later_approval_needs_a_consent_dated_after_it(tmp_path):
    app = ready_to_submit(tmp_path)
    write_history(app, [{"date": "2026-10-20T09:05", "status": "ready", "by": "jobs-reviewer"},
                        {"date": "2026-10-22T09:05", "status": "ready", "by": "jobs-reviewer"}])
    proc = run_gate(app)
    assert proc.returncode == 1 and "before the review approval 2026-10-22" in proc.stderr, proc.stderr
    consent(app, day="2026-10-22")
    assert run_gate(app).returncode == 0


def test_a_moved_consent_date_is_recorded_as_a_flag_after_the_gate(tmp_path):
    # The gate opened on the consent of 2026-10-20; a second approval on 2026-10-22 makes that date "before the
    # approval". The submit happened, so the record keeps it with the rule it went in over.
    app = ready_to_submit(tmp_path)
    (app.parent / "opening.md").write_text(
        f"---\nid: {OPENING_ID}\ncompany: Acme\nrole: Analyst\n"
        f"apply_url: https://jobs.lever.co/acme/2f1c9a7e-5b1d-4c2a-9e8f-1a2b3c4d5e6f/apply\n---\nPosting.\n",
        encoding="utf-8")
    assert run_gate(app).returncode == 0, "control: the gate opened for this opening, so it wrote gate.json"
    assert json.loads((app / "gate.json").read_text(encoding="utf-8"))["opening_id"] == OPENING_ID
    write_history(app, [{"date": "2026-10-20T09:05", "status": "ready", "by": "jobs-reviewer"},
                        {"date": "2026-10-22T09:05", "status": "ready", "by": "jobs-reviewer"}])
    assert check(app, submitted()).returncode == 1, "the plain check still refuses the moved date"
    proc = subprocess.run([sys.executable, str(RECORD), str(app / "submission.json"), "--json"],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["note"] == "recorded over the gate: consent.date", payload
    assert payload["status"] == "applied"


@pytest.mark.parametrize("by", ["jobs-applier", "Jobs-Applier", "jobs-writer", "jobs"])
def test_a_bot_profile_cannot_write_the_consent(tmp_path, by):
    # The applier wrote {by: jobs-applier, words: ok}: only the user's own name is consent.
    app = ready_to_submit(tmp_path)
    consent(app, by=by, words="ok")
    proc = run_gate(app)
    assert proc.returncode == 1 and "names the bot profile" in proc.stderr, proc.stderr


def test_a_change_to_the_documents_after_the_consent_closes_the_gate(tmp_path):
    # Consent was given, then a change round rewrote the CV and was approved the same day.
    app = ready_to_submit(tmp_path)
    assert run_gate(app).returncode == 0, "control: the gate is open while the documents are the ones the user saw"
    (app / "cv_ats.pdf").write_bytes(b"%PDF-1.4 the CV after the change\n")
    (app.parent / "review-2.json").write_text(json.dumps({"verdict": "APPROVED", "status": "ready"}),
                                              encoding="utf-8")
    write_history(app, [{"date": "2026-10-20T09:05", "status": "ready", "by": "jobs-reviewer"},
                        {"date": "2026-10-20T18:00", "status": "ready", "by": "jobs-reviewer",
                         "note": "review-2 after change"}])
    proc = run_gate(app)
    assert proc.returncode == 1 and "changed after the user said apply" in proc.stderr, proc.stderr
    assert check(app, submitted()).returncode == 1


def test_a_consent_without_a_kit_hash_is_refused(tmp_path):
    app = ready_to_submit(tmp_path)
    consent(app, kit_sha256=None)
    proc = run_gate(app)
    assert proc.returncode == 1 and "consent.kit_sha256" in proc.stderr, proc.stderr


def test_the_kit_hash_moves_with_each_deliverable_and_not_with_the_screenshots(tmp_path):
    app = make_application(tmp_path)
    (app / "cv_ats.pdf").write_bytes(b"%PDF-1.4 one\n")
    (app / "cover_letter.md").write_text("Letter one.\n", encoding="utf-8")
    first = kit_hash(app)
    (app / "cover_letter.md").write_text("Letter two.\n", encoding="utf-8")
    second = kit_hash(app)
    (app / "before.png").write_bytes(PNG + b"other")
    third = kit_hash(app)
    assert len(first) == 64 and first != second
    assert third == second, "a screenshot is not a deliverable of the kit"


def test_the_kit_hash_needs_a_cv(tmp_path):
    app = make_application(tmp_path)
    (app / "cv_ats.pdf").unlink()
    proc = subprocess.run([sys.executable, str(CHECK), "--kit-hash", str(app)], capture_output=True, text=True)
    assert proc.returncode == 2 and "cv_ats.pdf" in proc.stderr


def test_a_screenshot_outside_application_is_refused(tmp_path):
    # An absolute path to a confirmation image outside application/ was accepted as evidence.
    app = ready_to_submit(tmp_path)
    outside = tmp_path / "elsewhere" / "confirmation.png"
    outside.parent.mkdir()
    outside.write_bytes(PNG)
    data = submitted()
    data["screenshots"] = ["before.png", str(outside)]
    proc = check(app, data)
    assert proc.returncode == 1 and "inside application/" in proc.stderr, proc.stderr


def test_a_relative_screenshot_climbing_out_of_application_is_refused(tmp_path):
    app = ready_to_submit(tmp_path)
    (app.parent / "confirmation.png").write_bytes(PNG)  # beside application/, not inside it
    data = submitted()
    data["screenshots"] = ["before.png", "../confirmation.png"]
    proc = check(app, data)
    assert proc.returncode == 1 and "inside application/" in proc.stderr, proc.stderr


def test_the_pre_submit_approval_image_must_be_inside_application(tmp_path):
    app = ready_to_submit(tmp_path)
    project_profile(app, PROJECT_PROFILE.replace("review_before_submit: false", "review_before_submit: true"))
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "pre.png").write_bytes(PNG)
    consent(app, screenshot_approval={"by": "Ana Example", "words": "send it", "date": "2026-10-20",
                                      "screenshot": "../../../elsewhere/pre.png"})
    proc = check(app, submitted())
    assert proc.returncode == 1 and "inside application/" in proc.stderr, proc.stderr


# --- auto_apply: auto — one standing yes, the fit score, and the daily caps --------------------------------------

AUTO_PROFILE = ("---\nname: Example\nauto_apply: auto\nauto_apply_since: 2026-10-01\napply_consent: standing\n"
                "daily_apply_cap: 10\ndaily_easy_apply_cap: 5\nreview_before_submit: false\n---\nFictional project.\n")
LINKEDIN_JOB = "https://www.linkedin.com/jobs/view/4123456789/"
TODAY = date.today().isoformat()
ATS_FORM = "https://jobs.lever.co/acme/2f1c9a7e-5b1d-4c2a-9e8f-1a2b3c4d5e6f/apply"


def open_analysis(app, score=82, eligibility="PASS"):
    """analysis.json of the opening: the two values auto submission reads (score_analysis.py writes both)."""
    (app.parent / "analysis.json").write_text(json.dumps({
        "id": app.parent.name,
        "gates": {"eligibility": eligibility, "language": "PASS", "location": "PASS", "seniority": "PASS"},
        "fit": {"score": score, "band": "strong", "decision": "PURSUE"}}), encoding="utf-8")


def auto_ready(tmp_path, apply_url=ATS_FORM, score=82, eligibility="PASS"):
    """An approved opening of a project on standing consent: no consent.json, the profile carries the yes."""
    app = make_application(tmp_path, apply_url=apply_url)
    project_profile(app, AUTO_PROFILE)
    approve(app)
    open_analysis(app, score, eligibility)
    return app


def prior_submission(project, opening_id, method="no_login_form", day=None):
    """One submission the applier recorded on `day`: an applied line in status.json and the method in the record."""
    opening = project / "openings" / opening_id
    (opening / "application").mkdir(parents=True, exist_ok=True)
    path = opening / "status.json"
    history = json.loads(path.read_text(encoding="utf-8"))["history"] if path.is_file() else []
    history.append({"date": f"{day or TODAY}T11:00", "status": "applied", "by": "jobs-applier", "note": ""})
    path.write_text(json.dumps({"history": history, "status": "applied"}), encoding="utf-8")
    (opening / "application" / "submission.json").write_text(
        json.dumps({"id": opening_id, "result": "SUBMITTED", "method": method}), encoding="utf-8")


def gate(app, *extra):
    return subprocess.run([sys.executable, str(CHECK), str(app / "submission.json"), "--gate", *extra],
                          capture_output=True, text=True)


def test_auto_submits_on_the_profile_without_a_consent_file(tmp_path):
    # The user said yes once: the applier does not wait for another apply, and nothing writes consent.json.
    app = auto_ready(tmp_path)
    assert not (app / "consent.json").exists()
    proc = gate(app)
    assert proc.returncode == 0 and "gate: open" in proc.stdout, proc.stderr
    record = check(app, submitted())
    assert record.returncode == 0, record.stderr
    assert not (app / "consent.json").exists()


def test_auto_below_the_apply_threshold_closes_the_gate(tmp_path):
    app = auto_ready(tmp_path, score=69)  # apply_threshold defaults to 70
    proc = gate(app)
    assert proc.returncode == 1 and "below apply_threshold 70" in proc.stderr, proc.stderr
    assert check(app, submitted()).returncode == 1


def test_auto_refuses_an_opening_whose_eligibility_is_not_pass(tmp_path):
    app = auto_ready(tmp_path, eligibility="FLAG")
    proc = gate(app)
    assert proc.returncode == 1 and "gates.eligibility is 'FLAG'" in proc.stderr, proc.stderr


def test_auto_needs_the_opening_analysis_to_decide(tmp_path):
    app = auto_ready(tmp_path)
    (app.parent / "analysis.json").unlink()
    proc = gate(app)
    assert proc.returncode == 1 and "analysis.json" in proc.stderr, proc.stderr


def test_auto_without_standing_consent_closes_the_gate(tmp_path):
    app = auto_ready(tmp_path)
    project_profile(app, AUTO_PROFILE.replace("apply_consent: standing", "apply_consent: per_opening"))
    proc = gate(app)
    assert proc.returncode == 1 and "apply_consent: standing" in proc.stderr, proc.stderr


def test_auto_with_review_before_submit_contradicts_itself(tmp_path):
    app = auto_ready(tmp_path)
    project_profile(app, AUTO_PROFILE.replace("review_before_submit: false", "review_before_submit: true"))
    proc = gate(app)
    assert proc.returncode == 1 and "auto_apply: ask" in proc.stderr, proc.stderr


def auto_full_profile(since="2026-10-01"):
    """The validator's fictional project, moved to standing consent (the manager writes these keys)."""
    text = edit_profile(FULL_PROFILE, "auto_apply: try", "auto_apply: auto")
    text = edit_profile(text, "apply_consent: per_opening", "apply_consent: standing")
    if since:
        text = edit_profile(text, "review_before_submit: false",
                            f"auto_apply_since: {since}\nreview_before_submit: false")
    return text


def test_auto_without_the_day_the_user_said_yes_fails_validation(tmp_path):
    missing = write_full_project(tmp_path, profile=auto_full_profile(since=""))
    assert keyed_finding(profile_findings(missing), "profile.md", "auto_apply_since"), "the day is required with auto"
    dated = write_full_project(tmp_path, profile=auto_full_profile())
    assert keyed_finding(profile_findings(dated), "profile.md", "auto_apply_since") == []


def test_the_consent_shape_must_match_the_auto_apply_mode(tmp_path):
    # auto is the one standing consent; try and ask submit on each opening's own apply.
    auto_short = edit_profile(auto_full_profile(), "apply_consent: standing", "apply_consent: per_opening")
    assert keyed_finding(profile_findings(write_full_project(tmp_path, profile=auto_short)), "profile.md",
                         "apply_consent")
    try_standing = edit_profile(FULL_PROFILE, "apply_consent: per_opening", "apply_consent: standing")
    assert keyed_finding(profile_findings(write_full_project(tmp_path, profile=try_standing)), "profile.md",
                         "apply_consent")


def test_the_eleventh_application_of_the_day_closes_the_gate_until_tomorrow(tmp_path):
    app = auto_ready(tmp_path)
    project = app.parent.parent.parent
    assert gate(app).returncode == 0, "control: the first application of the day passes"
    for i in range(10):
        prior_submission(project, f"JOB-20260925-acme-role-{i:02d}")
    proc = gate(app)
    assert proc.returncode == 1 and proc.stdout == "", proc.stdout
    assert "daily_cap" in proc.stderr and "tomorrow" in proc.stderr and "never a kit" in proc.stderr, proc.stderr
    assert check(app, submitted()).returncode == 1, "the record of a submit the cap refused is refused too"


def test_a_previous_day_does_not_use_up_todays_cap(tmp_path):
    app = auto_ready(tmp_path)
    project = app.parent.parent.parent
    for i in range(10):
        prior_submission(project, f"JOB-20260924-acme-role-{i:02d}", day="2026-09-24")
    assert gate(app).returncode == 0, "yesterday's applications are not today's"


def test_recording_twice_never_reads_its_own_submission_as_the_cap(tmp_path):
    # The tenth application of the day: recording it a second time (record_submission is idempotent) must not look
    # like an eleventh.
    app = auto_ready(tmp_path)
    project = app.parent.parent.parent
    for i in range(9):
        prior_submission(project, f"JOB-20260925-acme-role-{i:02d}")
    assert check(app, submitted()).returncode == 0
    prior_submission(project, OPENING_ID)  # what record_submission.py leaves behind for this opening
    assert check(app, submitted()).returncode == 0


def test_easy_apply_is_allowed_only_on_a_linkedin_job_page(tmp_path):
    app = auto_ready(tmp_path, apply_url=LINKEDIN_JOB)
    proc = gate(app, "--method", "linkedin_easy_apply")
    assert proc.returncode == 0 and "gate: open" in proc.stdout, proc.stderr
    record = check(app, {**submitted(), "method": "linkedin_easy_apply"})
    assert record.returncode == 0, record.stderr

    search = "JOB-20260925-acme-second-role"
    other = make_application(tmp_path, opening_id=search,
                             apply_url="https://www.linkedin.com/jobs/search/?keywords=data%20analyst")
    project_profile(other, AUTO_PROFILE)
    approve(other)
    open_analysis(other)
    proc = gate(other, "--method", "linkedin_easy_apply")
    assert proc.returncode == 1 and "jobs/view" in proc.stderr, proc.stderr


def test_easy_apply_counts_against_its_own_cap_only(tmp_path):
    app = auto_ready(tmp_path, apply_url=LINKEDIN_JOB)
    project = app.parent.parent.parent
    for i in range(5):  # daily_easy_apply_cap defaults to 5, daily_apply_cap to 10
        prior_submission(project, f"JOB-20260925-acme-easy-{i:02d}", method="linkedin_easy_apply")
    proc = gate(app, "--method", "linkedin_easy_apply")
    assert proc.returncode == 1 and "daily_cap" in proc.stderr and "Easy Apply" in proc.stderr, proc.stderr
    ats = make_application(tmp_path, opening_id="JOB-20260925-acme-ats-role", apply_url=ATS_FORM)
    project_profile(ats, AUTO_PROFILE)
    approve(ats)
    open_analysis(ats)
    assert gate(ats, "--method", "no_login_form").returncode == 0, "the total cap is not reached: an ATS form may go"


def test_easy_apply_needs_standing_consent(tmp_path):
    app = ready_to_submit(tmp_path)  # try, with the user's words for this opening
    open_analysis(app)
    proc = check(app, {**submitted(), "method": "linkedin_easy_apply"}, "--apply-url", LINKEDIN_JOB)
    assert proc.returncode == 1 and "auto_apply: auto" in proc.stderr, proc.stderr


def test_try_still_needs_the_consent_file(tmp_path):
    app = ready_to_submit(tmp_path)
    open_analysis(app)  # a good score and a verified link do not replace the user's yes under try
    assert gate(app).returncode == 0
    (app / "consent.json").unlink()
    proc = gate(app)
    assert proc.returncode == 1 and "consent.json" in proc.stderr, proc.stderr
    assert check(app, submitted()).returncode == 1

