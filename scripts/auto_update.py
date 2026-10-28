#!/usr/bin/env python3
"""Update the builder and every installed squad from the squads repo, with no model and no tokens.

The one update path: cron `builder-update` runs it daily with --no-agent, and the user's "update yourself" runs
`scripts/hpy auto_update.py --force`. Steps:
  1. Compare the installed distribution.yaml with the repo's (default branch). Same version and no bot lagging
     behind this checkout: print nothing (a silent cron tick). --force always continues.
  2. Save a copy of every shipped file edited since the last update (local/backups/edits-<stamp>/).
  3. Only when the repo version is higher: `hermes profile update <builder> --yes`. It replaces only the files the
     distribution ships; memories, sessions, .env, config.yaml, local/ and learned skills stay. Hermes replaces a
     shipped skill directory whole, so local edits to it (the background skill review patches the skills it used)
     would be lost: each edited file under skills/ is merged three ways afterwards (merge3.py) against the copy
     shipped by the last update (local/state/shipped/). An edit to a file the update did not change is kept as is;
     non-overlapping changes are combined; an overlap keeps the new version and reports `Needs you` with the backup.
  4. `squadctl upgrade`: applies this checkout to the builder and every installed squad. It keeps learned skills,
     memories, the user's model choices and SOUL edits, fills only lanes the new version added, and skips a squad
     whose board has running cards (retried on the next run).
  5. Print a short list: version change, what changed (CHANGELOG), new squads, anything waiting for the user.
  6. Prune the automatic backups under local/backups/ (edits-*, skill-edits-*, <bot>-SOUL-*.md, desktop-*-stale-*)
     older than 14 days, keeping the newest 3 of each kind. A backup the user made by hand is never touched.

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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import merge3  # noqa: E402

RAW = "https://raw.githubusercontent.com/PuntoyComaTech/hermes-agent-squads/HEAD"
SHIPPED = ("SOUL.md", "builder.yaml", "skills", "scripts", "squads")
MERGED = ("skills",)  # where local edits are learned lessons: merged, not overwritten
SKIP = {"__pycache__", ".squad-sha", ".DS_Store"}
SHAS = "dist-files.json"
SNAPSHOT = "shipped"  # local/state/shipped/<path>: each shipped file as the last update left it (the merge base)


def home() -> Path:
    raw = os.environ.get("HERMES_HOME")
    return Path(raw).expanduser() if raw else Path.home() / ".hermes" / "profiles" / "builder"


def version_of(text: str) -> str | None:
    m = re.search(r"^version:\s*[\"']?(\d+\.\d+\.\d+)", text, re.M)
    return m.group(1) if m else None


def vtuple(v: str | None) -> tuple:
    return tuple(int(x) for x in v.split(".")) if v else ()


def remote_version(raw: str, timeout: int) -> str | None:
    req = urllib.request.Request(f"{raw.rstrip('/')}/distribution.yaml",
                                 headers={"User-Agent": "hermes-squads-auto-update"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return version_of(r.read().decode("utf-8", "replace"))


def shipped_files(h: Path) -> dict[str, str]:
    out = {}
    for root in SHIPPED:
        p = h / root
        files = [p] if p.is_file() else (sorted(p.rglob("*")) if p.is_dir() else [])
        for f in files:
            parts = f.relative_to(h).parts
            # dot entries (.usage.json, .curator_ledger.jsonl, .hub/) are runtime state, never shipped content
            if f.is_file() and not SKIP & set(parts) and not any(p.startswith(".") for p in parts):
                out[str(f.relative_to(h))] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def edited_files(h: Path, state: Path) -> dict[str, bytes]:
    """{path: current bytes} of shipped files whose content changed since the last update."""
    rec = state / SHAS
    if not rec.is_file():
        return {}
    before = json.loads(rec.read_text())
    return {f: (h / f).read_bytes() for f, s in shipped_files(h).items() if f in before and before[f] != s}


def save_local_edits(h: Path, edits: dict[str, bytes]) -> Path | None:
    """Copy edited shipped files to local/backups/edits-<stamp>/ before anything replaces them."""
    if not edits:
        return None
    dest = h / "local" / "backups" / f"edits-{time.strftime('%Y%m%d-%H%M%S')}"
    for f, data in edits.items():
        (dest / f).parent.mkdir(parents=True, exist_ok=True)
        (dest / f).write_bytes(data)
    return dest


def merge_back(h: Path, state: Path, edits: dict[str, bytes]) -> dict:
    """After `hermes profile update`: re-apply local edits under MERGED roots.

    Returns {kept, merged, conflicts: [paths], shipped: {path: bytes}}. `shipped` is the new shipped content of every
    file written here (the next merge base). base = the file as the last update shipped it (local/state/shipped/; with
    no snapshot yet, the new shipped file when its hash equals the one recorded at the last update, i.e. the update
    did not change it). A conflict keeps the local edit on disk (what the bot learned is never taken away) and records
    the new shipped file as the next merge base; the caller saves that upstream version beside the backup."""
    recorded = json.loads((state / SHAS).read_text()) if (state / SHAS).is_file() else {}
    out: dict = {"kept": [], "merged": [], "conflicts": [], "shipped": {}}
    for f, ours in sorted(edits.items()):
        if not f.startswith(tuple(f"{r}/" for r in MERGED)):
            continue
        path = h / f
        theirs = path.read_bytes() if path.is_file() else None
        if ours == theirs:
            continue  # the update shipped the very same edit (it went upstream)
        snap = state / SNAPSHOT / f
        if snap.is_file():
            base = snap.read_bytes()
        elif theirs is not None and recorded.get(f) == sha(theirs):
            base = theirs
        else:
            base = None
        result, clean = merge3.merge_bytes(base, ours, theirs, prefer="ours") if base is not None else (ours, False)
        if not clean:
            out["conflicts"].append(f)
            if theirs is not None:
                out["shipped"][f] = theirs
                out.setdefault("upstream", {})[f] = theirs
            if result is None:
                path.unlink(missing_ok=True)  # deleted here on purpose: it stays deleted
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(result)
            continue
        if result is None:
            continue
        if theirs is not None:
            out["shipped"][f] = theirs
        if result != theirs:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(result)
        out["kept" if theirs == base else "merged"].append(f)
    return out


def write_snapshot(h: Path, state: Path, shipped: dict[str, bytes] | None = None) -> None:
    """Record what this update shipped: hashes of every shipped file and copies under MERGED (the next merge base).

    A file that holds a re-applied local edit is recorded with its shipped content (`shipped`), not the edited one,
    so the next update still sees the edit and merges it again instead of overwriting it."""
    shipped = shipped or {}
    files = shipped_files(h)
    files.update({f: sha(data) for f, data in shipped.items()})
    snap, tmp = state / SNAPSHOT, state / f"{SNAPSHOT}.new"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for f in files:
        if f.startswith(tuple(f"{r}/" for r in MERGED)):
            (tmp / f).parent.mkdir(parents=True, exist_ok=True)
            (tmp / f).write_bytes(shipped[f] if f in shipped else (h / f).read_bytes())
    shutil.rmtree(snap, ignore_errors=True)
    tmp.rename(snap)
    (state / SHAS).write_text(json.dumps(files))


def squads_in(h: Path) -> dict[str, str]:
    out = {}
    for y in sorted((h / "squads").glob("*/squad.yaml")):
        if y.parent.name.startswith("_"):
            continue
        text = y.read_text(encoding="utf-8")
        name = re.search(r"^name:\s*[\"']?(.+?)[\"']?\s*$", text, re.M)
        desc = re.search(r"^description:\s*[\"']?(.+?)[\"']?\s*$", text, re.M)
        out[y.parent.name] = f"{name.group(1) if name else y.parent.name}: {desc.group(1) if desc else ''}".rstrip(": ")
    return out


def changelog(h: Path, old: str | None, new: str, limit: int = 8) -> list[str]:
    """First sentence of every `- ` bullet of the CHANGELOG sections in (old, new], at most `limit`."""
    text = (h / "CHANGELOG.md").read_text(encoding="utf-8") if (h / "CHANGELOG.md").is_file() else ""
    out: list[str] = []
    for m in re.finditer(r"^## (\d+\.\d+\.\d+)[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S):
        if (old and vtuple(m.group(1)) <= vtuple(old)) or vtuple(m.group(1)) > vtuple(new):
            continue
        for b in re.findall(r"^- (.+(?:\n  .+)*)", m.group(2), re.M):
            first = re.split(r"(?<=[.:])\s", " ".join(b.split()), maxsplit=1)[0].rstrip(":.")
            out.append(first if len(first) <= 110 else first[:107] + "...")
    return out[:limit] + ([f"... and {len(out) - limit} more in CHANGELOG.md"] if len(out) > limit else [])


AUTO_BACKUP = re.compile(r"^(edits|skill-edits(?:-pre-[\d.]+)?|desktop-[\w-]+-stale|[\w-]+-SOUL)-\d{8}")
BACKUP_DAYS, BACKUP_KEEP = 14, 3


def prune_backups(h: Path, now: float | None = None) -> list[str]:
    """Remove automatic backups older than BACKUP_DAYS, keeping the newest BACKUP_KEEP of each kind. Returns the
    names removed. Anything that does not look like an automatic backup (a hand export) stays."""
    root = h / "local" / "backups"
    now = time.time() if now is None else now
    kinds: dict[str, list[Path]] = {}
    for p in root.iterdir() if root.is_dir() else []:
        m = AUTO_BACKUP.match(p.name)
        if m:
            kinds.setdefault(re.sub(r"-pre-[\d.]+$", "", m.group(1)), []).append(p)
    gone = []
    for items in kinds.values():
        for p in sorted(items, key=lambda q: q.stat().st_mtime, reverse=True)[BACKUP_KEEP:]:
            if now - p.stat().st_mtime > BACKUP_DAYS * 86400:
                shutil.rmtree(p) if p.is_dir() else p.unlink()
                gone.append(p.name)
    return sorted(gone)


def run(argv: list[str], root: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    """A hermes or squadctl run against this install's root (never a profile home: `hermes profile` resolves
    profiles under HERMES_HOME)."""
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "PYTHONHOME")}
    env["HERMES_HOME"] = str(root)
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)


def upgrade(h: Path, root: Path, dry: bool) -> tuple[dict | None, str]:
    """(report, error) of `squadctl upgrade` run with this checkout's own scripts."""
    argv = [str(h / "scripts" / "hpy"), "squadctl.py", "upgrade", "--builder", h.name, "--hermes-root", str(root),
            "--json", *(["--dry-run"] if dry else [])]
    p = run(argv, root)
    try:
        rep = json.loads(p.stdout)
    except ValueError:
        return None, (p.stderr or p.stdout).strip()[-400:]
    return (None, rep["error"]) if "error" in rep and "applied" not in rep else (rep, "")


