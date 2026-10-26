"""squad-hub agent half: how a squad manager talks to its user, and the cards its replies carry in the Desktop app.

- A prompt section (frozen per session): a bot that needs a decision asks with `clarify` and offers the likely
  answers, so the user picks one instead of typing "ok". Empty in cron runs and Kanban workers, where nobody can
  answer. In a Desktop chat it also teaches the card line `::squad-task{board="..." id="..."}`, which the desktop half
  (desktop/plugin.js) draws as a live card.
- post_tool_call on `kanban_create`, and on a `terminal` call that filed cards with the CLI (`hermes kanban create`,
  `kanban_chain.py`), records the card a turn filed; transform_llm_output appends the cards the reply
  did not reference, Desktop chats only (on a messaging channel the line would read as raw text). Fail-open: any
  error leaves the reply as the model wrote it.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading

logger = logging.getLogger(__name__)

SECTION_ID = "squad-hub.conversation"
MAX_CARDS = 3
_TASK_ID = re.compile(r"^t_[0-9a-f]{4,32}$")
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_NO_HUMAN = {"cron", "subagent", "webhook", "msgraph_webhook", "api_server"}  # nobody reads a question there

ASK = (
    "Whenever a reply would end by asking the user for a decision (approve a plan, yes or no, pick an option, start "
    "now or later), do not write the question: call the `clarify` tool with the likely answers as choices, the "
    "recommended one first (for example: Approve / Change something / Not now). The user clicks instead of typing "
    "\"ok\". Put independent questions in one call. Only a question with no likely answers goes in plain text, and "
    "small choices you can make yourself are not asked at all."
)
CARDS = (
    "In this Desktop chat a Kanban card you filed or report on can be shown as a live card: put "
    "`::squad-task{board=\"<board slug>\" id=\"<task id>\"}` on its own line with a blank line before and after, "
    "outside any code block, using only ids the Kanban tools returned. `::squad-board{board=\"<board slug>\"}` shows a "
    "board's counts. At most three per reply, and say the same in one plain sentence."
)

_cards_on = lambda: False  # noqa: E731 - replaced in register() by the plugin's `desktop_cards` setting

_lock = threading.Lock()
_owed: dict[str, list[tuple[str, str]]] = {}  # turn id (else session id) -> [(board, task id)] filed this turn


def _worker() -> bool:
    return bool(os.environ.get("HERMES_KANBAN_TASK"))


def prompt_section(info) -> str:
    """The section text for one session: empty where nobody can answer a question."""
    platform = str((info or {}).get("platform") or "")
    if platform in _NO_HUMAN or _worker():
        return ""
    return ASK + ("\n\n" + CARDS if platform == "desktop" and _cards_on() else "")


_CLI_FILES = re.compile(r"(?:kanban\s+(?:--board\s+\S+\s+)?create|kanban_chain\.py|squadctl(?:\.py)?\s+chain)\b")
_CLI_CREATED = re.compile(r"(?:^|\n)\s*(?:Created|card)\s+(t_[0-9a-f]{4,32})\b")
_CLI_JSON_ID = re.compile(r'"(?:id|task_id)"\s*:\s*"(t_[0-9a-f]{4,32})"')
_CLI_BOARD = re.compile(r"--board[\s=]+([a-z0-9][a-z0-9_-]{0,63})\b")


def cli_cards(command: str, output: str) -> tuple[str, list[str]]:
    """(board, card ids) a terminal call filed with the Kanban CLI; nothing for any other command."""
    if not _CLI_FILES.search(command or ""):
        return "", []
    board = _CLI_BOARD.search(command)
    ids = list(dict.fromkeys(_CLI_CREATED.findall(output) + _CLI_JSON_ID.findall(output)))
    return (board.group(1) if board else ""), ids


def _key(turn_id: str, session_id: str) -> str:
    """The ledger key: the turn id, which survives the session id a mid-turn compression rotates."""
    return f"turn:{turn_id}" if turn_id else f"session:{session_id}"


def _record(key: str, board: str, task_id: str) -> None:
    with _lock:
        owed = _owed.setdefault(key, [])
        if (board, task_id) not in owed:
            owed.append((board, task_id))
        if len(_owed) > 500:
            _owed.pop(next(iter(_owed)))


def on_post_tool_call(tool_name="", args=None, result=None, session_id="", turn_id="", **_):
    """Record each card the turn filed, by session: the `kanban_create` tool or the Kanban CLI in `terminal`."""
    if tool_name not in ("kanban_create", "terminal") or not (session_id or turn_id) or _worker():
        return None
    try:
        data = json.loads(result) if isinstance(result, str) else (result or {})
    except (TypeError, ValueError):
        data = {}
    if tool_name == "terminal":
        output = str((data or {}).get("output") or "") if isinstance(data, dict) else ""
        board, ids = cli_cards(str((args or {}).get("command") or ""), output)
        for task_id in ids:
            _record(_key(turn_id, session_id), board, task_id)
        return None
    task_id = str((data or {}).get("task_id") or "")
    if not (data or {}).get("ok") or not _TASK_ID.match(task_id):
        return None
    board = str((args or {}).get("board") or "")  # none: the desktop card finds the board holding the id
    if board and not _SLUG.match(board):
        board = ""
    _record(_key(turn_id, session_id), board, task_id)
    return None


def card_line(board: str, task_id: str) -> str:
    return f'::squad-task{{board="{board}" id="{task_id}"}}' if board else f'::squad-task{{id="{task_id}"}}'


def owed_cards(text: str, owed: list[tuple[str, str]]) -> list[str]:
    """The card lines a reply still owes: cards it filed and never referenced, at most MAX_CARDS."""
    return [card_line(b, t) for b, t in owed if not re.search(r"\bid=[\"']?" + re.escape(t) + r"\b", text)][:MAX_CARDS]


def with_cards(text: str, lines: list[str]) -> str:
    """`text` with each card line appended as its own paragraph, after closing a code block the reply left open."""
    body = text.rstrip()
    if body.count("```") % 2:
        body += "\n```"
    return body + "".join("\n\n" + line for line in lines)


def on_transform_llm_output(response_text="", session_id="", platform="", turn_id="", **_):
    """Append the cards this turn filed and the reply did not show (Desktop chats only)."""
    if not (session_id or turn_id):
        return None
    with _lock:
        owed = _owed.pop(_key(turn_id, session_id), []) + (_owed.pop(_key("", session_id), []) if turn_id else [])
    if platform != "desktop" or not owed or not _cards_on() or not isinstance(response_text, str) or not response_text.strip():
        return None
    try:
        lines = owed_cards(response_text, owed)
        return with_cards(response_text, lines) if lines else None
    except Exception:  # noqa: BLE001 - fail open: the reply stays as written
        logger.debug("squad-hub: card append skipped", exc_info=True)
        return None


def register(ctx) -> None:
    global _cards_on

    def _cards_on():  # noqa: F811 - the desktop half sets it when it runs; without it a card line reads as raw text
        try:
            return ctx.get_config("desktop_cards", False) is True
        except Exception:  # noqa: BLE001
            return False
    ctx.register_system_prompt_section(SECTION_ID, prompt_section)
    ctx.register_hook("post_tool_call", on_post_tool_call)
    ctx.register_hook("transform_llm_output", on_transform_llm_output)
