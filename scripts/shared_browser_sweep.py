#!/usr/bin/env python3
"""Close tabs left on the shared signed-in browser by bot runs that crashed or were killed (no-agent cron).

The shared-browser-tabs plugin closes each run's tab when its turn ends. This sweep is the backstop: it stops
harness daemons whose lease is older than --max-idle-hours or whose Hermes process is gone, then closes every page
no daemon holds, in two checks --settle seconds apart. One blank page always stays. Silent on success, so the cron
delivers nothing; an unreachable browser is reported on stderr with exit 1. --verbose prints the counts.

usage: sweep.py [--cdp-url URL] [--max-idle-hours H] [--settle S] [--verbose]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import shared_browser_tabs as tabs  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    p.add_argument("--cdp-url", default=os.environ.get("BROWSER_CDP_URL") or "http://127.0.0.1:9333",
                   help="loopback CDP URL of the shared browser (default: BROWSER_CDP_URL or http://127.0.0.1:9333)")
    p.add_argument("--max-idle-hours", type=float, default=3.0, help="lease age that counts as abandoned (default 3)")
    p.add_argument("--settle", type=float, default=30.0,
                   help="seconds between the two free-page checks (default 30: a tab another bot just created has "
                        "time to attach)")
    p.add_argument("--verbose", action="store_true", help="print the result even when nothing was closed")
    a = p.parse_args(argv)
    port = tabs.loopback_port(a.cdp_url)
    if port is None:
        print(json.dumps({"error": f"not a loopback CDP URL: {a.cdp_url}"}), file=sys.stderr)
        return 2
    try:
        result = tabs.sweep(port, max_idle=a.max_idle_hours * 3600, settle=a.settle)
    except OSError as exc:
        print(json.dumps({"error": f"shared browser not reachable on port {port}: {exc}"}), file=sys.stderr)
        return 1
    if a.verbose:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
