"""2.2.0: SOUL composition from the installed Hermes, `squadctl upgrade`, auto_update.py, keep_awake.py.

Fakes only: tests/fakes/hermes.py for squadctl, small stubs for auto_update's `hpy` and `hermes`, a file:// raw URL.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from test_squadctl import FAKE_IDENTITY, REPO, SCRIPTS, Env, squadctl  # noqa: F401  (the shared fake-hermes harness)

sys.path.insert(0, str(SCRIPTS))
import auto_update  # noqa: E402
import keep_awake  # noqa: E402

BASE = (REPO / "squads" / "_base" / "hermes-base.md").read_text().rstrip("\n")


@pytest.fixture
def env(tmp_path, monkeypatch):
    return Env(tmp_path, monkeypatch)


def soul(env, bot):
    return (env.root / "profiles" / bot / "SOUL.md").read_text()


def qa(out):
    return next(b for b in out["bots"] if b["bot"] == "web-qa")


# --- SOUL -------------------------------------------------------------------------------------------------------

def test_soul_identity_comes_from_the_installed_hermes(env, capsys):
    env.squad("web")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    assert soul(env, "web-qa") == f"{FAKE_IDENTITY}\n\n{BASE}\n\nYou are web-qa.\n"
    (env.hsrc / "agent" / "prompt_builder.py").write_text('DEFAULT_AGENT_IDENTITY = "You are Hermes Agent v2."\n')
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    assert "SOUL.md updated" in qa(out)["actions"] and not qa(out).get("pending")
    assert soul(env, "web-qa").startswith("You are Hermes Agent v2.\n\n" + BASE)


def test_append_file_is_composed_last_and_kept(env, capsys):
    env.squad("web")
    extra = env.local / "squads" / "web" / "souls" / "web-qa.append.md"
    extra.parent.mkdir(parents=True)
    extra.write_text("Always test on Safari too.\n")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    assert soul(env, "web-qa").endswith("\n\nYou are web-qa.\n\nAlways test on Safari too.\n")
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    assert qa(out)["status"] == "unchanged"


def test_user_edited_soul_stays_pending_until_confirm_then_is_backed_up(env, capsys):
    env.squad("web")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    edited = soul(env, "web-qa") + "My own rule.\n"
    (env.root / "profiles" / "web-qa" / "SOUL.md").write_text(edited)
    (env.hsrc / "agent" / "prompt_builder.py").write_text('DEFAULT_AGENT_IDENTITY = "New identity."\n')
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    (pending,) = qa(out)["pending"]
    assert pending.startswith("soul:web-qa:") and "web-qa.append.md" in pending
    assert soul(env, "web-qa") == edited
    _, out = env.run("apply", "web", "--bots", "web-qa", "--confirm", "soul:web-qa", capsys=capsys)
    assert "SOUL.md updated" in qa(out)["actions"]
    (backup,) = (env.local / "backups").glob("web-qa-SOUL-*.md")
    assert backup.read_text() == edited and soul(env, "web-qa").startswith("New identity.")


def test_missing_marker_with_the_composed_soul_only_writes_the_marker(env, capsys):
    env.squad("web")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    mark = env.root / "profiles" / "web-qa" / squadctl.SOUL_MARK
    mark.unlink()
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    assert qa(out)["status"] == "unchanged" and mark.is_file()


def test_soul_without_marker_is_replaced_on_first_apply(env, capsys):
    """A profile squadctl never wrote (Hermes's seeded default SOUL.md) is not a user edit."""
    env.squad("web")
    env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    home = env.root / "profiles" / "web-qa"
    (home / squadctl.SOUL_MARK).unlink()
    (home / "SOUL.md").write_text("Hermes default persona.\n")
    _, out = env.run("apply", "web", "--bots", "web-qa", capsys=capsys)
    assert "SOUL.md updated" in qa(out)["actions"] and not qa(out).get("pending")
    assert not (env.local / "backups").exists() or not list((env.local / "backups").glob("*SOUL*"))


def test_every_squad_bot_has_a_soul_file():
    for manifest in sorted((REPO / "squads").glob("*/squad.yaml")):
        for bot in yaml.safe_load(manifest.read_text())["bots"]:
            assert (manifest.parent / "souls" / f"{bot}.md").is_file(), (manifest.parent.name, bot)
    for bot in yaml.safe_load((REPO / "builder.yaml").read_text())["bots"]:
        assert (REPO / "squads" / "builder" / "souls" / f"{bot}.md").is_file(), bot


def test_shipped_builder_soul_is_the_base_plus_its_role():
    """`hermes profile install` ships SOUL.md before the first apply composes it with the Hermes identity."""
    role = (REPO / "squads" / "builder" / "souls" / "builder.md").read_text()
    assert (REPO / "SOUL.md").read_text() == f"{BASE}\n\n{role}"


# --- squadctl upgrade -------------------------------------------------------------------------------------------

def upgrade(env, capsys, *extra, expect=0):
    return env.run("upgrade", *extra, expect=expect, capsys=capsys)[1]


@pytest.fixture
def installed(env, capsys):
    env.squad("web")
    env.run("apply", "web", capsys=capsys)
    return env


def test_upgrade_second_run_applies_nothing(installed, capsys):
    first = upgrade(installed, capsys)
    assert not first["errors"] and not first["waiting"]
    again = upgrade(installed, capsys)
    assert again["applied"] == {} and again["unchanged"] == ["web"] and again["lanes_added"] == {}


def test_upgrade_keeps_learned_skills(installed, capsys):
    learned = installed.root / "profiles" / "web-qa" / "skills" / "my-checks"
    learned.mkdir()
    (learned / "SKILL.md").write_text("---\nname: my-checks\n---\n")
    upgrade(installed, capsys)
    assert (learned / "SKILL.md").is_file()


def test_upgrade_keeps_a_model_the_user_switched(installed, capsys):
    cfg_path = installed.root / "profiles" / "web-qa" / "config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    cfg["model"].update(provider="prov-keyless", default="user-pick")
    cfg_path.write_text(yaml.safe_dump(cfg))
    out = upgrade(installed, capsys)
    assert out["models_kept"] == ["web-qa: user-pick"]
    assert yaml.safe_load(cfg_path.read_text())["model"]["default"] == "user-pick"
    pins = yaml.safe_load((installed.local / "installed.yaml").read_text())["bots"]
    assert pins["web-qa"]["model"] == "user-pick" and pins["web-qa"]["provider"] == "prov-keyless"
    assert upgrade(installed, capsys)["models_kept"] == []


def test_upgrade_fills_a_lane_a_new_version_added(installed, capsys, monkeypatch):
    path = installed.local / "installed.yaml"
    doc = yaml.safe_load(path.read_text())
    doc["lanes"].pop("research")
    path.write_text(yaml.safe_dump(doc))
    asked = []

    def advisor(ctx, lanes):
        asked.append(lanes)
        return [{"lane": "research", "provider": "prov-research", "model": "cheap-pick", "reasoning": "low"}]
    monkeypatch.setattr(squadctl, "advisor_lanes", advisor)
    out = upgrade(installed, capsys)
    assert asked == [["research"]] and out["lanes_added"]["research"]["model"] == "cheap-pick"
    assert yaml.safe_load(path.read_text())["lanes"]["research"]["model"] == "cheap-pick"
    assert installed.config("web")["delegation"]["model"] == "cheap-pick"
    assert not out["errors"]


def test_upgrade_skips_a_squad_with_running_cards(installed, capsys):
    store = installed.root / "cards-web.json"
    store.write_text(json.dumps({"k": {"id": "t_0001", "status": "running", "title": "x"}}))
    (installed.root / "profiles" / "web-qa" / "SOUL.md").unlink()
    out = upgrade(installed, capsys)
    assert out["waiting"] == ["web: 1 running card(s)"] and "web" not in out["applied"]
    assert not (installed.root / "profiles" / "web-qa" / "SOUL.md").exists()
    store.write_text(json.dumps({"k": {"id": "t_0001", "status": "done", "title": "x"}}))
    out = upgrade(installed, capsys)
    assert out["applied"]["web"]["bots"] == 1 and (installed.root / "profiles" / "web-qa" / "SOUL.md").is_file()


def test_upgrade_dry_run_writes_nothing(installed, capsys):
    (installed.root / "profiles" / "web-qa" / "SOUL.md").unlink()
    out = upgrade(installed, capsys, "--dry-run")
    assert out["dry_run"] and out["applied"]["web"]["bots"] == 1
    assert not (installed.root / "profiles" / "web-qa" / "SOUL.md").exists()


# --- auto_update.py ---------------------------------------------------------------------------------------------

HPY_STUB = """#!/bin/sh
echo "$@" >> "$(dirname "$0")/../hpy.log"
case "$*" in *--dry-run*) cat "$(dirname "$0")/../dry.json" ;; *) cat "$(dirname "$0")/../real.json" ;; esac
"""
HERMES_STUB = """#!/bin/sh
echo "HERMES_HOME=$HERMES_HOME $*" >> "{log}"
"""
EMPTY = {"applied": {}, "unchanged": ["builder"], "waiting": [], "pending": [], "lanes_added": {},
         "models_kept": [], "errors": []}


class Upd:
    """A builder home with stub `scripts/hpy` (squadctl) and `hermes` on PATH, and a file:// squads repo."""

    def __init__(self, tmp: Path, monkeypatch):
        self.root = tmp / "hermes"
        self.home = self.root / "profiles" / "builder"
        self.repo = tmp / "repo"
        (self.home / "scripts").mkdir(parents=True)
        self.repo.mkdir()
        hpy = self.home / "scripts" / "hpy"
        hpy.write_text(HPY_STUB)
        hpy.chmod(0o755)
        self.log = tmp / "hermes.log"
        bindir = tmp / "bin"
        bindir.mkdir()
        (bindir / "hermes").write_text(HERMES_STUB.format(log=self.log))
        (bindir / "hermes").chmod(0o755)
        monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("HERMES_HOME", str(self.home))
        self.installed_version = "2.2.0"
        self.versions("2.2.0", "2.2.0")
        self.reports(EMPTY, EMPTY)

    def versions(self, installed: str, remote: str):
        (self.home / "distribution.yaml").write_text(f"name: builder\nversion: {installed}\n")
        (self.repo / "distribution.yaml").write_text(f"name: builder\nversion: \"{remote}\"\n")

    def reports(self, dry: dict, real: dict):
        (self.home / "dry.json").write_text(json.dumps(dry))
        (self.home / "real.json").write_text(json.dumps(real))

    def run(self, capsys, *args):
        code = auto_update.main(["--raw-url", self.repo.as_uri(), *args])
        out = capsys.readouterr()
        return code, out.out, out.err

    def hermes_calls(self):
        return self.log.read_text().splitlines() if self.log.is_file() else []

    def hpy_calls(self):
        p = self.home / "hpy.log"
        return p.read_text().splitlines() if p.is_file() else []


@pytest.fixture
def upd(tmp_path, monkeypatch):
    return Upd(tmp_path, monkeypatch)


def test_auto_update_is_silent_when_versions_match_and_nothing_lags(upd, capsys):
    assert upd.run(capsys) == (0, "", "")
    assert upd.hermes_calls() == []
    assert [c for c in upd.hpy_calls() if "--dry-run" not in c] == []


def test_auto_update_brings_lagging_bots_up_without_profile_update(upd, capsys):
    lag = {**EMPTY, "applied": {"web": {"version": "1.0.0", "bots": 2, "actions": 3}}, "unchanged": []}
    upd.reports(lag, lag)
    code, out, _ = upd.run(capsys)
    assert code == 0 and out.splitlines() == ["Squads 2.2.0: bots brought up to date", "- web: 2 bot(s) updated"]
    assert upd.hermes_calls() == []


def test_manual_force_run_reports_even_with_nothing_new(upd, capsys):
    code, out, _ = upd.run(capsys, "--force")
    assert code == 0 and out.strip() == "Squads 2.2.0: everything is up to date"
    assert upd.hermes_calls() == []
    assert any("upgrade" in c and "--dry-run" not in c for c in upd.hpy_calls())


def test_auto_update_uses_profile_update_only_when_the_version_rose(upd, capsys):
    upd.versions("2.1.0", "2.2.0")
    (upd.home / "CHANGELOG.md").write_text(
        "# Changelog\n\n## 2.2.0 - 2026-10-17\n\n- Bots keep awake while cards run. More text.\n\n"
        "## 2.1.0 - 2026-10-16\n\n- Old entry.\n")
    (upd.home / "squads" / "studio").mkdir(parents=True)  # `hermes profile update` (stub below) lands it
    rep = {**EMPTY, "applied": {"builder": {"version": "2.2.0", "bots": 1, "actions": 4}},
           "lanes_added": {"deploy": {"provider": "prov-x", "model": "cheap"}},
           "waiting": ["web: 1 running card(s)"], "pending": ["web-qa: soul:web-qa: SOUL.md was edited"]}
    upd.reports(EMPTY, rep)
    real_update = upd.home / "squads" / "studio" / "squad.yaml"
    hermes_stub = upd.log.parent / "bin" / "hermes"
    hermes_stub.write_text(HERMES_STUB.format(log=upd.log) + f'printf \'name: Studio\\ndescription: "Video and 3D '
                           f'production"\\n\' > "{real_update}"\n')
    code, out, _ = upd.run(capsys)
    assert code == 0
    (call,) = upd.hermes_calls()
    assert call == f"HERMES_HOME={upd.root} profile update builder --yes"
    assert out.splitlines() == [
        "Squads updated 2.1.0 -> 2.2.0",
        "- Bots keep awake while cards run",
        "- builder: 1 bot(s) updated",
        "- New squad available: Studio: Video and 3D production. Tell me \"install studio\" to add it.",
        "- New lane deploy: cheap (prov-x); change it any time",
        "- Waiting: web: 1 running card(s) (retried on the next run)",
        "- Needs you: web-qa: soul:web-qa: SOUL.md was edited",
    ]


def test_auto_update_check_and_failures(upd, capsys):
    upd.versions("2.1.0", "2.2.0")
    assert upd.run(capsys, "--check") == (0, "Squads update available: 2.1.0 -> 2.2.0\n", "")
    assert upd.hermes_calls() == []
    (upd.repo / "distribution.yaml").unlink()
    code, out, err = upd.run(capsys)
    assert code == 1 and out == "" and "update check failed" in err


def test_auto_update_saves_edited_shipped_files(upd, capsys):
    (upd.home / "skills" / "x").mkdir(parents=True)
    f = upd.home / "skills" / "x" / "SKILL.md"
    f.write_text("v1\n")
    upd.run(capsys)  # silent tick records the shipped files
    f.write_text("edited\n")
    code, out, _ = upd.run(capsys, "--force")  # no new release: nothing is replaced, nothing to back up
    assert code == 0 and "edited shipped file" not in out and f.read_text() == "edited\n"
    upd.versions("2.2.0", "2.3.0")
    code, out, _ = upd.run(capsys)
    assert code == 0 and "1 edited shipped file(s) saved to" in out
    (copy,) = (upd.home / "local" / "backups").glob("edits-*/skills/x/SKILL.md")
    assert copy.read_text() == "edited\n"


def test_builder_update_cron_runs_auto_update_with_no_agent():
    cron = yaml.safe_load((REPO / "builder.yaml").read_text())["bots"]["builder"]["cron"]
    assert cron["builder-update"] == {"schedule": "30 6 * * *", "script": "auto_update.py", "agent": False}
    assert "args" not in cron["builder-watch"]


def test_auto_update_help_runs_without_network():
    p = subprocess.run([sys.executable, "-I", str(SCRIPTS / "auto_update.py"), "--help"], capture_output=True,
                       text=True, timeout=60)
    assert p.returncode == 0 and "--raw-url" in p.stdout and "--force" in p.stdout


# --- keep_awake.py ----------------------------------------------------------------------------------------------

KANBAN_STUB = """#!/bin/sh
echo "$@" >> "$0.log"
cat "$0.json"
"""


def kanban(tmp: Path, cards) -> Path:
    stub = tmp / "hermes"
    stub.write_text(KANBAN_STUB)
    stub.chmod(0o755)
    Path(f"{stub}.json").write_text(json.dumps(cards))
    return stub


@pytest.fixture
def spawned(monkeypatch):
    calls = []
    monkeypatch.setattr(keep_awake, "spawn", calls.append)
    monkeypatch.setattr(keep_awake.shutil, "which", lambda name: f"/usr/bin/{name}")
    return calls


def test_keep_awake_holds_sleep_off_while_cards_run(tmp_path, monkeypatch, spawned, capsys):
    monkeypatch.setattr(keep_awake.sys, "platform", "darwin")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "profiles" / "web"))
    stub = kanban(tmp_path, [{"id": "t_1", "status": "running"}])
    assert keep_awake.main(["--hermes-bin", str(stub)]) == 0
    assert spawned == [["caffeinate", "-is", "-t", "300"]]
    assert Path(f"{stub}.log").read_text().split() == ["kanban", "--board", "web", "list", "--status", "running",
                                                       "--json"]
    assert capsys.readouterr() == ("", "")


