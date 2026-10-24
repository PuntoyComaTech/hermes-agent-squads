#!/usr/bin/env python3
"""One pass over <project>/openings: state, score, apply link, kit age and gates.

Usage:
    python3 digest_fields.py <project> [--state in_review,delivered]

Why this exists: `analysis.json` carries no top-level `score`, `role`, company
string or `apply_url`, so a digest built by reading keys off that file alone
comes out empty. This prints what each file actually holds, one block per
opening, for a digest, a "why" answer or a pipeline count.
"""

import datetime
import glob
import json
import os
import re
import sys

VERDICT_RE = re.compile(r"\b(PURSUE|WATCH|REJECT|DISCARD|FLAG|NOT_APPROVED|CHANGE)\s+(\d{1,3})\b")
LINK_PATHS = (
    ("link_verification", "url"),
    ("link_resolution", "apply_url"),
    ("link_resolution", "canonical_url"),
    ("official_posting", "url"),
)
KIT_FILES = ("cv_ats.pdf", "cover_letter.md", "answers.md", "consent.json")


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def dig(data, *keys):
    cur = data
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def verdict(status):
    """Last non-empty history note plus the score it names."""
    for entry in reversed(status.get("history") or []):
        note = str(entry.get("note") or "")
        if not note:
            continue
        match = VERDICT_RE.search(note)
        return entry.get("date"), note, (int(match.group(2)) if match else None), (match.group(1) if match else None)
    return None, "", None, None


def apply_url(analysis, opening_md):
    for head, tail in LINK_PATHS:
        value = dig(analysis, head, tail)
        if value:
            return value
    for line in (opening_md or "").splitlines():
        for token in line.split():
            if token.startswith(("http://", "https://")):
                return token.strip("()[]<>\"',")
    return None


def front(opening_md, key):
    """One scalar from opening.md front matter; '' when absent or a placeholder (unknown)."""
    found = re.search(r"^%s:\s*(.+?)\s*$" % re.escape(key), opening_md.split("\n---", 2)[0] if opening_md else "", re.M)
    value = found.group(1).strip().strip("\"'") if found else ""
    return "" if value.lower() in ("", "unknown", "null", "none", "tbd") else value


def brief(analysis):
    """analysis.json `brief`, else the first sentence of the company summary (as application_notices.py)."""
    text = str(analysis.get("brief") or "").strip()
    if not text:
        summary = str(dig(analysis, "company", "summary") or "").strip()
        text = re.split(r"(?<=[.!?])\s", summary, maxsplit=1)[0] if summary else ""
    return " ".join(text.split())


def review_verdict(opening_dir):
    rounds = sorted(glob.glob(os.path.join(opening_dir, "review-*.json")))
    if not rounds:
        return None
    latest = load(rounds[-1])
    return "%s(%s: %s)" % (os.path.basename(rounds[-1]), latest.get("round", "?"), latest.get("verdict", "?"))


def kit(opening_dir):
    app = os.path.join(opening_dir, "application")
    parts = []
    for name in KIT_FILES:
        path = os.path.join(app, name)
        if os.path.exists(path):
            stamp = datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%m-%d %H:%M")
            parts.append("%s@%s" % (name, stamp))
    return " ".join(parts) or "-"


def main(argv):
    if len(argv) >= 2 and argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    if len(argv) < 2:
        print(__doc__)
        return 2
    project = os.path.expanduser(argv[1])
    only = None
    if "--state" in argv:
        only = {s.strip() for s in argv[argv.index("--state") + 1].split(",")}

    dirs = sorted(d for d in glob.glob(os.path.join(project, "openings", "*")) if os.path.isdir(d))
    counts = {}
    shown = 0
    for opening_dir in dirs:
        status = load(os.path.join(opening_dir, "status.json"))
        state = status.get("status") or status.get("state") or "unknown"
        counts[state] = counts.get(state, 0) + 1
        if only and state not in only:
            continue
        analysis = load(os.path.join(opening_dir, "analysis.json"))
        opening_md_path = os.path.join(opening_dir, "opening.md")
        opening_md = ""
        if os.path.exists(opening_md_path):
            with open(opening_md_path, encoding="utf-8", errors="replace") as fh:
                opening_md = fh.read()

        date, note, score, word = verdict(status)
        if score is None:
            score = dig(analysis, "fit", "score")
        gates = analysis.get("gates") or {}
        gate_line = " ".join(
            "%s=%s" % (key, gates.get(key, "-"))
            for key in ("eligibility", "language", "location", "seniority")
        )
        company = dig(analysis, "company", "name") or "?"

        shown += 1
        print("== %s [%s]" % (os.path.basename(opening_dir), state))
        print("   verdict: %s %s  (%s)" % (word or "?", score if score is not None else "?", date or "-"))
        print("   company: %s" % company)
        posted, mode = front(opening_md, "posted_at"), front(opening_md, "work_mode")
        if posted or mode:
            print("   posted:  %s   mode: %s" % (posted or "-", mode or "-"))
        if brief(analysis):
            print("   brief:   %s" % brief(analysis)[:160])
        print("   gates:   %s" % gate_line)
        for key in ("eligibility_note", "language_note", "location_note", "seniority_note"):
            if gates.get(key):
                print("            %s: %s" % (key.replace("_note", ""), gates[key]))
        print("   apply:   %s" % (apply_url(analysis, opening_md) or "no ATS link on file"))
        print("   kit:     %s" % kit(opening_dir))
        review = review_verdict(opening_dir)
        if review:
            print("   review:  %s" % review)
        if note:
            print("   note:    %s" % note[:200])
        print()

    print("states: " + ", ".join("%s=%d" % kv for kv in sorted(counts.items())))
    print("shown: %d of %d openings" % (shown, len(dirs)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
