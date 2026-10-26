"""squadctl: plan, apply, status, doctor, uninstall, project add, chain, against a fake `hermes` and a temp HERMES_HOME.

Nothing here touches the real ~/.hermes: PATH points at tests/fakes/hermes.py and every path lives under tmp_path.
Tests that need the real `hermes` binary are skipped only when it is not on PATH.
"""
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"
FAKES = REPO / "tests" / "fakes"
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))
import squadctl  # noqa: E402

from _real import needs_hermes as real_hermes  # noqa: E402  (skipped only when hermes is not on PATH)
# Every lane model-roles.yaml defines (aliases included), so a fixture that moves to a new lane still resolves.
LANES = sorted(yaml.safe_load((SCRIPTS / "data" / "model-roles.yaml").read_text())["lanes"])
FAKE_IDENTITY = "You are Hermes Agent (fake runtime identity). Be direct."  # tests/fakes/root/agent/prompt_builder.py
WEB_BOTS = ["web", "web-frontend", "web-backend", "web-qa", "web-deployer"]
ALWAYS = yaml.safe_load((SCRIPTS / "data" / "always-disabled.yaml").read_text())["always_disabled"]
WRITES = {("profile", "create"), ("profile", "delete"), ("profile", "describe"), ("profile", "export"),
          ("skills", "install"), ("skills", "opt-out"), ("cron", "create"), ("cron", "edit"), ("cron", "remove"),
          ("plugins", "enable"), ("plugins", "disable"), ("plugins", "install"), ("mcp", "add"),
          ("project", "create"), ("tools", "enable")}


@pytest.fixture(autouse=True)
def stub_cli_probes(monkeypatch):
    """`doctor` probes `requires.apps` with real subprocesses (`npx --version`, `gh auth status`,
    `cf auth whoami`): every test gets a stubbed runner, so no run depends on this machine's CLIs, its
    network or on somebody being logged in."""
    monkeypatch.setattr(squadctl, "run_quiet",
                        lambda argv, timeout=60: subprocess.CompletedProcess(argv, 0, "1.0.0\n", ""))


