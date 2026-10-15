"""gate_lib: the cron wake-gate helpers."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import gate_lib  # noqa: E402


@pytest.fixture(autouse=True)
def temp_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.delenv("GATE_STATE_DIR", raising=False)
    return tmp_path


def run_cli(*args, stdin=""):
    return subprocess.run([sys.executable, str(SCRIPTS / "gate_lib.py"), *args], input=stdin, capture_output=True, text=True)


def test_gate_line_is_one_json_line(capsys):
    gate_lib.emit(False, {"ignored": 1})
    gate_lib.emit(True, {"a": 1})
    no, yes = capsys.readouterr().out.splitlines()
    assert json.loads(no) == {"wakeAgent": False}
    assert json.loads(yes) == {"wakeAgent": True, "context": {"a": 1}}


def test_parse_gate_mirrors_hermes_rule():
    assert gate_lib.parse_gate('{"wakeAgent": false}\n') is False
    assert gate_lib.parse_gate('noise\n{"wakeAgent": false}\n\n') is False
    assert gate_lib.parse_gate('{"wakeAgent": false}\nnoise') is True  # only the last line counts
    assert gate_lib.parse_gate("") is True
    assert gate_lib.parse_gate('{"wakeAgent": true}') is True
    assert gate_lib.parse_gate('{"other": 1}') is True


def test_changed_tracks_fingerprint(temp_home):
    fp = gate_lib.fingerprint({"b": 1, "a": [2]})
    assert fp == gate_lib.fingerprint({"a": [2], "b": 1})
    assert gate_lib.changed("g", fp) is True
    assert gate_lib.changed("g", fp) is False
    assert gate_lib.changed("g", "other", save=False) is True
    assert gate_lib.changed("g", "other", save=False) is True  # not stored
    assert (temp_home / "local" / "state" / "gate_g.json").is_file()


def test_state_dir_is_not_created_by_reads(temp_home):
    assert gate_lib.load_state("watch") == {}
    assert not (temp_home / "local").exists()


def test_guarded_wakes_with_the_error(capsys):
    def boom():
        raise ValueError("nope")

    assert gate_lib.guarded("g", boom) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["wakeAgent"] is True and out["context"]["gate_error"] == "ValueError: nope"


def test_cli_help_and_changed():
    assert "usage" in run_cli("--help").stdout
    first = json.loads(run_cli("changed", "g", stdin='{"x": 1}').stdout)
    assert first["wakeAgent"] is True
    assert json.loads(run_cli("changed", "g", stdin='{"x": 1}').stdout) == {"wakeAgent": False}
    assert json.loads(run_cli("changed", "g", stdin="[]").stdout) == {"wakeAgent": False}
    assert json.loads(run_cli("emit", "--no-wake").stdout) == {"wakeAgent": False}
    bad = json.loads(run_cli("changed", "g", stdin="not json").stdout)
    assert bad["wakeAgent"] is True and "gate_error" in bad["context"]
