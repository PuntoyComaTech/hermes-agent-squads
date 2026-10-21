#!/usr/bin/env python3
"""Check one project's profile files (profile.md, achievements.yaml, contact.yaml, application-data.yaml).

Read-only and deterministic: the same files and --today give the same findings. Run it after the files are written
and before telling the user they are saved:

    python3 -I "$HERMES_HOME/skills/squad-jobs/jobs-contract/scripts/validate_profile.py" --project <folder> [--json]

Exit 0 no findings, 1 findings (file, key and message for each), 2 usage error. Contact values are never printed.
`--today YYYY-MM-DD` fixes "today" for replays and tests.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs_common as jc  # noqa: E402  - the one YAML reader, word matching, language names and experience years

PROFILE = "profile.md"
ACHIEVEMENTS = "achievements.yaml"
CONTACT = "contact.yaml"
APPLICATION = "application-data.yaml"
FRONT = re.compile(r"\ufeff?---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)

REQUIRED_PROFILE = ("search", "occupation", "target_roles", "seniority", "years_experience", "work_mode",
                    "search_keywords", "user_language", "timezone", "auto_apply", "apply_consent", "candidate",
                    "market", "eligibility")
SEARCH_VALUES = ("active", "paused")
AUTO_APPLY = ("never", "ask", "try")
APPLY_CONSENT = ("per_opening",)
STAGES = ("first_job", "junior", "mid", "senior", "lead", "career_change", "returning")
WORK_MODES = ("remote_global", "remote_region", "remote_country", "hybrid", "onsite")
ELIGIBILITY = ("citizen", "resident", "permit", "needs_sponsorship")
PROFICIENCY = ("led", "did", "participated", "familiar")
CEFR = ("A1", "A2", "B1", "B2", "C1", "C2")
WEIGHTS = ("technical", "experience", "behavioral", "career")
MODE_WORDS = {
    "hybrid": ("hybrid", "hibrido", "hybride"),
    "onsite": ("onsite", "on-site", "on site", "presencial", "in-office", "in office"),
    "remote": ("remote", "remoto", "remota", "teletrabajo"),
}
CONTACT_KEYS = ("name", "email", "phone", "location", "links")
APPLICATION_KEYS = ("work_authorization", "start_availability", "willing_to_relocate", "voluntary_questions",
                    "authorize_consents")
LANG_CODE = re.compile(r"^[a-z]{2}$")
COUNTRY = re.compile(r"^[A-Z]{2}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DATE = re.compile(r"^(\d{4})(?:-(\d{1,2}))?(?:-(\d{1,2}))?$")
YEARS_TOLERANCE = 0.5
BOOL_AS_TEXT = "reads as {value} in YAML: write the value in quotes (unquoted NO is false in YAML 1.1)"


class Report:
    def __init__(self):
        self.items = []

    def add(self, file, key, message):
        self.items.append({"file": file, "key": key, "message": message})


# --- field checks -----------------------------------------------------------------------------------------------

def need(report, file, mapping, field, where=""):
    """True when field is in mapping; otherwise one finding named where.field (or field alone at top level)."""
    if field in mapping:
        return True
    report.add(file, f"{where}.{field}" if where else field, "required key is missing")
    return False


def text_of(report, file, key, value):
    if value is None:
        return None
    if isinstance(value, bool):
        report.add(file, key, BOOL_AS_TEXT.format(value=str(value).lower()))
        return None
    if not isinstance(value, str) or not value.strip():
        report.add(file, key, "must be non-empty text")
        return None
    return value.strip()


def text_list(report, file, key, value):
    if value is None:
        return []
    if not isinstance(value, list):
        report.add(file, key, "must be a list")
        return []
    out = []
    for i, item in enumerate(value):
        word = text_of(report, file, f"{key}[{i}]", item)
        if word:
            out.append(word)
    return out


def number_of(report, file, key, value, low=0.0):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < low:
        report.add(file, key, f"must be a number, {low:g} or more")
        return None
    return float(value)


def flag_of(report, file, key, value):
    if value is None or isinstance(value, bool):
        return value
    report.add(file, key, "must be true or false")
    return None


def one_of(report, file, key, value, allowed):
    if value is None:
        return None
    if isinstance(value, bool):
        report.add(file, key, BOOL_AS_TEXT.format(value=str(value).lower()))
        return None
    if value not in allowed:
        report.add(file, key, f"must be one of {', '.join(str(a) for a in allowed)}; got {value!r}")
        return None
    return value


def country_of(report, file, key, value):
    if value is None:
        return None
    if isinstance(value, bool):
        report.add(file, key, BOOL_AS_TEXT.format(value=str(value).lower()))
        return None
    if not isinstance(value, str) or not COUNTRY.match(value):
        report.add(file, key, 'must be a two-letter country code in quotes, for example "PE"')
        return None
    return value


def list_of(report, file, key, value):
    if value is None:
        return []
    if not isinstance(value, list):
        report.add(file, key, "must be a list")
        return []
    return value


def ident_of(report, file, where, item, seen):
    value = item.get("id")
    if not isinstance(value, str) or not value.strip():
        report.add(file, f"{where}.id", "required key is missing")
        return None
    if value in seen:
        report.add(file, f"{where}.id", f"{value} is used more than once")
    seen.add(value)
    return value


def refs_of(report, file, where, values, valid):
    if values is None:
        return
    if not isinstance(values, list):
        report.add(file, where, "must be a list of achievement ids")
        return
    for ref in values:
        if ref not in valid:
            report.add(file, where, f"refers to {ref}, which is not in achievements.yaml")


def when_of(value):
    """A date as the first day of its month, the word 'current' for an open end, or None when unreadable."""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.replace(day=1)
    word = str(value if value is not None else "").strip().lower()
    if word in ("current", "present", "now", "actual"):
        return "current"
    match = DATE.match(word)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2) or 1), 1)
    except ValueError:
        return None


def zone_problem(name):
    """None when name is an IANA zone; otherwise why it is not."""
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        return "cannot be checked: this Python has no zoneinfo module (use Python 3.9 or newer)"
    try:
        ZoneInfo(name)
    except Exception:  # noqa: BLE001 - zoneinfo raises several types for an unknown key
        return f"{name!r} is not an IANA zone name, for example America/Lima"
    return None


# --- profile.md -------------------------------------------------------------------------------------------------

def check_profile(report, meta):
    for key in REQUIRED_PROFILE:
        if key not in meta:
            report.add(PROFILE, key, "required key is missing")
    one_of(report, PROFILE, "search", meta.get("search"), SEARCH_VALUES)
    text_of(report, PROFILE, "occupation", meta.get("occupation"))
    text_of(report, PROFILE, "seniority", meta.get("seniority"))
    roles = text_list(report, PROFILE, "target_roles", meta.get("target_roles"))
    if "target_roles" in meta and not roles:
        report.add(PROFILE, "target_roles", "needs at least one role")

    total = in_role = None
    if "years_experience" in meta:
        years = meta.get("years_experience")
        if not isinstance(years, dict):
            report.add(PROFILE, "years_experience", "must be a mapping with total and in_role")
        else:
            if need(report, PROFILE, years, "total", "years_experience"):
                total = number_of(report, PROFILE, "years_experience.total", years.get("total"))
            if need(report, PROFILE, years, "in_role", "years_experience"):
                in_role = number_of(report, PROFILE, "years_experience.in_role", years.get("in_role"))

    for mode in text_list(report, PROFILE, "work_mode", meta.get("work_mode")):
        if mode.split(":")[0] not in WORK_MODES:
            report.add(PROFILE, "work_mode", f"unknown work mode {mode!r}; use one of {', '.join(WORK_MODES)}")

    if "search_keywords" in meta:
        keywords = meta.get("search_keywords")
        if not isinstance(keywords, dict) or not keywords:
            report.add(PROFILE, "search_keywords", "must be a mapping of language code to a list of keywords")
        else:
            for lang, words in keywords.items():
                text_list(report, PROFILE, f"search_keywords.{lang}", words)

    one_of(report, PROFILE, "seniority_basis", meta.get("seniority_basis"), ("total", "role"))
    flag_of(report, PROFILE, "reject_on_skill_gaps", meta.get("reject_on_skill_gaps"))
    margin = meta.get("seniority_margin")
    if margin is not None and (isinstance(margin, bool) or not isinstance(margin, (int, float)) or not 0 <= margin <= 5):
        report.add(PROFILE, "seniority_margin", "must be a number of years from 0 to 5")
    flag_of(report, PROFILE, "reject_on_missing_credentials", meta.get("reject_on_missing_credentials"))
    flag_of(report, PROFILE, "plans_to_relocate", meta.get("plans_to_relocate"))

    lang = text_of(report, PROFILE, "user_language", meta.get("user_language"))
    if lang and not LANG_CODE.match(lang):
        report.add(PROFILE, "user_language", "must be an ISO 639-1 code: two lowercase letters, for example es")
    zone = text_of(report, PROFILE, "timezone", meta.get("timezone"))
    if zone:
        problem = zone_problem(zone)
        if problem:
            report.add(PROFILE, "timezone", problem)

    mode = one_of(report, PROFILE, "auto_apply", meta.get("auto_apply"), AUTO_APPLY)
    review = flag_of(report, PROFILE, "review_before_submit", meta.get("review_before_submit"))
    if mode == "ask" and review is not True:
        report.add(PROFILE, "review_before_submit",
                   "must be true when auto_apply is ask: the user checks the screenshot before the submit")
    one_of(report, PROFILE, "apply_consent", meta.get("apply_consent"), APPLY_CONSENT)

    for phrase in text_list(report, PROFILE, "deal_breakers", meta.get("deal_breakers")):
        for name, words in MODE_WORDS.items():
            if any(jc.word_in(word, phrase) for word in words):
                report.add(PROFILE, "deal_breakers",
                           f"{phrase!r} names a work mode ({name}); work modes belong in work_mode, and a deal "
                           "breaker must not discard a mode the user accepts")
                break

    if "candidate" in meta:
        candidate = meta.get("candidate")
        if not isinstance(candidate, dict):
            report.add(PROFILE, "candidate", "must be a mapping")
        else:
            if need(report, PROFILE, candidate, "stage", "candidate"):
                one_of(report, PROFILE, "candidate.stage", candidate.get("stage"), STAGES)
            age = candidate.get("age")
            if age is not None and (isinstance(age, bool) or not isinstance(age, int) or age < 0):
                report.add(PROFILE, "candidate.age", "must be a whole number or null")
            flag_of(report, PROFILE, "candidate.include_age_in_cv", candidate.get("include_age_in_cv"))
            flag_of(report, PROFILE, "candidate.photo_in_cv", candidate.get("photo_in_cv"))

    market_country = None
    if "market" in meta:
        market = meta.get("market")
        if not isinstance(market, dict):
            report.add(PROFILE, "market", "must be a mapping")
        elif need(report, PROFILE, market, "country", "market"):
            market_country = country_of(report, PROFILE, "market.country", market.get("country"))
            one_of(report, PROFILE, "market.cv_page_limit", market.get("cv_page_limit"), (1, 2))

    countries = []
    if "eligibility" in meta:
        rows = meta.get("eligibility")
        if not isinstance(rows, list) or not rows:
            report.add(PROFILE, "eligibility", "needs one row per country the user applies in")
        else:
            for i, row in enumerate(rows):
                where = f"eligibility[{i}]"
                if not isinstance(row, dict):
                    report.add(PROFILE, where, "must be a mapping with country and status")
                    continue
                code = None
                if need(report, PROFILE, row, "country", where):
                    code = country_of(report, PROFILE, f"{where}.country", row.get("country"))
                if need(report, PROFILE, row, "status", where):
                    one_of(report, PROFILE, f"{where}.status", row.get("status"), ELIGIBILITY)
                if code:
                    if code in countries:
                        report.add(PROFILE, f"{where}.country", f"{code} has a second row")
                    countries.append(code)
            if market_country and market_country not in countries:
                report.add(PROFILE, "eligibility", f"has no row for market.country {market_country}")

    scoring = meta.get("scoring")
    if isinstance(scoring, dict) and isinstance(scoring.get("weights"), dict):
        weights = scoring["weights"]
        values = []
        for key in WEIGHTS:
            value = number_of(report, PROFILE, f"scoring.weights.{key}", weights.get(key))
            if value is not None:
                values.append(value)
        for key in weights:
            if key not in WEIGHTS:
                report.add(PROFILE, f"scoring.weights.{key}", "is not a scoring dimension")
        if len(values) == len(WEIGHTS) and abs(sum(values) - 100) > 1e-9:
            report.add(PROFILE, "scoring.weights", f"sum to {sum(values):g}; they must sum to 100")

    for key in ("follow_up_days", "stale_days"):
        number_of(report, PROFILE, key, meta.get(key), low=1)
    if "updated" in meta and when_of(meta.get("updated")) is None:
        report.add(PROFILE, "updated", "must be a date, YYYY-MM-DD")
    return {"total": total, "in_role": in_role, "countries": countries, "auto_apply": mode}


# --- achievements.yaml ------------------------------------------------------------------------------------------

def check_experiences(report, data):
    """Dated experiences as spans, and the set of experience ids."""
    spans, ids = [], set()
    for i, exp in enumerate(list_of(report, ACHIEVEMENTS, "experiences", data.get("experiences"))):
        where = f"experiences[{i}]"
        if not isinstance(exp, dict):
            report.add(ACHIEVEMENTS, where, "must be a mapping")
            continue
        ident = ident_of(report, ACHIEVEMENTS, where, exp, ids)
        title = text_of(report, ACHIEVEMENTS, f"{where}.title", exp.get("title")) \
            if need(report, ACHIEVEMENTS, exp, "title", where) else None
        text_of(report, ACHIEVEMENTS, f"{where}.company", exp.get("company"))
        start, end = when_of(exp.get("from")), when_of(exp.get("to"))
        if not isinstance(start, date):
            report.add(ACHIEVEMENTS, f"{where}.from", "must be a date: YYYY-MM or YYYY-MM-DD")
        if end is None:
            report.add(ACHIEVEMENTS, f"{where}.to", "must be a date, or current")
        if isinstance(start, date) and isinstance(end, date) and end < start:
            report.add(ACHIEVEMENTS, f"{where}.to", "ends before it starts")
        elif isinstance(start, date) and end is not None and title:
            current = end == "current"
            spans.append({"id": ident, "title": title, "from": start.strftime("%Y-%m"), "current": current,
                          "to": "current" if current else end.strftime("%Y-%m")})
    return spans, ids


def check_achievements(report, data, today, prof):
    spans, exp_ids = check_experiences(report, data)
    if not spans:
        report.add(ACHIEVEMENTS, "experiences", "needs at least one dated experience with a title")

    ach_ids = set()
    for i, ach in enumerate(list_of(report, ACHIEVEMENTS, "achievements", data.get("achievements"))):
        where = f"achievements[{i}]"
        if not isinstance(ach, dict):
            report.add(ACHIEVEMENTS, where, "must be a mapping")
            continue
        ident_of(report, ACHIEVEMENTS, where, ach, ach_ids)
        ref = ach.get("experience")
        if ref is not None and ref not in exp_ids:
            report.add(ACHIEVEMENTS, f"{where}.experience", f"refers to {ref}, which is not in experiences")
        one_of(report, ACHIEVEMENTS, f"{where}.proficiency", ach.get("proficiency"), PROFICIENCY)
        if not (text_of(report, ACHIEVEMENTS, f"{where}.en", ach.get("en"))
                or text_of(report, ACHIEVEMENTS, f"{where}.es", ach.get("es"))):
            report.add(ACHIEVEMENTS, where, "needs the achievement text in en or es")
        if need(report, ACHIEVEMENTS, ach, "verified", where):
            flag_of(report, ACHIEVEMENTS, f"{where}.verified", ach.get("verified"))

    for i, skill in enumerate(list_of(report, ACHIEVEMENTS, "skills", data.get("skills"))):
        if isinstance(skill, dict):
            text_of(report, ACHIEVEMENTS, f"skills[{i}].name", skill.get("name"))
            refs_of(report, ACHIEVEMENTS, f"skills[{i}].achievements", skill.get("achievements"), ach_ids)

    for section, label in (("education", "degree"), ("certifications", "name")):
        seen = set()
        for i, row in enumerate(list_of(report, ACHIEVEMENTS, section, data.get(section))):
            where = f"{section}[{i}]"
            if not isinstance(row, dict):
                report.add(ACHIEVEMENTS, where, "must be a mapping")
                continue
            ident_of(report, ACHIEVEMENTS, where, row, seen)
            text_of(report, ACHIEVEMENTS, f"{where}.{label}", row.get(label))
            flag_of(report, ACHIEVEMENTS, f"{where}.verified", row.get("verified"))

    languages = list_of(report, ACHIEVEMENTS, "languages", data.get("languages"))
    if not languages:
        report.add(ACHIEVEMENTS, "languages", "needs at least one language with a CEFR level")
    seen_langs = set()
    for i, row in enumerate(languages):
        where = f"languages[{i}]"
        if not isinstance(row, dict):
            report.add(ACHIEVEMENTS, where, "must be a mapping")
            continue
        name = text_of(report, ACHIEVEMENTS, f"{where}.language", row.get("language"))
        one_of(report, ACHIEVEMENTS, f"{where}.level", row.get("level"), CEFR)
        if name:
            code = jc.normalize_language(name)
            if code in seen_langs:
                report.add(ACHIEVEMENTS, f"{where}.language", f"{name} is listed twice")
            seen_langs.add(code)
        flag_of(report, ACHIEVEMENTS, f"{where}.verified", row.get("verified"))

    for section in ("public_evidence", "star_stories"):
        for i, row in enumerate(list_of(report, ACHIEVEMENTS, section, data.get(section))):
            if isinstance(row, dict):
                refs_of(report, ACHIEVEMENTS, f"{section}[{i}].achievements", row.get("achievements"), ach_ids)

    if not spans:
        return {}
    years = jc.experience_years([{k: s[k] for k in ("title", "from", "to")} for s in spans], on=today)
    if prof is None:
        return {"total": years["total"], "by_title": years["by_title"]}
    if prof["total"] is not None and abs(prof["total"] - years["total"]) > YEARS_TOLERANCE:
        report.add(PROFILE, "years_experience.total",
                   f"is {prof['total']:g}, but the dates in achievements.yaml give {years['total']} years "
                   "(overlaps counted once): correct the profile or the dates")
    current = [jc.experience_years([{k: s[k] for k in ("title", "from", "to")}], on=today)["total"]
               for s in spans if s["current"]]
    if prof["in_role"] is not None and current:
        expected = max(current)
        if abs(prof["in_role"] - expected) > YEARS_TOLERANCE:
            report.add(PROFILE, "years_experience.in_role",
                       f"is {prof['in_role']:g}, but the current role (to: current) has run {expected} years by the "
                       "dates: in_role counts time in the current role only")
    return {"total": years["total"], "by_title": years["by_title"]}


# --- contact.yaml and application-data.yaml ---------------------------------------------------------------------

def check_contact(report, data):
    for key in CONTACT_KEYS:
        need(report, CONTACT, data, key)
    text_of(report, CONTACT, "name", data.get("name"))
    email = data.get("email")
    if email is not None and not (isinstance(email, str) and EMAIL.match(email)):
        report.add(CONTACT, "email", "does not look like an email address (the value is not shown)")
    if data.get("phone") not in (None, ""):  # optional: the user may keep it out of the chat and add it later
        text_of(report, CONTACT, "phone", data.get("phone"))
    text_of(report, CONTACT, "location", data.get("location"))
    if data.get("links") is not None and not isinstance(data.get("links"), list):
        report.add(CONTACT, "links", "must be a list")


def check_application(report, data, countries, required):
    if required:
        for key in APPLICATION_KEYS:
            need(report, APPLICATION, data, key)
    rows = data.get("work_authorization")
    if rows is not None:
        if not isinstance(rows, list) or not rows:
            report.add(APPLICATION, "work_authorization", "must be a list of {country, authorized, needs_sponsorship}")
            rows = []
        covered = set()
        for i, row in enumerate(rows):
            where = f"work_authorization[{i}]"
            if not isinstance(row, dict):
                report.add(APPLICATION, where, "must be a mapping")
                continue
            code = country_of(report, APPLICATION, f"{where}.country", row.get("country"))
            if code:
                covered.add(code)
            for field in ("authorized", "needs_sponsorship"):
                if need(report, APPLICATION, row, field, where):
                    flag_of(report, APPLICATION, f"{where}.{field}", row.get(field))
        for code in countries:
            if code not in covered:
                report.add(APPLICATION, "work_authorization", f"has no row for {code}, which eligibility lists")
    text_of(report, APPLICATION, "start_availability", data.get("start_availability"))
    text_of(report, APPLICATION, "voluntary_questions", data.get("voluntary_questions"))
    flag_of(report, APPLICATION, "willing_to_relocate", data.get("willing_to_relocate"))
    flag_of(report, APPLICATION, "authorize_consents", data.get("authorize_consents"))
    for i, row in enumerate(list_of(report, APPLICATION, "saved_answers", data.get("saved_answers"))):
        if not isinstance(row, dict) or "question" not in row or "answer" not in row:
            report.add(APPLICATION, f"saved_answers[{i}]", "must be a mapping with question and answer")


# --- loading and output -----------------------------------------------------------------------------------------

def load_file(report, folder, name, loaded, required=True):
    path = folder / name
    if not path.is_file():
        if required:
            report.add(name, "", "file is missing")
        return None
    loaded.append(name)
    text = path.read_text(encoding="utf-8", errors="ignore")
    source = text
    if name == PROFILE:
        match = FRONT.match(text)
        if not match:
            report.add(name, "", "has no YAML front matter between --- lines")
            return None
        source = match.group(1)
    try:
        data = jc.load_yaml(source)
    except Exception as exc:  # noqa: BLE001 - reported as a finding, never a traceback
        # Contact and application values never reach the output, not even inside a parser message.
        detail = "" if name in (CONTACT, APPLICATION) else f": {type(exc).__name__}: {str(exc)[:160]}"
        report.add(name, "", f"does not parse{detail}")
        return None
    if data is None:
        data = {}
    if not isinstance(data, dict):
        report.add(name, "", "must be a mapping at the top level")
        return None
    return data


def render(result):
    lines = [f"validate_profile: {result['project']}"]
    years = result["computed_years"]
    if years:
        by_title = "; ".join(f"{title} {value}" for title, value in sorted(years["by_title"].items()))
        lines.append(f"from achievements.yaml dates: total {years['total']} years"
                     + (f"; by title: {by_title}" if by_title else ""))
    if result["ok"]:
        lines.append("ok: no findings")
    else:
        lines.append(f"{len(result['findings'])} finding(s):")
        for item in result["findings"]:
            key = f": {item['key']}" if item["key"] else ""
            lines.append(f"- {item['file']}{key}: {item['message']}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="validate_profile.py", description=(__doc__ or "").split("\n\n")[0],
                                     epilog="Exit 0 no findings, 1 findings, 2 usage error.")
    parser.add_argument("--project", required=True, help="project folder holding the profile files")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--today", help="YYYY-MM-DD in place of today (replays and tests)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    folder = Path(args.project).expanduser()
    if not folder.is_dir():
        print(f"error: {folder} is not a folder", file=sys.stderr)
        return 2
    try:
        today = datetime.strptime(args.today, "%Y-%m-%d").date() if args.today else date.today()
    except ValueError:
        print(f"error: --today must be YYYY-MM-DD, got {args.today!r}", file=sys.stderr)
        return 2

    report, loaded = Report(), []
    meta = load_file(report, folder, PROFILE, loaded)
    prof = check_profile(report, meta) if meta is not None else None
    achievements = load_file(report, folder, ACHIEVEMENTS, loaded)
    computed = check_achievements(report, achievements, today, prof) if achievements is not None else {}
    contact = load_file(report, folder, CONTACT, loaded)
    if contact is not None:
        check_contact(report, contact)
    required = bool(prof and prof["auto_apply"] in ("try", "ask"))
    application = load_file(report, folder, APPLICATION, loaded, required=required)
    if application is not None:
        check_application(report, application, prof["countries"] if prof else [], required)

    result = {"ok": not report.items, "project": str(folder), "findings": report.items,
              "computed_years": computed, "checked": loaded}
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
