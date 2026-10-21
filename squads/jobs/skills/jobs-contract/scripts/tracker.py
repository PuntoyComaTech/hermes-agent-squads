#!/usr/bin/env python3
"""Application tracker of one job-search project: `<P>/tracker.csv`, one row per tracked application.

  tracker.py init       create tracker.csv, or append missing canonical columns to its header
  tracker.py add        --id ID --company C --role R --status S [--date D] [--channel X] [--fit-score N]
                        [--apply-url U] [--deadline D] [--applied-at D] [--cv-file F] [--cover-letter-file F]
                        [--source S] [--note TEXT] [--if-missing]
                        (--if-missing: an id already tracked is left as it is and reported, not refused; the applier
                        uses it so a repeated record never makes a second row)
  tracker.py update     --id ID [--status S] [--note TEXT] [--last-contact D] [--follow-ups-inc [--on D]]
                        [--applied-at D] [--deadline D] [--fit-score N] [--channel X] [--apply-url U]
                        [--cv-file F] [--cover-letter-file F] [--source S] [--stale-reported D]
                        (--status: a squad status; --note: one dated line appended to notes; --last-contact:
                        the date of the last exchange; --follow-ups-inc: log one follow-up sent, cap 2;
                        --stale-reported: the day the stale report named this row, so it is not named again;
                        --create: a row missing for ID is built from openings/<ID>/opening.md; needs --status)
  tracker.py list       [--status S ...] [--json]  every row, with derived fields (JSON; --json is accepted so a
                        caller can name the format)
  tracker.py followups  [--days N]                open applications quiet for N days, fewer than 2 follow-ups
  tracker.py stale      [--days N]                submitted applications quiet for N days (read-only sweep)
  tracker.py stats      counts, funnel, deadline flags, calibration readiness

Every command takes --project P (default $JOBS_PROJECT, else the current folder, which must hold profile.md)
and --today YYYY-MM-DD (replays and tests; default the local date). Thresholds come from profile.md:
follow_up_days (default 10) and stale_days (default 60).

Output is JSON on stdout. A refused write or unusable data exits 1 with the reason on stderr; usage errors exit 2.
Every write holds a lock on tracker.csv, so two bots writing at once cannot drop each other's rows.
apply_url must be an http or https link; a mailto: address only with --channel email.

Writes touch only the cells they change: every other row keeps its values, in its place. Cells that start with
= + - @ (or a tab or carriage return) are stored with a leading apostrophe. Statuses follow the vocabulary in the
tracking-outcomes skill; the legacy spellings ("no response", "offer declined") read and write as the underscore
forms. Deadline flags are data fields (deadline_flag: soon | passed | invalid), never emoji.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs_common as jc  # noqa: E402

FILE_NAME = "tracker.csv"
# stale_reported is not canonical: followup_gate adds it to a tracker's header the first time it marks a row.
COLUMNS = ["date", "id", "company", "role", "status", "channel", "fit_score", "apply_url", "deadline",
           "applied_at", "last_contact", "follow_ups", "notes", "cv_file", "cover_letter_file", "source"]
URL_START = re.compile(r"^https?://[^\s/?#]+", re.IGNORECASE)
REQUIRED = ("date", "id", "company", "role", "status")
ID_RE = re.compile(r"JOB-\d{8}-[a-z0-9]+(?:-[a-z0-9]+)*")
ID_MAX = 50
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")

# jobs_common.STATUSES, bucketed: not sent / submitted and open / offer / final.
NOT_SENT = frozenset({"found", "analyzed", "in_preparation", "in_review", "not_approved", "ready", "delivered",
                      "applying", "manual_application"})
CHASEABLE = frozenset({"applied", "followed_up", "screening", "interview", "waiting"})
OFFER_OPEN = frozenset({"offer"})
RESOLVED = frozenset({"hired", "rejected", "no_response", "withdrawn", "closed"})
FINAL = RESOLVED | {"skipped", "discarded"}
KNOWN = NOT_SENT | CHASEABLE | OFFER_OPEN | FINAL
assert KNOWN == frozenset(jc.STATUSES), sorted(KNOWN ^ frozenset(jc.STATUSES))  # one vocabulary: jobs_common
SUBMITTED = CHASEABLE | OFFER_OPEN | RESOLVED
INTERVIEW_OR_LATER = frozenset({"interview", "offer", "hired"})
OFFER_OR_LATER = frozenset({"offer", "hired"})
# Spellings older trackers may hold. They are read as the squad status and never written. The vocabulary has no
# offer_declined status: a declined offer is written as withdrawn with a note (the offer stage is then not counted).
LEGACY_READ = {"drafted": "ready", "offer_declined": "withdrawn"}
BANDS = ("strong", "good", "moderate", "weak")
DEFAULT_BANDS = {"strong": 75, "good": 60, "moderate": 45, "weak": 30}
DEFAULT_FOLLOW_UP_DAYS = 10
DEFAULT_STALE_DAYS = 60
FOLLOW_UP_CAP = 2
DEADLINE_SOON_DAYS = 7
CALIBRATION_MIN = 5
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


class DataError(Exception):
    """A refused write or unusable data: the reason goes to stderr and the exit code is 1."""


# --- values ------------------------------------------------------------------------------------------------------

def norm_status(value) -> str:
    """Lowercase snake_case; the legacy space and hyphen spellings map onto the underscore forms."""
    return re.sub(r"[\s-]+", "_", str(value or "").strip().lower())


def read_status(value) -> str:
    """The status as the squad reads it: legacy spellings map onto the squad status they stand for."""
    status = norm_status(value)
    return LEGACY_READ.get(status, status)


def clean(value) -> str:
    """One line of text: inputs never carry line breaks into a row."""
    return " ".join(str(value or "").split())


def safe_cell(value) -> str:
    """CSV-injection guard: a cell that a spreadsheet would read as a formula gets a leading apostrophe."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in FORMULA_START else text


