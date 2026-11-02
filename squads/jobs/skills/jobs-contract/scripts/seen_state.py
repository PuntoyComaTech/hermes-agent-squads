#!/usr/bin/env python3
"""Dedupe and rank state for one job search: <project>/searches/seen.json.

Subcommands print JSON on stdout. Errors go to stderr with exit 1.
  candidates  entries to fetch and score this run (status new or unreachable; tracker pairs excluded)
  apply       write scoring results back; print the ranking, retries, expiries and errors
  sweep       deadline pass over stored entries: a passed deadline expires, a close one is listed
  add         register entries from a search (an existing entry keeps its status). An entry whose employer_url
              (the employer's own ATS posting) another entry already holds becomes an alias of that entry: one entry
              per employer posting, the owner keeps its status, and its opening gets a status history line
  audit       check the state file for malformed entries, repeated company+title pairs and one employer posting
              under several entries
  stats       counts by status and band, plus stale and closing-soon counts

State file: {"schema": 1, "seen": {"<job key>": {...}}}. Writes are atomic (jobs_common.write_json).
An entry's employer posting is its employer_url, else its opening's apply_url. `candidates` never selects a second
entry of one employer posting, nor one whose posting a tracker.csv row already holds, nor one whose own or alias
title matches a tracker.csv company+role pair.

Scoring (also used by analyzing-jobs/scripts/score_analysis.py): the overall score is the weighted mean of the
four dimensions with profile.md scoring.weights (defaults 30/25/15/30), rounded half up. The band comes from
scoring.bands (defaults strong 75, good 60, moderate 45, weak 30; below that is poor).
Location is a verdict (PASS, FAIL, FLAG), never a weight. Statuses: new, ranked, skipped, expired, unreachable.

Usage:
  seen_state.py candidates --project P [--all] [--focus TEXT] [--limit N]
  seen_state.py apply --project P --results FILE [--dry-run] [--now ISO]
  seen_state.py sweep --project P [--write] [--exclude KEY,KEY]
  seen_state.py add --project P --file FILE|-
  seen_state.py audit --project P [--strict]
  seen_state.py stats --project P
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs_common as jc  # noqa: E402
import job_key as jk  # noqa: E402

SCHEMA = 1
STATUSES = ("new", "ranked", "skipped", "expired", "unreachable")
SWEEPABLE = ("new", "ranked", "unreachable")
AGENT_STATUSES = ("scored", "expired", "unreachable")
VERDICTS = ("PASS", "FAIL", "FLAG")
DIMENSIONS = ("technical", "experience", "behavioral", "career")
DEFAULT_WEIGHTS = {"technical": 30, "experience": 25, "behavioral": 15, "career": 30}
DEFAULT_BANDS = {"strong": 75, "good": 60, "moderate": 45, "weak": 30}
DEFAULT_APPLY_THRESHOLD = 70  # the value profile-files documents; a writer card needs at least this score
BAND_ORDER = ("strong", "good", "moderate", "weak")
DEFAULT_LIMIT = 10
URGENT_DAYS = 7
STALE_DAYS = 30
UNREACHABLE_MAX_ATTEMPTS = 3
UNREACHABLE_MIN_SPAN = timedelta(hours=48)
FETCH_ERROR_MAX = 200
GUARD_MAX = 200
NOTE_MAX = 300
ITEM_MAX = 300
LIST_MAX = 3
TIMESTAMP = "%Y-%m-%dT%H:%M:%SZ"
RETRY_FIELDS = ("fetch_attempts", "first_unreachable", "last_fetch_error")
ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class StateError(Exception):
    """A state file or input that cannot be used. Reported on stderr with exit 1."""


# --- text, numbers and dates --------------------------------------------------------------------------------------

def fold(text) -> str:
    """Casefold, drop accents, keep letters and digits of any script, join words with single spaces."""
    flat = unicodedata.normalize("NFKD", str(text or "").casefold())
    flat = "".join(ch for ch in flat if not unicodedata.combining(ch))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in flat).split())


def norm(text) -> str:
    """fold() without spaces: the identity used for tracker and company matching."""
    return fold(text).replace(" ", "")


def clip(text, limit: int = NOTE_MAX) -> str:
    """One line of plain text, capped. Used for short reasons shown in reports."""
    return " ".join(str(text or "").split())[:limit]


def cap(text, limit: int = NOTE_MAX) -> str:
    """Text kept verbatim (only the ends trimmed), capped. Used for agent notes stored as written."""
    return str(text or "").strip()[:limit]


def clip_list(value):
    """Up to LIST_MAX items stored as written, each capped; None when the value is not a list."""
    if not isinstance(value, list):
        return None
    return [cap(item, ITEM_MAX) for item in value][:LIST_MAX]


def check_number(value, label: str, low: float = 0, high: float = 100) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label} must be a finite number")
    if not low <= value <= high:
        raise ValueError(f"{label} must be between {low:g} and {high:g}")
    return float(value)


def tidy(value):
    """An integral float as int, so 30.0 prints as 30."""
    number = float(value)
    return int(number) if number.is_integer() else round(number, 2)


def as_iso(value):
    """YYYY-MM-DD for a date string or date object; None for anything else. Never guesses."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and ISO.match(value.strip()):
        try:
            return date.fromisoformat(value.strip()).isoformat()
        except ValueError:
            return None
    return None


