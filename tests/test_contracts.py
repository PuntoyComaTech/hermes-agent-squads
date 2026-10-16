"""Batch 0 contracts: squad schema, model-roles lanes, always-disabled toolsets, lint fixtures."""
import copy
import json
import os
import re
from fnmatch import fnmatch
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures"
SCHEMA = json.loads((REPO / "squads" / "_schema" / "squad.schema.json").read_text())
ROLES = yaml.safe_load((REPO / "scripts" / "data" / "model-roles.yaml").read_text())
ALWAYS_DISABLED = yaml.safe_load((REPO / "scripts" / "data" / "always-disabled.yaml").read_text())["always_disabled"]
VALIDATOR = Draft202012Validator(SCHEMA)

SQUADS = ["web", "marketing", "jobs"]
DRAFTS = SQUADS + ["builder"]
CACHES = sorted(p.stem for p in (FIX / "caches").glob("*.json"))
PLAN_LANES = {"manager", "frontend", "design-pro", "code-complex", "code-routine", "review", "deploy",
              "research", "digest", "aux", "vision"}
# Deprecated lane names kept as {alias_of: ...} so old squad.yaml files still resolve (a later card renames them).
ALIAS_LANES = {"lead": "manager", "design": "design-pro", "code": "code-routine", "advisor": "code-complex",
               "copy": "manager"}


def load_draft(name):
    return yaml.safe_load((FIX / "squads" / f"{name}.yaml").read_text())


def load_cache(name):
    return json.loads((FIX / "caches" / f"{name}.json").read_text())


def errors(doc):
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}" for e in VALIDATOR.iter_errors(doc)]


def lanes_used(doc):
    used = {v for k, v in (doc.get("defaults") or {}).items() if k.endswith("_lane")}
    for bot in doc["bots"].values():
        used.add(bot["lane"])
        if (bot.get("delegation") or {}).get("lane"):
            used.add(bot["delegation"]["lane"])
        for job in (bot.get("cron") or {}).values():
            if isinstance(job.get("agent"), dict):
                used.add(job["agent"]["lane"])
    for stages in (doc.get("chains") or {}).values():
        used.update(s["lane"] for s in stages if "lane" in s)
    return used


# --- schema ---------------------------------------------------------------------------------------------------

def test_schema_is_valid_draft_2020_12():
    Draft202012Validator.check_schema(SCHEMA)
    assert SCHEMA["$schema"] == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.parametrize("name", DRAFTS)
def test_draft_validates(name):
    assert errors(load_draft(name)) == []


@pytest.mark.parametrize("name", DRAFTS)
def test_draft_cross_field_rules(name):
    doc = load_draft(name)
    bots = doc["bots"]
    assert doc["manager"] in bots and bots[doc["manager"]]["role"] == "manager"
    assert [b for b, spec in bots.items() if spec["role"] == "manager"] == [doc["manager"]]
    for stages in (doc.get("chains") or {}).values():
        for stage in stages:
            assert stage["assignee"] in bots, stage
    assert lanes_used(doc) <= set(ROLES["lanes"]), lanes_used(doc) - set(ROLES["lanes"])
    for bot, spec in bots.items():
        assert not set(spec["toolsets"]) & set(ALWAYS_DISABLED), bot
        if spec["role"] == "worker":
            assert bot.startswith(f"{doc['key']}-"), bot


def test_draft_manager_naming():
    """C-11: the manager is the bot named after the squad key, titled '<Name> manager'; workers <key>-<role>."""
    for name in SQUADS:
        doc = load_draft(name)
        bots = doc["bots"]
        assert doc["manager"] == doc["key"] == name
        assert bots[name]["title"] == f"{doc['name']} manager"
        assert "hidden" not in bots[name]
        assert all("hidden" not in spec for spec in bots.values())


def test_stage_lane_carries_no_per_card_effort():
    """Per-card override is model+provider only: `hermes kanban create`, `set-model` and the
    `kanban_create` tool have no reasoning-effort flag. The chain stage must not claim one, and the
    reference must document the real path (dashboard `reasoning_effort`, V-07 profiles)."""
    stage = SCHEMA["$defs"]["stage"]["properties"]
    assert "reasoning" not in stage and set(stage) == {"stage", "assignee", "skill", "when", "lane"}
    ref = (REPO / "skills" / "hermes-platform" / "references" / "kanban.md").read_text()
    assert "reasoning-effort flag on `hermes kanban create`" in ref
    assert "reasoning_effort" in ref and "dedicated profile" in ref


