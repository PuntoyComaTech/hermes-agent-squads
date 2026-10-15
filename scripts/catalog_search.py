#!/usr/bin/env python3
"""Search what Hermes can install: plugin catalog, official optional skills, bundled skills, MCP and connector names.

Offline by default: reads plugin-catalog/*.yaml, optional-skills/, skills/ and optional-mcps/ from the Hermes source
tree (--hermes-src, $HERMES_SRC, <root>/hermes-agent, else the tree behind `hermes --print-runtime-command`).
`--hub` adds `hermes skills search --json` results (network). A query is AND over its words and matches names,
titles, tags, categories, connector slugs, env var NAMES and descriptions. Env var values are never read.

Each result carries `id` (the keep/enable string squads use: `official:<category>/<name>`, `bundled:<name>`,
`hub:<identifier>`, a plugin name, or `mcp:<name>`), `tier`, `needs_ok` (the builder must quote `disclosure` and get
the user's OK first) and an `install` command.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    import hermes_yaml as yaml
except ImportError:
    import yaml

DESC_MAX = 220
DISCLOSURE_MAX = 600
TIER_RANK = {"official": 0, "bundled": 1, "community": 2}
KINDS = ("plugin", "skill", "mcp")


class SearchError(Exception):
    pass


# --- source tree ------------------------------------------------------------------------------------------------

def hermes_root() -> Path:
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    return home.parent.parent if home.parent.name == "profiles" else home


def find_source(explicit: Path | None) -> Path:
    candidates = [explicit] if explicit else []
    if os.environ.get("HERMES_SRC"):
        candidates.append(Path(os.environ["HERMES_SRC"]))
    candidates.append(hermes_root() / "hermes-agent")
    for c in candidates:
        if c and c.is_dir():
            return c
    if not explicit:
        try:
            out = subprocess.run(["hermes", "--print-runtime-command"], capture_output=True, text=True, timeout=60)
            src = re.search(r"sys\.path\.insert\(0, '([^']+)'\)", json.loads(out.stdout)[-1])
            if src and Path(src.group(1)).is_dir():
                return Path(src.group(1))
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass
    raise SearchError("Hermes source tree not found; pass --hermes-src")


def read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except Exception:  # a malformed entry must not stop a search
        return {}
    return data if isinstance(data, dict) else {}


def frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return {}
    match = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    if not match:
        return {}
    try:
        data = yaml.safe_load(match.group(1))
    except Exception:  # malformed frontmatter must not stop a search
        return {}
    return data if isinstance(data, dict) else {}


# --- entries ----------------------------------------------------------------------------------------------------

def short(text: object, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else flat[: limit - 3].rstrip() + "..."


def entry(kind: str, id_: str, name: str, tier: str, source: str, desc: object, install: str, **extra) -> dict:
    return {"kind": kind, "id": id_, "name": name, "tier": tier, "source": source,
            "description": short(desc, DESC_MAX), "env": sorted(set(extra.pop("env", []))),
            "connector": extra.pop("connector", None), "disclosure": extra.pop("disclosure", ""),
            "needs_ok": extra.pop("needs_ok", False), "install": install, "_tags": extra.pop("tags", []),
            "_title": extra.pop("title", ""), "_category": extra.pop("category", "")}


def load_plugins(src: Path) -> list[dict]:
    root = src / "plugin-catalog"
    removed = {str(r.get("name")) for r in (read_yaml(root / "removed.yaml").get("removed") or []) if isinstance(r, dict)}
    out = []
    for path in sorted(root.glob("*.yaml")):
        if path.name == "removed.yaml":
            continue
        data = read_yaml(path)
        name = str(data.get("name") or "")
        if not name or name in removed:
            continue
        desc = str(data.get("description") or "")
        disclosure = re.search(r"Disclosure\s*[—:-]+\s*(.*)", " ".join(desc.split()))
        caps = data.get("capabilities") or {}
        tier = "official" if data.get("tier") == "official" else "community"
        out.append(entry(
            "plugin", name, name, tier, "plugin-catalog", desc, f"hermes plugins install {name}",
            env=caps.get("requires_env") or [], tags=list(caps.get("provides_tools") or []),
            title=data.get("title") or "", category=data.get("category") or "",
            disclosure=short(disclosure.group(1), DISCLOSURE_MAX) if disclosure else "",
            needs_ok=tier == "community" or bool(disclosure)))
    return out


def skill_env(meta: dict) -> list[str]:
    names = [e.get("name") for e in meta.get("required_environment_variables") or [] if isinstance(e, dict)]
    names += (meta.get("prerequisites") or {}).get("env_vars") or []
    return [n for n in names if isinstance(n, str)]


def load_skills(root: Path, prefix: str, tier: str, source: str, install) -> list[dict]:
    out = []
    for path in sorted(root.glob("**/SKILL.md")):
        meta = frontmatter(path)
        rel = path.parent.relative_to(root)
        name = str(meta.get("name") or path.parent.name)
        category = "/".join(rel.parts[:-1])
        hermes = (meta.get("metadata") or {}).get("hermes") or {}
        ident = f"{prefix}:{category}/{name}" if prefix == "official" else f"{prefix}:{name}"
        out.append(entry("skill", ident, name, tier, source, meta.get("description"), install(category, name),
                         env=skill_env(meta), tags=[str(t) for t in hermes.get("tags") or []], category=category))
    return out


def load_mcps(src: Path) -> list[dict]:
    out = []
    for path in sorted((src / "optional-mcps").glob("*/manifest.yaml")):
        data = read_yaml(path)
        name = str(data.get("name") or path.parent.name)
        slug = data.get("connector_slug")
        keywords = ((data.get("suggest") or {}).get("keywords") or [])
        out.append(entry("mcp", f"mcp:{name}", name, "official", "optional-mcps", data.get("description"),
                         f"hermes mcp install {name}", connector=slug, tags=[str(k) for k in keywords],
                         needs_ok=False))
    return out


def load_local(src: Path) -> tuple[list[dict], list[str]]:
    entries, warnings = [], []
    sources = (("plugin-catalog", lambda: load_plugins(src)),
               ("optional-skills", lambda: load_skills(
                   src / "optional-skills", "official", "official", "optional-skills",
                   lambda cat, name: f"hermes skills install official/{cat}/{name}")),
               ("skills", lambda: load_skills(src / "skills", "bundled", "bundled", "skills",
                                              lambda cat, name: "bundled with Hermes; list it under skills.keep")),
               ("optional-mcps", lambda: load_mcps(src)))
    for dirname, loader in sources:
        if (src / dirname).is_dir():
            entries += loader()
        else:
            warnings.append(f"{dirname}/ not found in the Hermes source tree")
    return entries, warnings


def load_hub(query: str, limit: int, have: set[str]) -> tuple[list[dict], list[str]]:
    try:
        out = subprocess.run(["hermes", "skills", "search", query, "--json", "--limit", str(limit)],
                             capture_output=True, text=True, timeout=120)
        rows = json.loads(out.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return [], [f"hub search failed for {query!r}: {exc.__class__.__name__}"]
    results = []
    for row in rows if isinstance(rows, list) else []:
        ident = str(row.get("identifier") or "")
        official = ident.startswith("official/") and row.get("trust_level") == "builtin"
        key = f"official:{ident.removeprefix('official/')}" if official else f"hub:{ident}"
        if not ident or key in have:
            continue
        results.append(entry("skill", key, str(row.get("name") or ident), "official" if official else "community",
                             "hub", row.get("description"), f"hermes skills install {ident}",
                             needs_ok=not official))
    return results, []


# --- search -----------------------------------------------------------------------------------------------------

def score(item: dict, words: list[str]) -> int:
    name = item["name"].lower()
    total = 0
    for w in words:
        if name == w:
            total += 100
        elif name.startswith(w):
            total += 70
        elif w in name:
            total += 50
        elif any(w in f.lower() for f in (item["_title"], item["_category"], item["connector"] or "", *item["_tags"])):
            total += 30
        elif any(w in e.lower() for e in item["env"]):
            total += 25
        elif w in item["description"].lower():
            total += 10
        else:
            return 0
    return total


def search(entries: list[dict], query: str, kinds: set[str], limit: int) -> tuple[list[dict], int]:
    words = query.lower().split()
    scored = [(score(e, words), e) for e in entries if e["kind"] in kinds] if words else []
    hits = sorted(((s, e) for s, e in scored if s), key=lambda t: (-t[0], TIER_RANK[t[1]["tier"]], t[1]["id"]))
    public = [{k: v for k, v in e.items() if not k.startswith("_")} | {"score": s} for s, e in hits]
    return public[:limit], len(public)


def render_text(result: dict) -> str:
    lines = [f"warning: {w}" for w in result["warnings"]]
    for q in result["queries"]:
        lines.append(f"\n{q['query']}: {q['total']} match(es)" + (", none found" if not q["results"] else ""))
        for r in q["results"]:
            ok = " [needs OK]" if r["needs_ok"] else ""
            conn = f" connector={r['connector']}" if r["connector"] else ""
            lines.append(f"  {r['id']}  ({r['kind']}, {r['tier']}){conn}{ok}")
            lines.append(f"      {r['description']}")
            if r["env"]:
                lines.append(f"      env: {', '.join(r['env'])}")
            if r["disclosure"]:
                lines.append(f"      disclosure: {r['disclosure']}")
            lines.append(f"      install: {r['install']}")
    return "\n".join(lines).lstrip("\n")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="catalog_search.py", description=__doc__.split("\n\n")[0],
        epilog="Exit 0 when the search ran (even with no matches), 2 on error (JSON {error} with --json).")
    p.add_argument("queries", nargs="+", metavar="QUERY", help="one search per argument; quote multi-word queries")
    p.add_argument("--kind", default=",".join(KINDS), help="comma list of: plugin, skill, mcp (default: all)")
    p.add_argument("--limit", type=int, default=8, help="max results per query (default 8)")
    p.add_argument("--hermes-src", type=Path, help="Hermes source tree (default: autodetect)")
    p.add_argument("--hub", action="store_true", help="also query the skills hub (network)")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    return p


def run(args: argparse.Namespace) -> dict:
    kinds = {k.strip() for k in args.kind.split(",") if k.strip()}
    if not kinds <= set(KINDS):
        raise SearchError(f"unknown kind: {', '.join(sorted(kinds - set(KINDS)))}")
    src = find_source(args.hermes_src)
    entries, warnings = load_local(src)
    if not entries:
        raise SearchError("no catalog entries found in the Hermes source tree")
    have = {e["id"] for e in entries}
    queries = []
    for q in args.queries:
        pool = entries
        if args.hub and "skill" in kinds:
            hub, warn = load_hub(q, args.limit, have)
            pool, warnings = entries + hub, warnings + warn
        results, total = search(pool, q, kinds, args.limit)
        queries.append({"query": q, "total": total, "results": results})
    return {"counts": {k: sum(e["kind"] == k for e in entries) for k in KINDS}, "queries": queries,
            "warnings": warnings}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run(args)
    except SearchError as exc:
        print(json.dumps({"error": str(exc)}) if args.json else f"error: {exc}")
        return 2
    print(json.dumps(result, indent=2) if args.json else render_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
