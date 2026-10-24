#!/usr/bin/env python3
"""Aggregate the five review lens blocks into one review-N.json: verdict, corrections, warnings, status.

Usage:
  aggregate_review.py --lenses truthfulness.json ats.json recruiter.json hiring_manager.json writing.json \
      --round N [--id JOB-...] [--application-dir application] [--opening opening.md] \
      [--summary TEXT] [--out review-N.json] [--json]

Each lens file holds one lens block (shapes in references/lenses.md). The lens is the block's "lens" key, else the
file name (truthfulness.json, ats.json, recruiter.json, hiring_manager.json, writing.json). One file per lens.

Rules, applied deterministically:
- Blocking items are truthfulness draft findings and dropped company claims, ats keywords with evidence and hard
  defects that are not environment notes, recruiter blockers and market violations, hiring_manager stretches the
  interview-backtrack test cannot answer from the sources, and writing findings and language mismatches.
- The render report is read from application/render_report.json (required). Every defect there blocks in the ats
  lens, except the environment codes docx_missing and engine_missing (warnings). Keyword coverage below KEYWORD_MIN
  blocks, measured by the render (declared keyword gaps do not excuse it).
- A lens verdict must match its blocking items: PASS (truthfulness: FAIL) if and only if there is a blocking item.
- Every blocking item carries a correction. mode "replace" needs file, old and new (old must occur exactly once in
  that file when --application-dir is given). mode "instruction" needs instructions. Both need a type.
- No blocking item -> APPROVED. Blocking items -> FIX in round 1, NOT_APPROVED in any later round.
  truthfulness FAIL is therefore never APPROVED.
- --apply (the reviewer's normal run): wording and positioning are the reviewer's to fix, not a reason for another
  round. Writing findings, recruiter blockers and supported missing keywords are "soft": a soft `replace` correction is
  written into the application file at once (listed under `applied`; one already in place counts as applied, so a
  re-run after a re-render is safe; a JSON file that would no longer parse is left alone), and a soft `instruction`
  goes to `polish`, which the reviewer carries out itself before the hand-off. Only the hard items decide the verdict:
  truthfulness, dropped company claims, render and lens hard defects, keyword coverage, market and language rules,
  unanswerable hiring-manager stretches, confidential terms.
- A kept company claim needs a source URL the reviewer located itself (the flag alone is not evidence), and either
  source_excerpt (at least 40 characters of the fetched page text) or source_file (a captured page in the application
  folder). A URL that appears in --opening is refused.
- --id must be an opening id (JOB-YYYYMMDD-<slug>).
- Review text never carries contact data (an e-mail address or an international phone number is refused).
- A profile.md `confidential_terms` entry (read from the project that owns --application-dir) in any outward file
  (cv_content.json, cover_letter.md, answers.md, recruiter_message.md) is a blocking correction of lens `privacy`,
  whatever the lens verdicts say.

Exit codes: 0 aggregated, 1 rule violation (nothing written; rework the named lens), 2 unreadable or malformed input.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

LENSES = ("truthfulness", "ats", "recruiter", "hiring_manager", "writing")
CHECKS = ("numbers", "dates", "titles", "companies", "tools", "levels", "languages", "citation", "grounding")
CORRECTION_TYPES = ("content", "format", "strategy")
MARKET_CONVENTIONS = ("photo", "age", "marital_status", "references_line")
CEFR = ("A1", "A2", "B1", "B2", "C1", "C2")
SUMMARY_MAX_LINES = 5
TEXT_SUFFIXES = (".md", ".txt", ".json", ".html")
STATUS_FOR = {"APPROVED": "ready", "FIX": "in_review", "NOT_APPROVED": "not_approved"}
RENDER_ENV_CODES = ("docx_missing", "engine_missing")  # environment notes: a warning, never a block
KEYWORD_MIN = 0.8  # ATS keyword coverage below this blocks while a missing keyword has no declared gap
KEYWORD_FLOOR = 0.34  # below this the CV matches under a third of the posting: blocks even when every miss is a gap
SOURCE_EXCERPT_MIN = 40  # characters of fetched page text a kept company claim must quote
CONTACT_PATTERNS = (
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"),
    re.compile(r"\+\d{1,3}[ -]?\d[\d -]{6,}\d"),
)
URL_RE = re.compile(r"https?://[^\s)\]>\"'<]+")
JOBS_COMMON = Path(__file__).resolve().parents[2] / "jobs-contract" / "scripts" / "jobs_common.py"


def _load_jobs_common():
    spec = importlib.util.spec_from_file_location("jobs_common_for_review", JOBS_COMMON)
    assert spec is not None and spec.loader is not None, JOBS_COMMON
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_JC = _load_jobs_common()
valid_opening_id = _JC.valid_opening_id
OUTWARD_FILES = ("cv_content.json", "cover_letter.md", "answers.md", "recruiter_message.md")


class InputError(Exception):
    """Unreadable or malformed input: exit 2."""


def verdicts_for(lens: str) -> tuple:
    return ("PASS", "FAIL") if lens == "truthfulness" else ("PASS", "FIX")


def url_key(url: str) -> str:
    """Scheme, host and path of a URL, lower-cased, without query, fragment or trailing slash."""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower().rsplit("@", 1)[-1]
    return f"{parts.scheme.lower()}://{host}{parts.path.rstrip('/')}" if host else ""


class Collector:
    """Holds the rule violations (errors), the corrections, the warnings and the blocking count per lens."""

    def __init__(self, app_files, opening_refs, render=None, apply=False):
        self.apply = apply
        self.soft = []  # (lens, correction) of soft blocking items, decided by aggregate()
        self.hard = 0
        self.errors = []
        self.corrections = []
        self.warnings = []
        self.dropped = []
        self.blocking = {lens: 0 for lens in LENSES}
        self.app_files = app_files
        self.opening_refs = opening_refs
        self.render = render  # application/render_report.json as a dict, or None when absent
        self.declared_gaps = []  # keywords the ats lens says no achievement backs
        self.forced = 0  # blocking corrections found by the script itself (confidential terms), outside any lens

    def supported_claim(self, claim: dict) -> bool:
        """A kept company claim is evidenced by quoted page text or a captured page in the application folder."""
        excerpt = claim.get("source_excerpt")
        if isinstance(excerpt, str) and len(excerpt.strip()) >= SOURCE_EXCERPT_MIN:
            return True
        name = claim.get("source_file")
        return isinstance(name, str) and self.app_files is not None and bool((self.app_files.get(name) or "").strip())

    def error(self, where, message):
        self.errors.append(f"{where}: {message}")

    def text(self, item, key, where):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
        self.error(where, f"'{key}' must be a non-empty string")
        return ""

    def items(self, block, key, where):
        value = block.get(key)
        if not isinstance(value, list):
            self.error(where, f"'{key}' must be a list (empty when nothing is found)")
            return []
        return value

    def blocking_item(self, lens, where, raw, location, hard=True):
        self.blocking[lens] += 1
        if not location or not str(location).strip():
            self.error(where, "a blocking item needs a location")
        correction = self.check_correction(raw, where, location)
        if hard or not self.apply:
            self.hard += 1
            if correction is not None:
                self.corrections.append({"lens": lens, **correction})
        elif correction is not None:
            self.soft.append({"lens": lens, **correction})

    def check_correction(self, raw, where, location):
        if not isinstance(raw, dict):
            self.error(where, "a blocking item needs a correction object")
            return None
        ctype = raw.get("type")
        if ctype not in CORRECTION_TYPES:
            self.error(where, "correction type must be content, format or strategy")
            return None
        mode = raw.get("mode")
        if mode == "replace":
            return self._replace(raw, where, ctype, location)
        if mode == "instruction":
            instructions = raw.get("instructions")
            if not isinstance(instructions, str) or not instructions.strip():
                self.error(where, "instruction correction needs 'instructions'")
                return None
            return {"type": ctype, "location": location, "mode": "instruction", "instructions": instructions}
        self.error(where, "correction mode must be replace or instruction")
        return None

    def _replace(self, raw, where, ctype, location):
        file_name, old, new = raw.get("file"), raw.get("old"), raw.get("new")
        if not isinstance(file_name, str) or not file_name.strip():
            self.error(where, "replace correction needs 'file'")
            return None
        if not isinstance(old, str) or not old:
            self.error(where, "replace correction needs a non-empty 'old' text")
            return None
        if not isinstance(new, str):
            self.error(where, "replace correction needs 'new' text (an empty string deletes)")
            return None
        if old == new:
            self.error(where, "'old' and 'new' are identical")
            return None
        if self.app_files is not None:
            text = self.app_files.get(file_name)
            if text is None:
                self.error(where, f"'{file_name}' is not in the application folder")
                return None
            count = text.count(old)
            if count == 0 and self.apply and new and new in text:
                return {"type": ctype, "location": location, "mode": "replace", "file": file_name, "old": old,
                        "new": new, "already_applied": True}
            if count != 1:
                self.error(where, f"'old' occurs {count} times in {file_name}; quote a span that occurs once")
                return None
        return {"type": ctype, "location": location, "mode": "replace", "file": file_name, "old": old, "new": new}


def lens_truthfulness(c: Collector, block: dict) -> None:
    where = "truthfulness"
    grounding = block.get("grounding")
    if not isinstance(grounding, dict) or not isinstance(grounding.get("sources"), list):
        c.error(where, "'grounding' object with a 'sources' list is required")
        sources = []
    else:
        sources = grounding["sources"]
    for needed in ("achievements.yaml", "profile.md"):
        if needed not in sources:
            c.error(where, f"grounding must check {needed} as well as the application")
    for i, item in enumerate(c.items(block, "findings", where)):
        w = f"{where}.findings[{i}]"
        if not isinstance(item, dict):
            c.error(w, "finding must be an object")
            continue
        loc = c.text(item, "location", w)
        c.text(item, "text", w)
        c.text(item, "problem", w)
        if item.get("check") not in CHECKS:
            c.error(w, f"check must be one of {', '.join(CHECKS)}")
        kind = item.get("kind")
        if kind == "draft":
            c.blocking_item("truthfulness", w, item.get("correction"), loc)
        elif kind == "profile_consistency":
            conflict = item.get("conflicting_sources")
            if not isinstance(conflict, list) or not {"achievements.yaml", "profile.md"} <= set(conflict):
                c.error(w, "profile_consistency needs conflicting_sources naming achievements.yaml and profile.md")
            c.warnings.append(f"profile consistency ({loc}): the sources disagree; reconcile them, draft unchanged")
        else:
            c.error(w, "kind must be draft or profile_consistency")
    for i, claim in enumerate(c.items(block, "company_claims", where)):
        w = f"{where}.company_claims[{i}]"
        if not isinstance(claim, dict):
            c.error(w, "company claim must be an object")
            continue
        claim_text = c.text(claim, "claim", w)
        loc = c.text(claim, "location", w)
        reason = c.text(claim, "reason", w)
        url = claim.get("source_url")
        key = url_key(url) if isinstance(url, str) else ""
        if not key:
            c.error(w, "source_url must be an http(s) URL")
        elif key in c.opening_refs:
            c.error(w, "source URL comes from the opening body; locate the company page by search")
        if claim.get("source_located_by_reviewer") is not True:
            c.error(w, "source_located_by_reviewer must be true; the reviewer locates its own sources")
        verdict = claim.get("verdict")
        if verdict == "dropped":
            c.dropped.append({"claim": claim_text, "location": loc, "reason": reason})
            c.blocking_item("truthfulness", w, claim.get("correction"), loc)
        elif verdict != "kept":
            c.error(w, "verdict must be kept or dropped")
        elif not c.supported_claim(claim):
            c.error(w, "a kept company claim needs source_excerpt (at least 40 characters of the fetched page) or "
                       "source_file naming a captured page in the application folder; the located flag is not evidence")


def lens_ats(c: Collector, block: dict) -> None:
    where = "ats"
    cov = block.get("keyword_coverage")
    if isinstance(cov, bool) or not isinstance(cov, (int, float)) or not 0 <= cov <= 1:
        c.error(where, "keyword_coverage must be a number from 0 to 1")
    for i, item in enumerate(c.items(block, "missing", where)):
        w = f"{where}.missing[{i}]"
        if isinstance(item, str) and item.strip():
            c.declared_gaps.append(item.strip())
            c.warnings.append(f"gap, not written: keyword '{item}' has no supporting achievement")
            continue
        if not isinstance(item, dict):
            c.error(w, "missing keyword must be an object or a plain gap string")
            continue
        keyword = c.text(item, "keyword", w)
        evidence = item.get("evidence", "")
        if not isinstance(evidence, str):
            c.error(w, "'evidence' must be an achievement id or an empty string")
            continue
        if evidence.strip():
            c.blocking_item("ats", w, item.get("correction"), item.get("location"), hard=False)
        elif keyword:
            c.declared_gaps.append(keyword)
            c.warnings.append(f"gap, not written: keyword '{keyword}' has no supporting achievement")
    hard = 0
    for i, item in enumerate(c.items(block, "defects", where)):
        w = f"{where}.defects[{i}]"
        if not isinstance(item, dict):
            c.error(w, "defect must be an object")
            continue
        loc = c.text(item, "location", w)
        problem = c.text(item, "problem", w)
        if item.get("hard") is True and item.get("environment") is not True:
            hard += 1
            c.blocking_item("ats", w, item.get("correction"), loc)
        else:
            c.warnings.append(f"note ({loc}): {problem}")
    render_checks(c)
    pages = block.get("pages")
    if pages is not None:
        if not (isinstance(pages, dict) and isinstance(pages.get("expected"), int)
                and isinstance(pages.get("actual"), int)):
            c.error(where, "'pages' must hold integers 'expected' and 'actual'")
        elif pages["expected"] != pages["actual"] and hard == 0:
            c.error(where, "page count differs from expected; add a hard defect with a correction")


def render_checks(c: Collector) -> None:
    """The measured render, read into the ats lens. Each non-environment defect is a blocking item with a correction,
    and keyword coverage below KEYWORD_MIN is one too (declared keyword gaps do not excuse it). The ats lens verdict
    must then be FIX: a PASS beside these items is refused by the verdict rule in run_lens."""
    where = "render_report"
    if c.render is None:
        c.error(where, "application/render_report.json is missing: render the CV and the letter (rendering-cv) "
                       "and pass --application-dir before the review")
        return
    for i, item in enumerate(c.items(c.render, "defects", where)):
        w = f"{where}.defects[{i}]"
        if not isinstance(item, dict):
            c.error(w, "defect must be an object with code and message")
            continue
        code = str(item.get("code") or "").strip()
        message = str(item.get("message") or "").strip()
        if not code or not message:
            c.error(w, "defect needs code and message")
            continue
        if code in RENDER_ENV_CODES:
            c.warnings.append(f"render ({code}): {message}")
            continue
        c.blocking_item("ats", w, {"type": "content", "mode": "instruction",
                                   "instructions": f"fix the render defect {code} ({message}), re-render, and read "
                                                   "render_report.json again"}, "render_report.json")
    measured = c.render.get("keyword_coverage")
    if measured is None:
        return  # the analysis named no keywords
    if isinstance(measured, bool) or not isinstance(measured, (int, float)) or not 0 <= measured <= 1:
        c.error(where, "keyword_coverage must be a number from 0 to 1")
        return
    missing = c.render.get("missing_keywords") if isinstance(c.render.get("missing_keywords"), list) else []
    # A keyword the ats lens declared a gap (no achievement backs it) can never be written truthfully. When every
    # missing keyword is such a gap, coverage is a warning for the user, not a FIX loop that cannot end.
    gaps = {str(k).strip().lower() for k in c.declared_gaps}
    unbacked = [k for k in missing if str(k).strip().lower() not in gaps]
    if measured < KEYWORD_MIN and not unbacked and measured >= KEYWORD_FLOOR:
        c.warnings.append(f"keyword coverage {measured}: every missing keyword is a declared gap "
                          f"({', '.join(map(str, missing))}); the digest tells the user")
        return
    if measured < KEYWORD_MIN:
        c.blocking_item("ats", f"{where}.keyword_coverage", {
            "type": "content", "mode": "instruction",
            "instructions": f"measured keyword coverage is {measured}, below {KEYWORD_MIN}: work each supported "
                            f"keyword into its achievement bullet; missing keywords: {', '.join(map(str, missing))}"},
            "cv_ats.txt")


def lens_recruiter(c: Collector, block: dict) -> None:
    where = "recruiter"
    secs = block.get("seconds_to_understand")
    if isinstance(secs, bool) or not isinstance(secs, int) or secs < 0:
        c.error(where, "seconds_to_understand must be a whole number of seconds")
    if not isinstance(block.get("would_open_evidence"), bool):
        c.error(where, "would_open_evidence must be true or false")
    for i, item in enumerate(c.items(block, "blockers", where)):
        w = f"{where}.blockers[{i}]"
        if not isinstance(item, dict):
            c.error(w, "blocker must be an object")
            continue
        loc = c.text(item, "location", w)
        c.text(item, "problem", w)
        c.blocking_item("recruiter", w, item.get("correction"), loc, hard=False)
    market = block.get("market")
    if not isinstance(market, dict):
        c.error(where, "'market' object is required")
        return
    checked = market.get("checked")
    if not isinstance(checked, list) or not checked:
        c.error(where, "market.checked must list the conventions checked against profile.md")
    else:
        for convention in checked:
            if convention not in MARKET_CONVENTIONS + ("page_limit",):
                c.error(where, "unknown market check in 'checked': use photo, age, marital_status, "
                               "references_line or page_limit")
    for i, item in enumerate(c.items(market, "violations", f"{where}.market")):
        w = f"{where}.market.violations[{i}]"
        if not isinstance(item, dict):
            c.error(w, "violation must be an object")
            continue
        if item.get("convention") not in MARKET_CONVENTIONS + ("page_limit",):
            c.error(w, "convention must name one market check")
        loc = c.text(item, "location", w)
        c.text(item, "problem", w)
        c.blocking_item("recruiter", w, item.get("correction"), loc)
    limit = market.get("page_limit")
    if limit is not None:
        pages = market.get("pages")
        if not (isinstance(limit, int) and isinstance(pages, int) and not isinstance(limit, bool)
                and not isinstance(pages, bool)):
            c.error(where, "market.page_limit and market.pages must be integers when given")
        elif pages > limit and not any(
                isinstance(v, dict) and v.get("convention") == "page_limit"
                for v in market.get("violations") or []):
            c.error(where, f"market: {pages} pages against a limit of {limit}; add a page_limit violation "
                           "with a correction")


def lens_hiring_manager(c: Collector, block: dict) -> None:
    where = "hiring_manager"
    if not isinstance(block.get("can_do_the_job"), bool):
        c.error(where, "can_do_the_job must be true or false")
    for concern in c.items(block, "concerns", where):
        if isinstance(concern, str) and concern.strip():
            c.warnings.append(f"concern: {concern}")
        else:
            c.error(where, "every concern must be a non-empty string")
    for question in c.items(block, "interview_questions", where):
        if not isinstance(question, str):
            c.error(where, "every interview question must be a string")
    for i, item in enumerate(c.items(block, "stretches", where)):
        w = f"{where}.stretches[{i}]"
        if not isinstance(item, dict):
            c.error(w, "stretch must be an object")
            continue
        loc = c.text(item, "location", w)
        c.text(item, "claim", w)
        c.text(item, "backtrack_question", w)
        answerable = item.get("answerable_from_sources")
        if not isinstance(answerable, bool):
            c.error(w, "answerable_from_sources must be true or false")
        elif answerable is False:
            c.blocking_item("hiring_manager", w, item.get("correction"), loc)


def lens_writing(c: Collector, block: dict) -> None:
    where = "writing"
    for i, item in enumerate(c.items(block, "findings", where)):
        w = f"{where}.findings[{i}]"
        if not isinstance(item, dict):
            c.error(w, "finding must be an object")
            continue
        loc = c.text(item, "location", w)
        c.text(item, "text", w)
        c.text(item, "fix", w)
        c.blocking_item("writing", w, item.get("correction"), loc, hard=False)
    lang = block.get("language")
    if not isinstance(lang, dict):
        c.error(where, "'language' object is required")
        return
    for name in ("document_language", "opening_language"):
        if not isinstance(lang.get(name), str) or not lang.get(name):
            c.error(f"{where}.language", f"'{name}' must be a language code")
    for name in ("declared_level", "implied_level"):
        if lang.get(name) is not None and lang.get(name) not in CEFR:
            c.error(f"{where}.language", f"'{name}' must be a CEFR level or null")
    mismatches = []
    if lang.get("document_language") != lang.get("opening_language"):
        mismatches.append("document language differs from the opening language")
    declared, implied = lang.get("declared_level"), lang.get("implied_level")
    if declared and implied and declared != implied:
        mismatches.append(f"declared level {declared} differs from the level the letter implies, {implied}")
    if mismatches:
        location = lang.get("location") if isinstance(lang.get("location"), str) else "letter"
        c.blocking_item("writing", f"{where}.language", lang.get("correction"), location)


HANDLERS = {
    "truthfulness": lens_truthfulness,
    "ats": lens_ats,
    "recruiter": lens_recruiter,
    "hiring_manager": lens_hiring_manager,
    "writing": lens_writing,
}


def run_lens(c: Collector, lens: str, block: dict) -> None:
    HANDLERS[lens](c, block)
    verdict = block.get("verdict")
    allowed = verdicts_for(lens)
    if verdict not in allowed:
        c.error(lens, f"verdict must be {' or '.join(allowed)}")
        return
    count = c.blocking[lens]
    if verdict == "PASS" and count:
        c.error(lens, f"verdict PASS with {count} blocking item(s); set the verdict to {allowed[1]}")
    if verdict != "PASS" and not count:
        c.error(lens, f"verdict {verdict} needs a blocking item; use PASS or name the item")


def default_summary(verdict: str, corrections: list) -> str:
    if verdict == "APPROVED":
        return "Approved: all five lenses pass."
    per_lens = {}
    for item in corrections:
        per_lens[item["lens"]] = per_lens.get(item["lens"], 0) + 1
    detail = ", ".join(f"{lens} {per_lens[lens]}" for lens in (*LENSES, "privacy") if lens in per_lens)
    return f"{verdict}: {len(corrections)} correction(s) ({detail})."


def scan_contact(c: Collector, value, where: str) -> None:
    if isinstance(value, dict):
        for key, inner in value.items():
            scan_contact(c, inner, f"{where}.{key}")
    elif isinstance(value, list):
        for i, inner in enumerate(value):
            scan_contact(c, inner, f"{where}[{i}]")
    elif isinstance(value, str) and any(p.search(value) for p in CONTACT_PATTERNS):
        c.error(where, "contact data found in review text; quote around it instead")


def confidential_checks(c: Collector, terms: list) -> None:
    """Each outward file that names a confidential term is one blocking correction (lens `privacy`) that no lens
    verdict can wave through: a leak never passes review because a child missed it."""
    for name in OUTWARD_FILES:
        text = (c.app_files or {}).get(name)
        hits = _JC.confidential_hits(text, terms) if text else []
        if hits:
            c.forced += 1
            c.corrections.append({"lens": "privacy", "type": "content", "location": name, "mode": "instruction",
                                  "instructions": f"remove {', '.join(map(repr, hits))} from {name} (profile.md "
                                                  "confidential_terms): describe the work by sector and scope, then "
                                                  "re-render"})


def aggregate(blocks: dict, round_no: int, c: Collector, summary, review_id, confidential=()):
    if confidential:
        confidential_checks(c, list(confidential))
    for lens in LENSES:
        run_lens(c, lens, blocks[lens])
    total = c.hard + c.forced
    if total == 0:
        verdict = "APPROVED"
    else:
        verdict = "FIX" if round_no == 1 else "NOT_APPROVED"
    if summary is None:
        summary = default_summary(verdict, c.corrections)
    lines = [line for line in summary.splitlines() if line.strip()]
    if not lines or len(lines) > SUMMARY_MAX_LINES:
        c.error("summary_for_user", f"must be 1 to {SUMMARY_MAX_LINES} lines")
    review = {
        "id": review_id,
        "round": round_no,
        "verdict": verdict,
        "status": STATUS_FOR[verdict],
        "reviews": {lens: blocks[lens] for lens in LENSES},
        "corrections": c.corrections,
        "applied": [s for s in c.soft if s["mode"] == "replace"],
        "polish": [s for s in c.soft if s["mode"] == "instruction"],
        "dropped_claims": c.dropped,
        "warnings": c.warnings,
        "summary_for_user": summary,
    }
    scan_contact(c, review, "review")
    return review


def apply_soft(folder: Path, review: dict) -> None:
    """Write each soft replace into its file; a correction already in place, or one that breaks a JSON file, is
    marked instead of written."""
    for item in review["applied"]:
        if item.pop("already_applied", False):
            item["result"] = "already in place"
            continue
        path = folder / item["file"]
        text = path.read_text(encoding="utf-8")
        new_text = text.replace(item["old"], item["new"], 1)
        if path.suffix == ".json":
            try:
                json.loads(new_text)
            except ValueError:
                item["result"] = "not written: the file would no longer be valid JSON"
                continue
        path.write_text(new_text, encoding="utf-8")
        item["result"] = "written"


def load_blocks(paths) -> dict:
    blocks = {}
    for raw in paths:
        path = Path(raw)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise InputError(f"cannot read {path.name}: {exc.strerror}") from None
        except ValueError:
            raise InputError(f"{path.name} is not valid JSON") from None
        if not isinstance(data, dict):
            raise InputError(f"{path.name}: a lens block is a JSON object")
        lens = data.pop("lens", None) or path.stem.replace("-", "_")
        if lens not in LENSES:
            raise InputError(f"{path.name}: lens must be one of {', '.join(LENSES)}")
        if lens in blocks:
            raise InputError(f"two files given for the lens {lens}")
        blocks[lens] = data
    missing = [lens for lens in LENSES if lens not in blocks]
    if missing:
        raise InputError("missing lens block(s): " + ", ".join(missing))
    return blocks


def read_application(folder) -> dict:
    base = Path(folder)
    if not base.is_dir():
        raise InputError(f"{base} is not a folder")
    return {p.name: p.read_text(encoding="utf-8", errors="ignore")
            for p in sorted(base.iterdir()) if p.is_file() and p.suffix in TEXT_SUFFIXES}


def read_render(folder) -> dict | None:
    """application/render_report.json as a dict; None when the file is absent (a rule error, reported by the lens)."""
    path = Path(folder) / "render_report.json"
    if not path.is_file():
        return None
    data = _read_report(path)
    letter = Path(folder) / "render_report_letter.json"
    if letter.is_file():
        # The letter is rendered separately: its defects block the review the same way the CV's do.
        other = _read_report(letter)
        data = dict(data)
        data["defects"] = list(data.get("defects") or []) + [
            {**d, "document": "letter"} if isinstance(d, dict) else {"code": str(d), "document": "letter"}
            for d in (other.get("defects") or [])]
        data["warnings"] = list(data.get("warnings") or []) + list(other.get("warnings") or [])
    return data


def _read_report(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise InputError(f"{path.name} is not valid JSON") from None
    if not isinstance(data, dict):
        raise InputError(f"{path.name} must hold one JSON object")
    return data


def read_opening_refs(path) -> set:
    try:
        text = Path(path).read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise InputError(f"cannot read the opening: {exc.strerror}") from None
    return {url_key(m.group(0)) for m in URL_RE.finditer(text)} - {""}


def write_json(path, data) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Aggregate five review lens blocks into one review-N.json: verdict, corrections, status.")
    p.add_argument("--lenses", nargs="+", required=True, metavar="FILE",
                   help="one JSON block per lens: truthfulness, ats, recruiter, hiring_manager, writing")
    p.add_argument("--round", type=int, required=True,
                   help="review round: 1 for the first review; 2 or more for a correction or CHANGE review")
    p.add_argument("--id", dest="review_id", help="opening id, e.g. JOB-20260925-acme-data-analyst")
    p.add_argument("--application-dir", required=True,
                   help="application/ folder: replace corrections quote it exactly once, and its render_report.json "
                        "is read (required)")
    p.add_argument("--opening", help="opening.md; URLs in it are never accepted as company sources")
    p.add_argument("--summary", help="summary_for_user: 1 to 5 lines, in the user's language")
    p.add_argument("--out", help="write review-N.json here, only when every rule passes")
    p.add_argument("--json", action="store_true", help="print the review (or {ok: false, errors}) as JSON")
    p.add_argument("--apply", action="store_true",
                   help="fix wording and positioning in place: soft replace corrections are written into the "
                        "application (with --out), soft instructions are listed under polish; only hard items decide")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.round < 1:
            raise InputError("--round must be 1 or more")
        if args.review_id is not None and not valid_opening_id(args.review_id):
            raise InputError("--id must be an opening id: JOB-YYYYMMDD-<slug>, no slash or dot")
        blocks = load_blocks(args.lenses)
        app_files = read_application(args.application_dir) if args.application_dir else None
        render = read_render(args.application_dir) if args.application_dir else None
        refs = read_opening_refs(args.opening) if args.opening else set()
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    c = Collector(app_files, refs, render, apply=args.apply)
    profile = Path(args.application_dir).resolve().parents[2] / "profile.md" if args.application_dir else None
    try:
        terms = _JC.confidential_terms(_JC.read_front_matter(profile)) if profile and profile.is_file() else []
    except Exception:  # noqa: BLE001 - an unreadable profile is validate_profile's finding, not the review's
        terms = []
    review = aggregate(blocks, args.round, c, args.summary, args.review_id, terms)
    if c.errors:
        for line in c.errors:
            print(f"rule: {line}", file=sys.stderr)
        if args.json:
            print(json.dumps({"ok": False, "errors": c.errors}, indent=2, ensure_ascii=False))
        return 1
    if args.out:
        if args.apply:
            apply_soft(Path(args.application_dir), review)
        write_json(args.out, review)
    if args.json:
        print(json.dumps(review, indent=2, ensure_ascii=False))
    else:
        print(f"verdict: {review['verdict']} (status {review['status']})")
        for item in review["corrections"]:
            print(f"- [{item['lens']}] {item['type']} at {item['location']} ({item['mode']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
