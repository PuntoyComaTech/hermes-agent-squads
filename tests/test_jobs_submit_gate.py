"""Adversarial cases for the jobs submission gate: the ones QA reproduced against HEAD.

Pins four things the pre-click gate must decide before an irreversible submit, whatever the files say:
- the analysis of *this* opening decided PURSUE and no gate FAILs (a REJECT is never auto-submitted);
- fit.score and apply_threshold are finite numbers in 0..100 (NaN, Infinity, 1e9 and negative values are refused);
- two appliers at nine of ten cannot both open the gate, and a submit whose cap filled up after the click is still
  recorded, flagged, never dropped;
- only no_login_form and linkedin_easy_apply may be submitted, no bot of the squad may write the consent, and the
  daily cap counts each opening by the newest date of its `applied` lines.

Every test runs the real scripts (subprocess). Fictional people only.
"""
import json
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

from test_jobs_profile import PROFILE as FULL_PROFILE
from test_jobs_profile import edit as edit_profile
from test_jobs_profile import findings as profile_findings
from test_jobs_profile import keyed as keyed_finding
from test_jobs_profile import write_project as write_full_project

REPO = Path(__file__).resolve().parents[1]
SUBMIT = REPO / "squads" / "jobs" / "skills" / "submitting-applications" / "scripts"
CHECK = SUBMIT / "check_submission.py"
RECORD = SUBMIT / "record_submission.py"
SQUAD = REPO / "squads" / "jobs" / "squad.yaml"
OPENING_ID = "JOB-20260925-acme-data-analyst"
ATS = "https://jobs.lever.co/acme/2f1c9a7e-5b1d-4c2a-9e8f-1a2b3c4d5e6f/apply"
PNG = b"\x89PNG\r\n\x1a\n"
TODAY = date.today().isoformat()
AUTO_PROFILE = ("---\nname: Example\nauto_apply: auto\nauto_apply_since: 2026-10-01\napply_consent: standing\n"
                "daily_apply_cap: 10\ndaily_easy_apply_cap: 5\nreview_before_submit: false\n---\nFictional project.\n")


def make_opening(root, opening_id=OPENING_ID, apply_url=ATS):
    """An approved opening of a project on standing consent: ready for the gate, nothing submitted yet."""
    app = root / "openings" / opening_id / "application"
    app.mkdir(parents=True)
    (app.parent / "opening.md").write_text(
        f"---\nid: {opening_id}\ncompany: Acme\nrole: Analyst\napply_url: {apply_url}\n---\nPosting.\n",
        encoding="utf-8")
    for name in ("before.png", "confirmation.png"):
        (app / name).write_bytes(PNG)
    (app / "cv_ats.pdf").write_bytes(b"%PDF-1.4 fictional CV\n")
    (root / "profile.md").write_text(AUTO_PROFILE, encoding="utf-8")
    (app.parent / "review-1.json").write_text(json.dumps({"verdict": "APPROVED"}), encoding="utf-8")
    (app.parent / "status.json").write_text(json.dumps({"history": [
        {"date": "2026-10-20T09:05", "status": "ready", "by": "jobs-reviewer"}], "status": "ready"}),
        encoding="utf-8")
    write_analysis(app)
    return app


def write_analysis(app, score=82, decision="PURSUE", gates=None, ident=None):
    """analysis.json as score_analysis.py finalize writes it: id, the four gates, fit.score and fit.decision."""
    doc = {
        "id": app.parent.name if ident is None else ident,
        "gates": {"eligibility": "PASS", "language": "PASS", "location": "PASS", "seniority": "PASS", **(gates or {})},
        "fit": {"score": score, "band": "strong", "decision": decision},
    }
    (app.parent / "analysis.json").write_text(json.dumps(doc), encoding="utf-8")


def write_analysis_text(app, text):
    """The raw text, for the values json.dump would refuse to write (NaN, Infinity) or a hand-edited score."""
    (app.parent / "analysis.json").write_text(text, encoding="utf-8")


