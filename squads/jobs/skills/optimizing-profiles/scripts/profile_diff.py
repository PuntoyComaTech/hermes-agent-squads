#!/usr/bin/env python3
"""Shows the user what a drafted profile would change, and checks afterwards that the change landed.

`diff` pairs the drafted copy with the profile as it was captured, field by field, so the manager can put "field,
before, after" in front of the user and take a yes per field. `verify` re-reads the profile that was captured after
the edit and exits 0 only when every approved field holds the approved text. Neither command opens a page or writes
the profile: the writer edits, this tool judges.

Usage:
  profile_diff.py diff   CURRENT.json DRAFT.json [--json]
  profile_diff.py verify APPROVED.json CURRENT.json [CURRENT.en.json ...] [--json]

A profile with two languages holds two texts per field. Each CURRENT file is one language's capture (`language` in
the file); an approved row with `language` is checked against the capture of that language, and a row whose language
no capture holds fails as "no capture in <lang>". Skills and top skills are one list for every language.

CURRENT.json is `documents/linkedin/current.json` (parse_profile.py). DRAFT.json is the copy the writer checked with
check_profile_copy.py: `blocks` with `section` and `text`, plus `skills`. An experience block names its role with
`company` and `title`, or with a `label` of the form "Title at Company".

APPROVED.json is what the manager writes after the user's yes, one row per approved field:
  {"fields": [{"field": "headline", "language": "es", "after": "..."}],
   "structure": [{"kind": "experience_title", "company": "Contoso", "title": "Frontend Developer",
                  "was": "Frontend Junior Analyst"}]}

`structure` rows hold the form edits a user approved (a position form is just a form: titles, dates, a new position, a
deletion). Kinds and their keys:
  experience_title   company, title, was?   (the entry carries `title`; `was` is the name it had)
  experience_dates   company, title, from, to   (to: "Present" matches present/actualidad)
  experience_create  company, title, from, to
  experience_delete  company, title
  education_title    institution, title (degree name), was?
  education_dates    institution, from, to
  education_delete   institution
`from`/`to` are the date tokens LinkedIn shows ("Oct 2023"). Structure is one list for every language.

Field ids: `headline`, `about`, `skills`, `top_skills`, `experience:<company>:<title>`,
`role_skills:<company>:<title>` (the skills shown under a role) and `education:<institution>` (its description).
Skills are compared as a set, case-insensitively: LinkedIn orders them itself and keeps its own casing for a skill
that was already on the profile. `diff` exits 0 always (it reports, it does not
judge); `verify` exits 0 when every approved field matches, 1 when one differs and 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

EXPERIENCE = "experience:"


class UsageError(ValueError):
    pass


def norm(text) -> str:
    """Whitespace-normalised text: the comparison every verify uses."""
    return re.sub(r"\s+", " ", str(text or "")).strip()


def same(before, after) -> bool:
    """Field equality as verify applies it: whitespace-normalised, lists item by item."""
    if isinstance(before, list) or isinstance(after, list):
        return [norm(x) for x in (before or [])] == [norm(x) for x in (after or [])]
    return norm(before) == norm(after)


def load(path: str, what: str) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise UsageError(f"cannot read {what}: {exc}") from exc
    if not isinstance(data, dict):
        raise UsageError(f"{what} must be a JSON object")
    return data


def blocks_of(draft: dict) -> list[dict]:
    blocks = draft.get("blocks")
    if not isinstance(blocks, list):
        raise UsageError("the draft needs a `blocks` list")
    return [b for b in blocks if isinstance(b, dict) and str(b.get("text") or "").strip()]


def joined(draft: dict, section: str, sep: str = "\n\n") -> str:
    return sep.join(str(b["text"]).strip() for b in blocks_of(draft) if str(b.get("section") or "") == section)


def role_key(block: dict) -> tuple[str, str]:
    company = norm(block.get("company"))
    title = norm(block.get("title"))
    if company and title:
        return company, title
    label = norm(block.get("label"))
    for pattern in (r"^(?P<title>.+?)\s+(?:at|en|@)\s+(?P<company>.+)$",
                    r"^(?P<title>.+?)\s*[—–-]\s*(?P<company>.+)$",
                    r"^(?P<title>[^,]+),\s*(?P<company>.+)$"):
        match = re.match(pattern, label)
        if match:
            return norm(match.group("company")), norm(match.group("title"))
    return company, title


def skill_set(items) -> list[str]:
    return sorted({norm(x).lower() for x in items or [] if norm(x)})


def find_school(current: dict, institution: str) -> dict | None:
    for row in current.get("education") or []:
        if isinstance(row, dict) and norm(row.get("institution")).lower() == institution.lower():
            return row
    return None


def find_role(current: dict, company: str, title: str) -> dict | None:
    """The row the field id names, by company and title; a role the profile does not hold has no row.

    There is no "closest row" fallback: a draft for a job the profile does not list would otherwise be paired with
    whatever single role happens to be there, the manager would ask the user to approve overwriting that role, and
    `verify` would then call the wrong text "applied".
    """
    rows = [r for r in current.get("experience") or [] if isinstance(r, dict)]
    for row in rows:
        if norm(row.get("company")).lower() == company.lower() and norm(row.get("title")).lower() == title.lower():
            return row
    return None


def diff(current: dict, draft: dict) -> dict:
    fields: list[dict] = []

    def add(field: str, label: str, before, after, matched: bool = True):
        fields.append({"field": field, "label": label, "before": before, "after": after,
                       "changed": not same(before, after), "matched": matched})

    if joined(draft, "headline", "\n"):
        add("headline", "Headline", current.get("headline", ""), joined(draft, "headline", "\n"))
    if joined(draft, "about"):
        add("about", "About", current.get("about", ""), joined(draft, "about"))
    skills = draft.get("skills")
    if isinstance(skills, list) and skills:
        add("skills", f"Skills ({len(skills)})", list(current.get("skills") or []),
            [str(s) for s in skills])
        fields[-1]["changed"] = skill_set(current.get("skills")) != skill_set(skills)
    top = draft.get("top_skills")
    if isinstance(top, list) and top:
        add("top_skills", "Top skills", list(current.get("top_skills") or []), [str(s) for s in top])
    for block in blocks_of(draft):
        if str(block.get("section") or "") != "education":
            continue
        school = norm(block.get("institution"))
        row = find_school(current, school) if school else None
        add(f"education:{school}", f"Education: {school or 'school'}", None if row is None else row.get("description", ""),
            str(block["text"]).strip(), matched=row is not None)
    for block in blocks_of(draft):
        if str(block.get("section") or "") != "experience":
            continue
        company, title = role_key(block)
        row = find_role(current, company, title) if company or title else None
        label = f"{title or 'role'} at {company or 'company'}"
        field = f"{EXPERIENCE}{company}:{title}"
        if row is None:
            add(field, label, None, str(block["text"]).strip(), matched=False)
        else:
            add(field, label, row.get("description", ""), str(block["text"]).strip())
        if isinstance(block.get("role_skills"), list) and block["role_skills"]:
            have = None if row is None else list(row.get("skills") or [])
            add(f"role_skills:{company}:{title}", f"Skills of {label}", have, [str(s) for s in block["role_skills"]],
                matched=row is not None)
            fields[-1]["changed"] = have is None or skill_set(have) != skill_set(block["role_skills"])
    changed = [f["field"] for f in fields if f["changed"]]
    return {"platform": draft.get("platform") or current.get("platform"), "captured": current.get("captured"),
            "fields": fields, "changed": changed,
            "unmatched": [f["field"] for f in fields if not f["matched"]],
            "counts": {"fields": len(fields), "changed": len(changed)}}


def value_of(current: dict, field: str):
    """The profile's current value for a field id, or a sentinel when the field is not on the profile."""
    if field == "headline":
        return current.get("headline", "")
    if field == "about":
        return current.get("about", "")
    if field in ("skills", "top_skills"):
        return [norm(s) for s in current.get(field) or []]
    if field.startswith("education:"):
        row = find_school(current, norm(field[len("education:"):]))
        return None if row is None else row.get("description", "")
    if field.startswith("role_skills:"):
        company, _, title = field[len("role_skills:"):].rpartition(":")
        row = find_role(current, norm(company), norm(title))
        return None if row is None else [norm(s) for s in row.get("skills") or []]
    if field.startswith(EXPERIENCE):
        body = field[len(EXPERIENCE):]
        company, _, title = body.rpartition(":")
        row = find_role(current, norm(company), norm(title))
        return None if row is None else row.get("description", "")
    return None


