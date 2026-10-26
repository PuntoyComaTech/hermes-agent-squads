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


def git(main="version: 1.0.0\n", status="", ls_remote=0):
    """Fake run_cmd for the git calls of main(): remote main with `main` as distribution.yaml."""
    def run(argv, env=None, **kw):
        if argv[:2] == ["git", "status"]:
            return cp(status)
        if argv[:2] == ["git", "ls-remote"]:
            return cp("", code=ls_remote, stderr="fatal: unreachable" if ls_remote not in (0, 2) else "")
        return cp(main)
    return run


def green(monkeypatch):
    monkeypatch.setattr(release, "gate_pytest", lambda py, selection=None: ("pytest", True, "338 passed"))
    monkeypatch.setattr(release, "test_selection", lambda remote, full: {"full": True, "reason": "--full", "tests": []})
    monkeypatch.setattr(release, "gate_skill_lint", lambda py: ("skill_lint", True, "ok"))
    monkeypatch.setattr(release, "gate_schema", lambda py=None: ("schema", True, "ok"))
    monkeypatch.setattr(release, "gate_plan", lambda py: ("plan", True, "ok"))


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


def test_schema_gate_accepts_optional_bots_beyond_five():
    """C-11: `web-frontend-pro` is a 6th bot with `optional: true`. The 5-bot cap counts required bots and
    is enforced by squadctl and skill_lint (`manager-naming`), not by the schema, which cannot count
    optional members."""
    import copy

    import yaml
    from jsonschema import Draft202012Validator

    doc = yaml.safe_load((REPO / "squads" / "web" / "squad.yaml").read_text())
    assert len(doc["bots"]) > 5
    assert doc["bots"]["web-frontend-pro"]["optional"] is True
    validator = Draft202012Validator(
        json.loads((REPO / "squads" / "_schema" / "squad.schema.json").read_text()))
    assert not [e for e in validator.iter_errors(doc)]
    without_flag = copy.deepcopy(doc)
    without_flag["bots"]["web-extra"] = copy.deepcopy(without_flag["bots"]["web-frontend-pro"])
    assert not [e for e in validator.iter_errors(without_flag)], "the count is cross-field, not schema"


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
    assert len(seen) == 4  # --self + web, marketing, jobs


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
    monkeypatch.setattr(release, "run_cmd", git())
    green(monkeypatch)
    pushed, pr = [], []
    monkeypatch.setattr(release, "push_to_main", lambda remote: (pushed.append(remote), (True, ""))[1])
    monkeypatch.setattr(release, "open_pr", lambda remote, checks: (pr.append(checks), (True, ""))[1])
    assert release.main([]) == 0
    assert pushed == ["origin"] and not pr


def test_red_checks_open_a_pr_and_never_push(monkeypatch, capsys):
    monkeypatch.setattr(release, "run_cmd", git())
    green(monkeypatch)
    monkeypatch.setattr(release, "gate_pytest", lambda py, selection=None: ("pytest", False, "1 failed"))
    pushed, pr = [], []
    monkeypatch.setattr(release, "push_to_main", lambda remote: (pushed.append(remote), (True, ""))[1])
    monkeypatch.setattr(release, "open_pr", lambda remote, checks: (pr.append(checks), (True, ""))[1])
    assert release.main([]) == 1
    assert not pushed and len(pr) == 1
    assert [n for n, ok, _d in pr[0] if not ok] == ["pytest"]


def test_dry_run_neither_pushes_nor_opens_a_pr(monkeypatch):
    monkeypatch.setattr(release, "run_cmd", git())
    green(monkeypatch)
    monkeypatch.setattr(release, "push_to_main", lambda remote: pytest.fail("pushed"))
    monkeypatch.setattr(release, "open_pr", lambda remote, checks: pytest.fail("pr"))
    assert release.main(["--dry-run"]) == 0


def no_release(monkeypatch):
    monkeypatch.setattr(release, "push_to_main", lambda remote: pytest.fail("pushed"))
    monkeypatch.setattr(release, "open_pr", lambda remote, checks: pytest.fail("pr"))


def test_only_skips_gates_and_never_pushes(monkeypatch, capsys):
    """A partial run must not release: the skipped gates were never checked."""
    monkeypatch.setattr(release, "run_cmd", git())
    green(monkeypatch)
    no_release(monkeypatch)
    assert release.main(["--only", "pytest"]) == 0
    assert "nothing pushed" in capsys.readouterr().out


def test_dirty_tree_is_red(monkeypatch, capsys):
    monkeypatch.setattr(release, "run_cmd", git(status=" M scripts/squadctl.py\n"))
    green(monkeypatch)
    pr = []
    monkeypatch.setattr(release, "push_to_main", lambda remote: pytest.fail("pushed"))
    monkeypatch.setattr(release, "open_pr", lambda remote, checks: (pr.append(checks), (True, ""))[1])
    assert release.main([]) == 1
    assert [n for n, ok, _d in pr[0] if not ok] == ["clean"]


def test_unreachable_remote_is_red_never_a_first_release(monkeypatch, capsys):
    monkeypatch.setattr(release, "run_cmd", git(ls_remote=128))
    green(monkeypatch)
    no_release(monkeypatch)
    assert release.main(["--dry-run"]) == 1
    assert "RED   bump: cannot read origin/main" in capsys.readouterr().out


