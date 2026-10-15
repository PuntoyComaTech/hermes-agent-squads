"""squadctl: plan, apply, status, doctor, uninstall, project add, chain, against a fake `hermes` and a temp HERMES_HOME.

Nothing here touches the real ~/.hermes: PATH points at tests/fakes/hermes.py and every path lives under tmp_path.
Tests that need the real `hermes` binary are skipped unless SQUADCTL_REAL_HERMES=1.
"""
import hashlib
import io
import json
import os
import re
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

real_hermes = pytest.mark.skipif(not os.environ.get("SQUADCTL_REAL_HERMES"), reason="needs the real hermes binary")
LANES = ["lead", "design", "code", "advisor", "review", "copy", "research", "digest", "aux", "vision"]
WEB_BOTS = ["web", "web-frontend", "web-backend", "web-qa", "web-deployer"]
ALWAYS = yaml.safe_load((SCRIPTS / "data" / "always-disabled.yaml").read_text())["always_disabled"]
WRITES = {("profile", "create"), ("profile", "delete"), ("profile", "describe"), ("profile", "export"),
          ("skills", "install"), ("skills", "opt-out"), ("cron", "create"), ("cron", "edit"), ("cron", "remove"),
          ("plugins", "enable"), ("plugins", "disable"), ("plugins", "install"), ("mcp", "add"),
          ("project", "create"), ("tools", "enable")}


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
        monkeypatch.setenv("FAKE_HERMES_LOG", str(self.log))
        monkeypatch.setenv("FAKE_HERMES_SRC", str(self.hsrc))
        self.models.write_text(yaml.safe_dump(models_doc()))
        (self.src / "squads" / "_schema").mkdir(parents=True)
        shutil.copy(REPO / "squads" / "_schema" / "squad.schema.json", self.src / "squads" / "_schema")

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
    assert (fe["model"]["provider"], fe["model"]["default"]) == ("prov-design", "model-design")
    assert fe["agent"]["reasoning_effort"] == "medium"
    assert web.config("web-backend")["agent"]["reasoning_effort"] == "medium"
    assert fe["platform_toolsets"]["cli"] == ["browser", "file", "kanban", "skills", "terminal", "todo", "vision"]
    assert fe["platform_toolsets"]["cron"] == ["terminal", "file", "skills", "kanban", "todo"]
    disabled = fe["agent"]["disabled_toolsets"]
    assert set(ALWAYS) <= set(disabled)
    assert {"web", "delegation", "memory", "cronjob"} <= set(disabled)
    assert not {"terminal", "file", "skills", "kanban", "browser", "vision", "todo"} & set(disabled)
    assert fe["auxiliary"]["compression"]["model"] == "model-aux"
    assert fe["auxiliary"]["vision"] == {"provider": "prov-vision", "model": "model-vision"}
    assert fe["skills"]["auto_load"] == ["building-frontend"]
    assert fe["terminal"]["cwd"] == str(web.root / "profiles" / "web-frontend" / "workspace")
    assert Path(fe["terminal"]["cwd"]).is_absolute()
    assert fe["memory"]["memory_enabled"] is False
    assert fe["kanban"]["max_in_progress_per_profile"] == 1
    assert fe["skills"]["external_dirs"] == [str(web.hsrc / "skills" / "cat" / "claude-design")]
    assert web.config("web")["memory"]["memory_enabled"] is True