def date_in(have, token: str, what: str) -> bool:
    """One date token ("Oct 2023", "Present") must show in the dates line the profile captured."""
    text = norm(have).lower()
    want = norm(token).lower()
    if want in ("present", "current", "actualidad"):
        return bool(re.search(r"present|actualidad|atual", text))
    return want in text


def check_structure(rows, current: dict) -> tuple[list, list]:
    """The approved form edits against the profile as captured after the edits: final state, not the diff."""
    results, failures = [], []
    for row in rows or []:
        if not isinstance(row, dict) or not str(row.get("kind") or "").strip():
            raise UsageError("every structure row needs a `kind`")
        kind = str(row["kind"]).strip()
        company, title = norm(row.get("company")), norm(row.get("title"))
        school = norm(row.get("institution"))
        have, why = None, ""
        if kind in ("experience_title", "experience_dates", "experience_create"):
            have = find_role(current, company, title)
            if have is not None:
                want_from, want_to = row.get("from"), row.get("to")
                if want_from and not date_in(have.get("dates"), str(want_from), "from"):
                    why = f"the dates do not show {want_from}"
                elif want_to and not date_in(have.get("dates"), str(want_to), "to"):
                    why = f"the dates do not show {want_to}"
                elif row.get("was") and find_role(current, company, norm(row.get("was"))) is not None:
                    why = f"the entry still carries its old title {row.get('was')!r}"
            else:
                why = "the entry is not on the profile"
        elif kind == "experience_delete":
            have = find_role(current, company, title)
            why = "the entry is still on the profile" if have is not None else ""
        elif kind in ("education_title", "education_dates"):
            have = find_school(current, school)
            if have is None:
                why = "the school is not on the profile"
            elif row.get("from") and not date_in(have.get("dates"), str(row["from"]), "from"):
                why = f"the dates do not show {row['from']}"
            elif row.get("to") and not date_in(have.get("dates"), str(row["to"]), "to"):
                why = f"the dates do not show {row['to']}"
            elif row.get("was") and find_school(current, norm(row.get("was"))) is not None:
                why = f"the entry still carries its old name {row.get('was')!r}"
        elif kind == "education_delete":
            have = find_school(current, school)
            why = "the school is still on the profile" if have is not None else ""
        else:
            raise UsageError(f"unknown structure kind {kind!r}")
        label = f"{title or school}{' at ' + company if company else ''}"
        ok = (have is None) if kind.endswith("delete") else (why == "")
        results.append({"field": f"structure:{kind}:{label}", "ok": ok, "reason": why or None})
        if not ok:
            failures.append({"field": f"structure:{kind}:{label}", "reason": why})
    return results, failures


