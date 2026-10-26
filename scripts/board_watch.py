#!/usr/bin/env python3
"""Print the cards of a squad board that need the owner, for the manager's channel or Bot Chat.

Reported once per wait (state: $HERMES_HOME/local/state/board_watch.json):
  - `blocked` with kind `needs_input` (or untyped), at once, with the block reason, unless the card has a
    notify subscription on a messaging platform (the chain started in that chat, so it already got the event). A
    Desktop or CLI subscription (`tui`, `cli`) does not count: a chain filed from a Desktop session inherits it on
    every card, and the owner who reads the squad from a phone channel would never see the question;
  - any other `blocked`, or `running` with no activity, after --hours;
  - `triage`, at once: Hermes's unblock-loop detector moved the card there after the same block came back twice.
    `unblock` and `promote` refuse a triage card, and the auto-decomposer would rewrite its title and body before
    the next run, so the owner (or the manager) decides it: the line names the last block reason;
  - a block that follows `gave_up` (the worker crashed until the dispatcher stopped retrying) carries the crash
    reason, so a host failure is not read as the bot asking something.

The text is read on a phone. A card that asks the owner prints its block reason as written (the reason is the
message), and a worker's question names the worker and the card; stale cards get one line each with the first line
of their reason. A `MEDIA:<path>` line in a reason is kept, so the delivery attaches that file. The delivery sends
every attachment after the text, so a run prints at most ONE card that carries a file (the rest wait for the next
run); cards without a file are printed together.

Cron runs it with --no-agent on each manager: non-empty stdout is delivered (`notify: true`: the connected channel,
else Bot Chat), empty stdout sends nothing. Stdlib only: the cron runs it with the system python3.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

STATE = "board_watch"
KEEP = 200  # reported keys kept in the state file
LOCAL_SURFACES = frozenset({"tui", "cli", "local", "desktop"})  # subscriptions the owner does not read away from the desk


def home() -> Path:
    raw = os.environ.get("HERMES_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".hermes"


def to_epoch(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def hermes_json(argv: list[str], default):
    """JSON stdout of a hermes command; `default` when it fails or prints no JSON."""
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        return json.loads(proc.stdout) if proc.returncode == 0 and proc.stdout.strip() else default
    except (OSError, subprocess.SubprocessError, ValueError):
        return default


BLOCK_KINDS = ("blocked", "gave_up", "block_loop_detected")


def last_block(base: list[str], card_id: str) -> dict:
    """{'epoch', 'kind', 'reason', 'event'} of the newest blocked, gave_up or block_loop_detected event; {} when
    unreadable. A gave_up (the dispatcher stopped retrying a crashing worker) has no kind: its reason is the error."""
    data = hermes_json([*base, "show", card_id, "--json"], {})
    events = [e for e in (data.get("events") or []) if isinstance(e, dict) and e.get("kind") in BLOCK_KINDS]
    if not events:
        return {}
    newest = max(events, key=lambda e: to_epoch(e.get("created_at")) or 0)
    payload = newest.get("payload") if isinstance(newest.get("payload"), dict) else {}
    reason = (payload.get("reason") or "").strip()
    if newest.get("kind") == "gave_up":
        error = " ".join(str(payload.get("error") or "").split())
        reason = f"the worker crashed {payload.get('failures') or ''} times and the dispatcher gave up: {error[:240]}"
    return {"epoch": to_epoch(newest.get("created_at")), "kind": payload.get("kind"),
            "reason": reason, "event": newest.get("kind")}


def subscribed(base: list[str], card_id: str) -> bool:
    """True when a messaging chat (Discord, Telegram, ...) already gets this card's events."""
    subs = hermes_json([*base, "notify-list", card_id, "--json"], [])
    return isinstance(subs, list) and any(
        isinstance(s, dict) and str(s.get("platform") or "").lower() not in LOCAL_SURFACES for s in subs)


def load_state(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    return [str(k) for k in data.get("reported", [])] if isinstance(data, dict) else []


def save_state(path: Path, keys: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"reported": keys[-KEEP:]}, indent=2) + "\n")
    os.replace(tmp, path)