def test_no_main_on_the_remote_is_a_first_release(monkeypatch, capsys):
    monkeypatch.setattr(release, "run_cmd", git(ls_remote=2))
    green(monkeypatch)
    no_release(monkeypatch)
    assert release.main(["--dry-run"]) == 0
    assert "first release" in capsys.readouterr().out


def test_schema_gate_runs_under_the_given_interpreter():
    import sys
    name, ok, detail = release.gate_schema(sys.executable)
    assert name == "schema" and ok, detail
    name, ok, detail = release.gate_schema("/nonexistent/python")
    assert not ok


def test_pytest_gate_names_the_venv_when_pytest_is_missing(monkeypatch):
    monkeypatch.setattr(release, "run_cmd", lambda argv, **k: cp("", code=1, stderr="No module named pytest"))
    name, ok, detail = release.gate_pytest("/hermes/runtime/python")
    assert name == "pytest" and not ok and "--python .venv/bin/python" in detail


def test_a_red_pytest_gate_names_the_failing_tests(monkeypatch):
    out = (".....F..\n=========================== short test summary info ============================\n"
           "FAILED tests/test_a.py::test_one - AssertionError: boom\n"
           "FAILED tests/test_b.py::test_two[x] - KeyError: 'k'\n"
           "2 failed, 2110 passed in 900.00s\n")
    calls = []

    def fake(argv, **k):
        calls.append(argv)
        return cp(out, code=1) if "pytest" in argv and "-c" not in argv else cp("")

    monkeypatch.setattr(release, "run_cmd", fake)
    name, ok, detail = release.gate_pytest("/venv/python")
    assert not ok and "-rf" in calls[-1]
    assert detail.startswith("2 failed, 2110 passed in 900.00s: tests/test_a.py::test_one, tests/test_b.py::test_two[x]")


def pytest_calls(monkeypatch, xdist=True):
    calls = []

    def fake(argv, **k):
        calls.append(argv)
        if argv[-1] == "import xdist":
            return cp("", code=0 if xdist else 1)
        return cp("3 passed in 1.00s\n")

    monkeypatch.setattr(release, "run_cmd", fake)
    return calls


def test_pytest_gate_runs_only_the_selected_files_in_parallel(monkeypatch):
    calls = pytest_calls(monkeypatch)
    sel = {"full": False, "reason": "2 changed path(s)", "tests": ["test_release.py", "test_docs.py"]}
    name, ok, detail = release.gate_pytest("/venv/python", sel)
    run = calls[-1]
    assert ok and run[-4:] == ["-n", "auto", "tests/test_release.py", "tests/test_docs.py"]
    assert "2 test files: 2 changed path(s)" in detail


def test_pytest_gate_full_selection_names_no_file_and_runs_serially_without_xdist(monkeypatch):
    calls = pytest_calls(monkeypatch, xdist=False)
    name, ok, detail = release.gate_pytest("/venv/python", {"full": True, "reason": "--full", "tests": []})
    run = calls[-1]
    assert ok and "-n" not in run and not [a for a in run if a.startswith("tests/")]
    assert "whole suite" in detail and "pip install pytest-xdist" in detail


def test_pytest_gate_with_nothing_selected_runs_no_pytest(monkeypatch):
    calls = pytest_calls(monkeypatch)
    name, ok, detail = release.gate_pytest("/venv/python", {"full": False, "reason": "no change", "tests": []})
    assert ok and "no test to run" in detail
    assert not [c for c in calls if "pytest" in c and "-c" not in c]


def test_full_flag_reaches_the_test_selection(monkeypatch):
    monkeypatch.setattr(release, "run_cmd", git())
    green(monkeypatch)
    no_release(monkeypatch)
    seen = []
    monkeypatch.setattr(release, "test_selection", lambda remote, full: (seen.append(full), {"full": full,
                        "reason": "x", "tests": ["test_docs.py"]})[1])
    release.main(["--only", "pytest"])
    release.main(["--only", "pytest", "--full"])
    assert seen == [False, True]


def test_open_pr_pushes_a_branch_then_uses_real_gh_flags(monkeypatch):
    calls = []
    monkeypatch.setattr(release, "run_cmd", lambda cmd, **kw: (calls.append(cmd), subprocess.CompletedProcess(cmd, 0, "url", ""))[1])
    ok, _ = release.open_pr("origin", [("bump", False, "not a bump")])
    assert ok
    push, pr = calls
    assert push[:3] == ["git", "push", "--force"] and push[-1].startswith("HEAD:refs/heads/release/")
    assert pr[:3] == ["gh", "pr", "create"] and "--push" not in pr
    assert pr[pr.index("--head") + 1] == push[-1].removeprefix("HEAD:refs/heads/")


def test_run_cmd_drops_the_hermes_runtime_pythonpath(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/hermes/site-packages")
    monkeypatch.setenv("PYTHONHOME", "/hermes")
    p = release.run_cmd(["python3", "-c", "import os; print(os.environ.get('PYTHONPATH'), os.environ.get('PYTHONHOME'))"])
    assert p.stdout.strip() == "None None"
