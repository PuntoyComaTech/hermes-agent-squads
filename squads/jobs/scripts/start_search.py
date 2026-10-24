#!/usr/bin/env python3
"""File the search card of every project whose search is active, on the scheduled slot (cron, no agent).

Every project of the manager is checked, or only --project. A project is active while its `profile.md` says
`search: active`. `search: paused` stops it; quoted, uppercase and the Spanish `pausada` also pause. Any other value
is an error: that project does not search and the cron alert fires.

The cron runs every hour (squad.yaml), on the host clock. The gate reads the time in each project's `timezone` (IANA
name), so a project in another zone than the host still gets its card at its own hour. The slots are the project's
`search_times` (local "HH:MM", default one check at 12:00) on weekdays in that zone; a run up to two hours after a slot
belongs to it, so the hourly runs file one card per slot. Any other run, and any weekend run, files nothing.

Freshness: a posting loses most of its chance within a day, so each card searches only what appeared since the previous
slot (the previous weekday's last slot for the first check of a day; Monday reaches back over the weekend, at most
72 h). The card names that window; the scout passes it to `portals.py search --max-age-hours` and `prefilter --since`.
The card is filed with `hermes -p <manager> kanban --board <board> create` and the key
`jobs:search:<project>:<YYYY-MM-DD-HH>`, where HH is the slot hour, not the hour the run started.

stdout is what the cron delivers. A filed card, a paused search, a missing project and a missing `profile.md` print
nothing and exit 0 (`squadctl doctor` reports the setup gaps). A hermes failure, a broken `profile.md` or an unknown
search value prints the error and exits 1.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import math
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _base in (HERE.parent / "skills" / "jobs-contract" / "scripts",                  # repository layout
              HERE.parent / "skills" / "squad-jobs" / "jobs-contract" / "scripts"):  # installed profile
    if (_base / "jobs_common.py").is_file():
        sys.path.insert(0, str(_base))
        break
else:
    sys.exit("jobs-search: jobs_common.py not found beside the squad skills: reinstall the jobs squad")
import jobs_common as jc  # noqa: E402  - the one YAML reader for profile.md, used by every squad script

STAGE = "search"
SLOTS = ((12, 0),)              # default slot (hour, minute) in the project's zone: one check at midday
MAX_SLOTS = 4                   # search_times holds at most this many checks a day
MAX_WINDOW = timedelta(hours=72)  # Monday's first check reaches back over the weekend, never further
CATCH_UP = timedelta(hours=2)   # a run this long after a slot still belongs to it (Hermes replays missed runs)
WEEKDAYS = (0, 1, 2, 3, 4)      # Monday to Friday in the project's zone, as datetime.weekday()
PAUSED = frozenset({"paused", "pausada", "pausado", "pause", "pausa"})
ACTIVE = frozenset({"active", "activa", "activo"})
FRONT = re.compile(r"\ufeff?---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
NO_PROJECT = ("no project on the jobs manager: Sessions, pick jobs, \"+\" "
              "(or ask the manager to start a search)")

# Text the user reads, in the profile's user_language (ISO 639-1); English for any other language.
MESSAGES = {
    "en": {
        "search_value": "profile.md: search must be active or paused, got {value!r}. The search did not run.",
        "zone": "profile.md: timezone {value!r} is not an IANA zone name, for example America/Lima. "
                "The search did not run.",
        "front": "profile.md: the front matter does not parse ({why}). The search did not run.",
        "no_front": "profile.md: no front matter between --- lines. The search did not run.",
        "times": "profile.md: search_times must list 1 to 4 distinct local times like \"12:00\", got {value!r}. "
                 "The search did not run.",
    },
    "es": {
        "search_value": "profile.md: search debe ser active o paused, no {value!r}. La búsqueda no se ejecutó.",
        "zone": "profile.md: timezone {value!r} no es un nombre de zona IANA, por ejemplo America/Lima. "
                "La búsqueda no se ejecutó.",
        "front": "profile.md: el front matter no se puede leer ({why}). La búsqueda no se ejecutó.",
        "no_front": "profile.md: falta el front matter entre líneas ---. La búsqueda no se ejecutó.",
        "times": "profile.md: search_times debe listar de 1 a 4 horas locales distintas como \"12:00\", no {value!r}. "
                 "La búsqueda no se ejecutó.",
    },
}


class RunError(Exception):
    """hermes itself failed, or a file the squad depends on is broken: the cron error alert must fire."""


class ProfileError(RunError):
    """profile.md cannot be read as settings; the message is already in the user's language when known."""