def parse_day(value):
    iso = as_iso(value)
    return date.fromisoformat(iso) if iso else None


def optional_iso(value):
    """YYYY-MM-DD; None for an absent or 'unknown' value; False for anything else (a bad date to report)."""
    if value in (None, "") or (isinstance(value, str) and value.strip().lower() in ("unknown", "none", "null")):
        return None
    return as_iso(value) or False


def parse_timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value.strip(), TIMESTAMP).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_now(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _day_arg(text: str) -> date:
    parsed = parse_day(text)
    if parsed is None:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD")
    return parsed


# --- scoring ----------------------------------------------------------------------------------------------------

def _named(value, defaults: dict, label: str) -> dict:
    if value is None:
        return dict(defaults)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a mapping")
    missing = [key for key in defaults if key not in value]
    if missing:
        raise ValueError(f"{label} must set {', '.join(defaults)} (missing: {', '.join(missing)})")
    return {key: tidy(check_number(value[key], f"{label}.{key}")) for key in defaults}


def scoring_config(profile: dict) -> dict:
    """weights, bands and apply_threshold from profile.md. Defaults apply when a key is absent; bad values raise."""
    block = profile.get("scoring")
    if block is not None and not isinstance(block, dict):
        raise ValueError("scoring must be a mapping")
    block = block or {}
    weights = _named(block.get("weights"), DEFAULT_WEIGHTS, "scoring.weights")
    total = sum(weights.values())
    if abs(total - 100) > 1e-6:
        raise ValueError(f"scoring.weights must sum to 100 (got {total:g})")
    bands = _named(block.get("bands"), DEFAULT_BANDS, "scoring.bands")
    levels = [bands[name] for name in BAND_ORDER]
    if any(a < b for a, b in zip(levels, levels[1:])):
        raise ValueError("scoring.bands must not increase: strong >= good >= moderate >= weak")
    threshold = profile.get("apply_threshold")
    apply_threshold = DEFAULT_APPLY_THRESHOLD if threshold is None else tidy(check_number(threshold, "apply_threshold"))
    return {"weights": weights, "bands": bands, "apply_threshold": apply_threshold}


def dimension_score(scores: dict, dim: str) -> float:
    raw = scores.get(dim)
    if isinstance(raw, dict):
        raw = raw.get("score")
    return check_number(raw, f"score '{dim}'")


def overall_score(scores, weights: dict) -> int:
    if not isinstance(scores, dict):
        raise ValueError("scores must be an object")
    total = sum(dimension_score(scores, dim) * weight for dim, weight in weights.items())
    return int(math.floor(total / 100.0 + 0.5 + 1e-9))


def band_for(score: int, bands: dict) -> str:
    for name in BAND_ORDER:
        if score >= bands[name]:
            return name
    return "poor"


# --- files ------------------------------------------------------------------------------------------------------

def state_path(project: Path) -> Path:
    return project / "searches" / "seen.json"


def tracker_path(project: Path) -> Path:
    return project / "tracker.csv"


def read_profile(project: Path) -> dict:
    return jc.read_front_matter(project / "profile.md")


def load_state(path: Path) -> dict:
    """The state document. A missing file is an empty state, so a first run needs no setup."""
    if not path.is_file():
        return {"schema": SCHEMA, "seen": {}}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateError(f"{path} is not readable JSON: {exc}")
    if not isinstance(doc, dict) or not isinstance(doc.get("seen"), dict):
        raise StateError(f'{path}: expected {{"schema": {SCHEMA}, "seen": {{...}}}}')
    return doc


def save_state(path: Path, doc: dict) -> None:
    doc["schema"] = SCHEMA
    jc.write_json(path, doc)


def tracker_pairs(path: Path) -> set:
    """company+role pairs already in tracker.csv. Those openings are out of scope for ranking."""
    if not path.is_file():
        return set()
    pairs = set()
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                company = norm(row.get("company"))
                if company:
                    pairs.add((company, norm(row.get("role"))))
    except UnicodeDecodeError:
        raise StateError(f"{path} is not UTF-8 text; re-save it as CSV UTF-8")
    return pairs


def load_results(path: str) -> list:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise StateError(f"cannot read results file {path}: {exc}")
    if isinstance(data, dict):
        data = data.get("results")
    if not isinstance(data, list):
        raise StateError("results must be a JSON array of scoring objects")
    return data


def read_items(path: str) -> list:
    try:
        text = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, ValueError) as exc:
        raise StateError(f"cannot read entries from {path}: {exc}")
    if isinstance(data, dict):
        data = data.get("entries")
    if not isinstance(data, list):
        raise StateError("entries must be a JSON array (or an object with an 'entries' array)")
    return data


