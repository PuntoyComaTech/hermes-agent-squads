#!/usr/bin/env python3
"""File one search card per slot on the jobs board, unless the search is paused (cron --no-agent).

Usage:
  start_search.py [--project SLUG] [--board jobs] [--lead jobs] [--installed FILE] [--now "YYYY-MM-DD HH:MM"]

Reads `$HERMES_HOME` for the Hermes root, asks the lead profile for its project when --project is absent, pauses
when `<project>/profile.md` says `search: paused`, resolves the review-lane model from the builder's
`local/installed.yaml` and files the card through `hermes -p <lead> kanban create` with a per-slot idempotency key.

Silent when a card was filed (or already existed): the cron job delivers stdout, and empty stdout is nothing to
say. A line is printed when the search cannot run (missing project, missing profile.md). Exit 0 when the run was
decided, 1 when hermes failed, 2 usage error. No network beyond the local hermes CLI.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    import hermes_yaml as yaml
except ImportError:  # outside the Hermes runtime
    try:
        import yaml
    except ImportError:
        yaml = None

STAGE = "search"


class RunError(Exception):
    pass


def hermes_root() -> Path:
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    return home.parent.parent if home.parent.name == "profiles" else home


def profile_home(lead: str) -> Path:
    home = Path(os.environ.get("HERMES_HOME") or hermes_root() / "profiles" / lead)
    return home if home.name == lead else hermes_root() / "profiles" / lead


def hermes(bin_name: str, *args: str, check: bool = True) -> str:
    env = {**os.environ, "HERMES_HOME": str(hermes_root())}
    try:
        done = subprocess.run([bin_name, *args], capture_output=True, text=True, timeout=180, env=env,
                              stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise RunError(f"hermes not found on PATH (tried {bin_name})") from None
    except subprocess.SubprocessError as exc:
        raise RunError(f"hermes {' '.join(args)} failed: {exc}") from None
    if check and done.returncode != 0:
        raise RunError(f"hermes {' '.join(args)} failed ({done.returncode}): {(done.stderr or done.stdout).strip()[:300]}")
    return done.stdout


# --- project resolution ----------------------------------------------------------------------------------------

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


def resolve_project(bin_name: str, lead: str, explicit: str | None) -> tuple[str, str]:
    if explicit:
        slug = explicit
        show = hermes(bin_name, "-p", lead, "project", "show", slug, check=False)
    else:
        rows = project_slugs(hermes(bin_name, "-p", lead, "project", "list", check=False))
        if not rows:
            raise RunError("no project on the jobs lead: create it with "
                           "`squadctl project add jobs <name> <path>`")
        slug = next((s for s, active in rows if active), rows[0][0])
        show = hermes(bin_name, "-p", lead, "project", "show", slug, check=False)
    path = project_path(show)
    if not path:
        raise RunError(f"project {slug}: no folder found (run `hermes -p {lead} project show {slug}`)")
    folder = Path(path).expanduser()
    if not folder.is_dir():
        raise RunError(f"project {slug}: {folder} is not a directory")
    return slug, str(folder)


# --- search state, lane model ----------------------------------------------------------------------------------

def search_state(profile_md: Path) -> str:
    """`active`, `paused` or `missing`, from the front matter of profile.md."""
    if not profile_md.is_file():
        return "missing"
    text = profile_md.read_text(encoding="utf-8", errors="ignore")
    meta = {}
    match = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    if match and yaml is not None:
        try:
            loaded = yaml.safe_load(match.group(1))
            meta = loaded if isinstance(loaded, dict) else {}
        except Exception:  # noqa: BLE001 - a broken profile must not stop the gate
            meta = {}
    elif match:
        hit = re.search(r"^search:\s*(\S+)", match.group(1), re.M)
        meta = {"search": hit.group(1)} if hit else {}
    return "paused" if str(meta.get("search", "active")).strip().lower() == "paused" else "active"


def installed_candidates(args: argparse.Namespace, lead: str) -> list[Path]:
    out = []
    if args.installed:
        out.append(Path(args.installed).expanduser())
    own = profile_home(lead) / "local" / "installed.yaml"
    out.append(own)
    for sibling in sorted((hermes_root() / "profiles").glob("*/local/installed.yaml")):
        if sibling != own:
            out.append(sibling)
    return out


def review_lane_model(args: argparse.Namespace, lead: str) -> tuple[str, str] | None:
    """(model, provider) recorded for the review lane, else for jobs-reviewer, in the builder's installed.yaml."""
    if yaml is None:
        return None
    for path in installed_candidates(args, lead):
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:  # noqa: BLE001
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

