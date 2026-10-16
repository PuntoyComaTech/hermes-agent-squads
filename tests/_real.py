"""Helpers for tests that run the real `hermes` binary against a temporary root.

Two traps make a real-hermes test lie when it runs from inside Hermes (a Kanban worker, a delegate child):
- the parent's fence (`HERMES_DELEGATED_CHILD_CONTEXT`) and board pins (`HERMES_KANBAN_*`) leak into the child
  and make every kanban mutation fail;
- a `HERMES_HOME` under `~/.hermes` resolves the shared root (kanban boards, profiles list) to the REAL `~/.hermes`
  (hermes_constants.get_default_hermes_root), so the test would read or write the owner's data.
`env_for` strips the first and `temp_root` refuses the second.
"""
import os
import shutil
from pathlib import Path

import pytest

HERMES = shutil.which("hermes")
needs_hermes = pytest.mark.skipif(not HERMES, reason="the real `hermes` binary is not on PATH")
LEAKED = ("HERMES_DELEGATED_CHILD_CONTEXT", "HERMES_KANBAN_TASK", "HERMES_KANBAN_DB", "HERMES_KANBAN_BOARD",
          "HERMES_KANBAN_WORKSPACE", "HERMES_KANBAN_WORKSPACES_ROOT", "HERMES_KANBAN_HOME", "HERMES_PROFILE",
          "HERMES_SESSION_ID")


def temp_root(tmp_path: Path) -> Path:
    root = tmp_path / "hermes-root"
    root.mkdir()
    real = (Path.home() / ".hermes").resolve()
    if root.resolve() == real or real in root.resolve().parents:
        pytest.skip(f"temp root {root} is under {real}: Hermes would resolve the real root; set TMPDIR elsewhere")
    return root


def env_for(root: Path, **extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in LEAKED}
    return {**env, "HERMES_HOME": str(root), **extra}


def scrub(monkeypatch, root: Path) -> None:
    """The same as env_for, applied to this process (for code that shells out with os.environ)."""
    for k in LEAKED:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("HERMES_HOME", str(root))