def test_keep_awake_does_nothing_on_an_idle_board(tmp_path, monkeypatch, spawned, capsys):
    monkeypatch.setattr(keep_awake.sys, "platform", "darwin")
    assert keep_awake.main(["--board", "web", "--hermes-bin", str(kanban(tmp_path, []))]) == 0
    assert keep_awake.main(["--board", "web", "--hermes-bin", str(tmp_path / "missing")]) == 0
    assert spawned == [] and capsys.readouterr() == ("", "")


def test_keep_awake_hold_per_platform(spawned):
    assert keep_awake.hold_command("linux", 300) == ["systemd-inhibit", "--what=idle:sleep", "--who=hermes-squads",
                                                     "--why=Kanban cards running", "sleep", "300"]
    assert keep_awake.hold_command("win32", 300) is None
    assert keep_awake.hold_command("darwin", 120) == ["caffeinate", "-is", "-t", "120"]


def test_every_squad_manager_has_the_awake_cron():
    for manifest in sorted((REPO / "squads").glob("*/squad.yaml")):
        doc = yaml.safe_load(manifest.read_text())
        cron = doc["bots"][doc["manager"]].get("cron") or {}
        assert cron.get(f"{doc['key']}-awake") == {"schedule": "*/4 * * * *", "script": "keep_awake.py",
                                                   "agent": False}, doc["key"]