def submitted(opening_id=OPENING_ID, method="no_login_form"):
    return {
        "id": opening_id, "result": "SUBMITTED", "method": method,
        "filled_fields": [{"field": "Email", "source": "contact.yaml"},
                          {"field": "CV upload", "source": "cv"}],
        "pending_questions": [], "screenshots": ["before.png", "confirmation.png"], "reason": "",
    }


def gate(app, *extra):
    return subprocess.run([sys.executable, str(CHECK), str(app / "submission.json"), "--gate", *extra],
                          capture_output=True, text=True, timeout=120)


def record(app, data):
    path = app / "submission.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return subprocess.run([sys.executable, str(RECORD), str(path), "--json"],
                          capture_output=True, text=True, timeout=120)


def prior(project, opening_id, method="no_login_form", day=None, extra_lines=()):
    """One submission already recorded: an `applied` line (plus any later line) and its method in the record."""
    opening = project / "openings" / opening_id
    (opening / "application").mkdir(parents=True, exist_ok=True)
    history = [{"date": f"{day or TODAY}T11:00", "status": "applied", "by": "jobs-applier"}, *extra_lines]
    (opening / "status.json").write_text(json.dumps({"history": history, "status": "applied"}), encoding="utf-8")
    (opening / "application" / "submission.json").write_text(
        json.dumps({"id": opening_id, "result": "SUBMITTED", "method": method}), encoding="utf-8")


def nine_prior(project):
    for i in range(9):
        prior(project, f"JOB-20260925-acme-role-{i:02d}")


# --- 2. the analysis of this opening must decide PURSUE, with no failed gate ---------------------------------------

def test_a_rejected_analysis_is_never_auto_submitted(tmp_path):
    # gates {eligibility: PASS, language: FAIL, location: FAIL}, fit {score: 95, decision: REJECT}: the eligibility
    # gate alone and a high score used to open the gate, so a REJECT was submitted.
    app = make_opening(tmp_path)
    write_analysis(app, score=95, decision="REJECT", gates={"language": "FAIL", "location": "FAIL"})
    proc = gate(app)
    assert proc.returncode == 1 and proc.stdout == "", proc.stdout
    assert "gate FAIL: language, location" in proc.stderr, proc.stderr
    assert "fit.decision" in proc.stderr and "REJECT" in proc.stderr, proc.stderr
    assert record(app, submitted()).returncode == 1


def test_the_analysis_must_belong_to_this_opening(tmp_path):
    app = make_opening(tmp_path)
    write_analysis(app, ident="JOB-20260925-acme-other-role")
    proc = gate(app)
    assert proc.returncode == 1 and "analysis.id" in proc.stderr, proc.stderr


def test_a_watch_decision_keeps_the_gate_closed(tmp_path):
    # decide() returns WATCH for a gate FLAG or a score below apply_threshold: only PURSUE is a submit.
    app = make_opening(tmp_path)
    write_analysis(app, score=95, decision="WATCH", gates={"location": "FLAG"})
    proc = gate(app)
    assert proc.returncode == 1 and "fit.decision" in proc.stderr and "WATCH" in proc.stderr, proc.stderr


def test_an_analysis_without_a_decision_keeps_the_gate_closed(tmp_path):
    app = make_opening(tmp_path)
    write_analysis_text(app, json.dumps({"id": app.parent.name,
                                         "gates": {"eligibility": "PASS"},
                                         "fit": {"score": 95}}))
    proc = gate(app)
    assert proc.returncode == 1 and "fit.decision" in proc.stderr, proc.stderr


def test_a_pursue_analysis_opens_the_gate(tmp_path):
    app = make_opening(tmp_path)
    assert gate(app).returncode == 0, "control: the documented shape is PURSUE with four passing gates"
    assert record(app, submitted()).returncode == 0


# --- 3. the score and the threshold are finite numbers in 0..100 ---------------------------------------------------