def tree_hash(path: Path) -> str:
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        h.update(str(p.relative_to(path)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def models_doc() -> dict:
    return {"lanes": {lane: {"provider": f"prov-{lane}", "model": f"model-{lane}", "reasoning": "medium"}
                      for lane in LANES}}


class Env:
    def __init__(self, tmp: Path, monkeypatch):
        self.tmp = tmp
        self.root = tmp / "hermes"
        self.src = tmp / "src"
        self.hsrc = tmp / "hsrc"
        self.local = self.root / "profiles" / "builder" / "local"
        self.log = tmp / "calls.jsonl"
        self.models = tmp / "models.yaml"
        (self.root / "profiles").mkdir(parents=True)
        shutil.copytree(FAKES / "root", self.hsrc)
        bindir = tmp / "bin"
        bindir.mkdir()
        wrapper = bindir / "hermes"
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKES / "hermes.py"}" "$@"\n')
        wrapper.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("HERMES_HOME", str(self.root))
        # A test run that happens to come from a Kanban worker carries the fence marker; boards are then the
        # owner's errand, so clear it (and set it explicitly in the test that covers that path).
        monkeypatch.delenv("HERMES_DELEGATED_CHILD_CONTEXT", raising=False)
        monkeypatch.setenv("FAKE_HERMES_LOG", str(self.log))
        monkeypatch.setenv("FAKE_HERMES_SRC", str(self.hsrc))
        # apply runs project_sync.py --setup, which creates ~/Projects/<squad>: keep it inside the test dir
        self.home = tmp / "home"
        self.home.mkdir()
        monkeypatch.setenv("HERMES_REAL_HOME", str(self.home))
        self.models.write_text(yaml.safe_dump(models_doc()))
        (self.src / "squads" / "_schema").mkdir(parents=True)
        shutil.copy(REPO / "squads" / "_schema" / "squad.schema.json", self.src / "squads" / "_schema")
        shutil.copytree(REPO / "squads" / "_base", self.src / "squads" / "_base")
        # The builder manifest is versionless: the release version is injected from distribution.yaml (C-13).
        (self.src / "distribution.yaml").write_text(yaml.safe_dump({"name": "builder", "version": "2.0.0"}))

    # fixtures ----------------------------------------------------------------------------------------------

    def squad(self, key: str, mutate=None) -> dict:
        """Install a fixture draft as squads/<key>/squad.yaml with every asset it references."""
        name = "builder" if key == "builder" else key
        spec = yaml.safe_load((FIX / "squads" / f"{name}.yaml").read_text())
        if mutate:
            mutate(spec)
        dest = self.src / "builder.yaml" if key == "builder" else self.src / "squads" / key / "squad.yaml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(yaml.safe_dump(spec, sort_keys=False))
        base = self.src if key == "builder" else dest.parent
        for bot, b in spec["bots"].items():
            if key != "builder":
                (base / "souls").mkdir(exist_ok=True)
                (base / "souls" / f"{bot}.md").write_text(f"You are {bot}.\n")
            for skill in (b.get("skills") or {}).get("squad") or []:
                d = base / "skills" / skill
                d.mkdir(parents=True, exist_ok=True)
                (d / "SKILL.md").write_text(f"---\nname: {skill}\n---\n# {skill}\n")
                (d / "references").mkdir(exist_ok=True)
                (d / "references" / "a.md").write_text("ref\n")
            for job in (b.get("cron") or {}).values():
                (base / "scripts").mkdir(exist_ok=True)
                (base / "scripts" / job["script"]).write_text("#!/usr/bin/env python3\nprint('{}')\n")
            for entry in (b.get("skills") or {}).get("keep") or []:
                ident = entry if isinstance(entry, str) else entry["id"]
                kind, _, rest = ident.partition(":")
                if kind == "bundled":
                    (self.hsrc / "skills" / "cat" / rest).mkdir(parents=True, exist_ok=True)
                    (self.hsrc / "skills" / "cat" / rest / "SKILL.md").write_text("x")
                elif kind == "official":
                    (self.hsrc / "optional-skills" / rest).mkdir(parents=True, exist_ok=True)
                    (self.hsrc / "optional-skills" / rest / "SKILL.md").write_text("x")
            for plugin in (b.get("plugins") or {}).get("enable") or []:
                if isinstance(plugin, str):
                    (self.hsrc / "plugins" / plugin).mkdir(parents=True, exist_ok=True)
        return spec

    def seed_builder(self) -> Path:
        home = self.root / "profiles" / "builder"
        (home / "skills" / "bundled-demo").mkdir(parents=True)
        (home / "skills" / "bundled-demo" / "SKILL.md").write_text("x")
        (home / "skills" / ".bundled_manifest").write_text("bundled-demo:abc\n")
        (home / "config.yaml").write_text("model: {default: seed}\n")
        (home / "profile.yaml").write_text("description: builder\n")
        return home

    # runs --------------------------------------------------------------------------------------------------

    def run(self, *args, models: bool = True, expect: int | None = 0, capsys=None):
        argv = [*args, "--json", "--hermes-root", str(self.root), "--src", str(self.src), "--local", str(self.local)]
        if models and args[0] in ("plan", "apply"):
            argv += ["--models", str(self.models)]
        code = squadctl.main(argv)
        out = capsys.readouterr()
        if expect is not None:
            assert code == expect, (out.out, out.err)
        text = out.out.strip() or out.err.strip()
        try:
            return code, json.loads(text)
        except ValueError:
            return code, {"raw": text}

    def calls(self) -> list[dict]:
        return [json.loads(ln) for ln in self.log.read_text().splitlines()] if self.log.is_file() else []

    def writes_since(self, n: int) -> list[tuple]:
        return [tuple(c["args"][:2]) for c in self.calls()[n:] if tuple(c["args"][:2]) in WRITES
                or tuple(c["args"][:3]) in {("kanban", "boards", "create"), ("kanban", "boards", "rm")}]

    def config(self, bot: str) -> dict:
        return yaml.safe_load((self.root / "profiles" / bot / "config.yaml").read_text())

    def jobs(self, bot: str) -> list[dict]:
        p = self.root / "profiles" / bot / "cron" / "jobs.json"
        return json.loads(p.read_text())["jobs"] if p.is_file() else []


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


@pytest.fixture
def web(env, capsys):
    env.squad("web")
    code, out = env.run("apply", "web", capsys=capsys)
    assert out["summary"] == {"created": 5}
    return env


# --- apply ------------------------------------------------------------------------------------------------------

def test_apply_web_creates_five_profiles(web):
    for bot in WEB_BOTS:
        assert (web.root / "profiles" / bot / "config.yaml").is_file(), bot
        assert (web.root / "profiles" / bot / ".no-bundled-skills").exists(), bot
    create = [c["args"] for c in web.calls() if c["args"][:2] == ["profile", "create"]]
    assert len(create) == 5
    assert all("--no-skills" in c and "--no-alias" in c and "--description" in c for c in create)
    assert not any("--clone" in a or "--clone-all" in a for c in create for a in c)


def test_apply_writes_model_toolsets_and_lanes(web):
    fe = web.config("web-frontend")
    assert (fe["model"]["provider"], fe["model"]["default"]) == ("prov-frontend", "model-frontend")
    assert fe["agent"]["reasoning_effort"] == "medium"
    assert web.config("web-backend")["agent"]["reasoning_effort"] == "medium"
    assert fe["platform_toolsets"]["cli"] == ["browser", "code_execution", "delegation", "file", "image_gen", "kanban",
                                              "memory", "session_search", "skills", "terminal", "todo", "vision", "web"]
    assert fe["platform_toolsets"]["cron"] == ["terminal", "file", "skills", "kanban", "todo"]
    disabled = fe["agent"]["disabled_toolsets"]
    assert set(ALWAYS) <= set(disabled)
    assert {"cronjob", "video"} <= set(disabled)
    assert not {"terminal", "file", "skills", "kanban", "browser", "vision", "todo", "delegation", "memory", "web",
                "search", "code_execution", "session_search"} & set(disabled)
    assert fe["web"]["keyless_fallback"] is True
    assert fe["auxiliary"]["compression"]["model"] == "model-aux"
    assert fe["auxiliary"]["vision"] == {"provider": "prov-vision", "model": "model-vision"}
    assert fe["skills"]["auto_load"] == ["building-frontend"]
    assert fe["terminal"]["cwd"] == str(web.root / "profiles" / "web-frontend" / "workspace")
    assert Path(fe["terminal"]["cwd"]).is_absolute()
    assert fe["memory"]["memory_enabled"] is True
    assert fe["skills"]["external_dirs"] == [str(web.hsrc / "skills" / "cat" / d)
                                             for d in ("claude-design", "design-md", "popular-web-designs")]
    assert web.config("web")["memory"]["memory_enabled"] is True


def test_no_bot_browses_on_a_copy_of_the_owners_profile_and_an_old_copy_is_turned_off(env, capsys):
    """The owner keeps `browser.use_real_profile` on for their own chats. An earlier version mirrored it onto every
    bot with a browser, managers included: the copy fails whenever the owner's browser is open and hands a bot the
    owner's whole personal session. No bot gets it now, and apply turns off the copy an older version left."""
    (env.root / "config.yaml").write_text("browser:\n  use_real_profile: true\n  real_profile_pin: Profile 3\n")
    builder = env.seed_builder()
    (builder / "config.yaml").write_text("model: {default: seed}\nbrowser:\n  real_profile_pin: Profile 3\n")
    env.squad("web")
    env.run("apply", "web", capsys=capsys)
    for bot in ("web", "web-frontend", "web-qa"):
        assert (env.config(bot).get("browser") or {}).get("use_real_profile") is not True, bot
    cfg = env.config("web")
    cfg["browser"] = {"use_real_profile": True, "real_profile_pin": "Profile 3"}  # what 2.7.0-2.9.2 mirrored
    (env.root / "profiles" / "web" / "config.yaml").write_text(yaml.safe_dump(cfg))
    _, plan = env.run("plan", "web", capsys=capsys)
    assert "browser.use_real_profile" in json.dumps(plan)  # the plan shows the change before it is made
    env.run("apply", "web", capsys=capsys)
    browser = env.config("web")["browser"]
    assert browser["use_real_profile"] is False and not browser.get("real_profile_pin")
    _, again = env.run("plan", "web", capsys=capsys)
    assert "browser.use_real_profile" not in json.dumps(again), "turned off once, then left alone"


def test_apply_never_writes_a_kanban_cap(web, capsys):
    """No kanban cap anywhere: apply writes no `kanban.*` key, root or profile, and has no flag for one."""
    _, out = web.run("apply", "web", capsys=capsys)
    assert "root" not in out
    assert not (web.root / "config.yaml").exists()
    assert all("kanban" not in web.config(b) for b in ("web-frontend", "web-qa"))
    with pytest.raises(SystemExit):
        squadctl.main(["apply", "web", "--set-root-kanban-cap", "--hermes-root", str(web.root)])
    capsys.readouterr()


def test_doctor_warns_on_any_kanban_cap(web, capsys):
    (web.root / "config.yaml").write_text("kanban:\n  max_in_progress_per_profile: 1\n")
    cfg = web.config("web-qa")
    cfg["kanban"] = {"max_in_progress_per_profile": 2}
    (web.root / "profiles" / "web-qa" / "config.yaml").write_text(yaml.safe_dump(cfg))
    _, out = web.run("doctor", capsys=capsys)
    caps = {c["check"]: c for c in out["checks"] if c["check"].endswith(":kanban-cap")}
    assert set(caps) == {"default:kanban-cap", "web-qa:kanban-cap"}
    assert all(c["status"] == "warn" for c in caps.values())
    assert "dead config" in caps["web-qa:kanban-cap"]["detail"]
    assert "config unset kanban.max_in_progress_per_profile" in caps["default:kanban-cap"]["detail"]


def test_delegation_lane_and_passthrough(web):
    assert web.config("web-backend")["delegation"] == {"provider": "prov-code-complex", "model": "model-code-complex",
                                                       "reasoning_effort": "medium"}
    # every bot without its own delegation lane delegates on the cheap research lane
    assert web.config("web-qa")["delegation"]["model"] == "model-research"
    assert web.config("web")["delegation"]["model"] == "model-research"
    # Deploys run through the CLIs' own logins (D-036), so no bot passes a provider token through its env.
    assert web.config("web-deployer")["terminal"]["env_passthrough"] == []
    assert web.config("web-qa")["terminal"]["env_passthrough"] == []


def test_delegation_max_children_sets_the_one_shot_budget(env, capsys):
    """A kanban worker runs as `chat -q`, where Hermes caps delegate_task children at
    delegation.oneshot_max_children (default 2) for the whole run: the jobs reviewer needs five lenses plus re-runs."""
    env.squad("web", mutate=lambda s: s["bots"]["web-backend"]["delegation"].update(max_children=12))
    env.run("apply", "web", capsys=capsys)
    assert env.config("web-backend")["delegation"]["oneshot_max_children"] == 12
    assert "oneshot_max_children" not in env.config("web-qa")["delegation"]  # no key: Hermes's default stays


def test_ui_meta_hidden_section_and_revision(web):
    """All bots are visible (V-12); the manager is filed under Managers, workers under the squad section."""
    manager = yaml.safe_load((web.root / "profiles" / "web" / "profile.yaml").read_text())
    worker = yaml.safe_load((web.root / "profiles" / "web-qa" / "profile.yaml").read_text())
    # squadName: managers share the Managers section, and squad-hub letters an empty chat with the squad
    assert manager["ui_meta"]["hermes-bots"] == {"title": "Web manager", "hidden": False,
                                                 "sectionId": "managers", "sectionName": "Managers", "squadName": "Web"}
    assert worker["ui_meta"]["hermes-bots"] == {"title": "Web QA", "hidden": False,
                                                "sectionId": "web", "sectionName": "Web", "squadName": "Web"}
    assert manager["_ui_meta_revisions"] == {"hermes-bots": 1}


def test_skills_copied_with_sha_marker_and_soul(web):
    home = web.root / "profiles" / "web-frontend"
    for skill in ("building-frontend", "site-contract"):
        d = home / "skills" / "squad-web" / skill
        assert (d / "SKILL.md").is_file() and (d / "references" / "a.md").is_file()
        assert len((d / ".squad-sha").read_text().strip()) == 64
        assert not d.is_symlink()
    soul = (home / "SOUL.md").read_text()
    base = (REPO / "squads" / "_base" / "hermes-base.md").read_text().rstrip("\n")
    assert soul == f"{FAKE_IDENTITY}\n\n{base}\n\nYou are web-frontend.\n"
    assert not (home / "skills" / "squad-web" / "leading-web").exists()


def test_plugins_mcp_cron_board_installed(web):
    assert web.config("web-frontend")["plugins"]["enabled"] == ["disk-cleanup", "security-guidance", "squad-kanban"]
    assert "context7" in web.config("web-frontend")["mcp_servers"]
    assert "chrome-devtools" in web.config("web-qa")["mcp_servers"]
    (job,) = web.jobs("web")
    assert (job["name"], job["script"], job["no_agent"]) == ("web-watch", "board_watch.py", True)
    assert job["deliver"] == "bot-chat:web"
    assert job["schedule"]["expr"] == "*/30 * * * *"
    assert (web.root / "profiles" / "web" / "scripts" / "board_watch.py").is_file()
    assert web.jobs("web-qa") == []
    boards = json.loads((web.root / "boards.json").read_text())
    assert [(b["slug"], b["archived"]) for b in boards] == [("web", False)]
    installed = yaml.safe_load((web.local / "installed.yaml").read_text())
    assert installed["squads"]["web"]["bots"] == WEB_BOTS
    assert installed["lanes"]["frontend"]["model"] == "model-frontend"


def test_board_creation_is_the_owner_errand_inside_a_kanban_worker(env, capsys, monkeypatch):
    """Hermes refuses `kanban boards create` from a Kanban worker: skip the board, keep the profile work."""
    monkeypatch.setenv("HERMES_DELEGATED_CHILD_CONTEXT", str(env.root))
    env.squad("web")
    _, out = env.run("apply", "web", capsys=capsys)
    assert out["board"] == ("pending owner action: hermes kanban boards create "
                            + shlex.join(["web", "--name", "Web", "--icon=🌐", "--color=#2F6FEB",
                                          "--description=Web sites: interview, build, preview, QA, deploy"]))
    assert out["summary"] == {"created": 5}
    assert not any(c["args"][:3] == ["kanban", "boards", "create"] for c in env.calls())
    _, st = env.run("status", "web", capsys=capsys)
    assert st["squads"][0]["board"].startswith("pending owner action: hermes kanban boards create web")


def test_an_existing_board_is_reported_inside_a_kanban_worker(env, capsys, monkeypatch):
    """The fenced worker checks `kanban boards list` first: an existing board is 'exists', never an owner errand."""
    monkeypatch.setenv("HERMES_DELEGATED_CHILD_CONTEXT", str(env.root))
    env.squad("web")
    (env.root / "boards.json").write_text(json.dumps([{"slug": "web", "name": "Web", "archived": False}]))
    _, out = env.run("apply", "web", capsys=capsys)
    assert out["board"] == "exists"
    assert out["summary"] == {"created": 5}
    assert not any(c["args"][:3] == ["kanban", "boards", "create"] for c in env.calls())
    _, st = env.run("status", "web", capsys=capsys)
    assert st["squads"][0]["board"] == "exists"


def test_provider_plugin_is_copied_into_the_bot_profile(env, capsys):
    """A provider that is a user plugin of the builder is `Unknown provider` elsewhere until it is copied."""
    plugin = env.root / "profiles" / "builder" / "plugins" / "model-providers" / "prov-frontend"
    plugin.mkdir(parents=True)
    (plugin / "plugin.yaml").write_text("name: prov-frontend\nkind: model-provider\nversion: 1.0.0\n")
    (plugin / "__init__.py").write_text("registered = True\n")
    env.squad("web")
    _, out = env.run("apply", "web", capsys=capsys)
    fe = next(b for b in out["bots"] if b["bot"] == "web-frontend")
    assert "provider plugin + prov-frontend" in fe["actions"]
    dest = env.root / "profiles" / "web-frontend" / "plugins" / "model-providers" / "prov-frontend"
    assert (dest / "__init__.py").read_text() == "registered = True\n"
    # merged with the plugins.enable items of the spec, never replacing them
    assert env.config("web-frontend")["plugins"]["enabled"] == [
        "disk-cleanup", "model-providers/prov-frontend", "security-guidance", "squad-kanban"]
    # every bot gets every provider the user connected: a model switch or a card pin can pick it in any bot
    assert "model-providers/prov-frontend" in env.config("web-qa")["plugins"]["enabled"]
    _, out = env.run("apply", "web", "--bots", "web-frontend", capsys=capsys)
    assert out["bots"][0]["status"] == "unchanged"


def test_provider_change_clears_the_stale_route(env, capsys):
    """`model.base_url`/`api_mode` are route state of the old provider and would post the new key there."""
    env.squad("web")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    cfg = env.root / "profiles" / "web-qa" / "config.yaml"
    data = yaml.safe_load(cfg.read_text())
    data["model"] = {"provider": "old-prov", "default": "model-review", "base_url": "process://local",
                     "api_mode": "chat_completions"}
    cfg.write_text(yaml.safe_dump(data))
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    assert any("model.base_url" in a for a in qa["actions"])
    data = yaml.safe_load(cfg.read_text())
    assert (data["model"]["provider"], data["model"]["default"]) == ("prov-review", "model-review")
    assert data["model"]["base_url"] == "" and data["model"]["api_mode"] == ""


def test_root_provider_plugin_is_copied_and_keyless_provider_needs_no_key(env, capsys, monkeypatch):
    """A provider plugin installed at the root home is copied like a builder one; a provider that declares
    no API-key env var (OAuth or external process) gets no credentials note."""
    plugin = env.root / "plugins" / "prov-keyless"
    plugin.mkdir(parents=True)
    (plugin / "plugin.yaml").write_text("name: prov-keyless\nkind: model-provider\n")
    env.squad("web")
    doc = models_doc()
    doc["bots"] = {"web-frontend": {"provider": "prov-keyless", "model": "model-x", "reasoning": "high"}}
    env.models.write_text(yaml.safe_dump(doc))
    _, out = env.run("apply", "web", "--bots", "web-frontend", capsys=capsys)
    (fe,) = out["bots"]
    assert "provider plugin + prov-keyless" in fe["actions"]
    assert (env.root / "profiles" / "web-frontend" / "plugins" / "prov-keyless" / "plugin.yaml").is_file()
    assert "prov-keyless" in env.config("web-frontend")["plugins"]["enabled"]
    # the bot's own model needs no key; its delegation and auxiliary lanes still name theirs
    assert not any(n.startswith("credentials") and "prov-keyless" in n for n in fe.get("notes", []))


def test_inventory_documents_profiles_read_only(web, capsys):
    n = len(web.calls())
    (web.root / "profiles" / "web" / ".env").write_text("SECRET_TOKEN=do-not-read\n")
    _, out = web.run("inventory", capsys=capsys)
    rows = {r["profile"]: r for r in out["profiles"]}
    assert set(rows) == {"default", *WEB_BOTS}
    assert rows["web"]["squad"] == "web" and rows["web"]["section"] == "Managers"
    assert rows["web-frontend"]["model"]["provider"] == "prov-frontend"
    assert "do-not-read" not in json.dumps(out)
    assert web.writes_since(n) == []
    _, out = web.run("inventory", "--profiles", "web-qa", "--out", str(web.local / "fleet.yaml"), capsys=capsys)
    assert out == {"written": str(web.local / "fleet.yaml"), "profiles": 1}
    _, out = web.run("inventory", "--out", str(web.tmp / "fleet.yaml"), expect=1, capsys=capsys)
    assert "must live under" in out["error"]
    _, out = web.run("inventory", "--profiles", "nope", expect=1, capsys=capsys)
    assert "no such profile" in out["error"]


def test_a_plain_apply_copies_the_provider_key_and_plan_writes_nothing(env, capsys, monkeypatch):
    """Real problem: a new squad came up with every bot lacking its provider key, because the copy waited for an
    `--yes` the skills never passed; the user had to ask again. The plan lists the copy (that is the OK), the apply
    makes it, with no extra flag. The value never reaches output."""
    monkeypatch.setenv("PROV_FRONTEND_API_KEY", "sk-val...rint")
    env.squad("web")
    env_file = env.root / "profiles" / "web-frontend" / ".env"
    _, out = env.run("plan", "web", "--bots", "web-frontend", capsys=capsys)
    assert any("credentials PROV_FRONTEND_API_KEY: copied into web-frontend" in a for a in out["bots"][0]["actions"])
    assert not env_file.exists(), "plan writes nothing"
    _, out = env.run("apply", "web", "--bots", "web-frontend", capsys=capsys)
    (fe,) = out["bots"]
    assert "credentials PROV_FRONTEND_API_KEY: copied into web-frontend (mode 600)" in fe["actions"]
    assert "PROV_FRONTEND_API_KEY=sk-val...rint" in env_file.read_text().splitlines()
    assert oct(env_file.stat().st_mode)[-3:] == "600"
    assert "sk-val...rint" not in json.dumps(out)
    _, out = env.run("apply", "web", "--bots", "web-frontend", capsys=capsys)
    assert out["summary"] == {"unchanged": 1}, "the copy is idempotent"


def test_every_connected_provider_reaches_every_bot_not_only_its_lane(env, capsys, monkeypatch):
    """Real problem: the user switched a bot to another of their providers (or a card pinned one) and the bot had no
    key for it. Every provider connected at the root or in the builder lands in every bot, even one no lane uses."""
    for name in lane_keys():
        monkeypatch.delenv(name, raising=False)
    (env.root / ".env").write_text("PROV_RESEARCH_API_KEY=sk-root-research\n")
    builder_env = env.root / "profiles" / "builder" / ".env"
    builder_env.parent.mkdir(parents=True, exist_ok=True)
    builder_env.write_text("PROV_DIGEST_API_KEY=sk-builder-digest\n")  # `hermes model` run inside the builder
    env.squad("web")
    _, out = env.run("apply", "web", capsys=capsys)
    for bot in ("web", "web-frontend", "web-backend", "web-qa", "web-deployer"):
        names = env_names_of(env.root / "profiles" / bot / ".env")
        assert {"PROV_RESEARCH_API_KEY", "PROV_DIGEST_API_KEY"} <= names, (bot, names)
    assert "sk-root-research" not in json.dumps(out) and "sk-builder-digest" not in json.dumps(out)
    qa = next(b for b in out["bots"] if b["bot"] == "web-qa")
    assert not any("PROV_FRONTEND_API_KEY" in n for n in qa.get("notes") or []), "an unconnected extra is no gap"


def test_an_excluded_provider_is_not_handed_to_the_bots(env, capsys, monkeypatch):
    for name in lane_keys():
        monkeypatch.delenv(name, raising=False)
    (env.root / ".env").write_text("PROV_RESEARCH_API_KEY=sk-a\nPROV_DIGEST_API_KEY=sk-b\n")
    env.local.mkdir(parents=True, exist_ok=True)
    (env.local / "providers-exclude.txt").write_text("prov-digest  # the user's work account\n")
    env.squad("web")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    names = env_names_of(env.root / "profiles" / "web-qa" / ".env")
    assert "PROV_RESEARCH_API_KEY" in names and "PROV_DIGEST_API_KEY" not in names


def test_a_rotated_key_follows_into_the_bots_but_a_hand_set_one_is_kept(env, capsys, monkeypatch):
    """The user rotates a key at the root: bots that got squadctl's copy follow it on the next apply or upgrade; a key
    the user set by hand in one bot is theirs and is never overwritten."""
    for name in lane_keys():
        monkeypatch.delenv(name, raising=False)
    (env.root / ".env").write_text("PROV_REVIEW_API_KEY=sk-old\n")
    env.squad("web")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    fe_env = env.root / "profiles" / "web-frontend" / ".env"
    fe_env.parent.mkdir(parents=True, exist_ok=True)
    fe_env.write_text("PROV_REVIEW_API_KEY=sk-hand\n")
    (env.root / ".env").write_text("PROV_REVIEW_API_KEY=sk-new\n")
    _, out = env.run("apply", "web", "--bots", "web-qa,web-frontend", capsys=capsys)
    qa = next(b for b in out["bots"] if b["bot"] == "web-qa")
    assert "credentials PROV_REVIEW_API_KEY: refreshed in web-qa (the source key changed)" in qa["actions"]
    assert "PROV_REVIEW_API_KEY=sk-new" in (env.root / "profiles" / "web-qa" / ".env").read_text()
    assert "PROV_REVIEW_API_KEY=sk-hand" in fe_env.read_text()
    assert "sk-new" not in json.dumps(out) and "sk-hand" not in json.dumps(out)


def test_provider_key_is_copied_from_the_root_env_file(env, capsys, monkeypatch):
    """The root env file is the other copy source; quotes and export are handled, the value never reaches output."""
    monkeypatch.delenv("PROV_REVIEW_API_KEY", raising=False)
    (env.root / ".env").write_text("# gateway pool\nexport PROV_REVIEW_API_KEY='sk-root...alue'\n")
    env.squad("web")
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    assert "credentials PROV_REVIEW_API_KEY: copied into web-qa (mode 600)" in qa["actions"]
    env_file = env.root / "profiles" / "web-qa" / ".env"
    assert env_file.read_text() == "PROV_REVIEW_API_KEY=sk-root...alue\n"
    assert oct(env_file.stat().st_mode)[-3:] == "600"
    assert "sk-root...alue" not in json.dumps(out)


def test_a_root_key_the_cli_lists_as_env_is_still_copied_into_the_bot(env, capsys, monkeypatch):
    """Real install: `hermes -p <bot> auth list` printed the root key as an `env:` credential, apply took it for the
    profile's own store, copied nothing, and the bot ran on its fallback model. An env-sourced row is not the bot's."""
    for name in lane_keys():
        monkeypatch.delenv(name, raising=False)
    (env.root / ".env").write_text("".join(f"{k}=sk-root-{i}\n" for i, k in enumerate(lane_keys())))
    env.squad("web")
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    assert "credentials PROV_REVIEW_API_KEY: copied into web-qa (mode 600)" in qa["actions"], qa
    assert "PROV_REVIEW_API_KEY=" in (env.root / "profiles" / "web-qa" / ".env").read_text()
    _, out = env.run("doctor", "web", capsys=capsys)
    checks = {c["check"]: c for c in out["checks"]}
    assert checks["web-qa:credentials"]["status"] == "ok" and "env file" in checks["web-qa:credentials"]["detail"]


def test_every_provider_a_bot_runs_on_gets_its_key_not_only_the_main_model(env, capsys, monkeypatch):
    """Real install: jobs-writer ran on a subscription provider with no API key, its delegate_task children on a
    keyed provider whose key only the root held. Apply copied nothing and every delegation failed with "no key for
    the provider". Delegation, auxiliary slots and chain stages each get their provider's key."""
    for name in lane_keys():
        monkeypatch.delenv(name, raising=False)
    (env.root / ".env").write_text("".join(f"{k}=sk-root-{i}\n" for i, k in enumerate(lane_keys())))
    env.squad("web")
    doc = models_doc()
    doc["bots"] = {"web-backend": {"provider": "prov-keyless", "model": "model-x", "reasoning": "high"}}
    env.models.write_text(yaml.safe_dump(doc))
    plugin = env.root / "plugins" / "prov-keyless"
    plugin.mkdir(parents=True)
    (plugin / "plugin.yaml").write_text("name: prov-keyless\nkind: model-provider\n")
    _, out = env.run("apply", "web", "--bots", "web-backend", capsys=capsys)
    (be,) = out["bots"]
    copied = {a.split()[1].rstrip(":") for a in be["actions"] if a.startswith("credentials")}
    assert {"PROV_CODE_COMPLEX_API_KEY", "PROV_AUX_API_KEY", "PROV_VISION_API_KEY"} <= copied, be["actions"]
    written = env_names_of(env.root / "profiles" / "web-backend" / ".env")
    assert copied <= written
    _, out = env.run("doctor", "web", capsys=capsys)
    checks = {c["check"]: c for c in out["checks"]}
    assert checks["web-backend:credentials"]["status"] == "ok", checks["web-backend:credentials"]


def lane_keys() -> list[str]:
    return [f"PROV_{lane.upper().replace('-', '_')}_API_KEY" for lane in LANES]


def env_names_of(path: Path) -> set[str]:
    return {line.split("=", 1)[0] for line in path.read_text().splitlines() if "=" in line}


def test_doctor_credentials_check_and_models_never_pass_without_them(env, capsys, monkeypatch):
    """C-14: `<bot>:credentials` per bot; `models ok` passes only when the bot can authenticate."""
    monkeypatch.delenv("PROV_REVIEW_API_KEY", raising=False)
    env.squad("web")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    env.local.joinpath("installed.yaml").write_text(yaml.safe_dump({"squads": {"web": {"version": "3.0.0"}},
                                                                   **models_doc()}))
    _, out = env.run("doctor", "web", capsys=capsys)
    checks = {c["check"]: c for c in out["checks"]}
    assert checks["web-qa:credentials"]["status"] == "warn"
    assert "PROV_REVIEW_API_KEY" in checks["web-qa:credentials"]["detail"]
    assert checks["web-qa:models"]["status"] == "warn", "models ok must not pass without credentials"
    assert "assigned" in checks["web-qa:models"]["detail"]
    home = env.root / "profiles" / "web-qa"
    (home / ".env").write_text("PROV_REVIEW_API_KEY=sk-x\n")
    _, out = env.run("doctor", "web", capsys=capsys)
    checks = {c["check"]: c for c in out["checks"]}
    # its own key alone is not enough: delegation and auxiliary slots run on other providers
    assert checks["web-qa:credentials"]["status"] == "warn" and "PROV_AUX_API_KEY" in checks["web-qa:credentials"]["detail"]
    (home / ".env").write_text("".join(f"{k}=sk-x\n" for k in lane_keys()))
    _, out = env.run("doctor", "web", capsys=capsys)
    checks = {c["check"]: c for c in out["checks"]}
    assert checks["web-qa:credentials"]["status"] == "ok" and checks["web-qa:models"]["status"] == "ok"
    assert "sk-x" not in json.dumps(out)
    (home / ".env").unlink()
    (home / "auth-names.json").write_text(json.dumps([f"prov-{lane}" for lane in LANES]))  # the auth store counts too
    _, out = env.run("doctor", "web", capsys=capsys)
    checks = {c["check"]: c for c in out["checks"]}
    assert checks["web-qa:credentials"]["status"] == "ok" and "auth store" in checks["web-qa:credentials"]["detail"]
    assert checks["web-qa:models"]["status"] == "ok"


def test_apply_is_idempotent(web, capsys):
    mark = len(web.calls())
    before = tree_hash(web.root)
    _, out = web.run("apply", "web", capsys=capsys)
    assert out["summary"] == {"unchanged": 5}
    assert [b["status"] for b in out["bots"]] == ["unchanged"] * 5
    assert all(not b.get("actions") for b in out["bots"])
    assert web.writes_since(mark) == []
    assert tree_hash(web.root) == before


def test_dry_run_leaves_tree_equal(env, capsys):
    env.squad("web")
    before = (tree_hash(env.root), tree_hash(env.src))
    _, out = env.run("apply", "web", "--dry-run", capsys=capsys)
    assert out["dry_run"] is True and out["board"] == "would-create"
    assert out["summary"] == {"would-create": 5}
    assert (tree_hash(env.root), tree_hash(env.src)) == before
    assert list((env.root / "profiles").iterdir()) == []
    assert env.writes_since(0) == []
    assert not (env.local / "installed.yaml").exists()
    first = out["bots"][0]["actions"]
    assert first[0].startswith("profile create")
    assert any(a.startswith("set ") and "config keys (model prov-manager/model-manager medium)" in a for a in first)


def test_dry_run_after_apply_shows_diff_without_writing(web, capsys):
    web.models.write_text(yaml.safe_dump({"lanes": {**models_doc()["lanes"],
                                                    "frontend": {"provider": "p2", "model": "model-new"}}}))
    before = tree_hash(web.root)
    mark = len(web.calls())
    _, out = web.run("plan", "web", capsys=capsys)
    fe = next(b for b in out["bots"] if b["bot"] == "web-frontend")
    assert fe["status"] == "would-change"
    assert "set model.default: model-frontend -> model-new" in fe["actions"]
    assert tree_hash(web.root) == before and web.writes_since(mark) == []


def test_aux_lane_change_is_one_grouped_action(web, capsys):
    web.models.write_text(yaml.safe_dump({"lanes": {**models_doc()["lanes"], "aux": {"provider": "p", "model": "aux2"}}}))
    _, out = web.run("plan", "web", capsys=capsys)
    assert out["bots"][0]["actions"] == ["set auxiliary.*.provider: prov-aux -> p (13 keys)",
                                         "set auxiliary.*.model: model-aux -> aux2 (13 keys)"]


def test_plan_equals_apply_dry_run(env, capsys):
    env.squad("web")
    _, a = env.run("plan", "web", capsys=capsys)
    _, b = env.run("apply", "web", "--dry-run", capsys=capsys)
    assert a == b


def test_config_drift_is_repaired_and_only_that(web, capsys):
    cfg = web.root / "profiles" / "web-qa" / "config.yaml"
    data = yaml.safe_load(cfg.read_text())
    data["model"]["default"] = "hand-edited"
    cfg.write_text(yaml.safe_dump(data))
    _, out = web.run("apply", "web", capsys=capsys)
    assert out["summary"] == {"unchanged": 4, "changed": 1}
    qa = next(b for b in out["bots"] if b["bot"] == "web-qa")
    assert qa["actions"] == ["set model.default: hand-edited -> model-review"]
    assert web.config("web-qa")["model"]["default"] == "model-review"


def test_bots_filter(env, capsys):
    env.squad("web")
    _, out = env.run("apply", "web", "--bots", "web,web-qa", capsys=capsys)
    assert [b["bot"] for b in out["bots"]] == ["web", "web-qa"]
    assert not (env.root / "profiles" / "web-frontend").exists()
    _, out = env.run("apply", "web", "--bots", "nope", expect=1, capsys=capsys)
    assert "not in web" in out["error"]


def test_missing_models_plan_warns_apply_refuses(env, capsys):
    env.squad("web")
    _, out = env.run("plan", "web", models=False, capsys=capsys)
    notes = [n for b in out["bots"] for n in b.get("notes", [])]
    assert any("no model assigned for web-frontend (lane frontend)" in n for n in notes)
    _, err = env.run("apply", "web", models=False, expect=2, capsys=capsys)
    assert "model_advisor" in err["error"] and not (env.root / "profiles" / "web").exists()


def test_per_bot_model_beats_lane_and_user_reasoning_wins(env, capsys):
    env.squad("web")
    doc = models_doc()
    doc["bots"] = {"web-frontend": {"provider": "mine", "model": "pinned", "reasoning": "high"}}
    env.models.write_text(yaml.safe_dump(doc))
    env.run("apply", "web", capsys=capsys)
    fe = env.config("web-frontend")
    assert (fe["model"]["provider"], fe["model"]["default"], fe["agent"]["reasoning_effort"]) == ("mine", "pinned", "high")
    assert env.config("web-qa")["model"]["default"] == "model-review"


def test_fallback_chain_reaches_every_bot_its_children_and_installed_yaml(env, capsys):
    """Same shape as the owner's models file: a top-level `fallback:` list (Sonnet high, then Haiku xhigh)."""
    env.squad("web")
    doc = models_doc()
    doc["fallback"] = [{"provider": "anthropic", "model": "claude-sonnet-4-6", "reasoning": "high"},
                       {"provider": "anthropic", "model": "claude-haiku-4-5", "reasoning": "xhigh"},
                       {"provider": "anthropic"}]  # incomplete rows are dropped, as Hermes drops them
    env.models.write_text(yaml.safe_dump(doc))
    env.run("apply", "web", capsys=capsys)
    chain = [{"provider": "anthropic", "model": "claude-sonnet-4-6"},
             {"provider": "anthropic", "model": "claude-haiku-4-5"}]
    for bot in WEB_BOTS:
        cfg = env.config(bot)
        assert cfg["fallback_providers"] == chain, bot
        assert cfg["delegation"]["fallback_providers"] == chain, bot
        assert cfg["agent"]["reasoning_overrides"] == {"claude-sonnet-4-6": "high", "claude-haiku-4-5": "xhigh"}
    saved = yaml.safe_load((env.local / "installed.yaml").read_text())
    assert [r["model"] for r in saved["fallback"]] == ["claude-sonnet-4-6", "claude-haiku-4-5"]
    # A later models file without `fallback:` inherits the saved chain; `fallback: []` clears it.
    env.models.write_text(yaml.safe_dump(models_doc()))
    _, out = env.run("apply", "web", capsys=capsys)
    assert out["summary"] == {"unchanged": 5}
    env.models.write_text(yaml.safe_dump({**models_doc(), "fallback": []}))
    env.run("apply", "web", capsys=capsys)
    assert env.config("web-qa")["fallback_providers"] == []
    assert "fallback" not in yaml.safe_load((env.local / "installed.yaml").read_text())


def test_models_file_accepts_model_advisor_json(env, capsys):
    env.squad("web")
    rows = [{"bot": b, "lane": l, "model": f"adv-{l}", "provider": "adv", "reasoning": "low", "extras": []}
            for b, l in (("web", "manager"), ("web-frontend", "frontend"), ("web-backend", "code-routine"),
                         ("web-qa", "review"), ("web-deployer", "deploy"))]
    rows[2]["extras"] = [{"use": "delegation", "lane": "code-complex", "model": "adv-code-complex", "provider": "adv",
                          "reasoning": "medium"}]
    shared = [{"use": u, "lane": l, "model": f"adv-{l}", "provider": "adv", "reasoning": "low"}
              for u, l in (("aux", "aux"), ("vision", "vision"), ("delegation", "research"))]
    env.models.write_text(json.dumps({"bots": rows, "shared": shared}))
    env.run("apply", "web", capsys=capsys)
    assert env.config("web-backend")["delegation"]["model"] == "adv-code-complex"
    assert env.config("web-frontend")["auxiliary"]["vision"]["model"] == "adv-vision"
    assert env.config("web-frontend")["model"]["default"] == "adv-frontend"


def test_plan_self_resolves_lanes_from_the_real_model_advisor_json(env, capsys):
    """The builder's first run: `model_advisor.py builder --json > f`, then `plan --self --models f`."""
    import model_advisor
    env.squad("builder")
    env.seed_builder()
    assert model_advisor.main([str(env.src / "builder.yaml"), "--json", "--providers", "cache",
                               "--cache", str(FIX / "caches" / "anthropic-only.json"),
                               "--local-roles", str(FIX / "nonexistent.yaml")]) == 0
    advice = capsys.readouterr().out
    assert "squads" in json.loads(advice)  # the advisor nests bots under squads[]
    env.models.write_text(advice)
    _, out = env.run("plan", "--self", capsys=capsys)
    (bot,) = out["bots"]
    assert not [n for n in bot.get("notes", []) if n.startswith("no model assigned")], bot
    assert any(a.startswith("set model.default") and "claude" in a for a in bot["actions"]), bot["actions"]


def test_vision_capable_main_model_gets_no_auxiliary_vision(env, capsys):
    """An explicit auxiliary.vision turns native images into text descriptions in `auto` mode
    (agent/image_routing.py), so only text-only main models get one (D-021)."""
    env.squad("web")
    doc = models_doc()
    doc["lanes"]["frontend"]["model"] = "model-native-frontend"  # the fake image_routing calls it vision-capable
    env.models.write_text(yaml.safe_dump(doc))
    env.run("apply", "web", capsys=capsys)
    vision = (env.config("web-frontend").get("auxiliary") or {}).get("vision") or {}
    assert not vision.get("provider") and not vision.get("model")
    assert env.config("web")["auxiliary"]["vision"] == {"provider": "prov-vision", "model": "model-vision"}
    _, out = env.run("apply", "web", capsys=capsys)
    assert out["summary"] == {"unchanged": 5}


def test_a_vision_model_switch_clears_a_stale_auxiliary_vision(web, capsys):
    assert web.config("web-frontend")["auxiliary"]["vision"]["model"] == "model-vision"
    doc = models_doc()
    doc["lanes"]["frontend"]["model"] = "model-native-frontend"
    web.models.write_text(yaml.safe_dump(doc))
    web.run("apply", "web", capsys=capsys)
    assert web.config("web-frontend")["auxiliary"]["vision"] == {"provider": "", "model": ""}


# --- overlay and validation ---------------------------------------------------------------------------------------

def test_local_overlay_changes_one_bot_and_can_remove_one(env, capsys):
    env.squad("web")
    overlay = env.local / "squads" / "web" / "squad.yaml"
    overlay.parent.mkdir(parents=True)
    overlay.write_text(yaml.safe_dump({"bots": {"web-qa": {"toolsets": ["file", "skills", "kanban", "todo"]},
                                                "web-deployer": None},
                                       "chains": {"onboarding": None, "deploy-production": None,
                                                  "milestone": [{"stage": "ui", "assignee": "web-frontend"}]}}))
    _, out = env.run("plan", "web", capsys=capsys)
    assert [b["bot"] for b in out["bots"]] == ["web", "web-frontend", "web-backend", "web-qa"]
    env.run("apply", "web", capsys=capsys)
    # an overlay narrows the manifest toolsets; the Hermes base stays
    assert env.config("web-qa")["platform_toolsets"]["cli"] == ["code_execution", "delegation", "file", "kanban", "memory",
                                                              "session_search", "skills", "terminal", "todo", "web"]
    assert "browser" in env.config("web-qa")["agent"]["disabled_toolsets"]


@pytest.mark.parametrize("mutate,message", [
    (lambda s: s["bots"]["web"].update(role="worker"), "role manager"),
    (lambda s: s["bots"]["web"].update(title="Web lead"), "manager title must be"),
    (lambda s: s["bots"]["web-qa"].update(toolsets=["file", "kanban", "a2a"]), "always-disabled"),
    (lambda s: s["bots"]["web-qa"].update(lane="nonexistent"), "nonexistent"),
    (lambda s: s["chains"]["milestone"][0].update(assignee="ghost"), "ghost"),
    (lambda s: s.update(key="other"), "other"),
])
def test_invalid_squad_is_rejected(env, capsys, mutate, message):
    env.squad("web", mutate)
    _, out = env.run("plan", "web", expect=1, capsys=capsys)
    assert out["error"].startswith("invalid squad web") and message in out["error"]


def test_worker_must_carry_the_squad_prefix(env, capsys):
    def rename(spec):
        spec["bots"]["qa"] = spec["bots"].pop("web-qa")
    env.squad("web", rename)
    _, out = env.run("plan", "web", expect=1, capsys=capsys)
    assert "must be prefixed web-" in out["error"]


def test_manager_must_be_named_after_the_squad_key(env, capsys):
    def rename(spec):
        spec["manager"] = "chief"
        spec["bots"]["chief"] = spec["bots"].pop("web")
    env.squad("web", rename)
    _, out = env.run("plan", "web", expect=1, capsys=capsys)
    assert "must be named 'web'" in out["error"]


def test_more_than_five_required_bots_need_optional(env, capsys):
    def crowd(spec):
        spec["bots"]["web-extra"] = {"role": "worker", "title": "Web extra", "description": "sixth required bot",
                                     "lane": "manager", "toolsets": ["file", "skills", "kanban", "todo"]}
    env.squad("web", crowd)
    _, out = env.run("plan", "web", expect=1, capsys=capsys)
    assert "at most 5 required bots" in out["error"]


def test_optional_bot_installs_only_with_the_with_flag(env, capsys):
    def add_pro(spec):
        spec["bots"]["web-frontend-pro"] = {
            "optional": True, "role": "worker", "title": "Web frontend pro",
            "description": "3D and complex motion when the brief needs it",
            "lane": "manager", "toolsets": ["file", "skills", "kanban", "todo"]}
    env.squad("web", add_pro)
    _, out = env.run("apply", "web", capsys=capsys)
    assert out["summary"] == {"created": 5} and out["optional_skipped"] == ["web-frontend-pro"]
    assert not (env.root / "profiles" / "web-frontend-pro").exists()
    installed = yaml.safe_load((env.local / "installed.yaml").read_text())
    assert installed["squads"]["web"]["bots"] == WEB_BOTS
    _, st = env.run("status", "web", capsys=capsys)
    assert "web-frontend-pro" not in [b["bot"] for b in st["squads"][0]["bots"]]  # live-state hides a missing optional
    _, out = env.run("apply", "web", "--with", "web-frontend-pro", capsys=capsys)
    assert out["summary"] == {"created": 1, "unchanged": 5} and "optional_skipped" not in out
    assert (env.root / "profiles" / "web-frontend-pro" / "config.yaml").is_file()
    installed = yaml.safe_load((env.local / "installed.yaml").read_text())
    assert installed["squads"]["web"]["bots"] == [*WEB_BOTS, "web-frontend-pro"]
    _, st = env.run("status", "web", capsys=capsys)
    assert "web-frontend-pro" in [b["bot"] for b in st["squads"][0]["bots"]]
    _, out = env.run("apply", "web", "--bots", "web-frontend-pro", expect=1, capsys=capsys)
    assert "optional bots install only with --with" in out["error"]
    _, out = env.run("apply", "web", "--with", "web", expect=1, capsys=capsys)
    assert "names only optional bots" in out["error"]


def test_unknown_squad_lists_the_available_ones(env, capsys):
    env.squad("web")
    _, out = env.run("plan", "nope", expect=1, capsys=capsys)
    assert "available: web" in out["error"]


def test_apply_needs_a_squad_or_self(env, capsys):
    _, out = env.run("apply", expect=1, capsys=capsys)
    assert "squad key or --self" in out["error"]


# --- skills, plugins, confirm ---------------------------------------------------------------------------------------

def test_learned_skills_are_reported_never_removed(env, capsys):
    """Skills apply did not install (skill_manage writes, user copies) stay and show as `learned`."""
    env.squad("web")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    skills = env.root / "profiles" / "web-qa" / "skills"
    owned = json.loads((skills / squadctl.OWNED_FILE).read_text())["skills"]
    assert owned == ["squad-web/reviewing-sites", "squad-web/site-contract"]
    for stray in ("random-skill", "cat/other-skill"):
        (skills / stray).mkdir(parents=True)
        (skills / stray / "SKILL.md").write_text("x")
    _, plan = env.run("plan", "web", "--bots", "web-qa", capsys=capsys)
    assert plan["bots"][0]["learned"] == ["cat/other-skill", "random-skill"]
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    assert qa["status"] == "unchanged" and qa["learned"] == ["cat/other-skill", "random-skill"]
    assert (skills / "random-skill" / "SKILL.md").is_file() and (skills / "cat" / "other-skill" / "SKILL.md").is_file()
    assert not list((env.local / "backups").glob("web-qa-*.tar.gz"))


def test_prune_removes_only_what_apply_installed_and_backs_up_first(env, capsys):
    """A squad skill dropped from the manifest (an owned path) is removed; the hub lock is kept."""
    env.squad("web")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    skills = env.root / "profiles" / "web-qa" / "skills"
    old = skills / "squad-web" / "old-skill"
    old.mkdir()
    (old / "SKILL.md").write_text("x")
    squadctl.write_owned(skills.parent, squadctl.read_owned(skills.parent) | {"squad-web/old-skill"})
    (skills / ".hub").mkdir(exist_ok=True)
    lock = skills / ".hub" / "lock.json"
    data = json.loads(lock.read_text()) if lock.is_file() else {"installed": {}}
    data["installed"]["kept-by-lock"] = {}
    lock.write_text(json.dumps(data))
    (skills / "cat" / "kept-by-lock").mkdir(parents=True)
    (skills / "cat" / "kept-by-lock" / "SKILL.md").write_text("x")
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    assert qa["actions"] == ["skills removed: 1 (squad-web/old-skill)"]
    assert not old.exists()
    assert (skills / "cat" / "kept-by-lock" / "SKILL.md").is_file()
    assert (skills / "squad-web" / "reviewing-sites" / "SKILL.md").is_file()
    assert len(list((env.local / "backups").glob("web-qa-*.tar.gz"))) == 1


def test_memory_is_on_by_default_and_adds_the_toolset(env, capsys):
    """A bot without `memory:` gets built-in memory and the memory toolset; `memory: false` turns both off."""
    def mutate(spec):
        spec["bots"]["web-backend"].pop("memory", None)
        spec["bots"]["web-qa"]["memory"] = False
    env.squad("web", mutate)
    env.run("apply", "web", capsys=capsys)
    be, qa = env.config("web-backend"), env.config("web-qa")
    assert be["memory"]["memory_enabled"] is True and be["memory"]["user_profile_enabled"] is True
    assert "memory" in be["platform_toolsets"]["cli"] and "memory" not in be["agent"]["disabled_toolsets"]
    assert qa["memory"]["memory_enabled"] is False and "memory" in qa["agent"]["disabled_toolsets"]
    enables = [c["args"] for c in env.calls() if c["args"][:2] == ["tools", "enable"] and c.get("profile") == "web-backend"]
    assert not enables or "memory" in enables[-1]


def test_every_shipped_soul_says_what_its_memory_holds():
    souls = [REPO / "SOUL.md", *(REPO / "squads").glob("*/souls/*.md")]
    assert souls
    for soul in souls:
        lines = [ln for ln in soul.read_text().splitlines() if ln.startswith("Your memory holds")]
        assert len(lines) == 1 and "secret" in lines[0], soul


def test_changed_squad_skill_is_recopied_only_when_sha_differs(web, capsys):
    (web.src / "squads" / "web" / "skills" / "site-contract" / "SKILL.md").write_text("---\nname: site-contract\n---\nv2\n")
    _, out = web.run("apply", "web", capsys=capsys)
    assert out["summary"] == {"changed": 4, "unchanged": 1} or out["summary"].get("changed", 0) >= 4
    for bot in ("web-frontend", "web-qa"):
        assert "v2" in (web.root / "profiles" / bot / "skills" / "squad-web" / "site-contract" / "SKILL.md").read_text()
    _, again = web.run("apply", "web", capsys=capsys)
    assert again["summary"] == {"unchanged": 5}


def test_official_keep_installs_once_and_hub_lock_is_respected(env, capsys):
    env.squad("web")
    env.run("apply", "web", capsys=capsys)
    installs = [c["args"] for c in env.calls() if c["args"][:2] == ["skills", "install"]]
    assert ["skills", "install", "official/software-development/grill-me", "--yes"] in installs
    assert ["skills", "install", "official/web-development/publish-site", "--yes"] in installs
    n = len(installs)
    env.run("apply", "web", capsys=capsys)
    assert len([c for c in env.calls() if c["args"][:2] == ["skills", "install"]]) == n


def test_confirm_gated_keep_and_plugin(env, capsys):
    def gate(spec):
        spec["bots"]["web-qa"]["skills"]["keep"].append(
            {"id": "hub:skills-sh/acme/skills/remotion", "confirm": "Remotion needs a company licence from 4 people"})
        spec["bots"]["web-qa"]["plugins"]["enable"].append(
            {"name": "blender", "confirm": "Runs arbitrary Python inside Blender; needs Blender 5.1"})
    env.squad("web", gate)
    _, out = env.run("apply", "web", capsys=capsys)
    qa = next(b for b in out["bots"] if b["bot"] == "web-qa")
    assert len(qa["pending"]) == 2 and "Remotion" in qa["pending"][0]
    installs = [c["args"] for c in env.calls() if c["args"][:2] in (["skills", "install"], ["plugins", "install"])]
    assert not any("remotion" in " ".join(a) or "blender" in a for a in installs)
    _, out = env.run("apply", "web", "--confirm", "hub:skills-sh/acme/skills/remotion", "--confirm", "blender",
                     capsys=capsys)
    qa = next(b for b in out["bots"] if b["bot"] == "web-qa")
    assert "pending" not in qa
    assert any(a.startswith("skills install skills-sh/acme/skills/remotion") for a in qa["actions"])
    assert "plugins install --enable blender" in qa["actions"]
    assert "blender" in env.config("web-qa")["plugins"]["enabled"]


def test_yes_is_accepted_and_never_bypasses_confirm_gates(env, capsys):
    def gate(spec):
        spec["bots"]["web-qa"]["plugins"]["enable"].append(
            {"name": "blender", "confirm": "Runs arbitrary Python inside Blender; needs the user's OK"})
    env.squad("web", gate)
    _, out = env.run("apply", "web", capsys=capsys)
    qa = next(b for b in out["bots"] if b["bot"] == "web-qa")
    assert len(qa["pending"]) == 1 and "blender" in qa["pending"][0]
    assert not any(c["args"][:2] == ["plugins", "install"] for c in env.calls())


def test_plain_plugin_that_is_not_bundled_is_refused(env, capsys):
    env.squad("web", lambda s: s["bots"]["web-qa"]["plugins"]["enable"].append("community-thing"))
    shutil.rmtree(env.hsrc / "plugins" / "community-thing")
    _, out = env.run("apply", "web", expect=1, capsys=capsys)
    assert "community-thing" in out["error"] and "confirm" in out["error"]


def test_plugin_install_passes_yes_deps_so_the_plugin_ends_up_enabled(env, capsys):
    def gate(spec):
        spec["bots"]["web-qa"]["plugins"]["enable"].append(
            {"name": "blender", "confirm": "Runs arbitrary Python inside Blender; needs the user's OK"})
    env.squad("web", gate)
    env.run("apply", "web", "--bots", "web-qa", "--confirm", "blender", capsys=capsys)
    installs = [c["args"] for c in env.calls() if c["args"][:2] == ["plugins", "install"]]
    assert ["plugins", "install", "blender", "--enable", "--yes-deps"] in installs
    assert "blender" in env.config("web-qa")["plugins"]["enabled"]


def test_mcp_add_fails_loudly_when_the_server_does_not_land_enabled(env, capsys, monkeypatch):
    """`mcp add` must not end in "Cancelled." with exit 0: nothing saved, nothing reported, apply green."""
    monkeypatch.setenv("FAKE_MCP_PROBE_FAIL", "chrome-devtools")
    env.squad("web")
    _, out = env.run("apply", "web", "--bots", "web-qa", expect=1, capsys=capsys)
    assert "chrome-devtools" in out["error"] and "did not land enabled" in out["error"]
    assert "hermes -p web-qa mcp add chrome-devtools" in out["error"]
    # The server hermes did save (disabled) stays visible as an owner item on every later run.
    mark = len(env.calls())
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    assert env.config("web-qa")["mcp_servers"]["chrome-devtools"]["enabled"] is False
    assert any("chrome-devtools" in p and "saved disabled" in p for p in qa["pending"])
    assert "mcp add chrome-devtools" not in qa["actions"]  # a saved-disabled server is never re-added blindly
    assert not any(c["args"][:2] == ["mcp", "add"] for c in env.calls()[mark:])


def test_mcp_add_answers_the_auth_prompt_before_the_tool_picker(env, capsys):
    """An HTTP server asks "requires authentication?" first, so the answers must be ordered (n, then y)."""
    env.squad("web", lambda s: s["bots"]["web-qa"].update(mcp={"remote": {"url": "https://mcp.example.com/mcp"}}))
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    assert "mcp add remote" in qa["actions"]
    assert env.config("web-qa")["mcp_servers"]["remote"]["enabled"] is True


def test_missing_bundled_keep_is_an_error(env, capsys):
    env.squad("web")
    shutil.rmtree(env.hsrc / "skills" / "cat" / "claude-design")
    _, out = env.run("apply", "web", capsys=capsys, expect=1)
    assert "bundled skill not found" in out["error"]


def test_skip_skills_leaves_skills_alone(env, capsys):
    env.squad("web")
    _, out = env.run("apply", "web", "--skip-skills", capsys=capsys)
    assert not (env.root / "profiles" / "web-qa" / "skills" / "squad-web").exists()
    assert not any(c["args"][:2] == ["skills", "install"] for c in env.calls())


# --- cron -------------------------------------------------------------------------------------------------------

def test_cron_changes_are_edited_and_unlisted_jobs_removed(web, capsys):
    def bump(spec):
        spec["bots"]["web"]["cron"]["web-watch"]["schedule"] = "0 9 * * *"
    web.squad("web", bump)
    _, out = web.run("apply", "web", capsys=capsys)
    (lead,) = [b for b in out["bots"] if b["bot"] == "web"]
    assert lead["actions"] == ["cron ~ web-watch"]
    assert web.jobs("web")[0]["schedule"]["expr"] == "0 9 * * *"
    web.squad("web", lambda s: s["bots"]["web"].update(cron={}))
    _, out = web.run("apply", "web", capsys=capsys)
    assert web.jobs("web") == []


def test_unrelated_cron_jobs_are_never_removed(web, capsys):
    jobs = web.root / "profiles" / "web" / "cron" / "jobs.json"
    data = json.loads(jobs.read_text())
    data["jobs"].append({"id": "keepme", "name": "personal-digest", "script": "x.py", "no_agent": True})
    jobs.write_text(json.dumps(data))
    _, out = web.run("apply", "web", capsys=capsys)
    assert out["summary"] == {"unchanged": 5}
    assert {j["name"] for j in web.jobs("web")} == {"web-watch", "personal-digest"}


def test_cron_args_get_a_wrapper(env, capsys):
    def args(spec):
        spec["bots"]["web"]["cron"]["web-watch"]["args"] = "--board web --quiet"
    env.squad("web", args)
    env.run("apply", "web", capsys=capsys)
    (job,) = env.jobs("web")
    assert job["script"] == "web-watch.sh"
    wrapper = env.root / "profiles" / "web" / "scripts" / "web-watch.sh"
    assert wrapper.read_text() == '#!/usr/bin/env bash\nexec python3 "$(dirname "$0")/board_watch.py" --board web --quiet\n'
    assert os.access(wrapper, os.X_OK)
    _, out = env.run("apply", "web", capsys=capsys)
    assert out["summary"] == {"unchanged": 5}


def test_a_gate_that_imports_gate_lib_gets_it_beside_it(env, capsys):
    env.squad("web")
    (env.src / "squads" / "web" / "scripts" / "board_watch.py").write_text("import gate_lib\nprint('{}')\n")
    env.run("apply", "web", capsys=capsys)
    scripts = env.root / "profiles" / "web" / "scripts"
    assert (scripts / "gate_lib.py").read_text() == (SCRIPTS / "gate_lib.py").read_text()
    _, out = env.run("apply", "web", capsys=capsys)
    assert out["summary"] == {"unchanged": 5}


# --- builder ----------------------------------------------------------------------------------------------------

def test_apply_self_creates_builder_watch_on_the_digest_lane(env, capsys):
    env.squad("builder", lambda s: s["bots"]["builder"]["cron"]["builder-watch"].update(script="watch_upstream.py"))
    env.seed_builder()
    _, out = env.run("apply", "--self", capsys=capsys)
    assert out["squad"] == "builder" and out["board"] == "none" and out["summary"] == {"changed": 1}
    home = env.root / "profiles" / "builder"
    assert (home / ".no-bundled-skills").exists() and not (home / "skills" / "bundled-demo").exists()
    for skill in ("hermes-platform", "installing-squads"):
        assert (home / "skills" / skill / "SKILL.md").is_file()
    assert env.config("builder")["terminal"]["cwd"] == str(home)
    update, job = sorted(env.jobs("builder"), key=lambda j: j["name"])
    assert (update["name"], update["no_agent"], update["script"]) == ("builder-update", True, "auto_update.py")
    assert (job["name"], job["no_agent"], job["deliver"]) == ("builder-watch", False, "bot-chat:builder")
    assert job["script"] == "watch_upstream.py"  # no args, so no wrapper script
    assert (job["model"], job["provider"], job["reasoning_effort"], job["skills"]) == (
        "model-digest", "prov-digest", "high", ["tracking-updates"])
    meta = yaml.safe_load((home / "profile.yaml").read_text())["ui_meta"]["hermes-bots"]
    assert meta == {"title": "Builder", "hidden": False, "sectionId": "managers", "sectionName": "Managers", "squadName": "Builder"}
    assert not any(c["args"][:2] == ["profile", "create"] for c in env.calls())
    _, again = env.run("apply", "--self", capsys=capsys)
    assert again["summary"] == {"unchanged": 1}


def test_apply_self_installs_no_squad(env, capsys):
    """"set me up" applies the builder only: every squad stays opt-in until the user picks it."""
    env.squad("builder", lambda s: s["bots"]["builder"]["cron"]["builder-watch"].update(script="watch_upstream.py"))
    env.seed_builder()
    env.run("apply", "--self", capsys=capsys)
    profiles = sorted(p.name for p in (env.root / "profiles").iterdir() if p.is_dir())
    assert profiles == ["builder"]
    assert not any(c["args"][:2] == ["profile", "create"] for c in env.calls())
    _, st = env.run("status", capsys=capsys)
    assert st["installed"] == 1 and [s["squad"] for s in st["squads"]] == ["builder"]


def _hub_enables(env, name):
    return [c["args"] for c in env.calls() if c["args"][:3] == ["plugins", "enable", "squad-hub"] and c.get("profile") == name]


def test_every_manager_carries_squad_hub_and_runs_its_agent_half(env, capsys):
    """A manager talks to the user: it gets the package (the desktop half rides along, opt-in in Desktop) and its
    agent half enabled, so it asks with suggested answers. A worker never does: nobody answers a worker."""
    env.squad("builder", lambda s: s["bots"]["builder"]["cron"]["builder-watch"].update(script="watch_upstream.py"))
    env.seed_builder()
    env.run("apply", "--self", capsys=capsys)
    pkg = REPO / "squads" / "_plugins" / "squad-hub"
    home = env.root / "profiles" / "builder"
    for rel in ("plugin.yaml", "__init__.py", "desktop/plugin.js"):
        assert (home / "plugins" / "squad-hub" / rel).read_text() == (pkg / rel).read_text(), rel
    assert _hub_enables(env, "builder"), "the builder's agent half is enabled"
    env.squad("web")
    env.run("apply", "web", capsys=capsys)
    assert (env.root / "profiles" / "web" / "plugins" / "squad-hub" / "__init__.py").is_file()
    assert _hub_enables(env, "web")
    for worker in ("web-qa", "web-frontend"):
        assert not (env.root / "profiles" / worker / "plugins" / "squad-hub").exists(), worker
        assert not _hub_enables(env, worker), worker


def test_squad_hub_apply_restores_an_edit_and_a_second_apply_changes_nothing(env, capsys):
    env.squad("builder", lambda s: s["bots"]["builder"]["cron"]["builder-watch"].update(script="watch_upstream.py"))
    env.seed_builder()
    env.run("apply", "--self", capsys=capsys)
    assert "squad-hub" in env.config("builder")["plugins"]["enabled"], "the fake enable wrote it, as hermes does"
    js = env.root / "profiles" / "builder" / "plugins" / "squad-hub" / "desktop" / "plugin.js"
    js.write_text("// edited by hand\n")
    _, out = env.run("apply", "--self", capsys=capsys)
    assert out["summary"] == {"changed": 1}
    assert js.read_text() == (REPO / "squads" / "_plugins" / "squad-hub" / "desktop" / "plugin.js").read_text()
    n = len(env.calls())
    _, again = env.run("apply", "--self", capsys=capsys)
    assert again["summary"] == {"unchanged": 1}, "a second apply copies and enables nothing"
    assert not [c for c in env.calls()[n:] if c["args"][:2] == ["plugins", "enable"]]


def test_a_manager_that_opts_out_of_squad_hub_stays_off(env, capsys):
    """A manager that lists squad-hub under plugins.disable keeps it off on every apply, never flipping back on."""
    env.squad("web")
    env.run("apply", "web", capsys=capsys)
    assert _hub_enables(env, "web")

    def opt_out(spec):
        spec["bots"]["web"].setdefault("plugins", {})["disable"] = ["squad-hub"]
    env.squad("web", opt_out)
    n = len(env.calls())
    env.run("apply", "web", capsys=capsys)
    calls = [c["args"] for c in env.calls()[n:] if c.get("profile") == "web"]
    assert ["plugins", "disable", "squad-hub"] in calls
    assert not [c for c in calls if c[:3] == ["plugins", "enable", "squad-hub"]]
    n = len(env.calls())
    env.run("apply", "web", capsys=capsys)
    assert not [c["args"] for c in env.calls()[n:] if c.get("profile") == "web" and c["args"][:3] == ["plugins", "enable", "squad-hub"]], \
        "an opted-out manager stays off: apply never alternates"


def test_a_worker_that_still_runs_squad_hub_gets_it_disabled(env, capsys):
    """A bot moved from manager to worker keeps a stale squad-hub enable on disk; apply turns it off so the worker
    stops asking the user."""
    env.squad("web")
    env.run("apply", "web", capsys=capsys)
    cfg = env.config("web-qa")
    cfg.setdefault("plugins", {}).setdefault("enabled", []).append("squad-hub")
    (env.root / "profiles" / "web-qa" / "config.yaml").write_text(yaml.safe_dump(cfg))
    n = len(env.calls())
    env.run("apply", "web", capsys=capsys)
    assert ["plugins", "disable", "squad-hub"] in [c["args"] for c in env.calls()[n:] if c.get("profile") == "web-qa"]


def test_agent_cron_is_pinned_and_doctor_warns_on_an_unpinned_one(env, capsys):
    """Every agent cron squadctl writes carries --model/--provider (an unpinned job follows the main model at fire
    time); doctor flags a squad agent job that lost its pin, and the next apply restores it."""
    env.squad("builder", lambda s: s["bots"]["builder"]["cron"]["builder-watch"].update(script="watch_upstream.py"))
    env.seed_builder()
    env.run("apply", "--self", capsys=capsys)
    create = next(c["args"] for c in env.calls() if c["args"][:2] == ["cron", "create"] and "builder-watch" in c["args"])
    assert create[create.index("--model") + 1] == "model-digest"
    assert create[create.index("--provider") + 1] == "prov-digest"
    path = env.root / "profiles" / "builder" / "cron" / "jobs.json"
    data = json.loads(path.read_text())
    watch = next(j for j in data["jobs"] if j["name"] == "builder-watch")
    watch["model"] = watch["provider"] = None
    path.write_text(json.dumps(data))
    _, doc = env.run("doctor", "builder", expect=None, capsys=capsys)
    (warn,) = [c for c in doc["checks"] if c["check"] == "builder:cron:builder-watch"]
    assert warn["status"] == "warn" and "no model pin" in warn["detail"]
    _, out = env.run("apply", "--self", capsys=capsys)
    assert "cron ~ builder-watch" in out["bots"][0]["actions"]
    assert next(j for j in env.jobs("builder") if j["name"] == "builder-watch")["model"] == "model-digest"
    _, doc = env.run("doctor", "builder", expect=None, capsys=capsys)
    assert not [c for c in doc["checks"] if c["check"].startswith("builder:cron:")]


def test_apply_self_needs_the_installed_profile(env, capsys):
    env.squad("builder", lambda s: s["bots"]["builder"]["cron"]["builder-watch"].update(script="watch_upstream.py"))
    _, out = env.run("apply", "--self", expect=1, capsys=capsys)
    assert "hermes profile install" in out["error"]


def test_apply_self_uses_the_profile_name_from_the_builder_flag(env, capsys):
    """`hermes profile install <src> --name builder-test` is a supported install; builder.yaml names the bot
    `builder`, so `--builder builder-test` must reconcile that profile, not create one named `builder`."""
    env.squad("builder")
    home = env.root / "profiles" / "builder-test"
    (home / "skills").mkdir(parents=True)
    (home / "config.yaml").write_text("model: {default: seed}\n")
    argv = ["apply", "--self", "--builder", "builder-test", "--json", "--hermes-root", str(env.root),
            "--src", str(env.src), "--local", str(env.local), "--models", str(env.models)]
    assert squadctl.main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert [b["bot"] for b in out["bots"]] == ["builder-test"] and out["summary"] == {"changed": 1}
    assert (home / "skills" / "hermes-platform" / "SKILL.md").is_file()
    assert not (env.root / "profiles" / "builder" / "config.yaml").exists()  # no profile was created there
    jobs = {j["name"]: j for j in env.jobs("builder-test")}
    assert sorted(jobs) == ["builder-update", "builder-watch"]
    assert {j["deliver"] for j in jobs.values()} == {"bot-chat:builder-test"}
    assert env.config("builder-test")["terminal"]["cwd"] == str(home)
    assert not any(c["args"][:2] == ["profile", "create"] for c in env.calls())


def test_builder_version_comes_from_distribution_yaml(env, capsys):
    """One source of truth (C-13): the builder manifest is versionless and status reads distribution.yaml."""
    env.squad("builder")
    assert "version" not in yaml.safe_load((env.src / "builder.yaml").read_text())
    (env.src / "distribution.yaml").write_text(yaml.safe_dump({"name": "builder", "version": "9.9.9"}))
    env.seed_builder()
    env.run("apply", "--self", capsys=capsys)
    installed = yaml.safe_load((env.local / "installed.yaml").read_text())
    assert installed["squads"]["builder"]["version"] == "9.9.9"
    _, out = env.run("status", "builder", capsys=capsys)
    assert out["squads"][0]["repo"] == "9.9.9"


def test_a_squad_manifest_still_carries_its_version(env, capsys):
    """Only the builder manifest is versionless; a squad without one is invalid."""
    env.squad("web", mutate=lambda d: d.pop("version"))
    _, out = env.run("plan", "web", expect=1, capsys=capsys)
    assert "missing version" in out["error"]


# --- uninstall --------------------------------------------------------------------------------------------------

def test_uninstall_backs_up_removes_cron_deletes_profiles_archives_board(web, capsys):
    secret = web.root / "profiles" / "web-deployer" / ".env"
    secret.write_text("TOKEN=super-secret-value\n")
    (web.root / "profiles" / "web-deployer" / "auth.json").write_text('{"k":"super-secret-value"}')
    _, out = web.run("uninstall", "web", capsys=capsys)
    assert out["projects"] == "untouched" and out["board"] == "archive web"
    backups = sorted((web.local / "backups").glob("*.tar.gz"))
    assert len(backups) == 5
    with tarfile.open(next(b for b in backups if "web-deployer" in b.name)) as tf:
        assert not any(Path(n).name in (".env", "auth.json") for n in tf.getnames())
    assert list((web.root / "profiles").glob("web*")) == []
    assert json.loads((web.root / "boards.json").read_text())[0]["archived"] is True
    assert "web" not in yaml.safe_load((web.local / "installed.yaml").read_text())["squads"]
    assert any(c["args"][:2] == ["cron", "remove"] for c in web.calls())
    assert not any("--delete" in c["args"] for c in web.calls())


def test_uninstall_keep_profiles_removes_cron_only(web, capsys):
    _, out = web.run("uninstall", "web", "--keep-profiles", "--yes", capsys=capsys)
    assert len(list((web.root / "profiles").glob("web*"))) == 5
    assert web.jobs("web") == []
    assert len(list((web.local / "backups").glob("*.tar.gz"))) == 5
    assert not any(c["args"][:2] == ["profile", "delete"] for c in web.calls())


def test_uninstall_yes_flag_is_accepted(web, capsys):
    _, out = web.run("uninstall", "web", "--keep-profiles", capsys=capsys)
    assert len(list((web.root / "profiles").glob("web*"))) == 5
    assert web.jobs("web") == []


def test_uninstall_dry_run_changes_nothing(web, capsys):
    before = tree_hash(web.root)
    _, out = web.run("uninstall", "web", "--dry-run", capsys=capsys)
    assert tree_hash(web.root) == before
    assert out["bots"][0]["actions"] == ["profile export", "cron - web-watch", "profile delete"]


def test_uninstall_refuses_the_builder(env, capsys):
    env.squad("builder")
    _, out = env.run("uninstall", "builder", expect=1, capsys=capsys)
    assert "builder" in out["error"]


def test_reapply_after_uninstall_recreates_everything(web, capsys):
    web.run("uninstall", "web", capsys=capsys)
    _, out = web.run("apply", "web", capsys=capsys)
    assert out["summary"] == {"created": 5} and out["board"] == "created"


# --- project, chain ---------------------------------------------------------------------------------------------

def test_project_add_reaches_every_profile_once(web, tmp_path, capsys):
    site = tmp_path / "toy-site"
    site.mkdir()
    _, out = web.run("project", "add", "web", "Toy Site", str(site), capsys=capsys)
    assert [r["result"] for r in out["bots"]] == ["created"] * 5 and out["project"] == "toy-site"
    for bot in WEB_BOTS:
        assert "toy-site" in (web.root / "profiles" / bot / "projects.txt").read_text()
        assert "board=web" in (web.root / "profiles" / bot / "projects.txt").read_text()
    created = [c for c in web.calls() if c["args"][:2] == ["project", "create"]]
    assert {c["profile"] for c in created} == set(WEB_BOTS)
    assert all(c["args"][2:5] == ["Toy Site", str(site), "--slug"] for c in created)
    _, again = web.run("project", "add", "web", "Toy Site", str(site), capsys=capsys)
    assert [r["result"] for r in again["bots"]] == ["exists"] * 5
    proj = yaml.safe_load((web.local / "installed.yaml").read_text())["projects"]["toy-site"]
    assert proj == {"name": "Toy Site", "path": str(site), "squads": ["web"]}


def test_project_add_reports_missing_profiles_and_bad_paths(env, tmp_path, capsys):
    env.squad("web")
    (tmp_path / "site").mkdir()
    code, out = env.run("project", "add", "web", "Site", str(tmp_path / "site"), expect=1, capsys=capsys)
    assert {r["result"] for r in out["bots"]} == {"profile missing"}
    _, err = env.run("project", "add", "web", "Site", str(tmp_path / "nope"), expect=1, capsys=capsys)
    assert "not a directory" in err["error"]


def test_project_add_dry_run(web, tmp_path, capsys):
    (tmp_path / "s").mkdir()
    before = tree_hash(web.root)
    _, out = web.run("project", "add", "web", "S", str(tmp_path / "s"), "--dry-run", capsys=capsys)
    assert {r["result"] for r in out["bots"]} == {"would-create"} and tree_hash(web.root) == before


def test_chain_dry_run_filters_conditional_stages(env, capsys, monkeypatch):
    env.squad("web")
    monkeypatch.setitem(sys.modules, "kanban_chain", None)  # force the stub path
    _, plain = env.run("chain", "web", "milestone", "--project", "toy", "--title", "M1", "--dry-run", capsys=capsys)
    assert plain["executor"] == "stub"
    assert [c["stage"] for c in plain["cards"]] == ["ui", "preview", "qa", "accept"]
    _, withapi = env.run("chain", "web", "milestone", "--project", "toy", "--title", "M1", "--when", "backend",
                         "--dry-run", capsys=capsys)
    assert [c["stage"] for c in withapi["cards"]] == ["api", "ui", "preview", "qa", "accept"]
    assert withapi["cards"][1]["parent"] == "api" and withapi["cards"][0]["parent"] == "-"


def test_chain_without_the_module_refuses_a_real_run(env, capsys, monkeypatch):
    env.squad("web")
    monkeypatch.setitem(sys.modules, "kanban_chain", None)
    _, out = env.run("chain", "web", "milestone", "--project", "toy", "--title", "M1", expect=3, capsys=capsys)
    assert "kanban_chain" in out["error"]


def test_chain_delegates_to_kanban_chain_and_is_idempotent(web, tmp_path, capsys):
    (tmp_path / "s").mkdir()
    web.run("project", "add", "web", "Toy", str(tmp_path / "s"), capsys=capsys)
    args = ("chain", "web", "milestone", "--project", "toy", "--title", "M1", "--when", "backend")
    _, dry = web.run(*args, "--dry-run", capsys=capsys)
    assert dry["dry_run"] is True and dry["board"] == "web" and dry["manager"] == "web"
    assert [c["stage"] for c in dry["cards"]] == ["api", "ui", "preview", "qa", "accept"]
    _, first = web.run(*args, capsys=capsys)
    _, second = web.run(*args, capsys=capsys)
    ids = [c["id"] for c in first["cards"]]
    assert ids == [c["id"] for c in second["cards"]] and len(set(ids)) == 5
    cards = json.loads((web.root / "cards-web.json").read_text())
    assert len(cards) == 5 and all(c["project"] == "toy" for c in cards.values())
    assert [c["profile"] for c in web.calls() if c["args"][:3] == ["kanban", "--board", "web"]
            and c["args"][3] == "create"] == ["web"] * 10


def test_chain_unknown_name(env, capsys):
    env.squad("web")
    _, out = env.run("chain", "web", "nope", "--project", "p", "--title", "t", expect=1, capsys=capsys)
    assert "chains: onboarding, milestone" in out["error"]


# --- status, doctor ---------------------------------------------------------------------------------------------

def test_status_empty_and_installed(env, capsys):
    env.squad("web")
    _, out = env.run("status", capsys=capsys)
    assert out == {"installed": 0, "available": ["web"], "squads": []}
    env.run("apply", "web", capsys=capsys)
    _, out = env.run("status", capsys=capsys)
    (squad,) = out["squads"]
    assert squad["installed"] == "3.1.1" and squad["board"] == "exists"
    assert [b["state"] for b in squad["bots"]] == ["ok"] * 5
    assert squad["bots"][1]["model"] == "model-frontend"


def test_status_shows_drift_and_missing(web, capsys):
    cfg = web.root / "profiles" / "web-qa" / "config.yaml"
    data = yaml.safe_load(cfg.read_text())
    data["model"]["default"] = "x"
    cfg.write_text(yaml.safe_dump(data))
    shutil.rmtree(web.root / "profiles" / "web-deployer")
    _, out = web.run("status", "web", capsys=capsys)
    states = {b["bot"]: b["state"] for b in out["squads"][0]["bots"]}
    assert states["web-qa"] == "drift" and states["web-deployer"] == "missing" and states["web"] == "ok"


def test_doctor_reports_checks_and_never_prints_env_values(web, capsys, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_supersecretvalue")
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    _, out = web.run("doctor", capsys=capsys)
    checks = {c["check"]: c for c in out["checks"]}
    assert checks["hermes"]["status"] == "ok" and checks["gateway"]["status"] == "ok"
    assert checks["desktop-kanban"]["status"] == "info"
    assert checks["web:cards"]["detail"] == "no stale cards"
    assert "ghp_supersecretvalue" not in json.dumps(out)


def test_doctor_reports_required_apps_and_their_logins(web, capsys, monkeypatch):
    """D-036: a required CLI is reported twice — installed, and logged in — with no probe output in the check."""
    monkeypatch.setattr(squadctl, "app_problem", lambda spec: None)
    monkeypatch.setattr(squadctl, "find_app", lambda spec: (f"/usr/local/bin/{spec}", "9.9.9"))
    monkeypatch.setattr(squadctl, "login_probe", lambda name: ("warn", f"not logged in: run `{name} login` once"))
    _, out = web.run("doctor", capsys=capsys)
    checks = {c["check"]: c for c in out["checks"]}
    assert checks["web-deployer:app:cf"]["detail"] == "/usr/local/bin/cf 9.9.9"
    assert checks["web-deployer:app:wrangler"]["status"] == "ok"
    assert [checks[f"web-deployer:login:{a}"]["status"] for a in ("cf", "wrangler", "gh")] == ["warn"] * 3
    assert checks["web-deployer:login:gh"]["detail"] == "not logged in: run `gh login` once"
    assert "web-deployer:app:vercel" not in checks, "only the apps the bot declares are reported"


def test_app_launcher_prefers_path_then_npx(tmp_path, monkeypatch):
    """A required npm CLI that is not on PATH is still real when `npx --no-install` can run it (no download)."""
    npx = tmp_path / "npx"
    npx.write_text("#!/bin/sh\nexit 0\n")
    npx.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setattr(squadctl, "run_quiet",
                        lambda argv, timeout=60: subprocess.CompletedProcess(argv, 0, "4.1.0\n", ""))
    assert squadctl.app_launcher("wrangler") == ["npx", "--no-install", "wrangler"]
    assert squadctl.app_launcher("cf") == ["npx", "--no-install", "cf"]
    assert squadctl.app_launcher("gh") is None, "gh is not npm-packaged: no npx fallback"
    calls = []

    def no_copy(argv, timeout=60):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 1, "", "npx canceled")
    monkeypatch.setattr(squadctl, "run_quiet", no_copy)
    assert squadctl.app_launcher("wrangler") == ["npx", "wrangler"], "no local copy: npx downloads it on first use"
    assert squadctl.app_problem("cf") is None
    assert "downloaded on first use" in squadctl.app_problem("wrangler>=4")
    status, detail = squadctl.login_probe("cf")
    assert status == "info" and "npx cf auth login" in detail
    assert all("--no-install" in c for c in calls), "doctor never runs the downloading form"
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert squadctl.app_launcher("wrangler") is None, "no npx at all"


def test_login_probe_reads_the_exit_status_only(monkeypatch):
    """No probe output reaches a check: `gh auth status` prints the account and a masked token."""
    calls = []

    def fake(argv, timeout=60):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0 if len(calls) == 1 else 1,
                                           "account x, token ghp_supersecretvalue\n", "")
    monkeypatch.setattr(squadctl, "run_quiet", fake)
    monkeypatch.setattr(squadctl, "app_launcher", lambda name: ["faketool"])
    monkeypatch.setitem(squadctl.APP_LOGINS, "faketool", (["whoami"], "faketool login"))
    assert squadctl.login_probe("faketool") == ("ok", "logged in")
    status, detail = squadctl.login_probe("faketool")
    assert calls == [["faketool", "whoami"]] * 2
    assert status == "warn" and "faketool login" in detail and "ghp_supersecretvalue" not in detail
    monkeypatch.setattr(squadctl, "app_launcher", lambda name: None)
    assert squadctl.login_probe("faketool")[0] == "info", "nothing to check when the app is not installed"
    assert squadctl.login_probe("no-probe-cli") == (
        "info", "no-probe-cli: no login check (no probe for this app, or it is not installed)")