def test_keep_awake_cron_lands_on_the_manager(installed, capsys):
    (installed.src / "squads" / "web" / "scripts" / "keep_awake.py").write_text("print()\n")
    spec = yaml.safe_load((installed.src / "squads" / "web" / "squad.yaml").read_text())
    spec["bots"]["web"]["cron"]["web-awake"] = {"schedule": "*/4 * * * *", "script": "keep_awake.py", "agent": False}
    (installed.src / "squads" / "web" / "squad.yaml").write_text(yaml.safe_dump(spec, sort_keys=False))
    _, out = installed.run("apply", "web", "--bots", "web", capsys=capsys)
    assert "cron + web-awake" in out["bots"][0]["actions"]
    job = next(j for j in installed.jobs("web") if j["name"] == "web-awake")
    assert (job["no_agent"], job["script"], job["schedule"]["expr"]) == (True, "keep_awake.py", "*/4 * * * *")


# --- local skill edits survive an update --------------------------------------------------------------------------

LEARNED_RULE = "6. Check every hand-off between stages.\n"


def release(upd, version, files):
    """`hermes profile update` stub: writes the new shipped files, then auto_update merges the local edits back."""
    upd.versions(upd.installed_version, version)
    lines = "".join(f"mkdir -p \"$(dirname '{upd.home / rel}')\"; printf '%s' '{text}' > '{upd.home / rel}'\n"
                    for rel, text in files.items())
    (upd.log.parent / "bin" / "hermes").write_text(HERMES_STUB.format(log=upd.log) + lines)