def test_a_score_outside_the_scoring_range_closes_the_gate(tmp_path):
    for raw in ("NaN", "Infinity", "1e9", "-5", '"82"'):
        root = tmp_path / raw.strip('"').replace("-", "minus")
        app = make_opening(root)
        write_analysis_text(app, '{"id": "%s", "gates": {"eligibility": "PASS"}, "fit": {"score": %s, '
                                 '"decision": "PURSUE"}}' % (app.parent.name, raw))
        proc = gate(app)
        assert proc.returncode == 1 and proc.stdout == "", f"{raw}: {proc.stdout}{proc.stderr}"
        assert "fit.score" in proc.stderr, f"{raw}: {proc.stderr}"


def test_an_apply_threshold_outside_the_scoring_range_closes_the_gate(tmp_path):
    for raw in (".nan", ".inf", "-5", "150"):
        root = tmp_path / raw.replace(".", "").replace("-", "minus")
        app = make_opening(root)
        (root / "profile.md").write_text(AUTO_PROFILE.replace("daily_apply_cap: 10",
                                                              f"apply_threshold: {raw}\ndaily_apply_cap: 10"),
                                         encoding="utf-8")
        proc = gate(app)
        assert proc.returncode == 1 and "apply_threshold" in proc.stderr, f"{raw}: {proc.stderr}"


def test_the_validator_refuses_an_impossible_apply_threshold(tmp_path):
    for raw in (".nan", ".inf", "150", "-5", "'70'"):
        folder = tmp_path / raw.replace(".", "").replace("-", "minus").replace("'", "")
        folder.mkdir()
        project = write_full_project(folder, profile=edit_profile(
            FULL_PROFILE, "apply_threshold: 70", f"apply_threshold: {raw}"))
        assert keyed_finding(profile_findings(project), "profile.md", "apply_threshold"), f"{raw} must be refused"
    ok = tmp_path / "ok"
    ok.mkdir()
    project = write_full_project(ok, profile=edit_profile(FULL_PROFILE, "apply_threshold: 70",
                                                          "apply_threshold: 72"))
    assert keyed_finding(profile_findings(project), "profile.md", "apply_threshold") == []


# --- 4. two appliers at nine of ten, and a submit the cap cannot refuse after the click ---------------------------

def test_two_openings_at_nine_prior_cannot_both_open_the_gate(tmp_path):
    first = make_opening(tmp_path)
    second = make_opening(tmp_path, opening_id="JOB-20260925-acme-second-role")
    nine_prior(tmp_path)
    assert gate(first).returncode == 0, "control: nine of ten leaves one place"
    proc = gate(second)
    assert proc.returncode == 1 and "daily_cap" in proc.stderr, (
        "the first gate holds the tenth place: two concurrent appliers became eleven submissions")


def test_an_expired_reservation_gives_the_place_back(tmp_path):
    first = make_opening(tmp_path)
    second = make_opening(tmp_path, opening_id="JOB-20260925-acme-second-role")
    nine_prior(tmp_path)
    assert gate(first).returncode == 0
    state = tmp_path / "openings" / ".apply-state.json"
    doc = json.loads(state.read_text(encoding="utf-8"))
    doc["reservations"][first.parent.name]["at"] = "2026-01-01T00:00:00Z"  # an abandoned run, hours old
    state.write_text(json.dumps(doc), encoding="utf-8")
    assert gate(second).returncode == 0, "a reservation must expire, or an abandoned gate blocks the day"


def test_re_gating_the_same_opening_is_not_blocked_by_its_own_reservation(tmp_path):
    # Step 5 runs the gate again after before.png: the opening's own place must not count against it.
    app = make_opening(tmp_path)
    nine_prior(tmp_path)
    assert gate(app).returncode == 0
    proc = gate(app)
    assert proc.returncode == 0 and "gate: open" in proc.stdout, proc.stderr


