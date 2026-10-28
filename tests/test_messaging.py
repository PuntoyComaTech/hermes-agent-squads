"""Messaging channels: `squadctl connect`, `notify: true` cron jobs and the doctor check.

The scenario is the jobs owner's: the manager gets a Discord bot, a #job-alerts channel, and its user-facing crons
(search, follow-ups, board watch) deliver there while the housekeeping crons stay on Bot Chat. Every later apply and
upgrade must keep that, because an apply that silently moves the digest back to Bot Chat means the owner, who only
reads Discord, never sees it. Discord's REST API is replaced by an in-memory server (FakeDiscord); hermes is the fake.
"""
import json

import pytest
import yaml

from test_squadctl import REPO, Env, squadctl, stub_cli_probes  # noqa: F401  (autouse fixture for this module)

CHANNEL = "777000111"


class FakeDiscord:
    """One server with a #general channel. `joined=False` is a bot whose invite was never accepted."""

    def __init__(self, joined=True, manage=True):
        self.joined, self.manage = joined, manage
        self.channels = [{"id": "100", "name": "general", "type": 0}]
        self.calls = []

    def __call__(self, token, method, path, body=None):
        assert token == "tok-jobs", "connect must use the bot's own token"
        self.calls.append((method, path))
        if path == "/users/@me/guilds":
            return [{"id": "g1", "name": "Hermes", "permissions": "2048"}] if self.joined else []
        if path == "/oauth2/applications/@me":
            return {"id": "app42"}
        if path == "/guilds/g1/channels" and method == "GET":
            return list(self.channels)
        if path == "/guilds/g1/channels" and method == "POST":
            if not self.manage:
                raise squadctl.Fail("Discord POST /guilds/g1/channels: HTTP 403", 3)
            ch = {"id": CHANNEL, "name": body["name"], "type": 0}
            self.channels.append(ch)
            return ch
        raise AssertionError(f"unexpected Discord call {method} {path}")


def jobs_spec(spec):
    """The shipped jobs manager crons: three for the owner, two housekeeping ones."""
    spec["bots"]["jobs"]["cron"] = {
        "jobs-search": {"schedule": "0 * * * *", "script": "start_search.py", "agent": False, "notify": True},
        "jobs-followups": {"schedule": "0 9 * * 1-5", "script": "followup_gate.py", "agent": False, "notify": True},
        "jobs-watch": {"schedule": "*/30 * * * *", "script": "board_watch.py", "agent": False, "notify": True},
        "jobs-notices": {"schedule": "15 * * * *", "script": "application_notices.py", "agent": False,
                         "notify": True},
        "jobs-awake": {"schedule": "*/4 * * * *", "script": "keep_awake.py", "agent": False},
    }


@pytest.fixture
def jobs(tmp_path, monkeypatch, capsys):
    env = Env(tmp_path, monkeypatch)
    env.squad("jobs", jobs_spec)
    env.run("apply", "jobs", capsys=capsys)
    return env


def delivers(env):
    return {j["name"]: j["deliver"] for j in env.jobs("jobs")}


def give_token(env):
    (env.root / "profiles" / "jobs" / ".env").write_text("DISCORD_BOT_TOKEN=tok-jobs\n")


def connect(env, capsys, *extra, expect=0):
    return env.run("connect", "jobs", "discord", "--channel", "job-alerts", *extra, expect=expect, capsys=capsys)


def test_unconnected_manager_keeps_every_cron_on_bot_chat(jobs):
    assert set(delivers(jobs).values()) == {"bot-chat:jobs"}