def test_doctor_flags_a_missing_provider_plugin_and_filters_by_squad(env, capsys):
    """`doctor [<squad>]` answers for one squad: it loads no other squad's spec and flags a missing plugin."""
    plugin = env.root / "profiles" / "builder" / "plugins" / "model-providers" / "prov-frontend"
    plugin.mkdir(parents=True)
    (plugin / "plugin.yaml").write_text("name: prov-frontend\nkind: model-provider\n")
    env.squad("web")
    env.run("apply", "web", "--bots", "web", capsys=capsys)  # the lead only: no copy has happened yet
    installed = yaml.safe_load(env.local.joinpath("installed.yaml").read_text())
    installed["squads"]["jobs"] = {"version": "1.0.0"}
    env.local.joinpath("installed.yaml").write_text(yaml.safe_dump(installed))
    _, out = env.run("doctor", "web", capsys=capsys)
    checks = {c["check"]: c for c in out["checks"]}
    assert "web-frontend:provider-plugin" in checks, sorted(checks)
    assert "apply copies" in checks["web-frontend:provider-plugin"]["detail"]
    assert not any(c["check"].startswith("jobs") for c in out["checks"])
    _, all_out = env.run("doctor", expect=1, capsys=capsys)  # jobs has no spec: only the unfiltered run fails
    assert any(c["check"] == "jobs:spec" and c["status"] == "fail" for c in all_out["checks"])
    _, out = env.run("doctor", "nope", expect=1, capsys=capsys)
    assert "is not installed" in out["error"]


