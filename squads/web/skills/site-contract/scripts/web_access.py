#!/usr/bin/env python3
"""Get the site's deploy access ready with no work for the user beyond one click: GitHub (`gh`) and the hosting CLI.

`status` reads what already works: each CLI found (PATH, else its official package through `pnpm dlx`) and whether its stored login
is valid. A login the user already has is reused, never asked again. Nothing secret is printed: only exit codes are
read for the login checks.

`ensure <tool>` makes one tool ready: when the CLI is missing it is installed (gh with Homebrew, its official
installer; cf, wrangler and vercel run as `pnpm dlx <tool>@latest` under the squad's 3-day release-age rule, or
`npx <tool>@latest` without pnpm, nothing global); when it is not logged in it starts the CLI's own browser login in
the background and prints the URL (and the one-time code for a device login) for the manager to open as a tab beside
the chat. The user approves it there; `wait <tool>` then polls until the login is valid. The bot never types a
password, a code or a token: the user's click in the provider's own page is the credential.

Exit 0 ready (or `ensure` started a login and printed its URL), 1 not ready or failed, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from toolpath import augment_path  # noqa: E402

STACKS = HERE / "stacks.json"
_STACKS = json.loads(STACKS.read_text(encoding="utf-8")) if STACKS.is_file() else {}
PACKAGED = ("wrangler", "cf", "vercel")  # official npm packages, run without a global install
AGE = str((_STACKS.get("pnpm") or {}).get("minimumReleaseAge", 4320))
URL_RE = re.compile(r"https://\S+")
CODE_RE = re.compile(r"(?:one-time code|enter the code)[:\s]*\n?\s*([A-Za-z0-9]{4}-?[A-Za-z0-9]{4})", re.I)
TOOLS = ("gh", "cf", "wrangler", "vercel")
LOG_DIR = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")) / "cache" / "web-access"


def launcher(tool: str) -> list[str] | None:
    """How to run the tool here: on PATH, else its official package through pnpm dlx (3-day rule) or npx; None
    when it cannot run."""
    if shutil.which(tool):
        return [tool]
    if tool in PACKAGED and shutil.which("pnpm"):
        return ["pnpm", f"--config.minimum-release-age={AGE}", "dlx", f"{tool}@latest"]
    if tool in PACKAGED and shutil.which("npx"):
        return ["npx", "--yes", f"{tool}@latest"]
    return None


def quiet(argv: list[str], timeout: int = 120) -> int:
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL).returncode
    except (OSError, subprocess.TimeoutExpired):
        return 1


LOGIN_CHECK = {"gh": ["auth", "status"], "cf": ["auth", "whoami"], "wrangler": ["whoami"], "vercel": ["whoami"]}
LOGIN_START = {"gh": ["auth", "login", "--web", "-h", "github.com", "-p", "https", "-s", "repo,workflow",
                      "--skip-ssh-key"] + (["--clipboard"] if sys.platform == "darwin" else []),
               "cf": ["auth", "login", "--no-browser"],
               "wrangler": ["login", "--browser=false"],
               "vercel": ["login"]}


def logged_in(tool: str, argv: list[str]) -> bool:
    """True only for a valid stored login. `cf auth whoami` and `wrangler whoami` exit 0 when logged out, so their
    output is read here (never printed): cf answers JSON `authenticated`, wrangler says "not authenticated"."""
    try:
        done = subprocess.run(argv + LOGIN_CHECK[tool], capture_output=True, text=True, timeout=120,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return False
    if done.returncode != 0:
        return False
    text = done.stdout + done.stderr
    if tool == "cf":
        try:
            return json.loads(done.stdout).get("authenticated") is True
        except (ValueError, AttributeError):
            return False
    if tool == "wrangler":
        low = text.lower()
        return "not authenticated" not in low and "not logged in" not in low and "logged in" in low
    return True


def status_of(tool: str) -> dict:
    argv = launcher(tool)
    if argv is None:
        return {"tool": tool, "installed": False, "logged_in": False}
    return {"tool": tool, "installed": True, "runs_as": " ".join(argv), "logged_in": logged_in(tool, argv)}


def install(tool: str) -> dict:
    if tool == "gh":
        if not shutil.which("brew"):
            return {"ok": False, "detail": "gh is missing and Homebrew is not installed: https://cli.github.com"}
        rc = quiet(["brew", "install", "gh"], timeout=900)
        return {"ok": rc == 0 and bool(shutil.which("gh")), "detail": "brew install gh"}
    argv = launcher(tool)
    if not argv:
        return {"ok": False, "detail": "pnpm and npx are missing: install Node.js 22+ (https://nodejs.org)"}
    rc = quiet(argv + ["--version"], timeout=900)  # the first run downloads the package once
    return {"ok": rc == 0, "detail": " ".join(argv) + " --version"}


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def start_login(tool: str, argv: list[str]) -> dict:
    """Start the CLI's login in the background; return the URL and code it prints for the user. A login of this tool
    still waiting for the user is reused (same URL and code), never started twice."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / f"{tool}-login.log"
    pid_file = LOG_DIR / f"{tool}-login.pid"
    try:
        old = int(pid_file.read_text().strip())
    except (OSError, ValueError):
        old = 0
    if not (old and _alive(old)):
        env = {**os.environ, "BROWSER": "echo", "GH_BROWSER": "echo"}  # print the URL; the manager opens a tab
        with log.open("w", encoding="utf-8") as out:
            proc = subprocess.Popen(argv + LOGIN_START[tool], stdout=out, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, env=env, start_new_session=True)
        pid_file.write_text(str(proc.pid), encoding="utf-8")
    for _ in range(60):
        time.sleep(0.5)
        text = log.read_text(encoding="utf-8", errors="ignore")
        urls = URL_RE.findall(text)
        if urls:
            hit = CODE_RE.search(text)
            code = hit.group(1) if hit else None
            url = urls[-1].rstrip(".,)")
            if not code:
                hit = re.search(r"user_code=([A-Za-z0-9-]+)", url)
                code = hit.group(1) if hit else None
            if tool == "cf" and code and "user_code=" not in url:  # cf's verify page takes the code: one click
                url += ("&" if "?" in url else "?") + f"user_code={code}"
            return {"started": True, "url": url, "code": code, "log": str(log)}
    return {"started": False, "detail": f"no login URL within 30 s; see {log}"}


