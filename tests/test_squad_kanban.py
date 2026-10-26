"""squad-kanban plugin: CLI-filed cards reach the chat that filed them, and a worker with unsaved work is told to save.

The subscription test runs the real `hermes kanban create` on a temporary root and then calls the plugin's hook with
the terminal tool's real result shape; it reads the subscription back from Hermes's own kanban database.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from _real import HERMES, env_for, needs_hermes, temp_root

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "squads" / "_plugins" / "squad-kanban"


@pytest.fixture()
def plug(monkeypatch):
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    spec = importlib.util.spec_from_file_location("squad_kanban", PKG / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def terminal_result(output: str) -> str:
    return json.dumps({"output": output, "exit_code": 0, "error": None})


def test_only_a_create_command_reports_cards_and_only_the_ids_it_created(plug):
    created = "Created t_1a2b3c4d  (ready, assignee=web-frontend)\n"
    assert plug.filed_cards('hermes kanban --board web create "Hero" --assignee web-frontend', created) == ["t_1a2b3c4d"]
    assert plug.filed_cards("hermes kanban --board web show t_1a2b3c4d", created) == []
    listing = "● t_aaaa1111  running  web-frontend  Hero\n◻ t_bbbb2222  todo  web-qa  QA\n"
    assert plug.filed_cards("hermes kanban --board web list", listing) == [], "a list must never subscribe"
    chain = json.dumps({"cards": [{"id": "t_cccc3333"}, {"id": "t_dddd4444"}]})
    assert plug.filed_cards("scripts/hpy kanban_chain.py web milestone --project acme --title M1", chain) == [
        "t_cccc3333", "t_dddd4444"]


def test_a_worker_never_subscribes(plug, monkeypatch):
    calls = []
    monkeypatch.setattr(plug, "subscribe", lambda ids, board: calls.append(ids))
    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_0000aaaa")
    plug.on_post_tool_call("terminal", {"command": "hermes kanban create x --assignee y"},
                           terminal_result("Created t_1a2b3c4d  (ready, assignee=y)"))
    assert calls == []


DRIVER = """
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("squad_kanban", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
mod.on_post_tool_call("terminal", {"command": sys.argv[2]}, json.dumps({"output": sys.argv[3], "exit_code": 0}))
"""


def hermes_python() -> list[str]:
    """The Hermes runtime interpreter with its source root on sys.path (what a plugin runs inside)."""
    cmd = json.loads(subprocess.run([HERMES, "--print-runtime-command"], capture_output=True, text=True,
                                    env={k: v for k, v in os.environ.items() if k != "HERMES_HOME"}).stdout)
    root = cmd[3].split("sys.path.insert(0, '")[1].split("'")[0]
    return [cmd[0], "-I", "-c", f"import sys; sys.path.insert(0, {root!r}); import hermes_bootstrap; "
            "exec(sys.argv.pop(1))"]


@needs_hermes
def test_a_card_filed_with_the_cli_notifies_the_chat_that_filed_it(tmp_path):
    root = temp_root(tmp_path)
    env = {**env_for(root), "HERMES_SESSION_KEY": "20261025_120000_abcdef", "HERMES_SESSION_PROFILE": "default"}
    env = {k: v for k, v in env.items() if not k.startswith("HERMES_SESSION_") or k in (
        "HERMES_SESSION_KEY", "HERMES_SESSION_PROFILE")}
    run = lambda *a: subprocess.run([HERMES, *a], capture_output=True, text=True, env=env, timeout=180)
    assert run("kanban", "boards", "create", "web").returncode == 0
    cmd = ["kanban", "--board", "web", "create", "Hero section", "--assignee", "web-frontend"]
    made = run(*cmd)
    assert made.returncode == 0, made.stderr
    task = made.stdout.split()[1]
    db = root / "kanban" / "boards" / "web" / "kanban.db"

    def subs():
        with sqlite3.connect(db) as conn:
            return conn.execute("select platform, chat_id from kanban_notify_subs where task_id=?", (task,)).fetchall()

    assert subs() == [], "the CLI alone does not subscribe the chat (the gap this plugin closes)"
    hook = subprocess.run([*hermes_python(), DRIVER, str(PKG / "__init__.py"), "hermes " + " ".join(cmd), made.stdout],
                          capture_output=True, text=True, env=env, timeout=180)
    assert hook.returncode == 0, hook.stderr
    assert subs() == [("tui", "20261025_120000_abcdef")]


def git(repo: Path, *a: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, check=True).stdout


@pytest.fixture()
def worker(plug, tmp_path, monkeypatch):
    """The web layout: the card's workspace is the site folder, the git repo is `<site>/repo` (site.yaml repo.path)."""
    site = tmp_path / "site"
    repo = site / "repo"
    repo.mkdir(parents=True)
    (site / "site.yaml").write_text("slug: acme\nrepo: {path: repo}\n")
    git(repo, "init", "-q")
    git(repo, "config", "user.email", "bot@example.invalid")
    git(repo, "config", "user.name", "bot")
    (repo / "README.md").write_text("x\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_0000aaaa")
    monkeypatch.setenv("HERMES_KANBAN_WORKSPACE", str(site))
    clock = {"now": 1000.0}
    monkeypatch.setattr(plug.time, "monotonic", lambda: clock["now"])
    plug._state.update(nudged=0.0, checked=0.0)
    plug._written.clear()
    return plug, repo, clock


def write(plug, path: Path, text: str = "export const x = 1;\n") -> None:
    path.write_text(text)
    plug.on_transform_tool_result("write_file", {"path": str(path)}, '{"bytes_written": 1}')


def test_a_file_the_worker_wrote_unsaved_for_30_minutes_gets_a_save_reminder(worker):
    plug, repo, clock = worker
    write(plug, repo / "hero.ts")
    clock["now"] += 29 * 60
    assert plug.on_transform_tool_result("read_file", {}, "content") is None, "too early"
    clock["now"] += 2 * 60
    out = plug.on_transform_tool_result("read_file", {}, "content")
    assert out.startswith("content") and "save_progress.py" in out and "31 min" in out and "hero.ts" in out
    clock["now"] += 5 * 60
    assert plug.on_transform_tool_result("read_file", {}, "content") is None, "once per 10 minutes at most"


def test_a_committed_file_stops_its_clock(worker):
    plug, repo, clock = worker
    write(plug, repo / "hero.ts")
    clock["now"] += 20 * 60
    git(repo, "add", "hero.ts")
    git(repo, "commit", "-qm", "wip: hero")
    clock["now"] += 20 * 60
    assert plug.on_transform_tool_result("read_file", {}, "content") is None, "saved: nothing to remind"
    assert plug._written == {}, "the saved file leaves the list"


def test_another_builders_unsaved_files_never_nag_this_worker(worker):
    plug, repo, clock = worker
    (repo / "atmosphere.ts").write_text("half\n")  # another card, mid-edit, in the shared tree
    clock["now"] += 45 * 60
    assert plug.on_transform_tool_result("read_file", {}, "content") is None


def test_a_manager_chat_is_never_nagged(plug, monkeypatch, tmp_path):
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    plug._written.clear()
    plug._state.update(nudged=0.0, checked=0.0)
    assert plug.on_transform_tool_result("write_file", {"path": str(tmp_path / "x")}, "ok") is None
    assert plug._written == {}


def test_the_board_comes_from_any_form_of_the_command(plug):
    assert plug._board_of("hermes kanban --board web create x", "") == "web"
    assert plug._board_of("hermes kanban --board=web create x", "") == "web"
    assert plug._board_of("HERMES_KANBAN_BOARD=jobs hermes kanban create x", "") == "jobs"
    assert plug.filed_cards("hermes kanban --board=web create x", "Created t_1a2b3c4d  (ready)") == ["t_1a2b3c4d"]


def test_the_plugin_loads_under_hermes_and_registers_its_hooks(plug):
    hooks = []
    plug.register(type("Ctx", (), {"register_hook": lambda self, n, f: hooks.append(n)})())
    assert hooks == ["post_tool_call", "transform_tool_result"]
    manifest = (PKG / "plugin.yaml").read_text()
    assert all(f"- {h}" in manifest for h in hooks)