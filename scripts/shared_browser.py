#!/usr/bin/env python3
"""The shared signed-in browser every squad bot with `shared_browser: true` drives.

One Chromium (Hermes's managed Chrome for Testing), headless unless installed `--visible`, on one profile directory,
listening on a loopback CDP port. Bots reach it through `browser.cdp_url`; each bot run works in its own tab (plugin
shared-browser-tabs).
The owner signs in once per site in a normal, visible window on the same directory: no debugging port and no
headless flag there, so sites that refuse automated sign-in (Google) accept it.

The service browser reaches every site; nothing is blocked at the browser.

Commands:
  status            is the service installed, is the browser listening, how many pages
  install [--visible | --headless]
                    write and load the login service (macOS launchd or Linux systemd --user).
                    --visible runs the service as a normal window (same profile, same loopback port) for sites
                    whose bot check refuses a headless browser; --headless goes back. Without either flag the
                    current mode is kept. Headless is the default: a visible service puts a window on the desktop.
  uninstall         unload and remove the service
  start | stop      start or stop the service (stop frees the profile directory)
  login [URL ...]   stop the service, open a visible window on the profile (default: accounts.google.com),
                    wait until the owner quits it, then restore a previously running service

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
        raise SystemExit("Hermes's Chromium is not installed: run `hermes tools post-setup chromium` "
                         "(`agent_browser` on a Hermes before config v52)")
    return exe


def visible_flag() -> Path:
    """Present: the service runs as a normal window (`install --visible`). Kept beside the profile, not in the plist,
    so `install` without a flag (squadctl, auto_update) keeps the owner's choice."""
    return ROOT / "visible"


def visible() -> bool:
    return visible_flag().is_file()


def service_argv(exe: str, profile: Path | None = None, port: int | None = None,
                 headed: bool | None = None) -> list[str]:
    """The service browser's command line: headless unless `install --visible`, its own profile, a loopback port.

    The two modes differ by the headless flag alone: nothing else about the browser is changed or disguised."""
    headed = visible() if headed is None else headed
    return [exe, *([] if headed else ["--headless=new"]), f"--remote-debugging-port={port or PORT}",
            "--remote-debugging-address=127.0.0.1", f"--user-data-dir={profile or PROFILE_DIR}", *COMMON,
            "about:blank"]


def login_argv(exe: str, urls: list[str], profile: Path | None = None) -> list[str]:
    """The visible sign-in window: same profile, no debugging port."""
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
    pattern = "--user-data-dir=" + re.sub(r"([.\\^$*+?{}|()\[\]])", r"\\\1", str(profile or PROFILE_DIR)) + r"($|[[:space:]])"
    try:
        done = subprocess.run(["pgrep", "-f", "--", pattern], capture_output=True, text=True)
    except OSError as exc:
        raise ProbeError(f"cannot run pgrep: {exc}") from None
    if done.returncode not in (0, 1):
        raise ProbeError(f"pgrep -f {pattern!r} failed (exit {done.returncode}): "
                         f"{(done.stderr or done.stdout).strip()[:200]}")
    return done.returncode == 0


def launchctl(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True, check=check)


def domain() -> str:
    return f"gui/{os.getuid()}"


def loaded() -> bool:
    return launchctl("print", f"{domain()}/{LABEL}").returncode == 0


def private_dirs() -> None:
    """The state and profile directories, readable by the owner alone (they hold the signed-in session)."""
    for d in (ROOT, PROFILE_DIR):
        d.mkdir(parents=True, exist_ok=True)
        os.chmod(d, 0o700)


UNIT_NAME = f"{LABEL}.service"
GRAPHICAL_ENV = ("DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")


def unit_path() -> Path:
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not config.is_absolute():
        config = Path.home() / ".config"
    return config / "systemd" / "user" / UNIT_NAME


def systemctl(*args: str, allowed: tuple[int, ...] = (0,)) -> subprocess.CompletedProcess:
    try:
        result = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=5)
    except subprocess.TimeoutExpired:
        raise SystemExit("systemctl --user timed out; check the systemd user manager and session bus") from None
    except OSError as exc:
        raise SystemExit(f"cannot run systemctl --user: {exc}; install systemd and use a user session") from None
    if result.returncode not in allowed:
        detail = (result.stderr or result.stdout or "").strip()
        raise SystemExit(f"systemctl --user {' '.join(args)} failed: {detail}; "
                         "ensure the systemd user manager and session bus are available")
    return result


def check_user_manager() -> None:
    systemctl("show-environment")


