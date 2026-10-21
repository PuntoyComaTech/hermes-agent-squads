"""kanban_chain: squad.yaml chains -> dependent, idempotent cards. A fake `hermes` records every call."""
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from _real import needs_hermes

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "kanban_chain.py"
FIXTURE_SQUADS = REPO / "tests" / "fixtures" / "squads"

FAKE_HERMES = '''
import json, os, sys
argv = sys.argv[1:]
db = os.environ["FAKE_KANBAN_DB"]
state = json.load(open(db)) if os.path.exists(db) else {{"tasks": [], "calls": []}}
state["calls"].append({{"argv": argv, "hermes_home": os.environ.get("HERMES_HOME")}})
json.dump(state, open(db, "w"))
cmd = argv[2:] if argv[:1] == ["-p"] else argv
if cmd[:2] == ["project", "show"]:
    print("Project: demo")
    print("   primary: " + os.environ["FAKE_PROJECT_PRIMARY"])
    print("   * " + os.environ["FAKE_PROJECT_PRIMARY"])
    raise SystemExit(0)
flags = {{}}
i = argv.index("create") + 1
title = argv[i]
rest = argv[i + 1:]
for j in range(0, len(rest), 2):
    if rest[j] == "--json":
        break
    flags[rest[j]] = rest[j + 1]
    if rest[j + 1] == "--json":
        break
task = next((t for t in state["tasks"] if t["key"] == flags["--idempotency-key"]), None)
if task is None:
    task = {{"id": "t_%02d" % (len(state["tasks"]) + 1), "key": flags["--idempotency-key"], "title": title,
             "flags": flags}}
    state["tasks"].append(task)
json.dump(state, open(db, "w"))
print(json.dumps({{"id": task["id"]}}))
'''


def write_fake(path: Path, body: str) -> None:
    """A fake `hermes`: the Python body next to it plus a sh launcher. A `#!<python>` shebang breaks when the
    interpreter path holds a space (a checkout folder with a space in its name); the launcher quotes it."""
    path.with_suffix(".py").write_text(body)
    path.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(path.with_suffix('.py')))} \"$@\"\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


@pytest.fixture
def env(tmp_path, monkeypatch):
    home = tmp_path / "root" / "profiles" / "builder"
    (home / "local").mkdir(parents=True)
    squads = tmp_path / "squads"
    for src in FIXTURE_SQUADS.glob("*.yaml"):
        (squads / src.stem).mkdir(parents=True)
        shutil.copy(src, squads / src.stem / "squad.yaml")
    fake = tmp_path / "hermes"
    write_fake(fake, FAKE_HERMES.format())
    db = tmp_path / "kanban.json"
    monkeypatch.setenv("FAKE_KANBAN_DB", str(db))
    monkeypatch.setenv("FAKE_PROJECT_PRIMARY", str(tmp_path / "project"))
    monkeypatch.setenv("HERMES_HOME", str(home))
    return {"home": home, "squads": squads, "fake": fake, "db": db, "tmp": tmp_path}


def run(env, squad, chain, *extra, title="Landing page", project="demo"):
    args = [sys.executable, str(SCRIPT), squad, chain, "--project", project, "--title", title, "--squads-dir", str(env["squads"]),
            "--home", str(env["home"]), "--hermes-bin", str(env["fake"]), *extra]
    return subprocess.run(args, capture_output=True, text=True)


def db(env):
    return json.loads(env["db"].read_text()) if env["db"].exists() else {"tasks": [], "calls": []}


def test_dry_run_creates_nothing_and_skips_when_stages(env):
    proc = run(env, "web", "milestone", "--dry-run", "--json")
    out = json.loads(proc.stdout)
    assert proc.returncode == 0 and out["dry_run"] is True
    assert [c["stage"] for c in out["cards"]] == ["ui", "preview", "qa", "accept"]  # `api` needs --when backend
    assert out["skipped"] == [{"stage": "api", "when": "backend"}]
    assert not env["db"].exists()
    with_backend = json.loads(run(env, "web", "milestone", "--dry-run", "--json", "--when", "backend").stdout)
    assert [c["stage"] for c in with_backend["cards"]][:2] == ["api", "ui"] or True
    assert [c["stage"] for c in with_backend["cards"]] == ["api", "ui", "preview", "qa", "accept"]


def test_cards_are_chained_with_skill_key_project_and_manager(env):
    proc = run(env, "web", "milestone", "--when", "backend", "--json")
    assert proc.returncode == 0, proc.stdout
    tasks = db(env)["tasks"]
    assert [t["id"] for t in tasks] == ["t_01", "t_02", "t_03", "t_04", "t_05"]
    first, second, last = tasks[0], tasks[1], tasks[4]
    assert "--parent" not in first["flags"] and second["flags"]["--parent"] == "t_01" and last["flags"]["--parent"] == "t_04"
    assert first["flags"]["--skill"] == "building-backend" and first["flags"]["--assignee"] == "web-backend"
    assert first["flags"]["--project"] == "demo" and first["flags"]["--created-by"] == "web"
    assert first["key"] == "web:milestone:demo:landing-page:api"
    creates = [c for c in db(env)["calls"] if "create" in c["argv"]]
    argv = creates[0]["argv"]
    assert argv[:5] == ["-p", "web", "kanban", "--board", "web"]
    assert creates[0]["hermes_home"] == str(env["home"].parent.parent)  # root, not the builder profile
    out = json.loads(proc.stdout)
    assert [c["id"] for c in out["cards"]] == ["t_01", "t_02", "t_03", "t_04", "t_05"]


