#!/usr/bin/env python3
"""Save a builder's work in progress: one commit on its `web/<ID>` branch, so the live preview and the manager see it.

A builder runs it after every finished piece (a component, a page, a route, a passing test), not only at the end of
the card. It stages only the paths the builder names with --paths (its own files: other bots may have work in progress
in the same tree), plus already-tracked changes under them, lets the pre-commit hook format and lint what changed (Biome), and
commits as `wip(<ID>): <what>`. It refuses `main`, refuses a branch that is not `web/<ID>`, never pushes, and writes
one line to `<site>/milestones/<ID>.progress.log` (time, commit, what) that the manager reads for status.

A hook failure is not skipped: the commit is not made, the hook's output tail is printed, and the builder fixes it
before going on. Nothing to commit exits 0 with `saved: false`.

Exit 0 saved or nothing to save, 1 refused or the hook failed, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ID_RE = re.compile(r"\A[a-z0-9][a-z0-9-]*-\d{8}-(?:build|change|bug|domain|rollback)-\d{2}\Z")
TAIL = 1500


def git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=600,
                          stdin=subprocess.DEVNULL)


def save(repo: Path, work_id: str, what: str, site: Path | None, paths: list[str]) -> dict:
    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != f"web/{work_id}":
        return {"saved": False, "ok": False,
                "error": f"on branch {branch!r}: progress commits go only to web/{work_id} (never main)"}
    foreign = [p for p in git(repo, "diff", "--cached", "--name-only").stdout.split()
               if not any(p == q or p.startswith(q.rstrip("/") + "/") for q in paths)]
    if foreign:
        return {"saved": False, "ok": False, "error": "the index already holds files outside --paths (another bot's "
                "work?); leave them alone and ask the manager", "files": foreign}
    git(repo, "add", "-A", "--", *paths)
    if not git(repo, "diff", "--cached", "--name-only").stdout.strip():
        return {"saved": False, "ok": True, "detail": "nothing changed since the last save"}
    done = git(repo, "commit", "-q", "-m", f"wip({work_id}): {what}", "--", *paths)
    if done.returncode:
        return {"saved": False, "ok": False, "error": "the pre-commit hook or git refused the commit; fix and rerun",
                "tail": (done.stdout + done.stderr)[-TAIL:]}
    sha = git(repo, "rev-parse", "--short", "HEAD").stdout.strip()
    files = git(repo, "show", "--name-only", "--format=", "HEAD").stdout.split()
    if site is not None:
        log = site / "milestones" / f"{work_id}.progress.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as out:
            out.write(f"{datetime.now().isoformat(timespec='seconds')} {sha} {what}\n")
    return {"saved": True, "ok": True, "commit": sha, "branch": branch, "files": files}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0],
                                epilog="Exit 0 saved or nothing to save, 1 refused or hook failed, 2 usage error.")
    p.add_argument("--repo", required=True, help="the site repo (<site>/<site.yaml repo.path>)")
    p.add_argument("--id", required=True, help="work item id, e.g. acme-20261022-build-01")
    p.add_argument("--what", required=True, help="what this save holds, a few words: 'hero section', 'menu page'")
    p.add_argument("--paths", nargs="+", required=True,
                   help="the files or folders this piece touched (only these are committed)")
    p.add_argument("--site", help="site folder for the progress log (default: the repo's parent when it has site.yaml)")
    args = p.parse_args(argv)
    if not ID_RE.match(args.id) or not args.what.strip():
        print("error: --id must be a work item id (<slug>-<YYYYMMDD>-<kind>-<nn>) and --what non-empty", file=sys.stderr)
        return 2
    repo = Path(args.repo).expanduser().resolve()
    site = Path(args.site).expanduser().resolve() if args.site else next(
        (d for d in (repo, repo.parent) if (d / "site.yaml").is_file()), None)
    result = save(repo, args.id, " ".join(args.what.split()), site, args.paths)
    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
