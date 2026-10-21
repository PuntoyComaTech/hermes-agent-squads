#!/usr/bin/env python3
"""Hard-skill gaps across one project's analysed openings: a deterministic diff, never an estimate.

  skill_gaps.py --project P [--opening ID] [--json]

Reads openings/<ID>/analysis.json (requirements.must_have, nice_to_have, tools, keywords) and the skill names in
achievements.yaml. A skill is a gap when no achievement skill matches it; case, accents, spacing and punctuation are
ignored. Each skill gets a count per list: how many openings name it under must-have, nice-to-have, tools and
keywords. Nothing is inferred: a skill that no analysis names is never listed.

Output: a text table, or the full result with --json (skills and gaps, sorted: gaps first, must-have first).
Exit 0 on success; 1 when a file is unreadable or --opening has no analysis; 2 on usage errors.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs_common as jc  # noqa: E402

LISTS = (("must_have", "must"), ("nice_to_have", "nice"), ("tools", "tools"), ("keywords", "keywords"))


class DataError(Exception):
    """An unreadable file or a missing opening: the reason goes to stderr and the exit code is 1."""


def norm(text) -> str:
    flat = unicodedata.normalize("NFKD", str(text).casefold())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    flat = re.sub(r"[^\w+#.]+", " ", flat)
    return re.sub(r"\s+", " ", flat).strip(" .")


def covered_skills(project: Path) -> set:
    try:
        data = jc.read_data(project / "achievements.yaml")
    except ValueError as exc:
        raise DataError(f"achievements.yaml: {exc}")
    skills = data.get("skills") if isinstance(data, dict) else None
    names = set()
    for item in skills if isinstance(skills, list) else []:
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and norm(name):
            names.add(norm(name))
    return names


def requirements(project: Path, only) -> dict:
    folder = project / "openings"
    paths = sorted(folder.glob("*/analysis.json")) if folder.is_dir() else []
    if only:
        paths = [p for p in paths if p.parent.name == only]
        if not paths:
            raise DataError(f"no openings/{only}/analysis.json")
    found = {}
    for path in paths:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise DataError(f"{path}: {exc}")
        req = doc.get("requirements") if isinstance(doc, dict) else None
        if not isinstance(req, dict):
            raise DataError(f"{path}: no requirements object")
        found[path.parent.name] = req
    return found


def diff(project: Path, only=None) -> dict:
    reqs = requirements(project, only)
    have = covered_skills(project)
    table: dict = {}
    for opening, req in sorted(reqs.items()):
        for field, label in LISTS:
            values = req.get(field)
            for raw in values if isinstance(values, list) else []:
                key = norm(raw) if isinstance(raw, str) else ""
                if not key:
                    continue
                slot = table.setdefault(key, {"skill": raw.strip(), "must": set(), "nice": set(), "tools": set(),
                                              "keywords": set()})
                slot[label].add(opening)
    rows = []
    for key, slot in table.items():
        named = slot["must"] | slot["nice"] | slot["tools"] | slot["keywords"]
        rows.append({"skill": slot["skill"], "must_have": len(slot["must"]), "nice_to_have": len(slot["nice"]),
                     "tools": len(slot["tools"]), "keywords": len(slot["keywords"]), "openings": len(named),
                     "covered": key in have})
    rows.sort(key=lambda r: (r["covered"], -r["must_have"], -r["nice_to_have"], -r["openings"],
                             r["skill"].casefold()))
    return {"openings_analysed": len(reqs), "skills": rows, "gaps": [r for r in rows if not r["covered"]]}


def render_text(report: dict) -> str:
    lines = [f"Openings analysed: {report['openings_analysed']}",
             f"Skills named: {len(report['skills'])}; gaps: {len(report['gaps'])}", ""]
    if not report["gaps"]:
        lines.append("No hard-skill gaps: every named skill is covered by achievements.yaml.")
        return "\n".join(lines)
    lines.append(f"{'Skill':<32}{'Must':>5}{'Nice':>6}{'Tools':>7}{'Keywords':>10}{'Openings':>10}")
    for row in report["gaps"]:
        lines.append(f"{row['skill'][:31]:<32}{row['must_have']:>5}{row['nice_to_have']:>6}{row['tools']:>7}"
                     f"{row['keywords']:>10}{row['openings']:>10}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Hard-skill gaps across the analysed openings of a project.")
    parser.add_argument("--project", help="project folder holding profile.md (default: $JOBS_PROJECT, else the "
                                          "current folder)")
    parser.add_argument("--opening", help="limit the diff to one opening id (targeted mode)")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)
    try:
        project = jc.project_dir(args.project or os.environ.get("JOBS_PROJECT"))
        report = diff(project, args.opening)
    except DataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