# --- entry helpers ----------------------------------------------------------------------------------------------

def brief(key: str, entry: dict, **extra) -> dict:
    row = {"key": key, "title": entry.get("title"), "company": entry.get("company"), "url": entry.get("url")}
    row.update(extra)
    return row


def posted_age_days(entry: dict, today: date):
    posted = parse_day(entry.get("posted_at"))
    return None if posted is None else (today - posted).days


def is_stale(age) -> bool:
    return age is not None and age > STALE_DAYS


def clear_retry(entry: dict) -> None:
    for field in (*RETRY_FIELDS, "expired_reason"):
        entry.pop(field, None)


def retire(entry: dict, reason: str) -> None:
    clear_retry(entry)
    entry["status"] = "expired"
    entry["expired_reason"] = reason


def verdict_or(value, stored):
    """A verdict from the agent, else the stored one, else FLAG (visible, not vetoed). Bad values raise."""
    if value in (None, ""):
        return stored if stored in VERDICTS else "FLAG"
    if value not in VERDICTS:
        raise ValueError(f"verdict must be PASS, FAIL or FLAG (got {value!r})")
    return value


def normal_guard(raw):
    """The posting_guard verdict as stored: 'clean', or the warning line without its prefix."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    if text.lower().startswith("posting_guard:"):
        text = text[len("posting_guard:"):].strip()
    if text.lower().startswith("clean"):
        return "clean"
    return text[:GUARD_MAX]


def veto_reasons(row: dict) -> list:
    """Why a ranked row is kept off the shortlist: a FAIL gate or a deal-breaker phrase. Empty when none."""
    reasons = []
    for field, label in (("location_verdict", "location"), ("language_gate", "language"),
                         ("eligibility_gate", "eligibility")):
        if row.get(field) == "FAIL":
            reasons.append(label)
    if row.get("deal_breaker"):
        reasons.append("deal_breaker")
    return reasons


def sort_key(item):
    key, entry = item
    deadline = parse_day(entry.get("deadline"))
    return (deadline is None, deadline or date.max, key)


# --- one entry per employer posting ------------------------------------------------------------------------------

ALIAS_MAX = 50


def alias_keys(seen: dict) -> dict:
    """Portal key of an alias -> the key of the entry that holds it."""
    index = {}
    for key, entry in seen.items():
        if isinstance(entry, dict):
            for alias in entry.get("aliases") or []:
                if isinstance(alias, dict) and alias.get("key"):
                    index.setdefault(alias["key"], key)
    return index


def entry_employer_url(entry: dict, openings: dict) -> str:
    """The canonical employer posting of an entry: its own employer_url, else its opening's apply_url."""
    return jk.employer_url(entry.get("employer_url")) or openings.get(entry.get("opening_id") or "", "")


def posting_groups(seen: dict, openings: dict) -> dict:
    """Canonical employer URL -> the seen keys that hold it, owner first: the first seen, then the oldest opening id.

    An entry holds a posting through its employer_url or its opening's apply_url. The owner is the one entry a
    posting keeps; every other key of the group is a re-listing.
    """
    groups: dict = {}
    for key, entry in seen.items():
        if isinstance(entry, dict):
            canon = entry_employer_url(entry, openings)
            if canon:
                groups.setdefault(canon, []).append(
                    (str(entry.get("first_seen") or "9999"), entry.get("opening_id") or "~", key))
    return {canon: [row[2] for row in sorted(rows)] for canon, rows in groups.items()}


