#!/usr/bin/env python3
"""Print the idempotency key of a jobs card: the one format every stage uses, so no bot builds it by hand.

  card_key.py application <project> <ID> <stage>     jobs:application:<slug>:<ID>:<stage>
  card_key.py <kind> <project> <part>                 jobs:<kind>:<slug>:<part>   (search, rank, inbox, profile, ...)

<project> is the project slug (`job-search`) or its folder: a folder is turned into its slug, the folder's own name
lowercased with every run of other characters as one `-`. That is the slug Hermes gives a project created from that
folder, and the slug start_search.py and every other card of the board already use. A key never carries a path: a
path in it (`/Users/...`) makes a second card for a stage that already has one.

<stage> for the application chain: analyze, write, review, digest, apply; write-r2 / review-r2 for the correction
round; write-c<N> / review-c<N> / digest-c<N> for CHANGE round N. Anything else is refused.
Exit 0 printed, 2 usage error.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jobs_common as jc  # noqa: E402

STAGE = re.compile(r"^(?:analyze|write|review|digest|apply|(?:write|review)-r2|(?:write|review|digest|apply)-c\d{1,3})$")
KIND = re.compile(r"^[a-z][a-z0-9-]{1,30}$")
PART = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,80}$")


def slug_of(project: str) -> str:
    """The project slug, from a slug or a folder path."""
    text = str(project or "").strip().rstrip("/")
    if "/" in text or text.startswith("~"):
        text = Path(text).expanduser().name
    slug = re.sub(r"[^a-z0-9]+", "-", jc.ascii_fold(text).lower()).strip("-")
    if not slug:
        raise ValueError(f"no project slug in {project!r}")
    return slug


def key(kind: str, project: str, *parts: str) -> str:
    if not KIND.match(kind):
        raise ValueError(f"kind must be lowercase words joined by '-', got {kind!r}")
    slug = slug_of(project)
    if kind == "application":
        if len(parts) != 2:
            raise ValueError("application needs <ID> <stage>")
        opening, stage = parts
        if not jc.valid_opening_id(opening):
            raise ValueError(f"{opening!r} is not an opening id (JOB-YYYYMMDD-<slug>)")
        if not STAGE.match(stage):
            raise ValueError(f"stage {stage!r}: analyze, write, review, digest, apply, write-r2, review-r2, "
                             "write-c<N>, review-c<N>, digest-c<N> or apply-c<N>")
        return f"jobs:application:{slug}:{opening}:{stage}"
    if len(parts) != 1 or not PART.match(parts[0]):
        raise ValueError(f"{kind} needs one part (a date, a slot or an id) without spaces or slashes")
    return f"jobs:{kind}:{slug}:{parts[0]}"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Print a jobs card's idempotency key (project slug, never a path).")
    p.add_argument("kind", help="application, search, rank, inbox, profile, evidence, ...")
    p.add_argument("project", help="the project slug or its folder")
    p.add_argument("parts", nargs="+", help="application: <ID> <stage>; other kinds: one date, slot or id")
    args = p.parse_args(argv)
    try:
        print(key(args.kind, args.project, *args.parts))
    except ValueError as exc:
        print(f"card_key: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
