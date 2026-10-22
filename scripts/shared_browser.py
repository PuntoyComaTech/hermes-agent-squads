#!/usr/bin/env python3
"""The shared signed-in browser every squad bot with `shared_browser: true` drives.

One headless Chromium (Hermes's managed Chrome for Testing) on one profile directory, listening on a loopback CDP
port. Bots reach it through `browser.cdp_url`; each bot run works in its own tab (plugin shared-browser-tabs).
The owner signs in once per site in a normal, visible window on the same directory: no debugging port and no
headless flag there, so sites that refuse automated sign-in (Google) accept it.

The service browser resolves the Google private hosts (mail, drive, docs, the account console, passwords, payments,
Gemini, Chat, Meet, Voice, Messages, Sites, NotebookLM, AI Studio, ...) and the two wildcard families (per-user
`*.googleusercontent.com` storage, `*.mail.google.com`) to `~NOTFOUND` through `--host-resolver-rules`, so no tab it
serves can reach them however its code builds the URL (a manifest `website_blocklist` only filters URL literals).
What stays reachable on purpose: accounts.google.com (sign-in and the OAuth consent screens), google.com and
www.google.com. The visible login window deliberately does not get that flag either.

`status` reports `system_proxy` when macOS has an HTTP or HTTPS proxy enabled: a proxy makes Chrome send the request
by name and skip the local resolver, so the containment could be bypassed there.

Commands:
  status            is the service installed, is the browser listening, how many pages
  install           write and load the login service (macOS launchd; restarts the browser if it exits)
  uninstall         unload and remove the service
  start | stop      start or stop the service (stop frees the profile directory)
  login [URL ...]   stop the service, open a visible window on the profile (default: accounts.google.com),
                    wait until the owner quits it (Cmd+Q), then start the service again

Run under the Hermes runtime: scripts/hpy shared_browser.py <command>.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import plistlib
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

LABEL = "ai.hermes.shared-browser"
PORT = int(os.environ.get("HERMES_SHARED_BROWSER_PORT", "9333"))
ROOT = Path(os.environ.get("HERMES_SHARED_BROWSER_STATE") or Path.home() / ".hermes" / "browser-sessions")
PROFILE_DIR = ROOT / "hermes"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG = ROOT / "shared-browser.log"
COMMON = ["--use-mock-keychain", "--password-store=basic", "--no-first-run", "--no-default-browser-check"]
# Google's private pages stay out of reach of every tab of the service browser. `--host-resolver-rules` maps the
# names to ~NOTFOUND, so the block holds for a redirect, a click, or a URL built at run time, not only for a URL
# literal in the bot's code (a manifest website_blocklist only sees literals). accounts.google.com is never
# blocked: signing in (and an OAuth consent grant) needs it. The visible `login` window gets no such flag.
#
# A Chromium `MAP *.host ~NOTFOUND` rule matches subdomains only, never the bare apex (verified against the managed
# Chromium), so every apex this list means to block is named here and the wildcards only add their families.
GOOGLE_PRIVATE_HOSTS = (
    "mail.google.com", "drive.google.com", "docs.google.com", "myaccount.google.com",
    "pay.google.com", "payments.google.com", "photos.google.com", "calendar.google.com",
    "contacts.google.com", "inbox.google.com", "keep.google.com", "takeout.google.com",
    "passwords.google", "passwords.google.com", "myactivity.google.com", "gemini.google.com",
    "bard.google.com", "script.google.com", "chat.google.com", "meet.google.com", "voice.google.com",
    "messages.google.com", "sites.google.com", "notebooklm.google.com", "aistudio.google.com")
# Families, not single pages: per-user content on googleusercontent.com (mail attachments, Drive previews) and the
# Apps Script / Gmail front doors under mail.google.com.
GOOGLE_PRIVATE_PATTERNS = ("*.googleusercontent.com", "*.mail.google.com")
# Reachable on purpose. Never add these to the two tuples above: sign-in, the OAuth consent grant, and the plain
# search page are what the signed-in profile is for.
GOOGLE_ALLOWED_HOSTS = ("google.com", "www.google.com", "accounts.google.com")


def host_resolver_rules(hosts=GOOGLE_PRIVATE_HOSTS, patterns=GOOGLE_PRIVATE_PATTERNS) -> str:
    """A Chromium `--host-resolver-rules` value that fails resolution for each host and wildcard pattern."""
    return ",".join(f"MAP {name} ~NOTFOUND" for name in (*hosts, *patterns))


CONTAINMENT_FLAG = f"--host-resolver-rules={host_resolver_rules()}"


class ProbeError(RuntimeError):
    """A process probe failed: the answer is unknown, never "no browser holds the profile"."""


def chromium() -> str:
    """Hermes's managed Chromium (the one its browser tools use)."""
    override = os.environ.get("HERMES_SHARED_BROWSER_EXE")
    if override:
        return override
    try:
        from hermes_cli.browser_runtime import chromium_executable
        exe = chromium_executable(allow_override=False)
    except Exception as exc:  # noqa: BLE001 - outside the Hermes runtime
        raise SystemExit(f"run under the Hermes runtime (scripts/hpy shared_browser.py): {exc}")
    if not exe:
        raise SystemExit("Hermes's Chromium is not installed: run `hermes tools post-setup agent_browser`")
    return exe