def systemd_state() -> str:
    result = systemctl("is-active", UNIT_NAME, allowed=(0, 3, 4))
    state = result.stdout.strip()
    valid = {0: {"active", "reloading", "refreshing"},
             3: {"inactive", "failed", "activating", "deactivating", "maintenance"},
             4: {"unknown", "inactive"}}
    if result.stderr.strip() or state not in valid[result.returncode]:
        detail = (result.stderr or result.stdout or "empty response").strip()
        raise SystemExit(f"systemctl --user is-active returned an unexpected state: {detail}")
    return state


def systemd_active() -> bool:
    return systemd_state() in {"active", "reloading", "refreshing"}


SUPERVISED = {"active", "reloading", "refreshing", "activating", "deactivating"}
RESTORE = SUPERVISED - {"deactivating"}


def import_graphical_environment() -> None:
    names = [name for name in GRAPHICAL_ENV if os.environ.get(name)]
    if names:
        systemctl("import-environment", *names)


def systemd_quote(arg: str, *, executable: bool = False) -> str:
    # Specifiers expand in all words; environment substitution skips the executable path.
    if not executable:
        arg = arg.replace("$", "$$")
    escaped = (arg.replace("%", "%%").replace("\\", "\\\\")
               .replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t"))
    return f'"{escaped}"'


def service_unit(exe: str | None = None) -> bytes:
    command = " ".join(systemd_quote(arg, executable=(i == 0))
                       for i, arg in enumerate(service_argv(exe or chromium())))
    return ("[Unit]\nDescription=Hermes shared browser\n\n[Service]\n"
            f"ExecStart={command}\nRestart=always\nRestartSec=30\n\n"
            "[Install]\nWantedBy=default.target\n").encode()


def linux_status() -> int:
    check_user_manager()
    unit = unit_path()
    try:
        wanted = service_unit()
    except SystemExit:
        wanted = None
    report = {"cdp_url": cdp_url(), "profile_dir": str(PROFILE_DIR), "service_installed": unit.is_file(),
              "service_loaded": systemd_active(),
              # squadctl consumes this historical, platform-neutral currency field.
              "plist_current": None if wanted is None else (unit.is_file() and unit.read_bytes() == wanted),
              "visible": visible(), "listening": listening()}
    print(json.dumps(report))
    return 0


def linux_install(a) -> int:
    check_user_manager()
    exe = chromium()
    private_dirs()
    if getattr(a, "visible", False):
        visible_flag().touch()
    elif getattr(a, "headless", False):
        visible_flag().unlink(missing_ok=True)
    unit = unit_path()
    data = service_unit(exe)
    changed = not unit.is_file() or unit.read_bytes() != data
    state = systemd_state()
    active = state in {"active", "reloading", "refreshing"}
    if state in SUPERVISED and (changed or not active):
        systemctl("stop", UNIT_NAME)
        active = False
    if not active and profile_in_use():
        raise SystemExit(f"another browser holds {PROFILE_DIR}: quit it and run install again")
    if changed:
        unit.parent.mkdir(parents=True, exist_ok=True)
        unit.write_bytes(data)
        systemctl("daemon-reload")
    systemctl("enable", UNIT_NAME)
    if visible():
        import_graphical_environment()
    if not active:
        systemctl("start", UNIT_NAME)
    ok = wait_for(lambda: listening() is not None, 20)
    print(json.dumps({"installed": str(unit), "visible": visible(), "listening": listening() if ok else None}))
    return 0 if ok else 1


def linux_start() -> int:
    check_user_manager()
    if not unit_path().is_file():
        raise SystemExit("service not installed: run `scripts/hpy shared_browser.py install`")
    state = systemd_state()
    if state not in {"active", "reloading", "refreshing"}:
        if state in SUPERVISED:
            systemctl("stop", UNIT_NAME)
        if profile_in_use():
            raise SystemExit(f"another browser holds {PROFILE_DIR}: quit it and retry")
        if visible():
            import_graphical_environment()
        systemctl("start", UNIT_NAME)
    ok = wait_for(lambda: listening() is not None, 20)
    print(json.dumps({"listening": listening() if ok else None}))
    return 0 if ok else 1


def linux_stop() -> int:
    check_user_manager()
    if systemd_state() in SUPERVISED:
        systemctl("stop", UNIT_NAME)
    ok = wait_for(lambda: not profile_in_use(), 15)
    print(json.dumps({"stopped": ok}))
    return 0 if ok else 1


def linux_uninstall() -> int:
    check_user_manager()
    if systemd_state() in SUPERVISED:
        systemctl("stop", UNIT_NAME)
    if unit_path().is_file():
        systemctl("disable", UNIT_NAME)
        unit_path().unlink()
        systemctl("daemon-reload")
    print(json.dumps({"uninstalled": True}))
    return 0


def linux_login(a) -> int:
    check_user_manager()
    state = systemd_state()
    was_active = state in RESTORE
    try:
        if state in SUPERVISED:
            systemctl("stop", UNIT_NAME)
        if not wait_for(lambda: not profile_in_use(), 15):
            raise SystemExit(f"another browser still holds {PROFILE_DIR}: quit it and retry")
        private_dirs()
        import_graphical_environment()
        urls = a.url or ["https://accounts.google.com/"]
        print(json.dumps({"login_window": urls, "quit_with": "close the browser when every sign-in is done"}), flush=True)
        result = subprocess.run(login_argv(chromium(), urls), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode:
            raise SystemExit(f"login browser exited with status {result.returncode}; check the graphical session")
    finally:
        if was_active:
            systemctl("start", UNIT_NAME)
            if not wait_for(lambda: listening() is not None, 20):
                raise SystemExit("restored shared browser service did not become ready; check systemd user service logs")
    print(json.dumps({"login_window": "closed", "listening": listening()}))
    return 0


def wait_for(cond, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if cond():
            return True
        time.sleep(0.5)
    return cond()


def cmd_status(_a) -> int:
    wanted = plist_bytes()
    report = {"cdp_url": cdp_url(), "profile_dir": str(PROFILE_DIR), "service_installed": PLIST.is_file(),
              "service_loaded": platform.system() == "Darwin" and loaded(),
              # False: the installed job predates a change to the service command line; `install` rewrites it.
              "plist_current": None if wanted is None else (PLIST.is_file() and PLIST.read_bytes() == wanted),
              "visible": visible(), "listening": listening()}
    print(json.dumps(report))
    return 0


def cmd_install(a) -> int:
    exe = chromium()
    private_dirs()
    if getattr(a, "visible", False):
        visible_flag().touch()
    elif getattr(a, "headless", False):
        visible_flag().unlink(missing_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    data = plistlib.dumps(service_plist(exe))
    if not PLIST.is_file() or PLIST.read_bytes() != data:
        if loaded():
            launchctl("bootout", f"{domain()}/{LABEL}")
            # bootout returns while launchd still lists the job: reading loaded() at once skips the bootstrap below
            if not wait_for(lambda: not loaded(), 20):
                raise SystemExit("launchd did not remove the old shared-browser job; run install again")
        PLIST.write_bytes(data)
    if not loaded():
        if profile_in_use():
            raise SystemExit(f"another browser holds {PROFILE_DIR}: quit it (Cmd+Q) and run install again")
        launchctl("bootstrap", domain(), str(PLIST), check=True)
    ok = wait_for(lambda: listening() is not None, 20)
    print(json.dumps({"installed": str(PLIST), "visible": visible(), "listening": listening() if ok else None}))
    return 0 if ok else 1


def cmd_uninstall(_a) -> int:
    if loaded():
        launchctl("bootout", f"{domain()}/{LABEL}")
    PLIST.unlink(missing_ok=True)
    print(json.dumps({"uninstalled": True}))
    return 0


def cmd_start(_a) -> int:
    if not PLIST.is_file():
        raise SystemExit("service not installed: run `scripts/hpy shared_browser.py install`")
    if not loaded():
        launchctl("bootstrap", domain(), str(PLIST), check=True)
    ok = wait_for(lambda: listening() is not None, 20)
    print(json.dumps({"listening": listening() if ok else None}))
    return 0 if ok else 1


def cmd_stop(_a) -> int:
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
    for name in ("status", "uninstall", "start", "stop"):
        sub.add_parser(name)
    ip = sub.add_parser("install").add_mutually_exclusive_group()
    ip.add_argument("--visible", action="store_true", help="run the service as a normal window")
    ip.add_argument("--headless", action="store_true", help="run the service headless (the default)")
    lp = sub.add_parser("login")
    lp.add_argument("url", nargs="*", help="pages to open (default: accounts.google.com)")
    a = p.parse_args(argv)
    handlers = {"Darwin": {"status": cmd_status, "install": cmd_install, "uninstall": cmd_uninstall,
                           "start": cmd_start, "stop": cmd_stop, "login": cmd_login},
                "Linux": {"status": lambda _a: linux_status(), "install": linux_install,
                          "uninstall": lambda _a: linux_uninstall(), "start": lambda _a: linux_start(),
                          "stop": lambda _a: linux_stop(), "login": linux_login}}.get(platform.system())
    try:
        if handlers is None:
            raise SystemExit(f"unsupported operating system: {platform.system()}; "
                             "use macOS or Linux with systemd --user")
        return handlers[a.cmd](a)
    except ProbeError as exc:
        print(json.dumps({"error": f"cannot tell whether a browser holds {PROFILE_DIR}: {exc}"}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
