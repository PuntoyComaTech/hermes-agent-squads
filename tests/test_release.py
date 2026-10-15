"""release.py: bump + changelog checks, the four gates and the push-vs-PR decision."""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
spec = importlib.util.spec_from_file_location("release", SCRIPTS / "release.py")
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def cp(stdout="", code=0, stderr=""):
    return subprocess.CompletedProcess([], code, stdout, stderr)


# --- bump and changelog ----------------------------------------------------------------------------------------------

def test_bump_and_changelog_green():
    checks = release.meta_checks("2.1.0", "2.0.0", "# Changelog\n\n## 2.1.0 - 2026-10-15\n", "origin")
    assert all(ok for _n, ok, _d in checks), checks


def test_bump_red_when_version_unchanged():
    checks = release.meta_checks("2.0.0", "2.0.0", "## 2.0.0 - 2026-01-01\n", "origin")
    assert checks[0][1] is False and "not a bump" in checks[0][2]


def test_bump_red_when_version_goes_back():
    checks = release.meta_checks("1.9.0", "2.0.0", "## 1.9.0\n", "origin")
    assert checks[0][1] is False


def test_first_release_without_distribution_on_main():
    checks = release.meta_checks("2.0.0", None, "## 2.0.0\n", "origin")
    assert checks[0][1] is True and "first release" in checks[0][2]


def test_changelog_red_without_entry():
    checks = release.meta_checks("2.1.0", "2.0.0", "## 2.0.0\n", "origin")
    assert checks[1][1] is False and "## 2.1.0" in checks[1][2]


def test_missing_version_is_red():
    assert release.meta_checks(None, "1.0.0", "", "origin")[0][1] is False


def test_version_parsing():
    assert release.dist_version("name: builder\nversion: 2.0.0\n") == "2.0.0"
    assert release.dist_version(None) is None
    assert release.version_tuple("2.10.1") > release.version_tuple("2.9.9")


# --- schema gate ------------------------------------------------------------------------------------------------------

def test_schema_gate_passes_on_the_shipped_manifests():
    name, ok, detail = release.gate_schema()
    assert name == "schema" and ok, detail


def test_schema_gate_rejects_more_than_five_bots():
    import copy

    import yaml
    from jsonschema import Draft202012Validator

    doc = yaml.safe_load((REPO / "squads" / "web" / "squad.yaml").read_text())
    doc = copy.deepcopy(doc)
    for i in range(6):
        doc["bots"][f"web-extra-{i}"] = copy.deepcopy(next(iter(doc["bots"].values())))
    validator = Draft202012Validator(
        json.loads((REPO / "squads" / "_schema" / "squad.schema.json").read_text()))
    assert any("5" in e.message for e in validator.iter_errors(doc)), "no maxProperties: 5 on bots"


# --- plan gate --------------------------------------------------------------------------------------------------------

def test_plan_gate_runs_every_squad_on_a_temp_root(monkeypatch, tmp_path):
    seen = []

    def fake_run(argv, env=None, **kw):
        seen.append((argv, env))
        return cp('{"ok": true}')

    monkeypatch.setattr(release, "run_cmd", fake_run)
    name, ok, detail = release.gate_plan("python3")
    assert ok, detail
    assert [a[2] for a, _e in seen] == ["--self", *release.squad_keys()]
    homes = {env["HERMES_HOME"] for _a, env in seen}
    assert len(homes) == 1, "every plan must share one temp root"
    home = Path(homes.pop())
    assert home != Path.home() / ".hermes" and not home.exists(), "the temp HERMES_HOME is cleaned up"
    for argv, env in seen:
        assert argv[0].endswith("scripts/squadctl") and argv[1] == "plan"
        assert env["HPY_PYTHON"] == "python3"
    assert len(seen) == 5  # --self + web, marketing, jobs, studio


def test_plan_gate_reports_the_failing_plan(monkeypatch):
    calls = []

    def fake_run(argv, env=None, **kw):
        calls.append(argv)
        return cp("error: boom", code=1) if len(calls) == 2 else cp("{}")

    monkeypatch.setattr(release, "run_cmd", fake_run)
    name, ok, detail = release.gate_plan("python3")
    assert not ok and "failed" in detail


# --- push vs PR -------------------------------------------------------------------------------------------------------

def test_green_checks_push_to_main(monkeypatch, capsys):
    monkeypatch.setattr(release, "run_cmd", lambda *a, **k: cp("version: 1.0.0\n"))
    monkeypatch.setattr(release, "gate_pytest", lambda py: ("pytest", True, "338 passed"))
    monkeypatch.setattr(release, "gate_skill_lint", lambda py: ("skill_lint", True, "ok"))
    monkeypatch.setattr(release, "gate_schema", lambda: ("schema", True, "ok"))
    monkeypatch.setattr(release, "gate_plan", lambda py: ("plan", True, "ok"))
    pushed, pr = [], []
    monkeypatch.setattr(release, "push_to_main", lambda remote: (pushed.append(remote), (True, ""))[1])
    monkeypatch.setattr(release, "open_pr", lambda remote, checks: (pr.append(checks), (True, ""))[1])
    assert release.main([]) == 0
    assert pushed == ["origin"] and not pr


def test_red_checks_open_a_pr_and_never_push(monkeypatch, capsys):
    monkeypatch.setattr(release, "run_cmd", lambda *a, **k: cp("version: 1.0.0\n"))
    monkeypatch.setattr(release, "gate_pytest", lambda py: ("pytest", False, "1 failed"))
    monkeypatch.setattr(release, "gate_skill_lint", lambda py: ("skill_lint", True, "ok"))
    monkeypatch.setattr(release, "gate_schema", lambda: ("schema", True, "ok"))
    monkeypatch.setattr(release, "gate_plan", lambda py: ("plan", True, "ok"))
    pushed, pr = [], []
    monkeypatch.setattr(release, "push_to_main", lambda remote: (pushed.append(remote), (True, ""))[1])
    monkeypatch.setattr(release, "open_pr", lambda remote, checks: (pr.append(checks), (True, ""))[1])
    assert release.main([]) == 1
    assert not pushed and len(pr) == 1
    assert [n for n, ok, _d in pr[0] if not ok] == ["pytest"]


def test_dry_run_neither_pushes_nor_opens_a_pr(monkeypatch):
    monkeypatch.setattr(release, "run_cmd", lambda *a, **k: cp("version: 1.0.0\n"))
    for name in ("gate_pytest", "gate_skill_lint"):
        monkeypatch.setattr(release, name, lambda py: ("x", True, "ok"))
    monkeypatch.setattr(release, "gate_schema", lambda: ("schema", True, "ok"))
    monkeypatch.setattr(release, "gate_plan", lambda py: ("plan", True, "ok"))
    monkeypatch.setattr(release, "push_to_main", lambda remote: pytest.fail("pushed"))
    monkeypatch.setattr(release, "open_pr", lambda remote, checks: pytest.fail("pr"))
    assert release.main(["--dry-run"]) == 0