class SetupGap(Exception):
    """The search is not set up yet (no folder for the project): silent exit 0, reason in --json."""


def hermes_root() -> Path:
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    return home.parent.parent if home.parent.name == "profiles" else home


def profile_home(manager: str) -> Path:
    home = Path(os.environ.get("HERMES_HOME") or hermes_root() / "profiles" / manager)
    return home if home.name == manager else hermes_root() / "profiles" / manager


def hermes(bin_name: str, *args: str) -> str:
    """stdout of one hermes call. A missing binary or a non-zero exit is a RunError, never an empty answer."""
    env = {**os.environ, "HERMES_HOME": str(hermes_root())}
    try:
        done = subprocess.run([bin_name, *args], capture_output=True, text=True, timeout=180, env=env,
                              stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise RunError(f"hermes not found on PATH (tried {bin_name})") from None
    except subprocess.SubprocessError as exc:
        raise RunError(f"hermes {' '.join(args)} failed: {exc}") from None
    if done.returncode != 0:
        raise RunError(f"hermes {' '.join(args)} failed ({done.returncode}): "
                       f"{(done.stderr or done.stdout).strip()[:300]}")
    return done.stdout


# --- project resolution -----------------------------------------------------------------------------------------

def project_slugs(listing: str) -> list[tuple[str, bool]]:
    """Rows of `hermes project list`: `<*| > <slug> <name> [N folder(s)]` -> [(slug, active)]."""
    rows = []
    for line in listing.splitlines():
        stripped = line.strip()
        if not stripped or "folder(s)]" not in stripped:
            continue
        tokens = stripped.split()
        active = tokens[0] == "*"
        slug = tokens[1] if active else tokens[0]
        if re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
            rows.append((slug, active))
    return rows


def project_path(show: str) -> str | None:
    """`hermes project show <slug>`: the `primary:` line, else the `*` folder line."""
    primary = re.search(r"^\s*primary:\s*(.+?)\s*$", show, re.M)
    if primary:
        return primary.group(1)
    starred = re.search(r"^\s*\*\s+(\S.*?)\s*$", show, re.M)
    return starred.group(1) if starred else None


def project_folder(bin_name: str, manager: str, slug: str) -> str:
    path = project_path(hermes(bin_name, "-p", manager, "project", "show", slug))
    if not path:
        raise SetupGap(f"project {slug}: no folder found (run `hermes -p {manager} project show {slug}`)")
    folder = Path(path).expanduser()
    if not folder.is_dir():
        raise SetupGap(f"project {slug}: {folder} is not a directory")
    return str(folder)


def project_list(bin_name: str, manager: str) -> list[str]:
    """Every project slug of the manager, the Desktop-selected one first. An empty list is a setup gap."""
    rows = project_slugs(hermes(bin_name, "-p", manager, "project", "list"))
    return [slug for slug, _ in sorted(rows, key=lambda row: (not row[1], row[0]))]


def resolve_project(bin_name: str, manager: str, explicit: str | None) -> tuple[str, str]:
    """(slug, folder) of one project: --project, else the manager's selected project. Used by followup_gate.

    A project that is not on the manager is a setup gap (silent exit 0), not a hermes failure."""
    rows = project_slugs(hermes(bin_name, "-p", manager, "project", "list"))
    if explicit:
        if explicit not in {slug for slug, _ in rows}:
            raise SetupGap(f"project {explicit} is not on the jobs manager")
        return explicit, project_folder(bin_name, manager, explicit)
    if not rows:
        raise SetupGap(NO_PROJECT)
    slug = next((s for s, active in rows if active), rows[0][0])
    return slug, project_folder(bin_name, manager, slug)


# --- profile settings -------------------------------------------------------------------------------------------

def read_profile(profile_md: Path) -> dict | None:
    """The front matter of profile.md as a mapping; None when the file is missing. Never falls back silently."""
    if not profile_md.is_file():
        return None
    text = profile_md.read_text(encoding="utf-8", errors="ignore")
    match = FRONT.match(text)
    if not match:
        raise ProfileError(MESSAGES["en"]["no_front"])
    try:
        meta = jc.load_yaml(match.group(1)) or {}
    except Exception as exc:  # noqa: BLE001 - any parser error is reported to the user
        raise ProfileError(MESSAGES["en"]["front"].format(why=type(exc).__name__)) from None
    if not isinstance(meta, dict):
        raise ProfileError(MESSAGES["en"]["front"].format(why="not a mapping"))
    return meta


def language_of(meta: dict) -> str:
    code = str(meta.get("user_language") or "en").strip().lower()[:2]
    return code if code in MESSAGES else "en"


def search_value(meta: dict, lang: str) -> str:
    """`active` or `paused`. A missing key is active; any other value is an error the user reads."""
    if "search" not in meta:
        return "active"
    raw = meta.get("search")
    token = jc.ascii_fold(str(raw)).strip().strip("'\"").strip().lower()
    if token in PAUSED:
        return "paused"
    if token in ACTIVE:
        return "active"
    raise ProfileError(MESSAGES[lang]["search_value"].format(value=str(raw)))


def zone_of(meta: dict, lang: str):
    """The project's zone, or None (the host clock) when profile.md has no timezone."""
    name = meta.get("timezone")
    if name in (None, ""):
        return None
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        raise ProfileError("profile.md: timezone needs Python 3.9 or newer (zoneinfo). The search did not run.") \
            from None
    try:
        return ZoneInfo(str(name))
    except Exception:  # noqa: BLE001 - zoneinfo raises several types for an unknown key
        raise ProfileError(MESSAGES[lang]["zone"].format(value=str(name))) from None


def times_of(meta: dict, lang: str) -> tuple[tuple[int, int], ...] | None:
    """The project's check times as (hour, minute), from `search_times`; None when the profile sets none."""
    raw = meta.get("search_times")
    if raw in (None, "", []):
        return None
    try:
        return parse_slots(",".join(str(item) for item in raw) if isinstance(raw, list) else str(raw))
    except ValueError:
        raise ProfileError(MESSAGES[lang]["times"].format(value=raw)) from None


def profile_settings(profile_md: Path) -> dict:
    meta = read_profile(profile_md)
    if meta is None:
        return {"state": "missing", "zone": None, "language": "en", "slots": None}
    lang = language_of(meta)
    return {"state": search_value(meta, lang), "zone": zone_of(meta, lang), "language": lang,
            "slots": times_of(meta, lang)}


def search_state(profile_md: Path) -> str:
    """`active`, `paused` or `missing`. followup_gate reads it too: one pause rule for both cron gates."""
    return profile_settings(profile_md)["state"]


# --- clock and slot ---------------------------------------------------------------------------------------------

def parse_when(text: str, zone) -> datetime:
    """--now: 'YYYY-MM-DD HH:MM' is wall-clock time in the project zone; an ISO time with an offset is an instant,
    converted to the project zone. Returns a naive wall-clock datetime."""
    try:
        return datetime.strptime(text, "%Y-%m-%d %H:%M")
    except ValueError:
        pass
    try:
        instant = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"--now must be 'YYYY-MM-DD HH:MM' or an ISO time with an offset, got {text!r}") from None
    if instant.tzinfo is None:
        return instant
    local = instant.astimezone(zone) if zone else instant.astimezone()
    return local.replace(tzinfo=None)


