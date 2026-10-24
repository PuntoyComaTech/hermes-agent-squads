#!/usr/bin/env python3
"""Post one notice per sent application, with the CV that went attached (cron, no agent).

Every project of the manager is read, or only --project. An application counts as sent by the squad when the last line
of its `openings/<ID>/status.json` history is `applied` AND `application/submission.json` says `result: SUBMITTED`
(record_submission.py writes both after the click). An `applied` the owner reported ("I applied") has no submission
file and is never announced as a send. Each one is posted
once, oldest first, ONE per run: the delivery attaches every `MEDIA:` file after the text, so two notices in one
message would separate each CV from its opening. The cron runs every few minutes, so a busy day still clears fast.

The notice is read on a phone, in the profile's `user_language`:

    Applied: <role> - <company>
    <score>/100 · <work mode> · posted <date> · sent <date>
    <analysis.json brief: one line on what the job is>
    <apply link>
    MEDIA:<absolute path of application/cv_ats.pdf>

The `MEDIA:` line makes the delivery upload the PDF as a file, so the owner opens the CV that was sent from the chat
instead of reading a path on another computer. A missing CV file prints no `MEDIA:` line and says so.

State: `<manager home>/local/state/application_notices.json` (posted keys `<ID>@<applied date>`). Without a state
file (the first run after an install) only applications sent in the last 24 hours are posted; older ones are marked
as posted, so an install never floods the channel with history.

stdout is what the cron delivers (`notify: true`: the connected channel, else Bot Chat). Nothing to post prints
nothing. A hermes failure prints one line once an hour at most (the cron runs every 5 minutes) and exits 1. A state
file that does not parse is treated as a first run. Stdlib only: the cron runs it with the system python3.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import start_search as ss  # noqa: E402  - same folder on the manager: project resolution and profile.md reading

STATE = "application_notices"
KEEP = 500
FIRST_RUN_WINDOW = timedelta(hours=24)
ERROR_QUIET = timedelta(hours=1)
UNKNOWN = frozenset({"", "unknown", "tbd", "n/a", "none", "null"})
BRIEF_MAX = 160

TEXT = {
    "en": {"head": "Applied: {role} - {company}", "posted": "posted {d}", "sent": "sent {d}",
           "no_cv": "CV file missing: {path}",
           "modes": {"remote_global": "remote (global)", "remote_region": "remote (region)",
                     "remote_country": "remote", "hybrid": "hybrid", "onsite": "on site"}},
    "es": {"head": "Postulé: {role} - {company}", "posted": "publicada {d}", "sent": "enviada {d}",
           "no_cv": "No encuentro el CV: {path}",
           "modes": {"remote_global": "remoto (global)", "remote_region": "remoto (región)",
                     "remote_country": "remoto", "hybrid": "híbrido", "onsite": "presencial"}},
}


def read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def front_matter(path: Path) -> dict:
    try:
        return ss.read_profile(path) or {}
    except ss.RunError:
        return {}


def applied_line(opening: Path) -> dict | None:
    """The last status.json line when it is `applied`, else None."""
    history = read_json(opening / "status.json").get("history")
    lines = [h for h in history if isinstance(h, dict)] if isinstance(history, list) else []
    if not lines or lines[-1].get("status") != "applied":
        return None
    sent = read_json(opening / "application" / "submission.json").get("result") == "SUBMITTED"
    return lines[-1] if sent else None


def known(value) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in UNKNOWN else text


def day_of(text) -> str:
    return str(text or "")[:10]


def mode_text(raw, words: dict) -> str:
    value = known(raw)
    if not value or known(value.partition(":")[0]) == "":
        return ""
    base, _, where = value.partition(":")
    label = words.get(base, base.replace("_", " "))
    return f"{label} {where.upper()}".strip() if where else label


def brief_of(analysis: dict) -> str:
    """analysis.json `brief` (one line, user's language); else the first sentence of the company summary."""
    text = str(analysis.get("brief") or "").strip()
    if not text:
        summary = str((analysis.get("company") or {}).get("summary") or "").strip()
        text = re.split(r"(?<=[.!?])\s", summary, maxsplit=1)[0] if summary else ""
    text = " ".join(text.split())
    return text if len(text) <= BRIEF_MAX else text[:BRIEF_MAX - 1].rstrip() + "…"


def apply_link(opening_meta: dict, analysis: dict) -> str:
    resolved = analysis.get("link_resolution")
    resolved = resolved if isinstance(resolved, dict) else {}
    return str(resolved.get("apply_url") or opening_meta.get("apply_url") or opening_meta.get("url") or "").strip()


def notice(opening: Path, line: dict, lang: str) -> str:
    words = TEXT.get(lang, TEXT["en"])
    meta = front_matter(opening / "opening.md")
    analysis = read_json(opening / "analysis.json")
    fit = analysis.get("fit")
    fit = fit if isinstance(fit, dict) else {}
    role = str(meta.get("role") or opening.name).strip()
    company = str(meta.get("company") or "").strip()
    facts = []
    if isinstance(fit.get("score"), (int, float)):
        facts.append(f"{fit['score']:g}/100")
    mode = mode_text(meta.get("work_mode"), words["modes"])
    if mode:
        facts.append(mode)
    posted = day_of(known(meta.get("posted_at")) or known(analysis.get("posted_at")))
    if posted:
        facts.append(words["posted"].format(d=posted))
    facts.append(words["sent"].format(d=day_of(line.get("date"))))
    out = [words["head"].format(role=role, company=company).rstrip(" -"), " · ".join(facts)]
    brief = brief_of(analysis)
    if brief:
        out.append(brief)
    link = apply_link(meta, analysis)
    if link:
        out.append(link)
    cv = opening / "application" / "cv_ats.pdf"
    out.append(f"MEDIA:{cv}" if cv.is_file() else words["no_cv"].format(path=cv.name))
    return "\n".join(out)


def pending(folder: Path) -> list[tuple[str, Path, dict]]:
    """(key, opening dir, applied line) for every sent application of one project, oldest first."""
    rows = []
    for opening in sorted((folder / "openings").glob("*/")):
        line = applied_line(opening)
        if line:
            rows.append((f"{opening.name}@{day_of(line.get('date'))}", opening, line))
    return sorted(rows, key=lambda r: str(r[2].get("date") or ""))


def load_state(path: Path) -> list[str] | None:
    """Posted keys, or None when there is no state or it does not parse (both are a first run, never a replay)."""
    posted = read_json(path).get("posted") if path.is_file() else None
    return [str(k) for k in posted] if isinstance(posted, list) else None


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


def save_state(path: Path, keys: list[str]) -> None:
    write_json(path, {"posted": keys[-KEEP:]})


def report_error(path: Path, text: str, now: datetime) -> None:
    """Print the error unless the same text was printed within ERROR_QUIET (`<state>.error.json`)."""
    marker = path.with_name(path.stem + ".error.json")
    last = read_json(marker) if marker.is_file() else {}
    try:
        quiet = last.get("text") == text and now - datetime.fromisoformat(str(last.get("at"))) < ERROR_QUIET
    except ValueError:
        quiet = False
    if not quiet:
        print(text)
        write_json(marker, {"text": text, "at": now.isoformat(timespec="minutes")})


def recent(line: dict, now: datetime) -> bool:
    try:
        when = datetime.fromisoformat(str(line.get("date") or "")[:16])
    except ValueError:
        return False
    return now - when <= FIRST_RUN_WINDOW


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0],
                                epilog="Exit 0 read, 1 hermes failed.")
    p.add_argument("--project", help="project slug (default: every project of the manager)")
    p.add_argument("--manager", default="jobs", help="manager profile (default jobs)")
    p.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN", "hermes"), help="hermes executable")
    p.add_argument("--now", help="local time YYYY-MM-DDTHH:MM in place of the clock (tests and replays)")
    p.add_argument("--json", action="store_true", help="list what would be posted; state is not read or written")
    args = p.parse_args(argv)
    now = datetime.fromisoformat(args.now) if args.now else datetime.now()
    state = ss.profile_home(args.manager) / "local" / "state" / f"{STATE}.json"
    try:
        slugs = [args.project] if args.project else ss.project_list(args.hermes_bin, args.manager)
        folders = []
        for slug in slugs:
            try:
                folders.append(Path(ss.project_folder(args.hermes_bin, args.manager, slug)))
            except ss.SetupGap:
                continue
    except ss.RunError as exc:
        report_error(state, f"jobs-notices: {exc}", now)
        return 1
    rows = []
    for folder in folders:
        lang = ss.language_of(front_matter(folder / "profile.md"))
        rows += [(key, opening, line, lang) for key, opening, line in pending(folder)]
    rows.sort(key=lambda r: str(r[2].get("date") or ""))
    if args.json:
        print(json.dumps([{"key": k, "notice": notice(o, ln, lang)} for k, o, ln, lang in rows], indent=2,
                         ensure_ascii=False))
        return 0
    posted = load_state(state)
    if posted is None:  # first run: history is marked, only the last day is news
        posted = [k for k, _, ln, _ in rows if not recent(ln, now)]
    todo = [r for r in rows if r[0] not in posted]
    if todo:
        key, opening, line, lang = todo[0]
        print(notice(opening, line, lang))
        posted.append(key)
    save_state(state, posted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
