"""test_changed.py: a change runs the tests that can catch it, and the whole suite when it cannot be scoped.

The selection is checked against this repo's real files and tests: if a rule stops tying a script to the test that
loads it, or a shared harness file stops forcing the whole suite, these fail.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("test_changed_tool", REPO / "scripts" / "test_changed.py")
tc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tc)


@pytest.fixture(scope="module")
def repo():
    return tc.Repo()


def picks(repo, *paths):
    sel = tc.select(list(paths), repo)
    assert not sel["full"], sel["reason"]
    return set(sel["tests"])


@pytest.mark.parametrize("path", ["tests/conftest.py", "tests/_real.py", "tests/fakes/hermes.py", "scripts/squadctl.py",
                                  "squads/_schema/squad.schema.json", "squads/_base/hermes-base.md", "scripts/hpy"])
def test_shared_files_run_the_whole_suite(repo, path):
    sel = tc.select([path], repo)
    assert sel["full"] and path in sel["reason"]


# built at run time: written out literally, this file would itself be "a test that names it"
UNSEEN = "zzz_" + "never_named_tool.py"


def test_a_file_no_test_reaches_runs_the_whole_suite(repo):
    sel = tc.select([f"scripts/{UNSEEN}"], repo)
    assert sel["full"] and "no test is tied" in sel["reason"]


def test_a_new_squad_file_no_test_names_still_runs_that_squads_tests(repo):
    got = picks(repo, f"squads/web/skills/brand-new/scripts/{UNSEEN}")
    assert {"test_web_security.py", "test_help_no_yaml.py"} <= got


@pytest.mark.parametrize("script,test", [
    ("scripts/release.py", "test_release.py"),
    ("scripts/kanban_chain.py", "test_kanban_chain.py"),
    ("scripts/board_watch.py", "test_board_watch.py"),
    ("squads/web/skills/site-contract/scripts/check_site.py", "test_check_site.py"),
    ("squads/_plugins/squad-hub/desktop/plugin.js", "test_squad_hub_model.py"),
    ("squads/jobs/skills/jobs-contract/scripts/jobs_common.py", "test_jobs_common.py"),
])
def test_a_script_selects_the_test_that_loads_it(repo, script, test):
    assert test in picks(repo, script)


def test_a_module_selects_the_tests_of_every_script_that_imports_it(repo):
    # tracker.py is imported by build_dashboard.py and followup_gate.py; test_jobs_gates runs followup_gate.py
    assert "test_jobs_gates.py" in picks(repo, "squads/jobs/skills/jobs-contract/scripts/tracker.py")


def test_a_script_squadctl_runs_selects_the_squadctl_tests(repo):
    got = picks(repo, "scripts/project_sync.py")
    assert {"test_project_sync.py", "test_squadctl.py", "test_messaging.py", "test_update_path.py"} <= got


def test_a_squad_file_selects_that_squad_and_not_the_others(repo):
    got = picks(repo, "squads/web/skills/leading-web/SKILL.md")
    assert {"test_web_security.py", "test_web_base.py", "test_skill_ownership.py"} <= got
    assert not {t for t in got if t.startswith("test_jobs_")}


def test_a_test_file_selects_itself_and_the_modules_that_import_it(repo):
    got = picks(repo, "tests/test_jobs_profile.py")
    assert {"test_jobs_profile.py", "test_jobs_consent.py", "test_jobs_submit_gate.py"} <= got


def test_every_change_adds_the_repo_wide_checks(repo):
    assert tc.REPO_WIDE <= picks(repo, "scripts/board_watch.py")
    assert tc.REPO_WIDE <= picks(repo, "skills/designing-squads/SKILL.md")


def test_only_ignored_paths_run_nothing(repo):
    sel = tc.select(["LICENSE", ".github/workflows/ci.yml"], repo)
    assert not sel["full"] and sel["tests"] == []


def test_every_tracked_file_gets_a_selection(repo):
    """No tracked file ever yields an empty scoped selection: it is either tied to a test or runs the suite."""
    for path in repo.files:
        sel = tc.select([path], repo)
        if path in tc.IGNORED_FILES or path.startswith(tc.IGNORED_DIRS):
            continue
        assert sel["full"] or sel["tests"], path


def test_a_scoped_change_runs_far_fewer_tests_than_the_suite(repo):
    assert len(picks(repo, "scripts/release.py")) < len(repo.tests) / 4


# --- the change set and the pytest command -----------------------------------------------------------------------

def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def test_changed_paths_cover_committed_unstaged_and_untracked(tmp_path, monkeypatch):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    for name in ("a.txt", "b.txt", "c.txt"):
        (tmp_path / name).write_text("1\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-qm", "base")
    base = git(tmp_path, "rev-parse", "HEAD").strip()
    (tmp_path / "a.txt").write_text("2\n")
    git(tmp_path, "commit", "-qam", "committed")
    (tmp_path / "b.txt").write_text("2\n")             # unstaged
    (tmp_path / "new.txt").write_text("x\n")           # untracked
    monkeypatch.setattr(tc, "SRC", tmp_path)
    assert tc.changed_paths(base) == ["a.txt", "b.txt", "new.txt"]
    assert tc.changed_paths("no-such-ref") is None


def test_no_base_runs_the_whole_suite(monkeypatch):
    monkeypatch.setattr(tc, "changed_paths", lambda base, remote="origin": None)
    sel = tc.plan("nowhere", "origin", full=False)
    assert sel["full"] and "no merge-base" in sel["reason"]


def test_pytest_argv_is_parallel_with_xdist_and_lists_files_when_scoped():
    sel = {"full": False, "tests": ["test_release.py"]}
    argv = tc.pytest_argv("py", sel, parallel=True)
    assert argv[:3] == ["py", "-m", "pytest"] and argv[-3:] == ["-n", "auto", "tests/test_release.py"]
    assert "-n" not in tc.pytest_argv("py", sel, parallel=False)
    assert not [a for a in tc.pytest_argv("py", {"full": True, "tests": []}, parallel=True) if a.startswith("tests/")]


def test_list_prints_the_selection_and_runs_nothing(monkeypatch, capsys):
    monkeypatch.setattr(tc, "plan", lambda base, remote, full: {"full": False, "reason": "1 changed path(s)",
                                                                 "tests": ["test_release.py"], "why": {}})
    monkeypatch.setattr(tc.subprocess, "run", lambda *a, **k: pytest.fail("ran pytest"))
    assert tc.main(["--list"]) == 0
    assert json.loads(capsys.readouterr().out)["tests"] == ["test_release.py"]


def test_help_runs():
    p = subprocess.run([sys.executable, str(REPO / "scripts" / "test_changed.py"), "--help"], capture_output=True,
                       text=True)
    assert p.returncode == 0 and "--full" in p.stdout
