#!/usr/bin/env python3
"""Monthly report gate for the marketing squad (cron marketing-report, --no-agent).

Files one REPORT card on the marketing board only when a brand's analytics exports changed since the
last run. State is a fingerprint per project in `<profile>/local/state/gate_*.json`, via
scripts/gate_lib.py; the card's idempotency key `marketing-report:<project>:<YYYY-MM>` makes repeated
runs in the same month safe.

For every project of the marketing profile:
  - skip when the primary folder has no `brand.md` or its frontmatter `status` is not `active`;
  - skip when the folder holds a `PAUSE` file;
  - skip when `data/inbox/` holds no files (nothing to report yet);
  - skip when the fingerprint of `data/inbox/` equals the last one stored;
  - otherwise create the card, assigned to the lead, with skill `leading-marketing`.

Silent when there is nothing to file and when a card is filed; exit 1 on a real error so the cron
surfaces it.

Examples:
  report_gate.py --dry-run                # show what would be filed, write nothing
  report_gate.py --month 2026-09          # evaluate a specific reported month
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


def gate_lib():
    """gate_lib.py beside this script (squadctl copies it next to each cron script) or in a scripts/ dir."""
    try:
        import gate_lib as mod  # type: ignore[import-not-found]
        return mod
    except ImportError:
        pass
    h = home()
    root = h.parent.parent if h.parent.name == "profiles" else h
    here = Path(__file__).resolve()
    cands = [h / "scripts", here.parent, root / "scripts"]
    if len(here.parents) > 3:
        cands.append(here.parents[3] / "scripts")  # a repo checkout
    for cand in cands:
        if (cand / "gate_lib.py").is_file():
            sys.path.insert(0, str(cand))
            import gate_lib as mod  # type: ignore[import-not-found]
            return mod
    raise RuntimeError("gate_lib.py not found (looked in the profile scripts dir, beside this script, "
                       "in the hermes root and in the checkout's scripts dir)")


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
    return bool(block and re.search(r"^\s*status:\s*active\s*$", block.group(1), re.M))


def exports_fingerprint(folder: Path) -> list[list]:
    """Sorted [relative path, size, mtime] of every file under data/inbox/."""
    inbox = folder / "data" / "inbox"
    if not inbox.is_dir():
        return []
    rows = []
    for path in sorted(p for p in inbox.rglob("*") if p.is_file() and p.name != ".DS_Store"):
        st = path.stat()
        rows.append([str(path.relative_to(inbox)), st.st_size, int(st.st_mtime)])
    return rows


def report_month(override: str | None) -> str:
    if override:
        if not re.fullmatch(r"\d{4}-\d{2}", override):
            raise SystemExit("error: --month takes <YYYY-MM>, e.g. 2026-09")
        return override
    return (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def card_body(slug: str, folder: Path, month: str) -> str:
    return (
        f"Mode: REPORT (month {month}).\n"
        f"Brand: {slug} - project folder {folder}.\n"
        f"Input: data/inbox/ analytics exports (new since the previous report), calendar/ and the "
        f"pieces of {month}, published results.\n"
        f"Output: reports/{month}.md: what worked, what did not and why, matched per piece where the "
        f"UTM allows it; close with three numbered suggested decisions.\n"
        f"Rules: no conclusion from insufficient volume, state the window; name a missing export "
        f"instead of guessing; nothing is published or sent."
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=SUMMARY,
                                 epilog="Exit 0 clean (silent when nothing to file), 1 error.")
    ap.add_argument("--profile", help="marketing profile name (default: from HERMES_HOME)")
    ap.add_argument("--board", default="marketing", help="kanban board slug (default: marketing)")
    ap.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN", "hermes"),
                    help="hermes launcher (default: HERMES_BIN or hermes on PATH)")
    ap.add_argument("--month", help="reported month <YYYY-MM> (default: the previous month)")
    ap.add_argument("--workspace", default="dir", choices=["dir", "none"],
                    help="pin the card workspace to the brand folder (default: dir)")
    ap.add_argument("--dry-run", action="store_true", help="print what would be filed, create nothing, keep state")
    ap.add_argument("--json", action="store_true", help="machine-readable result")
    a = ap.parse_args(argv)
    try:
        profile = profile_from_home(a.profile)
        hermes = a.hermes_bin
        gate = gate_lib()
        state_dir = home() / "local" / "state"
        month = report_month(a.month)
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
            exports = exports_fingerprint(folder)
            if not exports:
                skipped.append({"project": slug, "reason": "no exports in data/inbox"})
                continue
            name = f"marketing_report_{slug}"
            fp = gate.fingerprint(exports)
            if not gate.changed(name, fp, save=False, directory=state_dir):
                skipped.append({"project": slug, "reason": "exports unchanged"})
                continue
            title = f"REPORT \u00b7 {slug} \u00b7 {month}"
            key = f"marketing-report:{slug}:{month}"
            cmd = [hermes, "-p", profile, "kanban", "--board", a.board, "create", title,
                   "--assignee", profile, "--created-by", profile, "--project", slug,
                   "--idempotency-key", key, "--skill", "leading-marketing",
                   "--body", card_body(slug, folder, month)]
            if a.workspace == "dir":
                cmd += ["--workspace", f"dir:{folder}"]
            if not a.dry_run:
                run(cmd + ["--json"])
                # Saved only after the card exists, so a failed create is retried on the next run.
                gate.save_state(f"gate_{name}", {"fp": fp}, directory=state_dir)
            filed.append({"project": slug, "month": month, "key": key, "title": title})
        if a.json:
            print(json.dumps({"filed": filed, "skipped": skipped, "dry_run": a.dry_run}, indent=2))
        elif a.dry_run:
            for row in filed:
                print(f"would file {row['title']} (key {row['key']})")
        return 0
    except SystemExit:
        raise
    except Exception as exc:  # a gate must fail loudly, never silently
        print(f"error: report_gate: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
