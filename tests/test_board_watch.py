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


def test_needs_input_block_is_posted_once_with_its_reason(tmp_path):
    now = int(time.time())
    env = setup(tmp_path, [{"id": "t1", "status": "blocked", "assignee": "jobs", "title": "digest"}],
                events={"t1": blocked("needs_input", "80/100 - Dev at Acme\nReply: apply", now)})
    first = run(env)
    assert first.returncode == 0
    assert "jobs board: 1 card(s) for you" in first.stdout
    assert "t1 | jobs | needs your answer: digest" in first.stdout
    assert "    Reply: apply" in first.stdout
    assert run(env).stdout == ""


def test_subscribed_card_is_left_to_its_chat_until_stale(tmp_path):
    now = int(time.time())
    env = setup(tmp_path, [{"id": "t1", "status": "blocked", "assignee": "web", "title": "accept"}],
                events={"t1": blocked("needs_input", "publish?", now)},
                subs={"t1": [{"platform": "tui", "chat_id": "s"}]})
    assert run(env).stdout == ""


def test_other_blocks_and_silent_runs_wait_for_hours(tmp_path):
    now = int(time.time())
    old = now - 30 * 3600
    cards = [{"id": "t1", "status": "blocked", "assignee": "web-qa", "title": "qa"},
             {"id": "t2", "status": "running", "assignee": "web-ui", "title": "ui", "started_at": old},
             {"id": "t3", "status": "running", "assignee": "web-ui", "title": "fresh", "started_at": now}]
    env = setup(tmp_path, cards, events={"t1": blocked("capability", "no browser", now)})
    out = run(env).stdout
    assert "t1" not in out and "t3" not in out
    assert "t2 | web-ui | running with no activity for 30h: ui" in out


def test_unreadable_board_exits_1(tmp_path):
    env = setup(tmp_path, [])
    (tmp_path / "hermes.json").write_text("{}")
    assert run(env).returncode == 1
