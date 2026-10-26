#!/usr/bin/env python3
"""Validate openings/<ID>/application/submission.json against the jobs contract, and gate the submit itself.

Usage:
  check_submission.py FILE [--json] [--apply-url URL]                      validate the record (any result)
  check_submission.py FILE --gate [--before-submit] [--json] [--apply-url URL] [--method METHOD]
                                                 decide before the first click; --before-submit also requires the
                                                 pre-submit screenshot approval (run it after before.png exists)
  check_submission.py FILE --post-submit [--json]                          the record check after the click: only the
                                                 rules that can move after the click are flags, and only with a fresh
                                                 gate stamp for this opening (record_submission.py uses it, so a real
                                                 submit is never lost)
  check_submission.py --kit-hash APP_DIR         print the kit hash of application/ (consent.json kit_sha256)

FILE is the submission.json of one opening. Relative paths resolve against the folder that holds FILE (application/);
a screenshot or approval image must resolve inside that folder. --method names the form class the gate is deciding for
when submission.json does not exist yet. --today YYYY-MM-DD fixes the day the daily caps count (replays and tests).
Nothing is written except under --gate: an open gate writes application/gate.json, the stamp {opening_id, method, mode,
opened_at} that says the gate opened for this opening in every mode, and under auto_apply: auto also takes a dated
reservation under the project's lock (scripts/apply_state.py), so two appliers at nine of ten cannot both take the
tenth place.

Rules (contract: jobs-contract references/opening-files.md, submission.json):
- --gate: a kit text (letter, answers, recruiter message, rendered CV or letter text) that names a profile.md
  `confidential_terms` entry closes the gate.
- id is a JOB-YYYYMMDD-<slug> of at most 50 characters and, when FILE sits in openings/<ID>/application/, equals the
  folder name.
- result is SUBMITTED, NEEDS_DATA or NOT_POSSIBLE; method is one of the seven form classes. An employer ATS name from
  official_hosts.json (ashby, greenhouse, lever, workable, ...) is accepted for no_login_form: those boards apply without
  an account. The gate then also requires the apply_url to sit on that same ATS, so a mislabelled form never passes.
- filled_fields lists {field, source} only: every filled field has a source (contact.yaml, application-data.yaml,
  answers.md, cv or consult:<card id>). A value key is refused: the file never carries field values.
- SUBMITTED: method no_login_form (or linkedin_easy_apply under auto_apply: auto); at least one filled field; no
  pending_questions; a screenshot named like confirmation.* that exists; every screenshot listed exists; the authority
  rules below; the apply_url is not `unverified` (link_check.py).
- NEEDS_DATA: at least one pending question with its text (options optional).
- NOT_POSSIBLE: a reason, and application/kit.md exists beside the file (manual_kit names it when given). A reason
  that names a code the form mailed to the applicant also needs code_request {card, outcome}: jobs-inbox was asked
  (code_wait.py) and answered no_code, unavailable or timeout. An e-mailed code is never a CAPTCHA.
- No e-mail address or international phone number in any text of the file or of consent.json.

Authority for SUBMITTED:
- profile.md auto_apply (default try): `never` refuses every SUBMITTED. `ask` needs review_before_submit true and the
  screenshot approval below. `try` needs application/consent.json for this opening, written by the manager from the
  user's own answer (typed, or the clarify choice clicked). `auto` is standing consent recorded once in profile.md: no consent.json, and instead
  apply_consent: standing, a dated auto_apply_since, the daily caps, a method of no_login_form or linkedin_easy_apply,
  and an analysis.json of this opening that clears the profile: fit.decision PURSUE, fit.score a finite number in
  0..100 at or above apply_threshold, no gate of GATE_NAMES at FAIL, and its id equal to the opening folder name.
  `auto` with review_before_submit true or apply_consent other than standing is refused: the settings contradict
  each other.
- The pre-click --gate refuses every method but no_login_form and linkedin_easy_apply: the other five classes are a
  manual kit, and nothing about them may be clicked.
- application/consent.json (try and ask) holds {opening_id, by, words, date, kit_sha256} for this opening only.
  opening_id equals the opening folder name; by and words are non-empty; by is not a bot profile name; date is
  YYYY-MM-DD.
- kit_sha256 equals the kit hash of application/ now: the consent binds to the documents the user saw.
- The gate is open only while the latest openings/<ID>/review-N.json is APPROVED and the latest status.json line is
  ready or applying. The approval day is the day of the latest ready line; the consent date is not before it.
- Daily caps (auto only): the openings/<ID>/status.json history of the project counts the submissions recorded today
  (the newest `applied` line of each opening, dated today, this opening excluded) plus the live reservations of the
  project. daily_apply_cap (default 10) caps them all; daily_easy_apply_cap (default 5) caps the linkedin_easy_apply
  ones. A cap reached closes the gate with a `daily_cap` rule: the applier applies the next day, never a kit.
- Easy Apply pace (pre-click --gate only): two linkedin_easy_apply gates of the project open at least
  easy_apply_gap_minutes (default 1, 0 turns it off) apart, read from the application/gate.json stamps. A closer one
  closes the gate with `easy_apply_gap` and the seconds left: wait them and run the gate again.
- linkedin_easy_apply: only on an https://<locale.>linkedin.com/jobs/view/<id> link, only under auto_apply: auto.
  Every other method needs an employer ATS link (link_check.py); a job board or portal page is kit only.
- profile.md review_before_submit (default false): true also needs consent.json screenshot_approval
  {by, words, date, screenshot}. The screenshot is an existing image in application/; the date is not before the
  approval date. The record check and the pre-click gate with --before-submit both require it.
- A profile.md that is missing, has no front matter, or does not parse refuses SUBMITTED: the settings cannot be read.

Exit codes: 0 valid (or gate open), 1 contract violations (listed on stderr), 2 unreadable or not JSON.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import re
import sys
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]
LINK_CHECK = SKILLS / "jobs-contract" / "scripts" / "link_check.py"
JOBS_COMMON = SKILLS / "jobs-contract" / "scripts" / "jobs_common.py"
SEEN_STATE = SKILLS / "jobs-contract" / "scripts" / "seen_state.py"
APPLY_STATE = Path(__file__).resolve().parent / "apply_state.py"

RESULTS = ("SUBMITTED", "NEEDS_DATA", "NOT_POSSIBLE")
METHODS = ("no_login_form", "requires_account", "email", "linkedin", "linkedin_easy_apply", "captcha", "other")
# The only two form classes a bot ever clicks: the rest are a manual kit (SKILL.md step 3).
SUBMITTABLE = ("no_login_form", "linkedin_easy_apply")
SOURCES = ("contact.yaml", "application-data.yaml", "answers.md", "cv")
AUTO_APPLY = ("never", "ask", "try", "auto")
APPLY_CONSENT = {"try": "per_opening", "ask": "per_opening", "auto": "standing"}
CONSUMED = ("try", "auto")  # the modes that submit without the user in the loop
CONSULT = re.compile(r"^consult:[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
# A reason that says the form mailed a code ("8-character code e-mailed", "security code sent to the applicant's
# e-mail", "verification code"): jobs-inbox reads it, so a kit needs the code_request that asked for it.
_CODE_WORD = r"(?:security|verification|confirmation|one[- ]time|otp|\d+[- ]character|\d+[- ]digit)\s+code|\bOTP\b"
_SENT = r"(?:e-?mail(?:ed|s)?|mailed|sent|inbox|correo|enviado)"
EMAILED_CODE = re.compile(rf"(?:{_CODE_WORD})[^.]{{0,80}}\b{_SENT}\b|\b{_SENT}\b[^.]{{0,80}}(?:{_CODE_WORD})"
                          r"|c[oó]digo\s+de\s+(?:seguridad|verificaci[oó]n)", re.I)
CODE_OUTCOMES = ("code", "no_code", "unavailable", "timeout")
ID_RE = re.compile(r"^JOB-\d{8}-[a-z0-9]+(?:-[a-z0-9]+)*$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# A LinkedIn Easy Apply run happens on the job page itself: https://<locale.>linkedin.com/jobs/view/<id>[/][?query]
EASY_APPLY_URL = re.compile(r"^https://(?:[a-z]{2,3}\.)?(?:www\.)?linkedin\.com/jobs/view/\d{6,12}/?(?:[?#]\S*)?$",
                            re.IGNORECASE)
FRONT = re.compile(r"\A\ufeff?---[ \t]*\n(.*?)\n---", re.S)
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
GATE_STATUSES = ("ready", "applying")
RECORD_STATUSES = ("ready", "applying", "applied")
KIT_SHA = re.compile(r"^[0-9a-f]{64}$")
REVIEW_NAME = re.compile(r"review-(c?)(\d+)\.json\Z")
# Every bot profile of squads/jobs/squad.yaml: consent.json is the user's own answer (typed or a clicked choice), and no bot writes it.
BOT_NAMES = frozenset({"jobs", "jobs-scout", "jobs-writer", "jobs-reviewer", "jobs-applier", "jobs-inbox"})
# --post-submit softens these rules and no others, and only with proof the gate opened for this opening under
# GATE_HOURS ago (application/gate.json, written by --gate): they are the ones that can move between the click and the
# record. A rule about what was never submittable (auto_apply: never, a missing consent file, no review, an unverifiable
# or job-board link, an analysis that said REJECT), a status history that never reached ready and an unreadable profile
# stay hard.
RECHECK_SOFT = frozenset({"daily_cap", "review.replaced", "review.status", "consent.date"})
DEFAULT_APPLY_CAP = 10
DEFAULT_EASY_APPLY_CAP = 5
DEFAULT_EASY_APPLY_GAP = 1  # minutes between two Easy Apply gates: LinkedIn restricts accounts that apply in bursts
DEFAULT_THRESHOLD = 70
NEEDS_REVIEW = ("SUBMITTED needs an approved review: openings/<ID>/review-N.json with verdict APPROVED, and a ready "
                "line in status.json")
NEEDS_ANALYSIS = ("auto_apply: auto needs openings/<ID>/analysis.json for this opening: its id, gates, fit.score and "
                  "fit.decision decide the submit")
REQUIRED = ("id", "result", "method", "filled_fields", "pending_questions", "screenshots", "reason")
CONTACT_PATTERNS = (
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"),
    re.compile(r"\+\d{1,3}[ -]?\d[\d -]{6,}\d"),
)


def ats_ids() -> tuple:
    """The employer ATS ids link_check.py knows (official_hosts.json `ats`): each names a no-login form."""
    module = load_module("jobs_link_check_ids", LINK_CHECK)
    try:
        return tuple(entry["id"] for entry in module.load_data()["ats"])
    except Exception:  # noqa: BLE001 - an unreadable host list is reported by check_apply_url
        return ()


def form_class(method: str):
    """(form class, ATS id): an ATS name stands for no_login_form on that ATS; a form class stands for itself."""
    name = (method or "").strip().lower()
    if name in METHODS:
        return name, ""
    if name in ats_ids():
        return "no_login_form", name
    return method, ""


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


jc = load_module("jobs_common_for_check", JOBS_COMMON)


@functools.lru_cache(maxsize=None)
def helper(name: str, path: Path):
    """A helper script of the squad, loaded once as a module: one rule, read by every script that needs it."""
    return load_module(f"jobs_{name}_for_check", path)


def gate_names() -> tuple:
    """The gates score_analysis.decide() reads: jobs_common.GATE_NAMES, the one list the decision and this gate share."""
    return jc.GATE_NAMES


def check_number(value, label: str) -> float:
    """A finite number from 0 to 100 (seen_state.check_number): a score is never NaN, Infinity or 1e9."""
    return helper("seen_state", SEEN_STATE).check_number(value, label)


AS = helper("apply_state", APPLY_STATE)


def read_object(path: Path):
    """The JSON object in path, or None when it is missing, unreadable or not an object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def strict_day(value):
    """A YYYY-MM-DD day, or None. Accepts the text and the date object YAML turns an unquoted date into."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not DAY_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def approval(opening: Path, allowed=GATE_STATUSES):
    """(day, problem, rule). The latest review-N.json must be APPROVED and the latest status.json line must be one of
    `allowed`; day is the day of the latest ready line. A later FIX, NOT_APPROVED, in_review or skipped closes it.
    The record check also accepts `applied`: the record writes it, so a second record must still pass. The rule says
    which part failed: a review that was replaced or a status that moved is a change round after the click
    (--post-submit may flag it), while a file that never held an approval is a fact about the opening."""
    # Every review file counts, whatever its numbering (review-2.json, review-c1.json): the newest one on disk is the
    # latest, so a later change review can never hide behind an older approval.
    reviews = []
    for path in opening.glob("review-*.json"):
        if REVIEW_NAME.match(path.name):
            reviews.append((path.stat().st_mtime_ns, path.name, path))
    if not reviews:
        return None, NEEDS_REVIEW, "review.missing"
    _, name, path = max(reviews)
    verdict = (read_object(path) or {}).get("verdict")
    if verdict != "APPROVED":
        return (None, f"SUBMITTED needs an approved review: the latest {name} is {verdict!r}, not APPROVED",
                "review.replaced")
    history = (read_object(opening / "status.json") or {}).get("history")
    lines = [item for item in history if isinstance(item, dict)] if isinstance(history, list) else []
    ready = [item for item in lines if item.get("status") == "ready"]
    stamp = ready[-1].get("date") if ready else None
    day = strict_day(stamp[:10]) if isinstance(stamp, str) else None
    if day is None:
        return None, "status.json has no dated ready line: the approval day is unknown", "review.never_ready"
    last = lines[-1].get("status") if lines else None
    if last not in allowed:
        return (None, f"the latest status.json line is {last!r}: SUBMITTED needs {' or '.join(allowed)}",
                "review.status")
    return day, None, ""


def kit_sha256(application: Path):
    """The kit hash; one definition in jobs_common so the manager's kit_hash.py and this gate never disagree."""
    return jc.kit_sha256(application)