def test_a_submit_is_recorded_even_when_the_cap_filled_up_after_the_gate(tmp_path):
    app = make_opening(tmp_path)
    nine_prior(tmp_path)
    assert gate(app).returncode == 0, "control: the gate is open, so the applier may click"
    prior(tmp_path, "JOB-20260925-acme-tenth-role")  # another run records the tenth application meanwhile
    proc = record(app, submitted())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["flags"] and "daily_cap" in " ".join(payload["flags"]), payload
    status = json.loads((app.parent / "status.json").read_text(encoding="utf-8"))
    assert status["status"] == "applied" and status["history"][-1]["status"] == "applied"
    assert "over the gate" in status["history"][-1]["note"] or "cap" in status["history"][-1]["note"]
    tracker = (tmp_path / "tracker.csv").read_text(encoding="utf-8")
    assert OPENING_ID in tracker, "a real submit keeps its tracker row"


def test_a_broken_record_is_still_refused_after_the_click(tmp_path):
    app = make_opening(tmp_path)
    nine_prior(tmp_path)
    assert gate(app).returncode == 0
    proc = record(app, submitted(method="captcha"))
    assert proc.returncode == 1, "recording a captcha 'submission' is not what the cap re-check was about"
    assert not (tmp_path / "tracker.csv").exists() or OPENING_ID not in (tmp_path / "tracker.csv").read_text(
        encoding="utf-8")


# --- 12. the pre-click gate refuses every method that goes to a kit ----------------------------------------------

def test_the_gate_refuses_a_method_that_goes_to_a_kit(tmp_path):
    for method in ("captcha", "requires_account", "email", "linkedin", "other"):
        app = make_opening(tmp_path / method)
        proc = gate(app, "--method", method)
        assert proc.returncode == 1 and proc.stdout == "", f"{method}: {proc.stdout}{proc.stderr}"
        assert "no_login_form" in proc.stderr and "linkedin_easy_apply" in proc.stderr, proc.stderr


def test_a_stale_record_naming_another_method_closes_the_gate(tmp_path):
    app = make_opening(tmp_path)
    (app / "submission.json").write_text(json.dumps({"method": "email"}), encoding="utf-8")
    proc = gate(app)
    assert proc.returncode == 1 and "email" in proc.stderr, proc.stderr


# --- 16. no bot of the squad writes the consent ----------------------------------------------------------------

def check_module():
    """check_submission.py as a module, for the constants the tests pin (BOT_NAMES)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_submission_for_tests", CHECK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_bot_of_the_squad_can_write_the_consent(tmp_path):
    bots = sorted(yaml.safe_load(SQUAD.read_text(encoding="utf-8"))["bots"])
    assert "jobs-inbox" in bots  # the optional bot of squad.yaml: it must not pass as the user either
    app = make_opening(tmp_path)
    (tmp_path / "profile.md").write_text(AUTO_PROFILE.replace("auto_apply: auto", "auto_apply: try")
                                         .replace("apply_consent: standing", "apply_consent: per_opening"),
                                         encoding="utf-8")
    module = check_module()
    kit = subprocess.run([sys.executable, str(CHECK), "--kit-hash", str(app)], capture_output=True, text=True)
    assert kit.returncode == 0, kit.stderr
    for bot in bots:
        (app / "consent.json").write_text(json.dumps({
            "opening_id": OPENING_ID, "by": bot, "words": "ok", "date": "2026-10-20",
            "kit_sha256": kit.stdout.strip()}), encoding="utf-8")
        proc = gate(app)
        assert proc.returncode == 1 and "names the bot profile" in proc.stderr, f"{bot}: {proc.stderr}"
        assert bot.casefold() in module.BOT_NAMES, f"{bot} is a bot of squad.yaml"


# --- 17. the cap counts each opening by the newest date of its applied lines -------------------------------------

def test_the_cap_counts_the_newest_applied_date_of_each_opening(tmp_path):
    app = make_opening(tmp_path)
    for i in range(10):
        # the applied line for today, then a later line in the list that is back-dated: the list order is not the date
        prior(tmp_path, f"JOB-20260925-acme-role-{i:02d}",
              extra_lines=[{"date": "2026-10-01T10:00", "status": "applied", "by": "jobs-applier"}])
    proc = gate(app)
    assert proc.returncode == 1 and "daily_cap" in proc.stderr, (
        "ten applications today must close the gate whatever order their history lists them in")


# --- the record softens a rule only with proof the gate opened for this opening ------------------------------------

APPLY_STATE = SUBMIT / "apply_state.py"
SKILL = SUBMIT.parent / "SKILL.md"
STAMP = "%Y-%m-%dT%H:%M:%SZ"


def stamp_of(app, opened_at=None, opening_id=None):
    """application/gate.json: the stamp check_submission.py --gate writes when the gate opens for this opening."""
    doc = {"opening_id": opening_id or app.parent.name, "method": "no_login_form", "mode": "auto",
           "opened_at": opened_at or datetime.now(timezone.utc).strftime(STAMP)}
    (app / "gate.json").write_text(json.dumps(doc), encoding="utf-8")
    return doc


def try_profile(app):
    """auto_apply: try + per_opening: the opening needs the user's consent.json for this one apply."""
    (app.parent.parent.parent / "profile.md").write_text(
        AUTO_PROFILE.replace("auto_apply: auto", "auto_apply: try")
                   .replace("apply_consent: standing", "apply_consent: per_opening"), encoding="utf-8")


