#!/usr/bin/env python3
"""Turns the raw capture of the user's own LinkedIn profile into `documents/linkedin/current.json`.

The writer reads the profile in the shared signed-in browser: the profile page for the name, headline, location and
About text, then `/details/experience/`, `/details/education/` and `/details/skills/`. Each page yields a JSON object
whose fields are the page's own line lists (the selectors are in `references/linkedin-profile-capture.md`), so this
tool holds every rule about how those lines become fields. It never opens a page and never writes the profile.

Usage:
  parse_profile.py CAPTURE.json --output current.json [--role-skills ROLE_SKILLS.json] [--today YYYY-MM-DD] [--json]

ROLE_SKILLS.json: {"<Company>:<Title>": ["skill", ...]}, the boxes ticked in each role's edit form (Page.ticked_skills()
in profile_form.py). It replaces the two skills the page shows for that role.

CAPTURE.json (what the three snippets return, merged):
  {"url": "https://www.linkedin.com/in/<slug>/", "name": "...", "headline": "...", "location": "...",
   "about": "...", "featured": [],
   "experience": {"found": true, "groups": [{"company": "...", "all": ["...", "..."],
                  "roles": [{"lines": ["title", "dates", "..."], "edit": "https://.../details/experience/edit/forms/1/"}]}]},
   "education": {"found": true, "items": [{"lines": ["institution", "degree", "dates", "..."], "edit": "..."}]},
   "skills": {"count": 36, "items": ["SQL", "..."]},
   "profile_languages": ["Español", "English"], "language": "es"}
A role or school may also be a bare list of lines; then it carries no `edit` and profile_form.py cannot open it.
A role (or a one-role group) may carry `skills`: the boxes ticked in its edit form. The page shows two skills and hides
the rest behind `+N skills` (with or without a `Skills:` label); without `skills` the row keeps the two it shows and
`skills_hidden: N`, and profile_diff.py verify refuses to judge that role's skills from it.

`profile_languages` is the profile's own "Profile language" card (primary first); `language` is the language whose text
this capture holds (default: the primary). The page mixes languages field by field, so a secondary language is
captured from the edit forms' language tabs and parsed into its own file (`current.en.json`).

Output: `current.json` with `platform`, `captured`, `url`, `own_profile`, `name`, `headline`, `location`, `about`,
`experience` (one row per role), `education`, `skills`, `skills_count`, `top_skills` (the "Top skills" line LinkedIn
appends to the About card, never part of the About text), `profile_languages`, `language`, `featured` and `missing`
(sections the capture did not carry). Exit 0 written, 1 when the capture holds no profile at all (a sign-in page, a checkpoint, an empty
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
# The role card's skills line without its label, as LinkedIn renders it since 2026-10: "Railway, Cloudflare and +1
# skill", "HTML5, Node.js and +3 skills", "React y 2 aptitudes más". Only a short line ending in that count matches.
BARE_SKILLS = re.compile(r"^(?P<list>(?:[^•.]|\.(?=\S)){1,160}?)\s*(?:,\s*|\s+(?:and|y|e)\s+)\+?\s*(?P<more>\d+)\s*"
                         r"(?:more\s+)?(?:skills?|aptitudes?|competencias?)(?:\s+m[aá]s)?\s*$", re.I)
MORE_SKILLS = re.compile(r"\+\s*(\d+)\s*(?:more\s+)?(?:skills?|aptitudes?|competencias?)", re.I)
MORE = re.compile(r"^(?:…|\.\.\.)\s*more?$", re.I)
EMPLOYMENT = re.compile(r"^(full-time|part-time|contract|freelance|internship|self-employed|seasonal|"
                        r"apprenticeship|jornada completa|media jornada|contrato|pasantía)\b", re.I)


TOP_SKILLS = re.compile(r"\n\s*(?:top skills|aptitudes principales|principais compet[eê]ncias)\s*\n(?P<list>[\s\S]*)$",
                        re.I)
LANGUAGE_NAMES = {"español": "es", "spanish": "es", "english": "en", "inglés": "en", "português": "pt",
                  "portuguese": "pt", "français": "fr", "french": "fr", "deutsch": "de", "german": "de",
                  "italiano": "it", "italian": "it", "nederlands": "nl"}


class UsageError(ValueError):
    pass


def language_code(value) -> str:
    """'Español', 'Spanish (Primary profile)', 'es', 'en_US' -> a two-letter code, or '' when unknown."""
    text = re.sub(r"\(.*?\)", "", one_line(value)).strip().lower()
    if re.fullmatch(r"[a-z]{2}([_-][a-z]{2})?", text):
        return text[:2]
    return LANGUAGE_NAMES.get(text, "")


def split_top_skills(about: str) -> tuple[str, list[str]]:
    """The About card ends with LinkedIn's own 'Top skills' line; it is a setting, not About text."""
    match = TOP_SKILLS.search("\n" + about)
    if not match:
        return about, []
    body = ("\n" + about)[:match.start()].strip()
    items = [one_line(x) for x in re.split(r"\s*[•·|]\s*|\n", match.group("list")) if one_line(x)]
    return body, items


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