def parse_date(value):
    text = str(value or "").strip()
    if not DATE_RE.fullmatch(text):
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def date_arg(text) -> date:
    parsed = parse_date(text)
    if parsed is None:
        raise DataError(f"'{clean(text)}' is not a date (use YYYY-MM-DD)")
    return parsed


def deadline_arg(text) -> str:
    if text is None or str(text).strip() == "":
        return ""
    return date_arg(text).isoformat()


def score_arg(text) -> str:
    if text is None or str(text).strip() == "":
        return ""
    value = str(text).strip()
    if not value.isdigit() or not 0 <= int(value) <= 100:
        raise DataError("fit score must be a whole number from 0 to 100")
    return str(int(value))


def checked_status(value) -> str:
    status = norm_status(value)
    if status in LEGACY_READ:
        raise DataError(f"'{clean(value)}' is a legacy spelling: write '{LEGACY_READ[status]}' instead")
    if status not in KNOWN:
        raise DataError(f"unknown status '{clean(value)}' (see the tracker vocabulary in the tracking-outcomes skill)")
    return status


def checked_id(value) -> str:
    text = str(value or "").strip()
    if len(text) > ID_MAX or not ID_RE.fullmatch(text):
        raise DataError("id must look like JOB-YYYYMMDD-company-role: lowercase, at most 50 characters")
    return text


MAILTO = re.compile(r"^mailto:[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?:\?[^\s<>\"]*)?$", re.IGNORECASE)


def checked_url(value, channel: str = "") -> str:
    """An apply link as stored. Empty clears it. An http(s) URL with a host; a mailto: address on the email channel."""
    text = clean(value)
    if not text:
        return ""
    if channel == "email" and MAILTO.match(text):
        return text
    if not URL_START.match(text):
        hint = " (or a mailto: address on the email channel)" if channel == "email" else ""
        raise DataError(f"apply_url '{text[:80]}' must be an http or https link{hint}")
    return text


# --- the file ----------------------------------------------------------------------------------------------------