def ship(upd, version, files):
    """Install `version` with `files` as if a previous update shipped them, then record them as the base."""
    for rel, text in files.items():
        (upd.home / rel).parent.mkdir(parents=True, exist_ok=True)
        (upd.home / rel).write_text(text)
    upd.installed_version = version
    upd.versions(version, version)
    upd.run(upd.capsys, "--force")


def test_a_learned_skill_edit_survives_an_update_that_did_not_touch_it(upd, capsys):
    upd.capsys = capsys
    ship(upd, "2.2.0", {"skills/authoring/SKILL.md": "1. Write.\n2. Lint.\n", "skills/other/SKILL.md": "old\n"})
    edited = upd.home / "skills" / "authoring" / "SKILL.md"
    edited.write_text("1. Write.\n2. Lint.\n" + LEARNED_RULE)  # the background skill review patched it
    release(upd, "2.3.0", {"skills/authoring/SKILL.md": "1. Write.\n2. Lint.\n", "skills/other/SKILL.md": "new\n"})
    code, out, _ = upd.run(capsys)
    assert code == 0 and "Kept your edits to 1 skill file(s)" in out
    assert edited.read_text().endswith(LEARNED_RULE)
    assert (upd.home / "skills" / "other" / "SKILL.md").read_text() == "new\n"
    (copy,) = (upd.home / "local" / "backups").glob("edits-*/skills/authoring/SKILL.md")
    assert copy.read_text().endswith(LEARNED_RULE)