def main(argv: list[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(description=doc.split("\n\n")[0], epilog=doc.split("\n\n", 1)[-1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--force", action="store_true",
                    help="manual run: bring every bot up to this version even when nothing is new, and always report")
    ap.add_argument("--check", action="store_true", help="only report whether an update exists; change nothing")
    ap.add_argument("--raw-url", default=RAW, help="raw base URL of the squads repo at its default branch (tests: file://)")
    ap.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds (default 20)")
    a = ap.parse_args(argv)

    h = home()
    root = h.parent.parent
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
        new = remote_version(a.raw_url, a.timeout)
    except OSError as exc:
        print(f"Squads update check failed: {exc}", file=sys.stderr)
        return 1
    if not new:
        print("Squads update check failed: the repo's distribution.yaml has no version", file=sys.stderr)
        return 1
    rose = vtuple(new) > vtuple(old)
    if a.check:
        if rose:
            print(f"Squads update available: {old or '?'} -> {new}")
        return 0
    if not rose and not a.force:
        lag, err = upgrade(h, root, dry=True)
        if lag is None:
            print(f"squadctl upgrade --dry-run failed: {err}", file=sys.stderr)
            return 1
        if not lag.get("applied") and not lag.get("lanes_added"):
            if not (state / SHAS).is_file():
                write_snapshot(h, state)
            prune_backups(h)  # silent: housekeeping is no news
            return 0

    edits = edited_files(h, state)
    backup = save_local_edits(h, edits) if rose else None  # only `hermes profile update` replaces files
    before = squads_in(h)
    merged: dict = {"kept": [], "merged": [], "conflicts": [], "shipped": {}}
    if rose:
        p = run(["hermes", "profile", "update", h.name, "--yes"], root)
        if p.returncode != 0:
            print(f"Squads update {old} -> {new} failed at `hermes profile update`: "
                  f"{(p.stderr or p.stdout).strip()[-400:]}", file=sys.stderr)
            return 1
        merged = merge_back(h, state, edits)
    rep, err = upgrade(h, root, dry=False)
    if rep is None:
        print(f"squadctl upgrade failed: {err}", file=sys.stderr)
        return 1
    if rose or not (state / SNAPSHOT).is_dir():
        write_snapshot(h, state, merged["shipped"])
    else:
        # no new release: local edits stay exactly as they are and stay counted as edits
        recorded = json.loads((state / SHAS).read_text()) if (state / SHAS).is_file() else {}
        (state / SHAS).write_text(json.dumps({**shipped_files(h), **{f: recorded[f] for f in edits if f in recorded}}))
    notes = []
    if merged["kept"]:
        notes.append(f"Kept your edits to {len(merged['kept'])} skill file(s) the update did not change: "
                     + ", ".join(merged["kept"]))
    if merged["merged"]:
        notes.append(f"Merged your edits into {len(merged['merged'])} updated skill file(s): "
                     + ", ".join(merged["merged"]))
    for f, data in (merged.get("upstream") or {}).items():
        if backup:
            (backup / "upstream" / f).parent.mkdir(parents=True, exist_ok=True)
            (backup / "upstream" / f).write_bytes(data)
    notes += [f"Needs you: {f} changed both here and upstream; your edit stays in place, the new version is in "
              f"{backup / 'upstream' / f}" for f in merged["conflicts"] if backup]
    if backup:
        notes.append(f"{len(edits)} edited shipped file(s) saved to {backup}")

    after = squads_in(h)
    lines = [f"Squads updated {old} -> {new}" if rose else
             f"Squads {old}: {'bots brought up to date' if rep.get('applied') else 'everything is up to date'}"]
    lines += [f"- {c}" for c in changelog(h, old, new)] if rose else []
    lines += [f"- {key}: {r['bots']} bot(s) updated" for key, r in (rep.get("applied") or {}).items()]
    lines += [f"- New squad available: {after[k]}. Tell me \"install {k}\" to add it."
              for k in sorted(set(after) - set(before))]
    lines += [f"- New lane {lane}: {m['model']} ({m['provider']}); change it any time"
              for lane, m in (rep.get("lanes_added") or {}).items()]
    lines += [f"- Kept your model: {m}" for m in rep.get("models_kept") or []]
    lines += [f"- Waiting: {w} (retried on the next run)" for w in rep.get("waiting") or []]
    lines += [f"- Needs you: {x}" for x in rep.get("pending") or []]
    lines += [f"- {n}" for n in notes]
    lines += [f"- Error: {e}" for e in rep.get("errors") or []]
    pruned = prune_backups(h)
    if pruned:
        lines.append(f"- Removed {len(pruned)} automatic backup(s) older than {BACKUP_DAYS} days")
    print("\n".join(lines))
    return 1 if rep.get("errors") else 0


if __name__ == "__main__":
    sys.exit(main())
