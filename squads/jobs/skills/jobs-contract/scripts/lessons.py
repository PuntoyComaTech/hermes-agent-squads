#!/usr/bin/env python3
"""Writing lessons of one job-search project: `<P>/writing-lessons.md`, the defects the review keeps finding.

  lessons.py add   --text "<rule: what to do instead, and why>" --source <opening ID> [--project P]
  lessons.py list  [--project P] [--json]

The reviewer adds a lesson when a defect it corrects has already been corrected in another opening; the writer reads
the list before every draft, so the next application avoids it instead of the review catching it again. One lesson is
one line of at most 300 characters. An entry whose words mostly repeat an existing lesson counts as seen again (its
count goes up) instead of being added twice. The file holds at most 25 lessons: a full file refuses `add` until the
reviewer merges or drops one by hand.

A lesson never carries contact data, nor a profile.md `confidential_terms` entry: the file is read into every writing
card. Output is JSON on stdout; a refused write exits 1 with the reason on stderr; usage errors exit 2.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jobs_common as jc  # noqa: E402

FILE = "writing-lessons.md"
MAX_LESSONS = 25
MAX_CHARS = 300
SAME = 0.6  # share of the shorter lesson's words found in the other one
HEADER = ("# Writing lessons\n\nDefects the review found in more than one application. jobs-reviewer adds them with "
          "`lessons.py add`; jobs-writer reads them before every draft.\n\n")
LINE = re.compile(r"^- \[(\d+)x, (\d{4}-\d{2}-\d{2}), ([^\]]+)\] (.+)$")
CONTACT = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\+\d[\d ()-]{7,}\d")
STOP = {"a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with", "is", "it", "as", "at", "by", "be",
        "never", "not", "no", "its", "his", "her", "their", "this", "that", "from", "one"}


def words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", jc.ascii_fold(text).lower()) if w not in STOP and len(w) > 1}


def read(path: Path) -> list:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = LINE.match(line.strip())
        if m:
            rows.append({"count": int(m[1]), "last": m[2], "source": m[3], "text": m[4]})
    return rows


def write(path: Path, rows: list) -> None:
    body = "".join(f"- [{r['count']}x, {r['last']}, {r['source']}] {r['text']}\n" for r in rows)
    jc.atomic_write(path, HEADER + body)


def same(a: str, b: str) -> bool:
    wa, wb = words(a), words(b)
    small = min(len(wa), len(wb))
    return bool(small) and len(wa & wb) / small >= SAME


def add(project: Path, text: str, source: str, today: str) -> dict:
    text = " ".join(str(text or "").split())
    if not text:
        raise ValueError("an empty lesson")
    if len(text) > MAX_CHARS:
        raise ValueError(f"a lesson is one line of at most {MAX_CHARS} characters, got {len(text)}: shorten it")
    if CONTACT.search(text):
        raise ValueError("a lesson never carries an e-mail address or a phone number")
    hits = jc.confidential_hits(text, jc.confidential_terms(jc.read_front_matter(project / "profile.md")))
    if hits:
        raise ValueError(f"a lesson never names a confidential term: {', '.join(hits)}")
    if not jc.valid_opening_id(source):
        raise ValueError(f"--source must be the opening id the defect came from, got {source!r}")
    path = project / FILE
    with jc.locked(path):
        rows = read(path)
        for row in rows:
            if same(row["text"], text):
                row["count"] += 1
                row["last"] = today
                row["source"] = source
                write(path, rows)
                return {"result": "seen_again", "lesson": row}
        if len(rows) >= MAX_LESSONS:
            raise ValueError(f"{FILE} already holds {MAX_LESSONS} lessons: merge two or drop one the writer no "
                             "longer gets wrong, then add again")
        row = {"count": 1, "last": today, "source": source, "text": text}
        rows.append(row)
        write(path, rows)
        return {"result": "added", "lesson": row}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("add", "list"):
        p = sub.add_parser(name)
        p.add_argument("--project", help="project folder holding profile.md (default: $JOBS_PROJECT, else the "
                                         "current folder)")
        p.add_argument("--today", help="YYYY-MM-DD in place of the local date (tests)")
        if name == "add":
            p.add_argument("--text", required=True)
            p.add_argument("--source", required=True)
        else:
            p.add_argument("--json", action="store_true", help="accepted; the output is always JSON")
    args = ap.parse_args(argv)
    project = jc.project_dir(args.project)
    if args.cmd == "list":
        rows = read(project / FILE)
        print(json.dumps({"lessons": rows, "count": len(rows)}, ensure_ascii=False, indent=1))
        return 0
    try:
        out = add(project, args.text, args.source, args.today or jc.today())
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
