#!/usr/bin/env python3
"""Update the builder and every installed squad from the squads repo, with no model and no tokens.

Cron `builder-update` runs it daily with --no-agent; the user's "update yourself" runs the same command. Steps:
  1. Compare the installed distribution.yaml with the repo's (default branch). Same version and nothing lagging:
     print nothing (a silent cron tick).
  2. Save a copy of every shipped file the user or the builder edited since the last update (local/backups/).
  3. `hermes profile update <builder> --yes`: replaces only the files the distribution ships; memories, sessions,
     .env, config.yaml, local/ and learned skills stay.
  4. `squadctl upgrade`: applies the new version to the builder and every installed squad. It keeps learned
     skills, memories, the user's model choices and SOUL edits, fills only lanes the new version added, and skips a
     squad whose board has running cards (retried on the next run).
  5. Print a short list: version change, what changed (CHANGELOG), new squads, anything waiting for the user.

Never runs `hermes update` (Hermes itself) and never installs a squad the user did not choose.
Stdlib only. Exit 0 on success or nothing to do, 1 on failure (cron then alerts once).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: no lock, one cron tick runs at a time anyway
    fcntl = None

RAW = "https://raw.githubusercontent.com/PuntoyComaTech/hermes-agent-squads/HEAD"
SHIPPED = ("SOUL.md", "builder.yaml", "skills", "scripts", "squads")
SKIP = {"__pycache__", ".squad-sha", ".DS_Store"}
SHAS = "dist-files.json"


def home() -> Path:
    raw = os.environ.get("HERMES_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".hermes" / "profiles" / "builder"


def version_of(text: str) -> str | None:
    m = re.search(r"^version:\s*[\"']?(\d+\.\d+\.\d+)", text, re.M)
    return m.group(1) if m else None


def vtuple(v: str | None) -> tuple:
    return tuple(int(x) for x in v.split(".")) if v else ()


def remote_version(timeout: int) -> str | None:
    req = urllib.request.Request(f"{RAW}/distribution.yaml", headers={"User-Agent": "hermes-squads-auto-update"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return version_of(r.read().decode("utf-8", "replace"))


def shipped_files(h: Path) -> dict[str, str]:
    out = {}
    for root in SHIPPED:
        p = h / root
        files = [p] if p.is_file() else (sorted(p.rglob("*")) if p.is_dir() else [])
        for f in files:
            if f.is_file() and not SKIP & set(f.relative_to(h).parts):
                out[str(f.relative_to(h))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def save_local_edits(h: Path, state: Path) -> list[str]:
    """Shipped files whose content changed since the last update are copied to local/backups/<stamp>/."""
    rec = state / SHAS
    if not rec.is_file():
        return []
    before = json.loads(rec.read_text())
    now = shipped_files(h)
    edited = [f for f, sha in now.items() if f in before and before[f] != sha]
    if edited:
        dest = h / "local" / "backups" / f"edits-{time.strftime('%Y%m%d-%H%M%S')}"
        for f in edited:
            (dest / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(h / f, dest / f)
        return [f"{len(edited)} edited shipped file(s) saved to {dest}"]
    return []


def squads_in(h: Path) -> dict[str, str]:
    out = {}
    for y in sorted((h / "squads").glob("*/squad.yaml")):
        if y.parent.name.startswith("_"):
            continue
        m = re.search(r"^description:\s*[\"']?(.+?)[\"']?\s*$", y.read_text(encoding="utf-8"), re.M)
        name = re.search(r"^name:\s*[\"']?(.+?)[\"']?\s*$", y.read_text(encoding="utf-8"), re.M)
        out[y.parent.name] = f"{name.group(1) if name else y.parent.name}: {m.group(1) if m else ''}".rstrip(": ")
    return out


def changelog(h: Path, old: str | None, new: str, limit: int = 8) -> list[str]:
    """`- ` bullets of every CHANGELOG section newer than `old`, first sentence each, at most `limit`."""
    text = (h / "CHANGELOG.md").read_text(encoding="utf-8") if (h / "CHANGELOG.md").is_file() else ""
    out: list[str] = []
    for m in re.finditer(r"^## (\d+\.\d+\.\d+)[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        if old and vtuple(m.group(1)) <= vtuple(old) or vtuple(m.group(1)) > vtuple(new):
            continue
        for b in re.findall(r"^- (.+(?:\n  .+)*)", m.group(2), re.M):
            line = " ".join(b.split())
            first = re.split(r"(?<=[.:])\s", line, maxsplit=1)[0].rstrip(":.")
            out.append(first if len(first) <= 110 else first[:107] + "...")
    return out[:limit] + ([f"... and {len(out) - limit} more in CHANGELOG.md"] if len(out) > limit else [])


def run(argv: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in ("HERMES_HOME", "PYTHONPATH", "PYTHONHOME")}
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)


def main(argv: list[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(description=doc.split("\n\n")[0], epilog=doc.split("\n\n", 1)[-1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="only report whether an update exists; change nothing")
    ap.add_argument("--force", action="store_true", help="run steps 3-5 even when the versions match")
    ap.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds (default 20)")
    a = ap.parse_args(argv)

    h = home()
    state = h / "local" / "state"
    state.mkdir(parents=True, exist_ok=True)
    lock = open(state / "auto_update.lock", "w")
    try:
        if fcntl:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return 0  # another run is updating
    dist = h / "distribution.yaml"
    old = version_of(dist.read_text()) if dist.is_file() else None
    try:
        new = remote_version(a.timeout)
    except OSError as exc:
        print(f"Squads update check failed: {exc}", file=sys.stderr)
        return 1
    if not new:
        return 0
    squadctl = [str(h / "scripts" / "hpy"), "squadctl.py", "--builder", h.name, "--hermes-root", str(h.parent.parent),
                "--json"]
    if vtuple(new) <= vtuple(old) and not a.force:
        lag = run([*squadctl[:2], "upgrade", "--dry-run", *squadctl[2:]])
        try:
            dry = json.loads(lag.stdout)
        except ValueError:
            dry = {}
        if not dry.get("applied") and not dry.get("lanes_added"):
            if not (state / SHAS).is_file():
                (state / SHAS).write_text(json.dumps(shipped_files(h)))
            return 0
    if a.check:
        print(f"Squads update available: {old or '?'} -> {new}")
        return 0

    notes = save_local_edits(h, state)
    before = squads_in(h)
    if vtuple(new) > vtuple(old):
        p = run(["hermes", "profile", "update", h.name, "--yes"])
        if p.returncode != 0:
            print(f"Squads update {old} -> {new} failed at `hermes profile update`: "
                  f"{(p.stderr or p.stdout).strip()[-400:]}", file=sys.stderr)
            return 1
    p = run([*squadctl[:2], "upgrade", *squadctl[2:]])
    try:
        rep = json.loads(p.stdout)
    except ValueError:
        print(f"squadctl upgrade failed: {(p.stderr or p.stdout).strip()[-400:]}", file=sys.stderr)
        return 1
    (state / SHAS).write_text(json.dumps(shipped_files(h)))

    lines = [f"Squads updated {old} -> {new}" if vtuple(new) > vtuple(old) else f"Squads {new}: bots brought up to date"]
    lines += [f"- {c}" for c in changelog(h, old, new)] if vtuple(new) > vtuple(old) else []
    for key, r in (rep.get("applied") or {}).items():
        lines.append(f"- {key}: {r['bots']} bot(s) updated")
    for key in sorted(set(squads_in(h)) - set(before)):
        lines.append(f"- New squad available: {squads_in(h)[key]}. Tell me \"install {key}\" to add it.")
    for lane, m in (rep.get("lanes_added") or {}).items():
        lines.append(f"- New lane {lane}: {m['model']} ({m['provider']}); change it any time")
    lines += [f"- Waiting: {w} (retried tomorrow)" for w in rep.get("waiting") or []]
    lines += [f"- Needs you: {x}" for x in rep.get("pending") or []]
    lines += [f"- {n}" for n in notes]
    lines += [f"- Error: {e}" for e in rep.get("errors") or []]
    print("\n".join(lines))
    return 1 if rep.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
