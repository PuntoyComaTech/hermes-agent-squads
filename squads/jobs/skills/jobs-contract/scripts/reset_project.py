#!/usr/bin/env python3
"""Reset a job-search project's personal data, recoverably: entries are moved to .trash, never deleted.

  reset_project.py --project P --scope profile|documents|all [--confirm RESET] [--json]

Without --confirm this only previews: it lists every entry with its size and changes nothing. With --confirm RESET it
moves the listed entries to <P>/.trash/<YYYYMMDD-HHMMSS>/ at the same relative paths and writes RESET-MANIFEST.json
beside them. Moving an entry back restores it.

Scopes:
  profile    profile.md, achievements.yaml, contact.yaml, application-data.yaml, calibration.md
  documents  documents/**, except documents/README.md and .gitkeep placeholders (kept)
  all        everything in P except .trash/ and the same kept placeholders; openings/ history included

Safety: symbolic links are moved as links and never followed, so a link into another folder leaves its target alone.
Refused (exit 1, nothing moved): P is not a folder or is the home folder; P has no profile.md and holds entries a
project does not have; documents/ or .trash/ is itself a symbolic link. Exit 2 on usage errors, including any
--confirm value other than RESET. Exit 0 on preview or success.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs_common as jc  # noqa: E402

SCOPES = ("profile", "documents", "all")
CONFIRM = "RESET"
TRASH = ".trash"
MANIFEST = "RESET-MANIFEST.json"
PROFILE_FILES = ("profile.md", "achievements.yaml", "contact.yaml", "application-data.yaml", "calibration.md")
DOCUMENTS = "documents"
SCAFFOLD_PATHS = frozenset({"documents/README.md"})
SCAFFOLD_NAME = ".gitkeep"
# Folders a reset keeps even when they end up empty: the project's standard layout.
STANDARD_FOLDERS = frozenset({"documents", "documents/cv", "documents/linkedin", "documents/diplomas",
                              "documents/references", "documents/projects"})
# Entries that make a folder a project. A folder with no profile.md may still be reset when it holds only these.
PROJECT_ENTRIES = frozenset({"documents", "openings", "searches", "companies", "reports", "tracker.csv", TRASH,
                             SCAFFOLD_NAME, ".DS_Store"} | set(PROFILE_FILES))


class ResetError(Exception):
    """A refusal or a failed move. The message says what happened; the exit code is 1."""


def project_root(arg: str) -> Path:
    root = Path(arg).expanduser().resolve()
    if not root.is_dir():
        raise ResetError(f"{root} is not a folder")
    if root == Path.home().resolve():
        raise ResetError("the home folder is never a project")
    return root


def is_scaffold(rel: str) -> bool:
    return rel in SCAFFOLD_PATHS or rel.rsplit("/", 1)[-1] == SCAFFOLD_NAME


def plan(root: Path, scope: str) -> tuple:
    """(entries as (path, kind, bytes), kept scaffold paths). Changes nothing."""
    trash = root / TRASH
    if trash.is_symlink() or (os.path.lexists(trash) and not trash.is_dir()):
        raise ResetError(f"{TRASH} exists and is not a folder; move it aside first")
    if not (root / "profile.md").is_file():
        stray = sorted(p.name for p in root.iterdir() if p.name not in PROJECT_ENTRIES)
        if stray:
            raise ResetError("no profile.md and the folder holds entries that a project does not have "
                             f"({', '.join(stray[:5])}); pass the project folder")

    if scope == "profile":
        entries = []
        for name in PROFILE_FILES:
            path = root / name
            if path.is_symlink():
                entries.append((name, "link", 0))
            elif path.exists():
                if not path.is_file():
                    raise ResetError(f"{name} is not a file; refusing")
                entries.append((name, "file", path.stat().st_size))
        kept = []
    else:
        if scope == "documents":
            docs = root / DOCUMENTS
            if docs.is_symlink():
                raise ResetError("documents is a symbolic link; replace it with a real folder first")
            walked = [(f"{DOCUMENTS}/{rel}", kind, size) for rel, kind, size in
                      (jc.tree_entries(docs) if docs.is_dir() else [])]
        else:
            walked = jc.tree_entries(root, skip=frozenset({TRASH}))
        entries, kept = [], []
        for rel, kind, size in walked:
            if kind == "dir":
                continue
            if is_scaffold(rel):
                kept.append(rel)
            else:
                entries.append((rel, kind, size))

    for rel, _kind, _size in entries:
        if not jc.inside(root, root / rel):
            raise ResetError(f"{rel} resolves outside the project; refusing")
    return entries, sorted(kept)


def trash_folder(root: Path) -> Path:
    base = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    dest = root / TRASH / base
    n = 1
    while os.path.lexists(dest):
        n += 1
        dest = root / TRASH / f"{base}-{n}"
    return dest


def prune(root: Path, parents: set) -> None:
    """Remove the deeper folders a move left empty, deepest first. Standard and top-level folders stay."""
    for folder in sorted(parents, key=lambda p: p.count("/"), reverse=True):
        if folder in STANDARD_FOLDERS or "/" not in folder:
            continue
        path = root / folder
        try:
            if path.is_dir() and not path.is_symlink() and not any(path.iterdir()):
                path.rmdir()
        except OSError:
            pass


def execute(root: Path, scope: str, entries: list) -> Path:
    dest = trash_folder(root)
    dest.mkdir(parents=True)
    moved, parents, error = [], set(), ""
    try:
        for rel, kind, size in entries:
            target = dest / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            os.rename(root / rel, target)  # renames a symbolic link itself; it never follows one
            moved.append({"path": rel, "kind": kind, "bytes": size})
            parent = rel.rpartition("/")[0]
            while parent:
                parents.add(parent)
                parent = parent.rpartition("/")[0]
    except OSError as exc:
        error = str(exc)
    prune(root, parents)
    manifest = {"schema": 1, "project": str(root), "scope": scope, "created": jc.now_iso(),
                "complete": not error, "entries": moved}
    if error:
        manifest["error"] = error
    jc.write_json(dest / MANIFEST, manifest)
    if error:
        raise ResetError(f"move failed after {len(moved)} of {len(entries)} entries ({error}); the moved entries "
                         f"and {MANIFEST} are under {dest}")
    return dest


def render(result: dict) -> str:
    entries = result["entries"]
    lines = [f"Project: {result['project']}", f"Scope: {result['scope']}"]
    if not entries:
        lines.append("Nothing to reset in this scope.")
    else:
        head = "Moved" if result["executed"] else "Would move"
        lines.append(f"{head} {len(entries)} entries, {result['total_bytes']} bytes of files:")
        for entry in entries:
            size = "symbolic link, not followed" if entry["kind"] == "link" else f"{entry['bytes']} bytes"
            lines.append(f"  {entry['path']}  ({size})")
    if result["kept"]:
        lines.append("Kept: " + ", ".join(result["kept"]))
    if result["executed"]:
        lines.append(f"Trash: {result['trash']} (see {MANIFEST}). Nothing was deleted.")
    elif entries:
        lines.append(f"Nothing was moved. To move these entries to {TRASH}/, run again with --confirm {CONFIRM}.")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Preview, then move (never delete) a project's personal data to "
                                                 ".trash. Without --confirm RESET nothing changes.")
    parser.add_argument("--project", required=True, help="the project folder (one person's search)")
    parser.add_argument("--scope", required=True, choices=SCOPES, help="profile, documents or all")
    parser.add_argument("--confirm", metavar=CONFIRM, help=f"move the listed entries; the value must be {CONFIRM}")
    parser.add_argument("--json", action="store_true", help="print the plan or the result as JSON")
    args = parser.parse_args(argv)
    if args.confirm is not None and args.confirm != CONFIRM:
        print(f"error: --confirm takes exactly {CONFIRM}; nothing was moved", file=sys.stderr)
        return 2
    try:
        root = project_root(args.project)
        entries, kept = plan(root, args.scope)
    except ResetError as exc:
        print(f"refused: {exc}. Nothing was moved.", file=sys.stderr)
        return 1
    try:
        executed = args.confirm == CONFIRM and bool(entries)
        trash = execute(root, args.scope, entries) if executed else None
    except ResetError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    result = {"project": str(root), "scope": args.scope, "executed": executed,
              "entries": [{"path": rel, "kind": kind, "bytes": size} for rel, kind, size in entries],
              "total_bytes": sum(size for _rel, kind, size in entries if kind == "file"),
              "kept": kept, "trash": str(trash) if trash else None}
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