class Tracker:
    """The rows as read. Each row stays a list of cells, so writing it back changes nothing it did not touch."""

    def __init__(self, path: Path):
        self.path = path
        self.header: list[str] = list(COLUMNS)
        self.rows: list[list[str]] = []
        self.exists = path.is_file()
        self.header_read = False  # True once a non-empty header was read from disk

    def load(self) -> "Tracker":
        if not self.exists:
            return self
        with self.path.open(encoding="utf-8-sig", newline="") as handle:
            table = list(csv.reader(handle))
        if not table or not any(cell.strip() for cell in table[0]):
            if any(any(cell.strip() for cell in row) for row in table[1:]):
                raise DataError(f"{FILE_NAME} has data rows but no header line: fix it by hand")
            return self
        self.header_read = True
        self.header = [cell.strip() for cell in table[0]]
        self.rows = table[1:]
        missing = [name for name in REQUIRED if name not in self.header]
        if missing:
            raise DataError(f"{FILE_NAME} header lacks {', '.join(missing)}: it is not a tracker this version reads")
        return self

    def record(self, index: int) -> dict:
        row = self.rows[index]
        padded = row + [""] * (len(self.header) - len(row))
        return dict(zip(self.header, padded))

    def find(self, rid: str):
        for index in range(len(self.rows)):
            if self.record(index).get("id", "") == rid:
                return index
        return None

    def set(self, index: int, column: str, value) -> None:
        if column not in self.header:
            self.header.append(column)
        row = self.rows[index]
        while len(row) < len(self.header):
            row.append("")
        row[self.header.index(column)] = safe_cell(value)

    def ensure_columns(self) -> None:
        self.header.extend(name for name in COLUMNS if name not in self.header)

    def new_row(self, values: dict) -> list:
        self.ensure_columns()
        return [safe_cell(values.get(name, "")) for name in self.header]

    def save(self) -> None:
        """Rows are written as they were read. Only a header that gained columns pads rows to the new width."""
        self.ensure_columns()
        width = len(self.header)
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(self.header)
        for row in self.rows:
            writer.writerow(row + [""] * (width - len(row)) if len(row) < width else row)
        jc.atomic_write(self.path, buffer.getvalue())


# --- derived fields ----------------------------------------------------------------------------------------------

# Only a stamped note part counts as activity: "2026-10-20 text" or "followed up 2026-10-20". A date that appears
# inside the text ("call booked 2026-10-28") is an event, not contact, and is ignored.
NOTE_STAMP = re.compile(r"(?:followed up )?(\d{4}-\d{2}-\d{2})(?!\d)")


def quiet_since(rec: dict, today: date):
    """Latest activity up to today: applied_at (the row date while blank), last_contact, or a dated note entry.
    A date in the future (an interview booked for next week) is not activity and is ignored."""
    found = [parse_date(rec.get("applied_at")) or parse_date(rec.get("date")), parse_date(rec.get("last_contact"))]
    for part in str(rec.get("notes") or "").split(" | "):
        stamp = NOTE_STAMP.match(part.strip())
        if stamp:
            found.append(parse_date(stamp.group(1)))
    dates = [d for d in found if d and d <= today]
    return max(dates) if dates else None


def quiet_days(rec: dict, today: date):
    since = quiet_since(rec, today)
    return max(0, (today - since).days) if since else None


LEGACY_FOLLOW_UP = re.compile(r"followed up \d{4}-\d{2}-\d{2}")


def follow_up_count(rec: dict):
    """The follow_ups cell; when blank, the `followed up YYYY-MM-DD` markers older rows carry in notes."""
    text = str(rec.get("follow_ups") or "").strip()
    if text:
        return int(text) if text.isdigit() else None
    return len(LEGACY_FOLLOW_UP.findall(str(rec.get("notes") or "")))


def deadline_info(rec: dict, today: date):
    """(flag, days_to_deadline): flag is soon (7 days or fewer), passed, invalid, or None."""
    raw = str(rec.get("deadline") or "").strip()
    if not raw:
        return None, None
    due = parse_date(raw)
    if due is None:
        return "invalid", None
    days = (due - today).days
    if days < 0:
        return "passed", days
    if days <= DEADLINE_SOON_DAYS:
        return "soon", days
    return None, days


def bucket(status: str) -> str:
    if status in NOT_SENT:
        return "not_sent"
    if status == "interview":
        return "interview"
    if status in CHASEABLE:
        return "active"
    if status == "offer":
        return "offer"
    if status == "hired":
        return "hired"
    if status in FINAL:
        return "closed"
    return "unrecognised"


def describe(rec: dict, today: date) -> dict:
    status = read_status(rec.get("status"))
    flag, days = deadline_info(rec, today) if status not in FINAL else (None, None)
    out = dict(rec)
    out["status"] = status
    out["bucket"] = bucket(status)
    out["quiet_days"] = quiet_days(rec, today) if status in CHASEABLE else None
    out["follow_ups_sent"] = follow_up_count(rec)
    out["deadline_flag"] = flag
    out["deadline_soon"] = flag == "soon"
    out["deadline_passed"] = flag == "passed"
    out["days_to_deadline"] = days
    return out


