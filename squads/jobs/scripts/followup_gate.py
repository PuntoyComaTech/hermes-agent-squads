#!/usr/bin/env python3
"""File one inbox card per project for jobs-writer when its tracked applications need attention (cron, no agent).

Every project of the manager is checked, or only --project. Each project reads its own `<project>/tracker.csv` through
the squad's `tracker.py followups` and `tracker.py stale`. Two kinds of item are filed:

- follow-ups due: applications quiet for follow_up_days or more, below the follow-up cap, and not yet stale;
- stale applications: quiet for stale_days or more. Each stale row is reported once: the filed card records
  `stale_reported` on the row, and no later card names it again until the user closes the row (a closed status
  leaves the stale list).

A due day files one jobs-writer card per project (skill triaging-inbox, body `Mode: INBOX`) with the idempotency key
`jobs:inbox:<project>:<YYYY-MM-DD>`, so a project never gets two cards on one day. Nothing due means nothing is filed.
`profile.md -> search: paused` pauses that project too.

stdout is what the cron delivers. Nothing is printed when a card is filed, nothing is due, the search is paused,
or the project has no profile.md; `--json` prints {"results": [one decision per project]} (reason "no tracker yet"
for a project without tracker.csv). A hermes or tracker failure prints, the other projects still run, and exit is 1.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import start_search as ss  # noqa: E402  - same folder on the manager: project resolution and the pause flag


def tracker_script(manager: str, explicit: Path | None) -> Path:
    if explicit:
        return explicit
    for base in (ss.profile_home(manager) / "skills" / "squad-jobs",
                 HERE.parent / "skills"):
        path = base / "jobs-contract" / "scripts" / "tracker.py"
        if path.is_file():
            return path
    raise ss.RunError("tracker.py not found: reinstall the jobs squad (squadctl apply jobs)")


def run_tracker(tracker: Path, args: list[str]) -> str:
    try:
        done = subprocess.run([sys.executable, str(tracker), *args], capture_output=True, text=True, timeout=120,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ss.RunError(f"tracker.py {args[0]} failed: {exc}") from None
    if done.returncode != 0:
        raise ss.RunError(f"tracker.py {args[0]} exited {done.returncode}: {done.stderr.strip()[:300]}")
    return done.stdout


def due(tracker: Path, folder: str, today: str) -> dict:
    """The follow-up and stale items as the tracker reports them (full records, one object per row)."""
    out = {}
    for command in ("followups", "stale"):
        try:
            data = json.loads(run_tracker(tracker, [command, "--project", folder, "--today", today]) or "{}")
        except ValueError:
            raise ss.RunError(f"tracker.py {command} printed no JSON") from None
        out[command] = [item for item in data.get("items") or [] if isinstance(item, dict)]
    return out


def decide(items: dict) -> tuple[list, list]:
    """(follow-ups to chase, stale rows not reported yet). A stale row never appears as a follow-up."""
    stale_ids = {str(item.get("id")) for item in items["stale"]}
    chase = [item for item in items["followups"] if str(item.get("id")) not in stale_ids]
    fresh = [item for item in items["stale"] if not item.get("stale_reported")]
    return chase, fresh


def label(item: dict) -> str:
    return str(item.get("id") or item.get("company") or "?")


def card_body(slug: str, folder: str, chase: list, fresh: list, today: str) -> str:
    lines = [
        "Mode: INBOX", f"Date: {today}.", f"Project: {slug} ({folder})",
        f"Follow-ups due: {', '.join(label(i) for i in chase) or 'none'}.",
        f"Quiet past stale_days, first report: {', '.join(label(i) for i in fresh) or 'none'}.",
        "Read job mail since the last inbox report, draft the due follow-ups, then hand the proposal to the "
        "manager (skill triaging-inbox).",
        f"File follow-up cards with project {slug} and workspace dir:{folder}.",
    ]
    return "\n".join(lines)


def file_card(args, slug: str, folder: str, chase: list, fresh: list, today: str) -> dict:
    key = f"jobs:inbox:{slug}:{today}"
    title = f"Inbox and follow-ups {today}"
    argv = ["-p", args.manager, "kanban", "--board", args.board, "create", title,
            "--assignee", args.writer, "--created-by", args.manager, "--skill", "triaging-inbox",
            "--project", slug, "--workspace", f"dir:{folder}", "--idempotency-key", key,
            "--body", card_body(slug, folder, chase, fresh, today), "--json"]
    result = {"key": key, "title": title, "assignee": args.writer, "board": args.board, "project": slug}
    if args.dry_run:
        return {**result, "body": card_body(slug, folder, chase, fresh, today)}
    stdout = ss.hermes(args.hermes_bin, *argv)
    try:
        result["id"] = str((json.loads(stdout.strip()) or {}).get("id") or "")
    except ValueError:
        result["id"] = stdout.strip().split()[-1] if stdout.strip() else ""
    return result


def mark_reported(tracker: Path, folder: str, fresh: list, today: str) -> None:
    """Record on each row that the stale report named it, so the next cards stay silent about it."""
    for item in fresh:
        run_tracker(tracker, ["update", "--project", folder, "--id", label(item), "--stale-reported", today,
                              "--today", today])


def project_decision(args, slug: str, folder: str, today: str) -> dict:
    """One project's decision: file its card, or say why not."""
    state = ss.search_state(Path(folder) / "profile.md")
    if state != "active":
        return {"project": slug, "filed": False, "reason": "paused" if state == "paused" else "no profile.md"}
    if not (Path(folder) / "tracker.csv").is_file():
        return {"project": slug, "filed": False, "reason": "no tracker yet"}
    tracker = tracker_script(args.manager, args.tracker)
    chase, fresh = decide(due(tracker, folder, today))
    if not chase and not fresh:
        return {"project": slug, "filed": False, "reason": "nothing due"}
    card = file_card(args, slug, folder, chase, fresh, today)
    if not args.dry_run:
        mark_reported(tracker, folder, fresh, today)
    return {"project": slug, ("would_file" if args.dry_run else "filed"): True, "followups": [label(i) for i in chase],
            "stale_reported": [label(i) for i in fresh], **card}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="followup_gate.py", description=(__doc__ or "").split("\n\n")[0],
        epilog="Exit 0 decided, 1 hermes or tracker failed, 2 usage error.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", help="project slug (default: every project of the manager)")
    parser.add_argument("--board", default="jobs", help="kanban board slug (default jobs)")
    parser.add_argument("--manager", default="jobs", help="manager profile that files the card (default jobs)")
    parser.add_argument("--writer", default="jobs-writer", help="assignee of the inbox card (default jobs-writer)")
    parser.add_argument("--tracker", type=Path, help="tracker.py to run (default: the installed squad copy)")
    parser.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN", "hermes"), help="hermes executable")
    parser.add_argument("--today", help="YYYY-MM-DD in place of the local date (tests and replays)")
    parser.add_argument("--dry-run", action="store_true", help="print the card, create nothing, mark nothing")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        today = datetime.strptime(args.today, "%Y-%m-%d").strftime("%Y-%m-%d") if args.today \
            else datetime.now().strftime("%Y-%m-%d")
    except ValueError:
        print(f"error: --today must be YYYY-MM-DD, got {args.today!r}", file=sys.stderr)
        return 2
    try:
        known = ss.project_list(args.hermes_bin, args.manager)
    except ss.RunError as exc:
        print(f"jobs-followups: {exc}")
        return 1
    results: list[dict] = []
    if args.project and args.project not in known:
        results.append({"project": args.project, "filed": False, "reason": "no project",
                        "message": f"project {args.project} is not on the jobs manager"})
        slugs: list[str] = []
    else:
        slugs = [args.project] if args.project else known
    if not slugs and not results:
        results.append({"filed": False, "reason": "no project", "message": ss.NO_PROJECT})
    failed = False
    for slug in slugs:
        try:
            folder = ss.project_folder(args.hermes_bin, args.manager, slug)
            results.append(project_decision(args, slug, folder, today))
        except ss.SetupGap as exc:
            results.append({"project": slug, "filed": False, "reason": str(exc)})
        except ss.RunError as exc:
            failed = True
            print(f"jobs-followups: {exc}")
            results.append({"project": slug, "filed": False, "reason": "error", "message": str(exc)})
    if args.json:
        print(json.dumps({"results": results}, indent=2, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
