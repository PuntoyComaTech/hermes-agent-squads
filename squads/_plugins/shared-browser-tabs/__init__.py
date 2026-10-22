"""shared-browser-tabs: one tab per bot run on a shared signed-in browser, closed when the turn ends.

Active only when the profile's `browser.cdp_url` (or BROWSER_CDP_URL) points at a loopback browser.

- pre_tool_call on browser_exec: a call without `session` gets a stable per-task name, so the bot runs in its
  own harness daemon and its own tab; every session name used is leased with this Hermes pid, and the page ids
  present before the call are snapshotted.
- post_tool_call on browser_exec: the tab the call attached is recorded for that session, so the turn end closes
  exactly the tabs these runs held. With no pre-call snapshot, or a snapshot that failed, nothing is recorded and
  the release falls back to its own before/after diff.
- on_session_end: stops the daemons of this turn's sessions and closes the tabs they held. The bot does nothing.
  With nothing recorded for the turn, `held=None` reaches the release so that fallback runs, rather than an empty
  set that would close nothing. Hermes ends an interrupted turn with no `task_id` (cli_shutdown, tui gateway), so
  a session is indexed by both ids and both are popped.
"""
from __future__ import annotations

import inspect
import logging
import os
import threading

from . import tabs  # squadctl installs scripts/shared_browser_tabs.py beside this file as tabs.py

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_used: dict[str, set[str]] = {}  # task id or session id -> session names used this turn
_held: dict[str, set[str]] = {}  # session name -> page target ids its runs attached
_before: dict[str, dict[str, bool]] = {}  # session name -> attached snapshot taken before a call


def _port() -> int | None:
    url = os.environ.get("BROWSER_CDP_URL", "").strip()
    if not url:
        try:
            from hermes_cli.config import read_raw_config
            url = str(((read_raw_config() or {}).get("browser") or {}).get("cdp_url") or "")
        except Exception:  # noqa: BLE001 - no config means no shared browser
            return None
    return tabs.loopback_port(url)


def _keys(task_id: str = "", session_id: str = "") -> list[str]:
    """Both ids of a turn: an interrupted turn ends with a session id only, a normal one carries both."""
    keys = sorted({k for k in (task_id, session_id) if k})
    return keys or ["default"]


# Runs after Hermes pins the named session to its own tab: new_tab() then navigates that tab instead of opening
# another, so a bot run holds one tab however its code is written.
ONE_TAB_PREFIX = (
    "# shared-browser-tabs: one tab per bot run\n"
    "def new_tab(url='about:blank'):\n"
    "    goto_url(url)\n"
    "    return current_tab()['targetId']\n"
)


def _session(args: dict, task_id: str, session_id: str) -> str:
    return str(args.get("session") or "").strip() or tabs.session_name(task_id, session_id)


def _on_pre_tool_call(tool_name: str = "", args: dict | None = None, task_id: str = "", session_id: str = "",
                      **_):
    if tool_name != "browser_exec":
        return None
    port = _port()
    if port is None:
        return None
    args = args if isinstance(args, dict) else {}
    name = str(args.get("session") or "").strip()
    change: dict = {}
    if not name:
        name = tabs.session_name(task_id, session_id)
        change["session"] = name
    code = args.get("code")
    if isinstance(code, str) and code.strip() and not code.startswith(ONE_TAB_PREFIX):
        change["code"] = ONE_TAB_PREFIX + code
    directive = {"action": "modify", "args": change} if change else None
    if tabs.SESSION_RE.match(name):
        with _lock:
            for key in _keys(task_id, session_id):
                _used.setdefault(key, set()).add(name)
        snapshot = getattr(tabs, "attached_now", None)  # an older tabs.py alongside a newer plugin: no recording
        if snapshot is not None:
            try:
                _before.setdefault(name, snapshot(port))
            except (OSError, RuntimeError) as exc:
                logger.debug("shared-browser-tabs: snapshot of %s failed: %s", name, exc)
        try:
            tabs.touch_lease(port, name)
        except OSError as exc:
            logger.debug("shared-browser-tabs: lease %s failed: %s", name, exc)
    return directive


def _on_post_tool_call(tool_name: str = "", args: dict | None = None, task_id: str = "", session_id: str = "",
                       **_):
    """Record the tab this call attached, so the turn end closes that tab and no other run's."""
    if tool_name != "browser_exec":
        return None
    port = _port()
    if port is None:
        return None
    args = args if isinstance(args, dict) else {}
    name = _session(args, task_id, session_id)
    claim = getattr(tabs, "claimed_targets", None)
    if claim is None:  # an older tabs.py alongside a newer plugin: the release falls back to its own snapshot
        return None
    before = _before.pop(name, None)
    if before is None:
        # No pre-call snapshot (a pre hook that failed or never ran, or a session named at call time): a diff
        # against {} would claim every attached page, another bot's tab included. Record nothing and let the
        # release use its own before/after fallback.
        return None
    try:
        claims = claim(port, before)
    except (OSError, RuntimeError) as exc:
        logger.debug("shared-browser-tabs: post-call snapshot failed: %s", exc)
        return None
    if claims:
        with _lock:
            _held.setdefault(name, set()).update(claims)
    return None


def _on_session_end(task_id: str = "", session_id: str = "", **_) -> None:
    with _lock:
        names: set[str] = set()
        for key in _keys(task_id, session_id):
            names |= _used.pop(key, set())
        # An interrupted turn names only the session id, so the same session names still sit under the task id:
        # drop them there too, or the next end of that turn releases (and logs) the same tabs again.
        for key, used_names in list(_used.items()):
            used_names -= names
            if not used_names:
                del _used[key]
        held: set[str] | None = None  # None: nothing was recorded, so `release` runs its before/after fallback
        for name in sorted(names):
            got = _held.pop(name, None)
            if got:
                held = (held or set()) | got
            _before.pop(name, None)
    if not names:
        return
    port = _port()
    if port is None:
        return
    kwargs = {"held": held} if "held" in inspect.signature(tabs.release).parameters else {}
    try:
        result = tabs.release(port, sorted(names), **kwargs)
        logger.info("shared-browser-tabs: released %s -> %s", sorted(names), result)
    except Exception as exc:  # noqa: BLE001 - the sweep cron catches anything left behind
        logger.warning("shared-browser-tabs: release of %s failed: %s", sorted(names), exc)


def register(ctx) -> None:
    ctx.register_hook("pre_tool_call", _on_pre_tool_call)
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("on_session_end", _on_session_end)