def settings(project: Path) -> dict:
    meta = jc.read_front_matter(project / "profile.md")

    def whole(name: str, default: int) -> int:
        value = meta.get(name, default)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else default

    bands = dict(DEFAULT_BANDS)
    scoring = meta.get("scoring") if isinstance(meta.get("scoring"), dict) else {}
    given = scoring.get("bands") if isinstance(scoring.get("bands"), dict) else {}
    for name in BANDS:
        value = given.get(name)
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 100:
            bands[name] = value
    return {"follow_up_days": whole("follow_up_days", DEFAULT_FOLLOW_UP_DAYS),
            "stale_days": whole("stale_days", DEFAULT_STALE_DAYS), "bands": bands}


def fit_band(score, bands: dict) -> str:
    try:
        value = int(str(score).strip())
    except (TypeError, ValueError):
        return "unscored"
    for name in BANDS:
        if value >= bands[name]:
            return name
    return "poor"


def due_items(tracker: Tracker, today: date, days: int, cap: bool):
    """Chaseable applications quiet for `days` or more. With cap, rows at the follow-up cap go to at_cap."""
    items, at_cap, skipped = [], [], []
    for index in range(len(tracker.rows)):
        rec = tracker.record(index)
        status = read_status(rec.get("status"))
        if status not in CHASEABLE:
            continue
        rid = rec.get("id", "")
        quiet = quiet_days(rec, today)
        if quiet is None:
            skipped.append({"id": rid, "reason": "no parseable applied_at, date or last_contact"})
            continue
        sent = follow_up_count(rec)
        if sent is None:
            skipped.append({"id": rid, "reason": "follow_ups is not a whole number"})
            continue
        if quiet < days:
            continue
        if cap and sent >= FOLLOW_UP_CAP:
            at_cap.append(rid)
            continue
        flag, to_deadline = deadline_info(rec, today)
        since = quiet_since(rec, today)
        reported = parse_date(rec.get("stale_reported"))
        items.append({
            "id": rid, "company": rec.get("company", ""), "role": rec.get("role", ""), "status": status,
            "channel": rec.get("channel", ""), "quiet_days": quiet, "follow_ups_sent": sent,
            "last_activity": since.isoformat() if since else None, "deadline_flag": flag,
            "days_to_deadline": to_deadline, "draft_path": f"reports/followups/{rid}-{sent + 1}.md",
            "apply_url": rec.get("apply_url", ""), "cv_file": rec.get("cv_file", ""),
            "cover_letter_file": rec.get("cover_letter_file", ""),
            "stale_reported": reported.isoformat() if reported else None,
        })
    items.sort(key=lambda item: (-item["quiet_days"], item["company"].casefold(), item["id"]))
    return items, at_cap, skipped


# --- commands ----------------------------------------------------------------------------------------------------

def cmd_init(args, project: Path, today: date) -> dict:
    tracker = Tracker(project / FILE_NAME).load()
    if not tracker.exists or not tracker.header_read:
        tracker.save()
        return {"path": str(tracker.path), "created": True, "columns": tracker.header}
    added = [name for name in COLUMNS if name not in tracker.header]
    if added:
        tracker.save()
    return {"path": str(tracker.path), "created": False, "added_columns": added}


def cmd_add(args, project: Path, today: date) -> dict:
    path = project / FILE_NAME
    with jc.locked(path):  # one read-modify-write: two bots adding at once keep both rows
        tracker = Tracker(path).load()
        rid = checked_id(args.id)
        existing = tracker.find(rid)
        if existing is not None:
            if args.if_missing:
                held = read_status(tracker.record(existing).get("status"))
                return {"added": None, "already_tracked": rid, "status": held, "path": str(tracker.path)}
            raise DataError(f"{rid} is already tracked: use update")
        status = checked_status(args.status)
        company, role = clean(args.company), clean(args.role)
        if not company or not role:
            raise DataError("company and role are required")
        row_date = date_arg(args.date) if args.date else today
        if args.applied_at:
            applied = date_arg(args.applied_at).isoformat()
        else:
            applied = row_date.isoformat() if status in SUBMITTED else ""
        values = {
            "date": row_date.isoformat(), "id": rid, "company": company, "role": role, "status": status,
            "channel": clean(args.channel), "fit_score": score_arg(args.fit_score),
            "apply_url": checked_url(args.apply_url, clean(args.channel)),
            "deadline": deadline_arg(args.deadline), "applied_at": applied, "last_contact": "", "follow_ups": "0",
            "notes": clean(args.note), "cv_file": clean(args.cv_file), "cover_letter_file": clean(args.cover_letter_file),
            "source": clean(args.source),
        }
        tracker.rows.append(tracker.new_row(values))
        tracker.save()
    return {"added": rid, "status": status, "path": str(tracker.path)}