def test_delegation_lane_and_passthrough(web):
    assert web.config("web-backend")["delegation"] == {"provider": "prov-advisor", "model": "model-advisor",
                                                       "reasoning_effort": "medium"}
    assert "delegation" not in web.config("web-qa") or not web.config("web-qa")["delegation"].get("model")
    assert web.config("web-deployer")["terminal"]["env_passthrough"] == [
        "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "GH_TOKEN"]
    assert web.config("web-qa")["terminal"]["env_passthrough"] == []


def test_ui_meta_hidden_section_and_revision(web):
    lead = yaml.safe_load((web.root / "profiles" / "web" / "profile.yaml").read_text())
    worker = yaml.safe_load((web.root / "profiles" / "web-qa" / "profile.yaml").read_text())
    assert lead["ui_meta"]["hermes-bots"] == {"title": "Web lead", "hidden": False, "sectionId": "web",
                                              "sectionName": "Web"}
    assert worker["ui_meta"]["hermes-bots"]["hidden"] is True
    assert lead["_ui_meta_revisions"] == {"hermes-bots": 1}


def test_skills_copied_with_sha_marker_and_soul(web):
    home = web.root / "profiles" / "web-frontend"
    for skill in ("building-frontend", "site-contract"):
        d = home / "skills" / "squad-web" / skill
        assert (d / "SKILL.md").is_file() and (d / "references" / "a.md").is_file()
        assert len((d / ".squad-sha").read_text().strip()) == 64
        assert not d.is_symlink()
    assert (home / "SOUL.md").read_text() == "You are web-frontend.\n"
    assert not (home / "skills" / "squad-web" / "leading-web").exists()


def test_plugins_mcp_cron_board_installed(web):
    assert web.config("web-frontend")["plugins"]["enabled"] == ["disk-cleanup", "security-guidance"]
    assert "context7" in web.config("web-frontend")["mcp_servers"]
    assert "chrome-devtools" in web.config("web-qa")["mcp_servers"]
    (job,) = web.jobs("web")
    assert (job["name"], job["script"], job["no_agent"]) == ("web-watch", "web_watch.py", True)
    assert job["deliver"] == "bot-chat:web"
    assert job["schedule"]["expr"] == "0 */4 * * *"
    assert (web.root / "profiles" / "web" / "scripts" / "web_watch.py").is_file()
    assert web.jobs("web-qa") == []
    boards = json.loads((web.root / "boards.json").read_text())
    assert [(b["slug"], b["archived"]) for b in boards] == [("web", False)]
    installed = yaml.safe_load((web.local / "installed.yaml").read_text())
    assert installed["squads"]["web"]["bots"] == WEB_BOTS
    assert installed["lanes"]["design"]["model"] == "model-design"


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
    assert any(a.startswith("set ") and "config keys (model prov-lead/model-lead medium)" in a for a in first)


def test_dry_run_after_apply_shows_diff_without_writing(web, capsys):
    web.models.write_text(yaml.safe_dump({"lanes": {**models_doc()["lanes"],
                                                    "design": {"provider": "p2", "model": "model-new"}}}))
    before = tree_hash(web.root)
    mark = len(web.calls())
    _, out = web.run("plan", "web", capsys=capsys)
    fe = next(b for b in out["bots"] if b["bot"] == "web-frontend")
    assert fe["status"] == "would-change"
    assert "set model.default: model-design -> model-new" in fe["actions"]
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
    assert any("no model assigned for web-frontend (lane design)" in n for n in notes)
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


def test_models_file_accepts_model_advisor_json(env, capsys):
    env.squad("web")
    rows = [{"bot": b, "lane": l, "model": f"adv-{l}", "provider": "adv", "reasoning": "low", "extras": []}
            for b, l in (("web", "lead"), ("web-frontend", "design"), ("web-backend", "code"), ("web-qa", "review"),
                         ("web-deployer", "research"))]
    rows[2]["extras"] = [{"use": "delegation", "lane": "advisor", "model": "adv-advisor", "provider": "adv",
                          "reasoning": "medium"}]
    shared = [{"use": u, "lane": l, "model": f"adv-{l}", "provider": "adv", "reasoning": "low"}
              for u, l in (("aux", "aux"), ("vision", "vision"))]
    env.models.write_text(json.dumps({"bots": rows, "shared": shared}))
    env.run("apply", "web", capsys=capsys)
    assert env.config("web-backend")["delegation"]["model"] == "adv-advisor"
    assert env.config("web-frontend")["auxiliary"]["vision"]["model"] == "adv-vision"
    assert env.config("web-frontend")["model"]["default"] == "adv-design"


# --- overlay and validation ---------------------------------------------------------------------------------------

def test_local_overlay_changes_one_bot_and_can_remove_one(env, capsys):
    env.squad("web")
    overlay = env.local / "squads" / "web" / "squad.yaml"
    overlay.parent.mkdir(parents=True)
    overlay.write_text(yaml.safe_dump({"bots": {"web-qa": {"toolsets": ["file", "skills", "kanban", "todo"]},
                                                "web-deployer": None},
                                       "chains": {"milestone": [{"stage": "ui", "assignee": "web-frontend"}]}}))
    _, out = env.run("plan", "web", capsys=capsys)
    assert [b["bot"] for b in out["bots"]] == ["web", "web-frontend", "web-backend", "web-qa"]
    env.run("apply", "web", capsys=capsys)
    assert env.config("web-qa")["platform_toolsets"]["cli"] == ["file", "kanban", "skills", "todo"]
    assert "browser" in env.config("web-qa")["agent"]["disabled_toolsets"]


@pytest.mark.parametrize("mutate,message", [
    (lambda s: s["bots"]["web"].update(role="worker"), "lead"),
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


def test_unknown_squad_lists_the_available_ones(env, capsys):
    env.squad("web")
    _, out = env.run("plan", "nope", expect=1, capsys=capsys)
    assert "available: web" in out["error"]


def test_apply_needs_a_squad_or_self(env, capsys):
    _, out = env.run("apply", expect=1, capsys=capsys)
    assert "squad key or --self" in out["error"]


# --- skills, plugins, confirm ---------------------------------------------------------------------------------------

def test_prune_keeps_only_declared_skills_and_backs_up_first(env, capsys):
    env.squad("web")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    skills = env.root / "profiles" / "web-qa" / "skills"
    for stray in ("random-skill", "cat/other-skill"):
        (skills / stray).mkdir(parents=True)
        (skills / stray / "SKILL.md").write_text("x")
    (skills / ".hub").mkdir(exist_ok=True)
    lock = skills / ".hub" / "lock.json"
    data = json.loads(lock.read_text()) if lock.is_file() else {"installed": {}}
    data["installed"]["kept-by-lock"] = {}
    lock.write_text(json.dumps(data))
    (skills / "cat" / "kept-by-lock").mkdir()
    (skills / "cat" / "kept-by-lock" / "SKILL.md").write_text("x")
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    (qa,) = out["bots"]
    assert qa["actions"] == ["skills removed: 2 (cat/other-skill, random-skill)"]
    assert not (skills / "random-skill").exists() and not (skills / "cat" / "other-skill").exists()
    assert (skills / "cat" / "kept-by-lock" / "SKILL.md").is_file()
    assert (skills / "squad-web" / "reviewing-sites" / "SKILL.md").is_file()
    assert len(list((env.local / "backups").glob("web-qa-*.tar.gz"))) == 1


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
    _, out = env.run("apply", "web", "--yes", capsys=capsys)
    qa = next(b for b in out["bots"] if b["bot"] == "web-qa")
    assert len(qa["pending"]) == 1 and "blender" in qa["pending"][0]
    assert not any(c["args"][:2] == ["plugins", "install"] for c in env.calls())


def test_plain_plugin_that_is_not_bundled_is_refused(env, capsys):
    env.squad("web", lambda s: s["bots"]["web-qa"]["plugins"]["enable"].append("community-thing"))
    shutil.rmtree(env.hsrc / "plugins" / "community-thing")
    _, out = env.run("apply", "web", expect=1, capsys=capsys)
    assert "community-thing" in out["error"] and "confirm" in out["error"]


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
    assert wrapper.read_text() == '#!/usr/bin/env bash\nexec python3 "$(dirname "$0")/web_watch.py" --board web --quiet\n'
    assert os.access(wrapper, os.X_OK)
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
    (job,) = env.jobs("builder")
    assert (job["name"], job["no_agent"], job["deliver"]) == ("builder-watch", False, "bot-chat:builder")
    assert (job["model"], job["provider"], job["reasoning_effort"], job["skills"]) == (
        "model-digest", "prov-digest", "high", ["tracking-updates"])
    meta = yaml.safe_load((home / "profile.yaml").read_text())["ui_meta"]["hermes-bots"]
    assert meta == {"title": "Builder", "hidden": False, "sectionId": "base", "sectionName": "Base"}
    assert not any(c["args"][:2] == ["profile", "create"] for c in env.calls())
    _, again = env.run("apply", "--self", capsys=capsys)
    assert again["summary"] == {"unchanged": 1}


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
    (job,) = env.jobs("builder-test")
    assert (job["name"], job["deliver"]) == ("builder-watch", "bot-chat:builder-test")
    assert env.config("builder-test")["terminal"]["cwd"] == str(home)
    assert not any(c["args"][:2] == ["profile", "create"] for c in env.calls())


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
    _, out = web.run("uninstall", "web", "--keep-profiles", capsys=capsys)
    assert len(list((web.root / "profiles").glob("web*"))) == 5
    assert web.jobs("web") == []
    assert len(list((web.local / "backups").glob("*.tar.gz"))) == 5
    assert not any(c["args"][:2] == ["profile", "delete"] for c in web.calls())


def test_uninstall_yes_flag_is_accepted(web, capsys):
    _, out = web.run("uninstall", "web", "--keep-profiles", "--yes", capsys=capsys)
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
    assert dry["dry_run"] is True and dry["board"] == "web" and dry["lead"] == "web"
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
    assert "chains: milestone" in out["error"]


# --- status, doctor ---------------------------------------------------------------------------------------------

def test_status_empty_and_installed(env, capsys):
    env.squad("web")
    _, out = env.run("status", capsys=capsys)
    assert out == {"installed": 0, "available": ["web"], "squads": []}
    env.run("apply", "web", capsys=capsys)
    _, out = env.run("status", capsys=capsys)
    (squad,) = out["squads"]
    assert squad["installed"] == "3.0.0" and squad["board"] == "exists"
    assert [b["state"] for b in squad["bots"]] == ["ok"] * 5
    assert squad["bots"][1]["model"] == "model-design"


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
    assert checks["web-deployer:GH_TOKEN"]["detail"] == "set"
    assert checks["web-deployer:CLOUDFLARE_API_TOKEN"]["status"] == "warn"
    assert checks["desktop-kanban"]["status"] == "info"
    assert checks["web:cards"]["detail"] == "no stale cards"
    assert "ghp_supersecretvalue" not in json.dumps(out)


def test_doctor_warns_about_missing_models(env, capsys):
    env.squad("web")
    env.run("apply", "web", "--bots", "web", capsys=capsys)
    env.local.joinpath("installed.yaml").write_text(yaml.safe_dump({"squads": {"web": {"version": "3.0.0"}}}))
    _, out = env.run("doctor", capsys=capsys)
    assert any(c["status"] == "warn" and "no model assigned" in c["detail"] for c in out["checks"])


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


def test_scripts_never_mention_secret_files():
    for name in ("squadctl.py", "_profile_apply.py", "squadctl"):
        text = (SCRIPTS / name).read_text()
        assert not re.search(r"\.env\b", text) and "auth.json" not in text, name
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
