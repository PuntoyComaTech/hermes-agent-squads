#!/usr/bin/env python3
"""Shows the user what a drafted profile would change, and checks afterwards that the change landed.

`diff` pairs the drafted copy with the profile as it was captured, field by field, so the manager can put "field,
before, after" in front of the user and take a yes per field. `verify` re-reads the profile that was captured after
the edit and exits 0 only when every approved field holds the approved text. Neither command opens a page or writes
the profile: the writer edits, this tool judges.

Usage:
  profile_diff.py diff   CURRENT.json DRAFT.json [--json]
  profile_diff.py verify APPROVED.json CURRENT.json [--json]

CURRENT.json is `documents/linkedin/current.json` (parse_profile.py). DRAFT.json is the copy the writer checked with
check_profile_copy.py: `blocks` with `section` and `text`, plus `skills`. An experience block names its role with
`company` and `title`, or with a `label` of the form "Title at Company".

APPROVED.json is what the manager writes after the user's yes, one row per approved field:
  {"fields": [{"field": "headline", "after": "..."}, {"field": "about", "after": "..."}]}

Field ids: `headline`, `about`, `skills`, `experience:<company>:<title>`. `diff` exits 0 always (it reports, it does not
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
    if field == "skills":
        return [norm(s) for s in current.get("skills") or []]
    if field.startswith(EXPERIENCE):
        body = field[len(EXPERIENCE):]
        company, _, title = body.rpartition(":")
        row = find_role(current, norm(company), norm(title))
        return None if row is None else row.get("description", "")
    return None


def verify(approved: dict, current: dict) -> dict:
    rows = approved.get("fields")
    if not isinstance(rows, list) or not rows:
        raise UsageError("APPROVED.json needs a non-empty `fields` list")
    results, failures = [], []
    for row in rows:
        if not isinstance(row, dict) or not str(row.get("field") or "").strip():
            raise UsageError("every approved row needs a `field`")
        field = str(row["field"]).strip()
        want = row["after"] if "after" in row else row.get("text")
        if want is None:
            raise UsageError(f"approved row {field!r} has no `after` text")
        have = value_of(current, field)
        if isinstance(want, list) or isinstance(have, list):
            ok = [norm(x) for x in (want or [])] == [norm(x) for x in (have or [])]
        else:
            ok = have is not None and norm(have) == norm(want)
        results.append({"field": field, "ok": ok, "expected_chars": len(norm(want)),
                        "found_chars": (len(norm(have)) if have is not None else None)})
        if not ok:
            failures.append({"field": field, "reason": "field not on the profile" if have is None
                             else "the profile text differs", "expected": norm(want)[:120],
                             "found": norm(have)[:120]})
    return {"ok": not failures, "fields": results, "failures": failures,
            "counts": {"approved": len(rows), "verified": len(rows) - len(failures)}}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("diff", help="field, before, after for the manager")
    d.add_argument("current")
    d.add_argument("draft")
    d.add_argument("--json", action="store_true")
    v = sub.add_parser("verify", help="did every approved field land?")
    v.add_argument("approved")
    v.add_argument("current")
    v.add_argument("--json", action="store_true")
    ns = p.parse_args(argv)
    try:
        if ns.cmd == "diff":
            out = diff(load(ns.current, "CURRENT.json"), load(ns.draft, "DRAFT.json"))
        else:
            out = verify(load(ns.approved, "APPROVED.json"), load(ns.current, "CURRENT.json"))
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
            print(("ok   " if f["ok"] else "FAIL ") + f["field"])
        for f in out["failures"]:
            print(f"  {f['field']}: {f['reason']}")
        print("verified" if out["ok"] else f"{len(out['failures'])} field(s) did not land")
    return 0 if (ns.cmd == "diff" or out["ok"]) else 1


if __name__ == "__main__":
    sys.exit(main())