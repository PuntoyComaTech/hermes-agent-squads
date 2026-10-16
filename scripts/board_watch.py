#!/usr/bin/env python3
"""Print the cards of a squad board that need the manager's Bot Chat.

Reported once per wait (state: $HERMES_HOME/local/state/board_watch.json):
  - `blocked` with kind `needs_input` (or untyped), at once, with the block reason, unless the card has a
    notify subscription (the chain started in a chat, so that chat already got the event);
  - any other `blocked`, or `running` with no activity, after --hours.

Cron runs it with --no-agent on each manager: non-empty stdout goes to the manager's Bot Chat, empty stdout sends
nothing. Stdlib only: the cron runs it with the system python3.
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


def last_block(base: list[str], card_id: str) -> dict:
    """{'epoch', 'kind', 'reason'} of the newest `blocked` event; {} when unreadable."""
    data = hermes_json([*base, "show", card_id, "--json"], {})
    events = [e for e in (data.get("events") or []) if isinstance(e, dict) and e.get("kind") == "blocked"]
    if not events:
        return {}
    newest = max(events, key=lambda e: to_epoch(e.get("created_at")) or 0)
    payload = newest.get("payload") if isinstance(newest.get("payload"), dict) else {}
    return {"epoch": to_epoch(newest.get("created_at")), "kind": payload.get("kind"),
            "reason": (payload.get("reason") or "").strip()}


def subscribed(base: list[str], card_id: str) -> bool:
    subs = hermes_json([*base, "notify-list", card_id, "--json"], [])
    return isinstance(subs, list) and bool(subs)


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
        if status not in ("blocked", "running") or not cid:
            continue
        block = last_block(base, cid) if status == "blocked" else {}
        since = block.get("epoch") or to_epoch(card.get("started_at")) or to_epoch(card.get("created_at"))
        if not since:
            continue
        idle = (now - since) / 3600
        asks_user = status == "blocked" and block.get("kind") in (None, "needs_input")
        if asks_user and not subscribed(base, cid):
            note = "needs your answer"
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
    lines = [f"{board} board: {len(new)} card(s) for you"]
    for f in new:
        lines.append(f"- {f['id']} | {f['assignee']} | {f['note']}: {f['title']}")
        if f["reason"]:
            lines.extend(f"    {line}" for line in f["reason"].splitlines())
    print("\n".join(lines))
    save_state(state, reported + [f["key"] for f in new])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
