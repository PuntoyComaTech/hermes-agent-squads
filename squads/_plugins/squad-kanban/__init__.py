"""squad-kanban: Hermes's own Kanban, kept honest for squads. No new board, no new state: it calls the kernel.

- Managers, post_tool_call on `terminal`: a card filed with the CLI (`hermes kanban create`, `kanban_chain.py`,
  `squadctl chain`) is subscribed to the chat that filed it, the way the `kanban_create` tool already does. Without
  this a CLI-filed card finishes and the chat never hears of it. The subscription is Hermes's own
  (`tools.kanban_tools._maybe_auto_subscribe`), so `kanban.auto_subscribe_on_create: false` still turns it off.
- Workers (`HERMES_KANBAN_TASK` set), transform_tool_result on every tool: when the card's git workspace has had
  unsaved changes for SAVE_AFTER_S since the worker started or last saved, one line is appended to the tool result
  telling it to save the finished piece now. At most once per NUDGE_EVERY_S. A worker runs one long turn, so a
  per-turn hook would fire once; a tool result is where the worker actually looks.

Fail-open everywhere: any error leaves the tool result as it was.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import threading
import time

logger = logging.getLogger(__name__)

SAVE_AFTER_S = 30 * 60
NUDGE_EVERY_S = 10 * 60
CHECK_EVERY_S = 60
_TASK = r"t_[0-9a-f]{4,32}"
_CREATED = re.compile(rf"(?:^|\n)\s*(?:Created|card)\s+({_TASK})\b")
_JSON_ID = re.compile(rf'"(?:id|task_id)"\s*:\s*"({_TASK})"')
_FILES = re.compile(r"(?:kanban\s+(?:--board\s+\S+\s+)?create|kanban_chain\.py|squadctl(?:\.py)?\s+chain)\b")
_SAVES = re.compile(r"save_progress\.py|git\s+(?:-C\s+\S+\s+)?commit\b")

_lock = threading.Lock()
_state = {"since": time.monotonic(), "nudged": 0.0, "checked": 0.0}


def _worker() -> bool:
    return bool(os.environ.get("HERMES_KANBAN_TASK"))


def _board_of(command: str, result: str) -> str | None:
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    for i, w in enumerate(words[:-1]):
        if w == "--board":
            return words[i + 1]
    m = re.search(r'"board"\s*:\s*"([a-z0-9][a-z0-9_-]*)"', result)
    return m.group(1) if m else None


def filed_cards(command: str, result: str) -> list[str]:
    """Card ids a terminal call filed: only for a create or chain command, only ids its output reports as created."""
    if not _FILES.search(command or ""):
        return []
    ids = _CREATED.findall(result) + _JSON_ID.findall(result)
    return list(dict.fromkeys(ids))


def _output(result) -> str:
    """The terminal tool returns JSON with `output`; anything else is read as text."""
    if not isinstance(result, str):
        return ""
    try:
        data = json.loads(result)
    except ValueError:
        return result
    return str(data.get("output") or "") if isinstance(data, dict) else result


def subscribe(task_ids: list[str], board: str | None) -> list[str]:
    """Subscribe the calling chat to each card with Hermes's own auto-subscribe; the ids it subscribed."""
    from tools.kanban_tools import _board, _maybe_auto_subscribe
    done = []
    with _board(board) as (kb, conn):
        for tid in task_ids:
            if kb.get_task(conn, tid) is not None and _maybe_auto_subscribe(conn, tid):
                done.append(tid)
    return done


def on_post_tool_call(tool_name="", args=None, result=None, **_):
    if tool_name != "terminal" or _worker():
        return None
    try:
        command = str((args or {}).get("command") or "")
        out = _output(result)
        ids = filed_cards(command, out)
        if ids:
            subscribe(ids, _board_of(command, out))
    except Exception:  # noqa: BLE001 - fail open: bookkeeping never breaks a tool call
        logger.debug("squad-kanban: subscribe skipped", exc_info=True)
    return None


def _git(workspace: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", workspace, *args], capture_output=True, text=True, timeout=20,
                          stdin=subprocess.DEVNULL)
    return proc.stdout if proc.returncode == 0 else ""


def unsaved(workspace: str) -> int:
    """Changed or new files in the workspace's git tree (0 when it is not a repo)."""
    return len([line for line in _git(workspace, "status", "--porcelain").splitlines() if line.strip()])


def nudge(now: float, workspace: str) -> str | None:
    """The reminder line, or None. Clock: worker start or its last save; then at most once per NUDGE_EVERY_S."""
    with _lock:
        if now - _state["since"] < SAVE_AFTER_S or now - _state["nudged"] < NUDGE_EVERY_S:
            return None
        if now - _state["checked"] < CHECK_EVERY_S:
            return None
        _state["checked"] = now
    count = unsaved(workspace)
    if not count:
        return None
    with _lock:
        _state["nudged"] = now
    minutes = int((now - _state["since"]) // 60)
    return (f"\n\n[squad-kanban] {minutes} min since your last save and {count} changed file(s) in the workspace. "
            "Save the piece you finished now with the save step your skill names (web: save_progress.py), "
            "then continue: unsaved work is invisible to the user and lost if this run stops.")


def on_transform_tool_result(tool_name="", args=None, result=None, **_):
    if not _worker() or not isinstance(result, str):
        return None
    try:
        now = time.monotonic()
        if tool_name == "terminal" and _SAVES.search(str((args or {}).get("command") or "")):
            with _lock:
                _state["since"] = now
            return None
        workspace = os.environ.get("HERMES_KANBAN_WORKSPACE") or os.getcwd()
        line = nudge(now, workspace)
        return result + line if line else None
    except Exception:  # noqa: BLE001 - fail open
        logger.debug("squad-kanban: nudge skipped", exc_info=True)
        return None


def register(ctx) -> None:
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("transform_tool_result", on_transform_tool_result)
