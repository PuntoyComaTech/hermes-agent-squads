#!/usr/bin/env python3
"""Three-way line merge of text files, stdlib only: keep local edits across an update.

    merge3.py BASE OURS THEIRS        print the merged text; exit 0 clean, 1 conflict, 2 usage error

BASE is the shipped version the local copy started from, OURS the local copy (edited by the bot, the curator or the
user), THEIRS the newly shipped version. Changes from both sides are combined when they touch different lines.
Changes that overlap or touch (adjacent lines, or insertions at the same point) are a conflict unless both sides made
the identical change: nothing is guessed. On a conflict the result is THEIRS unchanged, so a caller never writes a half
merge, unless the caller passes `prefer="ours"`: then each clashing stretch keeps OURS, every other change from both
sides still lands, and the result is reported not clean (what a bot learned is never taken away by an update). auto_update.py (builder files) and squadctl.py (squad skills copied into bots) use `merge()`.
"""
from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

Hunk = tuple[int, int, tuple[str, ...]]  # base lines [start, end) replaced by these lines


def hunks(base: list[str], other: list[str]) -> list[Hunk]:
    sm = difflib.SequenceMatcher(None, base, other, autojunk=False)
    return [(i1, i2, tuple(other[j1:j2])) for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag != "equal"]


def merge(base: str, ours: str, theirs: str, prefer: str | None = None) -> tuple[str, bool]:
    """(merged text, clean). prefer="ours": a clashing stretch keeps OURS instead of returning THEIRS whole."""
    if ours == theirs or theirs == base:
        return ours, True
    if ours == base:
        return theirs, True
    b = base.splitlines(True)
    ho = hunks(b, ours.splitlines(True))
    ht = [h for h in hunks(b, theirs.splitlines(True)) if h not in ho]  # the same change on both sides lands once
    clash = {t for t in ht for o in ho if o[0] <= t[1] and t[0] <= o[1]}  # overlapping or touching
    if clash and prefer != "ours":
        return theirs, False
    ht = [t for t in ht if t not in clash]
    out: list[str] = []
    pos = 0
    for s, e, repl in sorted(ho + ht, key=lambda h: (h[0], h[1])):
        out += b[pos:s]
        out += repl
        pos = e
    out += b[pos:]
    return "".join(out), not clash


def merge_bytes(base: bytes | None, ours: bytes | None, theirs: bytes | None,
                prefer: str | None = None) -> tuple[bytes | None, bool]:
    """One file, each side None when absent. (result or None to delete, clean). Not clean: THEIRS, or with
    prefer="ours" the merge where OURS wins each clash (a whole file OURS changed and THEIRS deleted stays)."""
    if ours == theirs or theirs == base:
        return ours, True
    if ours == base:
        return theirs, True
    fallback = ours if prefer == "ours" else theirs  # prefer ours: a file the bot deleted stays deleted
    if base is None or ours is None or theirs is None:
        return fallback, False  # added or deleted on one side and changed on the other
    try:
        text, clean = merge(base.decode("utf-8"), ours.decode("utf-8"), theirs.decode("utf-8"), prefer)
    except UnicodeDecodeError:
        return fallback, False  # binary on both sides: ours under prefer="ours", else theirs
    return text.encode("utf-8"), clean


SKIP = {"__pycache__", ".DS_Store", ".squad-sha"}


def read_tree(root: Path | None) -> dict[str, bytes]:
    if root is None or not root.is_dir():
        return {}
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and not SKIP & set(p.relative_to(root).parts)}


def merge_trees(base: Path | None, ours: Path, theirs: Path,
                prefer: str | None = None) -> tuple[dict[str, bytes], list[str]]:
    """(files of the merged tree, conflicting paths) for three directories. A file added only locally is kept."""
    b, o, t = read_tree(base), read_tree(ours), read_tree(theirs)
    out: dict[str, bytes] = {}
    conflicts: list[str] = []
    for rel in sorted(set(b) | set(o) | set(t)):
        result, clean = merge_bytes(b.get(rel), o.get(rel), t.get(rel), prefer)
        if not clean:
            conflicts.append(rel)
        if result is not None:
            out[rel] = result
    return out, conflicts


def main(argv: list[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(description=doc.split("\n\n")[0], epilog=doc.split("\n\n", 1)[-1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("ours")
    ap.add_argument("theirs")
    a = ap.parse_args(argv)
    try:
        texts = [Path(p).read_text(encoding="utf-8") for p in (a.base, a.ours, a.theirs)]
    except OSError as exc:
        print(f"merge3: {exc}", file=sys.stderr)
        return 2
    text, clean = merge(*texts)
    sys.stdout.write(text)
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