def last_easy_apply_gate(project: Path, exclude: str = ""):
    """UTC time of the newest Easy Apply gate opened in the project (application/gate.json), or None."""
    newest = None
    folder = project / "openings"
    for stamp_file in sorted(folder.glob("JOB-*/application/gate.json")) if folder.is_dir() else []:
        doc = read_object(stamp_file) or {}
        if stamp_file.parent.parent.name == exclude or doc.get("method") != "linkedin_easy_apply":
            continue
        try:
            when = datetime.strptime(str(doc.get("opened_at") or ""), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        newest = when if newest is None or when > newest else newest
    return newest


def submissions_today(project: Path, day: date, exclude: str = "") -> dict:
    """The submissions the project already holds on `day`: the recorded ones plus the reservations of open gates.

    record_submission.py appends `applied` to openings/<ID>/status.json and writes that opening's submission.json, so
    the history says when and the record says how. An opening counts once when the newest date among its `applied`
    lines is `day`: the list order says nothing, since a later line may carry an older date. It counts as an Easy Apply
    when its submission.json method is linkedin_easy_apply. A live reservation left by an open gate counts too, so two
    appliers at nine of ten cannot both take the tenth place, but an opening that already has an `applied` line of the
    day counts once: a record that died between its status append and its release must not use two places. `exclude`
    leaves this opening out, so recording the submit that just filled the cap never refuses itself.
    """
    total = easy = 0
    applied = set()
    folder = project / "openings"
    for opening in sorted(folder.glob("JOB-*")) if folder.is_dir() else []:
        if not opening.is_dir() or opening.name == exclude:
            continue
        history = (read_object(opening / "status.json") or {}).get("history")
        lines = [item for item in history if isinstance(item, dict)] if isinstance(history, list) else []
        days = [strict_day(str(item.get("date") or "")[:10]) for item in lines if item.get("status") == "applied"]
        # A record written today leaves an `applied` line dated today; a status moved on to interview or rejected
        # later keeps that line, so the history still counts the submission.
        when = max((found for found in days if found is not None), default=None)
        if when != day:
            continue
        applied.add(opening.name)
        total += 1
        if (read_object(opening / "application" / "submission.json") or {}).get("method") == "linkedin_easy_apply":
            easy += 1
    for opening_id, held in AS.live(project).items():
        if opening_id == exclude or opening_id in applied or strict_day(held.get("date")) != day:
            continue
        total += 1
        if held.get("method") == "linkedin_easy_apply":
            easy += 1
    return {"total": total, "easy_apply": easy}


def flag(value, name: str):
    """(True|False, problem): a yes/no profile key. Anything else is a problem, so a typo never reads as no."""
    if value in (None, False, "false", "no"):
        return False, None
    if value in (True, "true", "yes"):
        return True, None
    return None, f"{name} must be true or false in profile.md"


def profile_settings(base: Path):
    """(front matter, problem) of the profile.md of the project that owns this opening. A missing or unreadable
    profile refuses the submit: the settings that decide it must be known, never assumed."""
    if not (base.name == "application" and base.parent.parent.name == "openings"):
        return {}, "SUBMITTED needs the openings/<ID>/application layout: the project profile.md is read from it"
    path = base.parent.parent.parent / "profile.md"
    if not path.is_file():
        return {}, "profile.md is missing from the project: the auto_apply and review settings cannot be read"
    match = FRONT.match(path.read_text(encoding="utf-8", errors="ignore"))
    if not match:
        return {}, "profile.md has no front matter: the auto_apply and review settings cannot be read"
    try:
        meta = jc.load_yaml(match.group(1))
    except Exception as exc:  # noqa: BLE001 - any parser error means the settings are unknown
        return {}, f"profile.md front matter does not parse ({exc}): the settings cannot be read"
    return (meta if isinstance(meta, dict) else {}), None


class Checker:
    def __init__(self, path: Path):
        self.path = path
        self.base = path.parent
        self.errors: list[str] = []
        self.flags: list[str] = []
        self.soft = False
        self.post_submit = False
        self.apply_url = ""
        self.method = ""
        self.ats = ""  # the ATS id --method named, when it named one: the apply_url must sit on it
        self.today = date.today()
        self.gate_open_now = False  # True only on the pre-click --gate: the Easy Apply gap never refuses a record
        self._settings = None

    def error(self, where: str, message: str) -> None:
        """A contract violation, unless it is one of the rules that moved after the click and the gate opened for it."""
        softened = self.soft and where in RECHECK_SOFT
        (self.flags if softened else self.errors).append(f"{where}: {message}")

    @contextmanager
    def recheck(self):
        """The rules inside may have moved between the click and the record: --post-submit flags them.

        record_submission.py runs this check after the click. A submit that happened is recorded with the rule that
        moved, never dropped: an invisible submit escapes the cap and can be applied a second time. It needs proof the
        gate opened for this opening under GATE_HOURS ago (the application/gate.json stamp --gate writes), or the
        record is a first check and every rule stays hard.
        """
        self.soft = AS.gate_recent(self.base, self.base.parent.name)
        try:
            yield
        finally:
            self.soft = False

    def settings(self):
        """(front matter, problem) of the project profile.md, read once."""
        if self._settings is None:
            self._settings = profile_settings(self.base)
        return self._settings

    def settings_of(self):
        """(settings, mode, problem, key): the auto_apply mode, or the problem that stops the decision and its key."""
        settings, problem = self.settings()
        if problem:
            return {}, None, problem, "profile"
        mode = settings.get("auto_apply")
        mode = "try" if mode is None else mode
        if mode not in AUTO_APPLY:
            return settings, None, "must be never, ask, try or auto in profile.md", "auto_apply"
        return settings, mode, None, ""

    def strings(self, value, where: str):
        """Every string inside a value, with the path it sits at (for the contact-data scan)."""
        if isinstance(value, str):
            yield where, value
        elif isinstance(value, dict):
            for key, inner in value.items():
                yield from self.strings(inner, f"{where}.{key}")
        elif isinstance(value, list):
            for i, inner in enumerate(value):
                yield from self.strings(inner, f"{where}[{i}]")

    def resolve(self, raw: str) -> Path:
        candidate = Path(raw).expanduser()
        return candidate if candidate.is_absolute() else self.base / candidate

    def inside(self, raw: str):
        """The real path of a file under application/, or None when it resolves outside that folder."""
        target = self.resolve(raw).resolve()
        return target if target.is_relative_to(self.base.resolve()) else None

    def present(self, raw: str) -> bool:
        target = self.inside(raw)
        return target is not None and target.is_file()

    def check(self, data: dict) -> None:
        for key in REQUIRED:
            if key not in data:
                self.error(key, "missing")
        if self.errors:
            return
        self.method, self.ats = form_class(data["method"] if isinstance(data["method"], str) else "")
        data = {**data, "method": self.method}
        self.check_id(data["id"])
        if data["result"] not in RESULTS:
            self.error("result", f"must be one of {', '.join(RESULTS)}")
        if data["method"] not in METHODS:
            self.error("method", f"must be one of {', '.join(METHODS)}, or an employer ATS name ({', '.join(ats_ids())})")
        if not isinstance(data["reason"], str):
            self.error("reason", "must be a string (empty allowed for SUBMITTED)")
        fields = self.check_fields(data["filled_fields"])
        pending = self.check_pending(data["pending_questions"])
        shots = self.check_screenshots(data["screenshots"])
        for where, text in self.strings(data, ""):
            if any(p.search(text) for p in CONTACT_PATTERNS):
                self.error(where.lstrip(".") or "file", "contact data in a text value; keep values out of the file")
        if data["result"] == "SUBMITTED":
            mode = self.settings_of()[1]
            self.check_submitted(data, fields, pending, shots, mode)
            # The record file itself must be truthful; the authority around it can move between the click and here.
            if self.post_submit:
                with self.recheck():
                    self.check_authority(screenshot=True, at_gate=False)
                    self.check_apply_url(self.apply_url)
            else:
                self.check_authority(screenshot=True, at_gate=False)
                self.check_apply_url(self.apply_url)
        elif data["result"] == "NEEDS_DATA":
            if not pending:
                self.error("pending_questions", "NEEDS_DATA needs at least one question")
        elif data["result"] == "NOT_POSSIBLE":
            self.check_not_possible(data)

    def check_gate(self, before_submit: bool) -> None:
        """The checks that must pass before the first click on a submit (the screenshot part only before the click)."""
        opening = self.base.parent
        if not (self.base.name == "application" and ID_RE.match(opening.name) and len(opening.name) <= 50):
            self.error("folder", "the gate needs FILE inside openings/<ID>/application/")
            return
        if not self.method:
            # The record does not exist yet before the first click: the applier names the form class with --method.
            self.method = (read_object(self.path) or {}).get("method") or "no_login_form"
        self.method, self.ats = form_class(self.method)
        if self.method not in METHODS:
            self.error("method", f"must be one of {', '.join(METHODS)}, or an employer ATS name "
                                 f"({', '.join(ats_ids())}): an ATS board form is no_login_form")
            return
        if self.method not in SUBMITTABLE:
            self.error("method", f"{self.method} is never a submit click: only no_login_form or linkedin_easy_apply "
                                 f"are submitted, and every other form class goes to a manual kit")
            return
        project = opening.parent.parent
        self.gate_open_now = True
        self.check_confidential(project)
        # One applier at a time reads the caps and takes its place: the reservation written below is what a second
        # applier sees, so nine of ten leaves one place and not two.
        with AS.locked(project):
            self.check_authority(screenshot=before_submit, at_gate=True)
            self.check_apply_url(self.apply_url)
            if not self.errors:
                mode = self.settings_of()[1]
                # The stamp is the proof the record needs to soften a rule that moved after the click: every mode
                # writes it, because every mode can have its cap filled between the gate and the record.
                AS.stamp(self.base, opening.name, self.method, mode or "")
                if mode == "auto":
                    AS.reserve(project, opening.name, self.today, self.method)

    def check_id(self, opening_id) -> None:
        if not isinstance(opening_id, str) or not ID_RE.match(opening_id) or len(opening_id) > 50:
            self.error("id", "must be JOB-YYYYMMDD-<slug>, lowercase, at most 50 characters")
            return
        if self.path.parent.name == "application" and self.path.parent.parent.name != opening_id:
            self.error("id", f"does not match the opening folder '{self.path.parent.parent.name}'")

    def check_fields(self, fields) -> list:
        if not isinstance(fields, list):
            self.error("filled_fields", "must be a list")
            return []
        for i, item in enumerate(fields):
            where = f"filled_fields[{i}]"
            if not isinstance(item, dict):
                self.error(where, "must be an object {field, source}")
                continue
            extra = sorted(set(item) - {"field", "source"})
            if extra:
                self.error(where, f"holds {', '.join(extra)}; a filled field keeps its name and source only")
            if not isinstance(item.get("field"), str) or not item.get("field", "").strip():
                self.error(where, "field must name the form field")
            source = item.get("source")
            if not (source in SOURCES or (isinstance(source, str) and CONSULT.match(source))):
                self.error(where, "source must be contact.yaml, application-data.yaml, answers.md, cv "
                                  "or consult:<card id>")
        return fields

    def check_pending(self, pending) -> list:
        if not isinstance(pending, list):
            self.error("pending_questions", "must be a list")
            return []
        for i, item in enumerate(pending):
            where = f"pending_questions[{i}]"
            question = item.get("question") if isinstance(item, dict) else item
            if not isinstance(question, str) or not question.strip():
                self.error(where, "needs the question text")
            if isinstance(item, dict) and "options" in item and not isinstance(item["options"], list):
                self.error(where, "options must be a list of the form's choices")
        return pending

    def check_screenshots(self, shots) -> list:
        if not isinstance(shots, list):
            self.error("screenshots", "must be a list of image paths")
            return []
        for i, raw in enumerate(shots):
            where = f"screenshots[{i}]"
            if not isinstance(raw, str) or not raw.lower().endswith(IMAGE_SUFFIXES):
                self.error(where, "must be a path to a .png, .jpg, .jpeg or .webp file")
            elif self.inside(raw) is None:
                self.error(where, "must be a file inside application/: a path outside that folder is refused")
            elif not self.present(raw):
                self.error(where, "file does not exist")
        return shots

    def check_submitted(self, data, fields, pending, shots, mode) -> None:
        method = data["method"]
        if method == "linkedin_easy_apply":
            if mode != "auto":
                self.error("method", "linkedin_easy_apply needs auto_apply: auto in profile.md: Easy Apply runs on "
                                     "standing consent, never on one opening's apply")
        elif method != "no_login_form":
            self.error("method", "SUBMITTED needs method no_login_form or linkedin_easy_apply; every other class "
                                 "goes to a kit")
        if not fields:
            self.error("filled_fields", "SUBMITTED needs at least one filled field with its source")
        if pending:
            self.error("pending_questions", "SUBMITTED cannot carry open questions")
        confirmations = [s for s in shots if isinstance(s, str) and "confirm" in Path(s).name.lower()]
        if not confirmations:
            self.error("screenshots", "SUBMITTED needs a confirmation screenshot named confirmation.<ext>")
        elif not any(self.present(s) for s in confirmations):
            self.error("screenshots", "the confirmation screenshot does not exist")

    def check_confidential(self, project: Path) -> None:
        """A kit text that names a profile.md `confidential_terms` entry never goes out: the gate stays closed."""
        settings, _problem = self.settings()
        terms = jc.confidential_terms(settings) if isinstance(settings, dict) else []
        for name in ("cover_letter.md", "answers.md", "recruiter_message.md", "cv_ats.txt", "letter_ats.txt"):
            path = self.base / name
            hits = jc.confidential_hits(path.read_text(encoding="utf-8", errors="ignore"), terms) \
                if terms and path.is_file() else []
            if hits:
                self.error("confidential", f"{name} names {', '.join(map(repr, hits))} (profile.md "
                                           "confidential_terms): correct the kit before any submit")

    def check_authority(self, screenshot: bool, at_gate: bool) -> None:
        """The consent, the review approval and the profile settings that decide whether a submit may happen."""
        opening = self.base.parent
        settings, mode, problem, key = self.settings_of()
        if problem:
            self.error(key, problem)
            return
        if mode == "never":
            self.error("auto_apply", "profile.md sets auto_apply: never; this opening gets a manual kit, not a submit")
            return
        review_flag, problem = flag(settings.get("review_before_submit"), "review_before_submit")
        if problem:
            self.error("review_before_submit", problem)
            return
        if mode == "ask" and not review_flag:
            self.error("review_before_submit", "auto_apply: ask needs review_before_submit: true (the user approves "
                                               "the screenshot before the submit)")
            return
        if mode == "auto" and review_flag:
            self.error("review_before_submit", "auto_apply: auto submits on standing consent, so nobody sees the "
                                               "screenshot: write auto_apply: ask if the user approves each one")
            return
        approved, problem, rule = approval(opening, GATE_STATUSES if at_gate else RECORD_STATUSES)
        if problem:
            self.error(rule or "review", problem)
        if mode == "auto":
            self.check_standing(opening, settings)
            return
        needs_screenshot = review_flag or mode == "ask"
        path = self.base / "consent.json"
        if not path.is_file():
            self.error("consent", "SUBMITTED needs application/consent.json with the user's answer for this opening")
            return
        consent = read_object(path)
        if consent is None:
            self.error("consent", "consent.json is not a JSON object")
            return
        for where, text in self.strings(consent, "consent"):
            if any(p.search(text) for p in CONTACT_PATTERNS):
                self.error(where, "contact data in consent.json; quote the user's answer without addresses or numbers")
        if consent.get("opening_id") != opening.name:
            self.error("consent.opening_id", f"names {consent.get('opening_id')!r}, not this opening "
                                             f"{opening.name!r}: consent covers one opening")
        for key in ("by", "words"):
            if not isinstance(consent.get(key), str) or not consent[key].strip():
                self.error(f"consent.{key}", "must be the non-empty answer the user gave (typed or the choice clicked)")
        by = consent.get("by")
        if isinstance(by, str) and by.strip().casefold() in BOT_NAMES:
            self.error("consent.by", f"names the bot profile {by.strip()!r}: consent is the user's own name, and no bot "
                                     "writes it")
        given = strict_day(consent.get("date"))
        if given is None:
            self.error("consent.date", "must be YYYY-MM-DD")
        elif approved is not None and given < approved:
            self.error("consent.date", f"{given} is before the review approval {approved}")
        self.check_kit(consent)
        if needs_screenshot and screenshot:
            self.check_screenshot_approval(consent, approved)

    def check_standing(self, opening: Path, settings: dict) -> None:
        """auto_apply: auto — the consent recorded once in profile.md, and what still limits each submit."""
        consent = settings.get("apply_consent", "per_opening")
        if consent != "standing":
            self.error("apply_consent", "auto_apply: auto submits on standing consent: profile.md needs "
                                        "apply_consent: standing (per_opening asks for every opening)")
            return
        since = strict_day(settings.get("auto_apply_since"))
        if since is None:
            self.error("auto_apply_since", "auto_apply: auto needs the day the user said yes: "
                                           "auto_apply_since: YYYY-MM-DD in profile.md")
            return
        if since > self.today:
            self.error("auto_apply_since", f"{since} is after today: the standing consent is not in force yet")
        self.check_opening_fit(opening, settings)
        self.check_daily_caps(opening, settings)

    def check_opening_fit(self, opening: Path, settings: dict) -> None:
        """analysis.json of this opening: score_analysis.decide() said PURSUE, no gate FAILs, and the numbers are real.

        The score alone is not a decision. REJECT covers a failed language, location or seniority gate, a deal-breaker
        and a hard gap in a core must-have; a WATCH is a question the user still has to answer. None of them may be
        submitted on standing consent, and this is the last check before an irreversible click.
        """
        analysis = read_object(opening / "analysis.json")
        if analysis is None:
            self.error("analysis", NEEDS_ANALYSIS)
            return
        if analysis.get("id") != opening.name:
            self.error("analysis.id", f"names {analysis.get('id')!r}, not this opening {opening.name!r}: another "
                                      f"opening's analysis never decides this submit")
        gates = analysis.get("gates")
        gates = gates if isinstance(gates, dict) else {}
        failed = [name for name in gate_names() if gates.get(name) == "FAIL"]
        if failed:
            self.error("gates", f"gate FAIL: {', '.join(failed)}: auto_apply: auto never submits an opening that "
                                f"failed a gate")
        eligibility = gates.get("eligibility")
        if eligibility != "PASS":
            self.error("eligibility", f"auto_apply: auto submits only an eligible opening: gates.eligibility is "
                                      f"{eligibility!r}, not PASS")
        fit = analysis.get("fit")
        fit = fit if isinstance(fit, dict) else {}
        decision = fit.get("decision")
        if decision != "PURSUE":
            self.error("fit.decision", f"is {decision!r}, not PURSUE: auto_apply: auto submits only an opening "
                                       f"score_analysis.py decided to pursue, never a WATCH or a REJECT")
        try:
            threshold = check_number(settings.get("apply_threshold", DEFAULT_THRESHOLD), "apply_threshold")
        except ValueError:
            self.error("apply_threshold", "must be a finite number from 0 to 100 in profile.md")
            return
        try:
            score = check_number(fit.get("score"), "fit.score")
        except ValueError as exc:
            self.error("fit", f"analysis.json {exc}: the applier cannot tell whether the opening clears "
                              f"apply_threshold {threshold:g}")
            return
        if score < threshold:
            self.error("fit", f"fit.score {score:g} is below apply_threshold {threshold:g}: auto_apply: auto does "
                              f"not submit this one")

    def check_daily_caps(self, opening: Path, settings: dict) -> None:
        """The day's caps: submissions recorded today across the project, Easy Apply counted on its own."""
        caps = {}
        for key, default in (("daily_apply_cap", DEFAULT_APPLY_CAP), ("daily_easy_apply_cap", DEFAULT_EASY_APPLY_CAP)):
            value = settings.get(key, default)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                self.error(key, f"must be a whole number from 1 up in profile.md (default {default})")
                return
            caps[key] = value
        counts = submissions_today(opening.parent.parent, self.today, exclude=opening.name)
        if counts["total"] >= caps["daily_apply_cap"]:
            self.error("daily_cap", f"{counts['total']} applications are already recorded today and "
                                    f"daily_apply_cap is {caps['daily_apply_cap']}: apply this opening tomorrow, "
                                    f"never a kit")
        elif self.method == "linkedin_easy_apply" and counts["easy_apply"] >= caps["daily_easy_apply_cap"]:
            self.error("daily_cap", f"{counts['easy_apply']} LinkedIn Easy Apply submissions are already recorded "
                                    f"today and daily_easy_apply_cap is {caps['daily_easy_apply_cap']}: apply this "
                                    f"opening tomorrow, never a kit")
        elif self.method == "linkedin_easy_apply" and self.gate_open_now:
            self.check_easy_apply_gap(opening, settings)

    def check_easy_apply_gap(self, opening: Path, settings: dict) -> None:
        """LinkedIn restricts accounts that apply in bursts: two Easy Apply gates open at least
        `easy_apply_gap_minutes` (default 1) apart. A closed gap is `easy_apply_gap`: wait the seconds named, then
        run the gate again; never a kit and never tomorrow."""
        gap = settings.get("easy_apply_gap_minutes", DEFAULT_EASY_APPLY_GAP)
        if isinstance(gap, bool) or not isinstance(gap, (int, float)) or not 0 <= gap <= 60:
            self.error("easy_apply_gap_minutes", f"must be a number of minutes from 0 to 60 in profile.md "
                                                 f"(default {DEFAULT_EASY_APPLY_GAP})")
            return
        last = last_easy_apply_gate(opening.parent.parent, exclude=opening.name)
        if last is None or gap == 0:
            return
        left = int(gap * 60 - (datetime.now(timezone.utc) - last).total_seconds())
        if left > 0:
            self.error("easy_apply_gap", f"the last Easy Apply gate opened {int(gap * 60) - left} s ago and "
                                         f"easy_apply_gap_minutes is {gap:g}: wait {left} s, then run the gate again")

    def check_screenshot_approval(self, consent: dict, approved) -> None:
        shot = consent.get("screenshot_approval")
        if not isinstance(shot, dict):
            self.error("screenshot_approval", "review_before_submit is true: consent.json needs the user's approval of "
                                              "the pre-submit screenshot")
            return
        for key in ("by", "words"):
            if not isinstance(shot.get(key), str) or not shot[key].strip():
                self.error(f"screenshot_approval.{key}", "must be the non-empty answer the user gave (typed or the choice clicked)")
        given = strict_day(shot.get("date"))
        if given is None:
            self.error("screenshot_approval.date", "must be YYYY-MM-DD")
        elif approved is not None and given < approved:
            self.error("screenshot_approval.date", f"{given} is before the review approval {approved}")
        name = shot.get("screenshot")
        if not isinstance(name, str) or not name.lower().endswith(IMAGE_SUFFIXES):
            self.error("screenshot_approval.screenshot", "must name the pre-submit image (a .png, .jpg, .jpeg or .webp)")
        elif self.inside(name) is None:
            self.error("screenshot_approval.screenshot", "must name an image inside application/")
        elif not self.present(name):
            self.error("screenshot_approval.screenshot", "the named pre-submit image does not exist")

    def check_kit(self, consent: dict) -> None:
        """The consent is bound to the kit the user saw: its hash must equal the kit as it is now."""
        recorded = consent.get("kit_sha256")
        if not isinstance(recorded, str) or not KIT_SHA.match(recorded):
            self.error("consent.kit_sha256", "must be the kit hash (check_submission.py --kit-hash) written when the user "
                                             "said apply")
            return
        current = kit_sha256(self.base)
        if current is None:
            self.error("kit", "application/cv_ats.pdf is missing: there is no kit to bind the consent to")
        elif current != recorded:
            self.error("consent.kit_sha256", "the documents in application/ changed after the user said apply: ask the "
                                             "user again")

    def check_apply_url(self, apply_url) -> None:
        """An auto-submission is allowed only through a link this method may be filled on."""
        if not apply_url:
            opening = self.base.parent / "opening.md"
            meta = jc.read_front_matter(opening) if opening.is_file() else {}
            apply_url = str(meta.get("apply_url") or "")
        if not apply_url:
            self.error("apply_url", "SUBMITTED needs the opening's apply_url (opening.md or --apply-url) to check it")
            return
        if self.method == "linkedin_easy_apply":
            # Easy Apply happens on the job page the scout read; no ATS board exists and link_check.py calls it a
            # portal. The one address shape it may run on is the posting itself.
            if not EASY_APPLY_URL.match(apply_url.strip()):
                self.error("apply_url", "linkedin_easy_apply runs only on a https://www.linkedin.com/jobs/view/<id> "
                                        "link: this apply_url is not one")
            return
        if not LINK_CHECK.is_file():
            self.error("apply_url", f"link_check.py not found at {LINK_CHECK}; cannot clear the link")
            return
        module = load_module("jobs_link_check", LINK_CHECK)
        result = module.classify(apply_url, module.load_data())
        verdict, kind = result.get("verdict"), result.get("kind")
        if verdict == "unverified":
            self.error("apply_url", "the apply link is unverified (link_check.py): only a manual kit is allowed")
        elif verdict == "job_board" or kind == "portal":
            # The bot submits only through the employer's own ATS; a portal or board page is never an apply target.
            self.error("apply_url", "the apply link is a job board or portal, not the employer: kit only")
        elif verdict not in ("verified", "official_ats"):
            self.error("apply_url", f"the apply link verdict '{verdict}' is not an employer ATS: kit only")
        elif self.ats and result.get("ats") != self.ats:
            self.error("method", f"--method {self.ats} names an ATS the apply link is not on "
                                 f"({result.get('ats') or result.get('host')}): open the form on apply_url")

    def check_not_possible(self, data) -> None:
        if not isinstance(data["reason"], str) or not data["reason"].strip():
            self.error("reason", "NOT_POSSIBLE needs the reason")
        elif EMAILED_CODE.search(data["reason"]):
            # A code mailed to the applicant is in the user's mailbox, which jobs-inbox reads: it is asked for
            # (code_wait.py), and only its answer can end the submit in a kit.
            request = data.get("code_request")
            if not (isinstance(request, dict) and isinstance(request.get("outcome"), str)
                    and request["outcome"] in CODE_OUTCOMES and request["outcome"] != "code"):
                self.error("code_request", "the form mailed a code: ask jobs-inbox with code_wait.py and record "
                                           "code_request {card, outcome} (no_code, unavailable or timeout) before a "
                                           "NOT_POSSIBLE; outcome code means type it and submit")
            elif request["outcome"] != "unavailable" and not str(request.get("card") or "").strip():
                self.error("code_request", "code_request.card names the jobs-inbox card that was asked")
        kit = data.get("manual_kit", "application/kit.md")
        if not isinstance(kit, str) or not kit.endswith("kit.md"):
            self.error("manual_kit", "must name application/kit.md")
        if not (self.base / "kit.md").is_file():
            self.error("manual_kit", "application/kit.md does not exist beside submission.json")


def read(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"error: cannot read {path}: {exc.strerror}") from None
    try:
        data = json.loads(text)
    except ValueError:
        raise SystemExit(f"error: {path} is not valid JSON") from None
    if not isinstance(data, dict):
        raise SystemExit(f"error: {path} must hold one JSON object")
    return data


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Validate application/submission.json against the jobs contract.")
    p.add_argument("file", nargs="?", help="openings/<ID>/application/submission.json")
    p.add_argument("--kit-hash", metavar="APP_DIR", help="print the kit hash of an application/ folder and exit")
    p.add_argument("--gate", action="store_true",
                   help="decide before the first click: consent, review, profile settings and apply_url (FILE may "
                        "not exist yet)")
    p.add_argument("--before-submit", action="store_true",
                   help="with --gate: also require the pre-submit screenshot approval (review_before_submit)")
    p.add_argument("--post-submit", action="store_true",
                   help="after the click: the record's own contract still fails, but the rules that can move between "
                        "the gate and the record (cap, replaced review, consent date) are reported as flags when a "
                        "gate stamp for this opening is under 4 hours old")
    p.add_argument("--json", action="store_true", help="print {ok, result, errors} as JSON on stdout")
    p.add_argument("--apply-url", default="", help="the apply link (default: apply_url in ../opening.md)")
    p.add_argument("--method", default="", help="the form class the gate decides for, when submission.json does not "
                                               "exist yet: linkedin_easy_apply, no_login_form, or the employer ATS "
                                               "the form is on (ashby, greenhouse, lever, ...: a no_login_form)")
    p.add_argument("--today", default="", help="YYYY-MM-DD in place of the local date (the daily caps count it)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.kit_hash:
        folder = Path(args.kit_hash).expanduser().resolve()
        if not folder.is_dir():
            print(f"error: {folder} is not a folder", file=sys.stderr)
            return 2
        digest = kit_sha256(folder)
        if digest is None:
            print(f"error: {folder / 'cv_ats.pdf'} is missing: the kit has no CV", file=sys.stderr)
            return 2
        print(digest)
        return 0
    if not args.file:
        print("error: give FILE, or --kit-hash APP_DIR", file=sys.stderr)
        return 2
    path = Path(args.file).expanduser().resolve()
    checker = Checker(path)
    checker.apply_url = args.apply_url
    checker.method = args.method
    checker.post_submit = args.post_submit and not args.gate
    if args.today:
        day = strict_day(args.today)
        if day is None:
            print(f"error: --today must be YYYY-MM-DD, got {args.today!r}", file=sys.stderr)
            return 2
        checker.today = day
    if args.gate:
        checker.check_gate(before_submit=args.before_submit)
        if args.json:
            print(json.dumps({"ok": not checker.errors, "gate": "closed" if checker.errors else "open",
                              "errors": checker.errors}, indent=2))
        if checker.errors:
            for line in checker.errors:
                print(f"rule: {line}", file=sys.stderr)
            return 1
        if not args.json:
            print("gate: open")
        return 0
    try:
        data = read(path)
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 2
    checker.check(data)
    result = data.get("result") if isinstance(data.get("result"), str) else None
    for line in checker.flags:
        print(f"flag: {line}", file=sys.stderr)
    if args.json:
        print(json.dumps({"ok": not checker.errors, "result": result, "errors": checker.errors,
                          "flags": checker.flags}, indent=2))
    if checker.errors:
        for line in checker.errors:
            print(f"rule: {line}", file=sys.stderr)
        return 1
    if not args.json:
        print(f"valid: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