def clock(zone, now_text: str | None) -> datetime:
    if now_text is not None:
        return parse_when(now_text, zone)
    return datetime.now(zone).replace(tzinfo=None) if zone else datetime.now().replace(microsecond=0)


TIME_RE = re.compile(r"\A(\d{1,2})(?::(\d{2}))?\Z")


def parse_slots(text: str) -> tuple[tuple[int, int], ...]:
    """Local check times: "12:00", "9:30" or a bare hour "12", comma separated. One per hour at most (the card key
    carries the hour), 1 to MAX_SLOTS of them."""
    out = set()
    for part in (p.strip().strip("'\"") for p in text.split(",")):
        match = TIME_RE.match(part) if part else None
        if not match:
            raise ValueError(f"check times are local times like 12:00 separated by commas, got {text!r}")
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        if hour > 23 or minute > 59:
            raise ValueError(f"check times are local times like 12:00 separated by commas, got {text!r}")
        out.add((hour, minute))
    if not out or len(out) > MAX_SLOTS or len({h for h, _ in out}) != len(out):
        raise ValueError(f"1 to {MAX_SLOTS} check times, at most one per hour, got {text!r}")
    return tuple(sorted(out))


def slot_at(now: datetime, slots=SLOTS) -> datetime | None:
    """The scheduled slot this run belongs to: the latest slot of today that started at most CATCH_UP ago."""
    if now.weekday() not in WEEKDAYS:
        return None
    for hour, minute in sorted(slots, reverse=True):
        start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if start <= now <= start + CATCH_UP:
            return start
    return None


