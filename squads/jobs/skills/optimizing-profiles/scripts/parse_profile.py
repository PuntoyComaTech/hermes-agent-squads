#!/usr/bin/env python3
"""Turns the raw capture of the user's own LinkedIn profile into `documents/linkedin/current.json`.

The writer reads the profile in the shared signed-in browser: the profile page for the name, headline, location and
About text, then `/details/experience/`, `/details/education/` and `/details/skills/`. Each page yields a JSON object
whose fields are the page's own line lists (the selectors are in `references/linkedin-profile-capture.md`), so this
tool holds every rule about how those lines become fields. It never opens a page and never writes the profile.

Usage:
  parse_profile.py CAPTURE.json --output current.json [--today YYYY-MM-DD] [--json]

CAPTURE.json (what the three snippets return, merged):
  {"url": "https://www.linkedin.com/in/<slug>/", "name": "...", "headline": "...", "location": "...",
   "about": "...", "featured": [],
   "experience": {"found": true, "groups": [{"company": "...", "all": ["...", "..."], "roles": [["title", "dates", "..."]]}]},
   "education": {"found": true, "items": [["institution", "degree", "dates", "..."]]},
   "skills": {"count": 36, "items": ["SQL", "..."]}}

Output: `current.json` with `platform`, `captured`, `url`, `own_profile`, `name`, `headline`, `location`, `about`,
`experience` (one row per role), `education`, `skills`, `skills_count`, `featured` and `missing` (sections the capture
did not carry). Exit 0 written, 1 when the capture holds no profile at all (a sign-in page, a checkpoint, an empty
tab), 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

SLUG = re.compile(r"linkedin\.com/in/([A-Za-z0-9_-]+)")
DATES = re.compile(r"^(?:\w{3}\s+\d{4}|\d{4})\s*[-–—]\s*(?:present|actualidad|\w{3}\s+\d{4}|\d{4})", re.I)
SKILLS_LINE = re.compile(r"^(?:skills|aptitudes|competencias)\s*:\s*", re.I)
MORE = re.compile(r"^(?:…|\.\.\.)\s*more?$", re.I)
EMPLOYMENT = re.compile(r"^(full-time|part-time|contract|freelance|internship|self-employed|seasonal|"
                        r"apprenticeship|jornada completa|media jornada|contrato|pasantía)\b", re.I)


class UsageError(ValueError):
    pass


def clean(value) -> str:
    """Normalise a block of text: trim each line, drop '… more', keep one blank line between paragraphs."""
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    kept = [line for line in lines if line and not MORE.match(line)]
    return "\n".join(kept) if "\n" not in text else re.sub(r"\n{2,}", "\n\n", "\n".join(lines).strip())


def one_line(value) -> str:
    """A single field: its first non-empty line with whitespace collapsed."""
    for line in str(value or "").replace("\r", "\n").split("\n"):
        line = re.sub(r"\s+", " ", line).strip()
        if line and not MORE.match(line):
            return line
    return ""


def as_list(value) -> list[str]:
    if isinstance(value, list):
        return [one_line(v) for v in value if one_line(v)]
    return [line for line in clean(value).split("\n") if line]


def split_skills(line: str) -> list[str]:
    """`Skills: React.js, Node.js, +3 skills` -> ['React.js', 'Node.js'] (the count is not a skill)."""
    body = SKILLS_LINE.sub("", clean(line))
    out = []
    for part in re.split(r",\s*", body):
        part = part.strip()
        if not part or re.fullmatch(r"\+\s*\d+.*", part):
            continue
        out.append(part)
    return out


def role_from(lines: list[str]) -> dict:
    """One role's lines: title, dates, location and then skills or description."""
    title = one_line(lines[0]) if lines else ""
    dates = one_line(lines[1]) if len(lines) > 1 else ""
    rest = [one_line(x) for x in lines[2:] if one_line(x)]
    location, skills, description = "", [], []
    if rest and not SKILLS_LINE.match(rest[0]) and not DATES.match(rest[0]):
        location = rest.pop(0)
    for line in rest:
        if SKILLS_LINE.match(line):
            skills = split_skills(line)
        else:
            description.append(line)
    return {"title": title, "dates": dates, "location": location,
            "description": "\n".join(description).strip(), "skills": skills}