# The six openings QA recorded as `applied` with exit 0 although no gate had ever opened for them (life.py case 6).
NEVER_SUBMITTABLE = ("auto_apply never", "try without consent.json", "unverified apply_url", "job board apply_url",
                     "no review file", "empty status history")


def never_submittable(root, case):
    if case == "unverified apply_url":
        app = make_opening(root, apply_url="https://boards-greenhouse.io/acme/jobs/1")  # a look-alike: a sign of fraud
    elif case == "job board apply_url":
        app = make_opening(root, apply_url="https://www.computrabajo.com.co/ofertas-de-trabajo/x")
    else:
        app = make_opening(root)
    if case == "auto_apply never":
        (root / "profile.md").write_text(AUTO_PROFILE.replace("auto_apply: auto", "auto_apply: never"),
                                         encoding="utf-8")
    elif case == "try without consent.json":
        try_profile(app)
    elif case == "no review file":
        (app.parent / "review-1.json").unlink()
    elif case == "empty status history":
        (app.parent / "status.json").write_text(json.dumps({"history": []}), encoding="utf-8")
    return app


def applied(app, root):
    """(the tracker holds this opening, the last status line is applied)."""
    tracker = root / "tracker.csv"
    in_tracker = tracker.is_file() and app.parent.name in tracker.read_text(encoding="utf-8")
    status = json.loads((app.parent / "status.json").read_text(encoding="utf-8"))
    return in_tracker, status.get("status") == "applied" or (status.get("history") or [{}])[-1].get("status") == "applied"


@pytest.mark.parametrize("case", NEVER_SUBMITTABLE)
def test_a_record_without_proof_the_gate_opened_is_refused(tmp_path, case):
    # Before the fix every authority rule was softened, so a bot that skipped the gate wrote `applied` with exit 0.
    app = never_submittable(tmp_path, case)
    assert gate(app).returncode == 1, "control: no gate opens for this opening, so no stamp is written"
    assert not (app / "gate.json").exists(), "the gate writes a stamp only when it opens"
    proc = record(app, submitted(opening_id=app.parent.name))
    assert proc.returncode == 1, f"{case}: the record turned a refused submit into applied: {proc.stdout}"
    assert applied(app, tmp_path) == (False, False), f"{case}: a phantom submit reached the tracker or the status"


@pytest.mark.parametrize("case", NEVER_SUBMITTABLE)
def test_a_gate_stamp_never_softens_what_was_never_submittable(tmp_path, case):
    # A stamp proves the gate opened for this opening; it does not make a refusal into a submit.
    app = never_submittable(tmp_path, case)
    stamp_of(app)
    proc = record(app, submitted(opening_id=app.parent.name))
    assert proc.returncode == 1, f"{case}: a stamp softened a rule that never moved: {proc.stdout}"
    assert applied(app, tmp_path) == (False, False), f"{case}: a phantom submit reached the tracker or the status"