def test_a_learned_edit_merges_into_an_updated_skill_and_survives_the_next_update_too(upd, capsys):
    upd.capsys = capsys
    ship(upd, "2.2.0", {"skills/authoring/SKILL.md": "# A\n\n1. Write.\n2. Lint.\n\n## Pitfalls\n\n- old\n"})
    edited = upd.home / "skills" / "authoring" / "SKILL.md"
    edited.write_text("# A\n\n1. Write.\n2. Lint.\n" + LEARNED_RULE + "\n## Pitfalls\n\n- old\n")
    release(upd, "2.3.0", {"skills/authoring/SKILL.md": "# A\n\n1. Write.\n2. Lint.\n\n## Pitfalls\n\n- new upstream\n"})
    code, out, _ = upd.run(capsys)
    assert code == 0 and "Merged your edits into 1 updated skill file(s)" in out
    assert edited.read_text() == "# A\n\n1. Write.\n2. Lint.\n" + LEARNED_RULE + "\n## Pitfalls\n\n- new upstream\n"
    upd.installed_version = "2.3.0"
    release(upd, "2.4.0", {"skills/authoring/SKILL.md": "# A v2\n\n1. Write.\n2. Lint.\n\n## Pitfalls\n\n- new upstream\n"})
    code, out, _ = upd.run(capsys)
    assert code == 0 and "Merged your edits" in out
    assert edited.read_text().startswith("# A v2\n") and LEARNED_RULE in edited.read_text()


