"""catalog_search.py: plugin catalog, optional/bundled skills, MCP and connectors, env names, hub, golden outputs."""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "tests" / "fixtures" / "hermes-src"
GOLDEN = REPO / "tests" / "golden" / "catalog_search"
SCRIPT = REPO / "scripts" / "catalog_search.py"
QUERIES = {
    "blender": ["blender"],
    "video-gsap": ["video", "gsap"],
    "connector": ["neon_mcp", "context7"],
    "env-names": ["CLOUDFLARE_API_TOKEN", "SHOPIFY_SHOP"],
    "design": ["design"],
    "empty": ["remotion", "or-picker"],
}

spec = importlib.util.spec_from_file_location("catalog_search", SCRIPT)
cs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cs)


@pytest.fixture(autouse=True)
def temp_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.delenv("HERMES_SRC", raising=False)


def search(capsys, *argv, src=SRC):
    code = cs.main([*argv, "--hermes-src", str(src), "--json"])
    return code, json.loads(capsys.readouterr().out)


def ids(result, i=0):
    return [r["id"] for r in result["queries"][i]["results"]]


@pytest.mark.parametrize("name", sorted(QUERIES))
def test_golden(name, capsys):
    code, result = search(capsys, *QUERIES[name])
    assert code == 0
    golden = GOLDEN / f"{name}.json"
    if os.environ.get("UPDATE_GOLDEN"):
        golden.parent.mkdir(parents=True, exist_ok=True)
        golden.write_text(json.dumps(result, indent=2) + "\n")
    assert result == json.loads(golden.read_text())


def test_blender_resolves_to_the_official_plugin(capsys):
    _, result = search(capsys, "blender")
    first = result["queries"][0]["results"][0]
    assert (first["id"], first["kind"], first["tier"]) == ("blender", "plugin", "official")
    assert first["needs_ok"] and "arbitrary Python" in first["disclosure"]
    assert first["install"] == "hermes plugins install blender"
    assert ids(result) == ["blender", "blender-render-helper"]


def test_community_plugin_needs_ok_and_quotes_licence(capsys):
    _, result = search(capsys, "video")
    editor = next(r for r in result["queries"][0]["results"] if r["id"] == "hermes-video-editor")
    assert editor["tier"] == "community" and editor["needs_ok"] and "PolyForm Noncommercial" in editor["disclosure"]


def test_words_are_anded(capsys):
    _, result = search(capsys, "blender render")
    assert ids(result) == ["blender-render-helper"]


def test_kill_list_entries_are_excluded(capsys):
    _, result = search(capsys, "or-picker", "removed picker")
    assert ids(result, 0) == [] and ids(result, 1) == []
    assert result["queries"][0]["total"] == 0


def test_skill_ids_match_the_keep_syntax(capsys):
    _, result = search(capsys, "design", "llama", "test-driven")
    assert ids(result, 0) == ["bundled:claude-design", "official:creative/impeccable"]
    assert ids(result, 1) == ["official:mlops/inference/llama-cpp"]
    assert ids(result, 2) == ["bundled:test-driven-development"]


def test_mcp_and_connector_names(capsys):
    _, result = search(capsys, "neon_mcp", "neon", "postgres", "context7")
    neon = result["queries"][0]["results"][0]
    assert (neon["id"], neon["connector"], neon["kind"]) == ("mcp:neon", "neon_mcp", "mcp")
    assert ids(result, 1) == ids(result, 2) == ["mcp:neon"]
    assert result["queries"][3]["results"][0]["connector"] is None
    assert neon["install"] == "hermes mcp install neon"


def test_env_names_are_searchable_and_listed(capsys, monkeypatch):
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "super-secret-value-123")
    code = cs.main(["CLOUDFLARE_API_TOKEN", "--hermes-src", str(SRC), "--json"])
    out = capsys.readouterr().out
    assert code == 0 and "super-secret-value-123" not in out
    hit = json.loads(out)["queries"][0]["results"][0]
    assert hit["id"] == "cloudflare-pages" and hit["env"] == ["CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"]
    _, result = search(capsys, "SHOPIFY_SHOP")
    assert result["queries"][0]["results"][0]["env"] == ["SHOPIFY_ACCESS_TOKEN", "SHOPIFY_SHOP"]


def test_kind_filter_and_limit(capsys):
    _, result = search(capsys, "design", "--kind", "plugin")
    assert ids(result) == []
    _, result = search(capsys, "e", "--limit", "2")
    assert len(result["queries"][0]["results"]) == 2 and result["queries"][0]["total"] > 2
    assert cs.main(["x", "--kind", "nope", "--hermes-src", str(SRC), "--json"]) == 2
    assert "unknown kind" in json.loads(capsys.readouterr().out)["error"]