def is_skills_line(line: str) -> bool:
    """`Skills: A, B, +3 skills` or the bare `A, B and +1 skill`: the role's skills, never its description."""
    text = clean(line)
    return bool(SKILLS_LINE.match(text) or BARE_SKILLS.match(text))


def hidden_skills(line: str) -> int:
    """How many skills the line hides behind its `+N skills` count (0 when it lists them all)."""
    text = clean(line)
    bare = BARE_SKILLS.match(text)
    if bare and not SKILLS_LINE.match(text):
        return int(bare.group("more"))
    match = MORE_SKILLS.search(text)
    return int(match.group(1)) if match else 0


def split_skills(line: str) -> list[str]:
    """`Skills: React.js, Node.js, +3 skills` or `React.js, Node.js and +3 skills` -> ['React.js', 'Node.js']
    (the count is not a skill)."""
    body = SKILLS_LINE.sub("", clean(line))
    bare = BARE_SKILLS.match(body)
    if bare and not SKILLS_LINE.match(clean(line)):
        body = bare.group("list")
    out = []
    for part in re.split(r",\s*|\s+(?:and|y|e)\s+", body):
        part = part.strip()
        if not part or re.fullmatch(r"\+\s*\d+.*", part):
            continue
        out.append(part)
    return out


def role_from(lines: list[str], form_skills=None) -> dict:
    """One role's lines: title, dates, location and then skills or description. `form_skills` (the boxes ticked in
    the role's edit form) is the full list; the page shows two and hides the rest behind `+N skills`."""
    title = one_line(lines[0]) if lines else ""
    dates = one_line(lines[1]) if len(lines) > 1 else ""
    rest = [one_line(x) for x in lines[2:] if one_line(x)]
    location, skills, description, hidden = "", [], [], 0
    # a role with no location line starts straight with its description: a bullet or a sentence is not a place
    if (rest and not is_skills_line(rest[0]) and not DATES.match(rest[0])
            and not re.match(r"^[•\-*–]", rest[0]) and len(rest[0]) <= 80 and not rest[0].endswith(".")):
        location = rest.pop(0)
    for line in rest:
        if is_skills_line(line):
            skills, hidden = split_skills(line), hidden_skills(line)
        else:
            description.append(line)
    if isinstance(form_skills, list) and form_skills:
        skills, hidden = [one_line(s) for s in form_skills if one_line(s)], 0
    row = {"title": title, "dates": dates, "location": location,
           "description": "\n".join(description).strip(), "skills": skills}
    if hidden:
        row["skills_hidden"] = hidden  # the page listed only part: profile_diff.py verify asks for the form's boxes
    return row