def test_connect_creates_the_channel_moves_owner_crons_and_sends_a_test(jobs, monkeypatch, capsys):
    give_token(jobs)
    discord = FakeDiscord()
    monkeypatch.setattr(squadctl, "discord_api", discord)
    _, out = connect(jobs, capsys, "--create")
    assert out["channel"] == "#job-alerts" and out["test_message_id"] == "9001"
    assert ("POST", "/guilds/g1/channels") in discord.calls
    assert delivers(jobs) == {"jobs-search": f"discord:{CHANNEL}", "jobs-followups": f"discord:{CHANNEL}",
                              "jobs-watch": f"discord:{CHANNEL}", "jobs-notices": f"discord:{CHANNEL}",
                              "jobs-awake": "bot-chat:jobs"}
    cfg = jobs.config("jobs")
    assert cfg["platforms"]["discord"]["home_channel"]["chat_id"] == CHANNEL
    prompt = cfg["platforms"]["discord"]["channel_overrides"][CHANNEL]["system_prompt"]
    assert "mention-free" in prompt
    assert "MEDIA:<absolute path>" in prompt, "a CV sent as a bare path cannot be opened on the owner's phone"
    # 2026-10-27: every card-finished wake became a channel message and buried the few the owner had to answer.
    assert "exactly [SILENT]" in prompt and "clarify" in prompt, prompt
    assert cfg["cron"]["wrap_response"] is False, "a notice is the script's text, without the cron header and footer"
    assert cfg["discord"]["free_response_channels"] == CHANNEL  # a string: a list would become one bogus id
    sent = [json.loads(ln) for ln in (jobs.root / "sent.jsonl").read_text().splitlines()]
    assert sent[0]["to"] == f"discord:{CHANNEL}" and sent[0]["profile"] == "jobs"


def test_apply_and_upgrade_keep_owner_crons_on_the_connected_channel(jobs, monkeypatch, capsys):
    """The bug this guards: apply hard-coded bot-chat and moved the digest away from the channel the owner reads."""
    give_token(jobs)
    monkeypatch.setattr(squadctl, "discord_api", FakeDiscord())
    connect(jobs, capsys, "--create")
    _, out = jobs.run("apply", "jobs", capsys=capsys)
    (lead,) = [b for b in out["bots"] if b["bot"] == "jobs"]
    assert not any(a.startswith("cron") for a in lead.get("actions", [])), lead
    assert delivers(jobs)["jobs-watch"] == f"discord:{CHANNEL}"
    # a hand-moved job (the state before squadctl knew about channels) is also left where the owner put it
    jobs.run("upgrade", capsys=capsys)
    assert delivers(jobs)["jobs-search"] == f"discord:{CHANNEL}"
    assert delivers(jobs)["jobs-awake"] == "bot-chat:jobs"


def test_a_removed_token_sends_owner_crons_back_to_bot_chat_and_doctor_warns(jobs, monkeypatch, capsys):
    give_token(jobs)
    monkeypatch.setattr(squadctl, "discord_api", FakeDiscord())
    connect(jobs, capsys, "--create")
    _, out = jobs.run("doctor", "jobs", expect=None, capsys=capsys)
    assert {c["check"]: c["status"] for c in out["checks"]}["jobs:channel:discord"] == "ok"
    (jobs.root / "profiles" / "jobs" / ".env").write_text("")
    jobs.run("apply", "jobs", capsys=capsys)
    assert delivers(jobs)["jobs-watch"] == "bot-chat:jobs"  # a delivery to a dead channel would fail every run
    _, out = jobs.run("doctor", "jobs", expect=None, capsys=capsys)
    check = {c["check"]: c for c in out["checks"]}["jobs:channel:discord"]
    assert check["status"] == "warn" and "DISCORD_BOT_TOKEN" in check["detail"]


def test_doctor_warns_when_a_notify_job_was_moved_off_the_channel(jobs, monkeypatch, capsys):
    give_token(jobs)
    monkeypatch.setattr(squadctl, "discord_api", FakeDiscord())
    connect(jobs, capsys, "--create")
    path = jobs.root / "profiles" / "jobs" / "cron" / "jobs.json"
    data = json.loads(path.read_text())
    for j in data["jobs"]:
        if j["name"] == "jobs-followups":
            j["deliver"] = "bot-chat:jobs"
    path.write_text(json.dumps(data))
    _, out = jobs.run("doctor", "jobs", expect=None, capsys=capsys)
    check = {c["check"]: c for c in out["checks"]}["jobs:channel:discord"]
    assert check["status"] == "warn" and "jobs-followups" in check["detail"]