def test_rerun_is_idempotent(env):
    first = json.loads(run(env, "web", "milestone", "--json", "--when", "backend").stdout)
    second = json.loads(run(env, "web", "milestone", "--json", "--when", "backend").stdout)
    assert [c["id"] for c in first["cards"]] == [c["id"] for c in second["cards"]]
    creates = lambda: [c for c in db(env)["calls"] if "create" in c["argv"]]  # noqa: E731
    assert len(db(env)["tasks"]) == 5 and len(creates()) == 10
    third = json.loads(run(env, "web", "milestone", "--json", "--when", "backend", "--run-id", "second").stdout)
    assert len(db(env)["tasks"]) == 10 and third["cards"][0]["id"] == "t_06"


def test_lane_pins_the_model_from_installed_yaml(env):
    (env["home"] / "local" / "installed.yaml").write_text(yaml.safe_dump(
        {"bots": {"jobs-reviewer": {"provider": "opencode-go", "model": "mimo-v2.6-pro", "reasoning": "xhigh"}}}))
    out = json.loads(run(env, "jobs", "application", "--json").stdout)
    assert out["warnings"] == []
    flags = db(env)["tasks"][0]["flags"]
    assert flags["--model"] == "mimo-v2.6-pro" and flags["--provider"] == "opencode-go"
    assert all("--model" not in t["flags"] for t in db(env)["tasks"][1:])  # only the analyze stage names a lane


def test_lane_without_a_recorded_model_warns_and_omits_flags(env):
    out = json.loads(run(env, "jobs", "application", "--json").stdout)
    assert "lane 'review'" in out["warnings"][0]
    assert "--model" not in db(env)["tasks"][0]["flags"]


def test_workspace_defaults_to_the_project_primary_folder(env):
    """A project card must not fall into the CLI's git-worktree default; kanban_chain pins dir:<primary>."""
    out = json.loads(run(env, "jobs", "application", "--json").stdout)
    primary = env["tmp"] / "project"
    assert all(t["flags"]["--workspace"] == f"dir:{primary}" for t in db(env)["tasks"])
    assert not any("primary path unknown" in w for w in out["warnings"])


def test_explicit_workspace_overrides_the_default(env):
    run(env, "jobs", "application", "--json", "--workspace", "dir:/somewhere/else")
    assert all(t["flags"]["--workspace"] == "dir:/somewhere/else" for t in db(env)["tasks"])


def test_unresolvable_primary_warns_and_files_without_workspace(env):
    stub = env["tmp"] / "hermes-show-fails"
    write_fake(stub, "import json, os, sys\n"
                    "argv = sys.argv[1:]\n"
                    "if argv[:2] == ['project', 'show']:\n"
                    "    raise SystemExit(1)\n"
                    "print(json.dumps({'id': 't_01'}))\n")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    proc = subprocess.run([sys.executable, str(SCRIPT), "jobs", "application", "--project", "demo", "--title", "T",
                           "--json", "--squads-dir", str(env["squads"]), "--home", str(env["home"]),
                           "--hermes-bin", str(stub)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout
    out = json.loads(proc.stdout)
    assert any("primary path unknown" in w for w in out["warnings"])


def test_local_override_adds_a_chain(env):
    local = env["home"] / "local" / "squads" / "web"
    local.mkdir(parents=True)
    local.joinpath("squad.yaml").write_text(yaml.safe_dump(
        {"chains": {"hotfix": [{"stage": "fix", "assignee": "web-frontend", "skill": "building-frontend"}]}}))
    out = json.loads(run(env, "web", "hotfix", "--json", "--dry-run").stdout)
    assert [c["stage"] for c in out["cards"]] == ["fix"]
    assert run(env, "web", "milestone", "--dry-run").returncode == 0  # repo chains survive the merge


def test_errors_are_structured(env):
    bad_chain = run(env, "web", "nope", "--json")
    assert bad_chain.returncode == 2 and "nope" in json.loads(bad_chain.stdout)["error"]
    assert run(env, "ghost", "x", "--json").returncode == 2
    env["fake"].write_text("#!/bin/sh\necho boom >&2\nexit 1\n")
    failed = run(env, "web", "milestone", "--json")
    assert failed.returncode == 2 and "stage ui failed: boom" in json.loads(failed.stdout)["error"]


def test_help_works():
    proc = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert proc.returncode == 0 and "--dry-run" in proc.stdout


@needs_hermes
def test_real_hermes_chain_is_idempotent_on_a_temp_board(env, monkeypatch):
    from _real import env_for, scrub, temp_root
    root = temp_root(env["tmp"])
    scrub(monkeypatch, root)
    hermes = lambda *a: subprocess.run(["hermes", *a], capture_output=True, text=True, check=True, env=env_for(root))  # noqa: E731
    hermes("profile", "create", "web", "--no-skills", "--no-alias")
    hermes("kanban", "boards", "create", "web", "--name", "Web")
    site = env["tmp"] / "site"
    site.mkdir()
    hermes("-p", "web", "project", "create", "Demo", str(site), "--slug", "demo", "--board", "web")
    args = ["web", "milestone", "--when", "backend", "--json", "--hermes-bin", "hermes", "--hermes-root", str(root)]
    ids = []
    for _ in range(2):
        proc = subprocess.run([sys.executable, str(SCRIPT), *args[:2], "--project", "demo", "--title", "T", *args[2:],
                               "--squads-dir", str(env["squads"]), "--home", str(root / "profiles" / "builder")],
                              capture_output=True, text=True, env=env_for(root))
        assert proc.returncode == 0, proc.stdout
        ids.append([c["id"] for c in json.loads(proc.stdout)["cards"]])
    assert ids[0] == ids[1] and len(set(ids[0])) == 5
    board = json.loads(hermes("kanban", "--board", "web", "list", "--json").stdout)
    assert len(board) == 5
