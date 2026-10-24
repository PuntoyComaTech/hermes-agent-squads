#!/usr/bin/env python3
"""Checks the copy jobs-writer drafted for a public profile (LinkedIn or any other platform) before the user sees it.

The writer drafts `profiles/<platform>.json`; this tool refuses anything the user could not truthfully stand behind and
renders the paste-ready Markdown only when the copy is clean. Nothing here logs in to a platform or edits a profile:
the user pastes the text.

Usage:
  check_profile_copy.py COPY.json --project P [--market FILE] [--render OUT.md] [--json]

COPY.json:
  {"platform": "linkedin", "language": "en",
   "limits": {"headline": 220, "about": 2600},            # section -> max characters; LinkedIn's are built in
   "blocks": [{"section": "headline|about|experience|...", "label": "optional", "text": "...",
               "achievements": ["ACH-007"], "no_claim": false}],
   "skills": ["SQL", "Power BI"], "custom_url": "firstname-lastname"}

Defects (exit 1): over_limit, too_long, uncited_claim, unknown_achievement, unverified_achievement, unsupported_skill,
claims_a_gap, banned_phrase, private_data, confidential_term, skills_over_limit, bad_custom_url. Warnings never change
the exit code.

too_long: a public profile is read by a person in seconds before any search engine ranks it. The About stays within
CONCISE["about"] characters and each experience description within CONCISE["experience"]; the platform allows more,
and a copy's own `limits` may only lower these. confidential_term: a profile.md `confidential_terms` entry (a client,
a brand, an internal project) in any block.
Exit 0 clean, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
LINKEDIN_LIMITS = {"headline": 220, "about": 2600, "experience": 2000, "experience_title": 100, "recommendation": 3000,
                   "skill": 80, "skills_count": 100}
# Readable-at-a-glance caps, below the platform limits: the first ~265 characters of the About show before "see more".
CONCISE = {"about": 1500, "experience": 600}
BANNED = ("passionate", "results-oriented", "results oriented", "results-driven", "results driven", "thought leader",
          "synergy", "go-getter", "rockstar", "rock star", "ninja", "guru", "dynamic professional",
          "proven track record", "apasionad", "orientad[oa] a resultados", "l[ií]der de opini[oó]n", "sinergia",
          "apaixonad", "orientad[oa] (a|para) resultados", "motivad[oa] y proactiv")
PRIVATE = (
    ("email", re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")),
    ("birth", re.compile(r"\b(date of birth|born (in|on)|fecha de nacimiento|nacid[oa] (en|el)|data de nascimento)\b", re.I)),
    ("marital", re.compile(r"\b(marital status|estado civil|casad[oa]|soltero|soltera)\b", re.I)),
    ("nationality", re.compile(r"\b(nationality|nacionalidad|nacionalidade)\b", re.I)),
)
AGE = re.compile(r"\b(\d{2})\s*(years old|a[ñn]os de edad|anos de idade)\b", re.I)
SKIP_KEYS = frozenset({"id", "verified", "source", "evidence", "experience", "url", "proficiency", "from", "to",
                       "year", "years", "achievements", "metric"})


class UsageError(ValueError):
    pass


def jc_module():
    sibling = str(HERE.parents[1] / "jobs-contract" / "scripts")
    if sibling not in sys.path:
        sys.path.insert(0, sibling)
    import jobs_common  # noqa: E402 - the sibling path is added just above
    return jobs_common


def fold(text) -> str:
    return jc_module().ascii_fold(str(text or "")).lower()


def has_term(term: str, text: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(fold(term))}(?![a-z0-9])", fold(text)))


def load_project(project: Path) -> dict:
    jc = jc_module()
    try:
        meta = jc.read_front_matter(project / "profile.md")
    except Exception:  # noqa: BLE001
        meta = {}
    try:
        data = jc.read_data(project / "achievements.yaml") or {}
    except Exception:  # noqa: BLE001
        data = {}
    ids = {}
    for key in ("achievements", "education", "certifications"):
        for item in data.get(key) or []:
            if isinstance(item, dict) and item.get("id"):
                ids[str(item["id"]).strip()] = item.get("verified") is True
    chunks = [json.dumps(meta.get(k), ensure_ascii=False) for k in ("key_skills", "search_keywords", "target_roles")]

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k not in SKIP_KEYS:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            chunks.append(node)
    walk(data)
    candidate = meta.get("candidate") if isinstance(meta.get("candidate"), dict) else {}
    style = meta.get("writing_style") if isinstance(meta.get("writing_style"), dict) else {}
    avoid = style.get("avoid_phrases") if isinstance(style.get("avoid_phrases"), list) else []
    roles = meta.get("target_roles") if isinstance(meta.get("target_roles"), list) else []
    return {"ids": ids, "corpus": fold(" ".join(chunks)), "age_ok": candidate.get("include_age_in_cv") is True,
            "confidential": jc.confidential_terms(meta),
            "avoid": [str(a) for a in avoid if str(a).strip()], "roles": [str(r) for r in roles if str(r).strip()]}


def check(copy: dict, project: dict, market: dict | None) -> tuple[list, list]:
    defects, warnings = [], []

    def bad(code, where, detail):
        defects.append({"defect": code, "where": where, "detail": detail})

    platform = str(copy.get("platform") or "").strip().lower()
    limits = dict(LINKEDIN_LIMITS) if platform == "linkedin" else {}
    limits.update({k: v for k, v in (copy.get("limits") or {}).items() if isinstance(v, int) and v > 0})
    blocks = copy.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise UsageError("the copy needs a non-empty `blocks` list")
    by_section = defaultdict(list)
    for i, block in enumerate(blocks):
        if not isinstance(block, dict) or not str(block.get("text") or "").strip() or not block.get("section"):
            raise UsageError(f"blocks[{i}] needs a `section` and a `text`")
        by_section[str(block["section"])].append(block)
    for section, cap in CONCISE.items():
        own = (copy.get("limits") or {}).get(section)
        cap = min(cap, own) if isinstance(own, int) and own > 0 else cap
        items = by_section.get(section) or []
        if section == "about" and items:
            sized = [(section, len("\n\n".join(b["text"].strip() for b in items)))]
        else:
            sized = [(b.get("label") or section, len(b["text"].strip())) for b in items]
        for where, size in sized:
            if size > cap:
                bad("too_long", where, f"{size} characters; keep it under {cap} so a recruiter reads it in seconds")
    for section, items in by_section.items():
        cap = limits.get(section)
        if cap is None:
            continue
        if section in ("about", "headline"):
            total = len("\n\n".join(b["text"].strip() for b in items))
            if total > cap:
                bad("over_limit", section, f"{total} characters, the limit is {cap}")
        else:
            for b in items:
                if len(b["text"].strip()) > cap:
                    bad("over_limit", b.get("label") or section, f"{len(b['text'].strip())} characters, the limit is {cap}")

    for i, block in enumerate(blocks):
        where = block.get("label") or f"{block['section']}[{i}]"
        text = block["text"]
        ids = [str(x).strip() for x in block.get("achievements") or [] if str(x).strip()]
        if not ids and block.get("no_claim") is not True:
            bad("uncited_claim", where, "cites no achievement; a paragraph that asserts nothing sets no_claim: true")
        for ident in ids:
            if ident not in project["ids"]:
                bad("unknown_achievement", where, f"{ident} is not in achievements.yaml")
            elif not project["ids"][ident]:
                bad("unverified_achievement", where, f"{ident} is not verified: the user has not confirmed that text")
        for pattern in BANNED + tuple(re.escape(fold(p)) for p in project["avoid"]):
            if re.search(pattern, fold(text)):
                bad("banned_phrase", where, f"matches {pattern!r}")
        for term in jc_module().confidential_hits(text, project.get("confidential") or []):
            bad("confidential_term", where, f"{term!r} is confidential (profile.md confidential_terms)")
        for kind, rx in PRIVATE:
            if rx.search(text):
                bad("private_data", where, f"holds {kind} data that a public profile should not carry unasked")
        for match in re.finditer(r"(?<!\d)\+?\d[\d\s().-]{7,}\d", text):
            digits = re.findall(r"\d+", match.group(0))
            if sum(len(d) for d in digits) >= 9 and not all(re.fullmatch(r"(19|20)\d\d", d) for d in digits):
                bad("private_data", where, "holds a phone number")
                break
        if AGE.search(text) and not project["age_ok"]:
            bad("private_data", where, "states an age, and profile.md does not allow it (include_age_in_cv)")
        if market:
            for row in market.get("terms") or []:
                term = str(row.get("term") or "")
                if term and row.get("in_profile") is False and not row.get("profile_part") and has_term(term, text):
                    bad("claims_a_gap", where, f"uses {term!r}, a market term the profile does not hold")

    skills = copy.get("skills") or []
    if not isinstance(skills, list) or not all(isinstance(s, str) for s in skills):
        raise UsageError("`skills` is a list of text")
    seen = set()
    for skill in skills:
        key = skill.strip().lower()
        if key in seen:
            warnings.append(f"skill {skill!r} is listed twice")
        seen.add(key)
        if len(skill.strip()) > limits.get("skill", 10 ** 6):
            bad("skills_over_limit", skill, f"longer than {limits['skill']} characters")
        if not has_term(skill, project["corpus"]):
            bad("unsupported_skill", skill, "is not in key_skills, achievements.yaml skills, tags or text")
    if len(seen) > limits.get("skills_count", 10 ** 6):
        bad("skills_over_limit", "skills", f"{len(seen)} skills, the limit is {limits['skills_count']}")

    url = copy.get("custom_url")
    if url is not None and not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", str(url)):
        bad("bad_custom_url", "custom_url", "lowercase letters, digits and single dashes only")
    elif url is not None and (len(str(url)) < 3 or len(str(url)) > 100 or re.search(r"\d{4,}", str(url))):
        bad("bad_custom_url", "custom_url", "3 to 100 characters and no long digit run (a default hash or a birth year)")

    heads = by_section.get("headline")
    if heads and project["roles"]:
        front = fold(heads[0]["text"])[:70]
        if not any(fold(role) in front for role in project["roles"]):
            warnings.append("no target role appears in the first 70 characters of the headline, the part shown in search")
    return defects, warnings


def render(copy: dict) -> str:
    out = [f"# {copy.get('platform', 'profile')} - paste-ready copy", "",
           "Paste each block into the matching field yourself. Nothing here was sent to the platform.", ""]
    current = None
    for block in copy["blocks"]:
        if block["section"] != current:
            current = block["section"]
            out += [f"## {current}", ""]
        if block.get("label"):
            out += [f"**{block['label']}**", ""]
        out += [block["text"].strip(), "", f"<!-- achievements: {', '.join(block.get('achievements') or []) or 'none'} -->", ""]
    if copy.get("skills"):
        out += ["## skills", "", ", ".join(copy["skills"]), ""]
    if copy.get("custom_url"):
        out += ["## custom URL", "", f"linkedin.com/in/{copy['custom_url']}" if str(copy.get("platform")).lower() == "linkedin"
                else str(copy["custom_url"]), ""]
    return "\n".join(out)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("copy")
    p.add_argument("--project", required=True)
    p.add_argument("--market")
    p.add_argument("--render")
    p.add_argument("--json", action="store_true")
    ns = p.parse_args(argv)
    try:
        try:
            copy = json.loads(Path(ns.copy).read_text(encoding="utf-8"))
            market = json.loads(Path(ns.market).read_text(encoding="utf-8")) if ns.market else None
        except (OSError, ValueError) as exc:
            raise UsageError(f"cannot read input: {exc}") from exc
        if not isinstance(copy, dict) or not Path(ns.project).is_dir():
            raise UsageError("COPY.json must be an object and --project an existing folder")
        defects, warnings = check(copy, load_project(Path(ns.project)), market)
    except UsageError as exc:
        sys.stderr.write(json.dumps({"error": str(exc), "code": "BAD_INPUT"}) + "\n")
        return 2
    rendered = None
    if not defects and ns.render:
        Path(ns.render).parent.mkdir(parents=True, exist_ok=True)
        Path(ns.render).write_text(render(copy), encoding="utf-8")
        rendered = ns.render
    report = {"ok": not defects, "defects": defects, "warnings": warnings, "rendered": rendered}
    if ns.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        for d in defects:
            print(f"DEFECT {d['defect']} [{d['where']}]: {d['detail']}")
        for w in warnings:
            print(f"WARNING {w}")
        print("ok" if not defects else f"{len(defects)} defect(s)")
    return 0 if not defects else 1


if __name__ == "__main__":
    sys.exit(main())
