#!/usr/bin/env python3
"""Append one line to an opening's status history. Earlier history lines are never changed.

Every stage that acts on an opening records it here, so the history reads as a log of who did what and when.

Usage:
  python3 status.py append <opening_dir> <status> --by BOT [--note TEXT]
  python3 status.py show <opening_dir>

`append` reads status.json (creating it when missing), checks that every earlier history entry is still present and
identical, adds one entry {date, status, by, note} and sets the top-level "status" to the new value, then writes the
file atomically. Statuses are lowercase snake_case from the squad's fixed list; an unknown one is refused.

Exit 0 on success. Exit 1 when the existing status.json is damaged (its history would be lost). Exit 2 on a usage
error, an unknown status, or an opening folder that does not exist.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jobs_common import STATUSES, atomic_write, now_iso  # noqa: E402

NOTE_MAX = 300


class UsageError(ValueError):
    """The caller's arguments are wrong (exit 2), as opposed to a damaged file (exit 1)."""


def _load(path: Path, opening_id: str) -> dict:
    if not path.is_file():
        return {"id": opening_id, "status": None, "history": []}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("history", []), list):
        raise ValueError(f"{path}: expected an object with a history list")
    doc.setdefault("history", [])
    return doc


def append(opening_dir: Path, status: str, by: str, note: str = "") -> dict:
    if status not in STATUSES:
        raise UsageError(f"unknown status {status!r}; use one of: {', '.join(STATUSES)}")
    if not by.strip():
        raise UsageError("--by must name the bot or person acting")
    path = opening_dir / "status.json"
    doc = _load(path, opening_dir.name)
    before = [json.dumps(entry, sort_keys=True) for entry in doc["history"]]
    entry = {"date": now_iso(), "status": status, "by": by.strip()}
    if note:
        entry["note"] = note.strip()[:NOTE_MAX]
    doc["history"].append(entry)
    doc["status"] = status
    # The earlier lines are checked against their own content, not trusted: a rewrite that changed one fails here
    # before anything reaches the disk.
    after = [json.dumps(item, sort_keys=True) for item in doc["history"][:len(before)]]
    if after != before:
        raise RuntimeError("earlier history lines would change; refusing to write")
    atomic_write(path, json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
    return doc


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


def main(argv=None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(description="Append a line to an opening's status.json history.")
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("append", help="append one history line")
    add.add_argument("opening_dir", type=Path)
    add.add_argument("status", help="one of: " + ", ".join(STATUSES))
    add.add_argument("--by", required=True, help="the bot or person recording the change, e.g. jobs-scout")
    add.add_argument("--note", default="", help="one short line of context (kept to 300 characters)")

    show = sub.add_parser("show", help="print the current status and the history")
    show.add_argument("opening_dir", type=Path)

    args = parser.parse_args(argv)
    folder = args.opening_dir
    if not folder.is_dir():
        print(f"status: {folder} is not a folder", file=sys.stderr)
        return 2

    if args.command == "show":
        try:
            doc = _load(folder / "status.json", folder.name)
        except ValueError as exc:
            print(f"status: {exc}", file=sys.stderr)
            return 1
        print(json.dumps(doc, indent=2, ensure_ascii=False))
        return 0

    try:
        doc = append(folder, args.status, args.by, args.note)
    except UsageError as exc:
        print(f"status: {exc.args[0]}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"status: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(f"status: {exc}", file=sys.stderr)
        return 1
    print(f"status={doc['status']} lines={len(doc['history'])} file={folder / 'status.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
