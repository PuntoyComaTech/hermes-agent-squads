"""model_advisor.py: lane picking, review-family rule, provider detection and golden outputs."""
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"
GOLDEN = REPO / "tests" / "golden" / "model_advisor"
SCRIPT = REPO / "scripts" / "model_advisor.py"
NOW = 1792022400.0 + 3600
SQUADS = ["web", "marketing", "jobs", "studio", "builder"]
CACHES = sorted(p.stem for p in (FIX / "caches").glob("*.json"))

spec = importlib.util.spec_from_file_location("model_advisor", SCRIPT)
ma = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ma)


@pytest.fixture(autouse=True)
def temp_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home


def advise(capsys, *argv, cache="copilot-opencode-go", providers="cache", squads=()):
    args = [*(str(FIX / "squads" / f"{s}.yaml") for s in squads), "--json", "--now", str(NOW),
            "--providers", providers, "--local-roles", str(FIX / "nonexistent.yaml"), *argv]
    if cache:
        args += ["--cache", str(cache if isinstance(cache, Path) else FIX / "caches" / f"{cache}.json")]
    code = ma.main(args)
    return code, json.loads(capsys.readouterr().out)


def bots(result, squad):
    return {b["bot"]: b for s in result["squads"] if s["key"] == squad for b in s["bots"]}


@pytest.fixture
def all_families(tmp_path):
    merged = {}
    for name in ("anthropic-only", "copilot-opencode-go"):
        merged.update(json.loads((FIX / "caches" / f"{name}.json").read_text()))
    path = tmp_path / "all.json"
    path.write_text(json.dumps(merged))
    return path