def test_bot_context_carries_no_citations_or_decision_ids():
    """Bot-loaded files state facts: no decision ids, decision-log pointers or Hermes source citations."""
    bad = re.compile(r"\b[CVD]-\d{2,3}\b|docs/decisions\.md|\(`(?:website/docs|hermes_cli|tools|gateway|apps/desktop)/"
                     r"|`hermes [^`]*--help`\)")
    files = [REPO / "SOUL.md", *(REPO / "skills").rglob("*.md"), *(REPO / "skills").rglob("evals.json"),
             *(REPO / "squads").rglob("*.md"), *(REPO / "squads").rglob("evals.json")]
    hits = [f"{p.relative_to(REPO)}:{i}" for p in files for i, line in enumerate(p.read_text().splitlines(), 1)
            if bad.search(line)]
    assert hits == []


def test_shipped_manifests_validate_and_name_the_manager():
    """The shipped builder.yaml and squads/*/squad.yaml hold the same contract the fixtures hold."""
    paths = [REPO / "builder.yaml", *sorted((REPO / "squads").glob("*/squad.yaml"))]
    assert len(paths) == len(SQUADS) + 1
    for path in paths:
        doc = yaml.safe_load(path.read_text())
        assert errors(doc) == [], (path, errors(doc))
        bots = doc["bots"]
        assert [b for b, spec in bots.items() if spec["role"] == "manager"] == [doc["manager"]], path
        if path.name != "builder.yaml":
            assert doc["manager"] == doc["key"], path
            assert bots[doc["manager"]]["title"] == f"{doc['name']} manager", path
        for bot, spec in bots.items():
            assert "hidden" not in spec, (path, bot)
            if spec["role"] == "worker":
                assert bot.startswith(f"{doc['key']}-"), (path, bot)
            assert not set(spec["toolsets"]) & set(ALWAYS_DISABLED), (path, bot)
        assert len([b for b, spec in bots.items() if not spec.get("optional")]) <= 5, path
    web = yaml.safe_load((REPO / "squads" / "web" / "squad.yaml").read_text())
    pro = web["bots"]["web-frontend-pro"]
    assert pro["optional"] is True and pro["role"] == "worker" and pro["lane"] == "design-pro"


def test_the_deployer_logs_in_with_the_clis_instead_of_a_passed_token():
    """D-036: deploys use the CLIs' own logins (`gh auth login`, `cf auth login`), never a token in the
    profile env; the deployer declares the CLIs so `doctor` reports them installed and logged in."""
    web = yaml.safe_load((REPO / "squads" / "web" / "squad.yaml").read_text())
    deployer = web["bots"]["web-deployer"]
    assert deployer["requires"] == {"apps": ["cf", "wrangler", "gh"]}
    assert "passthrough" not in deployer
    assert "vercel_mcp" not in deployer["connectors"]["suggest"], "Vercel is opt-in per project, never suggested"
    assert not any(bot.get("passthrough") for bot in web["bots"].values())


def test_the_release_version_lives_only_in_distribution_yaml():
    """C-13: builder.yaml carries no version; distribution.yaml -> version is the single source of truth."""
    assert "version" not in yaml.safe_load((REPO / "builder.yaml").read_text())
    dist = yaml.safe_load((REPO / "distribution.yaml").read_text())
    assert re.fullmatch(r"\d+\.\d+\.\d+", str(dist.get("version") or "")), dist.get("version")


