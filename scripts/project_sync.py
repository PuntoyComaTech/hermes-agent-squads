#!/usr/bin/env python3
"""Copy a squad manager's Hermes Projects to every worker of the squad and bind them to the squad board.

Projects are per profile: a project the user creates with "+" in the manager's Desktop sidebar (or the manager creates
with `desktop_project`) exists only in the manager. This script reads `hermes -p <manager> project list` and
`project show`, then for each project:
  - in every worker that lacks the slug (`project list --all`): `project create <name> <folders> --slug <slug>
    --primary <primary> --board <board>`;
  - in the manager, when the project has no board: `project bind-board <slug> <board>`.
A project whose primary folder is the home directory or inside the Hermes root is skipped and reported.

`--setup` (once per squad, after apply): create ~/Projects/<squad> and set `desktop.repo_scan_roots: [~/Projects/<squad>]`
in the manager and every worker whose list is empty, so the Desktop Projects sidebar of those profiles lists only this
squad's folders instead of every git repo under the home directory. A custom list is kept.

Squad members are the profiles holding `skills/squad-<squad>/` (written by squadctl apply); without any, the
profiles named `<squad>-*`. Defaults come from $HERMES_HOME when it is `<root>/profiles/<manager>`, so the manager's
cron runs it with no arguments: `--no-agent`, non-empty stdout goes to the manager's Bot Chat, and a run with nothing
to do prints nothing. Skips and notes print once (state: <manager>/local/state/project_sync.json); actions and errors
print every time. Idempotent. Stdlib only: cron runs it with the system python3.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


def hermes_home() -> Path:
    raw = os.environ.get("HERMES_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".hermes"


def real_home() -> Path:
    raw = os.environ.get("HERMES_REAL_HOME")
    return Path(raw).expanduser() if raw else Path.home()


def defaults() -> tuple[Path, str | None]:
    """(Hermes root, manager) from $HERMES_HOME: `<root>/profiles/<name>` names the manager."""
    home = hermes_home()
    if home.parent.name == "profiles":
        return home.parent.parent, home.name
    return home, None


class Hermes:
    def __init__(self, binary: str, root: Path):
        self.binary, self.root = binary, root

    def run(self, profile: str, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "HERMES_HOME": str(self.root)}
        try:
            return subprocess.run([self.binary, "-p", profile, *args], capture_output=True, text=True, env=env,
                                  timeout=180, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError) as exc:
            return subprocess.CompletedProcess([], 1, "", str(exc))


def slugs(listing: str) -> list[str]:
    """Slugs of `hermes project list`: `<*| > <slug> <name>  [N folder(s)]` rows."""
    return [m.group(1) for m in re.finditer(r"^[* ] (\S+) .*\[\d+ folder\(s\)\]\s*$", listing, re.M)]


def parse_show(text: str) -> dict:
    """`hermes project show`: `name:`, `board:`, `primary:` lines and the `folders:` list (`*` marks the primary)."""
    info: dict = {"name": None, "board": None, "primary": None, "folders": []}
    in_folders = False
    for line in text.splitlines():
        m = re.match(r"^\s+(name|board|primary|about):\s*(.*?)\s*$", line)
        if m:
            in_folders = False
            if m.group(1) != "about":
                info[m.group(1)] = m.group(2) or None
            continue
        if re.match(r"^\s+folders:\s*$", line):
            in_folders = True
            continue
        if in_folders:
            m = re.match(r"^\s+(\*\s+)?(\S.*?)(?:\s+\([^)]*\))?\s*$", line)
            if m:
                info["folders"].append(m.group(2))
                if m.group(1) and not info["primary"]:
                    info["primary"] = m.group(2)
    if info["primary"] and info["primary"] not in info["folders"]:
        info["folders"].insert(0, info["primary"])
    return info


def members(root: Path, squad: str, manager: str) -> list[str]:
    profiles = sorted(p for p in (root / "profiles").glob("*") if p.is_dir()) if (root / "profiles").is_dir() else []
    marked = [p.name for p in profiles if (p / "skills" / f"squad-{squad}").is_dir()]
    names = marked or [p.name for p in profiles if p.name.startswith(f"{squad}-")]
    return [n for n in names if n != manager]


def unsafe(folder: str | None, root: Path) -> str | None:
    if not folder:
        return "no folder"
    path = Path(folder).expanduser().resolve()
    if path == real_home().resolve():
        return "the home folder"
    if path == root.resolve() or root.resolve() in path.parents:
        return "a Hermes profile folder"
    return None


def board_exists(h: Hermes, manager: str, board: str) -> bool | None:
    proc = h.run(manager, "kanban", "boards", "list", "--json")
    try:
        rows = json.loads(proc.stdout) if proc.returncode == 0 else None
    except ValueError:
        rows = None
    if not isinstance(rows, list):
        return None
    return board == "default" or any(isinstance(b, dict) and b.get("slug") == board for b in rows)


def sync(h: Hermes, manager: str, squad: str, board: str | None, workers: list[str], dry: bool) -> dict:
    report: dict = {"manager": manager, "squad": squad, "board": board, "workers": workers, "dry_run": dry,
                    "projects": [], "notes": [], "ok": True}
    listing = h.run(manager, "project", "list")
    if listing.returncode != 0:
        report["ok"] = False
        report["notes"].append(f"cannot list the projects of {manager}: {(listing.stderr or listing.stdout).strip()}")
        return report
    if board and board_exists(h, manager, board) is False:
        report["notes"].append(f"board {board} does not exist: projects are created without a board")
        board = None
    have = {}
    for w in workers:
        proc = h.run(w, "project", "list", "--all")
        if proc.returncode != 0:
            report["ok"] = False
            report["notes"].append(f"cannot list the projects of {w}: {(proc.stderr or proc.stdout).strip()}")
            continue
        have[w] = set(slugs(proc.stdout))
    for slug in slugs(listing.stdout):
        shown = h.run(manager, "project", "show", slug)
        row: dict = {"slug": slug, "actions": []}
        report["projects"].append(row)
        if shown.returncode != 0:
            report["ok"] = False
            row["error"] = (shown.stderr or shown.stdout).strip()
            continue
        info = parse_show(shown.stdout)
        row.update(name=info["name"] or slug, primary=info["primary"], board=info["board"])
        why = unsafe(info["primary"], h.root)
        if why:
            row["skipped"] = f"primary folder is {why}; move the project under ~/Projects/{squad}/<name>"
            continue
        if board and not info["board"]:
            row["actions"].append({"bot": manager, "action": f"bind-board {board}"})
            if not dry:
                proc = h.run(manager, "project", "bind-board", slug, board)
                if proc.returncode != 0:
                    report["ok"] = False
                    row["actions"][-1]["error"] = (proc.stderr or proc.stdout).strip()
        elif board and info["board"] != board:
            report["notes"].append(f"{slug}: bound to board {info['board']}, not {board}; left as is")
        target = board or info["board"]
        for w, present in have.items():
            if slug in present:
                continue
            folders = [info["primary"], *[f for f in info["folders"] if f != info["primary"]]]
            args = ["project", "create", row["name"], *folders, "--slug", slug, "--primary", info["primary"],
                    *(["--board", target] if target else [])]
            row["actions"].append({"bot": w, "action": "create"})
            if not dry:
                proc = h.run(w, *args)
                if proc.returncode != 0:
                    report["ok"] = False
                    row["actions"][-1]["error"] = (proc.stderr or proc.stdout).strip()
    return report


def text(report: dict, seen: set[str]) -> tuple[str, set[str]]:
    """Text report. Actions and errors always print; a skip or note prints once (`seen` holds those already sent)."""
    lines, notices = [], set()
    verb = "would " if report["dry_run"] else ""
    for row in report["projects"]:
        if row.get("error"):
            lines.append(f"{row['slug']}: {row['error']}")
        elif row.get("skipped"):
            notices.add(f"{row['slug']}: skipped, {row['skipped']}")
        for act in row["actions"]:
            done = f"{verb}{act['action']}" if not act.get("error") else f"{act['action']} failed: {act['error']}"
            lines.append(f"{row['slug']}: {act['bot']} {done}")
    notices |= set(report["notes"])
    return "\n".join(lines + sorted(notices - seen)), notices


def state_path(root: Path, manager: str) -> Path:
    return root / "profiles" / manager / "local" / "state" / "project_sync.json"


def load_seen(path: Path) -> set[str]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return set()
    return {str(x) for x in data.get("reported", [])} if isinstance(data, dict) else set()


def save_seen(path: Path, notices: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"reported": sorted(notices)}, indent=2) + "\n")
    os.replace(tmp, path)


def scan_roots(h: Hermes, bot: str) -> list[str] | None:
    """`desktop.repo_scan_roots` of a bot; [] when unset or empty, None when unreadable."""
    proc = h.run(bot, "config", "get", "desktop.repo_scan_roots")
    if proc.returncode != 0:
        return [] if "not set" in (proc.stdout + proc.stderr) else None
    out = proc.stdout.strip()
    if out in ("", "[]"):
        return []
    return [ln.strip()[2:].strip() for ln in out.splitlines() if ln.strip().startswith("- ")]


def setup(h: Hermes, squad: str, bots: list[str], dry: bool) -> dict:
    """Create ~/Projects/<squad> and point every squad bot's Desktop repo scan at it (only where the list is empty)."""
    folder = real_home() / "Projects" / squad
    want = f"~/Projects/{squad}"
    report: dict = {"folder": str(folder), "dry_run": dry, "bots": [], "ok": True}
    if not folder.is_dir():
        report["created_folder"] = True
        if not dry:
            folder.mkdir(parents=True, exist_ok=True)
    for bot in bots:
        roots = scan_roots(h, bot)
        if roots is None:
            report["ok"] = False
            report["bots"].append({"bot": bot, "result": "config unreadable"})
        elif roots in ([want], [str(folder)]):
            report["bots"].append({"bot": bot, "result": "ok"})
        elif roots:
            report["bots"].append({"bot": bot, "result": f"custom repo_scan_roots kept: {roots}"})
        else:
            report["bots"].append({"bot": bot, "result": "would set" if dry else "set"})
            if not dry:
                proc = h.run(bot, "config", "set", "desktop.repo_scan_roots", json.dumps([want]))
                if proc.returncode != 0:
                    report["ok"] = False
                    report["bots"][-1]["result"] = f"set failed: {(proc.stderr or proc.stdout).strip()}"
    return report


