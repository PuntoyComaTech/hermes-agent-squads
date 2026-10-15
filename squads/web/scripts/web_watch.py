#!/usr/bin/env python3
"""Report kanban cards that need attention on the web squad's board (cron, --no-agent).

Usage:
  web_watch.py [--board web] [--hours 24] [--profile <profile>] [--hermes-bin <path>] [--json]

Hermes delivers non-empty stdout to the lead's Bot Chat verbatim and stays silent on an empty one,
so this script prints only what needs a human: cards in `blocked` for longer than --hours (counted
from the last block event via `kanban show --json`) and `running` cards with no activity in that
window (from started_at, else created_at). The reported set is fingerprinted with
`gate_lib.changed`, so the same cards are not re-printed on every run.

Exit 0 the board was read, 1 the board or gate_lib could not be read (the delivery turns that into
one error alert, so a broken watchdog is never silent).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

WATCH_STATUSES = ("blocked", "running")


def home() -> Path:
    raw = os.environ.get("HERMES_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".hermes"


def gate_lib():
    """gate_lib.py beside this script (squadctl copies it next to each cron script) or in a scripts/ dir."""
    try:
        import gate_lib as mod
        return mod
    except ImportError:
        pass
    h = home()
    root = h.parent.parent if h.parent.name == "profiles" else h
    here = Path(__file__).resolve()
    cands = [here.parent, h / "scripts", root / "scripts"]
    if len(here.parents) > 3:
        cands.append(here.parents[3] / "scripts")  # a repo checkout
    for cand in cands:
        if (cand / "gate_lib.py").is_file():
            sys.path.insert(0, str(cand))
            import gate_lib as mod
            return mod
    raise RuntimeError("gate_lib.py not found (looked beside the script, in the profile scripts dir, "
                       "in the hermes root and in the checkout's scripts dir)")


def to_epoch(value) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def read_cards(argv: list[str], timeout: int = 120) -> list:
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(argv[:3])} failed: {(proc.stderr or proc.stdout).strip()[:300]}")
    data = json.loads(proc.stdout or "[]")
    if isinstance(data, dict):
        data = data.get("tasks") or data.get("items") or []
    return [c for c in data if isinstance(c, dict)]


def last_block_epoch(binary: str, profile: str | None, board: str, card_id: str) -> float | None:
    """Epoch of the newest `blocked` event of a card, from `kanban show --json`; None when unreadable."""
    argv = [binary, *(["-p", profile] if profile else []), "kanban", "--board", board, "show", card_id, "--json"]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        data = json.loads(proc.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    events = [e for e in (data.get("events") or []) if isinstance(e, dict) and e.get("kind") == "blocked"]
    return max((epoch for epoch in (to_epoch(e.get("created_at")) for e in events) if epoch), default=None)


def idle_since(card: dict, binary: str, profile: str | None, board: str) -> tuple[float | None, str]:
    """(epoch the wait started, its source): the last block event for a blocked card, else started_at/created_at."""
    if card.get("status") == "blocked":
        epoch = last_block_epoch(binary, profile, board, str(card.get("id") or ""))
        if epoch:
            return epoch, "last block event"
    for key in ("started_at", "created_at"):
        epoch = to_epoch(card.get(key))
        if epoch:
            return epoch, key
    return None, ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Report blocked or stale cards on the web squad's kanban board.",
        epilog="Exit 0 board read, 1 board or gate_lib unreadable.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--board", default="web", help="kanban board slug (default: web)")
    p.add_argument("--hours", type=float, default=24, help="hours before a card counts as stale (default: 24)")
    p.add_argument("--profile", help="run the kanban CLI in this Hermes profile (default: the profile this runs in)")
    p.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN") or "hermes",
                   help="hermes executable (default: $HERMES_BIN, else `hermes` on PATH)")
    p.add_argument("--json", action="store_true", help="machine-readable output, never gated")
    args = p.parse_args(argv)

    binary = shutil.which(args.hermes_bin) or (args.hermes_bin if os.path.isabs(args.hermes_bin) else None)
    if not binary:
        print(f"web-watch: hermes executable not found ({args.hermes_bin})", file=sys.stderr)
        return 1
    cmd = [binary, *(["-p", args.profile] if args.profile else []), "kanban", "--board", args.board, "list", "--json"]
    try:
        cards = read_cards(cmd)
    except (OSError, subprocess.SubprocessError, ValueError, RuntimeError) as exc:
        print(f"web-watch: cannot read board {args.board}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    now = time.time()
    findings = []
    for card in cards:
        if card.get("status") not in WATCH_STATUSES:
            continue
        epoch, source = idle_since(card, binary, args.profile, args.board)
        if not epoch:
            continue
        hours_idle = (now - epoch) / 3600
        if hours_idle >= args.hours:
            findings.append({"id": card.get("id"), "title": card.get("title"), "status": card.get("status"),
                             "assignee": card.get("assignee"), "hours": round(hours_idle, 1), "since": source})
    if not findings:
        return 0
    if args.json:
        print(json.dumps({"board": args.board, "cards": findings}, indent=2))
        return 0
    try:
        gate = gate_lib()
    except RuntimeError as exc:
        print(f"web-watch: {exc}", file=sys.stderr)
        return 1
    if not gate.changed("web_watch", gate.fingerprint(sorted(f["id"] for f in findings)),
                        directory=home() / "local" / "state"):
        return 0
    lines = [f"web board: {len(findings)} card(s) need attention"]
    for f in findings:
        note = "blocked, no answer" if f["status"] == "blocked" else "running with no activity"
        lines.append(f"- {f['id']} | {f['status']} | {f['assignee'] or 'unassigned'} | {note} for {f['hours']:g}h: {f['title']}")
    lines.append("Reply here to unblock, or ask the builder if a profile seems stuck.")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
