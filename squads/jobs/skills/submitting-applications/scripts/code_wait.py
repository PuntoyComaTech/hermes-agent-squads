#!/usr/bin/env python3
"""Ask jobs-inbox for the code a form just mailed the user, and wait for it with the form still open.

  code_wait.py --project P --opening ID --site greenhouse-mail.io [--window 15] [--timeout 480] [--attempt 1]
               [--board jobs] [--json]

An ATS that mails a security code after Submit ("confirm you're a human": Greenhouse sends 8 characters) is not a
CAPTCHA and not a reason for a manual kit: the code is in the user's mailbox, and jobs-inbox reads it (triaging-inbox,
Mode: CODE). This files that card (key `jobs:code:<ID>:<attempt>`, the sender's domain and the window in its body),
waits for jobs-inbox to complete it, and prints the code on stdout for the applier to type into the open form. Nothing
is written to disk: the code lives only in the card result and in this process's output.

Before filing it checks that jobs-inbox is installed and has a Gmail account (`hermes -p jobs-inbox connectors
accounts gmail`), so a missing mailbox costs seconds, not the code's lifetime.

Output (--json): {"outcome", "card", "code"?, "link"?, "reason"?}. outcome is
  code         the code (or the one confirm link) is here: type it, submit again
  no_code      jobs-inbox read the window and found none (or two different codes): request a new code once, then kit
  unavailable  jobs-inbox is not installed, has no Gmail account, or blocked: kit, and the reason says what to connect
  timeout      the card did not finish within --timeout seconds: kit
The applier records the card and the outcome in submission.json `code_request` {card, outcome}: a NOT_POSSIBLE that
names an e-mailed code is refused by check_submission.py without it.

Exit 0 code, 1 no_code, 3 unavailable, 4 timeout, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

INBOX = "jobs-inbox"
ID_RE = re.compile(r"^JOB-\d{8}-[a-z0-9][a-z0-9-]{0,80}$")
SITE_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,}$")
CODE_LINE = re.compile(r"\bcode:\s*([A-Za-z0-9]{4,10})\b")
LINK_LINE = re.compile(r"\blink:\s*(https://\S+)")
EXIT = {"code": 0, "no_code": 1, "unavailable": 3, "timeout": 4}


def hermes_root() -> Path:
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    return home.parent.parent if home.parent.name == "profiles" else home


def run(bin_name: str, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != "HERMES_KANBAN_TASK"}
    env["HERMES_HOME"] = str(hermes_root())
    return subprocess.run([bin_name, *args], capture_output=True, text=True, timeout=timeout, env=env,
                          stdin=subprocess.DEVNULL)


def inbox_ready(bin_name: str) -> str:
    """"" when jobs-inbox can read mail, else why not."""
    if not (hermes_root() / "profiles" / INBOX).is_dir():
        return f"{INBOX} is not installed: squadctl apply jobs --with {INBOX}"
    try:
        done = run(bin_name, "-p", INBOX, "connectors", "accounts", "gmail")
    except (OSError, subprocess.SubprocessError) as exc:
        return f"cannot ask {INBOX} for its mail account: {exc}"
    rows = [ln for ln in done.stdout.splitlines() if ln.strip().lower().startswith("gmail") and "retired" not in ln]
    if done.returncode != 0 or not rows:
        return f"{INBOX} has no Gmail account: hermes -p {INBOX} connectors connect gmail"
    return ""


def file_card(args) -> str:
    key = f"jobs:code:{args.opening}:{args.attempt}"
    body = (f"Mode: CODE\nProject: {args.project}\nOpening: {args.opening}\nSite: {args.site}\n"
            f"Window: {args.window} minutes\nThe applier has the form open and is waiting: return `code: <code>` "
            f"(or `link: <url>`) in the kanban_complete result, or `no code yet`.")
    done = run(args.hermes_bin, "kanban", "--board", args.board, "create", f"Code for {args.opening}",
               "--assignee", INBOX, "--skill", "triaging-inbox", "--workspace", f"dir:{args.project}",
               "--idempotency-key", key, "--created-by", "jobs-applier", "--body", body, "--json")
    if done.returncode != 0:
        raise RuntimeError((done.stderr or done.stdout).strip()[:300])
    return str(json.loads(done.stdout).get("id") or "")


def card_state(args, card: str) -> tuple[str, str]:
    done = run(args.hermes_bin, "kanban", "--board", args.board, "show", card, "--json")
    if done.returncode != 0:
        return "", ""
    data = json.loads(done.stdout)
    task = data.get("task") or {}
    text = "\n".join(str(x) for x in (task.get("result"), data.get("latest_summary")) if x)
    return str(task.get("status") or ""), text


def read_result(text: str) -> dict:
    code = CODE_LINE.search(text)
    if code:
        return {"outcome": "code", "code": code.group(1)}
    link = LINK_LINE.search(text)
    if link:
        return {"outcome": "code", "link": link.group(1)}
    return {"outcome": "no_code", "reason": text.strip()[:200] or "no code in the card result"}


def wait(args) -> dict:
    missing = inbox_ready(args.hermes_bin)
    if missing:
        return {"outcome": "unavailable", "card": "", "reason": missing}
    try:
        card = file_card(args)
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        return {"outcome": "unavailable", "card": "", "reason": f"the code card was not filed: {exc}"}
    deadline = time.monotonic() + args.timeout
    while True:
        status, text = card_state(args, card)
        if status == "done":
            return {**read_result(text), "card": card}
        if status in ("blocked", "triage", "archived"):
            return {"outcome": "unavailable", "card": card, "reason": f"{INBOX} {status}: {text.strip()[:200]}"}
        if time.monotonic() >= deadline:
            return {"outcome": "timeout", "card": card, "reason": f"no answer in {args.timeout} s"}
        time.sleep(args.poll)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Ask jobs-inbox for an e-mailed form code and wait for it.")
    p.add_argument("--project", required=True, help="the project folder (the card's workspace)")
    p.add_argument("--opening", required=True, help="the opening id")
    p.add_argument("--site", required=True, help="the sender's domain, e.g. greenhouse-mail.io")
    p.add_argument("--window", type=int, default=15, help="minutes of mail jobs-inbox searches (default 15)")
    p.add_argument("--timeout", type=int, default=480, help="seconds to wait for the card (default 480)")
    p.add_argument("--attempt", type=int, default=1, help="1 for the first code, 2 after requesting a new one")
    p.add_argument("--poll", type=float, default=10.0, help=argparse.SUPPRESS)
    p.add_argument("--board", default=os.environ.get("HERMES_KANBAN_BOARD") or "jobs")
    p.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN") or shutil.which("hermes") or "hermes")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    site = args.site.strip().lower().removeprefix("www.")
    if not ID_RE.match(args.opening) or not SITE_RE.match(site) or not 1 <= args.attempt <= 3 \
            or not Path(args.project).is_dir():
        print("code_wait: --opening must be an opening id, --site a bare domain, --attempt 1 to 3, --project a folder",
              file=sys.stderr)
        return 2
    args.site = site
    out = wait(args)
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(out.get("code") or out.get("link") or f"{out['outcome']}: {out.get('reason', '')}")
    return EXIT[out["outcome"]]


if __name__ == "__main__":
    sys.exit(main())