def note_relisting(project: Path, opening_id, text: str) -> bool:
    """One status.json history line on the opening that owns the posting; its status does not change."""
    if not opening_id or not jc.valid_opening_id(opening_id):
        return False
    folder = project / "openings" / opening_id
    try:
        current = json.loads((folder / "status.json").read_text(encoding="utf-8")).get("status")
    except (OSError, ValueError, AttributeError):
        return False
    if not current:
        return False
    import status as st  # noqa: E402 - only a re-listing writes a history line
    st.append(folder, current, "jobs-scout", text)
    return True


def absorb(project: Path, seen: dict, owner: str, key: str, item: dict, today: date) -> dict:
    """Record listing `key` as an alias of entry `owner` (one entry per employer posting) and drop `key` as an entry.

    The owner keeps its status, so a re-listing never resurrects a skipped, expired or applied opening. The owner's
    opening gets a history line naming the second listing. Returns the report row.
    """
    entry = seen[owner]
    old = seen.pop(key, None) if key != owner else None
    source = old if isinstance(old, dict) else item
    alias = {"key": key, "title": clip(source.get("title"), 200), "url": clip(source.get("url"), 500) or None,
             "portal": clip(source.get("portal"), 80) or None, "first_seen": source.get("first_seen") or today.isoformat()}
    if source.get("opening_id"):
        alias["opening_id"] = source["opening_id"]
    aliases = [a for a in entry.get("aliases") or [] if isinstance(a, dict) and a.get("key") != key]
    entry["aliases"] = (aliases + [{k: v for k, v in alias.items() if v}])[-ALIAS_MAX:]
    for nested in (old or {}).get("aliases") or []:
        if isinstance(nested, dict) and nested.get("key") not in {a.get("key") for a in entry["aliases"]}:
            entry["aliases"].append(nested)
    where = f"{alias.get('portal') or 'listing'} {alias.get('url') or key}"
    noted = note_relisting(project, entry.get("opening_id"),
                           f"re-listed as '{alias['title']}' ({where}); same employer posting, not a new opening")
    return {"key": key, "alias_of": owner, "opening_id": entry.get("opening_id"), "status": entry.get("status"),
            "history_noted": noted}


# --- commands ---------------------------------------------------------------------------------------------------

def known_titles(entry: dict) -> list:
    """The entry's own title and every alias title: the role names one employer posting was listed under."""
    return [entry.get("title")] + [a.get("title") for a in entry.get("aliases") or [] if isinstance(a, dict)]


def cmd_candidates(args) -> dict:
    seen = load_state(args.state)["seen"]
    excluded = tracker_pairs(args.tracker)
    openings = jk.opening_employer_urls(args.project)
    applied = jk.tracker_employer_urls(args.project)
    relistings = {key: keys[0] for keys in posting_groups(seen, openings).values() for key in keys[1:]}
    chosen, skipped_tracker, skipped_relisting = [], 0, []
    for key, entry in seen.items():
        if not isinstance(entry, dict):
            continue
        if key in relistings:
            # A second listing of an employer posting another entry owns: never a candidate of its own.
            skipped_relisting.append({"key": key, "alias_of": relistings[key]})
            continue
        status = entry.get("status")
        if args.all:
            if status == "skipped":
                continue
        elif status not in ("new", "unreachable"):
            continue
        if args.saved and not entry.get("opening_id"):
            continue  # triage scores saved openings only; an entry without opening.md is not yet triageable
        if not args.all and entry.get("analysis_decision"):
            continue  # already deep-analysed (analyzing-jobs wrote the decision here); --all re-triages it
        company = norm(entry.get("company"))
        canon = entry_employer_url(entry, openings)
        if (canon and applied.get(canon, entry.get("opening_id")) != entry.get("opening_id")) \
                or any((company, norm(title)) in excluded for title in known_titles(entry)):
            skipped_tracker += 1
            continue
        if args.focus:
            haystack = " ".join(
                [str(entry.get("title") or ""), str(entry.get("company") or "")]
                + [str(item) for item in (entry.get("strengths") or []) + (entry.get("gaps") or [])]
            )
            if args.focus.casefold() not in haystack.casefold():
                continue
        chosen.append((key, entry))
    chosen.sort(key=sort_key)
    eligible = len(chosen)
    shown = chosen[: args.limit] if args.limit > 0 else chosen
    selected = []
    for key, entry in shown:
        selected.append({
            "key": key,
            "title": entry.get("title"),
            "company": entry.get("company"),
            "url": entry.get("url"),
            "portal": entry.get("portal"),
            "status": entry.get("status"),
            "deadline": entry.get("deadline"),
            "posted_at": entry.get("posted_at"),
            "opening_id": entry.get("opening_id"),
        })
    return {
        "eligible": eligible,
        "selected": selected,
        "deferred": eligible - len(shown),
        "excluded_by_tracker": skipped_tracker,
        "excluded_as_relisting": skipped_relisting,
        "total_entries": len(seen),
    }