def ensure(tool: str) -> dict:
    row = status_of(tool)
    if not row["installed"]:
        row["install"] = install(tool)
        if not row["install"]["ok"]:
            return row
        row = {**status_of(tool), "install": row["install"]}
    if row["logged_in"]:
        return {**row, "ready": True}
    row["login"] = start_login(tool, launcher(tool) or [tool])
    row["ready"] = False
    return row


def wait(tool: str, seconds: int) -> dict:
    argv = launcher(tool)
    deadline = time.time() + seconds
    while argv and time.time() < deadline:
        if logged_in(tool, argv):
            return {"tool": tool, "ready": True}
        time.sleep(5)
    return {"tool": tool, "ready": False, "detail": f"not logged in after {seconds} s"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0],
                                epilog="Exit 0 ready or login started, 1 not ready or failed, 2 usage error.")
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="what is installed and logged in")
    st.add_argument("tools", nargs="*", default=["gh", "cf", "wrangler"],
                    help="default: gh cf wrangler (the Cloudflare default); name vercel for a Vercel site")
    en = sub.add_parser("ensure", help="install when missing, start the login when logged out")
    en.add_argument("tool", choices=TOOLS)
    wt = sub.add_parser("wait", help="poll until the tool is logged in")
    wt.add_argument("tool", choices=TOOLS)
    wt.add_argument("--seconds", type=int, default=300)
    args = p.parse_args(argv)
    augment_path()
    if args.cmd == "status":
        unknown = [t for t in args.tools if t not in TOOLS]
        if unknown:
            print(f"error: unknown tool(s) {', '.join(unknown)}; known: {', '.join(TOOLS)}", file=sys.stderr)
            return 2
        rows = [status_of(t) for t in args.tools]
        print(json.dumps({"tools": rows}, indent=2))
        return 0 if all(r["logged_in"] for r in rows) else 1
    if args.cmd == "ensure":
        row = ensure(args.tool)
        print(json.dumps(row, indent=2))
        return 0 if row.get("ready") or (row.get("login") or {}).get("started") else 1
    row = wait(args.tool, args.seconds)
    print(json.dumps(row, indent=2))
    return 0 if row["ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