def test_a_conflicting_edit_keeps_what_was_learned_and_saves_the_new_version_aside(upd, capsys):
    """An update never takes a learned rule away from the builder: the edit stays live, upstream waits beside it."""
    upd.capsys = capsys
    ship(upd, "2.2.0", {"skills/authoring/SKILL.md": "1. Write.\n2. Lint.\n"})
    edited = upd.home / "skills" / "authoring" / "SKILL.md"
    edited.write_text("1. Write.\n2. Lint with --strict.\n")
    release(upd, "2.3.0", {"skills/authoring/SKILL.md": "1. Write.\n2. Lint with skill_lint.py.\n"})
    code, out, _ = upd.run(capsys)
    assert code == 0 and "Needs you: skills/authoring/SKILL.md changed both here and upstream" in out
    assert edited.read_text() == "1. Write.\n2. Lint with --strict.\n"
    (upstream,) = (upd.home / "local" / "backups").glob("edits-*/upstream/skills/authoring/SKILL.md")
    assert upstream.read_text() == "1. Write.\n2. Lint with skill_lint.py.\n"


def test_an_edit_that_went_upstream_is_not_reported(upd, capsys):
    upd.capsys = capsys
    ship(upd, "2.2.0", {"skills/authoring/SKILL.md": "1. Write.\n"})
    (upd.home / "skills" / "authoring" / "SKILL.md").write_text("1. Write.\n" + LEARNED_RULE)
    release(upd, "2.3.0", {"skills/authoring/SKILL.md": "1. Write.\n" + LEARNED_RULE})
    code, out, _ = upd.run(capsys)
    assert code == 0 and "Kept your edits" not in out and "Merged" not in out and "Needs you" not in out


def test_runtime_dot_files_are_not_counted_as_edits(upd, capsys):
    upd.capsys = capsys
    ship(upd, "2.2.0", {"skills/a/SKILL.md": "x\n", "skills/.usage.json": "{}"})
    (upd.home / "skills" / ".usage.json").write_text('{"a": 3}')
    release(upd, "2.3.0", {"skills/a/SKILL.md": "x\n"})
    code, out, _ = upd.run(capsys)
    assert code == 0 and "edited shipped file" not in out


