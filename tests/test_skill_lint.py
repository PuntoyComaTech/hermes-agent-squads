"""skill_lint.py against the batch 0 fixtures and synthetic trees. Pure local; never touches the real ~/.hermes."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures" / "skills"
GOOD = FIX / "good"
BAD = FIX / "bad"
RULES = yaml.safe_load((BAD / "rules.yaml").read_text())["rules"]
SCRIPT = REPO / "scripts" / "skill_lint.py"
HAVE_SHELLCHECK = shutil.which("shellcheck") is not None

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("skill_lint", SCRIPT)
skill_lint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(skill_lint)


@pytest.fixture(autouse=True)
def temp_hermes_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path_factory.mktemp("hermes-home")))


def lint(capsys, *args):
    rc = skill_lint.main([*map(str, args), "--json"])
    return rc, json.loads(capsys.readouterr().out)


def rules_of(report):
    return {f["rule"] for f in report["findings"]}


def make_skill(tmp_path, name="building-widgets", body_extra="", desc=None, container="skills"):
    """Copy the good skill under tmp_path/<container>/<name>, optionally renamed and padded."""
    dest = tmp_path / container / name
    shutil.copytree(GOOD / "building-widgets", dest)
    md = dest / "SKILL.md"
    text = md.read_text().replace("name: building-widgets", f"name: {name}")
    if desc is not None:
        text = text.replace(
            'description: "Builds dashboard widgets from a data contract. Use when a card asks for a new widget or a widget fix."',
            f'description: "{desc}"')
    md.write_text(text + body_extra)
    return dest


def pad(lines):
    return "\n".join(f"- Extra check number {i}." for i in range(lines)) + "\n"


# --- rule registry and fixtures ---------------------------------------------------------------------------------

def test_rule_ids_match_fixture_rules():
    assert set(skill_lint.RULES) == set(RULES)


def test_good_fixtures_pass(capsys):
    rc, report = lint(capsys, GOOD)
    assert rc == 0, report["findings"]
    assert report["ok"] and len(report["targets"]) == 2  # the skill and the SOUL file


@pytest.mark.parametrize("rule", sorted(RULES))
def test_bad_fixture_fails_only_its_rule(rule, capsys):
    if rule == "script-shellcheck" and not HAVE_SHELLCHECK:
        pytest.skip("shellcheck not installed")
    rc, report = lint(capsys, BAD / rule)
    assert rc == 1
    assert rules_of(report) == {rule}, report["findings"]


def test_shellcheck_missing_is_skipped_or_required(capsys, monkeypatch):
    monkeypatch.setattr(skill_lint.shutil, "which", lambda name: None)
    rc, report = lint(capsys, BAD / "script-shellcheck")
    assert rc == 0 and report["skipped"]
    rc, report = lint(capsys, BAD / "script-shellcheck", "--require-shellcheck")
    assert rc == 1 and rules_of(report) == {"script-shellcheck"}


# --- budgets ----------------------------------------------------------------------------------------------------

def test_default_budget_is_worker(tmp_path, capsys):
    skill = make_skill(tmp_path, body_extra=pad(100))  # 24 + 100 = ~124 lines
    rc, report = lint(capsys, skill)
    assert rules_of(report) == {"skill-lines"}


def test_role_flag_forces_lead_budget(tmp_path, capsys):
    skill = make_skill(tmp_path, body_extra=pad(100))
    assert lint(capsys, skill, "--role", "lead")[0] == 0
    assert lint(capsys, make_skill(tmp_path, name="building-extras", body_extra=pad(140)), "--role", "lead")[0] == 1


def test_builder_skills_get_lead_budget(tmp_path, capsys):
    (tmp_path / "builder.yaml").write_text("key: builder\n")
    skill = make_skill(tmp_path, body_extra=pad(100))
    assert lint(capsys, skill)[0] == 0


def _squad(tmp_path, skill_users):
    squad = tmp_path / "squads" / "web"
    bots = {bot: {"role": "lead" if bot == "web" else "worker", "skills": {"squad": ["building-widgets"] if bot in skill_users else []}}
            for bot in ("web", "web-frontend")}
    squad.mkdir(parents=True)
    (squad / "squad.yaml").write_text(yaml.safe_dump({"schema": 2, "key": "web", "lead": "web", "bots": bots}))
    return make_skill(squad, body_extra=pad(100))


def test_lead_only_squad_skill_gets_lead_budget(tmp_path, capsys):
    assert lint(capsys, _squad(tmp_path, {"web"}))[0] == 0


def test_skill_used_by_a_worker_gets_worker_budget(tmp_path, capsys):
    rc, report = lint(capsys, _squad(tmp_path, {"web", "web-frontend"}))
    assert rules_of(report) == {"skill-lines"}


def test_index_budget_applies_to_hermes_platform(tmp_path, capsys):
    skill = make_skill(tmp_path, name="hermes-platform", body_extra=pad(60))  # ~84 lines: over 80, under 120
    assert rules_of(lint(capsys, skill)[1]) == {"index-lines"}


@pytest.mark.parametrize("name", ["site-contract", "jobs-contract", "hermes-platform", "marketing-plan",
                                  "product-marketing", "marketing-council", "marketing-psychology"])
def test_gerund_exemptions(name, tmp_path, capsys):
    assert lint(capsys, make_skill(tmp_path, name=name))[0] == 0


def test_non_gerund_still_fails(tmp_path, capsys):
    assert rules_of(lint(capsys, make_skill(tmp_path, name="widget-helper"))[1]) == {"name-gerund"}


def _desc(capability_len):
    capability = "Builds " + "x" * (capability_len - len("Builds .")) + "."
    assert len(capability) == capability_len
    return f"{capability} Use when a card asks for a widget."


def test_capability_clause_boundary(tmp_path, capsys):
    assert lint(capsys, make_skill(tmp_path, desc=_desc(57)))[0] == 0
    rc, report = lint(capsys, make_skill(tmp_path, name="building-more", desc=_desc(58)))
    assert rules_of(report) == {"desc-capability-length"}


def test_description_length_boundary(tmp_path, capsys):
    head = "Builds a widget. Use when a card asks for a widget "
    ok = head + "x" * (250 - len(head) - 1) + "."
    assert len(ok) == 250
    assert lint(capsys, make_skill(tmp_path, desc=ok))[0] == 0
    assert rules_of(lint(capsys, make_skill(tmp_path, name="building-more", desc=ok + "x"))[1]) == {"desc-length"}


def test_reference_toc_and_lines_boundaries(tmp_path, capsys):
    skill = make_skill(tmp_path)
    ref = skill / "references" / "widget-contract.md"
    body = ref.read_text().splitlines()
    ref.write_text("\n".join((body + ["- filler"] * 200)[:200]) + "\n")  # exactly 200 lines, TOC kept
    assert lint(capsys, skill)[0] == 0
    ref.write_text("\n".join((body + ["- filler"] * 200)[:201]) + "\n")
    assert rules_of(lint(capsys, skill)[1]) == {"ref-lines"}


def test_soul_boundaries(tmp_path, capsys):
    soul = tmp_path / "souls" / "web-frontend.md"
    soul.parent.mkdir()
    soul.write_text("Line one is short.\n" * 6)
    assert lint(capsys, soul)[0] == 0
    soul.write_text("x" * 800 + "\n")
    assert lint(capsys, soul)[0] == 0
    soul.write_text("x" * 801 + "\n")
    assert rules_of(lint(capsys, soul)[1]) == {"soul-chars"}


# --- text rules -------------------------------------------------------------------------------------------------

def test_english_homographs_do_not_trip_language(tmp_path, capsys):
    extra = "\n- I said no, a son did come with me, he is sin free, and so on, no a me he son sin come.\n" * 3
    assert lint(capsys, make_skill(tmp_path, body_extra=extra))[0] == 0


def test_spanish_inside_code_is_ignored(tmp_path, capsys):
    extra = "\n```\nnunca cambies los colores de la marca sin la aprobacion del cliente porque el equipo de diseno\n```\n"
    assert lint(capsys, make_skill(tmp_path, body_extra=extra))[0] == 0


def test_model_id_in_a_script_is_found(tmp_path, capsys):
    skill = make_skill(tmp_path)
    (skill / "scripts" / "render_widget.py").write_text(
        (skill / "scripts" / "render_widget.py").read_text() + "\nMODEL = 'gpt-9.1-turbo'\n")
    assert rules_of(lint(capsys, skill)[1]) == {"model-ids"}


def test_model_id_from_custom_roles_is_found(tmp_path, capsys):
    roles = tmp_path / "roles.yaml"
    roles.write_text(yaml.safe_dump({"lanes": {"x": {"candidates": [{"family": "f", "match": r"zed-nine"}]}}}))
    skill = make_skill(tmp_path, body_extra="\n- Prefer zed-nine for previews.\n")
    assert rules_of(lint(capsys, skill, "--roles", roles)[1]) == {"model-ids"}
    assert lint(capsys, skill)[0] == 0


def test_model_id_in_squad_yaml_is_found(tmp_path, capsys):
    squad = tmp_path / "squads" / "web"
    squad.mkdir(parents=True)
    (squad / "squad.yaml").write_text("description: runs on claude-sonnet-5-5\n")
    assert rules_of(lint(capsys, tmp_path)[1]) == {"model-ids"}


def test_model_prose_without_an_id_passes(tmp_path, capsys):
    assert lint(capsys, make_skill(tmp_path, body_extra="\n- Models are chosen per lane, never by name.\n"))[0] == 0


# --- scripts ----------------------------------------------------------------------------------------------------

def test_lint_leaves_no_bytecode_behind(tmp_path, capsys):
    skill = make_skill(tmp_path)
    assert lint(capsys, skill)[0] == 0
    assert not list(skill.rglob("__pycache__"))


def test_scripts_run_under_a_temp_hermes_home(tmp_path, capsys, monkeypatch):
    sentinel = tmp_path / "sentinel-home"
    monkeypatch.setenv("HERMES_HOME", str(sentinel))
    skill = make_skill(tmp_path)
    script = skill / "scripts" / "render_widget.py"
    script.write_text(
        "import os, sys\n"
        f"sys.exit(3 if os.environ.get('HERMES_HOME') == {str(sentinel)!r} or not os.environ.get('HERMES_HOME') else 0)\n")
    assert lint(capsys, skill)[0] == 0


def test_underscore_modules_are_compiled_but_not_run(tmp_path, capsys):
    skill = make_skill(tmp_path)
    (skill / "scripts" / "_helpers.py").write_text("raise SystemExit(9)\n")
    assert lint(capsys, skill)[0] == 0
    (skill / "scripts" / "_helpers.py").write_text("def broken(:\n")
    assert rules_of(lint(capsys, skill)[1]) == {"script-py-compile"}


def test_extensionless_shebang_scripts_are_checked(tmp_path, capsys):
    skill = make_skill(tmp_path)
    (skill / "scripts" / "run").write_text("#!/usr/bin/env bash\nexit 4\n")
    assert rules_of(lint(capsys, skill, "--no-scripts")[1]) == set()
    assert rules_of(lint(capsys, skill)[1]) == {"script-help"}


def test_no_scripts_flag_skips_script_rules(capsys):
    assert lint(capsys, BAD / "script-help", "--no-scripts")[0] == 0


# --- discovery and CLI ------------------------------------------------------------------------------------------

def test_tree_walk_finds_skills_and_souls_but_skips_tests_and_docs(tmp_path, capsys):
    make_skill(tmp_path, container="skills")
    make_skill(tmp_path / "squads" / "web", container="skills")
    (tmp_path / "squads" / "web" / "souls").mkdir()
    shutil.copy(GOOD / "souls" / "web-frontend.md", tmp_path / "squads" / "web" / "souls")
    (tmp_path / "SOUL.md").write_text("You are `builder`.\n")
    shutil.copytree(BAD / "skill-lines", tmp_path / "tests" / "fixtures")
    shutil.copytree(BAD / "skill-lines", tmp_path / "docs" / "examples")
    rc, report = lint(capsys, tmp_path)
    assert rc == 0, report["findings"]
    assert len(report["targets"]) == 4


def test_nested_skill_md_inside_a_skill_is_a_child_violation(tmp_path, capsys):
    skill = make_skill(tmp_path)
    (skill / "other").mkdir()
    shutil.copy(skill / "SKILL.md", skill / "other" / "SKILL.md")
    assert rules_of(lint(capsys, skill)[1]) == {"children-allowed"}


def test_evals_dir_may_only_hold_evals_json(tmp_path, capsys):
    skill = make_skill(tmp_path)
    (skill / "evals" / "notes.md").write_text("notes\n")
    assert rules_of(lint(capsys, skill)[1]) == {"children-allowed"}


def test_missing_path_is_a_usage_error(capsys):
    assert skill_lint.main(["/nonexistent/skill-path"]) == 2
    assert "no such path" in capsys.readouterr().err


def test_rules_listing(capsys):
    assert skill_lint.main(["--rules", "--json"]) == 0
    assert set(json.loads(capsys.readouterr().out)) == set(RULES)


def test_default_text_output(capsys):
    assert skill_lint.main([str(BAD / "soul-lines")]) == 1
    out = capsys.readouterr().out
    assert out.startswith("FAIL soul-lines ") and out.rstrip().endswith("fail: 1 targets, 1 findings")
    assert skill_lint.main([str(GOOD)]) == 0
    assert capsys.readouterr().out.strip() == "ok: 2 targets, 0 findings"


def test_json_report_shape(capsys):
    rc, report = lint(capsys, BAD / "name-length")
    assert set(report) == {"ok", "targets", "findings", "counts", "skipped"}
    assert report["counts"] == {"name-length": 1}
    assert set(report["findings"][0]) >= {"rule", "path", "message"}


def test_help_works_offline_as_a_subprocess():
    done = subprocess.run([sys.executable, "-B", str(SCRIPT), "--help"], capture_output=True, text=True, timeout=20,
                          env={"PATH": "/usr/bin:/bin", "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9"})
    assert done.returncode == 0 and "--json" in done.stdout