def service_argv(exe: str, profile: Path | None = None, port: int | None = None) -> list[str]:
    """The service browser's command line: headless, its own profile, and the Google private hosts unreachable."""
    return [exe, "--headless=new", f"--remote-debugging-port={port or PORT}",
            "--remote-debugging-address=127.0.0.1", f"--user-data-dir={profile or PROFILE_DIR}", *COMMON,
            CONTAINMENT_FLAG, "about:blank"]


def login_argv(exe: str, urls: list[str], profile: Path | None = None) -> list[str]:
    """The visible sign-in window: same profile, no debugging port, and NOT the containment flag."""
    return [exe, f"--user-data-dir={profile or PROFILE_DIR}", *COMMON, *urls]


def service_plist(exe: str | None = None) -> dict:
    """The launchd job for the service. Its bytes change with `service_argv`, so `install` rewrites and reloads it."""
    return {"Label": LABEL, "ProgramArguments": service_argv(exe or chromium()), "RunAtLoad": True,
            "KeepAlive": True, "ThrottleInterval": 30, "ProcessType": "Background",
            "StandardOutPath": str(LOG), "StandardErrorPath": str(LOG)}


def plist_bytes() -> bytes | None:
    """What `install` would write, or None when the Hermes runtime cannot say (Chromium not installed)."""
    try:
        return plistlib.dumps(service_plist())
    except SystemExit:
        return None


def cdp_url() -> str:
    return f"http://127.0.0.1:{PORT}"


def listening() -> dict | None:
    try:
        with urllib.request.urlopen(f"{cdp_url()}/json/version", timeout=2) as r:
            version = json.load(r)
        with urllib.request.urlopen(f"{cdp_url()}/json/list", timeout=2) as r:
            pages = [p for p in json.load(r) if p.get("type") == "page"]
        return {"browser": version.get("Browser"), "pages": len(pages)}
    except (OSError, ValueError):
        return None


def profile_in_use(profile: Path | None = None) -> bool:
    """A Chromium process holds the profile directory (headless service or a visible login window).

    `--` ends pgrep's options: without it the `--user-data-dir=...` pattern is read as an option, pgrep exits 2 with
    an error and the caller would take the empty output for "no browser holds the profile". A probe failure (any
    exit code above 1, or no pgrep at all) raises ProbeError instead of answering.
    """
    pattern = f"--user-data-dir={profile or PROFILE_DIR}"
    try:
        done = subprocess.run(["pgrep", "-f", "--", pattern], capture_output=True, text=True)
    except OSError as exc:
        raise ProbeError(f"cannot run pgrep: {exc}") from None
    if done.returncode > 1:
        raise ProbeError(f"pgrep -f {pattern!r} failed (exit {done.returncode}): "
                         f"{(done.stderr or done.stdout).strip()[:200]}")
    return done.returncode == 0


def launchctl(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=check)


def domain() -> str:
    return f"gui/{os.getuid()}"


def loaded() -> bool:
    return launchctl("print", f"{domain()}/{LABEL}").returncode == 0


def require_macos() -> None:
    if platform.system() != "Darwin":
        raise SystemExit("the service is implemented for macOS launchd only; on Linux run the browser with "
                         "`" + " ".join(service_argv("<chromium>")) + "` under your own supervisor")


def wait_for(cond, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.5)
    return cond()