def _mutations():
    def drop(key):
        return lambda d: d.pop(key)
    return {
        "schema-1": lambda d: d.update(schema=1),
        "no-manager": drop("manager"),
        "no-bots": drop("bots"),
        "unknown-top-key": lambda d: d.update(orchestration_skills="skills/orchestration"),
        "unknown-bot-key": lambda d: d["bots"]["web-frontend"].update(model="claude-opus-5-5"),
        "bad-role": lambda d: d["bots"]["web-frontend"].update(role="specialist"),
        "bad-reasoning": lambda d: d["bots"]["web-frontend"].update(reasoning="extreme"),
        "bad-keep-prefix": lambda d: d["bots"]["web-frontend"]["skills"]["keep"].append("link:accessibility"),
        "passthrough-value": lambda d: d["bots"]["web-qa"].update(passthrough=["ghp_abc123"]),
        "app-spec-value": lambda d: d["bots"]["web-deployer"]["requires"]["apps"].append("GH_TOKEN"),
        "bot-without-lane": lambda d: d["bots"]["web-qa"].pop("lane"),
        "cron-agent-true": lambda d: d["bots"]["web"]["cron"]["web-watch"].update(agent=True),
        "plugin-confirm-missing": lambda d: d["bots"]["web-qa"]["plugins"]["enable"].append({"name": "blender"}),
        "stage-without-assignee": lambda d: d["chains"]["milestone"][0].pop("assignee"),
        "bad-board-color": lambda d: d["board"].update(color="blue"),
    }


@pytest.mark.parametrize("case", sorted(_mutations()))
def test_schema_rejects(case):
    doc = copy.deepcopy(load_draft("web"))
    _mutations()[case](doc)
    assert errors(doc), case

# --- model-roles ------------------------------------------------------------------------------------------------

def test_model_roles_covers_every_plan_lane():
    assert set(ROLES["lanes"]) == PLAN_LANES | set(ALIAS_LANES)


def test_alias_lanes_point_at_live_lanes():
    for alias, target in ALIAS_LANES.items():
        assert ROLES["lanes"][alias] == {"alias_of": target}, alias
        assert target in PLAN_LANES
    assert all(ROLES["lanes"][lane].get("alias_of") not in ALIAS_LANES for lane in ALIAS_LANES), "no alias chains"


@pytest.mark.parametrize("lane", sorted(PLAN_LANES))
def test_lane_shape(lane):
    spec = ROLES["lanes"][lane]
    assert spec["why"] and spec["used_by"] and spec["candidates"]
    assert spec["reasoning"] in SCHEMA["$defs"]["reasoning"]["enum"]
    assert spec["fallback"] in {"cheapest", "first-choice-provider"}
    for cand in spec["candidates"]:
        assert set(cand) <= {"family", "match", "provider_pref", "reasoning"}, cand
        assert cand["family"] in ROLES["families"], cand
        assert cand.get("reasoning", spec["reasoning"]) in SCHEMA["$defs"]["reasoning"]["enum"]
        re.compile(cand["match"])
    assert {c["family"] for c in spec["candidates"]} == set(ROLES["families"]), "every family needs a candidate"


def providers_for(cand):
    return cand.get("provider_pref") or ROLES["families"][cand["family"]]


def families_present(cache):
    return {fam for fam, globs in ROLES["families"].items() if any(fnmatch(s, g) for s in cache for g in globs)}


def candidate_hits(cand, cache):
    return [(slug, m) for slug, entry in cache.items() if any(fnmatch(slug, g) for g in providers_for(cand))
            for m in entry["models"] if re.fullmatch(cand["match"], m)]


@pytest.mark.parametrize("cache_name", CACHES)
@pytest.mark.parametrize("lane", sorted(PLAN_LANES))
def test_lane_matches_fixture_cache(lane, cache_name):
    cache = load_cache(cache_name)
    present = families_present(cache)
    assert present, f"{cache_name} has no known family"
    for fam in present:
        hits = [h for c in ROLES["lanes"][lane]["candidates"] if c["family"] == fam for h in candidate_hits(c, cache)]
        assert hits, f"lane {lane}: no {fam} candidate matches {cache_name}"


def test_regexes_do_not_overmatch_variants():
    cands = {c["match"] for name, lane in ROLES["lanes"].items() if name in PLAN_LANES for c in lane["candidates"]}
    variants = ["gpt-5.4-mini", "gpt-5.4-nano", "glm-5.3-flash", "kimi-k3-base", "deepseek-v4-flash",
                "mimo-v2.6-flash", "claude-opus-5", "claude-sonnet-5[1m]"]
    for v in variants:
        hits = [p for p in cands if re.fullmatch(p, v)]
        assert hits in ([], ["gpt-5\\.\\d+-mini"]), (v, hits)


# --- fixtures ---------------------------------------------------------------------------------------------------

