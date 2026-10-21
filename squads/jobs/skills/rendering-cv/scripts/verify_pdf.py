#!/usr/bin/env python3
"""Check a rendered PDF the way an applicant tracking system reads it: page count and the text layer.

Extraction order: pypdf (`pip install pypdf`), then Poppler `pdftotext -raw -enc UTF-8`. Neither is required.
With no extractor the script prints "skipped: ..." on stderr and exits 2, so a machine without them never gets a
false pass or a false failure.

Checks (each optional):
  --pages N          exact page count (pdfinfo or pypdf must be able to count)
  --min-chars N      at least N non-space characters in the text layer (default 1)
  --contains TEXT    TEXT appears in the text layer; repeatable. Both sides are folded: whitespace, Unicode NFC and
                     typographic punctuation (curly quotes, en and em dashes), so "Master's" matches the typeset form
  --ascii-dates      no year joined to a non-ASCII dash in the RAW layer. Never folded: an applicant tracking
                     system that splits date ranges on the ASCII hyphen drops the date otherwise
  --dump-text FILE   the raw text layer, UTF-8, written before any check so a failed check still leaves it

Exit codes: 0 all checks pass, 1 a check failed, 2 usage error or skipped (no extractor, or no page counter).
No network. Stdlib only.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path


class Skipped(Exception):
    """No extractor or page counter is available: the check is not run, which is not a pass."""


class UsageError(Exception):
    """The PDF or an option is unusable."""


# Typographic punctuation a typesetter substitutes for plain keyboard characters. Applied to both sides of --contains
# only; the raw layer is never rewritten.
FOLDS = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u00a0": " ",
})

NON_ASCII_DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
_YEAR = r"(?<!\d)(?:19|20)\d{2}(?!\d)"
NON_ASCII_DATE_RANGE = re.compile(rf"{_YEAR}[^\S\n]*[{NON_ASCII_DASHES}]|[{NON_ASCII_DASHES}][^\S\n]*{_YEAR}")
_TOKEN_BEFORE = re.compile(r"(\S+)[^\S\n]*$")
_TOKEN_AFTER = re.compile(r"^[^\S\n]*(\S+)")
_BARE_NUMBER = re.compile(r"\d+(?:[.,]\d+)*[kKmM%]?")
_BARE_YEAR = re.compile(r"(?:19|20)\d{2}")
_TWO_DIGIT_YEAR = re.compile(r"\d{2}")
_OUTER = ".,;:!?()[]{}\"'"


def normalize_text(text: str) -> str:
    """The comparison alphabet for --contains: NFC, typographic punctuation folded, whitespace collapsed."""
    return " ".join(unicodedata.normalize("NFC", text).translate(FOLDS).split())


def _bare_number(token: str):
    core = token.strip(_OUTER)
    if not _BARE_NUMBER.fullmatch(core):
        return None
    groups = re.split(r"[.,]", core.rstrip("kKmM%"))
    if len(groups) > 1 and any(_BARE_YEAR.fullmatch(g) for g in groups):
        return None  # a numerically written date (01.2016), not a quantity
    return core


def _is_quantity_range(line: str, dash_index: int) -> bool:
    """Two bare numbers around the dash are a quantity (EUR 1500-2000), unless they form a date pair (2016-2024, 2016-17)."""
    before = _TOKEN_BEFORE.search(line[:dash_index])
    after = _TOKEN_AFTER.search(line[dash_index + 1:])
    if not before or not after:
        return False
    left, right = _bare_number(before.group(1)), _bare_number(after.group(1))
    if left is None or right is None:
        return False
    if _BARE_YEAR.fullmatch(left) and (_BARE_YEAR.fullmatch(right) or _TWO_DIGIT_YEAR.fullmatch(right)):
        return False
    return True


def find_non_ascii_date_ranges(raw_text: str) -> list:
    """(line, dash) for every year joined to a non-ASCII dash in the raw text layer."""
    hits = []
    for match in NON_ASCII_DATE_RANGE.finditer(raw_text):
        dash = next(c for c in match.group(0) if c in NON_ASCII_DASHES)
        line_start = raw_text.rfind("\n", 0, match.start()) + 1
        line_end = raw_text.find("\n", match.end())
        line_end = len(raw_text) if line_end == -1 else line_end
        line = raw_text[line_start:line_end]
        dash_at = match.start() + match.group(0).index(dash) - line_start
        if _is_quantity_range(line, dash_at):
            continue
        hits.append((" ".join(line.split()), dash))
    return hits


def _extract_pypdf(path: Path):
    """(text, pages) through pypdf, or None when pypdf is missing, fails, or finds no text."""
    try:
        from pypdf import PdfReader  # optional dependency
    except ImportError:
        return None
    try:
        reader = PdfReader(str(path))
        pages = len(reader.pages)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:  # noqa: BLE001 - a broken reader falls through to Poppler
        return None
    if not normalize_text(text):
        return None
    return text, pages


def _run(command: list) -> str:
    try:
        done = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise UsageError(f"{command[0]} failed: {exc}") from exc
    if done.returncode != 0:
        raise UsageError(f"{command[0]} could not read the PDF: {(done.stderr or '').strip()[:200]}")
    return done.stdout


def _pdfinfo_pages(path: Path):
    if not shutil.which("pdfinfo"):
        return None
    match = re.search(r"^Pages:\s+(\d+)", _run(["pdfinfo", str(path)]), re.M)
    return int(match.group(1)) if match else None


def extract_text_layer(path: Path) -> tuple:
    """(raw text, pages or None, extractor name). Raises Skipped when no extractor can read the file."""
    hit = _extract_pypdf(path)
    if hit is not None:
        return hit[0], hit[1], "pypdf"
    if shutil.which("pdftotext"):
        text = _run(["pdftotext", "-raw", "-enc", "UTF-8", str(path), "-"])
        return text, _pdfinfo_pages(path), "pdftotext"
    raise Skipped("no text extractor: install pypdf (pip install pypdf) or Poppler (pdftotext)")


def verify(path: Path, pages=None, min_chars: int = 1, contains=(), dump_text=None, ascii_dates: bool = False) -> dict:
    """Run the requested checks. Returns the result; raises Skipped or UsageError; failures are listed, not raised."""
    if not path.is_file():
        raise UsageError(f"PDF does not exist: {path}")
    raw, actual, extractor = extract_text_layer(path)
    if dump_text is not None:
        dump_text.parent.mkdir(parents=True, exist_ok=True)
        dump_text.write_text(raw if raw.endswith("\n") else raw + "\n", encoding="utf-8")
    failures = []
    if pages is not None:
        if actual is None:
            raise Skipped("page count not measurable: install Poppler (pdfinfo) or pypdf; --pages not checked")
        if actual != pages:
            failures.append(f"expected {pages} page(s), found {actual} (extractor: {extractor})")
    folded = normalize_text(raw)
    chars = len(folded.replace(" ", ""))
    if chars < min_chars:
        failures.append(f"text layer has {chars} character(s), expected at least {min_chars} (extractor: {extractor})")
    for needle in contains:
        if normalize_text(needle) not in folded:
            failures.append(f"text layer is missing {needle!r} (extractor: {extractor})")
    if ascii_dates:
        for line, dash in find_non_ascii_date_ranges(raw):
            failures.append(f"date range joined by U+{ord(dash):04X} (use one ASCII hyphen): {line[:80]!r}")
    return {"extractor": extractor, "pages": actual, "chars": chars, "failures": failures}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check a PDF's page count and ATS-readable text layer.",
                                     epilog="Exit 0 pass, 1 a check failed, 2 usage error or skipped.")
    parser.add_argument("pdf", type=Path, help="PDF file to check")
    parser.add_argument("--pages", type=int, help="exact page count required")
    parser.add_argument("--min-chars", type=int, default=1, help="minimum non-space characters in the text layer")
    parser.add_argument("--contains", action="append", default=[], metavar="TEXT",
                        help="text that must appear in the text layer (folded); repeatable")
    parser.add_argument("--dump-text", type=Path, metavar="FILE", help="write the raw text layer (UTF-8)")
    parser.add_argument("--ascii-dates", action="store_true",
                        help="fail on a year joined to a non-ASCII dash in the raw layer")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = verify(args.pdf, args.pages, args.min_chars, args.contains, args.dump_text, args.ascii_dates)
    except Skipped as exc:
        print(f"skipped: {exc}", file=sys.stderr)
        return 2
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if result["failures"]:
        for failure in result["failures"]:
            print(f"fail: {failure}", file=sys.stderr)
        return 1
    print(f"verified {args.pdf} (extractor: {result['extractor']}, pages: {result['pages']}, "
          f"characters: {result['chars']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