def _apply_unreachable(key, entry, result, today, now):
    deadline = parse_day(entry.get("deadline"))
    if deadline is not None and deadline < today:
        retire(entry, "deadline_passed")
        return "expired", brief(key, entry)
    previous = entry.get("fetch_attempts")
    previous = previous if isinstance(previous, int) and not isinstance(previous, bool) else 0
    attempts = previous + 1
    first = parse_timestamp(entry.get("first_unreachable")) or now
    entry["fetch_attempts"] = attempts
    entry["first_unreachable"] = first.strftime(TIMESTAMP)
    error = clip(result.get("fetch_error"), FETCH_ERROR_MAX)
    if error:
        entry["last_fetch_error"] = error
    row = brief(key, entry, fetch_attempts=attempts, last_fetch_error=entry.get("last_fetch_error"))
    if attempts >= UNREACHABLE_MAX_ATTEMPTS and now - first >= UNREACHABLE_MIN_SPAN:
        entry["status"] = "expired"
        entry["expired_reason"] = "unreachable"
        return "gave_up", row
    entry["status"] = "unreachable"
    return "unreachable", row


def _apply_scored(key, entry, result, today, now, cfg, warnings):
    # Validate everything before touching the entry, so a bad result leaves no half-written state.
    scores = result.get("scores")
    score = overall_score(scores, cfg["weights"])
    loc = verdict_or(result.get("location_verdict"), entry.get("location_verdict") or entry.get("location"))
    lang = verdict_or(result.get("language_gate"), entry.get("language_gate"))
    elig = verdict_or(result.get("eligibility_gate"), entry.get("eligibility_gate"))
    deal_breaker = result.get("deal_breaker")
    if deal_breaker is not None and not isinstance(deal_breaker, bool):
        raise ValueError("deal_breaker must be true or false")
    fresh_deadline = parse_day(result.get("deadline"))
    if result.get("deadline") not in (None, "") and fresh_deadline is None:
        warnings.append({"key": key, "warning": f"deadline {result.get('deadline')!r} is not YYYY-MM-DD; ignored"})
    deadline = fresh_deadline or parse_day(entry.get("deadline"))
    if deadline is not None and deadline < today:
        if fresh_deadline is not None:
            entry["deadline"] = fresh_deadline.isoformat()
        retire(entry, "deadline_passed")
        return "expired", brief(key, entry)

    if fresh_deadline is not None:
        entry["deadline"] = fresh_deadline.isoformat()
    posted = parse_day(result.get("posted_at"))
    if posted is not None:
        entry["posted_at"] = posted.isoformat()
    clear_retry(entry)
    if entry.get("location") in VERDICTS:
        entry.pop("location")  # a legacy verdict stored as the place; the real place string is never overwritten
    entry["status"] = "ranked"
    entry["rank_score"] = score
    entry["rank_band"] = band_for(score, cfg["bands"])
    entry["rank_scores"] = {dim: tidy(dimension_score(scores, dim)) for dim in cfg["weights"]}
    entry["rank_date"] = today.isoformat()
    entry["location_verdict"] = loc
    entry["language_gate"] = lang
    entry["eligibility_gate"] = elig
    entry["deal_breaker"] = bool(deal_breaker)
    if lang == "PASS":
        entry.pop("language_note", None)
    else:
        entry["language_note"] = cap(result.get("language_note"))
    strengths = clip_list(result.get("strengths"))
    if strengths is not None:
        entry["strengths"] = strengths
    gaps = clip_list(result.get("gaps"))
    if gaps is not None:
        entry["gaps"] = gaps
    guard = normal_guard(result.get("guard"))
    if guard:
        entry["guard"] = guard
    else:
        entry.pop("guard", None)  # absence means not run; a stale verdict must not label this fetch

    age = posted_age_days(entry, today)
    urgent = deadline is not None and today <= deadline <= today + timedelta(days=URGENT_DAYS)
    row = brief(
        key, entry,
        score=score,
        band=entry["rank_band"],
        location_verdict=loc,
        language_gate=lang,
        language_note=entry.get("language_note"),
        eligibility_gate=elig,
        deal_breaker=entry["deal_breaker"],
        location=entry.get("location"),
        deadline=entry.get("deadline"),
        posted_at=entry.get("posted_at"),
        posted_age_days=age,
        stale=is_stale(age),
        urgent=urgent,
        strengths=entry.get("strengths", []),
        gaps=entry.get("gaps", []),
        guard=entry.get("guard"),
    )
    return "ranked", row


