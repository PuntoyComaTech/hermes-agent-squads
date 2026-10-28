"""followup_gate.py: the no-agent cron that files one inbox card per day only when follow-ups are due."""
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FAKES = REPO / "tests" / "fakes"
GATE = REPO / "squads" / "jobs" / "scripts" / "followup_gate.py"
TRACKER = REPO / "squads" / "jobs" / "skills" / "jobs-contract" / "scripts" / "tracker.py"
RECORD = REPO / "squads" / "jobs" / "skills" / "submitting-applications" / "scripts" / "record_submission.py"
CHECK = REPO / "squads" / "jobs" / "skills" / "submitting-applications" / "scripts" / "check_submission.py"
PNG = b"\x89PNG\r\n\x1a\n"
STALE_ROW = ("2026-08-01,JOB-20260801-acme-analyst,Acme,Analyst,applied,portal,70,"
             "https://jobs.lever.co/acme/2f1c9a7e-5b1d-4c2a-9e8f-1a2b3c4d5e6f/apply,,2026-08-01,,0,,,,")
HEADER = ("date,id,company,role,status,channel,fit_score,apply_url,deadline,applied_at,last_contact,follow_ups,"
          "notes,cv_file,cover_letter_file,source")


def env_with_project(tmp: Path, profile: str = "search: active", rows=()) -> tuple[dict, Path]:
    root = tmp / "hermes"
    (root / "profiles" / "jobs").mkdir(parents=True)
    (root / "profiles" / "jobs-inbox").mkdir(parents=True)  # the inbox bot's profile: `apply --with jobs-inbox`
    bindir = tmp / "bin"
    bindir.mkdir()
    (bindir / "hermes").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKES / "hermes.py"}" "$@"\n')
    (bindir / "hermes").chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "HERMES_HOME": str(root)}
    # The crons and the applier run outside an agent turn; a delegated-child marker inherited from the test
    # runner's own session would make the fake hermes refuse every kanban write.
    env.pop("HERMES_DELEGATED_CHILD_CONTEXT", None)
    folder = tmp / "search"
    folder.mkdir()
    done = subprocess.run(["hermes", "-p", "jobs", "project", "create", "Search", str(folder), "--slug", "search"],
                          capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr
    subprocess.run(["hermes", "-p", "jobs", "kanban", "boards", "create", "jobs"], capture_output=True, env=env)
    (folder / "profile.md").write_text(f"---\n{profile}\nfollow_up_days: 10\nstale_days: 60\n---\n")
    if rows is not None:
        (folder / "tracker.csv").write_text("\n".join([HEADER, *rows]) + "\n")
    return env, folder


def gate(env, *extra):
    # The cron runs outside any agent turn: a delegated-child marker inherited from the test runner's own session
    # would make the fake hermes refuse the card (the real rule), which is not what is under test here.
    env = {k: v for k, v in env.items() if k != "HERMES_DELEGATED_CHILD_CONTEXT"}
    return subprocess.run([sys.executable, str(GATE), "--tracker", str(TRACKER), "--today", "2026-10-20", *extra],
                          capture_output=True, text=True, env=env, timeout=120)


def one(proc) -> dict:
    """The decision of a single-project run: --json prints {"results": [...]}, one object per project."""
    results = json.loads(proc.stdout)["results"]
    assert len(results) == 1, results
    return results[0]


QUIET = ("2026-09-01,JOB-20260901-acme-data-analyst,Acme,Data analyst,applied,portal,78,https://jobs.example.com/1,,"
         "2026-09-01,2026-09-01,0,,,,")


def test_nothing_due_is_silent(tmp_path):
    env, _ = env_with_project(tmp_path, rows=[])
    p = gate(env)
    assert (p.returncode, p.stdout) == (0, ""), p.stderr
    assert one(gate(env, "--json"))["reason"] == "nothing due"


def test_missing_tracker_and_paused_are_silent(tmp_path):
    env, folder = env_with_project(tmp_path, rows=None)
    assert one(gate(env, "--json"))["reason"] == "no tracker yet"
    quiet = gate(env)
    assert (quiet.returncode, quiet.stdout) == (0, ""), "without --json a missing tracker prints nothing"
    (folder / "profile.md").write_text("---\nsearch: paused\n---\n")
    (folder / "tracker.csv").write_text(HEADER + "\n" + QUIET + "\n")
    p = gate(env, "--json")
    assert p.returncode == 0 and one(p)["reason"] == "paused"


def test_quiet_application_files_one_card_per_day(tmp_path):
    env, _ = env_with_project(tmp_path, rows=[QUIET])
    first = one(gate(env, "--json"))
    assert first["filed"] is True, first
    assert first["followups"] == ["JOB-20260901-acme-data-analyst"]
    assert first["key"] == "jobs:inbox:search:2026-10-20" and first["assignee"] == "jobs-inbox"
    second = one(gate(env, "--json"))
    assert second.get("id") == first.get("id")  # same idempotency key, same card
    quiet_run = gate(env)
    assert (quiet_run.returncode, quiet_run.stdout) == (0, "")


def test_dry_run_creates_nothing(tmp_path):
    env, _ = env_with_project(tmp_path, rows=[QUIET])
    # A dry run says what it would file and shows the card the inbox bot would get; it files nothing.
    out = one(gate(env, "--dry-run", "--json"))
    assert out["would_file"] is True and "filed" not in out and "id" not in out
    assert "Inbox" in out["title"] and out["body"].strip()


def test_a_missing_inbox_bot_files_nothing_and_reports_nothing_again(tmp_path):
    """#6: without `--with jobs-inbox` the bot's profile does not exist, and kanban create accepts any assignee.

    Filing anyway left a card nobody reads on the board and stamped `stale_reported`, so the application was never
    reported again. Now nothing is filed, nothing is marked, one line names the missing profile, and the stale row
    is still reported by the first run after the bot is installed.
    """
    env, _ = env_with_project(tmp_path, rows=[STALE_ROW])
    kanban_stub(env, tmp_path)
    shutil.rmtree(Path(env["HERMES_HOME"]) / "profiles" / "jobs-inbox")
    blocked = gate(env)
    assert blocked.returncode == 0, blocked.stderr
    assert "jobs-inbox is not installed" in blocked.stdout
    assert len(blocked.stdout.strip().splitlines()) == 1, "one line, not one per project"
    assert "stale_reported" not in json.dumps(one(gate(env, "--json"))), "no row is marked"
    (Path(env["HERMES_HOME"]) / "profiles" / "jobs-inbox").mkdir()
    first = one(gate(env, "--json"))
    assert first["filed"] is True and first["stale_reported"] == ["JOB-20260801-acme-analyst"], \
        "the stale row is still unreported once the bot exists"


def test_help_exits_zero():
    p = subprocess.run([sys.executable, str(GATE), "--help"], capture_output=True, text=True)
    assert p.returncode == 0 and "inbox card" in p.stdout


# --- the applier, the tracker and the follow-up gate, across days ------------------------------------------------

ACME_APPLY = "https://jobs.lever.co/acme/2f1c9a7e-5b1d-4c2a-9e8f-1a2b3c4d5e6f/apply"
OPENING = "JOB-20261001-acme-data-analyst"


def gate_on(env, day, *extra):
    return subprocess.run([sys.executable, str(GATE), "--tracker", str(TRACKER), "--today", day, *extra],
                          capture_output=True, text=True, env=env, timeout=120)


def kanban_stub(env, tmp: Path) -> None:
    """Replace the hermes shim: kanban create answers with a task id, every other command runs the fake.

    The fake refuses kanban mutations inside a delegated child (the real rule), so this stub is the card sink only:
    the decisions under test (what is due, what is reported once) are the gate's own.
    """
    bindir = Path(env["PATH"].split(os.pathsep)[0])
    (bindir / "hermes").write_text(
        "#!/bin/sh\n"
        "case \"$*\" in *kanban*) echo '{\"id\": \"task-stub\"}'; exit 0;; esac\n"
        f'exec "{sys.executable}" "{FAKES / "hermes.py"}" "$@"\n')
    (bindir / "hermes").chmod(0o755)


def submitted_opening(folder: Path, day: str) -> Path:
    """An approved opening with the user's consent, ready for the applier (fictional company)."""
    opening = folder / "openings" / OPENING
    app = opening / "application"
    app.mkdir(parents=True)
    (opening / "opening.md").write_text(f"---\nid: {OPENING}\ncompany: Acme\nrole: Data analyst\n"
                                        f"apply_url: {ACME_APPLY}\n---\nPosting.\n", encoding="utf-8")
    for name in ("before.png", "confirmation.png"):
        (app / name).write_bytes(b"\x89PNG\r\n\x1a\n")
    (app / "kit.md").write_text("Answers ready to copy.\n", encoding="utf-8")
    (app / "cv_ats.pdf").write_bytes(b"%PDF-1.4 fictional CV\n")
    (opening / "review-1.json").write_text(json.dumps({"verdict": "APPROVED", "status": "ready"}), encoding="utf-8")
    (opening / "status.json").write_text(json.dumps({"history": [
        {"date": f"{day}T09:00", "status": "ready", "by": "jobs-reviewer"}], "status": "ready"}), encoding="utf-8")
    kit = subprocess.run([sys.executable, str(CHECK), "--kit-hash", str(app)], capture_output=True, text=True)
    assert kit.returncode == 0, kit.stderr
    (app / "consent.json").write_text(json.dumps({"opening_id": OPENING, "by": "Ana Example", "words": "Yes, apply.",
                                                  "date": day, "kit_sha256": kit.stdout.strip()}), encoding="utf-8")
    (app / "submission.json").write_text(json.dumps({
        "id": OPENING, "result": "SUBMITTED", "method": "no_login_form",
        "filled_fields": [{"field": "Work authorization", "source": "application-data.yaml"}],
        "pending_questions": [], "screenshots": ["before.png", "confirmation.png"], "reason": ""}), encoding="utf-8")
    return app / "submission.json"


def test_an_applied_opening_gets_a_row_and_is_chased_after_follow_up_days(tmp_path):
    # Apply -> tracker row -> follow-up due after follow_up_days, through the real applier record step.
    env, folder = env_with_project(tmp_path, rows=None)
    kanban_stub(env, tmp_path)
    assert one(gate_on(env, "2026-10-01", "--json"))["reason"] == "no tracker yet"
    submission = submitted_opening(folder, "2026-10-01")
    recorded = subprocess.run([sys.executable, str(RECORD), str(submission), "--today", "2026-10-01", "--json"],
                              capture_output=True, text=True, timeout=120)
    assert recorded.returncode == 0, recorded.stdout + recorded.stderr
    assert json.loads(recorded.stdout)["action"] == "added"
    with (folder / "tracker.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(r["id"], r["status"], r["applied_at"]) for r in rows] == [(OPENING, "applied", "2026-10-01")]
    assert one(gate_on(env, "2026-10-05", "--json"))["reason"] == "nothing due"
    due = one(gate_on(env, "2026-10-11", "--json"))
    assert due["filed"] is True and due["followups"] == [OPENING]


def test_a_stale_application_is_reported_once_not_on_every_day(tmp_path):
    # A stale row is named by the card once; later days stay silent about it until the user closes it.
    env, folder = env_with_project(tmp_path, rows=[STALE_ROW])
    kanban_stub(env, tmp_path)
    first = one(gate_on(env, "2026-10-20", "--json"))
    assert first["filed"] is True and first["stale_reported"] == ["JOB-20260801-acme-analyst"]
    assert first["followups"] == [], "a stale row is never also a follow-up card"
    second = gate_on(env, "2026-10-21", "--json")
    assert one(second)["reason"] == "nothing due", "the dead application must not get a second card"
    plain = gate_on(env, "2026-10-22")
    assert (plain.returncode, plain.stdout) == (0, "")


def test_a_closed_stale_row_stops_being_reported_and_an_open_follow_up_keeps_its_card(tmp_path):
    quiet = ("2026-09-01,JOB-20260901-beta-analyst,Beta,Analyst,applied,portal,78,"
             "https://jobs.lever.co/beta/2f1c9a7e-5b1d-4c2a-9e8f-1a2b3c4d5e6f/apply,,2026-09-01,,0,,,,")
    env, folder = env_with_project(tmp_path, rows=[STALE_ROW, quiet])
    kanban_stub(env, tmp_path)
    day1 = one(gate_on(env, "2026-10-20", "--json"))
    assert day1["stale_reported"] == ["JOB-20260801-acme-analyst"]
    day2 = one(gate_on(env, "2026-10-21", "--json"))
    assert day2["filed"] is True and day2["followups"] == ["JOB-20260901-beta-analyst"]
    assert day2["stale_reported"] == [], "the stale row is not named again"
    update = subprocess.run([sys.executable, str(TRACKER), "update", "--project", str(folder),
                             "--id", "JOB-20260801-acme-analyst", "--status", "no_response", "--today", "2026-10-22"],
                            capture_output=True, text=True, timeout=120)
    assert update.returncode == 0, update.stderr
    day3 = one(gate_on(env, "2026-10-23", "--json"))
    assert day3["stale_reported"] == [] and day3["followups"] == ["JOB-20260901-beta-analyst"]


def test_a_repeated_record_never_adds_or_moves_a_row(tmp_path):
    env, folder = env_with_project(tmp_path, rows=None)
    kanban_stub(env, tmp_path)
    submission = submitted_opening(folder, "2026-10-01")
    first = subprocess.run([sys.executable, str(RECORD), str(submission), "--today", "2026-10-01", "--json"],
                           capture_output=True, text=True, timeout=120)
    assert first.returncode == 0, first.stdout + first.stderr
    again = subprocess.run([sys.executable, str(RECORD), str(submission), "--today", "2026-10-03", "--json"],
                           capture_output=True, text=True, timeout=120)
    assert again.returncode == 0 and json.loads(again.stdout)["action"] == "unchanged"
    with (folder / "tracker.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(r["id"], r["status"], r["applied_at"]) for r in rows] == [(OPENING, "applied", "2026-10-01")]


def test_a_manual_kit_is_recorded_as_manual_application(tmp_path):
    # A kit-only opening (apply link unverified) is recorded as manual_application once its kit exists on disk.
    env, folder = env_with_project(tmp_path, rows=None)
    kanban_stub(env, tmp_path)
    submission = submitted_opening(folder, "2026-10-01")
    kit = {"id": OPENING, "result": "NOT_POSSIBLE", "method": "other", "filled_fields": [], "pending_questions": [],
           "screenshots": [], "reason": "apply link unverified: kit only", "manual_kit": "application/kit.md"}
    submission.write_text(json.dumps(kit), encoding="utf-8")
    submission.parent.joinpath("kit.md").unlink()
    refused = subprocess.run([sys.executable, str(RECORD), str(submission), "--today", "2026-10-01", "--json"],
                             capture_output=True, text=True, timeout=120)
    assert refused.returncode == 1 and "check_submission refused" in refused.stdout, refused.stdout
    assert not (folder / "tracker.csv").exists(), "a refused record writes no row"
    submission.parent.joinpath("kit.md").write_text("Answers ready to copy.\n", encoding="utf-8")
    recorded = subprocess.run([sys.executable, str(RECORD), str(submission), "--today", "2026-10-01", "--json"],
                              capture_output=True, text=True, timeout=120)
    assert recorded.returncode == 0, recorded.stdout + recorded.stderr
    with (folder / "tracker.csv").open(encoding="utf-8", newline="") as handle:
        assert [r["status"] for r in csv.DictReader(handle)] == ["manual_application"]


# --- manual outcomes, email applications, status after a record, and every project of the manager -----------------

def tracker_cli(folder, *args):
    return subprocess.run([sys.executable, str(TRACKER), *args, "--project", str(folder), "--today", "2026-10-12"],
                          capture_output=True, text=True, timeout=120)


def test_i_applied_with_no_row_is_recorded_by_update_create(tmp_path):
    # The user applied from the kit and says "I applied": the opening has no tracker row yet. The update used to exit 1.
    env, folder = env_with_project(tmp_path, rows=None)
    opening = folder / "openings" / OPENING
    opening.mkdir(parents=True)
    (opening / "opening.md").write_text(f"---\nid: {OPENING}\ncompany: Acme\nrole: Data analyst\n"
                                        f"apply_url: {ACME_APPLY}\n---\nPosting.\n", encoding="utf-8")
    refused = tracker_cli(folder, "update", "--id", OPENING, "--status", "applied")
    assert refused.returncode == 1 and "update --create" in refused.stderr, refused.stderr
    created = tracker_cli(folder, "update", "--id", OPENING, "--status", "applied", "--create")
    assert created.returncode == 0, created.stderr
    assert json.loads(created.stdout)["created"] is True
    with (folder / "tracker.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(r["id"], r["company"], r["role"], r["status"], r["applied_at"], r["apply_url"]) for r in rows] == [
        (OPENING, "Acme", "Data analyst", "applied", "2026-10-12", ACME_APPLY)]


def test_create_without_an_opening_file_refuses_and_writes_nothing(tmp_path):
    env, folder = env_with_project(tmp_path, rows=None)
    proc = tracker_cli(folder, "update", "--id", OPENING, "--status", "applied", "--create")
    assert proc.returncode == 1 and "opening.md is missing" in proc.stderr, proc.stderr
    assert not (folder / "tracker.csv").exists()


def test_an_email_application_is_recorded_with_its_mailto_address(tmp_path):
    # NOT_POSSIBLE with a mailto apply_url and method email: the record returned rc 1 ("must be an http or https link").
    env, folder = env_with_project(tmp_path, rows=None)
    kanban_stub(env, tmp_path)
    submission = submitted_opening(folder, "2026-10-01")
    opening = submission.parent.parent
    (opening / "opening.md").write_text(f"---\nid: {OPENING}\ncompany: Acme\nrole: Data analyst\n"
                                        "apply_url: mailto:jobs@acme.example\n---\nPosting.\n", encoding="utf-8")
    kit = {"id": OPENING, "result": "NOT_POSSIBLE", "method": "email", "filled_fields": [], "pending_questions": [],
           "screenshots": [], "reason": "the posting asks for an email application", "manual_kit": "application/kit.md"}
    submission.write_text(json.dumps(kit), encoding="utf-8")
    recorded = subprocess.run([sys.executable, str(RECORD), str(submission), "--today", "2026-10-01", "--json"],
                              capture_output=True, text=True, timeout=120)
    assert recorded.returncode == 0, recorded.stdout + recorded.stderr
    with (folder / "tracker.csv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [(r["status"], r["apply_url"], r["channel"]) for r in rows] == [
        ("manual_application", "mailto:jobs@acme.example", "email")]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "mailto:jobs@acme.example"])
def test_a_scheme_other_than_web_or_email_is_still_refused_as_apply_url(tmp_path, url):
    # mailto is accepted only on the email channel; javascript: never, on any channel.
    env, folder = env_with_project(tmp_path, rows=None)
    proc = tracker_cli(folder, "add", "--id", OPENING, "--company", "Acme", "--role", "Analyst", "--status", "applied",
                       "--apply-url", url, "--channel", "portal")
    assert proc.returncode == 1 and "must be an http or https link" in proc.stderr, proc.stderr
    proc = tracker_cli(folder, "add", "--id", OPENING, "--company", "Acme", "--role", "Analyst", "--status", "applied",
                       "--apply-url", "javascript:alert(1)", "--channel", "email")
    assert proc.returncode == 1 and "must be an http or https link" in proc.stderr, proc.stderr


def test_a_recorded_submit_leaves_status_json_at_applied(tmp_path):
    # SUBMITTED recorded: the tracker says applied and the status file used to stay at ready.
    env, folder = env_with_project(tmp_path, rows=None)
    kanban_stub(env, tmp_path)
    submission = submitted_opening(folder, "2026-10-01")
    status_file = submission.parent.parent / "status.json"
    assert json.loads(status_file.read_text(encoding="utf-8"))["status"] == "ready"
    recorded = subprocess.run([sys.executable, str(RECORD), str(submission), "--today", "2026-10-01", "--json"],
                              capture_output=True, text=True, timeout=120)
    assert recorded.returncode == 0, recorded.stdout + recorded.stderr
    doc = json.loads(status_file.read_text(encoding="utf-8"))
    assert doc["status"] == "applied"
    assert [h["status"] for h in doc["history"]] == ["ready", "applied"], "earlier lines are kept, one line added"
    assert doc["history"][-1]["by"] == "jobs-applier"
    again = subprocess.run([sys.executable, str(RECORD), str(submission), "--today", "2026-10-03", "--json"],
                           capture_output=True, text=True, timeout=120)
    assert again.returncode == 0 and json.loads(again.stdout)["action"] == "unchanged"
    assert [h["status"] for h in json.loads(status_file.read_text(encoding="utf-8"))["history"]] == ["ready", "applied"]


def add_project(env, slug: str, folder: Path, rows) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "profile.md").write_text("---\nsearch: active\nfollow_up_days: 10\nstale_days: 60\n---\n",
                                       encoding="utf-8")
    (folder / "tracker.csv").write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    done = subprocess.run(["hermes", "-p", "jobs", "project", "create", slug.title(), str(folder), "--slug", slug],
                          capture_output=True, text=True, env=env)
    assert done.returncode == 0, done.stderr