def test_doctor_warns_about_missing_models(env, capsys):
    env.squad("web")
    env.run("apply", "web", "--bots", "web", capsys=capsys)
    env.local.joinpath("installed.yaml").write_text(yaml.safe_dump({"squads": {"web": {"version": "3.0.0"}}}))
    _, out = env.run("doctor", capsys=capsys)
    assert any(c["status"] == "warn" and "no model assigned" in c["detail"] for c in out["checks"])


def test_doctor_reports_the_jobs_project_and_profile_md(env, tmp_path, capsys):
    """start_search.py is silent without a project or profile.md; doctor is where that gap shows."""
    env.squad("jobs")
    env.local.mkdir(parents=True, exist_ok=True)
    env.local.joinpath("installed.yaml").write_text(yaml.safe_dump({"squads": {"jobs": {"version": "1.0.0"}}}))
    _, out = env.run("doctor", capsys=capsys)
    checks = {c["check"]: c for c in out["checks"]}
    assert checks["jobs:project"]["status"] == "warn" and "+ in Desktop Sessions" in checks["jobs:project"]["detail"]
    folder = tmp_path / "search"
    folder.mkdir()
    env.local.joinpath("installed.yaml").write_text(yaml.safe_dump({
        "squads": {"jobs": {"version": "1.0.0"}},
        "projects": {"search": {"name": "Search", "path": str(folder), "squads": ["jobs"]}}}))
    _, out = env.run("doctor", capsys=capsys)
    checks = {c["check"]: c for c in out["checks"]}
    assert checks["jobs:project"]["status"] == "ok"
    assert checks["jobs:profile.md"]["status"] == "warn" and str(folder) in checks["jobs:profile.md"]["detail"]
    (folder / "profile.md").write_text("---\nsearch: active\n---\n")
    _, out = env.run("doctor", capsys=capsys)
    assert {c["check"]: c for c in out["checks"]}["jobs:profile.md"]["status"] == "ok"