def test_a_gate_stamp_older_than_four_hours_is_no_proof(tmp_path):
    app = make_opening(tmp_path)
    nine_prior(tmp_path)
    assert gate(app).returncode == 0
    prior(tmp_path, "JOB-20260925-acme-tenth-role")   # the cap fills up while the form is open
    stamp_of(app, opened_at="2026-01-01T00:00:00Z")   # ...hours after this gate opened
    proc = record(app, submitted())
    assert proc.returncode == 1 and "daily_cap" in proc.stdout, proc.stdout
    assert applied(app, tmp_path) == (False, False), "a stale stamp must not record over the cap"


def test_a_gate_stamp_of_another_opening_is_no_proof(tmp_path):
    first = make_opening(tmp_path)
    second = make_opening(tmp_path, opening_id="JOB-20260925-acme-second-role")
    nine_prior(tmp_path)
    assert gate(first).returncode == 0
    prior(tmp_path, "JOB-20260925-acme-tenth-role")
    (second / "gate.json").write_text((first / "gate.json").read_text(encoding="utf-8"), encoding="utf-8")
    proc = record(second, submitted(opening_id=second.parent.name))
    assert proc.returncode == 1 and "daily_cap" in proc.stdout, proc.stdout
    assert applied(second, tmp_path) == (False, False), "another opening's stamp is another opening's proof"


def test_the_gate_writes_the_stamp_of_this_opening(tmp_path):
    app = make_opening(tmp_path)
    nine_prior(tmp_path)
    assert gate(app).returncode == 0
    stamp = json.loads((app / "gate.json").read_text(encoding="utf-8"))
    assert stamp["opening_id"] == app.parent.name and stamp["method"] == "no_login_form"
    assert stamp["mode"] == "auto" and stamp["opened_at"]
    prior(tmp_path, "JOB-20260925-acme-tenth-role")
    proc = record(app, submitted())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["note"] == "recorded over the gate: daily_cap", payload
    status = json.loads((app.parent / "status.json").read_text(encoding="utf-8"))
    assert "recorded over the gate: daily_cap" in status["history"][-1]["note"]


def test_a_review_replaced_after_the_gate_is_recorded_as_a_flag(tmp_path):
    app = make_opening(tmp_path)
    assert gate(app).returncode == 0
    (app.parent / "review-2.json").write_text(json.dumps({"verdict": "NOT_APPROVED"}), encoding="utf-8")
    proc = record(app, submitted())
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["flags"] and payload["flags"][0].startswith("review.replaced:"), payload
    assert payload["note"] == "recorded over the gate: review.replaced"


def test_a_reservation_whose_opening_already_applied_counts_once(tmp_path):
    # The record died between its status append and its release: an `applied` line and a live reservation, one submit.
    first = make_opening(tmp_path)
    for i in range(8):
        prior(tmp_path, f"JOB-20260925-acme-role-{i:02d}")
    assert gate(first).returncode == 0
    history = json.loads((first.parent / "status.json").read_text(encoding="utf-8"))["history"]
    history.append({"date": f"{TODAY}T12:00", "status": "applied", "by": "jobs-applier"})
    (first.parent / "status.json").write_text(json.dumps({"history": history, "status": "applied"}), encoding="utf-8")
    state = json.loads((tmp_path / "openings" / ".apply-state.json").read_text(encoding="utf-8"))
    assert first.parent.name in state["reservations"], "control: the place is still held"
    assert check_module().submissions_today(tmp_path, date.today())["total"] == 9, "one opening counted twice"
    second = make_opening(tmp_path, opening_id="JOB-20260925-acme-second-role")
    assert gate(second).returncode == 0, "8 recorded + 1 = 9 of 10: the next opening still has a place"


def test_a_softened_record_prints_its_flags_and_the_status_note(tmp_path):
    # The applier's card quotes what it prints: a soft record must say so without --json, not only in the file.
    app = make_opening(tmp_path)
    nine_prior(tmp_path)
    assert gate(app).returncode == 0
    prior(tmp_path, "JOB-20260925-acme-tenth-role")
    (app / "submission.json").write_text(json.dumps(submitted()), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(RECORD), str(app / "submission.json")],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "flag: daily_cap:" in proc.stderr, proc.stderr
    assert "note: recorded over the gate: daily_cap" in proc.stdout, proc.stdout


