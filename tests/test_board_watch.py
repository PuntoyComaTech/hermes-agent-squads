"""board_watch.py: which blocked or stale cards reach the manager's Bot Chat, once each."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "board_watch.py"

STUB = '''#!/usr/bin/env python3
import json, sys
data = json.load(open(sys.argv[0] + ".json"))
args = sys.argv[1:]
cmd = args[3]
if cmd == "list":
    print(json.dumps(data["cards"]))
elif cmd == "show":
    print(json.dumps({"events": data["events"].get(args[4], [])}))
elif cmd == "notify-list":
    print(json.dumps(data["subs"].get(args[4], [])))
'''


def setup(tmp: Path, cards, events=None, subs=None) -> dict:
    stub = tmp / "hermes"
    stub.write_text(STUB)
    stub.chmod(0o755)
    (tmp / "hermes.json").write_text(json.dumps({"cards": cards, "events": events or {}, "subs": subs or {}}))
    home = tmp / "profiles" / "jobs"
    home.mkdir(parents=True)
    return {**os.environ, "HERMES_HOME": str(home), "HERMES_BIN": str(stub)}


def run(env):
    return subprocess.run([sys.executable, "-I", str(SCRIPT)], capture_output=True, text=True, env=env, timeout=60)


def blocked(kind, reason, at):
    return [{"kind": "blocked", "created_at": at, "payload": {"kind": kind, "reason": reason}}]


def test_needs_input_block_is_posted_once_as_its_own_message(tmp_path):
    """The manager's digest is the block reason: it reaches the phone as written, with its CV upload line intact."""
    now = int(time.time())
    reason = "80/100 · Dev - Acme · remote\nhttps://jobs.lever.co/acme/1\nMEDIA:/p/openings/JOB-1/application/cv_ats.pdf"
    env = setup(tmp_path, [{"id": "t1", "status": "blocked", "assignee": "jobs", "title": "Digest: JOB-1"}],
                events={"t1": blocked("needs_input", reason, now)})
    first = run(env)
    assert first.returncode == 0
    assert first.stdout.strip() == reason, "no board header, no card id and no indent around the manager's message"
    assert run(env).stdout == ""


def test_two_digests_with_a_cv_each_go_out_in_two_runs(tmp_path):
    """Attachments land after the text: two digests in one message would leave two CVs nobody can tell apart."""
    now = int(time.time())
    cards = [{"id": "t1", "status": "blocked", "assignee": "jobs", "title": "Digest: JOB-1"},
             {"id": "t2", "status": "blocked", "assignee": "jobs", "title": "Digest: JOB-2"}]
    env = setup(tmp_path, cards, events={"t1": blocked("needs_input", "Acme\nMEDIA:/p/1/cv_ats.pdf", now),
                                         "t2": blocked("needs_input", "Globex\nMEDIA:/p/2/cv_ats.pdf", now)})
    first, second = run(env).stdout, run(env).stdout
    assert first.count("MEDIA:") == 1 and second.count("MEDIA:") == 1
    assert {first.split()[0], second.split()[0]} == {"Acme", "Globex"}
    assert run(env).stdout == ""


def test_a_worker_question_says_who_asks(tmp_path):
    now = int(time.time())
    env = setup(tmp_path, [{"id": "t9", "status": "blocked", "assignee": "jobs-applier", "title": "Apply JOB-2"}],
                events={"t9": blocked("needs_input", "The form asks for a salary expectation in USD.", now)})
    out = run(env).stdout
    assert out.startswith("The form asks for a salary expectation in USD.")
    assert "(jobs-applier: Apply JOB-2 · t9)" in out


def test_a_desktop_subscription_does_not_hide_the_question_from_the_owners_channel(tmp_path):
    """The bug: a chain filed from a Desktop session hands its `tui` subscription to every card it spawns, so the
    watch skipped every digest and the owner, reading the squad from Discord, had to ask for each one."""
    now = int(time.time())
    env = setup(tmp_path, [{"id": "t1", "status": "blocked", "assignee": "jobs", "title": "Digest: JOB-1"}],
                events={"t1": blocked("needs_input", "74/100 · Dev - Acme", now)},
                subs={"t1": [{"platform": "tui", "chat_id": "20261023_210732_3557cb"}]})
    assert run(env).stdout.strip() == "74/100 · Dev - Acme"


def test_a_card_followed_in_a_messaging_chat_is_left_to_that_chat_until_stale(tmp_path):
    now = int(time.time())
    env = setup(tmp_path, [{"id": "t1", "status": "blocked", "assignee": "web", "title": "accept"}],
                events={"t1": blocked("needs_input", "publish?", now)},
                subs={"t1": [{"platform": "discord", "chat_id": "777"}]})
    assert run(env).stdout == ""


def test_other_blocks_and_silent_runs_wait_for_hours(tmp_path):
    now = int(time.time())
    old = now - 30 * 3600
    cards = [{"id": "t1", "status": "blocked", "assignee": "web-qa", "title": "qa"},
             {"id": "t2", "status": "running", "assignee": "web-ui", "title": "ui", "started_at": old},
             {"id": "t3", "status": "running", "assignee": "web-ui", "title": "fresh", "started_at": now}]
    events = {"t1": blocked("capability", "no browser", now), "t4": blocked("capability", "deploy token expired", old)}
    cards.append({"id": "t4", "status": "blocked", "assignee": "web-deployer", "title": "deploy"})
    env = setup(tmp_path, cards, events=events)
    out = run(env).stdout
    assert "t1" not in out and "t3" not in out
    assert "ui (web-ui · t2): running with no activity for 30h" in out
    assert "deploy (web-deployer · t4): blocked 30h - deploy token expired" in out, "the reason says what is wrong"


def test_unreadable_board_exits_1(tmp_path):
    env = setup(tmp_path, [])
    (tmp_path / "hermes.json").write_text("{}")
    assert run(env).returncode == 1