def main(argv: list[str] | None = None) -> int:
    root, manager = defaults()
    p = argparse.ArgumentParser(description="Copy the manager's Hermes Projects to every worker of its squad and "
                                            "bind them to the squad board. Idempotent.",
                                epilog="Exit 0 synced or nothing to do, 1 a hermes call failed, 2 bad arguments.")
    p.add_argument("--manager", default=manager, help="manager profile (default: the $HERMES_HOME profile)")
    p.add_argument("--squad", help="squad key (default: the manager name)")
    p.add_argument("--board", help="squad board slug (default: the squad key)")
    p.add_argument("--workers", help="comma-separated worker profiles (default: profiles holding skills/squad-<key>)")
    p.add_argument("--hermes-root", type=Path, default=root, help=f"Hermes root holding profiles/ (default: {root})")
    p.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN") or "hermes",
                   help="hermes executable (default: $HERMES_BIN, else `hermes` on PATH)")
    p.add_argument("--setup", action="store_true",
                   help="instead of syncing: create ~/Projects/<squad> and set desktop.repo_scan_roots to it in the "
                        "manager and every worker whose list is empty, so the Desktop Projects sidebar lists only "
                        "this squad's folders")
    p.add_argument("--dry-run", action="store_true", help="show what would change; change nothing")
    p.add_argument("--json", action="store_true", help="print the full report as JSON")
    a = p.parse_args(argv)
    if not a.manager:
        p.error("--manager is required outside a manager profile")
    binary = shutil.which(a.hermes_bin) or (a.hermes_bin if os.path.isabs(a.hermes_bin) else None)
    if not binary:
        print(f"project-sync: hermes executable not found ({a.hermes_bin})", file=sys.stderr)
        return 1
    squad = a.squad or a.manager
    workers = [w.strip() for w in a.workers.split(",") if w.strip()] if a.workers else \
        members(a.hermes_root, squad, a.manager)
    if a.setup:
        rep = setup(Hermes(binary, a.hermes_root), squad, [a.manager, *workers], a.dry_run)
        if a.json:
            print(json.dumps(rep, indent=2))
        else:
            changed = [r for r in rep["bots"] if r["result"] != "ok"]
            if rep.get("created_folder"):
                print(f"{'would create' if a.dry_run else 'created'} {rep['folder']}")
            for r in changed:
                print(f"{r['bot']}: {r['result']}")
        return 0 if rep["ok"] else 1
    report = sync(Hermes(binary, a.hermes_root), a.manager, squad, a.board or squad, workers, a.dry_run)
    if a.json:
        print(json.dumps(report, indent=2))
    else:
        state = state_path(a.hermes_root, a.manager)
        out, notices = text(report, set() if a.dry_run else load_seen(state))
        if not a.dry_run and (state.parent.parent.parent.is_dir()):
            save_seen(state, notices)
        if out:
            print(out)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