def previous_slot(slot: datetime, slots=SLOTS) -> datetime:
    """The check before this one: an earlier slot today, else the last slot of the previous weekday."""
    earlier = [slot.replace(hour=h, minute=m) for h, m in slots if (h, m) < (slot.hour, slot.minute)]
    if earlier:
        return max(earlier)
    day = slot
    for _ in range(7):
        day -= timedelta(days=1)
        if day.weekday() in WEEKDAYS:
            h, m = max(slots)
            return day.replace(hour=h, minute=m)
    return slot - timedelta(days=1)


def window_of(slot: datetime, slots=SLOTS) -> tuple[datetime, int]:
    """(since, hours): the postings this check reads, since the previous check, capped at MAX_WINDOW."""
    since = max(previous_slot(slot, slots), slot - MAX_WINDOW)
    return since, max(1, math.ceil((slot - since).total_seconds() / 3600))


def slot_id(slot: datetime) -> str:
    return slot.strftime("%Y-%m-%d-%H")


# --- lane model -------------------------------------------------------------------------------------------------

def installed_candidates(args: argparse.Namespace, manager: str) -> list[Path]:
    out = []
    if args.installed:
        out.append(Path(args.installed).expanduser())
    own = profile_home(manager) / "local" / "installed.yaml"
    out.append(own)
    for sibling in sorted((hermes_root() / "profiles").glob("*/local/installed.yaml")):
        if sibling != own:
            out.append(sibling)
    return out