# --- units, output, shim ----------------------------------------------------------------------------------------

def test_toon_encodes_tables_lists_and_blocks():
    lines = squadctl.toon({"squad": "web", "ok": True, "n": 5, "none": None, "tags": ["a", "b"], "empty": [],
                           "bots": [{"bot": "x", "status": "ok"}, {"bot": "y", "status": "drift"}],
                           "mixed": [{"bot": "x", "actions": ["a, b", "c"]}], "s": "a: b"})
    assert lines == ["squad: web", "ok: true", "n: 5", "none: null", "tags[2]: a,b", "empty[0]:",
                     "bots[2]{bot,status}:", "  x,ok", "  y,drift", "mixed[1]:", "  - bot: x",
                     "    actions[2]:", "      - a, b", "      - c", 's: "a: b"']


def test_default_output_is_toon_and_json_flag_switches(env, capsys):
    env.squad("web")
    argv = ["status", "--hermes-root", str(env.root), "--src", str(env.src), "--local", str(env.local)]
    assert squadctl.main(argv) == 0
    assert capsys.readouterr().out.splitlines()[:2] == ["installed: 0", "available[1]: web"]


def test_deep_merge_replaces_lists_merges_dicts_and_deletes_none():
    base = {"a": {"b": 1, "c": [1, 2]}, "bots": {"x": 1, "y": 2}}
    assert squadctl.deep_merge(base, {"a": {"c": [3]}, "bots": {"y": None, "z": 3}}) == {
        "a": {"b": 1, "c": [3]}, "bots": {"x": 1, "z": 3}}