def test_upgrade_merges_a_bot_edit_into_an_updated_squad_skill(installed, capsys):
    """squadctl copies squad skills into each bot; the bot's own edit (background skill review) must survive."""
    dest = installed.root / "profiles" / "web-qa" / "skills" / "squad-web" / "reviewing-sites" / "SKILL.md"
    src = installed.src / "squads" / "web" / "skills" / "reviewing-sites" / "SKILL.md"
    dest.write_text(dest.read_text() + "LEARNED: check the mobile menu.\n")
    src.write_text("UPSTREAM HEADER\n" + src.read_text())
    out = upgrade(installed, capsys)
    assert not out["errors"]
    text = dest.read_text()
    assert text.startswith("UPSTREAM HEADER\n") and text.endswith("LEARNED: check the mobile menu.\n")
    again = upgrade(installed, capsys)  # merged copy is stable: no re-copy, edit still there
    assert again["applied"] == {} and dest.read_text() == text


def test_a_file_the_bot_deleted_stays_deleted_when_upstream_edits_it(installed, capsys):
    skill = installed.root / "profiles" / "web-qa" / "skills" / "squad-web" / "reviewing-sites"
    ref = next(p for p in sorted((skill / "references").glob("*.md")))
    rel = ref.relative_to(skill)
    src = installed.src / "squads" / "web" / "skills" / "reviewing-sites" / rel
    ref.unlink()
    src.write_text(src.read_text() + "UPSTREAM LINE\n")
    upgrade(installed, capsys)
    assert not ref.exists(), "the bot removed it on purpose"


def test_without_a_merge_base_only_the_files_the_bot_touched_keep_its_copy(installed, capsys):
    """Bots installed before merge bases existed: an untouched file must still update, never freeze."""
    import os
    import shutil as sh
    skill = installed.root / "profiles" / "web-qa" / "skills" / "squad-web" / "reviewing-sites"
    src = installed.src / "squads" / "web" / "skills" / "reviewing-sites"
    sh.rmtree(installed.local / "state" / "skill-base" / "web-qa" / "reviewing-sites")
    ref_rel = next(p for p in sorted((skill / "references").glob("*.md"))).relative_to(skill)
    stamp = (skill / ".squad-sha").stat().st_mtime
    os.utime(skill / ref_rel, (stamp, stamp))
    (skill / "SKILL.md").write_text((skill / "SKILL.md").read_text() + "LEARNED\n")
    os.utime(skill / "SKILL.md", (stamp + 60, stamp + 60))
    (src / ref_rel).write_text((src / ref_rel).read_text() + "UPSTREAM REF\n")
    upgrade(installed, capsys)
    assert (skill / "SKILL.md").read_text().endswith("LEARNED\n")
    assert (skill / ref_rel).read_text().endswith("UPSTREAM REF\n"), "an untouched file takes the new version"


def test_upgrade_reports_a_conflicting_bot_edit_and_keeps_a_copy(installed, capsys):
    dest = installed.root / "profiles" / "web-qa" / "skills" / "squad-web" / "reviewing-sites" / "SKILL.md"
    src = installed.src / "squads" / "web" / "skills" / "reviewing-sites" / "SKILL.md"
    first = dest.read_text().splitlines(True)
    dest.write_text("".join(["LOCAL TITLE\n", *first[1:]]))
    src.write_text("".join(["UPSTREAM TITLE\n", *first[1:]]))
    (dest.parent / "references").mkdir(exist_ok=True)
    (dest.parent / "references" / "learned.md").write_text("LEARNED REFERENCE\n")  # a file only the bot added
    out = upgrade(installed, capsys)
    assert any("skill reviewing-sites: edited here and changed upstream" in p for p in out["pending"])
    assert dest.read_text().startswith("LOCAL TITLE\n"), "the bot keeps what it learned"
    assert (dest.parent / "references" / "learned.md").read_text() == "LEARNED REFERENCE\n"
    (upstream,) = (installed.local / "backups").glob("skill-edits-*/web-qa/reviewing-sites/upstream/SKILL.md")
    assert upstream.read_text().startswith("UPSTREAM TITLE\n")
    again = upgrade(installed, capsys)  # the conflict is reported once, not on every apply
    assert again["applied"] == {} and not any("reviewing-sites" in p for p in again["pending"])
    assert dest.read_text().startswith("LOCAL TITLE\n")
    src.write_text(src.read_text() + "UPSTREAM FOOTER\n")  # a later, non-clashing upstream change still merges in
    upgrade(installed, capsys)
    assert dest.read_text().startswith("LOCAL TITLE\n") and dest.read_text().endswith("UPSTREAM FOOTER\n")