# --- golden outputs ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("cache", CACHES)
def test_golden(cache, capsys):
    code, result = advise(capsys, cache=cache, squads=SQUADS)
    assert code == 0
    golden = GOLDEN / f"{cache}.json"
    if os.environ.get("UPDATE_GOLDEN"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(json.dumps(result, indent=2) + "\n")
    assert result == json.loads(golden.read_text())


@pytest.mark.parametrize("cache", CACHES)
def test_every_bot_has_pick_alternatives_and_reason(cache, capsys):
    _, result = advise(capsys, cache=cache, squads=SQUADS)
    for squad in result["squads"]:
        for bot in squad["bots"]:
            assert bot["model"] and bot["provider"] and bot["reasoning"] and bot["reason"]
            assert len(bot["alternatives"]) <= 2
            assert result["providers"]["authenticated"]
            assert bot["provider"] in {p["slug"] for p in result["providers"]["authenticated"]}


# --- review lane ------------------------------------------------------------------------------------------------

def test_review_prefers_a_family_no_producer_uses(capsys, all_families):
    _, result = advise(capsys, cache=all_families, squads=["web"])
    web = bots(result, "web")
    producers = {web[b]["provider"] for b in ("web-frontend", "web-backend", "web-deployer")}
    review = web["web-qa"]
    assert review["provider"] not in producers
    assert review["model"] == "gpt-5.4" and "differs from the producers" in review["reason"]


def test_review_lane_avoids_requested_producer_family(capsys, all_families):
    _, result = advise(capsys, "--lane", "review", "--producer-lane", "design", cache=all_families)
    pick = result["lanes"][0]
    assert pick["provider"] == "opencode-go" and pick["model"] == "mimo-v2.6-pro"
    _, plain = advise(capsys, "--lane", "review", cache=all_families)
    assert plain["lanes"][0]["model"] == "mimo-v2.6-pro"
    _, vs_open = advise(capsys, "--lane", "review", "--producer-lane", "code", cache=all_families)
    assert vs_open["lanes"][0]["provider"] != "opencode-go"


def test_review_with_one_family_says_so(capsys):
    _, result = advise(capsys, cache="anthropic-only", squads=["web"])
    assert "only one family available" in bots(result, "web")["web-qa"]["reason"]


def test_review_chain_stage_lane_is_an_extra(capsys, all_families):
    _, result = advise(capsys, cache=all_families, squads=["jobs"])
    extras = bots(result, "jobs")["jobs-scout"]["extras"]
    assert [e["use"] for e in extras] == ["chain:application/analyze"] and extras[0]["lane"] == "review"


def test_delegation_and_shared_lanes(capsys):
    _, result = advise(capsys, cache="anthropic-only", squads=["web"])
    assert bots(result, "web")["web-backend"]["extras"][0]["use"] == "delegation"
    assert {s["use"] for s in result["squads"][0]["shared"]} == {"aux", "vision"}


# --- lanes, fallbacks, overrides --------------------------------------------------------------------------------

def test_lane_table_without_squads_lists_every_lane(capsys):
    _, result = advise(capsys, cache="opencode-go-only")
    assert {p["lane"] for p in result["lanes"]} == {"design", "lead", "code", "advisor", "review", "copy", "research",
                                                  "digest", "aux", "vision"}


def test_regex_survives_provider_renames(capsys):
    # a Copilot catalog serving claude-opus-5.5 gets it on the design lane via provider_pref
    _, dotted = advise(capsys, "--lane", "design", cache="copilot-opencode-go", providers="copilot")
    assert dotted["lanes"][0]["model"] == "claude-opus-5.5" and dotted["lanes"][0]["provider"] == "copilot"
    _, dashed = advise(capsys, "--lane", "design", cache="anthropic-only", providers="anthropic")
    assert dashed["lanes"][0]["model"] == "claude-opus-5-5"


def test_providers_list_restricts_to_named_providers(capsys):
    _, result = advise(capsys, "--lane", "code", providers="copilot")
    assert [p["slug"] for p in result["providers"]["authenticated"]] == ["copilot"]
    assert result["lanes"][0]["provider"] == "copilot"


def test_fallback_cheapest_for_unknown_provider(tmp_path, capsys):
    cache = tmp_path / "custom.json"
    cache.write_text(json.dumps({"custom-x": {"at": NOW, "models": ["big-model-1", "tiny-mini", "other"]}}))
    _, result = advise(capsys, "--lane", "design", "--lane", "aux", cache=cache)
    for pick in result["lanes"]:
        assert (pick["model"], pick["provider"]) == ("tiny-mini", "custom-x")
        assert "no candidate matches" in pick["reason"]


def test_local_override_replaces_lane_candidates(tmp_path, capsys):
    local = tmp_path / "model-roles.yaml"
    local.write_text("lanes:\n  design:\n    candidates:\n      - {family: open-weights, match: 'glm-5\\.3', reasoning: low}\n")
    code = ma.main(["--lane", "design", "--json", "--providers", "cache", "--local-roles", str(local),
                    "--cache", str(FIX / "caches" / "copilot-opencode-go.json")])
    out = json.loads(capsys.readouterr().out)
    assert code == 0 and out["roles"] == ["base", "local"]
    assert (out["lanes"][0]["model"], out["lanes"][0]["reasoning"]) == ("glm-5.3", "low")


def test_alternatives_are_distinct_and_capped(capsys):
    _, result = advise(capsys, "--lane", "lead", cache="anthropic-only")
    pick = result["lanes"][0]
    alts = [(a["model"], a["provider"]) for a in pick["alternatives"]]
    assert len(alts) == 2 and len(set(alts)) == 2 and (pick["model"], pick["provider"]) not in alts


# --- providers, cache, errors -----------------------------------------------------------------------------------

def test_stale_cache_entries_are_reported(capsys):
    _, fresh = advise(capsys, "--lane", "lead", cache="anthropic-only")
    assert fresh["providers"]["stale"] == []
    args = ["--lane", "lead", "--json", "--providers", "cache", "--now", str(NOW + 8 * 86400),
            "--cache", str(FIX / "caches" / "anthropic-only.json")]
    ma.main(args)
    stale = json.loads(capsys.readouterr().out)["providers"]["stale"]
    assert sorted(stale) == ["anthropic", "claude-subscription-directsdk-experimental"]


def test_detection_models_fill_providers_missing_from_cache(monkeypatch, capsys):
    monkeypatch.setattr(ma, "probe_in_process", lambda: [
        {"slug": "nous", "models": ["deepseek-v4.1-flash", "claude-opus-5.5"]},
        {"slug": "opencode-go", "models": ["only-in-probe"]}])
    code, result = advise(capsys, "--lane", "code", providers="auto", cache="copilot-opencode-go")
    assert code == 0 and result["providers"]["source"] == "in-process"
    by_slug = {p["slug"]: p for p in result["providers"]["authenticated"]}
    assert by_slug["nous"]["models"] == 2, "no cache entry: the detection call's models are used"
    assert by_slug["opencode-go"]["models"] == 45, "cache entry wins over the detection call's models"
    assert result["lanes"][0]["provider"] == "opencode-go"


def test_detection_models_are_used_for_a_provider_without_cache(monkeypatch, capsys):
    monkeypatch.setattr(ma, "probe_in_process", lambda: [{"slug": "nous", "models": ["deepseek-v4.1-flash"]}])
    _, result = advise(capsys, "--lane", "code", providers="auto", cache="copilot-opencode-go")
    assert (result["lanes"][0]["model"], result["lanes"][0]["provider"]) == ("deepseek-v4.1-flash", "nous")


def test_detection_falls_back_through_runtime_to_auth_list(monkeypatch, capsys):
    for name in ("probe_in_process", "probe_runtime"):
        monkeypatch.setattr(ma, name, lambda: None)
    sample = ("copilot (1 credentials):\n  #1  gh auth token  api_key sk-should-not-be-read priority=0\n\n"
              "opencode-go (1 credentials):\n  #1  OPENCODE_GO_API_KEY  api_key id=242ecf priority=0 env:X <-\n")
    monkeypatch.setattr(ma.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, sample, ""))
    assert ma.probe_auth_list() == [{"slug": "copilot", "models": []}, {"slug": "opencode-go", "models": []}]
    code, result = advise(capsys, "--lane", "lead", providers="auto")
    assert code == 0 and result["providers"]["source"] == "auth-list"
    assert "sk-should-not-be-read" not in json.dumps(result)