def test_every_project_gets_its_own_follow_up_card_and_one_per_day(tmp_path):
    # Two projects, each with an applied row 49 days old. The cron runs with no --project: the second project got
    # no card before (only the active project was checked).
    env, search = env_with_project(tmp_path, rows=[QUIET])
    beta = tmp_path / "beta"
    add_project(env, "beta", beta, ["2026-09-01,JOB-20260901-beta-analyst,Beta,Analyst,applied,portal,70,"
                                    "https://jobs.lever.co/beta/2f1c9a7e-5b1d-4c2a-9e8f-1a2b3c4d5e6f/apply,,"
                                    "2026-09-01,,0,,,,"])
    first = json.loads(gate(env, "--json").stdout)["results"]
    by_project = {r["project"]: r for r in first}
    assert set(by_project) == {"search", "beta"}, first
    assert by_project["search"]["filed"] is True and by_project["beta"]["filed"] is True, first
    assert by_project["beta"]["followups"] == ["JOB-20260901-beta-analyst"]
    assert by_project["beta"]["key"] == "jobs:inbox:beta:2026-10-20"
    cards = json.loads((tmp_path / "hermes" / "cards-jobs.json").read_text(encoding="utf-8"))
    assert sorted(cards) == ["jobs:inbox:beta:2026-10-20", "jobs:inbox:search:2026-10-20"], cards
    assert cards["jobs:inbox:beta:2026-10-20"]["project"] == "beta"
    gate(env)  # the same day again: the keys hold, no third card
    cards = json.loads((tmp_path / "hermes" / "cards-jobs.json").read_text(encoding="utf-8"))
    assert len(cards) == 2, cards
    later = {r["project"]: r for r in json.loads(gate(env, "--json").stdout)["results"]}
    assert later["beta"]["key"] == "jobs:inbox:beta:2026-10-20"