def slot_id(now: datetime) -> str:
    return now.strftime("%Y-%m-%d-%H")


def card_title(now: datetime) -> str:
    return f"Search {now.strftime('%Y-%m-%d %H:00')}"


def card_body(slug: str, folder: str, now: datetime, lane: tuple[str, str] | None) -> str:
    lines = [f"Mode: {'SEARCH'}.", f"Date: {now.strftime('%Y-%m-%d %H:%M')}. Slot: {slot_id(now)}.",
             f"Project: {slug} ({folder})"]
    if lane:
        lines.append(f"Analysis cards: pin --model {lane[0]} --provider {lane[1]} (review lane).")
    else:
        lines.append("Analysis cards: no review-lane model on record; file them without --model.")
    lines.append(f"File follow-up cards with project {slug} and workspace dir:{folder}.")
    return "\n".join(lines)


def file_card(bin_name: str, lead: str, args: argparse.Namespace, slug: str, folder: str,
              now: datetime, lane: tuple[str, str] | None) -> dict:
    key = f"jobs:{STAGE}:{slug}:{slot_id(now)}"
    argv = ["-p", lead, "kanban", "--board", args.board, "create", card_title(now),
            "--assignee", args.scout, "--created-by", lead, "--skill", args.skill,
            "--project", slug, "--workspace", f"dir:{folder}", "--idempotency-key", key,
            "--body", card_body(slug, folder, now, lane), "--json"]
    result = {"key": key, "title": card_title(now), "assignee": args.scout, "board": args.board, "project": slug,
              "workspace": f"dir:{folder}", "command": [bin_name, *argv[:-1]]}
    if args.dry_run:
        return result
    stdout = hermes(bin_name, *argv)
    try:
        result["id"] = str((json.loads(stdout.strip()) or {}).get("id") or "")
    except ValueError:
        result["id"] = stdout.strip().split()[-1] if stdout.strip() else ""
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="start_search.py", description=(__doc__ or "").split("\n\n")[0],
        epilog="Exit 0 decided, 1 hermes failed, 2 usage error.", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", help="project slug (default: the lead's active project)")
    parser.add_argument("--board", default="jobs", help="kanban board slug (default jobs)")
    parser.add_argument("--lead", default="jobs", help="lead profile that files the card (default jobs)")
    parser.add_argument("--scout", default="jobs-scout", help="assignee of the search card (default jobs-scout)")
    parser.add_argument("--skill", default="finding-jobs", help="skill the card loads (default finding-jobs)")
    parser.add_argument("--installed", type=Path, help="installed.yaml holding the lane models")
    parser.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN", "hermes"), help="hermes executable")
    parser.add_argument("--now", help="slot time, 'YYYY-MM-DD HH:MM' (tests and backfills)")
    parser.add_argument("--dry-run", action="store_true", help="print the card, create nothing")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        now = datetime.strptime(args.now, "%Y-%m-%d %H:%M") if args.now else datetime.now()
    except ValueError:
        print(f"error: --now must be 'YYYY-MM-DD HH:MM', got {args.now!r}", file=sys.stderr)
        return 2
    note = ""
    try:
        slug, folder = resolve_project(args.hermes_bin, args.lead, args.project)
        state = search_state(Path(folder) / "profile.md")
        if state == "paused":
            payload = {"filed": False, "reason": "paused", "project": slug, "slot": slot_id(now)}
        elif state == "missing":
            payload = {"filed": False, "reason": "no profile.md", "project": slug}
            note = (f"jobs-search: {slug} has no profile.md under {folder}; the search waits. "
                    f"Say \"set up my profile\" in the jobs Bot Chat.")
        else:
            payload = {"filed": True, "project": slug, "slot": slot_id(now),
                       **file_card(args.hermes_bin, args.lead, args, slug, folder, now,
                                   review_lane_model(args, args.lead))}
    except RunError as exc:
        print(f"jobs-search: {exc}")
        return 1
    if args.json:
        print(json.dumps(payload, indent=2))
    elif note:
        print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