def experience_rows(section, role_skills=None) -> list[dict]:
    rows = []
    role_skills = {norm_key(k): v for k, v in (role_skills or {}).items()}
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
        if not roles and len(all_lines) > 2 and " · " in all_lines[1] and DATES.match(all_lines[2]):
            # a company with one role renders as one item: title, "Company · Employment", dates, then the rest
            company, _, employment = all_lines[1].partition(" · ")
            company, employment = company.strip(), employment.strip()
            roles = [{"lines": [all_lines[0], *all_lines[2:]], "edit": group.get("edit"), "skills": group.get("skills")}]
            company_dates = company_location = ""
        for role_lines in roles:
            row = role_from(as_list(lines_of(role_lines)),
                            role_lines.get("skills") if isinstance(role_lines, dict) else None)
            if not row["title"]:
                continue
            boxes = role_skills.get(norm_key(f"{company}:{row['title']}"))
            if isinstance(boxes, list):
                row["skills"] = [one_line(s) for s in boxes if one_line(s)]
                row.pop("skills_hidden", None)
            rows.append({"company": company, "employment": employment, "company_dates": company_dates,
                         "company_location": company_location, **row, "edit": edit_of(role_lines)})
    return rows


def norm_key(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def lines_of(item):
    """A capture item is its list of lines, or {"lines": [...], "edit": "<the entry's edit-form URL>"}."""
    return item.get("lines") if isinstance(item, dict) else item


def edit_of(item) -> str:
    """The entry's own edit form, kept so the apply step opens that form and no other."""
    return one_line(item.get("edit")) if isinstance(item, dict) else ""


def education_rows(section) -> list[dict]:
    rows = []
    if not isinstance(section, dict):
        return rows
    for item in section.get("items") or []:
        lines = as_list(lines_of(item))
        if not lines:
            continue
        rest = [x for x in lines[3:] if not is_skills_line(x)]
        rows.append({"institution": lines[0], "degree": lines[1] if len(lines) > 1 else "",
                     "dates": lines[2] if len(lines) > 2 else "",
                     "description": "\n".join(rest).strip(), "edit": edit_of(item)})
    return rows


def build(capture: dict, today: str, role_skills=None) -> dict:
    if not isinstance(capture, dict):
        raise UsageError("CAPTURE.json must be an object")
    url = one_line(capture.get("url"))
    match = SLUG.search(url)
    about, top_skills = split_top_skills(clean(capture.get("about")))
    raw_languages = capture.get("profile_languages")
    languages = []
    for item in raw_languages if isinstance(raw_languages, list) else []:
        code = language_code(item)
        if code and code not in languages:
            languages.append(code)
    language = language_code(capture.get("language")) or (languages[0] if languages else "")
    experience = experience_rows(capture.get("experience"), role_skills)
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
    if not languages:
        missing.append("profile_languages")
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
        "top_skills": top_skills,
        "profile_languages": languages,
        "primary_language": languages[0] if languages else "",
        "language": language,
        "featured": [one_line(x) for x in (capture.get("featured") or []) if one_line(x)],
        "missing": sorted(set(missing)),
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("capture")
    p.add_argument("--output", required=True)
    p.add_argument("--today", default=date.today().isoformat())
    p.add_argument("--role-skills", help='{"<Company>:<Title>": [skills]} from each role form\'s ticked boxes')
    p.add_argument("--json", action="store_true")
    ns = p.parse_args(argv)
    try:
        try:
            capture = json.loads(Path(ns.capture).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise UsageError(f"cannot read the capture: {exc}") from exc
        role_skills = None
        if ns.role_skills:
            try:
                role_skills = json.loads(Path(ns.role_skills).read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                raise UsageError(f"cannot read --role-skills: {exc}") from exc
            if not isinstance(role_skills, dict):
                raise UsageError('--role-skills must be {"<Company>:<Title>": [skills]}')
        try:
            current = build(capture, ns.today, role_skills)
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