def experience_rows(section) -> list[dict]:
    rows = []
    if not isinstance(section, dict):
        return rows
    groups = section.get("groups") or []
    for group in groups:
        if not isinstance(group, dict):
            continue
        all_lines = as_list(group.get("all"))
        company = one_line(group.get("company")) or (all_lines[0] if all_lines else "")
        employment, company_dates, company_location = "", "", ""
        for line in all_lines:
            if line == company:
                continue
            if not employment and EMPLOYMENT.match(line):
                head, _, tail = line.partition(" · ")
                employment = head.strip()
                company_dates = tail.strip()
                continue
            if not company_location and not DATES.match(line):
                company_location = line
                break
        roles = group.get("roles") or []
        for role_lines in roles:
            row = role_from(as_list(role_lines))
            if not row["title"]:
                continue
            rows.append({"company": company, "employment": employment, "company_dates": company_dates,
                         "company_location": company_location, **row})
    return rows


def education_rows(section) -> list[dict]:
    rows = []
    if not isinstance(section, dict):
        return rows
    for item in section.get("items") or []:
        lines = as_list(item)
        if not lines:
            continue
        rest = [x for x in lines[3:] if not SKILLS_LINE.match(x)]
        rows.append({"institution": lines[0], "degree": lines[1] if len(lines) > 1 else "",
                     "dates": lines[2] if len(lines) > 2 else "",
                     "description": "\n".join(rest).strip()})
    return rows


def build(capture: dict, today: str) -> dict:
    if not isinstance(capture, dict):
        raise UsageError("CAPTURE.json must be an object")
    url = one_line(capture.get("url"))
    match = SLUG.search(url)
    about = clean(capture.get("about"))
    experience = experience_rows(capture.get("experience"))
    education = education_rows(capture.get("education"))
    skills_section = capture.get("skills")
    skills_section = skills_section if isinstance(skills_section, dict) else {}
    skills = [s for s in (one_line(x) for x in (skills_section.get("items") or [])) if s]
    headline = one_line(capture.get("headline"))
    name = one_line(capture.get("name"))
    if not any((name, headline, about, experience, skills)):
        raise ValueError("the capture holds no profile: a sign-in page, a checkpoint or an empty tab")
    missing = []
    for key in ("experience", "education", "skills"):
        section = capture.get(key)
        if not isinstance(section, dict) or section.get("found") is False:
            missing.append(key)
    if not skills and "skills" not in missing:
        missing.append("skills")
    count = skills_section.get("count")
    return {
        "platform": "linkedin",
        "captured": today,
        "url": url or (f"https://www.linkedin.com/in/{match.group(1)}/" if match else ""),
        "own_profile": match.group(1) if match else one_line(capture.get("own_slug")),
        "name": name,
        "headline": headline,
        "location": one_line(capture.get("location")),
        "about": about,
        "experience": experience,
        "education": education,
        "skills": skills,
        "skills_count": len(skills) or (count if isinstance(count, int) else 0),
        "featured": [one_line(x) for x in (capture.get("featured") or []) if one_line(x)],
        "missing": sorted(set(missing)),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("capture")
    p.add_argument("--output", required=True)
    p.add_argument("--today", default=date.today().isoformat())
    p.add_argument("--json", action="store_true")
    ns = p.parse_args(argv)
    try:
        try:
            capture = json.loads(Path(ns.capture).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise UsageError(f"cannot read the capture: {exc}") from exc
        try:
            current = build(capture, ns.today)
        except ValueError as exc:
            sys.stderr.write(json.dumps({"error": str(exc), "code": "EMPTY_CAPTURE"}) + "\n")
            return 1
    except UsageError as exc:
        sys.stderr.write(json.dumps({"error": str(exc), "code": "BAD_INPUT"}) + "\n")
        return 2
    out = Path(ns.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(current, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    summary = {"ok": True, "written": str(out), "name": current["name"],
               "roles": len(current["experience"]), "education": len(current["education"]),
               "skills": len(current["skills"]), "about_chars": len(current["about"]),
               "headline_chars": len(current["headline"]), "missing": current["missing"]}
    if ns.json:
        print(json.dumps(summary, ensure_ascii=False, indent=1))
    else:
        print(f"wrote {out}: {summary['roles']} roles, {summary['education']} education, "
              f"{summary['skills']} skills, headline {summary['headline_chars']} chars, "
              f"about {summary['about_chars']} chars"
              + (f"; missing: {', '.join(current['missing'])}" if current["missing"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())