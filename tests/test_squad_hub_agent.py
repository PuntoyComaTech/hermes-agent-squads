"""squad-hub agent half: what a manager is told about asking the user, and the Kanban cards appended to its Desktop
replies. Payload shapes are Hermes 0.22's: `kanban_create` returns `{"ok": true, "task_id": ...}` as a JSON string,
`transform_llm_output` gets `response_text, session_id, platform` and replaces the reply with the first string a hook
returns, prompt sections get `{session_id, model, provider, platform, profile_name, cwd}`."""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "squads" / "_plugins" / "squad-hub"


@pytest.fixture()
def hub(monkeypatch):
    monkeypatch.delenv("HERMES_KANBAN_TASK", raising=False)
    spec = importlib.util.spec_from_file_location("squad_hub_agent", PKG / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "_cards_on", lambda: True)
    return mod


def created(task_id, ok=True):
    return json.dumps({"ok": ok, "task_id": task_id, "status": "ready", "gated": False})


def info(platform):
    return {"session_id": "s1", "model": "m", "provider": "p", "platform": platform, "profile_name": "web", "cwd": "/x"}


def test_a_manager_in_a_chat_asks_with_choices_and_desktop_also_gets_the_card_grammar(hub):
    desktop = hub.prompt_section(info("desktop"))
    assert "`clarify`" in desktop and "choices" in desktop and '"ok"' in desktop and "yes or no" in desktop
    assert "::squad-task{" in desktop and "blank line" in desktop
    assert "independent questions in one call" in desktop, "Hermes' clarify takes several questions per call"
    assert "do not write the question" in desktop
    telegram = hub.prompt_section(info("telegram"))
    assert "`clarify`" in telegram and "::squad-task" not in telegram, "a channel would show the card line raw"


def test_nobody_answers_a_cron_run_or_a_kanban_worker(hub, monkeypatch):
    assert hub.prompt_section(info("cron")) == ""
    assert hub.prompt_section(info("subagent")) == ""
    for nobody in ("webhook", "msgraph_webhook", "api_server"):
        assert hub.prompt_section(info(nobody)) == "", nobody
    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_abcd")
    assert hub.prompt_section(info("desktop")) == ""


def test_a_card_filed_this_turn_is_appended_to_the_desktop_reply_once(hub):
    hub.on_post_tool_call(tool_name="kanban_create", args={"board": "web", "title": "hero"}, result=created("t_ab12"),
                          session_id="s1")
    hub.on_post_tool_call(tool_name="kanban_create", args={}, result=created("t_cd34"), session_id="s1")
    out = hub.on_transform_llm_output(response_text="Filed two cards for the hero section.", session_id="s1",
                                      platform="desktop")
    assert out == ('Filed two cards for the hero section.\n\n::squad-task{board="web" id="t_ab12"}'
                   '\n\n::squad-task{id="t_cd34"}'), "no board named: the card reads the current board"
    # each line is its own paragraph: Desktop only draws a directive whose paragraph holds nothing else
    for para in out.split("\n\n")[1:]:
        assert re.fullmatch(r'::squad-task\{(board="web" )?id="t_[0-9a-f]+"\}', para)
    assert hub.on_transform_llm_output(response_text="next turn", session_id="s1", platform="desktop") is None


def test_a_card_filed_with_the_kanban_cli_gets_its_live_card_too(hub):
    """Managers also file from the terminal (`hermes kanban create`, kanban_chain.py); those cards must show as well."""
    out = json.dumps({"output": "Created t_ab12cd34  (ready, assignee=web-frontend)\n", "exit_code": 0})
    hub.on_post_tool_call(tool_name="terminal", result=out, session_id="s1",
                          args={"command": 'hermes kanban --board web create "Hero" --assignee web-frontend'})
    listing = json.dumps({"output": "● t_99998888  running  web-qa  QA\n", "exit_code": 0})
    hub.on_post_tool_call(tool_name="terminal", args={"command": "hermes kanban --board web list"}, result=listing,
                          session_id="s1")
    reply = hub.on_transform_llm_output(response_text="Filed the hero card.", session_id="s1", platform="desktop")
    assert reply == 'Filed the hero card.\n\n::squad-task{board="web" id="t_ab12cd34"}', "a listed card is not filed"


def test_a_reply_that_already_shows_the_card_is_left_alone(hub):
    hub.on_post_tool_call(tool_name="kanban_create", args={"board": "web"}, result=created("t_ab12"), session_id="s1")
    text = 'Done.\n\n::squad-task{board="web" id="t_ab12"}'
    assert hub.on_transform_llm_output(response_text=text, session_id="s1", platform="desktop") is None


