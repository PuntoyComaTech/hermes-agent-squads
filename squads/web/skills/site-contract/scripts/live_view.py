#!/usr/bin/env python3
"""Keep a site's dev server running so the user watches the work live in a tab beside the chat.

`start` finds the running server of this repo (the PID file under the repo's `.hermes-live/`), else starts the
stack's `dev` script on a free port in the background, detached from the caller, waits until it answers and prints
`{"url": ...}`. The manager opens that URL with `desktop_preview` (a tab beside the chat, never a link or an inline
preview in the message). The dev server reloads on every file a builder saves, so the tab follows the work.
`stop` ends it; `status` says whether it answers.

The builders write in this same working tree (their card's site folder), so the tab shows every file the moment it
is saved, before any commit. `.hermes-live/` (PID, port, log) is added to `.git/info/exclude`, never committed.

Exit 0 running (or stopped), 1 it could not start (no base yet, or no answer: the server is stopped), 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from toolpath import augment_path  # noqa: E402

STATE = ".hermes-live"
WAIT_S = 90


def free_port(preferred: int) -> int:
    for port in [preferred, *range(preferred + 1, preferred + 50)]:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def answers(url: str) -> bool:
    """True when anything answers HTTP at url: a dev server showing a compile error (500) is alive, not gone."""
    try:
        with urllib.request.urlopen(url, timeout=3):  # noqa: S310 - localhost only
            return True
    except urllib.error.HTTPError:
        return True
    except Exception:  # noqa: BLE001 - refused, timeout: nothing listens yet
        return False


def state_of(repo: Path) -> dict:
    path = repo / STATE / "server.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def exclude(repo: Path) -> None:
    """Keep the state folder out of git without touching the user's .gitignore."""
    info = repo / ".git" / "info" / "exclude"
    if info.parent.is_dir():
        text = info.read_text(encoding="utf-8") if info.is_file() else ""
        if f"{STATE}/" not in text.split():
            info.write_text(text + ("" if text.endswith("\n") or not text else "\n") + f"{STATE}/\n", encoding="utf-8")


def dev_argv(pnpm: str, repo: Path, port: int) -> list[str]:
    """The stack's dev script on `port`, bound to localhost: Next names the host flag --hostname, Vite and Astro
    --host."""
    try:
        dev = json.loads((repo / "package.json").read_text(encoding="utf-8")).get("scripts", {}).get("dev", "")
    except (OSError, ValueError):
        dev = ""
    host = "--hostname" if dev.strip().startswith("next") else "--host"
    return [pnpm, "run", "dev", "--port", str(port), host, "127.0.0.1"]


def default_port(repo: Path) -> int:
    """The stack's usual port: Next 3000, Vite 5173 or the TanStack 3000, Astro 4321."""
    try:
        dev = json.loads((repo / "package.json").read_text(encoding="utf-8")).get("scripts", {}).get("dev", "")
    except (OSError, ValueError):
        return 4321
    return 4321 if "astro" in dev else 3000


def start(repo: Path, port: int) -> dict:
    current = state_of(repo)
    if current.get("pid") and alive(int(current["pid"])):
        # the recorded server is ours and alive: reuse it even while it shows an error page
        return {**current, "running": True, "reused": True, "answers": answers(current.get("url", ""))}
    pnpm = shutil.which("pnpm")
    if not pnpm:
        return {"running": False, "error": "pnpm is not on PATH: run site_base.py --install first"}
    port = free_port(port)
    url = f"http://localhost:{port}"
    (repo / STATE).mkdir(exist_ok=True)
    exclude(repo)
    log = (repo / STATE / "server.log").open("w", encoding="utf-8")
    env = {**os.environ, "PORT": str(port), "BROWSER": "none"}
    proc = subprocess.Popen(dev_argv(pnpm, repo, port), cwd=repo,
                            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, env=env,
                            start_new_session=True)
    row = {"pid": proc.pid, "url": url, "port": port, "repo": str(repo)}
    (repo / STATE / "server.json").write_text(json.dumps(row), encoding="utf-8")  # `stop` can always reach it
    deadline = time.time() + WAIT_S
    while time.time() < deadline and proc.poll() is None:
        if answers(url):
            return {**row, "running": True, "reused": False}
        time.sleep(1)
    stop(repo)  # never leave a server that did not come up
    tail = (repo / STATE / "server.log").read_text(encoding="utf-8", errors="ignore")[-1200:]
    return {"running": False, "error": f"the dev server did not answer on {url} within {WAIT_S} s", "tail": tail}


def stop(repo: Path) -> dict:
    current = state_of(repo)
    pid = int(current.get("pid") or 0)
    if pid and alive(pid):
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            os.kill(pid, signal.SIGTERM)
    (repo / STATE / "server.json").unlink(missing_ok=True)
    return {"running": False, "stopped": bool(pid)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0],
                                epilog="Exit 0 running or stopped, 1 could not start, 2 usage error.")
    p.add_argument("action", choices=["start", "stop", "status"])
    p.add_argument("--repo", required=True, help="the site repo the user watches")
    p.add_argument("--port", type=int, help="preferred port (default: the stack's; the next free one is used)")
    args = p.parse_args(argv)
    augment_path()
    repo = Path(args.repo).expanduser().resolve()
    if not (repo / "package.json").is_file():
        print(json.dumps({"running": False, "error": f"{repo} has no package.json: lay the base first (site_base.py)"}))
        return 1
    if args.action == "start":
        row = start(repo, args.port or default_port(repo))
    elif args.action == "stop":
        row = stop(repo)
    else:
        cur = state_of(repo)
        up = bool(cur.get("pid")) and alive(int(cur["pid"]))
        row = {**cur, "running": up, "answers": up and answers(cur.get("url", ""))}
    print(json.dumps(row, indent=2))
    return 0 if row.get("running") or args.action == "stop" else 1


if __name__ == "__main__":
    sys.exit(main())
