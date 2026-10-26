"""squad-kanban: Hermes's own Kanban, kept honest for squads. No new board, no new state: it calls the kernel.

- Managers, post_tool_call on `terminal`: a card filed with the CLI (`hermes kanban create`, `kanban_chain.py`,
  `squadctl chain`) is subscribed to the chat that filed it, the way the `kanban_create` tool already does. Without
  this a CLI-filed card finishes and the chat never hears of it. The subscription is Hermes's own
  (`tools.kanban_tools._maybe_auto_subscribe`), so `kanban.auto_subscribe_on_create: false` still turns it off.
- Workers (`HERMES_KANBAN_TASK` set), transform_tool_result on every tool: the plugin remembers each file this
  worker wrote (`write_file`, `patch`) and when it first wrote it. When one of those files is still uncommitted in its
  own git repo after SAVE_AFTER_S, one line is appended to the tool result telling the worker to save the finished
  piece now; at most once per NUDGE_EVERY_S. Only the worker's own files count (another builder's work in the shared
  tree never nags it, a reviewer that writes nothing is never nagged), the repo is found from each file (a site whose
  repo is `<site>/repo` works), and a file leaves the list the moment a commit holds it. A worker runs one long
  turn, so a per-turn hook would fire once; a tool result is where the worker actually looks.

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
_FILES = re.compile(r"(?:kanban\s+(?:--board[\s=]+\S+\s+)?create|kanban_chain\.py|squadctl(?:\.py)?\s+chain)\b")
_WRITERS = {"write_file": ("path",), "patch": ("path",)}

_lock = threading.Lock()
_state = {"nudged": 0.0, "checked": 0.0}
_written: dict[str, float] = {}  # absolute path this worker wrote -> when it first wrote it since the last commit


def _worker() -> bool:
    return bool(os.environ.get("HERMES_KANBAN_TASK"))


def _board_of(command: str, result: str) -> str | None:
    try:
        words = shlex.split(command)
    except ValueError:
        words = command.split()
    for i, w in enumerate(words):
        if w == "--board" and i + 1 < len(words):
            return words[i + 1]
        if w.startswith("--board="):
            return w.split("=", 1)[1]
        if w.startswith("HERMES_KANBAN_BOARD="):
            return w.split("=", 1)[1]
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
            if kb.get_task(conn, tid) is None:
                logger.info("squad-kanban: %s is not on board %s; chat not subscribed", tid, board or "(current)")
            elif _maybe_auto_subscribe(conn, tid):
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


def _git(cwd: str, *args: str) -> str:
    proc = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=20,
                          stdin=subprocess.DEVNULL)
    return proc.stdout if proc.returncode == 0 else ""


def uncommitted(path: str) -> bool:
    """True when `path` sits in a git repo and differs from that repo's HEAD (new, changed or staged)."""
    folder = os.path.dirname(path) or "."
    while not os.path.isdir(folder) and folder != os.path.dirname(folder):
        folder = os.path.dirname(folder)
    return bool(_git(folder, "status", "--porcelain", "--", path).strip())


def remember(tool_name: str, args: dict | None, now: float) -> None:
    """Record the files a write tool touched, keeping the time of the first write since the last commit."""
    for key in _WRITERS.get(tool_name, ()):
        value = (args or {}).get(key)
        if isinstance(value, str) and value.strip():
            path = os.path.abspath(os.path.expanduser(value))
            with _lock:
                _written.setdefault(path, now)


def nudge(now: float) -> str | None:
    """The reminder line, or None: one of this worker's files uncommitted for SAVE_AFTER_S; once per NUDGE_EVERY_S."""
    with _lock:
        if now - _state["nudged"] < NUDGE_EVERY_S or now - _state["checked"] < CHECK_EVERY_S:
            return None
        due = [p for p, t in _written.items() if now - t >= SAVE_AFTER_S]
        if not due:
            return None
        _state["checked"] = now
    pending = []
    for path in due:
        if uncommitted(path):
            pending.append(path)
        else:
            with _lock:
                _written.pop(path, None)  # a commit holds it now: its clock stops
    if not pending:
        return None
    with _lock:
        _state["nudged"] = now
        oldest = min(_written[p] for p in pending if p in _written)
    minutes = int((now - oldest) // 60)
    names = ", ".join(os.path.basename(p) for p in pending[:3]) + (" ..." if len(pending) > 3 else "")
    return (f"\n\n[squad-kanban] {len(pending)} file(s) you wrote are still unsaved after {minutes} min ({names}). "
            "Save the piece you finished now with the save step your skill names (web: save_progress.py), "
            "then continue: unsaved work is invisible to the user and lost if this run stops.")


def on_transform_tool_result(tool_name="", args=None, result=None, **_):
    if not _worker() or not isinstance(result, str):
        return None
    try:
        now = time.monotonic()
        remember(tool_name, args, now)
        line = nudge(now)
        return result + line if line else None
    except Exception:  # noqa: BLE001 - fail open
        logger.debug("squad-kanban: nudge skipped", exc_info=True)
        return None


def register(ctx) -> None:
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("transform_tool_result", on_transform_tool_result)