def cmd_apply(args) -> dict:
    doc = load_state(args.state)
    seen = doc["seen"]
    cfg = scoring_config(read_profile(args.project))
    results = load_results(args.results)
    ranked, expired, unreachable, gave_up, errors, warnings = [], [], [], [], [], []
    for result in results:
        if not isinstance(result, dict):
            errors.append({"key": None, "error": "result is not an object"})
            continue
        raw_key = result.get("key")
        key = raw_key if isinstance(raw_key, str) else ""
        entry = seen.get(key) if key else None
        if not isinstance(entry, dict):
            errors.append({"key": raw_key, "error": "no such key in seen.json"})
            continue
        if entry.get("status") == "skipped":
            errors.append({"key": key, "error": "entry is skipped; not scored"})
            continue
        status = result.get("status", "scored")
        if status not in AGENT_STATUSES:
            errors.append({"key": key, "error": f"unknown status {status!r}; expected one of {', '.join(AGENT_STATUSES)}"})
            continue
        try:
            if status == "unreachable":
                outcome, row = _apply_unreachable(key, entry, result, args.today, args.now)
            elif status == "expired":
                retire(entry, "closed")
                outcome, row = "expired", brief(key, entry)
            else:
                outcome, row = _apply_scored(key, entry, result, args.today, args.now, cfg, warnings)
        except ValueError as exc:
            errors.append({"key": key, "error": str(exc)})
            continue
        {"ranked": ranked, "expired": expired, "unreachable": unreachable, "gave_up": gave_up}[outcome].append(row)

    if not args.dry_run:
        save_state(args.state, doc)
    ranked.sort(key=lambda r: (r["score"], r["urgent"]), reverse=True)
    vetoed, shortlist = [], []
    for row in ranked:
        reasons = veto_reasons(row)
        if reasons:
            row["vetoed_by"] = reasons
            vetoed.append(row)
        else:
            shortlist.append(row)
    return {
        "ranked": shortlist,
        "vetoed": vetoed,
        "expired": expired,
        "unreachable": unreachable,
        "gave_up": gave_up,
        "errors": errors,
        "warnings": warnings,
        "written": not args.dry_run,
        "_exit": 1 if errors else 0,
    }


def cmd_sweep(args) -> dict:
    doc = load_state(args.state)
    seen = doc["seen"]
    exclude = {item.strip() for item in (args.exclude or "").split(",") if item.strip()}
    expired, closing, unparseable, checked = [], [], [], 0
    for key, entry in seen.items():
        if not isinstance(entry, dict) or entry.get("status") not in SWEEPABLE or key in exclude:
            continue
        checked += 1
        raw = entry.get("deadline")
        if raw in (None, ""):
            continue
        parsed = parse_day(raw)
        if parsed is None:
            unparseable.append({"key": key, "portal": entry.get("portal"), "deadline": raw})
            continue
        row = brief(key, entry, deadline=parsed.isoformat())
        if parsed < args.today:
            expired.append(row)
        elif (parsed - args.today).days <= URGENT_DAYS:
            closing.append(row)
    written = False
    if args.write and expired:
        for row in expired:
            retire(seen[row["key"]], "deadline_passed")
        save_state(args.state, doc)
        written = True
    closing.sort(key=lambda r: r["deadline"])
    return {
        "swept": checked,
        "newly_expired": expired,
        "closing_soon": closing,
        "unparseable_deadlines": unparseable,
        "written": written,
    }