def test_deep_merge_list_edits_keep_repo_list_updates_flowing():
    base = {"keep": ["a", {"id": "b", "confirm": "old"}, "c"], "enable": ["x"], "auto_load": None}
    over = {"keep_add": [{"id": "b", "confirm": "new"}, "d"], "keep_remove": ["c"], "enable_add": ["y"]}
    assert squadctl.deep_merge(squadctl.deep_merge(None, base), over) == {
        "keep": ["a", {"id": "b", "confirm": "new"}, "d"], "enable": ["x", "y"], "auto_load": None}
    # the repo later adds "e": the overlay's edits still apply on top of it
    base["keep"].append("e")
    assert squadctl.deep_merge(base, over)["keep"] == ["a", {"id": "b", "confirm": "new"}, "e", "d"]


def test_overlay_keep_add_and_enable_remove_follow_the_repo_lists(env, capsys):
    env.squad("web")
    overlay = env.local / "squads" / "web" / "squad.yaml"
    overlay.parent.mkdir(parents=True)
    overlay.write_text(yaml.safe_dump({"bots": {"web-qa": {
        "skills": {"keep_add": ["hub:skills-sh/acme/skills/extra-check"]},
        "plugins": {"enable_remove": ["disk-cleanup"]}}}}))
    repo = yaml.safe_load((env.src / "squads" / "web" / "squad.yaml").read_text())
    repo_keep = repo["bots"]["web-qa"]["skills"]["keep"]
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    assert any("skills install skills-sh/acme/skills/extra-check" in a for a in qa["actions"])
    assert sum(1 for a in qa["actions"] if a.startswith("skills install")) == 1 + sum(
        1 for k in repo_keep if (k if isinstance(k, str) else k["id"]).startswith(("hub:", "official:")))
    assert "disk-cleanup" not in (env.config("web-qa").get("plugins") or {}).get("enabled", [])
    assert not any("disk-cleanup" in a for a in qa["actions"])


