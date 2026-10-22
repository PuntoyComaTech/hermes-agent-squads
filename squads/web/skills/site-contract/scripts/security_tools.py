#!/usr/bin/env python3
"""The web squad's security scanners, installed and kept current by their official installer.

`status` lists each tool: found (PATH and Homebrew's folders) and its version. `ensure <tool>...` installs what is
missing with `brew install <formula>`: osv-scanner, gitleaks, nuclei and semgrep all ship official Homebrew formulae
on macOS and Linux, and `brew upgrade` keeps them current. Without Homebrew it stops and says so; it never downloads
a binary itself. `nuclei` also needs its template set: `nuclei -update-templates` first and, when its 60-second
downloader cannot finish on a slow link, a shallow `git clone` of the official template repository. The set is
refreshed weekly; nuclei never runs its code-protocol templates unless asked to (`-code`), and the audit does not.

Exit 0 every requested tool is ready, 1 one could not be installed (its JSON row says why), 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from toolpath import augment_path, tools_dir  # noqa: E402

CONFIG = json.loads((HERE / "stacks.json").read_text(encoding="utf-8")).get("security_tools", {})
FORMULAE = CONFIG.get("formulae", {})
TOOLS = ("osv-scanner", "gitleaks", "nuclei", "semgrep")
TEMPLATES_MAX_AGE = 7 * 24 * 3600


def which(tool: str) -> str | None:
    augment_path()
    return shutil.which(tool)


def version(tool: str) -> str | None:
    path = which(tool)
    if not path:
        return None
    flag = {"gitleaks": "version", "nuclei": "-version"}.get(tool, "--version")
    try:
        done = subprocess.run([path, flag], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    lines = [ln.strip() for ln in (done.stdout + done.stderr).splitlines() if any(ch.isdigit() for ch in ln)]
    return lines[0][:80] if lines else "unknown"


def templates_dir() -> Path:
    return tools_dir() / "nuclei-templates"


def templates_ready() -> bool:
    return any(templates_dir().glob("http/**/*.yaml"))


def ensure_templates() -> dict:
    """nuclei's official template set in the squad's folder: nuclei's own updater, else a shallow clone of the
    official repository (git has no 60-second cap). Refreshed when older than a week; a failed refresh keeps the
    set already there."""
    folder = templates_dir()
    stamp = folder / ".fetched"
    if templates_ready() and stamp.is_file() and time.time() - stamp.stat().st_mtime < TEMPLATES_MAX_AGE:
        return {}
    folder.parent.mkdir(parents=True, exist_ok=True)
    tried = []
    nuclei = which("nuclei")
    if nuclei:
        done = subprocess.run([nuclei, "-update-templates", "-update-template-dir", str(folder)], capture_output=True,
                              text=True, timeout=600, stdin=subprocess.DEVNULL,
                              env={**os.environ, "HOME": str(tools_dir())})
        tried.append(f"nuclei -update-templates (exit {done.returncode})")
    if not templates_ready() and which("git"):
        work = folder.with_name(folder.name + ".clone")
        shutil.rmtree(work, ignore_errors=True)
        done = subprocess.run([which("git") or "git", "clone", "--depth", "1", "--quiet", CONFIG["nuclei_templates"],
                               str(work)], capture_output=True, text=True, timeout=1800, stdin=subprocess.DEVNULL)
        tried.append(f"git clone (exit {done.returncode})")
        if done.returncode == 0 and any(work.glob("http/**/*.yaml")):
            shutil.rmtree(folder, ignore_errors=True)
            work.rename(folder)
        shutil.rmtree(work, ignore_errors=True)
    if not templates_ready():
        return {"ready": False, "detail": "nuclei templates could not be fetched: " + "; ".join(tried)}
    stamp.write_text(time.strftime("%Y-%m-%d"), encoding="utf-8")
    return {"detail": "nuclei templates ready: " + "; ".join(tried)}


def ensure(tool: str) -> dict:
    formula = FORMULAE.get(tool)
    if not formula:
        return {"tool": tool, "ready": False, "detail": f"no Homebrew formula for {tool} in stacks.json"}
    if which(tool):
        row = {"tool": tool, "ready": True, "detail": "already installed"}
    else:
        brew = which("brew")
        if not brew:
            return {"tool": tool, "ready": False,
                    "detail": f"{tool} is missing and Homebrew, its official installer, is not: install Homebrew "
                              f"(https://brew.sh), then run `brew install {formula}`"}
        done = subprocess.run([brew, "install", formula], capture_output=True, text=True, timeout=1800,
                              stdin=subprocess.DEVNULL)
        ok = done.returncode == 0 and bool(which(tool))
        row = {"tool": tool, "ready": ok,
               "detail": f"brew install {formula}" if ok else (done.stdout + done.stderr).strip()[-400:]}
    if row["ready"]:
        row["version"] = version(tool)
        if tool == "nuclei":
            row.update(ensure_templates())
    return row


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0],
                                epilog="Exit 0 ready, 1 an install failed, 2 usage error.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="found tools and their versions")
    en = sub.add_parser("ensure", help="install what is missing (brew)")
    en.add_argument("tools", nargs="+", help="osv-scanner gitleaks nuclei semgrep")
    args = p.parse_args(argv)
    if args.cmd == "status":
        rows = [{"tool": t, "path": which(t), "version": version(t),
                 "ready": bool(which(t)) and (t != "nuclei" or templates_ready())} for t in TOOLS]
        print(json.dumps({"templates": str(templates_dir()), "tools": rows}, indent=2))
        return 0 if all(r["ready"] for r in rows) else 1
    unknown = [t for t in args.tools if t not in TOOLS]
    if unknown:
        print(f"error: unknown tool(s) {', '.join(unknown)}; known: {', '.join(TOOLS)}", file=sys.stderr)
        return 2
    rows = [ensure(t) for t in args.tools]
    print(json.dumps({"tools": rows}, indent=2))
    return 0 if all(r["ready"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
