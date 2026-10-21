#!/usr/bin/env python3
"""Check a rendered CV or letter for layout faults that a page count does not show.

A PDF can have the right page count, a clean text layer and still look broken. This script measures the word boxes
(Poppler `pdftotext -bbox`) and reports:

  hole          a gap above 100pt between two body lines (an entry pushed to the next page leaves one)
  page ends early   a page that is not the last stops more than 25% above the bottom margin
  thin last page    the last page is more than 35% empty (reads as an unfinished document)
  stranded heading  a section heading is the last line of a page; its content starts on the next page
  orphaned entry    a page ends on a job or project title while its bullets resume on the next page
  footer collision  body text sits inside the bottom 90pt band reserved for the page footer
  empty page        a page with no text

Page count is NOT checked here: verify_pdf.py --pages does that. Exit codes: 0 clean, 1 layout problems,
2 usage error or skipped (no pdftotext with -bbox). No network. Stdlib only.
"""
from __future__ import annotations

import argparse
import functools
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

GAP_LIMIT_PT = 100.0
BOTTOM_LIMIT_FRACTION = 0.25
LAST_PAGE_THIN_FRACTION = 0.35
FOOTER_BAND_PT = 90.0
INDENT_PT = 8.0
SAME_LINE_PT = 3.0
# Templates set headings about 1.15 to 1.2 times body size (classic h2 12.5pt on 10.5pt body): 1.12 catches them.
HEADING_HEIGHT_RATIO = 1.12

PAGE_RE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', re.S)
WORD_RE = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="[\d.]+" yMax="([\d.]+)">([^<]*)</word>')
TEXT_RE = re.compile(r"\w")


class Skipped(Exception):
    """No Poppler with -bbox: the layout check is not run."""


@dataclass
class Line:
    top: float
    bottom: float
    left: float
    height: float
    text: str


