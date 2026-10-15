#!/usr/bin/env python3
"""Report kanban cards that need attention on the web squad's board (cron, --no-agent).

Usage:
  web_watch.py [--board web] [--hours 24] [--profile <profile>] [--hermes-bin <path>] [--json]

The cron job `web-watch` runs this every 4 hours on the lead. Hermes delivers non-empty stdout to
the lead's Bot Chat verbatim and stays silent on an empty one, so this script prints only what
needs a human: cards in `blocked` for longer than --hours, and `running` cards with no activity in
that window (the same staleness definition `squadctl doctor` uses: now - (started_at or
created_at)). Nothing to report means nothing is printed.

Exit 0 reported or not; 1 the board could not be read (the delivery turns that into one error
alert, so a broken watchdog is never silent).
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

WATCH_STATUSES = ("blocked", "running")


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


def stale(card: dict, hours: float, now: float) -> tuple[float, str]:
    """(idle hours, which timestamp) for a card that is blocked or looks abandoned."""
    if card.get("status") not in WATCH_STATUSES:
        return 0.0, ""
    for key in ("started_at", "created_at"):
        epoch = to_epoch(card.get(key))
        if epoch:
            hours_idle = (now - epoch) / 3600
            if hours_idle >= hours:
                return hours_idle, key
            return 0.0, ""
    return 0.0, ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Report blocked or stale cards on the web squad's kanban board.",
        epilog="Exit 0 reported or not, 1 the board could not be read.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--board", default="web", help="kanban board slug (default: web)")
    p.add_argument("--hours", type=float, default=24, help="hours before a card counts as stale (default: 24)")
    p.add_argument("--profile", help="run the kanban CLI in this Hermes profile (default: the profile this runs in)")
    p.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN") or "hermes",
                   help="hermes executable (default: $HERMES_BIN, else `hermes` on PATH)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
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
        hours_idle, source = stale(card, args.hours, now)
        if hours_idle:
            findings.append({"id": card.get("id"), "title": card.get("title"), "status": card.get("status"),
                             "assignee": card.get("assignee"), "hours": round(hours_idle, 1), "since": source})
    if not findings:
        return 0
    if args.json:
        print(json.dumps({"board": args.board, "cards": findings}, indent=2))
        return 0
    lines = [f"⚠️ web board: {len(findings)} card(s) need attention"]
    for f in findings:
        note = "blocked with no answer" if f["status"] == "blocked" else "running with no activity"
        lines.append(f"- {f['id']} · {f['status']} · {f['assignee'] or 'unassigned'} · {note} for {f['hours']:g}h: {f['title']}")
    lines.append('Reply here to unblock, or ask the builder if a profile seems stuck.')
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