def system_proxy() -> dict[str, str]:
    """host:port of each web proxy macOS reports enabled, keyed HTTP / HTTPS; {} when none or not macOS.

    `--host-resolver-rules` is a resolver rule, and with a proxy Chrome sends the request to the proxy by name, so
    the local resolver (and the Google refusal) can be skipped. `status` says so instead of implying containment.
    """
    if platform.system() != "Darwin":
        return {}
    try:
        done = subprocess.run(["scutil", "--proxy"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return {}
    if done.returncode != 0:
        return {}
    values = {key: value for key, value in re.findall(r"^\s*(\w+)\s*:\s*(\S.*?)\s*$", done.stdout, re.MULTILINE)}
    out = {}
    for scheme in ("HTTP", "HTTPS"):
        host = values.get(f"{scheme}Proxy")
        if values.get(f"{scheme}Enable") == "1" and host:
            port = values.get(f"{scheme}Port")
            out[scheme.lower()] = f"{host}:{port}" if port else host
    return out


def cmd_status(_a) -> int:
    wanted = plist_bytes()
    proxy = system_proxy()
    report = {"cdp_url": cdp_url(), "profile_dir": str(PROFILE_DIR), "service_installed": PLIST.is_file(),
              "service_loaded": platform.system() == "Darwin" and loaded(),
              # False: the installed job predates a change to the service command line (the Google
              # containment flag, the Chromium path); `install` rewrites and reloads it.
              "plist_current": None if wanted is None else (PLIST.is_file() and PLIST.read_bytes() == wanted),
              "google_hosts_blocked": list(GOOGLE_PRIVATE_HOSTS),
              "google_patterns_blocked": list(GOOGLE_PRIVATE_PATTERNS),
              "google_hosts_allowed": list(GOOGLE_ALLOWED_HOSTS),
              "listening": listening(),
              # A system proxy sends the request by name, so the resolver refusal may never be consulted.
              "system_proxy": {"proxies": proxy,
                               "warning": "macOS has a web proxy enabled: Chrome may send the request by host name, "
                                          "skipping the local resolver, so the Google host containment is not "
                                          "guaranteed. Clear the proxy or verify the browser yourself."}
              if proxy else None}
    print(json.dumps(report))
    return 0


def cmd_install(_a) -> int:
    require_macos()
    exe = chromium()
    ROOT.mkdir(parents=True, exist_ok=True)
    os.chmod(ROOT, 0o700)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(PROFILE_DIR, 0o700)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    data = plistlib.dumps(service_plist(exe))
    if not PLIST.is_file() or PLIST.read_bytes() != data:
        if loaded():
            launchctl("bootout", f"{domain()}/{LABEL}")
        PLIST.write_bytes(data)
    if not loaded():
        if profile_in_use():
            raise SystemExit(f"another browser holds {PROFILE_DIR}: quit it (Cmd+Q) and run install again")
        launchctl("bootstrap", domain(), str(PLIST), check=True)
    ok = wait_for(lambda: listening() is not None, 20)
    print(json.dumps({"installed": str(PLIST), "listening": listening() if ok else None}))
    return 0 if ok else 1


def cmd_uninstall(_a) -> int:
    require_macos()
    if loaded():
        launchctl("bootout", f"{domain()}/{LABEL}")
    PLIST.unlink(missing_ok=True)
    print(json.dumps({"uninstalled": True}))
    return 0


def cmd_start(_a) -> int:
    require_macos()
    if not PLIST.is_file():
        raise SystemExit("service not installed: run `scripts/hpy shared_browser.py install`")
    if not loaded():
        launchctl("bootstrap", domain(), str(PLIST), check=True)
    ok = wait_for(lambda: listening() is not None, 20)
    print(json.dumps({"listening": listening() if ok else None}))
    return 0 if ok else 1


def cmd_stop(_a) -> int:
    require_macos()
    if loaded():
        launchctl("bootout", f"{domain()}/{LABEL}")
    ok = wait_for(lambda: not profile_in_use(), 15)
    print(json.dumps({"stopped": ok}))
    return 0 if ok else 1


def cmd_login(a) -> int:
    """The only way to sign in: a plain visible window, nothing attached to it.

    The service is booted out so the visible window can own the profile. Whatever happens after that (a probe that
    fails, a browser that still holds the profile, a Ctrl-C while the owner is in the window) the service is put
    back in the `finally`: a raise used to leave the squad without a browser until someone ran `start`.
    """
    was_loaded = platform.system() == "Darwin" and loaded()
    if was_loaded:
        launchctl("bootout", f"{domain()}/{LABEL}")
    try:
        if not wait_for(lambda: not profile_in_use(), 15):
            raise SystemExit(f"another browser still holds {PROFILE_DIR}: quit it and retry")
        urls = a.url or ["https://accounts.google.com/"]
        print(json.dumps({"login_window": urls, "quit_with": "Cmd+Q when every sign-in is done"}), flush=True)
        subprocess.run(login_argv(chromium(), urls),
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    finally:
        if was_loaded:
            launchctl("bootstrap", domain(), str(PLIST))
            wait_for(lambda: listening() is not None, 20)
    print(json.dumps({"login_window": "closed", "listening": listening()}))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter,
                                epilog=(__doc__ or "").split("\n\n", 2)[-1])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("status", "install", "uninstall", "start", "stop"):
        sub.add_parser(name)
    lp = sub.add_parser("login")
    lp.add_argument("url", nargs="*", help="pages to open (default: accounts.google.com)")
    a = p.parse_args(argv)
    handler = {"status": cmd_status, "install": cmd_install, "uninstall": cmd_uninstall, "start": cmd_start,
               "stop": cmd_stop, "login": cmd_login}[a.cmd]
    try:
        return handler(a)
    except ProbeError as exc:
        print(json.dumps({"error": f"cannot tell whether a browser holds {PROFILE_DIR}: {exc}"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
