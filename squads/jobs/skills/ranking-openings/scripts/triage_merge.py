#!/usr/bin/env python3
"""Turn triage scores into a ranking: gates and deal-breakers are computed here, scores come from the scorer.

The scorer (a delegated subagent) reads one saved opening and returns four dimension scores with one-line notes,
plus strengths and gaps. It never decides a gate: eligibility, language, location, deal-breaker and the guard
verdict are computed from the opening's front matter and profile.md by score_analysis.py, the same code the deep
analysis uses. This script joins the two and hands the result to seen_state.py apply, which writes seen.json.

Input (--scores FILE, a JSON array; a scorer's output for one batch):
  {"key": "<seen.json key>", "status": "scored" | "expired" | "unreachable",
   "scores": {"technical": 0-100, "experience": 0-100, "behavioral": 0-100, "career": 0-100},
   "strengths": ["..."], "gaps": ["..."], "fetch_error": "..."}
  The opening folder comes from the entry's opening_id in seen.json (openings/<opening_id>/opening.md).

Output: the seen_state apply report on stdout (ranked, vetoed, expired, unreachable, gave_up, errors).
Exit 0 on success, 1 when any item could not be written (see errors).

Usage:
  triage_merge.py --project P --scores FILE [--dry-run] [--today YYYY-MM-DD] [--now ISO]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parents[1]  # .../skills/ranking-openings/scripts -> .../skills
CONTRACT = SKILLS / "jobs-contract" / "scripts"
ANALYSIS = SKILLS / "analyzing-jobs" / "scripts"
for folder in (CONTRACT, ANALYSIS):
    sys.path.insert(0, str(folder))

import jobs_common as jc  # noqa: E402
import score_analysis as sa  # noqa: E402
import seen_state as ss  # noqa: E402

DIMENSIONS = ("technical", "experience", "behavioral", "career")


def guard_severity(normal) -> int:
    """For a normalised verdict: 0 for 'clean', 2 for any warning line. Higher is more severe."""
    return 0 if normal == "clean" else 2


def most_severe_guard(intake, scorer):
    """The guard verdict a ranked row carries: the more severe of the intake check and the scorer's reading of the
    same text. A scorer's 'clean' never overrides an intake warning. Two different warnings are both kept. A missing
    verdict on one side defers to the other side. The result is normalised: 'clean', a warning line, or None."""
    a, b = ss.normal_guard(intake), ss.normal_guard(scorer)
    if a is None:
        return b
    if b is None:
        return a
    if a != b and guard_severity(a) == 2 and guard_severity(b) == 2:
        return ss.clip(f"{a}; {b}", ss.GUARD_MAX)
    return a if guard_severity(a) >= guard_severity(b) else b


def gates_for(project: Path, folder: Path, company: str, profile: dict, achievements: dict) -> dict:
    """The deterministic part of a triage row: gates, deal-breakers and the dates from the opening."""
    opening_fm, body = sa.read_opening(folder)
    policy = profile.get("languages_policy") if isinstance(profile.get("languages_policy"), dict) else None
    eligibility, eligibility_note = sa.eligibility_gate(profile, opening_fm, body)
    language, language_note = sa.language_gate(opening_fm, achievements, policy)
    location, location_note = sa.location_gate(profile, opening_fm)
    hits = sa.deal_breaker_hits(profile, body, {"company": {"name": company, "sector": ""}})
    return {
        "eligibility_gate": eligibility,
        "eligibility_note": eligibility_note,
        "language_gate": language,
        "language_note": language_note,
        "location_verdict": location,
        "location_note": location_note,
        "deal_breaker": bool(hits),
        "deal_breaker_hits": hits,
        "deadline": ss.optional_iso(opening_fm.get("deadline")) or None,
        "posted_at": ss.optional_iso(opening_fm.get("posted_at")) or None,
        "guard": opening_fm.get("guard"),
    }


def build_results(project: Path, items: list, today) -> tuple[list, list]:
    """(results for seen_state apply, errors found while building them)."""
    seen = ss.load_state(ss.state_path(project))["seen"]
    profile = sa.read_profile(project)
    achievements = sa.read_achievements(project)
    results, errors = [], []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("key"), str):
            errors.append({"key": None, "error": "item needs a string key"})
            continue
        key = item["key"]
        entry = seen.get(key)
        if not isinstance(entry, dict):
            errors.append({"key": key, "error": "no such key in seen.json"})
            continue
        status = item.get("status", "scored")
        if status != "scored":
            results.append({"key": key, "status": status, "fetch_error": item.get("fetch_error")})
            continue
        opening_id = entry.get("opening_id") or item.get("opening_id")
        if not opening_id or not isinstance(opening_id, str):
            errors.append({"key": key, "error": "entry has no opening_id; the scout must save opening.md first"})
            continue
        if not jc.valid_opening_id(opening_id):
            # An id is a folder name under openings/. A path such as ../../x would read a file outside the project.
            errors.append({"key": key, "error": f"opening_id {opening_id!r} is not a valid JOB-YYYYMMDD-<slug> id"})
            continue
        folder = project / "openings" / opening_id
        if not (folder / "opening.md").is_file():
            errors.append({"key": key, "error": f"openings/{opening_id}/opening.md is missing"})
            continue
        try:
            gates = gates_for(project, folder, str(entry.get("company") or ""), profile, achievements)
        except (ValueError, OSError) as exc:
            errors.append({"key": key, "error": f"cannot read the opening: {exc}"})
            continue
        # strengths and gaps go to seen.json exactly as the scorer wrote them; a deal-breaker is a flag, not an edit
        row = {"key": key, "status": "scored", "scores": item.get("scores") or {},
               "strengths": item.get("strengths") or [], "gaps": item.get("gaps") or []}
        row.update({k: v for k, v in gates.items() if k not in ("eligibility_note", "location_note", "deal_breaker_hits")})
        # The more severe of the intake check and the scorer's reading; a warning is never downgraded to clean.
        row["guard"] = most_severe_guard(gates.get("guard"), item.get("guard"))
        results.append(row)
    return results, errors


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Merge triage scores with computed gates and rank them.")
    ap.add_argument("--project", help="project folder (default: $JOBS_PROJECT or the current folder)")
    ap.add_argument("--scores", required=True, help="JSON array of scorer output")
    ap.add_argument("--dry-run", action="store_true", help="show the ranking without writing seen.json")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD (default: today)")
    ap.add_argument("--now", default=None, help="ISO date-time for retry floors (default: now)")
    args = ap.parse_args(argv)
    try:
        project = jc.project_dir(args.project)
        raw = json.loads(Path(args.scores).read_text(encoding="utf-8"))
        items = raw.get("results", []) if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            raise ValueError("scores must be a JSON array")
        today = ss.parse_day(args.today) if args.today else date.today()
        if args.today and today is None:
            raise ValueError("--today must be YYYY-MM-DD")
        results, errors = build_results(project, items, today)
    except (OSError, ValueError, SystemExit) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    fd, tmp = tempfile.mkstemp(prefix="triage-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(results, handle, ensure_ascii=False)
        argv_apply = ["apply", "--project", str(project), "--results", tmp, "--today", today.isoformat()]
        if args.now:
            argv_apply += ["--now", args.now]
        if args.dry_run:
            argv_apply.append("--dry-run")
        code = ss.main(argv_apply)
    finally:
        os.unlink(tmp)
    if errors:
        print(json.dumps({"merge_errors": errors}, indent=2, ensure_ascii=False), file=sys.stderr)
    return 1 if (errors or code) else 0


if __name__ == "__main__":
    sys.exit(main())
