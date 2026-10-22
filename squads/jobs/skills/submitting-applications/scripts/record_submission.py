#!/usr/bin/env python3
"""Record a finished submit step in the project tracker: one row per opening, written once.

Usage:
  record_submission.py FILE [--today YYYY-MM-DD] [--json]

FILE is openings/<ID>/application/submission.json. check_submission.py runs first on FILE; a failed check records
nothing and exits 1. The project is the folder that holds openings/ (its profile.md must exist).

  SUBMITTED       -> tracker row and status.json: applied (applied_at = today)
  NOT_POSSIBLE    -> tracker row and status.json: manual_application (the kit is delivered)
  NEEDS_DATA      -> nothing recorded: the opening is still waiting for the user

The whole record runs under the project's apply lock (openings/.apply.lock, scripts/apply_state.py) and drops the
reservation an open gate left, so the cap and the tracker change together.

A SUBMITTED record that fails only on the rules that can move after the click (the cap, a review replaced, the
consent date) is still recorded when the gate opened for this opening under 4 hours ago (application/gate.json, the
stamp check_submission.py --gate writes): the submit happened, and an unrecorded submit is invisible to the cap and
can be applied twice. Its status line says `recorded over the gate: <the rules>` and --json prints them as `flags`.
Every other rule stays hard, stamp or no stamp: the record's own contract (id, result, method, filled fields,
screenshots, contact data), auto_apply: never, a missing consent file, a missing approval, an unverifiable or a
job-board apply_url and an analysis that never said PURSUE are refused, writes nothing and exits 1.

A row already tracked is updated only when it is not yet past the target stage, so running this twice never
moves a row back or forward twice. The row is created with tracker.py add --if-missing. An email application
(method email) may carry a mailto: address as its apply link. status.json gets the target line through
status.py append, once: a status that already reads the target is left alone.

Exit codes: 0 recorded or nothing to record, 1 the check failed or the tracker refused, 2 bad input.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECK = HERE / "check_submission.py"
APPLY_STATE = HERE / "apply_state.py"
JOBS_CONTRACT = HERE.parent.parent / "jobs-contract" / "scripts"
TRACKER = JOBS_CONTRACT / "tracker.py"
JOBS_COMMON = JOBS_CONTRACT / "jobs_common.py"
STATUS = JOBS_CONTRACT / "status.py"

# Statuses that mean the application has not been sent yet (the tracker's NOT_SENT bucket).
NOT_SENT = frozenset({"found", "analyzed", "in_preparation", "in_review", "not_approved", "ready", "delivered",
                      "applying", "manual_application"})
TARGET = {"SUBMITTED": "applied", "NOT_POSSIBLE": "manual_application"}
NOTE_MAX = 300


def load_module(name: str, path: Path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AS = load_module("jobs_apply_state_for_record", APPLY_STATE)


def run(argv: list) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, *argv], capture_output=True, text=True, timeout=120,
                          stdin=subprocess.DEVNULL)


def status_now(opening_dir: Path):
    """The last status.json history line, or None when there is no status file yet."""
    try:
        doc = json.loads((opening_dir / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    history = doc.get("history") if isinstance(doc, dict) else None
    lines = [item for item in history if isinstance(item, dict)] if isinstance(history, list) else []
    return lines[-1].get("status") if lines else None


def sync_status(opening_dir: Path, target: str, action: str, held, flags=()) -> str:
    """Move status.json to the target stage through status.py append. Returns an error text, or '' when done."""
    current = status_now(opening_dir)
    if current == target:
        return ""
    moved = action in ("added", "updated") or (held == target and current in ("ready", "applying"))
    if not moved:
        return ""
    note = "submitted by the applier" if target == "applied" else "manual kit delivered"
    if flags:
        note += "; " + over_gate(flags)
    done = run([str(STATUS), "append", str(opening_dir), target, "--by", "jobs-applier", "--note",
                note[:NOTE_MAX]])
    return "" if done.returncode == 0 else f"status.py append refused: {done.stderr.strip()[:300]}"


def over_gate(flags: list) -> str:
    """The one status line that says the record went in over a rule that moved after the click."""
    rules = []
    for line in flags:
        rule = line.split(":", 1)[0].strip()
        if rule and rule not in rules:
            rules.append(rule)
    return f"recorded over the gate: {', '.join(rules)}"


def fail(message: str, code: int = 1) -> int:
    print(f"record_submission: {message}", file=sys.stderr)
    return code


def record(path: Path, today: str) -> tuple[int, dict]:
    base = path.parent
    if base.name != "application" or base.parent.parent.name != "openings":
        return 2, {"error": "FILE must be openings/<ID>/application/submission.json"}
    opening_dir = base.parent
    project = opening_dir.parent.parent
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 2, {"error": f"{path} is not readable JSON"}
    if not isinstance(data, dict):
        return 2, {"error": f"{path} must hold one JSON object"}

    # One applier at a time: the cap, the reservation and the row change together.
    with AS.locked(project):
        flags = []
        checked = run([str(CHECK), str(path)])
        if checked.returncode != 0:
            # The click already happened. A record whose own contract is sound but whose authority moved (the cap
            # filled up, the review or consent changed, the settings moved) is recorded and flagged: dropping it
            # leaves the submit invisible to the cap and open to a second apply.
            after = run([str(CHECK), str(path), "--post-submit", "--json"])
            flags = authority_flags(after.stdout)
            if after.returncode != 0 or not flags:
                return 1, {"error": "check_submission refused the record",
                           "detail": checked.stderr.strip()[:600]}
        result = data.get("result")
        if result == "NEEDS_DATA":
            AS.release(project, opening_dir.name)  # no click: the place goes back to the day's cap
            return 0, {"recorded": False, "flags": flags,
                       "reason": "NEEDS_DATA: the opening waits for the user; status unchanged"}
        target = TARGET.get(result)
        if target is None:
            return 2, {"error": f"unknown result {result!r}"}
        common = load_module("jobs_common_for_record", JOBS_COMMON)
        meta = common.read_front_matter(opening_dir / "opening.md")
        fields = {key: str(meta.get(key) or "").strip() for key in ("id", "company", "role", "apply_url")}
        if not fields["company"] or not fields["role"] or not fields["id"]:
            return 1, {"error": "opening.md needs id, company and role in its front matter"}

        channel = ["--channel", "email"] if data.get("method") == "email" else []
        added = run([str(TRACKER), "add", "--project", str(project), "--id", fields["id"],
                     "--company", fields["company"], "--role", fields["role"], "--status", target,
                     "--apply-url", fields["apply_url"], *channel, "--date", today, "--today", today,
                     "--if-missing"])
        if added.returncode != 0:
            return 1, {"error": "tracker add refused", "detail": added.stderr.strip()[:600]}
        payload = json.loads(added.stdout)
        held = None
        if payload.get("added"):
            action = "added"
        else:
            held = payload.get("status")
            if held not in NOT_SENT or held == target:
                # Already submitted (or closed) rows never move back; a row at the target stage is left alone.
                action = "unchanged"
            else:
                changed = run([str(TRACKER), "update", "--project", str(project), "--id", fields["id"],
                               "--status", target, "--today", today])
                if changed.returncode != 0:
                    return 1, {"error": "tracker update refused", "detail": changed.stderr.strip()[:600]}
                action = "updated"
        synced = sync_status(opening_dir, target, action, held, flags)
        if synced:
            return 1, {"error": synced, "id": fields["id"], "action": action, "flags": flags}
        AS.release(project, opening_dir.name)
    shown = held if action == "unchanged" else target
    out = {"recorded": True, "id": fields["id"], "status": shown, "action": action, "flags": flags}
    if flags:
        out["note"] = over_gate(flags)
    if action == "updated":
        out["was"] = held
    return 0, out


def authority_flags(stdout: str) -> list:
    """The flags --post-submit reported, or [] when it printed nothing usable."""
    try:
        payload = json.loads(stdout)
    except ValueError:
        return []
    flags = payload.get("flags") if isinstance(payload, dict) else None
    return flags if isinstance(flags, list) else []


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Record a submit or manual-kit step in tracker.csv (idempotent).")
    parser.add_argument("file", help="openings/<ID>/application/submission.json")
    parser.add_argument("--today", help="YYYY-MM-DD in place of the local date (replays and tests)")
    parser.add_argument("--json", action="store_true", help="print the outcome as JSON on stdout")
    args = parser.parse_args(argv)
    today = args.today or date.today().isoformat()
    try:
        date.fromisoformat(today)
    except ValueError:
        return fail(f"--today must be YYYY-MM-DD, got {today!r}", 2)
    code, payload = record(Path(args.file).expanduser().resolve(), today)
    if args.json or code != 0:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    elif payload.get("reason"):
        print(payload["reason"])
    else:
        print(f"tracker: {payload.get('action')} {payload.get('id')} -> {payload.get('status')}")
    # A record that went in over the gate names the rules in the manager's digest, not only in a log nobody reads.
    if not args.json:
        for line in payload.get("flags") or []:
            print(f"flag: {line}", file=sys.stderr)
    if payload.get("note") and not args.json:
        print(f"note: {payload['note']}")
    return code


if __name__ == "__main__":
    sys.exit(main())