def test_fixture_caches():
    assert CACHES == ["anthropic-only", "copilot-opencode-go", "opencode-go-only"]
    for name in CACHES:
        for slug, entry in load_cache(name).items():
            assert set(entry) == {"fp", "at", "models"} and entry["fp"] == "fixture", slug
            assert entry["models"] and all(isinstance(m, str) for m in entry["models"]), slug
    assert all(s.startswith("claude-subscription") or s == "anthropic" for s in load_cache("anthropic-only"))


def test_model_ids_only_in_data():
    patterns = [c["match"] for name, lane in ROLES["lanes"].items() if name in PLAN_LANES for c in lane["candidates"]]
    files = list((FIX / "squads").glob("*.yaml")) + [p for p in (FIX / "skills" / "good").rglob("*") if p.is_file()]
    for f in files:
        text = f.read_text()
        for p in patterns:
            assert not re.search(rf"(?<![\w.-]){p}(?![\w.])", text), (f, p)


def test_one_bad_fixture_per_lint_rule():
    bad = FIX / "skills" / "bad"
    rules = yaml.safe_load((bad / "rules.yaml").read_text())["rules"]
    assert {p.name for p in bad.iterdir() if p.is_dir()} == set(rules)
    for rule in rules:
        assert any((bad / rule).rglob("SKILL.md")) or any((bad / rule).glob("souls/*.md")) \
            or any((bad / rule).glob("*.yaml")), rule
    good = FIX / "skills" / "good"
    assert (good / "building-widgets" / "SKILL.md").is_file() and (good / "souls").is_dir()


# --- always-disabled --------------------------------------------------------------------------------------------

def test_always_disabled_shape():
    assert ALWAYS_DISABLED == sorted(set(ALWAYS_DISABLED))
    assert not {"setup", "start_chat", "stt"} & set(ALWAYS_DISABLED)


HERMES_SRC = Path(os.environ.get("HERMES_AGENT_SRC", Path.home() / ".hermes" / "hermes-agent"))


@pytest.mark.skipif(not (HERMES_SRC / "toolsets.py").is_file(), reason="Hermes source tree not available")
def test_always_disabled_names_exist_in_hermes():
    static = (HERMES_SRC / "toolsets.py").read_text()
    plugin_text = "\n".join(p.read_text() for p in (HERMES_SRC / "plugins").rglob("*.py"))
    for name in ALWAYS_DISABLED:
        assert f'"{name}":' in static or f'toolset="{name}"' in plugin_text, name


def hermes_configurable_toolsets() -> set[str]:
    """CONFIGURABLE_TOOLSETS keys of the real hermes_cli/tools_config.py: what `hermes tools enable` accepts."""
    text = (HERMES_SRC / "hermes_cli" / "tools_config.py").read_text()
    block = text.split("CONFIGURABLE_TOOLSETS = [", 1)[1].split("\n]", 1)[0]
    return set(re.findall(r'^\s*\(\s*"([a-z_]+)"', block, re.M))


@pytest.mark.skipif(not (HERMES_SRC / "hermes_cli" / "tools_config.py").is_file(),
                    reason="Hermes source tree not available")
def test_fake_tools_enable_accepts_what_real_hermes_accepts():
    """The fake's KNOWN_TOOLSETS is a copy; a copy that drifts makes every toolset test pass on a fiction."""
    text = (REPO / "tests" / "fakes" / "hermes.py").read_text()
    fake = set(text.split('KNOWN_TOOLSETS = frozenset("""', 1)[1].split('"""', 1)[0].split())
    real = hermes_configurable_toolsets()
    assert fake == real, {"only_fake": sorted(fake - real), "only_real": sorted(real - fake)}


@pytest.mark.skipif(not (HERMES_SRC / "hermes_cli" / "tools_config.py").is_file(),
                    reason="Hermes source tree not available")
def test_every_shipped_toolset_is_one_hermes_tools_enable_accepts():
    """`hermes tools enable` drops an unknown name and exits 0, so a typo in a shipped manifest reaches a bot."""
    known = hermes_configurable_toolsets()
    for path in [REPO / "builder.yaml", *sorted((REPO / "squads").glob("*/squad.yaml"))]:
        doc = yaml.safe_load(path.read_text())
        cron = (doc.get("defaults") or {}).get("cron_toolsets") or []
        for bot, spec in doc["bots"].items():
            assert set(spec["toolsets"]) <= known, (path.name, bot, sorted(set(spec["toolsets"]) - known))
        assert set(cron) <= known, (path.name, sorted(set(cron) - known))