def review_lane_model(args: argparse.Namespace, manager: str) -> tuple[str, str] | None:
    """(model, provider) recorded for the review lane, else for jobs-reviewer, in the builder's installed.yaml."""
    for path in installed_candidates(args, manager):
        if not path.is_file():
            continue
        try:
            data = jc.load_yaml(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001 - another candidate may still answer
            continue
        if not isinstance(data, dict):
            continue
        lanes = data.get("lanes") or {}
        review = lanes.get("review")
        if isinstance(review, dict) and review.get("model"):
            return str(review["model"]), str(review.get("provider") or "")
        bots = data.get("bots") or {}
        if isinstance(bots, dict):
            for name, entry in bots.items():
                if isinstance(entry, dict) and name.endswith("-reviewer") and entry.get("model"):
                    return str(entry["model"]), str(entry.get("provider") or "")
    return None


# --- card -------------------------------------------------------------------------------------------------------

def card_title(slot: datetime) -> str:
    return f"Search {slot.strftime('%Y-%m-%d %H:00')}"


def card_body(slug: str, folder: str, now: datetime, slot: datetime, lane: tuple[str, str] | None,
              language: str, slots=SLOTS) -> str:
    since, hours = window_of(slot, slots)
    lines = ["Mode: SEARCH", f"Date: {now.strftime('%Y-%m-%d %H:%M')}. Slot: {slot_id(slot)}.",
             f"Window: postings since {since.strftime('%Y-%m-%d %H:%M')} ({hours} h). Search with "
             f"--max-age-hours {hours}; prefilter with --since {since.strftime('%Y-%m-%d')}.",
             f"Project: {slug} ({folder})",
             f"User language: {language}. Anything the user reads is written in it."]
    if lane:
        lines.append(f"Analysis cards: model {lane[0]}" + (f", provider {lane[1]}" if lane[1] else "")
                     + " (review lane).")
    lines.append(f"File follow-up cards with project {slug} and workspace dir:{folder}.")
    return "\n".join(lines)


def file_card(bin_name: str, manager: str, args: argparse.Namespace, slug: str, folder: str, now: datetime,
              slot: datetime, lane: tuple[str, str] | None, language: str, slots=SLOTS) -> dict:
    key = f"jobs:{STAGE}:{slug}:{slot_id(slot)}"
    argv = ["-p", manager, "kanban", "--board", args.board, "create", card_title(slot),
            "--assignee", args.scout, "--created-by", manager, "--skill", args.skill,
            "--project", slug, "--workspace", f"dir:{folder}", "--idempotency-key", key,
            "--body", card_body(slug, folder, now, slot, lane, language, slots), "--json"]
    since, hours = window_of(slot, slots)
    result = {"key": key, "title": card_title(slot), "assignee": args.scout, "board": args.board,
              "since": since.strftime("%Y-%m-%d %H:%M"), "window_hours": hours,
              "workspace": f"dir:{folder}", "command": [bin_name, *argv[:-1]]}
    if args.dry_run:
        return result
    stdout = hermes(bin_name, *argv)
    try:
        result["id"] = str((json.loads(stdout.strip()) or {}).get("id") or "")
    except ValueError:
        result["id"] = stdout.strip().split()[-1] if stdout.strip() else ""
    return result


def run_project(args: argparse.Namespace, slug: str, override, now_text: str | None) -> dict:
    folder = project_folder(args.hermes_bin, args.manager, slug)
    settings = profile_settings(Path(folder) / "profile.md")
    base = {"project": slug}
    if settings["state"] == "missing":
        return {**base, "filed": False, "reason": "no profile.md"}
    if settings["state"] == "paused":
        return {**base, "filed": False, "reason": "paused"}
    now = clock(settings["zone"], now_text)
    slots = override or settings["slots"] or SLOTS  # --slots, else the profile's search_times, else midday
    slot = slot_at(now, slots)
    if slot is None:
        return {**base, "filed": False, "reason": "outside schedule hours", "now": now.strftime("%Y-%m-%d %H:%M")}
    card = file_card(args.hermes_bin, args.manager, args, slug, folder, now, slot,
                     review_lane_model(args, args.manager), settings["language"], slots)
    return {**base, "filed": True, "slot": slot_id(slot), **card}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="start_search.py", description=(__doc__ or "").split("\n\n")[0],
        epilog="Exit 0 decided, 1 hermes or profile.md failed, 2 usage error.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", help="project slug (default: every project of the manager)")
    parser.add_argument("--board", default="jobs", help="kanban board slug (default jobs)")
    parser.add_argument("--manager", default="jobs", help="manager profile that files the card (default jobs)")
    parser.add_argument("--scout", default="jobs-scout", help="assignee of the search card (default jobs-scout)")
    parser.add_argument("--skill", default="finding-jobs", help="skill the card loads (default finding-jobs)")
    parser.add_argument("--installed", type=Path, help="installed.yaml holding the lane models")
    parser.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN", "hermes"), help="hermes executable")
    parser.add_argument("--slots", help="check times like 09:00,15:00, overriding every profile's search_times "
                                        "(default: each profile's search_times, else 12:00)")
    parser.add_argument("--now", help="run time: 'YYYY-MM-DD HH:MM' in the project zone, or an ISO time with an "
                                      "offset (tests and backfills)")
    parser.add_argument("--dry-run", action="store_true", help="print the card, create nothing")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        slots = parse_slots(args.slots) if args.slots else None
        if args.now is not None:
            parse_when(args.now, None)  # syntax only; the zone is applied per project
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        known = project_list(args.hermes_bin, args.manager)
    except RunError as exc:
        print(f"jobs-search: {exc}")
        return 1
    results, failed = [], False
    if args.project and args.project not in known:
        slugs = []
        results.append({"project": args.project, "filed": False, "reason": "no project",
                        "message": f"project {args.project} is not on the jobs manager"})
    else:
        slugs = [args.project] if args.project else known
        if not slugs:
            results.append({"filed": False, "reason": "no project", "message": NO_PROJECT})
    for slug in slugs:
        try:
            results.append(run_project(args, slug, slots, args.now))
        except SetupGap as exc:
            results.append({"project": slug, "filed": False, "reason": "no folder", "message": str(exc)})
        except RunError as exc:
            failed = True
            print(f"jobs-search: {exc}")
            results.append({"project": slug, "filed": False, "reason": "error", "message": str(exc)})
    if args.json:
        print(json.dumps({"results": results}, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