def test_connect_without_a_token_names_the_setup_command(jobs, capsys):
    _, out = connect(jobs, capsys, expect=2)
    assert "hermes -p jobs gateway setup" in out["error"]
    assert set(delivers(jobs).values()) == {"bot-chat:jobs"}


def test_connect_before_the_invite_is_accepted_prints_the_invite_link(jobs, monkeypatch, capsys):
    give_token(jobs)
    monkeypatch.setattr(squadctl, "discord_api", FakeDiscord(joined=False))
    _, out = connect(jobs, capsys, "--create", expect=2)
    assert "client_id=app42" in out["error"] and "permissions=" in out["error"]
    assert "platforms" not in jobs.config("jobs")


def test_connect_finds_an_existing_channel_by_name_and_never_creates_twice(jobs, monkeypatch, capsys):
    give_token(jobs)
    discord = FakeDiscord()
    discord.channels.append({"id": "555", "name": "job-alerts", "type": 0})
    monkeypatch.setattr(squadctl, "discord_api", discord)
    _, out = connect(jobs, capsys, "--create", "--no-test")
    assert out["chat_id"] == "555" and ("POST", "/guilds/g1/channels") not in discord.calls
    _, again = connect(jobs, capsys, "--no-test")
    assert again["actions"] == ["unchanged"]


def test_connect_without_manage_channels_says_to_create_it_by_hand(jobs, monkeypatch, capsys):
    give_token(jobs)
    monkeypatch.setattr(squadctl, "discord_api", FakeDiscord(manage=False))
    _, out = connect(jobs, capsys, "--create", expect=2)
    assert "create #job-alerts in Discord" in out["error"]


def test_connect_dry_run_writes_and_sends_nothing(jobs, monkeypatch, capsys):
    give_token(jobs)
    discord = FakeDiscord()
    monkeypatch.setattr(squadctl, "discord_api", discord)
    _, out = connect(jobs, capsys, "--create", "--dry-run")
    assert "discord channel + #job-alerts in Hermes" in out["actions"]
    assert any(a.startswith("cron ~ jobs-watch") for a in out["actions"])
    assert ("POST", "/guilds/g1/channels") not in discord.calls
    assert set(delivers(jobs).values()) == {"bot-chat:jobs"}
    assert not (jobs.root / "sent.jsonl").exists()


def test_connect_keeps_other_free_response_channels(jobs, monkeypatch, capsys):
    give_token(jobs)
    cfg = jobs.config("jobs")
    cfg["discord"] = {"free_response_channels": "123"}
    (jobs.root / "profiles" / "jobs" / "config.yaml").write_text(yaml.safe_dump(cfg))
    monkeypatch.setattr(squadctl, "discord_api", FakeDiscord())
    connect(jobs, capsys, "--create", "--no-test")
    assert jobs.config("jobs")["discord"]["free_response_channels"] == f"123,{CHANNEL}"


def test_telegram_connect_takes_a_chat_id(jobs, capsys):
    (jobs.root / "profiles" / "jobs" / ".env").write_text("TELEGRAM_BOT_TOKEN=t\n")
    _, out = jobs.run("connect", "jobs", "telegram", "--chat-id", "-100200", "--name", "Job alerts",
                      capsys=capsys)
    assert out["test_message_id"] == "9001"
    assert delivers(jobs)["jobs-search"] == "telegram:-100200"
    assert delivers(jobs)["jobs-awake"] == "bot-chat:jobs"


def test_shipped_squads_mark_only_user_facing_crons_notify():
    """Owner-facing crons (digests, board watch, reports) notify; housekeeping (awake, projects, sweep) never does."""
    for key in ("jobs", "web", "marketing"):
        spec = yaml.safe_load((REPO / "squads" / key / "squad.yaml").read_text())
        crons = spec["bots"][key]["cron"]
        assert crons[f"{key}-watch"].get("notify") is True, key
        if key == "jobs":  # the sent-application notice is the one message auto mode owes the owner
            assert crons["jobs-notices"].get("notify") is True
        for house in ("awake", "projects"):
            assert not crons[f"{key}-{house}"].get("notify"), (key, house)