def test_channels_failures_and_other_tools_never_get_a_card(hub):
    hub.on_post_tool_call(tool_name="kanban_create", args={}, result=created("t_ab12"), session_id="s1")
    assert hub.on_transform_llm_output(response_text="Filed.", session_id="s1", platform="discord") is None
    # the ledger is spent even on a channel: a later Desktop turn must not inherit a stale card
    assert hub.on_transform_llm_output(response_text="Later.", session_id="s1", platform="desktop") is None
    hub.on_post_tool_call(tool_name="kanban_create", args={}, result=created("t_ab12", ok=False), session_id="s2")
    hub.on_post_tool_call(tool_name="kanban_comment", args={}, result=created("t_cd34"), session_id="s2")
    hub.on_post_tool_call(tool_name="kanban_create", args={}, result="not json", session_id="s2")
    hub.on_post_tool_call(tool_name="kanban_create", args={"board": "../etc"}, result=created("t_ef56"), session_id="s3")
    assert hub.on_transform_llm_output(response_text="x", session_id="s2", platform="desktop") is None
    out = hub.on_transform_llm_output(response_text="x", session_id="s3", platform="desktop")
    assert out == 'x\n\n::squad-task{id="t_ef56"}', "an invalid board slug is dropped, the card still shows"


def test_a_worker_filing_cards_records_nothing(hub, monkeypatch):
    monkeypatch.setenv("HERMES_KANBAN_TASK", "t_0000")
    hub.on_post_tool_call(tool_name="kanban_create", args={}, result=created("t_ab12"), session_id="s1")
    monkeypatch.delenv("HERMES_KANBAN_TASK")
    assert hub.on_transform_llm_output(response_text="x", session_id="s1", platform="desktop") is None


def test_at_most_three_cards_and_an_open_code_block_is_closed_first(hub):
    for i in range(5):
        hub.on_post_tool_call(tool_name="kanban_create", args={"board": "web"}, result=created(f"t_aa0{i}"),
                              session_id="s1")
    out = hub.on_transform_llm_output(response_text="Plan:\n```\nstep 1", session_id="s1", platform="desktop")
    assert out.count("::squad-task") == 3
    assert out.index("```\n\n::squad-task") > out.index("step 1"), "the cards sit outside the code block"


def test_the_manifest_declares_the_hooks_register_adds(hub):
    import yaml
    manifest = yaml.safe_load((PKG / "plugin.yaml").read_text())
    seen = []

    class Ctx:
        def register_system_prompt_section(self, sid, fn):
            seen.append(("section", sid))

        def register_hook(self, name, fn):
            seen.append(("hook", name))

    hub.register(Ctx())
    assert sorted(n for k, n in seen if k == "hook") == sorted(manifest["provides_hooks"])
    assert ("section", "squad-hub.conversation") in seen


def test_a_card_filed_before_a_mid_turn_compression_still_reaches_the_reply(hub):
    """Compression rotates the session id inside a turn; the turn id does not change, so the card is not lost."""
    hub.on_post_tool_call(tool_name="kanban_create", args={"board": "web"}, result=created("t_ab12"),
                          session_id="s-before", turn_id="turn-7")
    out = hub.on_transform_llm_output(response_text="Filed it.", session_id="s-after", platform="desktop",
                                      turn_id="turn-7")
    assert out == 'Filed it.\n\n::squad-task{board="web" id="t_ab12"}'
    assert hub._owed == {}, "nothing leaks for the next turn"


def test_a_card_the_reply_wrote_with_single_quotes_is_not_added_twice(hub):
    hub.on_post_tool_call(tool_name="kanban_create", args={"board": "web"}, result=created("t_ab12"), session_id="s1")
    text = "Done.\n\n::squad-task{board='web' id='t_ab12'}"
    assert hub.on_transform_llm_output(response_text=text, session_id="s1", platform="desktop") is None


def test_without_the_desktop_half_no_card_lines_are_taught_or_appended(hub, monkeypatch):
    """The agent half runs on every manager, the desktop half is opt-in; Desktop leaves an unregistered `::name{}`
    line as raw text, so with the desktop half off neither the prompt nor the append may produce one."""
    monkeypatch.setattr(hub, "_cards_on", lambda: False)
    assert "::squad-task" not in hub.prompt_section(info("desktop"))
    hub.on_post_tool_call(tool_name="kanban_create", args={"board": "web"}, result=created("t_ab12"), session_id="s1")
    assert hub.on_transform_llm_output(response_text="Filed.", session_id="s1", platform="desktop") is None


def test_the_cards_switch_is_the_plugin_setting_desktop_writes(hub):
    seen = []

    class Ctx:
        def register_system_prompt_section(self, sid, fn): pass
        def register_hook(self, name, fn): pass
        def get_config(self, key, default=None):
            seen.append(key)
            return {"desktop_cards": True}.get(key, default)
    hub.register(Ctx())
    assert hub._cards_on() is True and seen == ["desktop_cards"]
    import yaml
    schema = yaml.safe_load((PKG / "plugin.yaml").read_text())["config_schema"]
    assert schema["desktop_cards"]["default"] is False
