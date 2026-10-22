#!/usr/bin/env python3
"""Turns the hiring posts the scout read in the shared browser into the leads the rest of the squad reads.

The browser collects one item per post card (`componentkey` and the card's visible text). This tool does the parsing:
every card the capture holds becomes one lead row, so the count in `meta` can be checked against what was read.

Usage:
  capture_rows.py --kind posts --input CAPTURE.json [--max-age-hours N] [--output FILE]

CAPTURE.json:
  {"source_url": "<the posts search url>", "items": [{"componentkey": "expanded...FeedType_FLAGSHIP_SEARCH",
                                                     "text": "<card innerText>"}]}

A measured post card reads, top to bottom: "Feed post", the author's or page's name, sometimes "• 2nd" and a
headline, the relative age ("31m", "2h"), the button ("Follow", "Join", "Request services"), then the post. The
header stops there: the author's name and headline are not kept (the lead is the employer's post, not a person),
and e-mail addresses and phone numbers are replaced by a marker.

Rules: no card is dropped for its wording. The search already applied the Boolean, and a post that is hiring can
read as "unete a nuestro equipo" or "opening on our team" as easily as "we're hiring": the scout reads the snippet
and decides, and this tool never invents a second keyword filter. A card IS dropped when its relative age ("hace
3 días", "2 semanas", "1 año", "1y", "1 year ago") is older than --max-age-hours, and — because an age the tool
cannot read is not proof of recency — when the window is given and no age could be read at all; those are counted
`dropped_older` and `no_age_dropped`. Without the window every card is kept, and an unreadable age is counted
`no_age`. A row's `date` is never taken from relative text. Cards carry no permalink and no URN, so `id` is a hash of
the card's `componentkey` (stable across visits) and `url` is the search that found the card plus that id, which is a
pointer for the user, not a page to open. A card that embeds a LinkedIn job carries that job id in `job_ids`: read it
with the portal tool's `detail`, never by opening the page. Exit 0 on success, 2 on a usage error or an unreadable
input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from urllib.parse import urlsplit, urlunsplit

AGE = re.compile(
    r"^(?:(?:hace|há|il y a|vor)\s+)?(\d+)\s*(minutes?|mins?|minutos?|m|hours?|hrs?|horas?|h|days?|d[ií]as?|d|"
    r"weeks?|semanas?|w|months?|mo|mes(?:es)?|m[eê]s(?:es)?|years?|a[nñ]os?|yr|y)\b(?:\s+ago|\s+atr[aá]s)?"
    r"(?:\s*[•·]\s*(?:edited|editado|modificada))?$|"
    r"^(just now|ahora mismo|agora mesmo|hace un momento|today|hoy|hoje)$", re.I)
SHORT_UNIT = {"m": 1 / 60, "h": 1, "d": 24, "w": 168, "mo": 720, "y": 8760, "yr": 8760}
AGE_UNIT = (("min", 1 / 60), ("hour", 1), ("hr", 1), ("hora", 1), ("day", 24), ("week", 168), ("semana", 168),
            ("mes", 720), ("month", 720), ("dia", 24), ("year", 8760), ("ano", 8760))
BUTTONS = ("follow", "following", "join", "join community", "request services", "seguir", "unirse",
           "unirme", "solicitar servicios")
FOOTER = ("… more", "... more", "…more", "…", "​", "see more")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")
PHONE = re.compile(r"(?<!\d)(\+?\d[\d\s().-]{7,}\d)(?!\d)")
JOB_LINK = re.compile(r"/jobs/view/(\d{6,})")


class UsageError(ValueError):
    pass


def lines_of(text) -> list[str]:
    out: list[str] = []
    for raw in str(text or "").replace("\r", "\n").split("\n"):
        line = re.sub(r"\s+", " ", raw).strip().strip("​").strip()
        if line and (not out or out[-1].lower() != line.lower()):
            out.append(line)
    return out


def age_hours(text) -> float | None:
    match = AGE.match(str(text or "").strip())
    if not match:
        return None
    if match.group(1) is None:
        return 0.0
    unit = match.group(2).lower().replace("í", "i").replace("ê", "e").replace("ñ", "n")
    if unit in SHORT_UNIT:          # m, h, d, w, mo, y are the card's own short forms
        return round(int(match.group(1)) * SHORT_UNIT[unit], 2)
    for prefix, hours in AGE_UNIT:
        if unit.startswith(prefix):
            return round(int(match.group(1)) * hours, 2)
    return None


def body_of(rows: list[str]) -> tuple[list[str], str | None]:
    """The post's own text and the relative age line: everything after the age and the card's button."""
    head = rows[:9]
    age_at = next((i for i, line in enumerate(head)
                   if len(line) < 25 and age_hours(line) is not None), None)
    start = 0 if age_at is None else age_at + 1
    for i in range(start, min(start + 3, len(rows))):
        if rows[i].strip().lower() in BUTTONS:
            start = i + 1
            break
    body = [line for line in rows[start:] if line not in FOOTER and not re.fullmatch(r"\d+", line)]
    return body, (rows[age_at] if age_at is not None else None)


def redact(text: str) -> str:
    text = EMAIL.sub("[email]", text)

    def mask(match):
        groups = re.findall(r"\d+", match.group(0))
        years = all(re.fullmatch(r"(19|20)\d\d", g) for g in groups)
        return "[phone]" if sum(len(g) for g in groups) >= 9 and not years else match.group(0)

    return PHONE.sub(mask, text)


def ident_of(key: str) -> str:
    return "post-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def search_url(source) -> str:
    parts = urlsplit(str(source or "").strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


def post_rows(items, max_age) -> tuple[list, dict]:
    leads, seen = [], set()
    counts = {"items": len(items), "no_id": 0, "duplicate": 0, "no_text": 0, "dropped_older": 0, "no_age_dropped": 0,
              "no_age": 0}
    for item in items:
        key = str(item.get("componentkey") or "").strip()
        if not key:
            counts["no_id"] += 1
            continue
        if key in seen:
            counts["duplicate"] += 1
            continue
        seen.add(key)
        rows = lines_of(item.get("text"))
        if rows and rows[0].lower() == "feed post":
            rows = rows[1:]
        body, age_line = body_of(rows)
        if not body or not " ".join(body).strip():
            counts["no_text"] += 1
            continue
        age = age_hours(age_line)
        if age is None:
            if max_age is not None:        # an age it cannot read is not proof the post is recent
                counts["no_age_dropped"] += 1
                continue
            counts["no_age"] += 1
        elif max_age is not None and age > max_age:
            counts["dropped_older"] += 1
            continue
        ident = ident_of(key)
        source = search_url(item.get("source_url"))
        job_ids = list(dict.fromkeys(JOB_LINK.findall(" ".join(item.get("anchors") or []))))
        lead = {"id": ident, "kind": "post", "lead": True, "card_id": key,
                "url": f"{source}#{ident}" if source else None, "source": "linkedin-posts",
                "snippet": redact(" ".join(body))[:500], "company": None, "role": None}
        if age_line:
            lead["posted_text"] = age_line
        if age is not None:
            lead["posted_age_hours"] = age
        if job_ids:
            lead["job_ids"] = job_ids
        leads.append(lead)
    return leads, counts


def run(kind, capture, max_age) -> dict:
    items = capture.get("items")
    if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
        raise UsageError("the capture needs an `items` list of objects")
    if max_age is not None and max_age <= 0:
        raise UsageError("--max-age-hours must be positive")
    for item in items:
        item.setdefault("source_url", capture.get("source_url"))
    rows, counts = post_rows(items, max_age)
    meta = {"kind": "posts", "source_url": capture.get("source_url"), "max_age_hours": max_age, "counts": counts,
            "kept": len(rows)}
    if rows:
        meta["note"] = ("posts carry no permalink: `url` is the search that found the card plus its id, a pointer "
                        "for the user, not a page to open")
    return {"meta": meta, "leads": rows}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--kind", required=True, choices=("posts",))
    p.add_argument("--input", required=True)
    p.add_argument("--max-age-hours", type=float)
    p.add_argument("--output")
    ns = p.parse_args(argv)
    try:
        try:
            with open(ns.input, encoding="utf-8") as handle:
                capture = json.load(handle)
        except (OSError, ValueError) as exc:
            raise UsageError(f"{ns.input} is not readable JSON ({exc})") from exc
        if not isinstance(capture, dict):
            raise UsageError("the capture must be a JSON object")
        out = run(ns.kind, capture, ns.max_age_hours)
    except UsageError as exc:
        sys.stderr.write(json.dumps({"error": str(exc), "code": "BAD_INPUT"}) + "\n")
        return 2
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if ns.output:
        with open(ns.output, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
