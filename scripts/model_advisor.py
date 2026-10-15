#!/usr/bin/env python3
"""Suggest a model, provider and reasoning effort per squad bot from the user's authenticated providers.

Inputs
  providers  hermes_cli.model_switch_providers.list_authenticated_providers() in-process, else the same call under
             the Hermes runtime interpreter, else `hermes auth list` (slugs only). `--providers cache` or a comma
             list skips detection (offline).
  key homes  where each provider's key lives (root vs profile): the same detection is re-run with HERMES_HOME
             pointed at the root and at the profile, and the two views are diffed. "provider X authenticated at
             root but not in profile Y" is that diff. Auto detection only; never reads .env or auth.json itself.
  models     <HERMES_HOME>/provider_models_cache.json ({slug: {fp, at, models[]}}); falls back to the models the
             detection call returned (providers such as nous have no cache entry).
  lanes      scripts/data/model-roles.yaml, overridden per lane/family by <builder>/local/model-roles.yaml;
             deprecated lane names (lead, design, code, advisor, copy) resolve through `alias_of`.
  excluded   <builder>/local/providers-exclude.txt (one slug per line): those providers are detected and
             reported but never recommended.

Output per bot: lane, model, provider, reasoning, up to 2 alternatives, one-line reason. The review lane prefers a
family the producers of the squad do not use. Never reads or prints secrets. Cache entries older than 7 days are
reported as stale; refreshing (`hermes model --refresh`) needs the user's OK and is never run here.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from fnmatch import fnmatch
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
BUILDER = SCRIPTS.parent
STALE_SECONDS = 7 * 86400
CHEAP_RANK = ("nano", "mini", "flash", "haiku", "lite")

# Runs under the Hermes runtime interpreter; prints [{"slug", "models"}] and nothing else.
PROBE = """
import json, os, sys
sys.path.insert(0, {src!r})
import hermes_bootstrap
from hermes_cli.model_switch_providers import list_authenticated_providers as lap
rows = lap(non_blocking_catalogs=True, probe_custom_providers=False)
print(json.dumps([{{"slug": r["slug"], "models": list(r.get("models") or [])}} for r in rows]))
"""


class AdvisorError(Exception):
    pass


def _yaml():
    """YAML module on first use, never at import: `--help` must work without PyYAML (scripts/hpy provides
    hermes_yaml; a bare python3 falls back to PyYAML when a command actually reads YAML)."""
    try:
        import hermes_yaml as y  # the Hermes runtime's YAML module
    except ImportError:
        try:
            import yaml as y
        except ImportError:
            raise AdvisorError("no YAML module: run scripts/hpy model_advisor.py (Hermes runtime) or install PyYAML") from None
    return y


# --- paths ------------------------------------------------------------------------------------------------------

def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")


def hermes_root() -> Path:
    home = hermes_home()
    return home.parent.parent if home.parent.name == "profiles" else home


def default_cache_path() -> Path:
    own = hermes_home() / "provider_models_cache.json"
    return own if own.is_file() else hermes_root() / "provider_models_cache.json"


def load_yaml(path: Path):
    try:
        return _yaml().safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # a malformed roles file must give one clear line, never a traceback
        raise AdvisorError(f"cannot read {path.name}: {exc}") from exc


# --- roles ------------------------------------------------------------------------------------------------------

def load_roles(base: Path, local: Path) -> tuple[dict, list[str]]:
    roles = load_yaml(base)
    sources = ["base"]
    if local.is_file():
        over = load_yaml(local)
        roles.setdefault("families", {}).update(over.get("families") or {})
        for lane, spec in (over.get("lanes") or {}).items():
            roles.setdefault("lanes", {}).setdefault(lane, {}).update(spec)
        sources.append("local")
    return roles, sources


# --- providers --------------------------------------------------------------------------------------------------

def load_cache(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AdvisorError(f"cannot read provider cache {path.name}: {exc}") from exc
    return {slug: e for slug, e in data.items() if isinstance(e, dict) and isinstance(e.get("models"), list)}


def runtime_python() -> tuple[list[str], str] | None:
    try:
        out = subprocess.run(["hermes", "--print-runtime-command"], capture_output=True, text=True, timeout=60)
        argv = json.loads(out.stdout)
        src = re.search(r"sys\.path\.insert\(0, '([^']+)'\)", argv[-1])
        return argv[:2], src.group(1)
    except (OSError, ValueError, IndexError, AttributeError, subprocess.SubprocessError):
        return None


def probe_in_process() -> list[dict] | None:
    try:
        from hermes_cli.model_switch_providers import list_authenticated_providers as lap
    except ImportError:
        return None
    rows = lap(non_blocking_catalogs=True, probe_custom_providers=False)
    return [{"slug": r["slug"], "models": list(r.get("models") or [])} for r in rows]


def probe_runtime(env: dict | None = None) -> list[dict] | None:
    rt = runtime_python()
    if not rt:
        return None
    (python, flag), src = rt
    try:
        out = subprocess.run([python, flag, "-c", PROBE.format(src=src)], capture_output=True, text=True,
                             timeout=180, env=env)
        return json.loads(out.stdout.strip().splitlines()[-1]) if out.returncode == 0 else None
    except (OSError, ValueError, IndexError, subprocess.SubprocessError):
        return None


def probe_auth_list(env: dict | None = None) -> list[dict] | None:
    try:
        out = subprocess.run(["hermes", "auth", "list"], capture_output=True, text=True, timeout=60, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    # Provider header lines only ("<slug> (N credentials):", "<slug>: <label>", "<slug> (...):", as in
    # `nous: Free tier` or `bedrock (...)`); credential rows are indented and never parsed.
    slugs = re.findall(r"^([a-z0-9][a-z0-9._-]*)(?: \([^)]*\))?:", out.stdout, re.M)
    slugs = [s for s in slugs if s not in {"note", "error", "warning", "usage", "hint"}]
    return [{"slug": s, "models": []} for s in dict.fromkeys(slugs)] or None


def detect_providers(mode: str, cache: dict) -> tuple[list[dict], str]:
    if mode == "cache":
        return [{"slug": s, "models": []} for s in cache], "cache"
    if mode != "auto":
        return [{"slug": s.strip(), "models": []} for s in mode.split(",") if s.strip()], "list"
    for name, probe in (("in-process", probe_in_process), ("runtime", probe_runtime), ("auth-list", probe_auth_list)):
        rows = probe()
        if rows:
            return rows, name
    raise AdvisorError("no authenticated provider detected; run `hermes model` or pass --providers")


def resolve_providers(mode: str, cache: dict, now: float) -> dict:
    rows, source = detect_providers(mode, cache)
    providers, stale = [], []
    for row in rows:
        entry = cache.get(row["slug"])
        models = [m for m in (entry["models"] if entry else row["models"]) if isinstance(m, str)]
        if entry and now - float(entry.get("at") or 0) > STALE_SECONDS:
            stale.append(row["slug"])
        providers.append({"slug": row["slug"], "models": models})
    if not providers:
        raise AdvisorError("no authenticated provider detected; run `hermes model` or pass --providers")
    return {"providers": providers, "source": source, "stale": stale}


# --- key locations and exclusions -------------------------------------------------------------------------------

def scope_providers(home: Path) -> set[str]:
    """Slugs Hermes reports authenticated with HERMES_HOME=home: its own view of that scope (root or
    profile). Runs detection with the scope's home in the subprocess environment; never opens .env or
    auth.json here."""
    env = {**os.environ, "HERMES_HOME": str(home)}
    for probe in (probe_runtime, probe_auth_list):
        try:
            rows = probe(env)
        except Exception:
            rows = None
        if rows:
            return {r["slug"] for r in rows}
    return set()


def key_locations(slugs: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """Where each provider's key lives (root / profile), as Hermes sees it per scope. Returns
    (key_in per slug, report lines "provider X authenticated at root but not in profile Y")."""
    root, profile = hermes_root(), hermes_home()
    scopes = [("root", root)] if root == profile else [("root", root), ("profile", profile)]
    found = {}
    for name, home in scopes:
        try:
            found[name] = scope_providers(home)
        except Exception:
            found[name] = set()
    key_in = {slug: [name for name, _ in scopes if slug in found[name]] for slug in slugs}
    report = [f"provider {slug} authenticated at root but not in profile {profile.name}"
              for slug in slugs if root != profile and key_in[slug] == ["root"]]
    return key_in, report


def load_exclusions(path: Path | None) -> list[str]:
    """Provider slugs that must never be recommended (one per line, # comments allowed)."""
    if not path or not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise AdvisorError(f"cannot read {path.name}: {exc}") from exc
    return [s for s in (line.split("#", 1)[0].strip() for line in lines) if s]


# --- picking ----------------------------------------------------------------------------------------------------

class Advisor:
    def __init__(self, roles: dict, providers: list[dict], exclude: set[str] | None = None):
        self.families = roles["families"]
        self.lanes = roles["lanes"]
        self.excluded = set(exclude or ())
        self.providers = [p for p in providers if p["slug"] not in self.excluded]

    def resolve(self, lane: str) -> str:
        """Follow alias_of (lead -> manager ...) to the live lane; cycle-safe."""
        seen = set()
        while True:
            spec = self.lanes.get(lane)
            if spec is None:
                raise AdvisorError(f"unknown lane: {lane}")
            target = spec.get("alias_of")
            if not target:
                return lane
            if target in seen or target not in self.lanes:
                raise AdvisorError(f"broken lane alias: {lane} -> {target}")
            seen.add(lane)
            lane = target

    def real_lanes(self) -> list[str]:
        """Lane names that are not aliases (the alias entries resolve to these)."""
        return [name for name, spec in self.lanes.items() if not spec.get("alias_of")]

    def lane_spec(self, lane: str) -> dict:
        """Effective lane spec: the canonical lane's, overlaid with any keys the requested (alias)
        entry sets itself, so a local override of an old lane name wins over its alias target."""
        real = self.resolve(lane)
        spec = dict(self.lanes[real])
        if real != lane:
            spec.update({k: v for k, v in self.lanes[lane].items() if k != "alias_of"})
        return spec

    def family_of(self, slug: str) -> str | None:
        return next((f for f, globs in self.families.items() if any(fnmatch(slug, g) for g in globs)), None)

    def present_families(self) -> list[str]:
        return [f for f in self.families if any(self.family_of(p["slug"]) == f for p in self.providers)]

    def candidate_hits(self, cand: dict, lane_reasoning: str) -> list[dict]:
        globs = cand.get("provider_pref") or self.families[cand["family"]]
        rx = re.compile(cand["match"])
        hits = []
        for glob in globs:
            for prov in self.providers:
                if not fnmatch(prov["slug"], glob):
                    continue
                models = sorted((m for m in prov["models"] if rx.fullmatch(m)), key=lambda m: (len(m), m))
                hits += [{"model": m, "provider": prov["slug"], "family": cand["family"],
                          "reasoning": cand.get("reasoning", lane_reasoning)} for m in models[:1]]
        return hits

    def cheapest(self, reasoning: str) -> dict | None:
        best = None
        for prov in self.providers:
            for m in prov["models"]:
                rank = next((i for i, tok in enumerate(CHEAP_RANK) if tok in m), None)
                key = (len(CHEAP_RANK) if rank is None else rank, len(m), m)
                if best is None or key < best[0]:
                    best = (key, m, prov["slug"])
        if best is None:
            return None
        return {"model": best[1], "provider": best[2], "family": self.family_of(best[2]), "reasoning": reasoning}

    def pick(self, lane: str, avoid: dict[str, int] | None = None, _depth: int = 0) -> dict:
        real = self.resolve(lane)
        spec = self.lane_spec(lane)
        default = spec["reasoning"]
        cands = list(spec["candidates"])
        total = len(cands)
        order = list(range(total))
        if avoid is not None and spec.get("rule") == "different-family-from-producer":
            order.sort(key=lambda i: avoid.get(cands[i]["family"], 0))
        hits = [(i, h) for i in order for h in self.candidate_hits(cands[i], default)]
        why = str(spec.get("why", "")).split(";")[0].strip()
        shown = f"{lane} lane" + (f" (alias of {real})" if real != lane else "")
        if hits:
            idx, best = hits[0]
            reason = f"{shown}, candidate {idx + 1}/{total} ({best['family']}): {why}"
            if avoid is not None and spec.get("rule") == "different-family-from-producer":
                reason += "; " + self.review_note(best["family"], avoid)
            return {"lane": lane, **best, "alternatives": self.alternatives(hits), "reason": reason}
        mode = spec.get("fallback", "cheapest")
        best = None
        if mode == "first-choice-provider" and real != "manager" and _depth == 0:
            lead = self.pick("manager", _depth=1)
            best = {k: lead[k] for k in ("model", "provider", "family")} | {"reasoning": default}
            mode = "manager pick"
        if best is None:
            best = self.cheapest(default)
            mode = "cheapest model"
        if best is None:
            raise AdvisorError(f"no model available for lane {lane}; refresh the provider cache")
        return {"lane": lane, **best, "alternatives": [],
                "reason": f"{shown}: no candidate matches the connected providers, using the {mode}; {why}"}

    def review_note(self, family: str, avoid: dict[str, int]) -> str:
        if not avoid:
            return "no producer in scope"
        if avoid.get(family, 0) == 0:
            return "family differs from the producers"
        if len(self.present_families()) <= 1:
            return "only one family available, same as the producers"
        return "every available family is used by a producer, least shared one chosen"

    @staticmethod
    def alternatives(hits: list[tuple[int, dict]]) -> list[dict]:
        norm = lambda m: re.sub(r"\[1m\]$", "", m).replace(".", "-")
        chosen = hits[0][1]
        out: list[dict] = []
        for same_model_ok in (False, True):
            for _, h in hits[1:]:
                if len(out) == 2:
                    break
                if h in out or (h["model"], h["provider"]) == (chosen["model"], chosen["provider"]):
                    continue
                if not same_model_ok and norm(h["model"]) in {norm(chosen["model"]), *map(norm, (o["model"] for o in out))}:
                    continue
                out.append(h)
        return [{k: o[k] for k in ("model", "provider", "reasoning")} for o in out]


def slim(pick: dict, use: str | None = None) -> dict:
    out = {k: pick[k] for k in ("lane", "model", "provider", "reasoning", "alternatives", "reason")}
    return {"use": use, **out} if use else out


# --- squads -----------------------------------------------------------------------------------------------------

def find_squad(ref: str) -> Path:
    path = Path(ref)
    if path.is_file():
        return path
    candidates = [BUILDER / "local" / "squads" / ref / "squad.yaml", BUILDER / "squads" / ref / "squad.yaml"]
    if ref == "builder":
        candidates.append(BUILDER / "builder.yaml")
    for c in candidates:
        if c.is_file():
            return c
    raise AdvisorError(f"squad not found: {ref}")


def bot_extras(doc: dict, name: str, bot: dict) -> list[tuple[str, str]]:
    extras = []
    if (bot.get("delegation") or {}).get("lane"):
        extras.append(("delegation", bot["delegation"]["lane"]))
    for job, spec in (bot.get("cron") or {}).items():
        if isinstance(spec.get("agent"), dict):
            extras.append((f"cron:{job}", spec["agent"]["lane"]))
    for chain, stages in (doc.get("chains") or {}).items():
        for st in stages:
            if st.get("assignee") == name and st.get("lane"):
                extras.append((f"chain:{chain}/{st['stage']}", st["lane"]))
    return extras


def advise_squad(adv: Advisor, doc: dict) -> dict:
    bots = doc["bots"]
    producers = {n: adv.pick(b["lane"]) for n, b in bots.items()
                 if adv.resolve(b["lane"]) != "review" and b["role"] != "lead"}
    if not producers:
        producers = {n: adv.pick(b["lane"]) for n, b in bots.items() if adv.resolve(b["lane"]) != "review"}
    avoid: dict[str, int] = {}
    for p in producers.values():
        avoid[p["family"]] = avoid.get(p["family"], 0) + 1

    def pick(lane: str) -> dict:
        return adv.pick(lane, avoid) if adv.resolve(lane) == "review" else adv.pick(lane)

    out = []
    for name, bot in bots.items():
        row = {"bot": name, "role": bot["role"], **slim(pick(bot["lane"]))}
        row["extras"] = [slim(pick(lane), use) for use, lane in bot_extras(doc, name, bot)]
        out.append(row)
    shared = [slim(adv.pick(lane), use) for use, lane in
              ((k.removesuffix("_lane"), v) for k, v in (doc.get("defaults") or {}).items() if k.endswith("_lane"))]
    return {"key": doc["key"], "bots": out, "shared": shared}


# --- output -----------------------------------------------------------------------------------------------------

def render_text(result: dict) -> str:
    lines = [f"providers: {', '.join(p['slug'] for p in result['providers']['authenticated'])} "
             f"(via {result['providers']['source']})"]
    for p in result["providers"]["authenticated"]:
        where = ", ".join(p["key_in"]) if p["key_in"] else "unknown home"
        flag = " [excluded: never recommended]" if p.get("excluded") else ""
        lines.append(f"  {p['slug']}: key in {where}, {len(p['models'])} models{flag}")
    lines.extend(f"  {line}" for line in result["providers"].get("report", []))
    if result["providers"]["stale"]:
        lines.append(f"stale cache (older than 7 days): {', '.join(result['providers']['stale'])}; "
                     f"ask the user to run `hermes model --refresh` in a terminal (it opens a picker)")

    def row(label: str, p: dict, indent: str = "") -> None:
        lines.append(f"{indent}{label:<22} {p['lane']:<9} {p['model']} @ {p['provider']} [{p['reasoning']}]")
        for alt in p["alternatives"]:
            lines.append(f"{indent}{'':<22}   alt: {alt['model']} @ {alt['provider']} [{alt['reasoning']}]")
        lines.append(f"{indent}{'':<22}   why: {p['reason']}")

    for squad in result.get("squads", []):
        lines.append(f"\n{squad['key']}")
        for bot in squad["bots"]:
            row(bot["bot"], bot)
            for extra in bot["extras"]:
                row("  " + extra["use"], extra)
        for extra in squad["shared"]:
            row("(shared) " + extra["use"], extra)
    if result.get("lanes"):
        lines.append("")
        for p in result["lanes"]:
            row(p["lane"], p)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="model_advisor.py", description=__doc__.split("\n\n")[0],
        epilog="Exit 0 on success, 2 on error (JSON {error} with --json).")
    p.add_argument("squads", nargs="*", metavar="SQUAD", help="squad key or path to a squad.yaml; none = lane table")
    p.add_argument("--lane", action="append", default=[], help="also advise this lane (repeatable)")
    p.add_argument("--producer-lane", action="append", default=[],
                   help="with --lane review: lanes whose family the review should avoid")
    p.add_argument("--providers", default="auto", metavar="auto|cache|a,b",
                   help="auto detects authenticated providers; cache trusts every cache entry; or a slug list")
    p.add_argument("--cache", type=Path, help="provider_models_cache.json (default: $HERMES_HOME, then the root)")
    p.add_argument("--roles", type=Path, default=SCRIPTS / "data" / "model-roles.yaml",
                   help="lane table (default: scripts/data/model-roles.yaml)")
    p.add_argument("--local-roles", type=Path, default=BUILDER / "local" / "model-roles.yaml",
                   help="per-user override of lanes and families (default: local/model-roles.yaml)")
    p.add_argument("--exclude-file", type=Path, default=BUILDER / "local" / "providers-exclude.txt",
                   help="providers that must never be recommended, one slug per line "
                        "(default: local/providers-exclude.txt)")
    p.add_argument("--now", type=float, help="epoch seconds used for cache staleness (tests)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    return p


def run(args: argparse.Namespace) -> dict:
    roles, sources = load_roles(args.roles, args.local_roles)
    cache = load_cache(args.cache or default_cache_path())
    found = resolve_providers(args.providers, cache, args.now if args.now is not None else time.time())
    excluded = set(load_exclusions(args.exclude_file))
    adv = Advisor(roles, found["providers"], exclude=excluded)
    slugs = [p["slug"] for p in found["providers"]]
    key_map, report = key_locations(slugs) if args.providers == "auto" else ({s: [] for s in slugs}, [])
    result = {
        "roles": sources,
        "providers": {"authenticated": [{"slug": p["slug"], "family": adv.family_of(p["slug"]),
                                         "models": p["models"], "key_in": key_map.get(p["slug"], []),
                                         **({"excluded": True} if p["slug"] in excluded else {})}
                                        for p in found["providers"]],
                      "families": adv.present_families(), "source": found["source"], "stale": found["stale"],
                      "report": report, "excluded": [s for s in slugs if s in excluded]},
        "squads": [advise_squad(adv, load_yaml(find_squad(ref))) for ref in args.squads],
    }
    lanes = args.lane or ([] if args.squads else adv.real_lanes())
    avoid = None
    if args.producer_lane:
        avoid = {}
        for lane in args.producer_lane:
            fam = adv.pick(lane)["family"]
            avoid[fam] = avoid.get(fam, 0) + 1
    result["lanes"] = [slim(adv.pick(lane, avoid)) for lane in lanes]
    return result


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run(args)
    except AdvisorError as exc:
        print(json.dumps({"error": str(exc)}) if args.json else f"error: {exc}")
        return 2
    print(json.dumps(result, indent=2) if args.json else render_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
