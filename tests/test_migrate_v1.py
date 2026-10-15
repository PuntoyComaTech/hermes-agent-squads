"""migrate_v1: a synthetic v1 tree (legacy profiles, deliver crons, ~/Hermes/projects) against the fake `hermes`.

Nothing touches the real ~/.hermes: PATH points at tests/fakes/hermes.py, the v1 project root is a tmp dir and every
project registration runs through scripts/squadctl with SQUADCTL_PYTHON pointing at this test interpreter.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"
FAKES = REPO / "tests" / "fakes"
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))
import migrate_v1  # noqa: E402

JOBS_BOTS = ["jobs", "jobs-scout", "jobs-writer", "jobs-reviewer"]
WEB_BOTS = ["web", "web-frontend", "web-backend", "web-qa", "web-deployer"]


def tree_hash(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        h.update(str(p.relative_to(path)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


class Env:
    def __init__(self, tmp: Path, monkeypatch):
        self.tmp = tmp
        self.root = tmp / "hermes"
        self.src = tmp / "src"
        self.hsrc = tmp / "hsrc"
        self.local = tmp / "local"
        self.legacy = tmp / "legacy" / "projects"
        self.log = tmp / "calls.jsonl"
        (self.root / "profiles").mkdir(parents=True)
        self.legacy.mkdir(parents=True)
        (self.legacy.parent / "outbox").mkdir()
        shutil.copytree(FAKES / "root", self.hsrc)
        bindir = tmp / "bin"
        bindir.mkdir()
        wrapper = bindir / "hermes"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKES / "hermes.py"}" "$@"\n')
        wrapper.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("HERMES_HOME", str(self.root))
        monkeypatch.setenv("FAKE_HERMES_LOG", str(self.log))
        monkeypatch.setenv("FAKE_HERMES_SRC", str(self.hsrc))
        monkeypatch.setenv("SQUADCTL_PYTHON", sys.executable)
        (self.src / "squads" / "_schema").mkdir(parents=True)
        shutil.copy(REPO / "squads" / "_schema" / "squad.schema.json", self.src / "squads" / "_schema")
        for key in ("jobs", "web"):
            dest = self.src / "squads" / key
            dest.mkdir(parents=True)
            shutil.copy(FIX / "squads" / f"{key}.yaml", dest / "squad.yaml")

    # fixtures ----------------------------------------------------------------------------------------------

    def profile(self, name: str, jobs: list[dict] | None = None) -> Path:
        home = self.root / "profiles" / name
        (home / "cron").mkdir(parents=True, exist_ok=True)
        (home / "config.yaml").write_text("model: {default: seed}\n")
        if jobs is not None:
            (home / "cron" / "jobs.json").write_text(json.dumps({"jobs": jobs}))
        return home

    def deliver_job(self, name: str = "deliver") -> dict:
        return {"id": f"id-{name}", "name": name, "script": "deliver.py", "no_agent": False,
                "schedule": {"kind": "interval", "display": "every 15m"}}

    def v1_tree(self) -> None:
        self.profile("orchestrator", [self.deliver_job("deliver"), {"id": "keep", "name": "keep-me", "script": "x.py"}])
        for name in JOBS_BOTS + WEB_BOTS + ["web-architect", "web-developer"]:
            self.profile(name, [self.deliver_job("deliver")] if name.endswith(("scout", "architect")) else [])
        for key in ("jobs", "web", "misc"):
            folder = self.legacy / key
            folder.mkdir()
            (folder / "README.md").write_text(f"{key} v1 folder\n")

    # runs --------------------------------------------------------------------------------------------------

    def run(self, *args, expect: int | None = 0, capsys):
        argv = [*args, "--json", "--hermes-root", str(self.root), "--v1-projects", str(self.legacy),
                "--local", str(self.local), "--src", str(self.src), "--squadctl", str(SCRIPTS / "squadctl")]
        code = migrate_v1.main(argv)
        out = capsys.readouterr()
        if expect is not None:
            assert code == expect, (out.out, out.err)
        text = out.out.strip() or out.err.strip()
        try:
            return json.loads(text)
        except ValueError:
            return {"raw": text}

    def calls(self) -> list[dict]:
        return [json.loads(ln) for ln in self.log.read_text().splitlines()] if self.log.is_file() else []

    def jobs(self, bot: str) -> list[dict]:
        path = self.root / "profiles" / bot / "cron" / "jobs.json"
        raw = json.loads(path.read_text()) if path.is_file() else []
        return raw.get("jobs", []) if isinstance(raw, dict) else raw


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


# --- detection ---------------------------------------------------------------------------------------------------

def test_empty_root_is_not_a_v1_install(env, capsys):
    out = env.run(capsys=capsys)
    assert out["v1"] is False and out["actions"] == []
    assert any("no v1 install found" in n for n in out["notes"])


def test_detects_profiles_deliver_crons_and_project_folders(env, capsys):
    env.v1_tree()
    out = env.run("--dry-run", capsys=capsys)
    assert out["v1"] is True
    found = out["found"]
    assert "orchestrator" in found["profiles"] and "web-architect" in found["profiles"]
    assert [r["profile"] for r in found["deliver_crons"]] == ["jobs-scout", "orchestrator", "web-architect"]
    assert found["v1_projects"] == ["jobs", "misc", "web"]
    assert found["outbox"].endswith("outbox")


def test_legacy_profile_names_alone_are_reported_as_v1(env, capsys):
    env.profile("web-architect")  # the v1 web squad's own bot names
    out = env.run(capsys=capsys)
    assert out["v1"] is True and out["actions"] == []
    assert any("v1-shaped profiles: web-architect" in n for n in out["notes"])


def test_is_deliver_matches_script_and_name():
    assert migrate_v1.is_deliver({"script": "deliver.py"})
    assert migrate_v1.is_deliver({"script": "scripts/deliver.py"})
    assert migrate_v1.is_deliver({"name": "deliver"})
    assert not migrate_v1.is_deliver({"name": "delivery-status", "script": "web_watch.py"})


def test_read_jobs_accepts_both_store_shapes(env):
    home = env.profile("orchestrator")
    (home / "cron" / "jobs.json").write_text(json.dumps([{"id": "a", "name": "deliver"}]))
    assert [j["id"] for j in migrate_v1.read_jobs(home)] == ["a"]
    (home / "cron" / "jobs.json").write_text("not json")
    assert migrate_v1.read_jobs(home) == []


# --- project folders ---------------------------------------------------------------------------------------------

def test_project_folders_become_native_projects_in_every_bot(env, capsys):
    env.v1_tree()
    out = env.run(capsys=capsys)
    added = {a["squad"]: a for a in out["actions"] if a["action"] == "project add"}
    assert added["jobs"]["result"] == "created" and added["web"]["result"] == "created"
    for bot in JOBS_BOTS:
        assert "jobs" in (env.root / "profiles" / bot / "projects.txt").read_text()
    for bot in WEB_BOTS:
        assert "web" in (env.root / "profiles" / bot / "projects.txt").read_text()
        assert "board=web" in (env.root / "profiles" / bot / "projects.txt").read_text()
    created = [c for c in env.calls() if c["args"][:2] == ["project", "create"]]
    assert {c["profile"] for c in created} == set(JOBS_BOTS) | set(WEB_BOTS)
    installed = (env.local / "installed.yaml").read_text()
    assert "jobs" in installed and "path:" in installed


def test_project_folder_without_a_v2_squad_is_skipped(env, capsys):
    env.v1_tree()
    out = env.run(capsys=capsys)
    misc = next(a for a in out["actions"] if a.get("path", "").endswith("misc"))
    assert misc["result"] == "skipped" and "unknown squad" in misc["reason"]
    assert not (env.root / "profiles" / "orchestrator" / "projects.txt").exists()


def test_project_add_reports_missing_profiles(env, capsys):
    (env.legacy / "jobs").mkdir()
    out = env.run(capsys=capsys)
    add = next(a for a in out["actions"] if a["action"] == "project add")
    assert add["result"] == "profile missing" and add["reason"] == "run `squadctl apply jobs` first"


def test_second_run_is_idempotent(env, capsys):
    env.v1_tree()
    env.run(capsys=capsys)
    out = env.run(capsys=capsys)
    results = {a["squad"]: a["result"] for a in out["actions"] if a["action"] == "project add"}
    assert results == {"jobs": "exists", "misc": "skipped", "web": "exists"}


# --- deliver crons -----------------------------------------------------------------------------------------------

def test_deliver_crons_are_removed_and_others_kept(env, capsys):
    env.v1_tree()
    out = env.run(capsys=capsys)
    removed = [a for a in out["actions"] if a["action"] == "cron remove"]
    assert {a["profile"] for a in removed} == {"orchestrator", "jobs-scout", "web-architect"}
    assert [j["name"] for j in env.jobs("orchestrator")] == ["keep-me"]
    assert env.jobs("jobs") == []
    assert [c["args"][0] for c in env.calls() if c["args"][:2] == ["cron", "remove"]] == ["cron"] * 3
    assert any("bot-chat" in n for n in out["notes"])


# --- orchestrator ------------------------------------------------------------------------------------------------

def test_orchestrator_is_exported_into_local_backups(env, capsys):
    env.v1_tree()
    secret = env.root / "profiles" / "orchestrator" / ".env"
    secret.write_text("TOKEN=super-secret-value\n")
    out = env.run(capsys=capsys)
    (export,) = [a for a in out["actions"] if a["action"] == "profile export"]
    assert export["result"] == "exported" and export["profile"] == "orchestrator"
    backups = sorted((env.local / "backups").glob("orchestrator-*.tar.gz"))
    assert len(backups) == 1
    with tarfile.open(backups[0]) as tf:
        names = tf.getnames()
    assert any(n.endswith("orchestrator/config.yaml") for n in names)
    assert not any(Path(n).name in (".env", "auth.json") for n in names)
    assert (env.root / "profiles" / "orchestrator").is_dir()  # kept unless asked otherwise
    assert any("hermes profile delete orchestrator" in n for n in out["notes"])


def test_delete_orchestrator_removes_it_after_the_export(env, capsys):
    env.v1_tree()
    out = env.run("--delete-orchestrator", capsys=capsys)
    assert [a["result"] for a in out["actions"] if a["action"] == "profile export"] == ["exported"]
    deleted = [a for a in out["actions"] if a["action"] == "profile delete"]
    assert [a["result"] for a in deleted] == ["deleted"]
    assert not (env.root / "profiles" / "orchestrator").exists()
    assert len(list((env.local / "backups").glob("orchestrator-*.tar.gz"))) == 1


def test_a_failed_export_never_deletes_the_orchestrator(env, capsys):
    env.v1_tree()
    out = env.run("--delete-orchestrator", "--hermes-bin", str(env.tmp / "no-hermes"), capsys=capsys)
    assert [a["result"] for a in out["actions"] if a["action"] == "profile export"] == ["failed"]
    assert not [a for a in out["actions"] if a["action"] == "profile delete"]
    assert (env.root / "profiles" / "orchestrator").is_dir()
    assert any("was NOT deleted" in n for n in out["notes"])


# --- dry run, output, cli ----------------------------------------------------------------------------------------

def test_dry_run_writes_nothing_and_calls_nothing(env, capsys):
    env.v1_tree()
    before = tree_hash(env.root)
    out = env.run("--dry-run", capsys=capsys)
    assert out["dry_run"] is True and out["v1"] is True
    assert {a["result"] for a in out["actions"]} == {"would-add", "would-remove", "would-export"}
    assert tree_hash(env.root) == before
    assert env.calls() == [] and not env.local.exists()


def test_dry_run_with_delete_orchestrator_reports_it(env, capsys):
    env.v1_tree()
    out = env.run("--dry-run", "--delete-orchestrator", capsys=capsys)
    assert {a["result"] for a in out["actions"]} == {"would-add", "would-remove", "would-export", "would-delete"}


def test_output_is_toon_by_default(env, capsys):
    env.v1_tree()
    argv = ["--hermes-root", str(env.root), "--v1-projects", str(env.legacy), "--src", str(env.src)]
    assert migrate_v1.main([*argv, "--dry-run"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "v1: true" and any(ln.startswith("actions[") for ln in lines)


def test_help_works_without_hermes_or_network(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    out = subprocess.run([sys.executable, str(SCRIPTS / "migrate_v1.py"), "--help"], capture_output=True, text=True,
                         env=env, timeout=30)
    assert out.returncode == 0 and "deliver" in out.stdout and "--dry-run" in out.stdout


def test_missing_squadctl_shim_is_reported_and_not_fatal(env, capsys):
    env.v1_tree()
    argv = ["--json", "--hermes-root", str(env.root), "--v1-projects", str(env.legacy), "--src", str(env.src),
            "--squadctl", str(env.tmp / "nope")]
    assert migrate_v1.main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert {a["result"] for a in out["actions"] if a["action"] == "project add"} == {"skipped"}


def test_resolve_root_matches_squadctl(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "r" / "profiles" / "builder"))
    assert migrate_v1.resolve_root(None) == tmp_path / "r"
