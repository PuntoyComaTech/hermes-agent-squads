#!/usr/bin/env python3
"""Keep the machine awake while the squad board has running cards. Prints nothing.

Cron `<squad>-awake` runs it every 4 minutes with --no-agent on each squad manager. With a running card it starts a
detached hold that expires by itself after --seconds (default 300), so holds overlap while work goes on and end
within 5 minutes of the last card:
  macOS    caffeinate -is -t <seconds>    (idle and system sleep; the display may still sleep)
  Linux    systemd-inhibit --what=idle:sleep sleep <seconds>
  Windows  nothing
An idle sleep freezes the gateway and its Kanban workers; the interrupted worker turn ends with exit 130.
Stdlib only. Exit 0 always: a missing tool or an unreadable board only means no hold this tick.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def running(hermes: str, board: str) -> bool:
    try:
        p = subprocess.run([hermes, "kanban", "--board", board, "list", "--status", "running", "--json"],
                           capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        cards = json.loads(p.stdout) if p.returncode == 0 and p.stdout.strip() else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return False
    if isinstance(cards, dict):
        cards = cards.get("tasks") or cards.get("items") or []
    return isinstance(cards, list) and bool(cards)


def hold_command(platform: str, seconds: int) -> list[str] | None:
    if platform == "darwin" and shutil.which("caffeinate"):
        return ["caffeinate", "-is", "-t", str(seconds)]
    if platform.startswith("linux") and shutil.which("systemd-inhibit"):
        return ["systemd-inhibit", "--what=idle:sleep", "--who=hermes-squads", "--why=Kanban cards running",
                "sleep", str(seconds)]
    return None


def main(argv: list[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(description=doc.split("\n\n")[0], epilog=doc.split("\n\n", 1)[-1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--board", help="board slug (default: the profile name, which is the squad key on a manager)")
    ap.add_argument("--seconds", type=int, default=300, help="length of one hold (default 300)")
    ap.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN") or "hermes",
                    help="hermes executable (default: $HERMES_BIN, else `hermes` on PATH)")
    a = ap.parse_args(argv)
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    cmd = hold_command(sys.platform, a.seconds)
    if cmd is None or not running(a.hermes_bin, a.board or home.name):
        return 0
    spawn(cmd)
    return 0


def spawn(cmd: list[str]) -> None:
    """Start the hold detached: it outlives this cron tick and ends on its own timer."""
    try:
        subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass


if __name__ == "__main__":
    sys.exit(main())
