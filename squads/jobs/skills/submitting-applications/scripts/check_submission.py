#!/usr/bin/env python3
"""Validate openings/<ID>/application/submission.json against the jobs contract, and gate the submit itself.

Usage:
  check_submission.py FILE [--json] [--apply-url URL]                      validate the record (any result)
  check_submission.py FILE --gate [--before-submit] [--json] [--apply-url URL]
                                                 decide before the first click; --before-submit also requires the
                                                 pre-submit screenshot approval (run it after before.png exists)
  check_submission.py --kit-hash APP_DIR         print the kit hash of application/ (consent.json kit_sha256)

FILE is the submission.json of one opening. Relative paths resolve against the folder that holds FILE (application/);
a screenshot or approval image must resolve inside that folder. Nothing is written.

Rules (contract: jobs-contract references/opening-files.md, submission.json):
- id is a JOB-YYYYMMDD-<slug> of at most 50 characters and, when FILE sits in openings/<ID>/application/, equals the
  folder name.
- result is SUBMITTED, NEEDS_DATA or NOT_POSSIBLE; method is one of the six form classes.
- filled_fields lists {field, source} only: every filled field has a source (contact.yaml, application-data.yaml,
  answers.md, cv or consult:<card id>). A value key is refused: the file never carries field values.
- SUBMITTED: method no_login_form; at least one filled field; no pending_questions; a screenshot named like
  confirmation.* that exists; every screenshot listed exists; the authority rules below; the apply_url is not
  `unverified` (link_check.py).
- NEEDS_DATA: at least one pending question with its text (options optional).
- NOT_POSSIBLE: a reason, and application/kit.md exists beside the file (manual_kit names it when given).
- No e-mail address or international phone number in any text of the file or of consent.json.

Authority for SUBMITTED:
- application/consent.json holds {opening_id, by, words, date, kit_sha256}. The manager writes it from the user's
  literal words for this opening only. opening_id equals the opening folder name; by and words are non-empty; by is
  not a bot profile name; date is YYYY-MM-DD.
- kit_sha256 equals the kit hash of application/ now: the consent binds to the documents the user saw.
- The gate is open only while the latest openings/<ID>/review-N.json is APPROVED and the latest status.json line is
  ready or applying. The approval day is the day of the latest ready line; the consent date is not before it.
- profile.md auto_apply (default try): `never` refuses every SUBMITTED. `ask` needs review_before_submit true and the
  screenshot approval below. Any value other than never, ask or try is refused.
- profile.md review_before_submit (default false): true also needs consent.json screenshot_approval
  {by, words, date, screenshot}. The screenshot is an existing image in application/; the date is not before the
  approval date. The record check and the pre-click gate with --before-submit both require it.
- A profile.md that is missing, has no front matter, or does not parse refuses SUBMITTED: the settings cannot be read.

Exit codes: 0 valid (or gate open), 1 contract violations (listed on stderr), 2 unreadable or not JSON.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from datetime import date
from pathlib import Path

SKILLS = Path(__file__).resolve().parents[2]
LINK_CHECK = SKILLS / "jobs-contract" / "scripts" / "link_check.py"
JOBS_COMMON = SKILLS / "jobs-contract" / "scripts" / "jobs_common.py"

RESULTS = ("SUBMITTED", "NEEDS_DATA", "NOT_POSSIBLE")
METHODS = ("no_login_form", "requires_account", "email", "linkedin", "captcha", "other")
SOURCES = ("contact.yaml", "application-data.yaml", "answers.md", "cv")
AUTO_APPLY = ("never", "ask", "try")
CONSULT = re.compile(r"^consult:[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")
ID_RE = re.compile(r"^JOB-\d{8}-[a-z0-9]+(?:-[a-z0-9]+)*$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FRONT = re.compile(r"\A\ufeff?---[ \t]*\n(.*?)\n---", re.S)
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
KIT_FILES = ("cv_ats.pdf", "cv.docx", "letter_ats.pdf", "letter.docx", "cover_letter.md", "answers.md")
GATE_STATUSES = ("ready", "applying")
RECORD_STATUSES = ("ready", "applying", "applied")
KIT_SHA = re.compile(r"^[0-9a-f]{64}$")
REVIEW_NAME = re.compile(r"review-(c?)(\d+)\.json\Z")
BOT_NAMES = frozenset({"jobs", "jobs-scout", "jobs-writer", "jobs-reviewer", "jobs-applier"})
NEEDS_REVIEW = ("SUBMITTED needs an approved review: openings/<ID>/review-N.json with verdict APPROVED, and a ready "
                "line in status.json")
REQUIRED = ("id", "result", "method", "filled_fields", "pending_questions", "screenshots", "reason")
CONTACT_PATTERNS = (
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"),
    re.compile(r"\+\d{1,3}[ -]?\d[\d -]{6,}\d"),
)


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


jc = load_module("jobs_common_for_check", JOBS_COMMON)


def read_object(path: Path):
    """The JSON object in path, or None when it is missing, unreadable or not an object."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def strict_day(value):
    """A YYYY-MM-DD date, or None."""
    if not isinstance(value, str) or not DAY_RE.match(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def approval(opening: Path, allowed=GATE_STATUSES):
    """(day, problem). The latest review-N.json must be APPROVED and the latest status.json line must be one of
    `allowed`; day is the day of the latest ready line. A later FIX, NOT_APPROVED, in_review or skipped closes it.
    The record check also accepts `applied`: the record writes it, so a second record must still pass."""
    # Every review file counts, whatever its numbering (review-2.json, review-c1.json): the newest one on disk is the
    # latest, so a later change review can never hide behind an older approval.
    reviews = []
    for path in opening.glob("review-*.json"):
        if REVIEW_NAME.match(path.name):
            reviews.append((path.stat().st_mtime_ns, path.name, path))
    if not reviews:
        return None, NEEDS_REVIEW
    _, name, path = max(reviews)
    verdict = (read_object(path) or {}).get("verdict")
    if verdict != "APPROVED":
        return None, f"SUBMITTED needs an approved review: the latest {name} is {verdict!r}, not APPROVED"
    history = (read_object(opening / "status.json") or {}).get("history")
    lines = [item for item in history if isinstance(item, dict)] if isinstance(history, list) else []
    last = lines[-1].get("status") if lines else None
    if last not in allowed:
        return None, f"the latest status.json line is {last!r}: SUBMITTED needs {' or '.join(allowed)}"
    ready = [item for item in lines if item.get("status") == "ready"]
    stamp = ready[-1].get("date") if ready else None
    day = strict_day(stamp[:10]) if isinstance(stamp, str) else None
    if day is None:
        return None, "status.json has no dated ready line: the approval day is unknown"
    return day, None


def kit_sha256(application: Path):
    """sha256 over the sorted (name, bytes) of the kit files present in application/; None without cv_ats.pdf."""
    if not (application / "cv_ats.pdf").is_file():
        return None
    digest = hashlib.sha256()
    for name in sorted(n for n in KIT_FILES if (application / n).is_file()):
        data = (application / name).read_bytes()
        digest.update(f"{name}\n{len(data)}\n".encode("utf-8"))
        digest.update(data)
    return digest.hexdigest()


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
        self.apply_url = ""

    def error(self, where: str, message: str) -> None:
        self.errors.append(f"{where}: {message}")

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
        self.check_id(data["id"])
        if data["result"] not in RESULTS:
            self.error("result", f"must be one of {', '.join(RESULTS)}")
        if data["method"] not in METHODS:
            self.error("method", f"must be one of {', '.join(METHODS)}")
        if not isinstance(data["reason"], str):
            self.error("reason", "must be a string (empty allowed for SUBMITTED)")
        fields = self.check_fields(data["filled_fields"])
        pending = self.check_pending(data["pending_questions"])
        shots = self.check_screenshots(data["screenshots"])
        for where, text in self.strings(data, ""):
            if any(p.search(text) for p in CONTACT_PATTERNS):
                self.error(where.lstrip(".") or "file", "contact data in a text value; keep values out of the file")
        if data["result"] == "SUBMITTED":
            self.check_submitted(data, fields, pending, shots)
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
        self.check_authority(screenshot=before_submit, at_gate=True)
        self.check_apply_url(self.apply_url)

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

    def check_submitted(self, data, fields, pending, shots) -> None:
        if data["method"] != "no_login_form":
            self.error("method", "SUBMITTED needs method no_login_form; every other class goes to a kit")
        if not fields:
            self.error("filled_fields", "SUBMITTED needs at least one filled field with its source")
        if pending:
            self.error("pending_questions", "SUBMITTED cannot carry open questions")
        confirmations = [s for s in shots if isinstance(s, str) and "confirm" in Path(s).name.lower()]
        if not confirmations:
            self.error("screenshots", "SUBMITTED needs a confirmation screenshot named confirmation.<ext>")
        elif not any(self.present(s) for s in confirmations):
            self.error("screenshots", "the confirmation screenshot does not exist")

    def check_authority(self, screenshot: bool, at_gate: bool) -> None:
        """The user's consent, the review approval and the profile settings that decide whether a submit may happen."""
        opening = self.base.parent
        settings, problem = profile_settings(self.base)
        if problem:
            self.error("profile", problem)
            return
        mode = settings.get("auto_apply")
        mode = "try" if mode is None else mode
        if mode not in AUTO_APPLY:
            self.error("auto_apply", "must be never, ask or try in profile.md")
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
        needs_screenshot = review_flag or mode == "ask"
        approved, problem = approval(opening, GATE_STATUSES if at_gate else RECORD_STATUSES)
        if problem:
            self.error("review", problem)
        path = self.base / "consent.json"
        if not path.is_file():
            self.error("consent", "SUBMITTED needs application/consent.json with the user's words for this opening")
            return
        consent = read_object(path)
        if consent is None:
            self.error("consent", "consent.json is not a JSON object")
            return
        for where, text in self.strings(consent, "consent"):
            if any(p.search(text) for p in CONTACT_PATTERNS):
                self.error(where, "contact data in consent.json; quote the user's words without addresses or numbers")
        if consent.get("opening_id") != opening.name:
            self.error("consent.opening_id", f"names {consent.get('opening_id')!r}, not this opening "
                                             f"{opening.name!r}: consent covers one opening")
        for key in ("by", "words"):
            if not isinstance(consent.get(key), str) or not consent[key].strip():
                self.error(f"consent.{key}", "must be the non-empty text the user wrote")
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

    def check_screenshot_approval(self, consent: dict, approved) -> None:
        shot = consent.get("screenshot_approval")
        if not isinstance(shot, dict):
            self.error("screenshot_approval", "review_before_submit is true: consent.json needs the user's approval of "
                                              "the pre-submit screenshot")
            return
        for key in ("by", "words"):
            if not isinstance(shot.get(key), str) or not shot[key].strip():
                self.error(f"screenshot_approval.{key}", "must be the non-empty text the user wrote")
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
        """An auto-submission is allowed only through a link the classifier does not call unverified."""
        if not apply_url:
            opening = self.base.parent / "opening.md"
            meta = jc.read_front_matter(opening) if opening.is_file() else {}
            apply_url = str(meta.get("apply_url") or "")
        if not apply_url:
            self.error("apply_url", "SUBMITTED needs the opening's apply_url (opening.md or --apply-url) to check it")
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

    def check_not_possible(self, data) -> None:
        if not isinstance(data["reason"], str) or not data["reason"].strip():
            self.error("reason", "NOT_POSSIBLE needs the reason")
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
    p.add_argument("--json", action="store_true", help="print {ok, result, errors} as JSON on stdout")
    p.add_argument("--apply-url", default="", help="the apply link (default: apply_url in ../opening.md)")
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
    if args.json:
        print(json.dumps({"ok": not checker.errors, "result": result, "errors": checker.errors}, indent=2))
    if checker.errors:
        for line in checker.errors:
            print(f"rule: {line}", file=sys.stderr)
        return 1
    if not args.json:
        print(f"valid: {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