def test_a_paused_project_does_not_stop_the_other_projects_card(tmp_path):
    env, search = env_with_project(tmp_path, rows=[QUIET])
    (search / "profile.md").write_text("---\nsearch: paused\n---\n", encoding="utf-8")
    beta = tmp_path / "beta"
    add_project(env, "beta", beta, ["2026-09-01,JOB-20260901-beta-analyst,Beta,Analyst,applied,portal,70,"
                                    "https://jobs.lever.co/beta/2f1c9a7e-5b1d-4c2a-9e8f-1a2b3c4d5e6f/apply,,"
                                    "2026-09-01,,0,,,,"])
    by_project = {r["project"]: r for r in json.loads(gate(env, "--json").stdout)["results"]}
    assert by_project["search"] == {"project": "search", "filed": False, "reason": "paused"}, by_project
    assert by_project["beta"]["filed"] is True, by_project


def test_the_scheduled_mail_check_files_a_card_each_slot_even_with_nothing_due(tmp_path):
    """--check-mail (cron Mon-Sat 9:00 and 17:00): new mail is read on schedule, not only when a follow-up is due."""
    env, _ = env_with_project(tmp_path, rows=[])
    inbox = Path(env["HERMES_HOME"]) / "profiles" / "jobs-inbox"
    off = one(gate(env, "--json", "--check-mail", "--hour", "09"))
    assert off == {"project": "search", "filed": False, "reason": "mail not connected"}
    assert "connect my mail" in gate(env, "--check-mail", "--hour", "09").stdout
    (inbox / "mail.json").write_text('{"email": "cand@example.com"}')
    morning = one(gate(env, "--json", "--check-mail", "--hour", "09"))
    assert morning["filed"] is True and morning["key"] == "jobs:inbox:search:2026-10-20T09"
    again = one(gate(env, "--json", "--check-mail", "--hour", "09"))
    assert again["id"] == morning["id"], "a rerun of the same slot reuses its card"
    evening = one(gate(env, "--json", "--check-mail", "--hour", "17"))
    assert evening["filed"] is True and evening["id"] != morning["id"]
    body = one(gate(env, "--json", "--check-mail", "--hour", "17", "--dry-run"))["body"]
    assert "Mode: INBOX" in body and "since: 2026-10-19" in body
    assert (gate(env, "--check-mail", "--hour", "17").stdout) == "", "a filed check posts nothing to the channel"
    assert one(gate(env, "--json"))["reason"] == "nothing due", "without --check-mail the gate is unchanged"