def cmd_add(args) -> dict:
    doc = load_state(args.state)
    seen = doc["seen"]
    added, updated, errors, relisted = [], [], [], []
    openings = jk.opening_employer_urls(args.project)
    for item in read_items(args.file):
        if not isinstance(item, dict):
            errors.append({"key": None, "error": "entry is not an object"})
            continue
        raw_key = item.get("key")
        if not isinstance(raw_key, str) or not raw_key.strip():
            errors.append({"key": None, "error": "key is required (the job_key.py output)"})
            continue
        key = raw_key.strip()
        company, title = clip(item.get("company"), 200), clip(item.get("title"), 200)
        if not company or not title:
            errors.append({"key": key, "error": "company and title are required"})
            continue
        dates = {f: optional_iso(item.get(f)) for f in ("posted_at", "deadline")}
        bad = [f for f, value in dates.items() if value is False]
        if bad:
            errors.append({"key": key, "error": f"{', '.join(bad)} must be YYYY-MM-DD, unknown or null"})
            continue
        values = {
            "url": clip(item.get("url"), 500) or None,
            "portal": clip(item.get("portal"), 80) or None,
            "opening_id": clip(item.get("opening_id"), 80) or None,
            "posted_at": dates["posted_at"] or None,
            "deadline": dates["deadline"] or None,
        }
        if values["opening_id"] and not jc.valid_opening_id(values["opening_id"]):
            errors.append({"key": key, "error": "opening_id must be JOB-YYYYMMDD-<slug>: no slash, no dot"})
            continue
        canon = jk.employer_url(item.get("employer_url"))
        if item.get("employer_url") and not canon:
            errors.append({"key": key, "error": "employer_url is not an employer posting (link_check.py: an ATS or "
                                                "employer site); leave it out for a portal link"})
            continue
        aliased = alias_keys(seen).get(key)
        if aliased and aliased in seen:
            relisted.append(absorb(args.project, seen, aliased, key, item, args.today))
            continue  # a listing already recorded as an alias: the owner entry stands for it
        if canon:
            mine = seen.get(key) if isinstance(seen.get(key), dict) else {}
            item = {**item, "first_seen": mine.get("first_seen") or args.today.isoformat()}
            probe = dict(seen)
            probe[key] = {**mine, "employer_url": canon, "first_seen": item["first_seen"],
                          "opening_id": mine.get("opening_id") or values["opening_id"]}
            owner = posting_groups(probe, openings)[canon][0]
            if owner != key:
                relisted.append(absorb(args.project, seen, owner, key, item, args.today))
                continue
            values["employer_url"] = canon
        if key in seen and isinstance(seen[key], dict):
            entry = seen[key]
            filled = []
            for field, value in values.items():
                if value and not entry.get(field):
                    entry[field] = value
                    filled.append(field)
            updated.append({"key": key, "filled": filled})
            continue
        status = "skipped" if item.get("status") == "skipped" else "new"
        entry = {
            "company": company,
            "title": title,
            "first_seen": args.today.isoformat(),
            "status": status,
        }
        entry.update({field: value for field, value in values.items() if value})
        if status == "skipped":
            entry["skip_reason"] = clip(item.get("skip_reason"), 200)
        seen[key] = entry
        added.append(key)
    written = bool(added or updated or relisted)
    if written:
        save_state(args.state, doc)
    return {"added": added, "updated": updated, "relisted": relisted, "errors": errors, "written": written,
            "_exit": 1 if errors else 0}


def cmd_audit(args) -> dict:
    seen = load_state(args.state)["seen"]
    bands = set(BAND_ORDER) | {"poor"}
    problems, pairs = [], {}
    for key, entry in seen.items():
        if not isinstance(entry, dict):
            problems.append({"key": key, "issue": "entry is not an object"})
            continue

        def flag(issue: str) -> None:
            problems.append({"key": key, "issue": issue})

        status = entry.get("status")
        if status not in STATUSES:
            flag(f"unknown status {status!r}")
        for field in ("company", "title"):
            if not str(entry.get(field) or "").strip():
                flag(f"missing {field}")
        for field in ("posted_at", "deadline", "first_seen"):
            value = entry.get(field)
            if value not in (None, "") and as_iso(value) is None:
                flag(f"{field} is not YYYY-MM-DD: {value!r}")
        if status == "ranked":
            if not isinstance(entry.get("rank_score"), (int, float)) or isinstance(entry.get("rank_score"), bool):
                flag("ranked without a numeric rank_score")
            if entry.get("rank_band") not in bands:
                flag(f"ranked with unknown rank_band {entry.get('rank_band')!r}")
        if status == "unreachable" and not isinstance(entry.get("fetch_attempts"), int):
            flag("unreachable without fetch_attempts")
        if entry.get("opening_id") and not jc.valid_opening_id(entry.get("opening_id")):
            flag("opening_id is not JOB-YYYYMMDD-<slug>: a path outside openings/ is refused")
        if entry.get("location") in VERDICTS:
            flag("a verdict is stored in location (apply moves it to location_verdict)")
        pair = (norm(entry.get("company")), norm(entry.get("title")))
        if pair[0]:
            pairs.setdefault(pair, []).append(key)
    duplicates = [
        {"company": seen[keys[0]].get("company"), "title": seen[keys[0]].get("title"), "keys": keys}
        for keys in pairs.values() if len(keys) > 1
    ]
    # One employer posting under several entries: the next `add` of a re-listing merges it into the first.
    same_posting = [
        {"employer_url": canon, "keys": keys}
        for canon, keys in posting_groups(seen, jk.opening_employer_urls(args.project)).items() if len(keys) > 1
    ]
    return {
        "entries": len(seen),
        "ok": not problems,
        "problems": problems,
        "possible_duplicates": duplicates,
        "same_employer_posting": same_posting,
        "_exit": 1 if (args.strict and problems) else 0,
    }


