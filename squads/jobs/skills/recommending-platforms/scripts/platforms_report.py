#!/usr/bin/env python3
"""Checks and summarises the platform recommendation the scout writes for one person's market.

The scout researches which job platforms matter where the user can work (`reports/platforms-YYYY-MM-DD.json`). This
tool refuses a recommendation that is not backed: a `recommended` platform needs two evidence pages on different hosts,
at least one of them not the platform's own site, and a stated field limit (headline length and the like) needs the
page that states it.

Usage:
  platforms_report.py validate FILE [--portals-dir DIR] [--json]
  platforms_report.py summary FILE

FILE shape:
  {"schema": 1, "date": "YYYY-MM-DD", "country": "CO", "cities": [], "languages": ["es"], "field": "data analytics",
   "platforms": [{"name": "...", "url": "https://...", "scope": "global|country|region|sector|remote",
                  "tier": "recommended|optional|skip", "why": "...", "login_required": true|false|null,
                  "evidence": [{"url": "https://...", "note": "..."}],
                  "search": {"method": "portal_cli|browser_url|manual", "portal": "name", "note": "..."},
                  "profile_fields": {"headline_max": 220}, "profile_fields_source": "https://..."}]}

Exit 0 when valid (warnings are printed), 1 with defects, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
SCOPES = ("global", "country", "region", "sector", "remote")
TIERS = ("recommended", "optional", "skip")
METHODS = ("portal_cli", "browser_url", "manual")
FIELD_KEYS = ("headline_max", "summary_max", "skills_max", "title_max", "bio_max")
MAX_PLATFORMS, MAX_RECOMMENDED = 12, 6


def host(url) -> str:
    return (urlsplit(str(url or "")).hostname or "").lower().removeprefix("www.")


def same_site(a: str, b: str) -> bool:
    return bool(a and b and (a == b or a.endswith("." + b) or b.endswith("." + a)))


def check(data, portals_dir: Path | None) -> tuple[list, list]:
    defects, warnings = [], []

    def bad(where, why):
        defects.append({"where": where, "defect": why})

    if not isinstance(data, dict):
        return [{"where": "file", "defect": "the top level must be an object"}], []
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(data.get("date") or "")):
        bad("date", "must be YYYY-MM-DD")
    if not re.fullmatch(r"[A-Z]{2}", str(data.get("country") or "")):
        bad("country", "must be an ISO 3166 alpha-2 code in capitals, for example CO")
    if not str(data.get("field") or "").strip():
        bad("field", "name the user's field: a platform is recommended for a person's work, not in general")
    platforms = data.get("platforms")
    if not isinstance(platforms, list) or not platforms:
        bad("platforms", "needs at least one platform")
        return defects, warnings
    if len(platforms) > MAX_PLATFORMS:
        bad("platforms", f"{len(platforms)} entries; keep the {MAX_PLATFORMS} that matter, a long list helps nobody")
    names = set()
    for i, item in enumerate(platforms):
        label = f"platforms[{i}]"
        if not isinstance(item, dict):
            bad(label, "must be an object")
            continue
        name = str(item.get("name") or "").strip()
        label = f"platforms[{i}] {name or '?'}"
        if not name:
            bad(label, "has no name")
        elif name.casefold() in names:
            bad(label, "is listed twice")
        names.add(name.casefold())
        url = str(item.get("url") or "")
        if not url.startswith("https://") or not host(url):
            bad(label, "url must be an https address")
        if item.get("scope") not in SCOPES:
            bad(label, f"scope must be one of {', '.join(SCOPES)}")
        tier = item.get("tier")
        if tier not in TIERS:
            bad(label, f"tier must be one of {', '.join(TIERS)}")
        why = str(item.get("why") or "").strip()
        if not why or len(why) > 300:
            bad(label, "why is required and at most 300 characters")
        if item.get("login_required") not in (True, False, None):
            bad(label, "login_required must be true, false or null (unknown)")
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        hosts = set()
        for j, ev in enumerate(evidence):
            if not isinstance(ev, dict) or not str(ev.get("url") or "").startswith("https://") \
                    or not str(ev.get("note") or "").strip():
                bad(label, f"evidence[{j}] needs an https url and a note")
                continue
            hosts.add(host(ev["url"]))
        if tier == "recommended":
            if len(hosts) < 2:
                bad(label, "recommended needs evidence from two different hosts")
            if hosts and all(same_site(h, host(url)) for h in hosts):
                bad(label, "recommended needs evidence that is not the platform's own site")
        search = item.get("search")
        if not isinstance(search, dict) or search.get("method") not in METHODS:
            bad(label, f"search.method must be one of {', '.join(METHODS)}")
        elif search["method"] == "portal_cli":
            portal = str(search.get("portal") or "")
            if not re.fullmatch(r"[a-z0-9-]+", portal):
                bad(label, "search.portal names the installed portal directory")
            elif portals_dir is not None and not (portals_dir / portal / "portal.json").is_file():
                bad(label, f"search.portal {portal!r} is not an installed portal under {portals_dir}")
        fields = item.get("profile_fields")
        if fields is not None:
            if not isinstance(fields, dict) or not fields:
                bad(label, "profile_fields must be an object of field limits, or absent")
            else:
                for key, value in fields.items():
                    if key not in FIELD_KEYS:
                        bad(label, f"profile_fields.{key} is not a known limit ({', '.join(FIELD_KEYS)})")
                    elif isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                        bad(label, f"profile_fields.{key} must be a positive whole number")
                if not str(item.get("profile_fields_source") or "").startswith("https://"):
                    bad(label, "profile_fields needs profile_fields_source: the page that states the limits")
    if sum(1 for p in platforms if isinstance(p, dict) and p.get("tier") == "recommended") > MAX_RECOMMENDED:
        bad("platforms", f"more than {MAX_RECOMMENDED} recommended; rank them and demote the rest to optional")
    if "linkedin" not in " ".join(names):
        warnings.append("LinkedIn is not listed: say why it does not apply in this market, or add it")
    return defects, warnings


def summary(data) -> str:
    rows = ["| Platform | Scope | Tier | Login | Squad searches it | Why |", "|---|---|---|---|---|---|"]
    order = {t: i for i, t in enumerate(TIERS)}
    for item in sorted(data["platforms"], key=lambda p: order.get(p.get("tier"), 9)):
        login = {True: "yes", False: "no", None: "unknown"}[item.get("login_required")]
        method = (item.get("search") or {}).get("method")
        rows.append(f"| [{item['name']}]({item['url']}) | {item['scope']} | {item['tier']} | {login} | "
                    f"{ {'portal_cli': 'portal tool', 'browser_url': 'browser', 'manual': 'you, by hand'}.get(method, '?') } | "
                    f"{item['why']} |")
    head = f"Platforms for {data['field']} in {data['country']} ({data['date']})"
    return head + "\n\n" + "\n".join(rows)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("file")
    v.add_argument("--portals-dir")
    v.add_argument("--json", action="store_true")
    s = sub.add_parser("summary")
    s.add_argument("file")
    ns = p.parse_args(argv)
    try:
        data = json.loads(Path(ns.file).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.stderr.write(json.dumps({"error": f"cannot read {ns.file}: {exc}", "code": "BAD_INPUT"}) + "\n")
        return 2
    default_portals = HERE.parents[1] / "searching-portals" / "scripts"
    if ns.cmd == "summary":
        defects, _ = check(data, default_portals if default_portals.is_dir() else None)
        if defects:
            sys.stderr.write(json.dumps({"error": "the file does not validate; run validate first", "code": "INVALID"}) + "\n")
            return 1
        print(summary(data))
        return 0
    portals = Path(ns.portals_dir) if ns.portals_dir else default_portals
    defects, warnings = check(data, portals if portals.is_dir() else None)
    report = {"ok": not defects, "defects": defects, "warnings": warnings}
    if ns.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        for d in defects:
            print(f"DEFECT {d['where']}: {d['defect']}")
        for w in warnings:
            print(f"WARNING {w}")
        print("ok" if not defects else f"{len(defects)} defect(s)")
    return 0 if not defects else 1


if __name__ == "__main__":
    sys.exit(main())
