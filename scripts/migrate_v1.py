#!/usr/bin/env python3
"""Migrate a v1 install to v2: legacy profile layout, project folders, deliver crons and the orchestrator.

A v1 install is recognised by any of (all three are reported, never guessed):
  1. profiles with a v1-only bot name: `orchestrator`, `jobs-analyst`, `marketing-strategist`, `web-architect`,
     `web-developer`, `web-advisor` or `web-reviewer` (the v1 bot layout);
  2. `~/Hermes/projects/<key>/` folders (the fixed work layout v2 replaces with native Projects);
  3. cron jobs that run `deliver.py` (the v1 outbox delivery, replaced by kanban notify + `bot-chat`).

Profiles whose names the v2 squads also use (`jobs-*`, `marketing-*`, `web-*` workers) are reported
separately as "kept by v2" and are never listed for deletion.

What it does, in order:
  1. registers every `~/Hermes/projects/<key>/` folder as a native Hermes Project through
     `scripts/squadctl project add <key> <key> <path>`, which creates it in the squad's manager and workers;
  2. removes the `deliver.py` cron jobs from every profile (`hermes -p <bot> cron remove <id>`);
  3. exports the `orchestrator` profile to `<local>/backups/orchestrator-<stamp>.tar.gz`
     (`hermes profile export`), and with `--delete-orchestrator` deletes it afterwards;
  4. reports the legacy profile names the user can remove with `hermes profile delete <name>`.

Nothing else is touched: no project folder is moved or renamed, no profile is deleted by default, and no file is
copied between roots. `--dry-run` prints the plan and writes nothing; `--json` prints JSON instead of TOON.

Exit codes: 0 migrated (or nothing to migrate), 1 error, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import squadctl  # noqa: E402  (TOON output + the HERMES_HOME/root rule, so both tools agree)

LEGACY_PROFILE_RE = re.compile(
    r"^(?:orchestrator|jobs-analyst|marketing-strategist|web-architect|web-developer|web-advisor|web-reviewer)$")
# Names the v2 squads use for their own workers: after a v2 install these are NOT v1 leftovers.
V2_KEPT_RE = re.compile(r"^(?:jobs|marketing|web)-[a-z0-9][a-z0-9-]*$")
DELIVER_NAME_RE = re.compile(r"^deliver(?:-|$)", re.I)
ORCHESTRATOR = "orchestrator"


def resolve_root(explicit: str | None) -> Path:
    return squadctl.resolve_root(explicit)


def read_jobs(home: Path) -> list[dict]:
    path = home / "cron" / "jobs.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    jobs = raw.get("jobs", []) if isinstance(raw, dict) else raw
    return [j for j in jobs if isinstance(j, dict)]


def is_deliver(job: dict) -> bool:
    return (Path(str(job.get("script") or "")).name == "deliver.py"
            or bool(DELIVER_NAME_RE.match(str(job.get("name") or ""))))


def detect(root: Path, legacy: Path) -> dict:
    """The three v1 markers, then `v1` is true when at least one of them is present. Only v1-only profile
    names count as legacy; shared v2 names are reported as kept, and a `deliver.py` cron is a marker whatever
    the profile is called."""
    profiles, kept = {}, {}
    deliver_crons: list[dict] = []
    pdir = root / "profiles"
    for entry in sorted(pdir.iterdir()) if pdir.is_dir() else []:
        if not entry.is_dir():
            continue
        crons = [j for j in read_jobs(entry) if is_deliver(j)]
        if LEGACY_PROFILE_RE.match(entry.name):
            profiles[entry.name] = {"deliver_crons": crons}
        elif V2_KEPT_RE.match(entry.name):
            kept[entry.name] = {}
        deliver_crons += [{"profile": entry.name, "id": j.get("id"), "name": j.get("name"), "script": j.get("script")}
                          for j in crons]
    projects = sorted(p.name for p in legacy.iterdir() if p.is_dir()) if legacy.is_dir() else []
    return {
        "profiles": profiles,
        "kept_by_v2": sorted(kept),
        "deliver_crons": deliver_crons,
        "v1_projects": projects,
        "legacy_projects_dir": str(legacy),
        "outbox": str(legacy.parent / "outbox") if (legacy.parent / "outbox").is_dir() else None,
    }


# --- steps ----------------------------------------------------------------------------------------------------------

def hermes(bin: str, root: Path, *args: str, profile: str | None = None) -> subprocess.CompletedProcess:
    """Run one `hermes` command against *root*. A missing binary is a failed run, never a traceback."""
    cmd = [bin, *(["-p", profile] if profile else []), *args]
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                              env={**os.environ, "HERMES_HOME": str(root)})
    except OSError as exc:
        return subprocess.CompletedProcess(cmd, 127, "", str(exc))


def add_project(shim: Path, root: Path, local: Path | None, src: Path | None, key: str, folder: Path) -> dict:
    argv = [str(shim), "project", "add", key, key, str(folder), "--json", "--hermes-root", str(root)]
    if local is not None:
        argv += ["--local", str(local)]
    if src is not None:
        argv += ["--src", str(src)]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=600, env=os.environ)
    except OSError as exc:
        return {"squad": key, "result": f"failed: {exc}"[:200], "bots": []}
    try:
        out = json.loads(proc.stdout or "{}")
    except ValueError:
        out = {}
    if "error" in out:
        return {"squad": key, "result": "skipped", "reason": str(out["error"])[:200], "bots": []}
    rows = out.get("bots") or []
    results = sorted({str(r.get("result")) for r in rows})
    if "profile missing" in results:
        return {"squad": key, "result": "profile missing", "bots": rows,
                "reason": f"run `squadctl apply {key}` first"}
    return {"squad": key, "result": ",".join(results) or proc.stdout.strip()[:80] or "unknown", "bots": rows}


def error_of(proc: subprocess.CompletedProcess) -> str:
    return (proc.stderr or proc.stdout or "").strip()[:200] or f"exit {proc.returncode}"


def export_profile(bin: str, root: Path, local: Path, name: str) -> dict:
    out = local / "backups" / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = hermes(bin, root, "profile", "export", name, "-o", str(out))
    row = {"action": "profile export", "profile": name, "path": str(out),
           "result": "exported" if proc.returncode == 0 else "failed"}
    return row if proc.returncode == 0 else {**row, "error": error_of(proc)}


def run(args) -> dict:
    root = resolve_root(args.hermes_root)
    legacy = Path(args.v1_projects).expanduser().absolute() if args.v1_projects else Path.home() / "Hermes" / "projects"
    found = detect(root, legacy)
    v1 = bool(found["profiles"]) or bool(found["deliver_crons"]) or bool(found["v1_projects"])
    local = Path(args.local).expanduser().absolute() if args.local else root / "profiles" / args.builder / "local"
    shim = Path(args.squadctl).expanduser().absolute() if args.squadctl else HERE / "squadctl"
    actions: list[dict] = []
    notes: list[str] = []

    for key in found["v1_projects"]:
        folder = legacy / key
        if not folder.is_dir():
            continue
        if shim.is_file() and not args.dry_run:
            row = add_project(shim, root, local if args.local else None, args.src, key, folder)
            actions.append({"action": "project add", "path": str(folder), **row})
        else:
            actions.append({"action": "project add", "path": str(folder), "squad": key,
                            "result": "would-add" if args.dry_run else "skipped", "bots": []})
    if found["v1_projects"]:
        notes.append(f"{len(found['v1_projects'])} v1 project folder(s) mapped; "
                     "legacy folders are never moved or renamed")

    for row in found["deliver_crons"]:
        home, job = root / "profiles" / row["profile"], row
        if not home.is_dir():
            continue
        if args.dry_run:
            actions.append({"action": "cron remove", **row, "result": "would-remove"})
            continue
        proc = hermes(args.hermes_bin, root, "cron", "remove", str(job["id"]), profile=row["profile"])
        actions.append({"action": "cron remove", **row, "result": "removed" if proc.returncode == 0 else "failed",
                        **({} if proc.returncode == 0 else {"error": error_of(proc)})})
    if found["deliver_crons"]:
        notes.append("v2 delivers cards to bot-chat; the deliver/outbox loop is gone")

    orche = root / "profiles" / ORCHESTRATOR
    if orche.is_dir():
        if args.dry_run:
            actions.append({"action": "profile export", "profile": ORCHESTRATOR,
                            "path": str(local / "backups" / f"{ORCHESTRATOR}-<stamp>.tar.gz"), "result": "would-export"})
        else:
            actions.append(export_profile(args.hermes_bin, root, local, ORCHESTRATOR))
        exported = actions[-1]["result"] == "exported"
        if args.delete_orchestrator and (args.dry_run or exported):
            if args.dry_run:
                actions.append({"action": "profile delete", "profile": ORCHESTRATOR, "result": "would-delete"})
            else:
                proc = hermes(args.hermes_bin, root, "profile", "delete", ORCHESTRATOR, "--yes")
                actions.append({"action": "profile delete", "profile": ORCHESTRATOR,
                                "result": "deleted" if proc.returncode == 0 else "failed",
                                **({} if proc.returncode == 0 else {"error": error_of(proc)})})
                notes.append(f"{ORCHESTRATOR} archived then deleted; its sessions live in the export")
        elif args.delete_orchestrator:
            notes.append(f"export failed: {ORCHESTRATOR} was NOT deleted; fix the export and re-run")

    if v1 and not args.delete_orchestrator and orche.is_dir():
        notes.append(f"keep the export safe, then remove the old bot with `hermes profile delete {ORCHESTRATOR}`")
    if found["outbox"]:
        notes.append(f"v1 outbox found at {found['outbox']}: v2 replaces it with bot-chat delivery; left untouched")
    if found["profiles"]:
        names = ", ".join(sorted(found["profiles"]))
        notes.append(f"v1-only profiles: {names}. Export each, then remove it with `hermes profile delete <name>`")
    if found["kept_by_v2"]:
        notes.append("profiles kept by v2: " + ", ".join(found["kept_by_v2"])
                     + ". These are the v2 squad bots; never delete them as v1 leftovers")
    if not v1:
        notes.append("no v1 install found: nothing to migrate")

    return {"v1": v1, "hermes_root": str(root), "local": str(local), "dry_run": bool(args.dry_run),
            "found": found, "actions": actions, "notes": notes}


def build_parser() -> argparse.ArgumentParser:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(description=doc.split("\n\n")[0], epilog=doc.split("\n\n", 1)[-1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="JSON output instead of TOON")
    ap.add_argument("--dry-run", action="store_true", help="report only: no project, cron or profile change")
    ap.add_argument("--hermes-root", help="Hermes root (default: HERMES_HOME without /profiles/<name>, else ~/.hermes)")
    ap.add_argument("--v1-projects", help="v1 project folder root (default: ~/Hermes/projects)")
    ap.add_argument("--local", help="builder local/ dir (default: <root>/profiles/<builder>/local)")
    ap.add_argument("--builder", default="builder", help="builder profile name (default: builder)")
    ap.add_argument("--src", help="distribution root holding squads/ (default: this checkout)")
    ap.add_argument("--squadctl", help="squadctl shim to call (default: scripts/squadctl here)")
    ap.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN", "hermes"),
                    help="hermes executable (default: $HERMES_BIN, else hermes)")
    ap.add_argument("--delete-orchestrator", action="store_true",
                    help="after the export succeeds, delete the orchestrator profile")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run(args)
    except Exception as exc:  # noqa: BLE001 - the builder reads one line and stops
        if args.json:
            print(json.dumps({"error": f"{type(exc).__name__}: {exc}"[:400]}))
        else:
            print(f"error: {type(exc).__name__}: {exc}"[:400], file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else "\n".join(squadctl.toon(result)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
