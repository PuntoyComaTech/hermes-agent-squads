"""Failures seen in real installs that no other test caught. Each test states the failure it pins.

Covered elsewhere (not repeated here): provider key missing in a bot profile
(test_squadctl::test_doctor_credentials_check_and_models_never_pass_without_them), provider plugin missing
(::test_doctor_flags_a_missing_provider_plugin_and_filters_by_squad), `mcp add` silent cancel
(::test_mcp_add_fails_loudly_when_the_server_does_not_land_enabled), board inside a Kanban worker
(::test_board_creation_is_the_owner_errand_inside_a_kanban_worker, ::test_an_existing_board_is_reported_inside_a_kanban_worker),
learned skills kept by apply (::test_learned_skills_are_reported_never_removed).
"""
import json

import pytest
import yaml

from test_squadctl import Env, models_doc  # noqa: F401  (the shared fake-hermes harness)


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


def test_a_toolset_hermes_does_not_know_fails_apply_instead_of_vanishing(env, capsys):
    """Real `hermes tools enable` prints "Unknown toolset" and exits 0, and squadctl had already written the name
    into platform_toolsets.cli itself: the bot silently lacked the tool and status showed no drift."""
    env.squad("web", lambda s: s["bots"]["web-qa"]["toolsets"].append("browsr"))
    _, out = env.run("apply", "web", "--bots", "web-qa", expect=1, capsys=capsys)
    assert "browsr" in out["error"] and "web-qa" in out["error"], out


def test_an_unquoted_1m_model_id_in_a_flow_mapping_is_a_clear_error(env, capsys):
    """`{provider: p, model: claude-opus-5-5[1m]}` is invalid YAML for both PyYAML and Hermes's ruamel loader.
    squadctl crashed with a parser traceback that did not name the file; it must stop with the file and the fix."""
    env.squad("web")
    env.models.write_text("lanes:\n" + "".join(
        f"  {lane}: {{provider: prov-{lane}, model: model-{lane}[1m]}}\n" for lane in models_doc()["lanes"]))
    _, out = env.run("plan", "web", expect=1, capsys=capsys)
    assert str(env.models) in out["error"] and "[1m]" in out["error"] and "quote" in out["error"], out


def test_a_quoted_1m_model_id_is_applied_whole(env, capsys):
    """The quoted form must reach the profile intact, suffix included."""
    env.squad("web")
    env.models.write_text("lanes:\n" + "".join(
        f"  {lane}: {{provider: prov-{lane}, model: 'model-{lane}[1m]'}}\n" for lane in models_doc()["lanes"]))
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    assert env.config("web-qa")["model"]["default"] == "model-review[1m]"


def test_a_stale_bot_pin_in_installed_yaml_is_visible_in_plan(env, capsys):
    """A per-bot pin left in local/installed.yaml beats the lane forever, even after --models changes the lane:
    the wrong model is applied and nothing says why. Plan must name the pin when it overrides a lane."""
    env.squad("web")
    doc = models_doc()
    doc["bots"] = {"web-qa": {"provider": "old-prov", "model": "old-model"}}
    env.models.write_text(yaml.safe_dump(doc))
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)  # the pin lands in installed.yaml
    env.models.write_text(yaml.safe_dump(models_doc()))  # a new models file without the pin
    _, out = env.run("plan", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    text = json.dumps(qa)
    assert env.config("web-qa")["model"]["default"] == "old-model"
    assert "old-model" in text and "pin" in text, qa