def test_the_release_command_gives_a_place_back(tmp_path):
    app = make_opening(tmp_path)
    second = make_opening(tmp_path, opening_id="JOB-20260925-acme-second-role")
    nine_prior(tmp_path)
    assert gate(app).returncode == 0
    assert gate(second).returncode == 1
    released = subprocess.run([sys.executable, str(APPLY_STATE), "--release", str(tmp_path),
                               "--opening", app.parent.name], capture_output=True, text=True, timeout=120)
    assert released.returncode == 0, released.stderr
    assert json.loads(released.stdout) == {"opening": app.parent.name, "released": True}
    assert gate(second).returncode == 0, "the tenth place went back to the day"
    again = subprocess.run([sys.executable, str(APPLY_STATE), "--release", str(tmp_path),
                            "--opening", app.parent.name], capture_output=True, text=True, timeout=120)
    assert json.loads(again.stdout)["released"] is False, "there is no place left to give back"


def test_the_record_softens_only_the_rules_that_move_after_the_click():
    # The policy is code, not prose: these rules and the stamp gate are the only way a record goes in over a refusal.
    assert check_module().RECHECK_SOFT == {"daily_cap", "review.replaced", "review.status", "consent.date"}


def test_the_skill_records_a_submit_without_a_second_check_and_names_the_release():
    step = SKILL.read_text(encoding="utf-8").split("6. **Record.**", 1)[1].split("\n7. ", 1)[0]
    assert "runs the record alone, and never `check_submission.py` first" in step, step
    assert "--post-submit" in step and "never turned into NOT_POSSIBLE" in step, step
    assert "gate.json" in step, "the stamp the softening needs must be named where the applier reads it"
    assert "--release" in step, "an applier that blocks on NOT_POSSIBLE or NEEDS_DATA gives its place back"


def test_apply_state_documents_the_lock_wait_and_the_release_command():
    text = APPLY_STATE.read_text(encoding="utf-8")
    assert "--release" in text and "--opening" in text
    assert "waits with no timeout" in text, "the lock wait is kept as it is and written down"



# --- Easy Apply pace: LinkedIn restricts accounts that apply in bursts ----------------------------------------------

EASY_URL = "https://www.linkedin.com/jobs/view/4483184903"


def easy_stamp(project, opening_id, seconds_ago):
    """The gate.json an Easy Apply gate left on another opening, `seconds_ago` seconds back."""
    app = project / "openings" / opening_id / "application"
    app.mkdir(parents=True, exist_ok=True)
    when = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() - seconds_ago, timezone.utc)
    (app / "gate.json").write_text(json.dumps({"opening_id": opening_id, "method": "linkedin_easy_apply",
                                               "mode": "auto", "opened_at": when.strftime("%Y-%m-%dT%H:%M:%SZ")}))


def test_a_second_easy_apply_within_a_minute_waits_and_then_opens(tmp_path):
    app = make_opening(tmp_path, apply_url=EASY_URL)
    easy_stamp(tmp_path, "JOB-20260925-globex-analyst", seconds_ago=20)
    early = gate(app, "--method", "linkedin_easy_apply")
    assert early.returncode == 1 and "easy_apply_gap" in early.stdout + early.stderr
    assert "wait" in early.stdout + early.stderr, "the applier is told how long to wait, not to give up"
    easy_stamp(tmp_path, "JOB-20260925-globex-analyst", seconds_ago=75)
    later = gate(app, "--method", "linkedin_easy_apply")
    assert later.returncode == 0, later.stdout + later.stderr


def test_the_pause_never_holds_back_an_employer_form_or_the_record_of_a_click(tmp_path):
    app = make_opening(tmp_path)
    easy_stamp(tmp_path, "JOB-20260925-globex-analyst", seconds_ago=5)
    assert gate(app, "--method", "no_login_form").returncode == 0