def create_row(tracker: Tracker, rid: str, args, project: Path, today: date) -> int:
    """Append the row of an opening the tracker does not hold yet, built from its opening.md. Returns its index."""
    if args.status is None:
        raise DataError(f"{rid} is not tracked: --create needs --status (the stage the user reports)")
    opening = project / "openings" / rid / "opening.md"
    if not opening.is_file():
        raise DataError(f"{rid} is not tracked and openings/{rid}/opening.md is missing: nothing to build the row from")
    meta = jc.read_front_matter(opening)
    company, role = clean(meta.get("company")), clean(meta.get("role"))
    if not company or not role:
        raise DataError(f"openings/{rid}/opening.md needs company and role in its front matter")
    url = clean(meta.get("apply_url"))
    channel = clean(args.channel) if args.channel is not None else ("email" if url.lower().startswith("mailto:") else "")
    status = checked_status(args.status)
    values = {"date": today.isoformat(), "id": rid, "company": company, "role": role, "status": status,
              "channel": channel, "apply_url": checked_url(url, channel),
              "applied_at": today.isoformat() if status in SUBMITTED else "", "follow_ups": "0"}
    tracker.rows.append(tracker.new_row(values))
    return len(tracker.rows) - 1


def cmd_update(args, project: Path, today: date) -> dict:
    path = project / FILE_NAME
    with jc.locked(path):
        return _update(args, path, today)


def _update(args, path: Path, today: date) -> dict:
    tracker = Tracker(path).load()
    rid = checked_id(args.id)
    index = tracker.find(rid)
    created = index is None
    if created:
        if not args.create:
            raise DataError(f"{rid} is not tracked: use add, or update --create (the row is then built from opening.md)")
        index = create_row(tracker, rid, args, path.parent, today)
    rec = tracker.record(index)
    old = read_status(rec.get("status"))
    changes: dict = {}
    notes: list[str] = []
    status_now = old
    if args.status is not None:
        new = checked_status(args.status)
        if old in SUBMITTED and new in NOT_SENT:
            raise DataError(f"{rid} was submitted: it cannot go back to {new}")
        changes["status"] = new
        status_now = new
    if args.applied_at is not None:
        changes["applied_at"] = date_arg(args.applied_at).isoformat()
    elif old in NOT_SENT and status_now in SUBMITTED:
        # The date column holds the draft date until submission: the submission date replaces it.
        changes["applied_at"] = today.isoformat()
    if old in NOT_SENT and status_now in SUBMITTED:
        changes["date"] = changes["applied_at"]
    if args.last_contact is not None:
        changes["last_contact"] = date_arg(args.last_contact).isoformat()
    if args.deadline is not None:
        changes["deadline"] = deadline_arg(args.deadline)
    if args.fit_score is not None:
        changes["fit_score"] = score_arg(args.fit_score)
    if args.stale_reported is not None:
        changes["stale_reported"] = date_arg(args.stale_reported).isoformat()
    for name in ("channel", "cv_file", "cover_letter_file", "source"):
        value = getattr(args, name)
        if value is not None:
            changes[name] = clean(value)
    if args.apply_url is not None:
        changes["apply_url"] = checked_url(args.apply_url,
                                           clean(args.channel) if args.channel is not None else str(rec.get("channel") or ""))
    if args.follow_ups_inc:
        if status_now not in CHASEABLE:
            raise DataError(f"follow-ups are logged only for {', '.join(sorted(CHASEABLE))}; {rid} is {status_now}")
        sent = follow_up_count(rec)
        if sent is None:
            raise DataError(f"{rid} has follow_ups that is not a whole number: fix the row by hand")
        if sent >= FOLLOW_UP_CAP:
            raise DataError(f"{rid} already has {sent} follow-ups (the cap is {FOLLOW_UP_CAP}): record the resolution")
        when = date_arg(args.on) if args.on else today
        changes["follow_ups"] = str(sent + 1)
        changes["last_contact"] = when.isoformat()
        if status_now == "applied":
            changes["status"] = "followed_up"
        notes.append(f"followed up {when.isoformat()}")
    if args.note:
        notes.append(f"{today.isoformat()} {clean(args.note)}")
    if notes:
        existing = str(rec.get("notes") or "")
        changes["notes"] = " | ".join(part for part in [existing, *notes] if part)
    if not changes:
        raise DataError("nothing to update: pass at least one field")
    for column, value in changes.items():
        tracker.set(index, column, value)
    tracker.save()
    return {"updated": rid, "created": created, "changed": sorted(changes), "row": describe(tracker.record(index), today)}