class Page:
    def __init__(self, height: float, lines: list):
        self.height = height
        self.lines = sorted(lines, key=lambda ln: ln.top)
        self.body = [ln for ln in self.lines if ln.top < height - FOOTER_BAND_PT and TEXT_RE.search(ln.text)]

    @property
    def empty(self) -> bool:
        return not self.body

    @property
    def bottom_space(self) -> float:
        return self.height - max(ln.bottom for ln in self.body) if self.body else self.height

    @property
    def median_height(self) -> float:
        heights = sorted(ln.height for ln in self.body)
        return heights[len(heights) // 2] if heights else 0.0

    def largest_gap(self) -> tuple:
        tops = sorted({round(ln.top, 1) for ln in self.body})
        if len(tops) < 2:
            return 0.0, 0.0
        return max((tops[i + 1] - tops[i], tops[i]) for i in range(len(tops) - 1))

    def footer_crowded(self) -> bool:
        band = self.height - FOOTER_BAND_PT
        return len({round(ln.top, 1) for ln in self.lines if ln.top >= band}) > 1

    def is_heading(self, line: Line) -> bool:
        return bool(self.median_height) and line.height > self.median_height * HEADING_HEIGHT_RATIO


@functools.lru_cache(maxsize=1)
def find_pdftotext():
    """A pdftotext that supports -bbox. Git for Windows ships an xpdf build without it; try each PATH entry."""
    candidates = []
    for entry in os.get_exec_path():
        found = shutil.which("pdftotext", path=entry)
        if found and found not in candidates:
            candidates.append(found)
    for candidate in candidates:
        try:
            probe = subprocess.run([candidate, "-h"], capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", timeout=20)
        except (OSError, subprocess.SubprocessError):
            continue
        if "-bbox" in (probe.stdout or "") + (probe.stderr or ""):
            return candidate
    return None


def parse_pages(path: Path) -> list:
    binary = find_pdftotext()
    if binary is None:
        raise Skipped("pdftotext (Poppler) with -bbox not found: install poppler (brew install poppler, "
                      "apt install poppler-utils)")
    done = subprocess.run([binary, "-bbox", "-enc", "UTF-8", str(path), "-"], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)
    if done.returncode != 0:
        detail = (done.stderr or "").strip().splitlines()[:1]
        raise Skipped(f"pdftotext could not produce word boxes ({detail[0] if detail else done.returncode}); "
                      "some Poppler builds abort on PDFs with empty Info fields: set a title in the HTML")
    pages = []
    for width, height, body in PAGE_RE.findall(done.stdout):
        del width
        rows: dict = {}
        for x_min, y_min, y_max, word in WORD_RE.findall(body):
            rows.setdefault(round(float(y_min)), []).append((float(x_min), float(y_min), float(y_max), word))
        lines = []
        for words in rows.values():
            words.sort()
            lines.append(Line(top=min(w[1] for w in words), bottom=max(w[2] for w in words),
                              left=min(w[0] for w in words), height=max(w[2] - w[1] for w in words),
                              text=" ".join(w[3] for w in words)))
        pages.append(Page(float(height), lines))
    return pages


def find_stranded_and_orphans(pages: list) -> list:
    problems = []
    body_lines = [ln for p in pages for ln in p.body]
    if not body_lines:
        return problems
    margin = min(ln.left for ln in body_lines)
    for i in range(len(pages) - 1):
        here, nxt = pages[i], pages[i + 1]
        if here.empty or nxt.empty:
            continue
        last = here.body[-1]
        first = nxt.body[0]
        if here.is_heading(last):
            problems.append(f"p{i + 1} ends on the heading {last.text.strip()[:50]!r} with its content on p{i + 2}")
            continue
        # A title is set flush left; its bullets are indented. The last title line on this page is followed by an
        # indented first line on the next page.
        if last.left <= margin + INDENT_PT and first.left > margin + INDENT_PT and not here.is_heading(first):
            problems.append(f"p{i + 1} ends on {last.text.strip()[:50]!r} while its bullets resume on p{i + 2}: "
                            "keep the entry together (shorten it or move it)")
    return problems


def report(path: Path, pages: list) -> list:
    problems = []
    print(f"{path}: {len(pages)} page(s)")
    for i, page in enumerate(pages, 1):
        if page.empty:
            problems.append(f"p{i} contains no text")
            print(f"  p{i}: EMPTY")
            continue
        gap, gap_y = page.largest_gap()
        share = page.bottom_space / page.height
        print(f"  p{i}: text {page.body[0].top:.0f}..{page.body[-1].bottom:.0f} of {page.height:.0f}pt | "
              f"bottom {page.bottom_space:.0f}pt ({share * 100:.0f}%) | largest gap {gap:.0f}pt at y{gap_y:.0f}")
        if gap > GAP_LIMIT_PT:
            problems.append(f"p{i} has a {gap:.0f}pt hole at y{gap_y:.0f}: shorten the entry after it or move a "
                            "shorter section above it")
        if i < len(pages) and share > BOTTOM_LIMIT_FRACTION:
            problems.append(f"p{i} ends {share * 100:.0f}% early although more pages follow")
        if page.footer_crowded():
            problems.append(f"p{i} has body text inside the footer band: cut content instead of stretching the page")
        if i == len(pages) > 1 and share > LAST_PAGE_THIN_FRACTION:
            problems.append(f"p{i} is the last page and {share * 100:.0f}% empty: it reads as unfinished")
    problems.extend(find_stranded_and_orphans(pages))
    return problems


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check a rendered CV or letter for holes, early page ends, thin "
                                                 "last pages, stranded headings and split entries.",
                                     epilog="Exit 0 clean, 1 layout problems, 2 usage error or skipped.")
    parser.add_argument("pdf", type=Path, help="rendered PDF")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not args.pdf.is_file():
        print(f"error: {args.pdf} not found", file=sys.stderr)
        return 2
    try:
        pages = parse_pages(args.pdf)
    except Skipped as exc:
        print(f"skipped: {exc}", file=sys.stderr)
        return 2
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    problems = report(args.pdf, pages)
    if problems:
        print("LAYOUT PROBLEMS:")
        for line in problems:
            print(f"  - {line}")
        return 1
    print("layout: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
