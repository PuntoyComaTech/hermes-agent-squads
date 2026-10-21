#!/usr/bin/env python3
"""File the search card of every project whose search is active, on the scheduled slot (cron, no agent).

Every project of the manager is checked, or only --project. A project is active while its `profile.md` says
`search: active`. `search: paused` stops it; quoted, uppercase and the Spanish `pausada` also pause. Any other value
is an error: that project does not search and the cron alert fires.

The cron runs every hour (squad.yaml), on the host clock. The gate reads the time in each project's `timezone` (IANA
name), so a project in another zone than the host still gets its card at its own 08:00. The slot is 08:00 on weekdays
in that zone; a run up to two hours after it belongs to the slot, so the hourly runs of the morning file one card. Any
other run, and any weekend run in the project's zone, files nothing. The card is filed with
`hermes -p <manager> kanban --board <board> create` and the key `jobs:search:<project>:<YYYY-MM-DD-HH>`, where HH is
the slot hour, not the hour the run started.

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
SLOTS = (8,)                    # slot hours in the project's zone; squad.yaml runs the gate every hour
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
    },
    "es": {
        "search_value": "profile.md: search debe ser active o paused, no {value!r}. La búsqueda no se ejecutó.",
        "zone": "profile.md: timezone {value!r} no es un nombre de zona IANA, por ejemplo America/Lima. "
                "La búsqueda no se ejecutó.",
        "front": "profile.md: el front matter no se puede leer ({why}). La búsqueda no se ejecutó.",
        "no_front": "profile.md: falta el front matter entre líneas ---. La búsqueda no se ejecutó.",
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


def profile_settings(profile_md: Path) -> dict:
    meta = read_profile(profile_md)
    if meta is None:
        return {"state": "missing", "zone": None, "language": "en"}
    lang = language_of(meta)
    return {"state": search_value(meta, lang), "zone": zone_of(meta, lang), "language": lang}


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


def parse_slots(text: str) -> tuple[int, ...]:
    try:
        hours = sorted({int(part) for part in text.split(",") if part.strip()})
    except ValueError:
        hours = []
    if not hours or any(h < 0 or h > 23 for h in hours):
        raise ValueError(f"--slots takes hours 0-23 separated by commas, got {text!r}")
    return tuple(hours)


def slot_at(now: datetime, slots=SLOTS) -> datetime | None:
    """The scheduled slot this run belongs to: the latest slot of today that started at most CATCH_UP ago."""
    if now.weekday() not in WEEKDAYS:
        return None
    for hour in sorted(slots, reverse=True):
        start = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if start <= now <= start + CATCH_UP:
            return start
    return None


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
              language: str) -> str:
    lines = ["Mode: SEARCH", f"Date: {now.strftime('%Y-%m-%d %H:%M')}. Slot: {slot_id(slot)}.",
             f"Project: {slug} ({folder})",
             f"User language: {language}. The search summary to the user is written in it."]
    if lane:
        lines.append(f"Analysis cards: model {lane[0]}" + (f", provider {lane[1]}" if lane[1] else "")
                     + " (review lane).")
    lines.append(f"File follow-up cards with project {slug} and workspace dir:{folder}.")
    return "\n".join(lines)


def file_card(bin_name: str, manager: str, args: argparse.Namespace, slug: str, folder: str, now: datetime,
              slot: datetime, lane: tuple[str, str] | None, language: str) -> dict:
    key = f"jobs:{STAGE}:{slug}:{slot_id(slot)}"
    argv = ["-p", manager, "kanban", "--board", args.board, "create", card_title(slot),
            "--assignee", args.scout, "--created-by", manager, "--skill", args.skill,
            "--project", slug, "--workspace", f"dir:{folder}", "--idempotency-key", key,
            "--body", card_body(slug, folder, now, slot, lane, language), "--json"]
    result = {"key": key, "title": card_title(slot), "assignee": args.scout, "board": args.board,
              "workspace": f"dir:{folder}", "command": [bin_name, *argv[:-1]]}
    if args.dry_run:
        return result
    stdout = hermes(bin_name, *argv)
    try:
        result["id"] = str((json.loads(stdout.strip()) or {}).get("id") or "")
    except ValueError:
        result["id"] = stdout.strip().split()[-1] if stdout.strip() else ""
    return result


def run_project(args: argparse.Namespace, slug: str, slots: tuple[int, ...], now_text: str | None) -> dict:
    folder = project_folder(args.hermes_bin, args.manager, slug)
    settings = profile_settings(Path(folder) / "profile.md")
    base = {"project": slug}
    if settings["state"] == "missing":
        return {**base, "filed": False, "reason": "no profile.md"}
    if settings["state"] == "paused":
        return {**base, "filed": False, "reason": "paused"}
    now = clock(settings["zone"], now_text)
    slot = slot_at(now, slots)
    if slot is None:
        return {**base, "filed": False, "reason": "outside schedule hours", "now": now.strftime("%Y-%m-%d %H:%M")}
    card = file_card(args.hermes_bin, args.manager, args, slug, folder, now, slot,
                     review_lane_model(args, args.manager), settings["language"])
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
    parser.add_argument("--slots", default=",".join(str(h) for h in SLOTS),
                        help="scheduled hours, comma separated (default: the squad.yaml schedule)")
    parser.add_argument("--now", help="run time: 'YYYY-MM-DD HH:MM' in the project zone, or an ISO time with an "
                                      "offset (tests and backfills)")
    parser.add_argument("--dry-run", action="store_true", help="print the card, create nothing")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        slots = parse_slots(args.slots)
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