def cmd_list(args, project: Path, today: date) -> dict:
    tracker = Tracker(project / FILE_NAME).load()
    wanted = {read_status(s) for s in args.status} if args.status else None
    rows = []
    for index in range(len(tracker.rows)):
        rec = describe(tracker.record(index), today)
        if wanted is None or rec["status"] in wanted:
            rows.append(rec)
    return {"count": len(rows), "rows": rows}


def cmd_followups(args, project: Path, today: date) -> dict:
    cfg = settings(project)
    days = args.days if args.days is not None else cfg["follow_up_days"]
    items, at_cap, skipped = due_items(Tracker(project / FILE_NAME).load(), today, days, cap=True)
    return {"today": today.isoformat(), "threshold_days": days, "follow_up_cap": FOLLOW_UP_CAP,
            "items": items, "at_cap": at_cap, "skipped": skipped}


def cmd_stale(args, project: Path, today: date) -> dict:
    cfg = settings(project)
    days = args.days if args.days is not None else cfg["stale_days"]
    items, _, skipped = due_items(Tracker(project / FILE_NAME).load(), today, days, cap=False)
    return {"today": today.isoformat(), "threshold_days": days, "items": items, "skipped": skipped}


def tally(rows: list, key) -> dict:
    out: dict = {}
    for row in rows:
        slot = out.setdefault(key(row), {"resolved": 0, "interview_or_later": 0, "offer_or_later": 0,
                                         "rejected_or_no_response": 0})
        slot["resolved"] += 1
        slot["interview_or_later"] += row["status"] in INTERVIEW_OR_LATER
        slot["offer_or_later"] += row["status"] in OFFER_OR_LATER
        slot["rejected_or_no_response"] += row["status"] in ("rejected", "no_response")
    return dict(sorted(out.items()))


def cmd_stats(args, project: Path, today: date) -> dict:
    tracker = Tracker(project / FILE_NAME).load()
    cfg = settings(project)
    rows = [describe(tracker.record(i), today) for i in range(len(tracker.rows))]
    statuses = Counter(row["status"] for row in rows)
    open_rows = [row for row in rows if row["status"] in NOT_SENT | CHASEABLE | OFFER_OPEN]
    resolved = [row for row in rows if row["status"] in RESOLVED]
    flags = Counter(row["deadline_flag"] for row in open_rows if row["deadline_flag"])
    quiet, _, _ = due_items(tracker, today, cfg["follow_up_days"], cap=True)
    stale, _, _ = due_items(tracker, today, cfg["stale_days"], cap=False)
    return {
        "today": today.isoformat(),
        "total": len(rows),
        "by_status": dict(sorted(statuses.items())),
        "by_bucket": dict(sorted(Counter(row["bucket"] for row in rows).items())),
        "unrecognised_status": sorted({row["status"] for row in rows if row["bucket"] == "unrecognised"}),
        "not_sent": sum(row["status"] in NOT_SENT for row in rows),
        "active": sum(row["status"] in CHASEABLE for row in rows),
        "offer_open": sum(row["status"] in OFFER_OPEN for row in rows),
        "funnel": {
            "applied": sum(row["status"] in SUBMITTED for row in rows),
            "interview_or_later": sum(row["status"] in INTERVIEW_OR_LATER for row in rows),
            "offer_or_later": sum(row["status"] in OFFER_OR_LATER for row in rows),
            "hired": sum(row["status"] == "hired" for row in rows),
        },
        "quiet_candidates": len(quiet),
        "stale_candidates": len(stale),
        "deadlines": {"soon": flags.get("soon", 0), "passed": flags.get("passed", 0),
                      "invalid": flags.get("invalid", 0)},
        "calibration": {
            "resolved": len(resolved),
            "minimum": CALIBRATION_MIN,
            "ready": len(resolved) >= CALIBRATION_MIN,
            "by_fit_band": tally(resolved, lambda row: fit_band(row.get("fit_score"), cfg["bands"])),
            "by_channel": tally(resolved, lambda row: row.get("channel") or "unknown"),
        },
        "thresholds": {"follow_up_days": cfg["follow_up_days"], "stale_days": cfg["stale_days"],
                       "follow_up_cap": FOLLOW_UP_CAP, "deadline_soon_days": DEADLINE_SOON_DAYS},
    }


