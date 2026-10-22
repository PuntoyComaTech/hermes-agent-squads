#!/usr/bin/env python3
"""The project-level submit lock, the dated reservations that hold a place in the day's cap, and the gate stamp.

check_submission.py --gate and record_submission.py hold one exclusive flock on `<P>/openings/.apply.lock` while they
read the cap and write, so the cap is decided by one applier at a time: two runs at nine of ten cannot both take the
tenth place. The lock waits with no timeout, and record_submission.py holds it while it runs up to four subprocesses of
up to 120 s each: a hung record blocks the day's gate until it exits, and that wait is deliberate (the alternative is
two appliers reading the same cap). flock is dropped when the process exits, so no stale lock survives a crash.

Under `auto_apply: auto` the open gate also writes a reservation to `<P>/openings/.apply-state.json`. It counts against
the daily cap like an `applied` line of the same day, and record_submission.py drops it when it appends this opening's
`applied` line. A reservation older than RESERVATION_HOURS is ignored, so an abandoned run gives its place back, and
submissions_today counts an opening once when it holds both an `applied` line of the day and a live reservation (the
record died between the two writes).

    {"schema": 1, "reservations": {"<ID>": {"date": "YYYY-MM-DD", "at": "YYYY-MM-DDTHH:MM:SSZ", "method": "..."}}}

In every mode the open gate writes `openings/<ID>/application/gate.json`, the stamp that says the gate opened for this
opening: {opening_id, method, mode, opened_at}. It is the only proof record_submission.py accepts for softening a rule
that moved between the click and the record, and only for GATE_HOURS after it was written.

    {"opening_id": "<ID>", "method": "no_login_form", "mode": "auto", "opened_at": "YYYY-MM-DDTHH:MM:SSZ"}

Both scripts load this file as a module. `apply_state.py --status <P>` prints the live reservations, for a human
asking why the gate is closed; `apply_state.py --release <P> --opening <ID>` gives one place back (the applier runs it
when a NOT_POSSIBLE or NEEDS_DATA record left the reservation of its open gate behind). A missing or damaged state
file reads as no reservations; a missing or damaged stamp reads as no proof.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA = 1
LOCK_NAME = ".apply.lock"
STATE_NAME = ".apply-state.json"
GATE_NAME = "gate.json"
RESERVATION_HOURS = 4
GATE_HOURS = RESERVATION_HOURS
TIMESTAMP = "%Y-%m-%dT%H:%M:%SZ"


def lock_path(project: Path) -> Path:
    return Path(project) / "openings" / LOCK_NAME


def state_path(project: Path) -> Path:
    return Path(project) / "openings" / STATE_NAME


@contextmanager
def locked(project: Path):
    """Hold the project's apply lock. Every reader-writer of the cap runs inside this, never beside it."""
    path = lock_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _stamp(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime(TIMESTAMP)


def _expired(entry: dict, now: datetime) -> bool:
    """A reservation past RESERVATION_HOURS, or one whose date we cannot read: its place goes back."""
    try:
        at = datetime.strptime(str(entry.get("at") or ""), TIMESTAMP).replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return now - at > timedelta(hours=RESERVATION_HOURS)


def _read(project: Path) -> dict:
    """The reservations in the state file, unpruned; {} when it is missing, unreadable or not the documented shape."""
    try:
        doc = json.loads(state_path(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    held = doc.get("reservations") if isinstance(doc, dict) else None
    return {key: value for key, value in held.items() if isinstance(value, dict)} if isinstance(held, dict) else {}


def _write(project: Path, held: dict) -> None:
    path = state_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps({"schema": SCHEMA, "reservations": held}, indent=2, ensure_ascii=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def live(project: Path, now: datetime | None = None) -> dict:
    """The reservations still holding a place: {opening id: entry}. Reads only, so a reader never writes."""
    now = now or datetime.now(timezone.utc)
    return {key: entry for key, entry in _read(project).items() if not _expired(entry, now)}


def reserve(project: Path, opening_id: str, day, method: str) -> dict:
    """Take this opening's place in the day's cap. The caller holds the lock, and rewrote no other place."""
    now = datetime.now(timezone.utc)
    held = {key: entry for key, entry in _read(project).items() if not _expired(entry, now)}
    held[opening_id] = {"date": str(day), "at": _stamp(now), "method": method}
    _write(project, held)
    return held[opening_id]


def release(project: Path, opening_id: str) -> bool:
    """Give the place back (the record closed the opening, or nothing was clicked). True when one was held."""
    now = datetime.now(timezone.utc)
    held = {key: entry for key, entry in _read(project).items() if not _expired(entry, now)}
    dropped = held.pop(opening_id, None) is not None
    _write(project, held)
    return dropped


def gate_path(application: Path) -> Path:
    return Path(application) / GATE_NAME


def gate_stamp(application: Path):
    """The gate stamp in application/, or None when it is missing, unreadable or not the documented shape."""
    try:
        doc = json.loads(gate_path(application).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) and isinstance(doc.get("opening_id"), str) else None


def stamp(application: Path, opening_id: str, method: str, mode: str) -> dict:
    """Write that the gate opened for this opening: the one proof record_submission.py softens a moved rule with."""
    path = gate_path(application)
    entry = {"opening_id": opening_id, "method": method, "mode": mode, "opened_at": _stamp()}
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return entry


def gate_recent(application: Path, opening_id: str, now: datetime | None = None) -> bool:
    """True when the gate opened for THIS opening under GATE_HOURS ago. A stamp of another opening, an old one or an
    unreadable one is no proof: the record is then the first check of those rules, not a second one."""
    doc = gate_stamp(application)
    if doc is None or doc.get("opening_id") != opening_id:
        return False
    return not _expired({"at": doc.get("opened_at")}, now or datetime.now(timezone.utc))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="The project apply lock, the reservations that hold a place in "
                                                 "the day's cap, and the gate stamp.")
    parser.add_argument("--status", metavar="PROJECT", help="print the live reservations of a project and exit")
    parser.add_argument("--release", metavar="PROJECT", help="give back the place of --opening in PROJECT")
    parser.add_argument("--opening", metavar="ID", help="the opening whose reservation --release drops")
    args = parser.parse_args(argv)
    if args.status:
        project = Path(args.status).expanduser()
        print(json.dumps(live(project), indent=2, ensure_ascii=False, sort_keys=True))
        return 0
    if args.release:
        if not args.opening:
            print("error: --release needs --opening <ID>", file=sys.stderr)
            return 2
        dropped = release(Path(args.release).expanduser(), args.opening)
        print(json.dumps({"released": dropped, "opening": args.opening}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
