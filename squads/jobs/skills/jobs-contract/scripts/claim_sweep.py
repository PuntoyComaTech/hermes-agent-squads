#!/usr/bin/env python3
"""Every sentence of an application that makes the same claim, in every file at once.

  claim_sweep.py APPLICATION_DIR --terms Python FastAPI "AI layer" [--json]

A correction names one instance of a claim ("Python and FastAPI in the OMS AI layer"); the same mix is often written
again in the letter, the recruiter message, the CV and the form answers. Fixing only the instance a review named costs
one review round per instance. This lists every sentence that holds all the terms (whole words, accents and case
aside), in the files an employer reads: cv_content.json (every text value), cover_letter.md, recruiter_message.md and
answers.md. Sentences of answers.md outside its [FIELD] blocks are notes no employer reads: listed with
`outward: false`.

The writer runs it for each correction before handing back (writing-applications), and the reviewer's
aggregate_review.py runs it for each finding that names `claim_terms`, so every instance is corrected in one round.

Exit 0 (instances listed, possibly none), 2 usage error.
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

OUTWARD_FILES = ("cv_content.json", "cover_letter.md", "recruiter_message.md", "answers.md")
FIELD_BLOCK = re.compile(r"\[FIELD\](.*?)\[/FIELD\]", re.S)
COMMENT = re.compile(r"<!--.*?-->", re.S)


def json_texts(value) -> list:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [t for v in value.values() for t in json_texts(v)]
    if isinstance(value, list):
        return [t for v in value for t in json_texts(v)]
    return []


def spans(name: str, text: str) -> list:
    """(text, outward) parts of one file."""
    if name == "cv_content.json":
        try:
            return [(t, True) for t in json_texts(json.loads(text))]
        except ValueError:
            return [(text, True)]
    text = COMMENT.sub(" ", text)
    if name != "answers.md":
        return [(text, True)]
    blocks = FIELD_BLOCK.findall(text)
    if not blocks:
        return [(text, True)]  # an older kit without [FIELD] markers: all of it is pasted
    return [(b, True) for b in blocks] + [(FIELD_BLOCK.sub("\n", text), False)]


def instances(files: dict, terms) -> list:
    """[{file, sentence, outward}] for every sentence holding all terms. files: {name: text}."""
    out = []
    for name in OUTWARD_FILES:
        text = files.get(name)
        if not text:
            continue
        for part, outward in spans(name, text):
            for sentence in jc.same_claim_hits(part, terms):
                row = {"file": name, "sentence": sentence, "outward": outward}
                if row not in out:
                    out.append(row)
    return out


def read_dir(folder: Path) -> dict:
    return {n: (folder / n).read_text(encoding="utf-8", errors="ignore")
            for n in OUTWARD_FILES if (folder / n).is_file()}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="List every sentence of an application that makes the same claim.")
    p.add_argument("application_dir", help="openings/<ID>/application")
    p.add_argument("--terms", nargs="+", required=True, help="the words the claim ties together (all must appear)")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    folder = Path(args.application_dir)
    if not folder.is_dir():
        print(f"claim_sweep: {folder} is not a folder", file=sys.stderr)
        return 2
    rows = instances(read_dir(folder), args.terms)
    if args.json:
        print(json.dumps({"terms": args.terms, "instances": rows}, indent=2, ensure_ascii=False))
    else:
        for row in rows:
            print(f"{row['file']}{'' if row['outward'] else ' (note)'}: {row['sentence']}")
        print(f"{len(rows)} instance(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