def test_no_provider_is_a_structured_error(monkeypatch, capsys):
    for name in ("probe_in_process", "probe_runtime", "probe_auth_list"):
        monkeypatch.setattr(ma, name, lambda: None)
    code, result = advise(capsys, "--lane", "lead", providers="auto")
    assert code == 2 and "no authenticated provider" in result["error"]


def test_unknown_lane_and_missing_squad_are_errors(capsys):
    code, result = advise(capsys, "--lane", "nonsense")
    assert code == 2 and "unknown lane" in result["error"]
    code = ma.main(["no-such-squad", "--json", "--providers", "cache", "--cache", str(FIX / "caches" / "anthropic-only.json")])
    assert code == 2 and "squad not found" in json.loads(capsys.readouterr().out)["error"]


def test_default_cache_prefers_profile_then_root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    profile = root / "profiles" / "builder"
    profile.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(profile))
    assert ma.default_cache_path() == root / "provider_models_cache.json"
    (profile / "provider_models_cache.json").write_text("{}")
    assert ma.default_cache_path() == profile / "provider_models_cache.json"


def test_cache_file_is_never_modified(tmp_path, capsys):
    cache = tmp_path / "c.json"
    cache.write_text((FIX / "caches" / "anthropic-only.json").read_text())
    before = cache.read_bytes()
    advise(capsys, "--lane", "lead", cache=cache)
    assert cache.read_bytes() == before


def test_help_works_without_network(temp_home):
    out = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True,
                         env={"HERMES_HOME": str(temp_home), "PATH": "/nonexistent"}, timeout=30)
    assert out.returncode == 0 and "--json" in out.stdout and "--providers" in out.stdout


@pytest.mark.skipif(not os.environ.get("RUN_HERMES_TESTS"), reason="needs the real hermes binary; set RUN_HERMES_TESTS=1")
def test_real_runtime_probe_with_empty_home(temp_home):
    rows = ma.probe_runtime()
    assert rows is None or isinstance(rows, list)