def test_plan_notes_enabled_plugins_the_manifest_does_not_declare_and_keeps_them(env, capsys):
    """Declared = repo enable + overlay enable_add + the provider plugin key apply copies; the rest is a note."""
    plugin = env.root / "profiles" / "builder" / "plugins" / "model-providers" / "prov-review"
    plugin.mkdir(parents=True)
    (plugin / "plugin.yaml").write_text("name: prov-review\nkind: model-provider\n")
    env.squad("web")
    (env.hsrc / "plugins" / "extra-ok").mkdir(parents=True)
    overlay = env.local / "squads" / "web" / "squad.yaml"
    overlay.parent.mkdir(parents=True)
    overlay.write_text(yaml.safe_dump({"bots": {"web-qa": {"plugins": {"enable_add": ["extra-ok"]}}}}))
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    cfg = env.config("web-qa")
    assert "model-providers/prov-review" in cfg["plugins"]["enabled"]
    cfg["plugins"]["enabled"] += ["hand-made"]
    (env.root / "profiles" / "web-qa" / "config.yaml").write_text(yaml.safe_dump(cfg))
    _, out = env.run("plan", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    plug = [n for n in qa["notes"] if n.startswith("plugin ")]
    assert len(plug) == 1 and plug[0].startswith("plugin hand-made is enabled but not in the manifest; kept.")
    assert "hermes -p web-qa plugins disable hand-made" in plug[0]
    assert qa["status"] == "unchanged"
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    assert "hand-made" in env.config("web-qa")["plugins"]["enabled"]
    assert not any(c["args"][:2] == ["plugins", "disable"] for c in env.calls())


def test_plan_notes_profile_kanban_keys_the_dispatcher_never_reads(web, capsys):
    cfg = web.config("web-qa")
    cfg["kanban"] = {"max_in_progress_per_profile": 1, "failure_limit": 3, "auto_subscribe_on_create": False}
    (web.root / "profiles" / "web-qa" / "config.yaml").write_text(yaml.safe_dump(cfg))
    _, out = web.run("plan", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    kb = [n for n in qa["notes"] if n.startswith("kanban.")]
    assert [n.split(" ", 1)[0] for n in kb] == ["kanban.failure_limit", "kanban.max_in_progress_per_profile"]
    assert all("reads the root config only" in n and "hermes -p web-qa config unset kanban." in n for n in kb)
    assert qa["status"] == "unchanged"
    assert web.config("web-qa")["kanban"]["failure_limit"] == 3


def test_a_dropped_hub_keep_is_uninstalled_and_a_learned_hub_skill_stays(env, capsys):
    env.squad("web", lambda s: s["bots"]["web-qa"]["skills"]["keep"].append("hub:skills-sh/acme/skills/old-check"))
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    home = env.root / "profiles" / "web-qa"
    owned = json.loads((home / "skills" / ".squad-installed.json").read_text())
    assert "old-check" in owned["hub"]
    # the bot installed a hub skill of its own: never apply's to remove
    lock = home / "skills" / ".hub" / "lock.json"
    data = json.loads(lock.read_text())
    data["installed"]["mine"] = {"identifier": "skills-sh/me/mine"}
    lock.write_text(json.dumps(data))
    env.squad("web")  # the manifest drops old-check
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    assert "skills uninstall old-check (hub keep no longer in the manifest)" in qa["actions"]
    assert ["skills", "uninstall", "old-check", "--yes"] in [c["args"] for c in env.calls()]
    assert set(json.loads(lock.read_text())["installed"]) >= {"mine"} and "old-check" not in json.loads(lock.read_text())["installed"]
    _, again = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    assert again["summary"] == {"unchanged": 1}


def test_a_confirmed_installed_hub_keep_is_not_pending(env, capsys):
    gate = lambda s: s["bots"]["web-qa"]["skills"]["keep"].append(
        {"id": "hub:skills-sh/acme/skills/remotion", "confirm": "Remotion needs a company licence from 4 people"})
    env.squad("web", gate)
    env.run("apply", "web", "--bots", "web-qa", "--confirm", "hub:skills-sh/acme/skills/remotion", capsys=capsys)
    _, out = env.run("plan", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    assert not qa.get("pending") and qa["status"] == "unchanged"


def test_confirm_text_may_carry_a_full_disclosure(env, capsys):
    text = "Licence and data disclosure: " + "x" * 900
    env.squad("web", lambda s: s["bots"]["web-qa"]["plugins"]["enable"].append({"name": "blender", "confirm": text}))
    _, out = env.run("plan", "web", "--bots", "web-qa", capsys=capsys)
    assert any(p.startswith("plugin blender: Licence") for p in out["bots"][0]["pending"])


@pytest.mark.parametrize("req,have,ok", [(">=0.22.0", "0.22.0", True), (">=0.22.0", "0.21.9", False),
                                         (">=0.22", "0.22.1", True), (">1.0", "1.0.0", False), ("", "0.1.0", True)])
def test_version_ok(req, have, ok):
    assert squadctl.version_ok(req, have) is ok


def test_resolve_root(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "x" / "profiles" / "builder"))
    assert squadctl.resolve_root(None) == tmp_path / "x"
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "plain"))
    assert squadctl.resolve_root(None) == tmp_path / "plain"
    assert squadctl.resolve_root(str(tmp_path / "given")) == tmp_path / "given"
    monkeypatch.delenv("HERMES_HOME")
    assert squadctl.resolve_root(None) == Path.home() / ".hermes"


def test_sched_matches_intervals_and_cron():
    assert squadctl.sched_matches({"schedule": {"kind": "interval", "display": "every 120m"}}, "every 2h")
    assert squadctl.sched_matches({"schedule": {"expr": "0 8 * * *"}}, "0 8 * * *")
    assert not squadctl.sched_matches({"schedule": {"expr": "0 8 * * *"}}, "0 9 * * *")


def test_scripts_never_touch_the_auth_store_or_clone():
    """C-14 lets apply write the profile env file (name+value, value never shown); the auth store stays
    out of reach of every script, and no script may clone a profile."""
    for name in ("squadctl.py", "_profile_apply.py", "squadctl"):
        text = (SCRIPTS / name).read_text()
        assert "auth.json" not in text, name
        assert "--clone" not in text.replace("Never `--clone`", ""), name


def test_help_works_without_hermes_or_network(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    out = subprocess.run([sys.executable, str(SCRIPTS / "squadctl.py"), "--help"], capture_output=True, text=True,
                         env=env, timeout=30)
    assert out.returncode == 0 and "plan" in out.stdout and "uninstall" in out.stdout
    sub = subprocess.run([sys.executable, str(SCRIPTS / "squadctl.py"), "apply", "--help"], capture_output=True,
                         text=True, env=env, timeout=30)
    assert sub.returncode == 0 and "--dry-run" in sub.stdout and "--models" in sub.stdout


def test_profile_apply_help_and_ui_meta_merge():
    out = subprocess.run([sys.executable, str(SCRIPTS / "_profile_apply.py"), "--help"], capture_output=True,
                         text=True, timeout=30)
    assert out.returncode == 0 and "In-process config writer" in out.stdout
    import _profile_apply as pa
    first = pa.merge_ui_meta({"description": "d", "ui_meta": {"other": 1}}, {"title": "T", "hidden": True})
    assert first["ui_meta"] == {"other": 1, "hermes-bots": {"title": "T", "hidden": True}}
    assert first["_ui_meta_revisions"] == {"hermes-bots": 1}
    assert pa.merge_ui_meta(first, {"title": "T"}) is None
    assert pa.merge_ui_meta(first, {"title": "U"})["_ui_meta_revisions"] == {"hermes-bots": 2}
    assert pa.same(None, "") and pa.same("[1, 2]", [1, 2]) and not pa.same(None, "x")


def test_shim_runs_squadctl_with_an_explicit_interpreter(env):
    out = subprocess.run([str(SCRIPTS / "squadctl"), "status", "--json", "--hermes-root", str(env.root),
                          "--src", str(env.src), "--local", str(env.local)],
                         capture_output=True, text=True, timeout=60,
                         env={**os.environ, "SQUADCTL_PYTHON": sys.executable})
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == {"installed": 0, "available": [], "squads": []}
    assert subprocess.run(["bash", "-n", str(SCRIPTS / "squadctl")]).returncode == 0


def test_shim_uses_the_hermes_runtime_when_present(env):
    """The fake runtime launcher returns sys.executable plus the fake source root, as the real one does."""
    out = subprocess.run([str(SCRIPTS / "squadctl"), "status", "--json", "--hermes-root", str(env.root),
                          "--src", str(env.src), "--local", str(env.local)],
                         capture_output=True, text=True, timeout=60, env=os.environ)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout)["installed"] == 0