def verify(approved: dict, current: dict | list) -> dict:
    captures = current if isinstance(current, list) else [current]
    by_language = {str(c.get("language") or "").lower()[:2]: c for c in captures}
    rows = approved.get("fields") or []
    structure = approved.get("structure") or []
    if not isinstance(rows, list) or (not rows and not structure):
        raise UsageError("APPROVED.json needs a `fields` list or `structure` rows")
    results, failures = [], []
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("field") or "").strip():
            raise UsageError("every approved row needs a `field`")
        field = str(row["field"]).strip()
        want = row["after"] if "after" in row else row.get("text")
        if want is None:
            raise UsageError(f"approved row {field!r} has no `after` text")
        lang = str(row.get("language") or "").lower()[:2]
        shared = field in ("skills", "top_skills") or field.startswith("role_skills:")
        capture = captures[0] if (shared or not lang) else by_language.get(lang)
        if capture is None:
            results.append({"field": field, "language": lang, "ok": False, "expected_chars": len(norm(want)),
                            "found_chars": None})
            failures.append({"field": field, "language": lang, "reason": f"no capture in {lang}: re-read the "
                             f"profile in that language tab", "expected": norm(str(want))[:120], "found": ""})
            continue
        have = value_of(capture, field)
        if field == "top_skills":
            ok = have is not None and [norm(x).lower() for x in want or []] == [norm(x).lower() for x in have]
        elif isinstance(want, list) or isinstance(have, list):
            ok = have is not None and skill_set(want) == skill_set(have)
        else:
            ok = have is not None and norm(have) == norm(want)
        results.append({"field": field, "language": lang, "ok": ok, "expected_chars": len(norm(want)),
                        "found_chars": (len(norm(have)) if have is not None else None)})
        if not ok:
            failures.append({"field": field, "language": lang, "reason": "field not on the profile" if have is None
                             else "the profile text differs", "expected": norm(want)[:120],
                             "found": norm(have)[:120]})
    if structure:
        s_results, s_failures = check_structure(structure, captures[0])
        results += s_results
        failures += s_failures
    total = len(rows) + len(structure)
    return {"ok": not failures, "fields": results, "failures": failures,
            "counts": {"approved": total, "verified": total - len(failures)}}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diff", help="field, before, after for the manager")
    d.add_argument("current")
    d.add_argument("draft")
    d.add_argument("--json", action="store_true")
    v = sub.add_parser("verify", help="did every approved field land?")
    v.add_argument("approved")
    v.add_argument("current", nargs="+", help="one capture per profile language")
    v.add_argument("--json", action="store_true")
    ns = p.parse_args(argv)
    try:
        if ns.cmd == "diff":
            out = diff(load(ns.current, "CURRENT.json"), load(ns.draft, "DRAFT.json"))
        else:
            out = verify(load(ns.approved, "APPROVED.json"), [load(c, "CURRENT.json") for c in ns.current])
    except UsageError as exc:
        sys.stderr.write(json.dumps({"error": str(exc), "code": "BAD_INPUT"}) + "\n")
        return 2
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    elif ns.cmd == "diff":
        for f in out["fields"]:
            mark = "CHANGE" if f["changed"] else "same"
            print(f"{mark} {f['field']}")
            if f["changed"]:
                print(f"  before: {norm(f['before'])[:200] or '(empty)'}")
                print(f"  after:  {norm(f['after'])[:200]}")
        if out["unmatched"]:
            print(f"not on the profile, cannot be applied: {', '.join(out['unmatched'])}")
        print(f"{out['counts']['changed']} of {out['counts']['fields']} fields change")
    else:
        for f in out["fields"]:
            print(("ok   " if f["ok"] else "FAIL ") + f["field"] + (f" [{f['language']}]" if f.get("language") else ""))
        for f in out["failures"]:
            print(f"  {f['field']}: {f['reason']}")
        print("verified" if out["ok"] else f"{len(out['failures'])} field(s) did not land")
    return 0 if (ns.cmd == "diff" or out["ok"]) else 1


if __name__ == "__main__":
    sys.exit(main())