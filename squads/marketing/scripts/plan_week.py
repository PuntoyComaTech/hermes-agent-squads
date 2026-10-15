#!/usr/bin/env python3
"""Weekly calendar gate for the marketing squad (cron marketing-plan-week, --no-agent).

Files one CALENDAR card, assigned to the lead, for every project whose primary folder holds an `active`
brand.md, no PAUSE file and no calendar/<YYYY>-W<WW>.md for the coming week. Idempotency key:
marketing-plan-week:<project>:<YYYY>-W<WW>. Prints nothing unless --dry-run or --json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

SUMMARY = (__doc__ or "").split("\n\n")[0]


def home() -> Path:
    raw = os.environ.get("HERMES_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".hermes"


def profile_from_home(profile_arg: str | None) -> str:
    if profile_arg:
        return profile_arg
    h = home()
    if h.parent.name == "profiles":
        return h.name
    raise SystemExit("error: pass --profile: HERMES_HOME is not a profile home")


def run(argv: list[str]) -> str:
    proc = subprocess.run(argv, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(argv[:5])} failed ({proc.returncode}): {(proc.stderr or proc.stdout).strip()[:300]}")
    return proc.stdout


def project_slugs(hermes: str, profile: str) -> list[str]:
    """Slugs from `hermes project list` (archived projects are absent without --all)."""
    out = run([hermes, "-p", profile, "project", "list"])
    slugs = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith("No projects yet"):
            continue
        line = line[1:].strip() if line.startswith("*") else line
        slug = line.split()[0] if line.split() else ""
        if slug and " (archived)" not in line:
            slugs.append(slug)
    return slugs


def project_folder(hermes: str, profile: str, slug: str) -> Path | None:
    """Primary folder from `hermes project show`, else the first folder."""
    out = run([hermes, "-p", profile, "project", "show", slug])
    primary = re.search(r"^\s*primary:\s*(\S.*)$", out, re.M)
    if primary:
        return Path(primary.group(1).strip()).expanduser()
    first = re.search(r"^\s+(?:\*\s+)?(/\S.*)$", out, re.M)
    return Path(first.group(1).strip()).expanduser() if first else None


def brand_is_active(folder: Path) -> bool:
    brand = folder / "brand.md"
    if not brand.is_file():
        return False
    text = brand.read_text(encoding="utf-8", errors="replace")
    block = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    return bool(block and re.search(r"^\s*status:\s*active\s*(#.*)?$", block.group(1), re.M))


def target_week(override: str | None) -> tuple[int, int]:
    if override:
        m = re.fullmatch(r"(\d{4})-W(\d{2})", override)
        if not m:
            raise SystemExit("error: --week takes <YYYY>-W<WW>, e.g. 2026-W42")
        return int(m.group(1)), int(m.group(2))
    y, w, _ = (date.today() + timedelta(days=7)).isocalendar()
    return y, w


def card_body(folder: Path, year: int, week: int) -> str:
    monday = date.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6)
    return (
        f"Mode: CALENDAR, week {year}-W{week:02d} ({monday} to {sunday}).\n"
        f"Brand folder: {folder}.\n"
        f"Follow leading-marketing step 4."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=SUMMARY, epilog="Exit 0 done, 1 error (stderr).")
    ap.add_argument("--profile", help="marketing profile name (default: from HERMES_HOME)")
    ap.add_argument("--board", default="marketing", help="kanban board slug (default: marketing)")
    ap.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN", "hermes"),
                    help="hermes launcher (default: HERMES_BIN or hermes on PATH)")
    ap.add_argument("--week", help="target week <YYYY>-W<WW> (default: the coming week)")
    ap.add_argument("--workspace", default="dir", choices=["dir", "none"],
                    help="pin the card workspace to the brand folder (default: dir)")
    ap.add_argument("--dry-run", action="store_true", help="print what would be filed, create nothing")
    ap.add_argument("--json", action="store_true", help="machine-readable result")
    a = ap.parse_args(argv)
    try:
        profile = profile_from_home(a.profile)
        hermes = a.hermes_bin
        year, week = target_week(a.week)
        filed, skipped = [], []
        for slug in project_slugs(hermes, profile):
            folder = project_folder(hermes, profile, slug)
            if folder is None or not folder.is_dir():
                skipped.append({"project": slug, "reason": "no folder"})
                continue
            if not brand_is_active(folder):
                skipped.append({"project": slug, "reason": "brand not active"})
                continue
            if (folder / "PAUSE").exists():
                skipped.append({"project": slug, "reason": "PAUSE"})
                continue
            calendar = folder / "calendar" / f"{year}-W{week:02d}.md"
            if calendar.exists():
                skipped.append({"project": slug, "reason": f"calendar {year}-W{week:02d} exists"})
                continue
            title = f"CALENDAR - {slug} - {year}-W{week:02d}"
            key = f"marketing-plan-week:{slug}:{year}-W{week:02d}"
            cmd = [hermes, "-p", profile, "kanban", "--board", a.board, "create", title,
                   "--assignee", profile, "--created-by", profile, "--project", slug,
                   "--idempotency-key", key, "--skill", "leading-marketing",
                   "--body", card_body(folder, year, week)]
            if a.workspace == "dir":
                cmd += ["--workspace", f"dir:{folder}"]
            if not a.dry_run:
                run(cmd + ["--json"])
            filed.append({"project": slug, "week": f"{year}-W{week:02d}", "key": key, "title": title})
        if a.json:
            print(json.dumps({"filed": filed, "skipped": skipped, "dry_run": a.dry_run}, indent=2))
        elif a.dry_run:
            for row in filed:
                print(f"would file {row['title']} (key {row['key']})")
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # a gate must fail loudly, never silently
        print(f"error: plan_week: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