def findings(cards: list[dict], base: list[str], hours: float, now: float) -> list[dict]:
    out = []
    for card in cards:
        status, cid = card.get("status"), str(card.get("id") or "")
        if status not in ("blocked", "running", "triage") or not cid:
            continue
        block = last_block(base, cid) if status in ("blocked", "triage") else {}
        if status == "triage":
            if block.get("event") != "block_loop_detected":
                continue  # a card filed into triage on purpose is the specifier's, not the owner's
            out.append({"id": cid, "title": card.get("title") or "", "assignee": card.get("assignee") or "unassigned",
                        "status": status, "note": "loop", "reason": block.get("reason") or "",
                        "key": f"{cid}@{int(block.get('epoch') or 0)}"})
            continue
        since = block.get("epoch") or to_epoch(card.get("started_at")) or to_epoch(card.get("created_at"))
        if not since:
            continue
        idle = (now - since) / 3600
        asks_user = status == "blocked" and block.get("kind") in (None, "needs_input") and block.get("event") != "gave_up"
        if asks_user and not subscribed(base, cid):
            note = "asks"
        elif idle >= hours:
            note = f"blocked {idle:.0f}h" if status == "blocked" else f"running with no activity for {idle:.0f}h"
        else:
            continue
        out.append({"id": cid, "title": card.get("title") or "", "assignee": card.get("assignee") or "unassigned",
                    "status": status, "note": note, "reason": block.get("reason") or "",
                    "key": f"{cid}@{int(since)}"})
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Report the cards of a squad board that wait on the manager's Bot Chat.",
                                epilog="Exit 0 board read, 1 board unreadable.")
    p.add_argument("--board", help="board slug (default: the profile name, which is the squad key on a manager)")
    p.add_argument("--hours", type=float, default=24,
                   help="hours before another blocked or a silent running card is reported (default: 24)")
    p.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN") or "hermes",
                   help="hermes executable (default: $HERMES_BIN, else `hermes` on PATH)")
    p.add_argument("--json", action="store_true", help="print every finding as JSON; state is not read or written")
    args = p.parse_args(argv)

    board = args.board or home().name
    binary = shutil.which(args.hermes_bin) or (args.hermes_bin if os.path.isabs(args.hermes_bin) else None)
    if not binary:
        print(f"board-watch: hermes executable not found ({args.hermes_bin})", file=sys.stderr)
        return 1
    base = [binary, "kanban", "--board", board]
    cards = hermes_json([*base, "list", "--json"], None)
    if isinstance(cards, dict):
        cards = cards.get("tasks") or cards.get("items")
    if not isinstance(cards, list):
        print(f"board-watch: cannot read board {board}", file=sys.stderr)
        return 1

    found = findings([c for c in cards if isinstance(c, dict)], base, args.hours, time.time())
    if args.json:
        print(json.dumps({"board": board, "cards": found}, indent=2))
        return 0
    state = home() / "local" / "state" / f"{STATE}.json"
    reported = load_state(state)
    new = [f for f in found if f["key"] not in reported]
    if not new:
        return 0
    manager = home().name
    blocks, sent, with_file = [], [], False
    for f in new:
        carries = "MEDIA:" in f["reason"]
        if carries and with_file:
            continue  # its file would land under another card's text: next run
        with_file = with_file or carries
        if f["note"] == "asks" and f["reason"]:
            # the reason is the message; a worker's question also says who asks, so the reply can be routed
            tail = "" if f["assignee"] == manager else f"\n({f['assignee']}: {f['title']} · {f['id']})"
            blocks.append(f["reason"] + tail)
        elif f["note"] == "asks":
            blocks.append(f"{f['title']} ({f['assignee']} · {f['id']}) is waiting for you")
        elif f["note"] == "loop":
            first = next((ln.strip() for ln in f["reason"].splitlines() if ln.strip() and "MEDIA:" not in ln), "")
            blocks.append(f"{f['title']} ({f['assignee']} · {f['id']}) blocked twice for the same reason and went to "
                          f"triage; nothing runs it until you decide" + (f": {first}" if first else ""))
        else:
            first = next((ln.strip() for ln in f["reason"].splitlines() if ln.strip() and "MEDIA:" not in ln), "")
            blocks.append(f"{f['title']} ({f['assignee']} · {f['id']}): {f['note']}" + (f" - {first}" if first else ""))
        sent.append(f["key"])
    print("\n\n".join(blocks))
    save_state(state, reported + sent)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