@real_hermes
def test_real_hermes_runtime_help(tmp_path):
    out = subprocess.run([str(SCRIPTS / "squadctl"), "--help"], capture_output=True, text=True, timeout=60,
                         env={"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]})
    assert out.returncode == 0 and "plan" in out.stdout


def test_every_bot_gets_the_hermes_base_and_a_worker_can_withhold(web):
    """Root fix: no bot loses web_search, terminal or delegation by accident; managers get the full base."""
    for bot in WEB_BOTS:
        cfg = web.config(bot)
        disabled = set(cfg["agent"]["disabled_toolsets"])
        assert not {"search", "desktop_ui", "project", "terminal", "delegation"} & disabled, bot
        soul = (web.root / "profiles" / bot / "SOUL.md").read_text()
        assert soul.startswith(FAKE_IDENTITY + "\n\nYou are one bot of a Hermes squad"), bot
    mgr = set(web.config("web")["platform_toolsets"]["cli"])
    assert {"terminal", "web", "browser", "delegation", "clarify", "cronjob", "code_execution"} <= mgr


def test_withhold_is_only_for_workers_and_known_toolsets(env, capsys):
    env.squad("web", lambda s: s["bots"]["web"].update(withhold=["terminal"]))
    _, out = env.run("plan", "web", expect=1, capsys=capsys)
    assert "cannot withhold" in out["error"]


def test_doctor_fails_a_bot_whose_web_search_is_disabled(web, capsys):
    cfg_path = web.root / "profiles" / "web-qa" / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["agent"]["disabled_toolsets"].append("search")
    cfg_path.write_text(yaml.safe_dump(cfg))
    _, out = web.run("doctor", capsys=capsys, expect=1)
    rows = {c["check"]: c for c in out["checks"]}
    assert rows["web-qa:web"]["status"] == "fail" and rows["web:web"]["status"] == "ok"


def test_apply_installs_the_managed_browser_once_a_bot_has_browser(web):
    assert any(c["args"][:3] == ["tools", "post-setup", "agent_browser"] for c in web.calls())


# --- projects ---------------------------------------------------------------------------------------------------

def test_apply_runs_project_sync_setup_for_a_squad_with_a_board(web, capsys):
    """After `apply <squad>`: no squad folder is imposed and no bot's Desktop repo scan is pinned to one."""
    assert not (web.home / "Projects").exists()
    for bot in WEB_BOTS:
        assert not (web.config(bot).get("desktop") or {}).get("repo_scan_roots"), bot
    _, out = web.run("apply", "web", capsys=capsys)
    assert out["summary"] == {"unchanged": 5}
    assert out["projects"]["ok"] and {b["result"] for b in out["projects"]["bots"]} == {"ok"}


def test_project_setup_keeps_a_custom_scan_list_and_plan_only_reports_it(env, capsys):
    env.squad("web")
    _, plan = env.run("plan", "web", capsys=capsys)
    assert plan["projects"].startswith("would run: ") and "--setup" in plan["projects"]
    assert not (env.home / "Projects").exists()
    env.run("apply", "web", "--bots", "web", capsys=capsys)
    subprocess.run(["hermes", "-p", "web", "config", "set", "desktop.repo_scan_roots", '["~/code"]'], check=True,
                   capture_output=True)
    _, out = env.run("apply", "web", "--bots", "web", capsys=capsys)
    (row,) = [b for b in out["projects"]["bots"] if b["bot"] == "web"]
    assert row["result"].startswith("custom repo_scan_roots kept")
    assert env.config("web")["desktop"]["repo_scan_roots"] == ["~/code"]


def test_apply_runs_the_project_sync_of_the_source_being_applied(env, capsys):
    """`apply --src <checkout>` ran the builder's installed project_sync.py, so a fixed setup in the new version
    never ran and the old one re-created the squad folder: the --src copy must win."""
    (env.src / "scripts").mkdir(exist_ok=True)
    (env.src / "scripts" / "project_sync.py").write_text(
        'import json\nprint(json.dumps({"ok": True, "bots": [], "from": "src"}))\n')
    env.squad("web")
    _, out = env.run("apply", "web", "--bots", "web", capsys=capsys)
    assert out["projects"].get("from") == "src", out["projects"]


def test_self_apply_runs_no_project_setup(env, capsys):
    env.squad("builder", lambda s: s["bots"]["builder"]["cron"]["builder-watch"].update(script="watch_upstream.py"))
    env.seed_builder()
    _, out = env.run("apply", "--self", capsys=capsys)
    assert "projects" not in out and not (env.home / "Projects").exists()


def test_squads_with_a_board_sync_projects_every_ten_minutes():
    for key in ("web", "marketing", "jobs"):
        spec = yaml.safe_load((REPO / "squads" / key / "squad.yaml").read_text())
        assert spec.get("board"), key
        job = spec["bots"][spec["manager"]]["cron"][f"{key}-projects"]
        assert job == {"schedule": "*/10 * * * *", "script": "project_sync.py", "agent": False}, key


def test_projects_cron_installs_project_sync_from_the_repo_scripts(env, capsys):
    """The manager's cron runs project_sync.py with no arguments: the script defaults come from its $HERMES_HOME."""
    (env.src / "scripts").mkdir(exist_ok=True)
    shutil.copy(SCRIPTS / "project_sync.py", env.src / "scripts" / "project_sync.py")
    env.squad("web", lambda s: s["bots"]["web"]["cron"].update(
        {"web-projects": {"schedule": "*/10 * * * *", "script": "project_sync.py", "agent": False}}))
    (env.src / "squads" / "web" / "scripts" / "project_sync.py").unlink()  # Env.squad stubs every cron script
    env.run("apply", "web", capsys=capsys)
    job = next(j for j in env.jobs("web") if j["name"] == "web-projects")
    assert (job["script"], job["no_agent"], job["deliver"]) == ("project_sync.py", True, "bot-chat:web")
    installed = env.root / "profiles" / "web" / "scripts" / "project_sync.py"
    assert installed.read_text() == (SCRIPTS / "project_sync.py").read_text()
    folder = env.home / "Projects" / "web" / "acme"
    folder.mkdir(parents=True)
    run = lambda *a: subprocess.run(["hermes", *a], capture_output=True, text=True, check=True)  # noqa: E731
    run("-p", "web", "project", "create", "Acme", str(folder), "--slug", "acme")
    p = subprocess.run([sys.executable, str(installed)], capture_output=True, text=True,
                       env={**os.environ, "HERMES_HOME": str(env.root / "profiles" / "web")})
    assert p.returncode == 0, p.stderr
    assert "web-qa create" in p.stdout and "web bind-board web" in p.stdout
    assert "acme" in run("-p", "web-qa", "project", "list").stdout


def test_doctor_warns_on_a_paused_squad_cron_job(env, capsys):
    """A paused squad job never fires (profile update installs new jobs paused; a user may pause one): doctor says
    so with the resume command, ignores jobs of other squads, and apply never resumes it on its own."""
    env.squad("builder", lambda s: s["bots"]["builder"]["cron"]["builder-watch"].update(script="watch_upstream.py"))
    env.seed_builder()
    env.run("apply", "--self", capsys=capsys)
    path = env.root / "profiles" / "builder" / "cron" / "jobs.json"
    data = json.loads(path.read_text())
    watch = next(j for j in data["jobs"] if j["name"] == "builder-watch")
    watch.update(enabled=False, state="paused", paused_reason="Installed from a profile distribution; review it")
    data["jobs"].append({"id": "other1", "name": "mine-nightly", "enabled": False, "state": "paused"})
    path.write_text(json.dumps(data))
    _, doc = env.run("doctor", "builder", expect=None, capsys=capsys)
    (warn,) = [c for c in doc["checks"] if c["check"] == "builder:cron:builder-watch"]
    assert warn["status"] == "warn" and "paused (Installed from a profile distribution" in warn["detail"]
    assert f"hermes -p builder cron resume {watch['id']}" in warn["detail"]
    assert not [c for c in doc["checks"] if "mine-nightly" in c["check"]]
    env.run("apply", "--self", capsys=capsys)
    again = next(j for j in json.loads(path.read_text())["jobs"] if j["name"] == "builder-watch")
    assert again["enabled"] is False


def test_an_unattended_upgrade_hands_the_keys_to_the_bots(env, capsys, monkeypatch):
    """Real problem: a provider connected after the install, and the daily update only printed "run apply --yes";
    bots kept failing until the user asked. The upgrade now copies the key itself."""
    for name in lane_keys():
        monkeypatch.delenv(name, raising=False)
    env.squad("web")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    (env.root / ".env").write_text("".join(f"{k}=sk-root-{i}\n" for i, k in enumerate(lane_keys())))
    env.local.joinpath("installed.yaml").write_text(yaml.safe_dump({"squads": {"web": {"version": "3.0.0"}},
                                                                   **models_doc()}))
    _, out = env.run("upgrade", capsys=capsys)
    assert "PROV_REVIEW_API_KEY" in env_names_of(env.root / "profiles" / "web-qa" / ".env")
    assert not any("credentials" in p for p in out["pending"]), out["pending"]
    assert "sk-root" not in json.dumps(out)


def test_an_empty_website_blocklist_lifts_the_block_an_earlier_version_installed(env, capsys):
    """Jobs 4.1 lets the scout open LinkedIn: removing the key from the manifest used to leave the old domain in the
    installed profile, so the scout stayed blocked after the update. An explicit empty list clears it."""
    def block(domains):
        return lambda spec: spec["bots"]["web-qa"].__setitem__("website_blocklist", domains)

    env.squad("web", mutate=block(["linkedin.com"]))
    env.run("apply", "web", capsys=capsys)
    held = env.config("web-qa")["security"]["website_blocklist"]
    assert held["enabled"] is True and held["domains"] == ["linkedin.com"]
    env.squad("web", mutate=block([]))
    env.run("apply", "web", capsys=capsys)
    lifted = env.config("web-qa")["security"]["website_blocklist"]
    assert lifted["enabled"] is False and lifted["domains"] == []
    assert "website_blocklist" not in env.config("web-frontend").get("security", {})   # a bot that never named it is untouched


# --- shared browser --------------------------------------------------------------------------------------------

def _shared(spec):
    spec["bots"]["web-qa"]["shared_browser"] = True


def _service_calls(monkeypatch, listening=None, status_extra=None):
    """Stub the shared-browser service script: record each command, report `listening` for status."""
    seen = []

    def fake(argv, timeout=60):
        seen.append(argv[2:])
        if argv[2:] == ["status"]:
            return subprocess.CompletedProcess(argv, 0,
                                               json.dumps({"listening": listening, **(status_extra or {})}), "")
        return subprocess.CompletedProcess(argv, 0, "{}", "")
    monkeypatch.setattr(squadctl, "run_quiet", fake)
    return seen


def test_shared_browser_bot_gets_cdp_url_plugin_and_the_manager_a_3_hourly_sweep(env, capsys, monkeypatch):
    """A bot that drives the shared signed-in browser: cdp_url points at it, the real-profile copy is off (it would
    win over cdp_url and fail while the owner's browser is open), the tab plugin is installed WITH tabs.py (the
    plugin imports it) and enabled, and the manager gets the no-agent sweep with its helper shipped beside it."""
    seen = _service_calls(monkeypatch)
    env.squad("web", _shared)
    _, out = env.run("apply", "web", capsys=capsys)
    cfg = env.config("web-qa")
    assert cfg["browser"]["cdp_url"] == "http://127.0.0.1:9333"
    assert cfg["browser"]["use_real_profile"] is False
    assert "shared-browser-tabs" in cfg["plugins"]["enabled"]
    plug = env.root / "profiles" / "web-qa" / "plugins" / "shared-browser-tabs"
    assert sorted(p.name for p in plug.iterdir()) == ["__init__.py", "plugin.yaml", "tabs.py"]
    assert (plug / "tabs.py").read_text() == (SCRIPTS / "shared_browser_tabs.py").read_text()
    assert "browser" not in (env.config("web-frontend").get("browser") or {}).get("cdp_url", "")
    assert "shared-browser-tabs" not in (env.config("web-frontend").get("plugins") or {}).get("enabled", [])
    sweep = [j for j in env.jobs("web") if j["name"] == "web-browser-sweep"]
    assert len(sweep) == 1 and sweep[0]["no_agent"] and sweep[0]["schedule"]["expr"] == "0 */3 * * *"
    scripts = env.root / "profiles" / "web" / "scripts"
    assert (scripts / "shared_browser_sweep.py").is_file() and (scripts / "shared_browser_tabs.py").is_file()
    assert ["install"] in seen and out["shared_browser"].startswith("installed on http://127.0.0.1:9333")
    assert not any("shared-browser-tabs is enabled but not in the manifest" in n
                   for b in out["bots"] for n in b.get("notes", []))


def test_shared_browser_second_apply_is_a_no_op_and_dropping_the_flag_undoes_it(env, capsys, monkeypatch):
    seen = _service_calls(monkeypatch, listening={"browser": "Chrome/145", "pages": 1})
    env.squad("web", _shared)
    env.run("apply", "web", capsys=capsys)
    n = len(env.calls())
    _, again = env.run("apply", "web", capsys=capsys)
    assert all(b["status"] == "unchanged" for b in again["bots"]), again["bots"]
    assert env.writes_since(n) == []
    assert ["install"] not in seen, "a listening browser is never reinstalled"
    env.squad("web")  # flag removed
    _, out = env.run("apply", "web", capsys=capsys)
    assert not (env.config("web-qa").get("browser") or {}).get("cdp_url")
    assert "shared-browser-tabs" not in env.config("web-qa")["plugins"]["enabled"]
    assert [j for j in env.jobs("web") if j["name"] == "web-browser-sweep"] == []


def test_every_squad_bot_runs_squad_kanban_and_the_builder_never_does(env, capsys):
    """CLI-filed cards must notify the manager's chat and workers must be told to save: the plugin is on every bot."""
    env.squad("web")
    env.run("apply", "web", capsys=capsys)
    src = REPO / "squads" / "_plugins" / "squad-kanban"
    for bot in ("web", "web-frontend", "web-qa"):
        dest = env.root / "profiles" / bot / "plugins" / "squad-kanban"
        assert (dest / "__init__.py").read_text() == (src / "__init__.py").read_text()
        assert "squad-kanban" in env.config(bot)["plugins"]["enabled"]
    tampered = env.root / "profiles" / "web-qa" / "plugins" / "squad-kanban" / "__init__.py"
    tampered.write_text("broken = True\n")
    _, plan = env.run("plan", "web", capsys=capsys)
    assert tampered.read_text() == "broken = True\n", "plan writes nothing"
    qa = next(b for b in plan["bots"] if b["bot"] == "web-qa")
    assert "plugin ~ squad-kanban" in qa["actions"]
    env.run("apply", "web", capsys=capsys)
    assert tampered.read_text() == (src / "__init__.py").read_text()
    _, again = env.run("plan", "web", capsys=capsys)
    assert all("squad-kanban" not in " ".join(b.get("actions") or []) for b in again["bots"])


def test_shared_browser_without_the_browser_toolset_is_refused(env, capsys):
    env.squad("web", lambda s: s["bots"]["web-deployer"].update(shared_browser=True))
    _, out = env.run("plan", "web", expect=1, capsys=capsys)
    assert "web-deployer sets shared_browser without the browser toolset" in out["error"]


def test_shared_browser_on_a_manager_without_the_browser_toolset_is_refused(env, capsys, monkeypatch):
    """#18: the check looked at the manifest's toolsets list and skipped managers, so a manager whose real toolset
    set has no browser passed and got cdp_url plus a plugin it cannot use. It must judge the toolsets the bot gets."""
    monkeypatch.setattr(squadctl.Ctx, "default_toolsets",
                        lambda self: {"terminal", "file", "skills", "web", "vision", "delegation", "session_search",
                                      "clarify", "cronjob", "kanban", "memory", "code_execution", "todo"})
    env.squad("web", lambda s: s["bots"]["web"].update(shared_browser=True))
    _, out = env.run("plan", "web", expect=1, capsys=capsys)
    assert "web sets shared_browser without the browser toolset" in out["error"]


def test_a_manager_whose_toolsets_include_the_browser_may_share_the_browser(env, capsys, monkeypatch):
    _service_calls(monkeypatch)
    env.squad("web", lambda s: s["bots"]["web"].update(shared_browser=True))
    _, plan = env.run("plan", "web", capsys=capsys)
    assert plan["shared_browser"], "a manager with the browser toolset in its base set is fine"


def test_shared_browser_apply_reinstalls_a_stale_job(env, capsys, monkeypatch):
    """The service is listening but its installed job differs from the current command line (an older plist: no
    Google containment flag, a moved Chromium). Apply must reinstall it, not report it as running."""
    seen = _service_calls(monkeypatch, listening={"browser": "Chrome/145", "pages": 1}, status_extra={
        "plist_current": False, "service_installed": True})
    env.squad("web", _shared)
    _, out = env.run("apply", "web", capsys=capsys)
    assert ["install"] in seen, seen
    assert out["shared_browser"].startswith("reinstalled on http://127.0.0.1:9333")


def test_shared_browser_plan_says_it_would_reinstall_a_stale_job(env, capsys, monkeypatch):
    seen = _service_calls(monkeypatch, listening={"browser": "Chrome/145", "pages": 1}, status_extra={
        "plist_current": False, "service_installed": True})
    env.squad("web", _shared)
    _, plan = env.run("plan", "web", capsys=capsys)
    assert "would reinstall" in plan["shared_browser"] and ["install"] not in seen


def test_the_builder_never_gets_the_users_real_profile(env, capsys):
    """The owner's real-profile consent is mirrored to squad bots, never to the builder: a builder chat that browsed
    there opened the owner's personal sessions inside a profile copy and left the owner's tabs in the wrong browser."""
    (env.root / "config.yaml").write_text("browser:\n  use_real_profile: true\n")
    builder = env.seed_builder()
    (builder / "config.yaml").write_text("model: {default: seed}\nbrowser:\n  use_real_profile: false\n")
    env.squad("builder")
    _, plan = env.run("plan", "--self", capsys=capsys)
    assert "browser.use_real_profile" not in json.dumps(plan)  # squad bots: the real-profile test above


def test_doctor_finds_bun_where_its_installer_puts_it(tmp_path, monkeypatch):
    """bun's official installer writes ~/.bun/bin/bun and edits only the shell rc, so a bot's PATH lacks it. The
    portal wrapper runs it from there; doctor warned "app bun not found" on a machine where search worked."""
    home = tmp_path / "home"
    (home / ".bun" / "bin").mkdir(parents=True)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(squadctl.Path, "home", classmethod(lambda cls: home))
    assert squadctl.app_problem("bun") is not None  # not installed anywhere: still reported
    bun = home / ".bun" / "bin" / "bun"
    bun.write_text("#!/bin/sh\necho 1.3.13\n")
    bun.chmod(0o755)
    assert squadctl.app_launcher("bun") == [str(bun)]
    assert squadctl.app_problem("bun") is None