def cmd_stats(args) -> dict:
    seen = load_state(args.state)["seen"]
    by_status = {status: 0 for status in STATUSES}
    by_band: dict = {}
    stale = closing = unparseable = 0
    for entry in seen.values():
        if not isinstance(entry, dict):
            continue
        status = entry.get("status")
        by_status[status] = by_status.get(status, 0) + 1
        if status == "ranked":
            band = entry.get("rank_band") or "unknown"
            by_band[band] = by_band.get(band, 0) + 1
        if status in ("new", "ranked", "unreachable") and is_stale(posted_age_days(entry, args.today)):
            stale += 1
        raw = entry.get("deadline")
        if raw not in (None, ""):
            parsed = parse_day(raw)
            if parsed is None:
                unparseable += 1
            elif status in SWEEPABLE and 0 <= (parsed - args.today).days <= URGENT_DAYS:
                closing += 1
    return {
        "total": len(seen),
        "by_status": by_status,
        "ranked_by_band": by_band,
        "stale_over_30_days": stale,
        "closing_within_7_days": closing,
        "unparseable_deadlines": unparseable,
    }


# --- CLI --------------------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", help="project folder (default: $JOBS_PROJECT, else the current folder)")
    common.add_argument("--today", type=_day_arg, default=None, help="date to use (default: today)")
    common.add_argument("--now", type=parse_now, default=None, help="UTC date-time for retry floors (default: now)")

    ap = argparse.ArgumentParser(description="Dedupe and rank state for a job search (searches/seen.json).")
    sub = ap.add_subparsers(dest="command", required=True)

    cand = sub.add_parser("candidates", parents=[common], help="entries to fetch and score this run")
    cand.add_argument("--all", action="store_true", help="every status except skipped (re-scores ranked too)")
    cand.add_argument("--focus", help="substring over title, company and stored notes")
    cand.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="0 for no cap (default 10)")
    cand.add_argument("--saved", action="store_true", help="only entries whose opening.md is saved (opening_id set)")

    apply = sub.add_parser("apply", parents=[common], help="write scoring results back, print the ranking")
    apply.add_argument("--results", required=True, help="JSON array of scoring objects")
    apply.add_argument("--dry-run", action="store_true", help="print the outcome without writing")

    sweep = sub.add_parser("sweep", parents=[common], help="deadline pass over stored entries, no fetch")
    sweep.add_argument("--write", action="store_true", help="persist the expiries")
    sweep.add_argument("--exclude", help="comma-separated keys to leave alone this run")

    add = sub.add_parser("add", parents=[common], help="register entries from a search")
    add.add_argument("--file", required=True, help="JSON array of entries, or - for stdin")

    audit = sub.add_parser("audit", parents=[common], help="check the state file")
    audit.add_argument("--strict", action="store_true", help="exit 1 when problems are found")

    sub.add_parser("stats", parents=[common], help="counts by status and band")
    return ap


WRITERS = ("apply", "sweep", "add")

HANDLERS = {
    "candidates": cmd_candidates,
    "apply": cmd_apply,
    "sweep": cmd_sweep,
    "add": cmd_add,
    "audit": cmd_audit,
    "stats": cmd_stats,
}


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


def main(argv=None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        project = jc.project_dir(args.project)
        args.project = project
        args.today = args.today or date.today()
        args.now = args.now or datetime.now(timezone.utc)
        args.state = state_path(project)
        args.tracker = tracker_path(project)
        if args.command in WRITERS:
            # Read-modify-write under one lock: two processes adding at once keep both entries.
            with jc.locked(args.state):
                payload = HANDLERS[args.command](args)
        else:
            payload = HANDLERS[args.command](args)
    except StateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    code = payload.pop("_exit", 0)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
