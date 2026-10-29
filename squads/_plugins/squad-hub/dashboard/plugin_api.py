"""squad-hub backend: the read-only Kanban data its Desktop panes need.

The Desktop plugin SDK has no door to another plugin's REST, so the Squads Hub panes cannot call
``/api/plugins/kanban/*``. This router serves the three reads they need — the board list with its counts, one
board with its columns, and one card with its comments, events and runs — from the same ``hermes_cli.kanban_db``
code the Kanban page uses, so the two surfaces cannot drift. GET only: nothing here writes.

Mounted at ``/api/plugins/squad-hub/`` and reached by the desktop half through ``ctx.rest``.
"""

from __future__ import annotations

import time
from contextlib import closing
from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from hermes_cli import kanban_db
from hermes_cli import kanban_db_connect as kbc
from hermes_cli import kanban_workflow

router = APIRouter()

# Dashboard columns, left to right, from the one workflow definition (a status missing here falls into `todo`).
BOARD_COLUMNS: list[str] = list(kanban_workflow.DEFAULT_WORKFLOW.keys())
_CARD_SUMMARY_PREVIEW_CHARS = 200
_BOARD_Q = Query(None, description="Kanban board slug (omit for the active board)")


def _connect(board: Optional[str]):
    """A connection to an existing board (404 otherwise); ``None`` keeps the active board."""
    if board:
        try:
            normed = kanban_db._normalize_board_slug(board)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=f"board {board!r} does not exist") from exc
        if not normed or not kanban_db.board_exists(normed):
            raise HTTPException(status_code=404, detail=f"board {board!r} does not exist")
        board = normed
    return kbc.connect(board=board)


def _board_counts(slug: str) -> dict[str, int]:
    """``{status: count}`` for a board; ``{}`` on a missing or unreadable store."""
    try:
        if not kanban_db.kanban_db_path(board=slug).exists():
            return {}
        with closing(kbc.connect(board=slug)) as conn:
            rows = conn.execute("SELECT status, COUNT(*) AS n FROM tasks GROUP BY status").fetchall()
            return {r["status"]: int(r["n"]) for r in rows}
    except Exception:  # noqa: BLE001 - a count is never a reason to fail the list
        return {}


def _task_row(task, summary: Optional[str] = None) -> dict[str, Any]:
    row = asdict(task)
    row["latest_summary"] = summary
    return row


@router.get("/boards")
def list_boards(include_archived: bool = Query(False)) -> dict[str, Any]:
    """Every board on disk with its live task count and which one is active."""
    boards = kanban_db.list_boards(include_archived=include_archived)
    current = kanban_db.get_current_board()
    for board in boards:
        board["is_current"] = board["slug"] == current
        counts = board["counts"] = _board_counts(board["slug"])
        board["total"] = sum(n for status, n in counts.items() if status != "archived")
    return {"boards": boards, "current": current}


@router.get("/board")
def get_board(
    board: Optional[str] = _BOARD_Q,
    tenant: Optional[str] = Query(None),
    include_archived: bool = Query(False),
) -> dict[str, Any]:
    """One board grouped by status column, cards carrying a summary preview."""
    with closing(_connect(board)) as conn:
        tasks = kanban_db.list_tasks(conn, tenant=tenant, include_archived=include_archived)
        summaries = kanban_db.latest_summaries(conn, [t.id for t in tasks])
        columns: dict[str, list[dict[str, Any]]] = {name: [] for name in BOARD_COLUMNS}
        if include_archived:
            columns["archived"] = []
        for task in tasks:
            full = summaries.get(task.id)
            row = _task_row(task, full[:_CARD_SUMMARY_PREVIEW_CHARS] if full else None)
            columns[task.status if task.status in columns else "todo"].append(row)
        tenants = [r["tenant"] for r in conn.execute(
            "SELECT DISTINCT tenant FROM tasks WHERE tenant IS NOT NULL ORDER BY tenant")]
        assignees = [entry["name"] for entry in kanban_db.known_assignees(conn)]
        latest = conn.execute("SELECT COALESCE(MAX(id), 0) AS m FROM task_events").fetchone()["m"]
    return {
        "columns": [{"name": name, "tasks": columns[name]} for name in columns],
        "tenants": tenants,
        "assignees": assignees,
        "latest_event_id": int(latest),
        "now": int(time.time()),
    }


@router.get("/tasks/{task_id}")
def get_task(task_id: str, board: Optional[str] = _BOARD_Q) -> dict[str, Any]:
    """One card with its full summary, comments, events and runs — what the card dialog draws."""
    with closing(_connect(board)) as conn:
        task = kanban_db.get_task(conn, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"task {task_id} not found")
        return {
            "task": _task_row(task, kanban_db.latest_summary(conn, task_id)),
            "comments": [asdict(c) for c in kanban_db.list_comments(conn, task_id)],
            "events": [asdict(e) for e in kanban_db.list_events(conn, task_id)],
            "runs": [asdict(r) for r in kanban_db.list_runs(conn, task_id)],
        }