COMMANDS = {"init": cmd_init, "add": cmd_add, "update": cmd_update, "list": cmd_list,
            "followups": cmd_followups, "stale": cmd_stale, "stats": cmd_stats}


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--project", help="project folder holding profile.md (default: $JOBS_PROJECT, else the "
                                          "current folder)")
    common.add_argument("--today", help="YYYY-MM-DD in place of the local date (replays and tests)")
    parser = argparse.ArgumentParser(prog="tracker.py", description=__doc__.split("\n\n")[0],
                                     epilog=__doc__.split("\n\n", 1)[1], formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", metavar="COMMAND", required=True)
    sub.add_parser("init", parents=[common], help="create tracker.csv or add missing columns")
    add = sub.add_parser("add", parents=[common], help="track a new application")
    add.add_argument("--id", required=True)
    add.add_argument("--company", required=True)
    add.add_argument("--role", required=True)
    add.add_argument("--status", required=True)
    for name in ("date", "channel", "fit-score", "apply-url", "deadline", "applied-at", "cv-file",
                 "cover-letter-file", "source", "note"):
        add.add_argument(f"--{name}")
    add.add_argument("--if-missing", action="store_true",
                     help="an id already tracked is reported and left as it is (the applier's idempotent record)")
    upd = sub.add_parser("update", parents=[common], help="change one tracked application")
    upd.add_argument("--id", required=True, help="the opening id, JOB-YYYYMMDD-company-role")
    upd.add_argument("--status", help="a squad status, e.g. applied, interview, offer, rejected, no_response")
    upd.add_argument("--note", help="one line appended to notes, dated today (no commas needed; kept as text)")
    upd.add_argument("--last-contact", help="YYYY-MM-DD of the last exchange with the employer")
    upd.add_argument("--follow-ups-inc", "--follow-up-sent", dest="follow_ups_inc", action="store_true",
                     help="log one follow-up sent; increments follow_ups (cap: 2)")
    upd.add_argument("--on", help="date of the follow-up, with --follow-ups-inc (default today)")
    upd.add_argument("--create", action="store_true",
                     help="a row missing for --id is built from openings/<ID>/opening.md (needs --status)")
    for name, text in (("applied-at", "YYYY-MM-DD the application was submitted"),
                       ("stale-reported", "YYYY-MM-DD the stale report named this row (set by followup_gate)"),
                       ("deadline", "YYYY-MM-DD application deadline, or empty to clear"),
                       ("fit-score", "whole number 0-100"), ("channel", "portal, email, referral, ..."),
                       ("apply-url", "posting or application URL"), ("cv-file", "path of the CV sent"),
                       ("cover-letter-file", "path of the cover letter sent"), ("source", "where the opening came from")):
        upd.add_argument(f"--{name}", help=text)
    lst = sub.add_parser("list", parents=[common], help="list rows with derived fields")
    lst.add_argument("--status", action="append", help="filter by status (repeatable)")
    lst.add_argument("--json", action="store_true", help="JSON output (the only output format; accepted for callers)")
    for name, text in (("followups", "open applications due for a follow-up"),
                       ("stale", "submitted applications quiet for the stale threshold")):
        part = sub.add_parser(name, parents=[common], help=text)
        part.add_argument("--days", type=int, help="threshold in days (default from profile.md)")
    sub.add_parser("stats", parents=[common], help="counts, funnel, deadlines, calibration readiness")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        today = date_arg(args.today) if args.today else date.fromisoformat(jc.today())
        project = jc.project_dir(args.project or os.environ.get("JOBS_PROJECT"))
        result = COMMANDS[args.command](args, project, today)
    except DataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