def test_ranking_is_deterministic_and_prefers_official(capsys):
    _, one = search(capsys, "blender")
    _, two = search(capsys, "blender")
    assert one == two
    scores = [r["score"] for r in one["queries"][0]["results"]]
    assert scores == sorted(scores, reverse=True)


def test_missing_source_dirs_warn_and_missing_tree_errors(tmp_path, capsys):
    partial = tmp_path / "src"
    (partial / "optional-mcps").parent.mkdir()
    (partial / "optional-mcps").symlink_to(SRC / "optional-mcps")
    code, result = search(capsys, "neon", src=partial)
    assert code == 0 and ids(result) == ["mcp:neon"]
    assert any("plugin-catalog/ not found" in w for w in result["warnings"])
    empty = tmp_path / "empty"
    empty.mkdir()
    code, result = search(capsys, "neon", src=empty)
    assert code == 2 and "no catalog entries" in result["error"]
    code, result = search(capsys, "neon", src=tmp_path / "missing")
    assert code == 2 and "source tree not found" in result["error"]


def test_malformed_entries_do_not_stop_the_search(tmp_path, capsys):
    src = tmp_path / "src"
    (src / "plugin-catalog").mkdir(parents=True)
    (src / "plugin-catalog" / "bad.yaml").write_text("name: [unclosed\n")
    (src / "plugin-catalog" / "good.yaml").write_text("name: good\ndescription: ok\ntier: official\n")
    (src / "skills" / "x" / "broken").mkdir(parents=True)
    (src / "skills" / "x" / "broken" / "SKILL.md").write_text("---\nname: [oops\n---\n")
    code, result = search(capsys, "good", src=src)
    assert code == 0 and ids(result) == ["good"]


def test_hub_results_are_mapped_and_deduped(monkeypatch, capsys):
    rows = [
        {"name": "hyperframes", "identifier": "official/creative/hyperframes", "trust_level": "builtin",
         "description": "dup of the local official skill"},
        {"name": "gsap", "identifier": "skills-sh/mengto/skills/gsap", "trust_level": "community",
         "description": "Indexed by skills.sh"},
        {"name": "newskill", "identifier": "official/creative/newskill", "trust_level": "builtin", "description": "gsap too"},
    ]
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, json.dumps(rows), "")

    monkeypatch.setattr(cs.subprocess, "run", fake_run)
    code, result = search(capsys, "gsap", "--hub")
    assert code == 0 and calls == [["hermes", "skills", "search", "gsap", "--json", "--limit", "8"]]
    by_id = {r["id"]: r for r in result["queries"][0]["results"]}
    assert set(by_id) == {"official:creative/hyperframes", "hub:skills-sh/mengto/skills/gsap",
                          "official:creative/newskill"}
    assert by_id["hub:skills-sh/mengto/skills/gsap"]["needs_ok"] and by_id["hub:skills-sh/mengto/skills/gsap"]["tier"] == "community"
    assert not by_id["official:creative/newskill"]["needs_ok"]
    assert by_id["hub:skills-sh/mengto/skills/gsap"]["install"] == "hermes skills install skills-sh/mengto/skills/gsap"


def test_hub_failure_is_a_warning_not_an_error(monkeypatch, capsys):
    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(cs.subprocess, "run", boom)
    code, result = search(capsys, "gsap", "--hub")
    assert code == 0 and ids(result) == ["official:creative/hyperframes"]
    assert any("hub search failed" in w for w in result["warnings"])


def test_hub_is_off_by_default(monkeypatch, capsys):
    monkeypatch.setattr(cs.subprocess, "run", lambda *a, **k: pytest.fail("network call without --hub"))
    search(capsys, "gsap")


def test_text_output_has_definitive_empty_state(capsys):
    assert cs.main(["remotion", "--hermes-src", str(SRC)]) == 0
    assert "remotion: 0 match(es), none found" in capsys.readouterr().out


def test_help_works_without_network(temp_home):
    out = subprocess.run([sys.executable, str(SCRIPT), "--help"], capture_output=True, text=True,
                         env={"HERMES_HOME": str(temp_home), "PATH": "/nonexistent"}, timeout=30)
    assert out.returncode == 0 and "--hub" in out.stdout and "--json" in out.stdout


@pytest.mark.skipif(not os.environ.get("RUN_HERMES_TESTS"), reason="needs the real Hermes tree; set RUN_HERMES_TESTS=1")
def test_real_tree_resolves_blender_to_official(monkeypatch, capsys):
    monkeypatch.delenv("HERMES_HOME")
    code = cs.main(["blender", "--json"])
    first = json.loads(capsys.readouterr().out)["queries"][0]["results"][0]
    assert code == 0 and (first["id"], first["tier"]) == ("blender", "official")
