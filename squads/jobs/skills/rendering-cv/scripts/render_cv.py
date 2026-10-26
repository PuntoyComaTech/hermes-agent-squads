#!/usr/bin/env python3
"""Render a CV or a cover letter to the files an application submits, and report defects.

Inputs:  --content cv_content.json (--kind cv) or cover_letter.md (--kind letter)
Outputs: --output cv_ats.html, cv_ats.txt, cv_ats.pdf (letter: letter_ats.*), cv.docx (letter: letter.docx),
         CV_<Name>_<Surname>.pdf: a byte copy of cv_ats.pdf named after the printed name (contact.yaml
         `short_name` wins), the file the applier uploads and the owner receives; earlier CV_*.pdf copies are removed,
         render_report.json, or render_report_letter.json for --kind letter (pages, page budget, cuts, stretch flags, keyword coverage, defects, warnings)

Profile facts (--profile profile.md): candidate.stage (section order and stage checks), candidate.age printed only
with candidate.include_age_in_cv: true, market.country (paper size), market.cv_page_limit (page budget),
market.conventions.references_line. Achievements (--achievements achievements.yaml): every cited id must exist and
be verified, and a language level is never raised above the declared CEFR level.

Page budget: --pages wins; otherwise the profile limit (CV 2, letter 1). Only a measured PDF over budget triggers
cutting: the lowest relevance-weighted experience bullet is removed, one at a time, and listed under "cuts". No
bullet text is ever changed. Without a PDF engine nothing is cut; the page count is estimated and reported as such.

Exit codes: 0 clean, 1 the report holds defects, 2 usage or input error. No network.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import importlib.util
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jobs-contract" / "scripts"))
import jobs_common as jc  # noqa: E402 - shared YAML subset reader and front matter helpers

SKILL_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = SKILL_DIR / "templates"
TEMPLATE_NAMES = ("classic", "compact", "modern")
TEMPLATE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
GATE_SUFFIX = ".gate.json"  # written by template_check.py --register beside a project template
STAGES = ("first_job", "junior", "mid", "senior", "lead", "career_change", "returning")
LETTER_PAPER_COUNTRIES = {"US", "CA", "MX", "PH"}
DASHES = "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"
MAX_CUTS = 40
CHARS_PER_LINE, LINES_PER_PAGE = 92, 56
BULLET_WORDS = (12, 22)
LETTER_WORDS_MAX = 250        # a recruiter reads a letter in under a minute
SUMMARY_WORDS_MAX = 50        # three short lines: who, what, for whom
ROLE_BULLETS_MAX = (5, 3)     # most recent role, every other role: a skim reader stops after that
KEYWORD_REPEAT_MAX = 3
STRONG_OWNERSHIP = {"led", "managed", "owned", "architected", "launched", "designed", "built", "created",
                    "drove", "directed", "established", "delivered"}
WEAK_PROFICIENCY = {"participated", "familiar"}

# Section order per stage. Keys are section names; sections without content are skipped.
DEFAULT_ORDER = ["summary", "transferable", "experience", "skills", "projects", "education", "languages"]
STAGE_ORDER = {
    "first_job": ["summary", "education", "projects", "experience", "skills", "languages"],
    "career_change": ["summary", "transferable", "skills", "experience", "projects", "education", "languages"],
    "senior": ["summary", "experience", "skills", "projects", "education", "languages"],
    "returning": ["summary", "experience", "skills", "projects", "education", "languages"],
}

# Headings follow the CV language; a language without a table falls back to English (reported as a warning).
HEADINGS = {
    "en": {"summary": "Summary", "transferable": "Transferable skills", "experience": "Experience",
           "projects": "Projects", "skills": "Skills", "education": "Education", "languages": "Languages"},
    "es": {"summary": "Perfil", "transferable": "Habilidades transferibles", "experience": "Experiencia",
           "projects": "Proyectos", "skills": "Habilidades", "education": "Formaci\u00f3n", "languages": "Idiomas"},
}
PHRASES = {
    "en": {"closing": "Kind regards,", "references": "References available upon request.", "age": "Age"},
    "es": {"closing": "Atentamente,", "references": "Referencias disponibles a solicitud.", "age": "Edad"},
}
CHROMIUM_CANDIDATES = (
    "chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)
# Writing-style rules (references/writing-style.md). Matched case-insensitively on word boundaries.
CLICHES = ("passionate about", "i am passionate", "i believe i would be a great fit", "leverage my",
           "hit the ground running", "drive results", "synergy", "synergies", "team player", "go-getter",
           "think outside the box", "results-driven", "detail-oriented", "fast learner", "dynamic professional",
           "proven track record", "i would love to", "i am a perfect fit", "in today's fast-paced")
LETTER_OPEN = re.compile(r"^(dear|hi|hello|estimad[oa]s?|hola)\b", re.I)
LETTER_CLOSE = re.compile(r"^(kind regards|best regards|sincerely|regards|yours (truly|sincerely)|atentamente|"
                          r"saludos cordiales|saludos|cordialmente)\b", re.I)


class InputError(Exception):
    """Unusable input: reported on stderr, exit 2."""


# --- text helpers ----------------------------------------------------------------------------------------------------

def norm(text: str) -> str:
    """Lowercase, accent-free, punctuation-light: the ATS comparison alphabet."""
    flat = unicodedata.normalize("NFKD", str(text).lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9+#.]+", " ", flat).strip()


def ascii_dash(value) -> str:
    """Dates keep ASCII hyphens: ATS date import splits ranges on U+002D only. Spacing is kept."""
    return "".join("-" if ch in DASHES else ch for ch in str(value or "")).strip()


def has_em_dash(text: str) -> bool:
    """The style rule bans em dashes (and spaced en dashes or double hyphens used as one)."""
    return "\u2014" in text or " \u2013 " in text or " -- " in text


def strong_verb(text: str) -> bool:
    words = str(text).split()
    return bool(words) and words[0].lower().strip(".,:;") in STRONG_OWNERSHIP


def style_hits(text: str, avoid: list) -> list:
    """Cliches and profile avoid_phrases found in the text (phrases are literal, case-insensitive)."""
    low = " ".join(str(text).lower().split())
    hits = []
    for phrase in list(CLICHES) + [a.lower() for a in avoid if str(a).strip()]:
        if re.search(rf"(?<![a-z]){re.escape(phrase)}(?![a-z])", low):
            hits.append(phrase)
    return hits


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", str(text)))


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def headings_for(language: str) -> dict:
    return HEADINGS.get(language[:2].lower(), HEADINGS["en"])


def phrases_for(language: str) -> dict:
    return PHRASES.get(language[:2].lower(), PHRASES["en"])


# --- inputs ----------------------------------------------------------------------------------------------------------

def read_text(path: Path, label: str) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise InputError(f"cannot read {label} {path}: {exc}") from exc


def read_json_object(path: Path, label: str) -> dict:
    try:
        data = json.loads(read_text(path, label))
    except ValueError as exc:
        raise InputError(f"{label} {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise InputError(f"{label} {path}: top level must be an object")
    return data


def read_yaml_file(path: Path, label: str) -> dict:
    try:
        data = jc.load_yaml(read_text(path, label))
    except ValueError as exc:
        raise InputError(f"{label} {path} is not readable YAML: {exc}") from exc
    return data if isinstance(data, dict) else {}


class UnknownTemplate(InputError):
    """A template name that is neither a project template nor a shipped one: a usage error (exit 2)."""


def template_fingerprint(path: Path) -> str:
    """sha256 of the template HTML and its manifest: any edit after the gate changes it."""
    digest = hashlib.sha256(path.read_bytes())
    manifest = path.with_name(path.stem + ".json")
    if manifest.is_file():
        digest.update(b"\0manifest\0" + manifest.read_bytes())
    return digest.hexdigest()


def template_manifest(path: Path):
    """<name>.json beside a project template: kind (cv or letter) and page_limit (1 to 3). None when absent."""
    manifest = path.with_name(path.stem + ".json")
    if not manifest.is_file():
        return None
    data = read_json_object(manifest, "template manifest")
    if data.get("kind") not in (None, "cv", "letter"):
        raise InputError(f"template manifest {manifest.name}: kind must be cv or letter")
    limit = data.get("page_limit")
    if limit is not None and (isinstance(limit, bool) or limit not in (1, 2, 3)):
        raise InputError(f"template manifest {manifest.name}: page_limit must be 1, 2 or 3")
    return data


def check_gate(template: Path, kind: str) -> dict:
    """A project template renders only with a passing gate record for this kind, and only while its files still
    match the fingerprint the gate saw. Returns the record; its gates say whether the PDF check ran."""
    record_file = template.with_name(template.stem + GATE_SUFFIX)
    try:
        record = json.loads(record_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        record = None
    if not isinstance(record, dict) or record.get("verdict") != "pass":
        raise InputError(f"template {template.name} has not passed the ATS and layout gates: run "
                         f"template_check.py {template} --kind {kind} --register")
    if record.get("kind") != kind:
        raise InputError(f"template {template.name} passed the gates as {record.get('kind')}, not {kind}: run "
                         f"template_check.py {template} --kind {kind} --register")
    if record.get("fingerprint") != template_fingerprint(template):
        raise InputError(f"template {template.name} changed after it passed the gates: run "
                         f"template_check.py {template} --kind {kind} --register again")
    return record


def resolve_template(name: str, templates_dir, project, kind: str, gate: bool) -> tuple:
    """(path, source, manifest, gate record). Lookup: project templates (--templates-dir, else <P>/templates), then
    the shipped set. gate=False is for template_check.py's own smoke render; the CLI never passes it."""
    if not TEMPLATE_NAME.fullmatch(name or ""):
        raise UnknownTemplate(f"template name {name!r} is not valid: lowercase letters, digits and single hyphens")
    user_dir = templates_dir or (project / "templates" if project else None)
    if user_dir is not None and (user_dir / f"{name}.html").is_file():
        path = user_dir / f"{name}.html"
        manifest = template_manifest(path)
        declared = (manifest or {}).get("kind")
        if declared not in (None, kind):
            raise InputError(f"template {name} is a {declared} template: it cannot render as {kind}")
        record = check_gate(path, kind) if gate else None
        return path, "project", manifest, record
    if name in TEMPLATE_NAMES:
        return TEMPLATES_DIR / f"{name}.html", "shipped", None, None
    raise UnknownTemplate(f"unknown template {name!r}: shipped are {', '.join(TEMPLATE_NAMES)}; a project template "
                          "needs --project or --templates-dir and a passing gate record")


def load_profile(path: Path) -> dict:
    meta, _ = jc.split_front_matter(read_text(path, "profile"))
    return meta


def profile_facts(profile: dict) -> dict:
    cand = profile.get("candidate") if isinstance(profile.get("candidate"), dict) else {}
    market = profile.get("market") if isinstance(profile.get("market"), dict) else {}
    conventions = market.get("conventions") if isinstance(market.get("conventions"), dict) else {}
    age = cand.get("age")
    age_line = age if (cand.get("include_age_in_cv") is True and isinstance(age, int)
                       and not isinstance(age, bool)) else None
    limit = market.get("cv_page_limit")
    stage = str(cand.get("stage") or "").strip().lower() or None
    style = profile.get("writing_style") if isinstance(profile.get("writing_style"), dict) else {}  # noqa: E501
    avoid = [str(x) for x in (style.get("avoid_phrases") or []) if str(x).strip()]
    return {
        "avoid": avoid,
        "confidential": jc.confidential_terms(profile),
        "stage": stage,
        "age_line": age_line,
        "photo_requested": cand.get("photo_in_cv") is True,
        "country": str(market.get("country") or "").strip().upper() or None,
        "page_limit": limit if limit in (1, 2) and not isinstance(limit, bool) else None,
        "references_line": conventions.get("references_line") is True,
        "cv_template": str(profile.get("cv_template") or "").strip() or None,
        "target_roles": _list_of_text(profile.get("target_roles")),
        "key_skills": _list_of_text(profile.get("key_skills")),
        "profile_meta": profile,
    }


def _list_of_text(value) -> list:
    return [str(x).strip() for x in value if str(x).strip()] if isinstance(value, list) else []


def achievement_index(data: dict) -> tuple[dict, dict]:
    index = {}
    for item in data.get("achievements") or []:
        if isinstance(item, dict) and item.get("id"):
            index[str(item["id"]).strip()] = item
    langs = {}
    for lang in data.get("languages") or []:
        if isinstance(lang, dict) and lang.get("language"):
            langs[str(lang["language"]).strip().lower()] = lang
    return index, langs


def letter_citations(markdown: str) -> set:
    ids = set()
    for block in re.findall(r"<!--\s*achievements:(.*?)-->", markdown, re.S):
        ids.update(i for i in re.split(r"[\s,]+", block.strip()) if i)
    return ids


def parse_letter(markdown: str) -> dict:
    """Cover letter markdown -> salutation, body blocks (with citations), closing lines.

    Blocks are separated by blank lines. A block may end in <!-- achievements: ACH-... --> comments; the ids are kept
    on the block and the comment is removed from the text. Headings are skipped. A block whose lines all start with
    "- " is a list. The first block is the salutation when it opens with Dear/Hi/Estimado. The closing is the last
    block (or the one before a bare signature line) that opens with a closing phrase.
    """
    text = markdown.replace("\r\n", "\n")
    text = re.sub(r"\A\s*---\n.*?\n---\n", "", text, count=1, flags=re.S)
    blocks = []
    for raw in re.split(r"\n\s*\n", text):
        ids: list[str] = []
        flags = {"no_claim": False}

        def take(match) -> str:
            # "<!-- achievements: none -->" marks a motivation paragraph that asserts no fact about the candidate.
            found = [i for i in re.split(r"[\s,]+", match.group(1).strip()) if i]
            if [i.lower() for i in found] == ["none"]:
                flags["no_claim"] = True
            ids.extend(i for i in found if i.lower() != "none")
            return " "

        lines = []
        for ln in raw.split("\n"):
            ln = ln.strip()
            if not ln or ln.startswith("#"):
                continue
            ln = re.sub(r"<!--\s*achievements:(.*?)-->", take, ln).strip()
            if ln:
                lines.append(ln)
        if not lines:
            continue
        if all(ln.startswith("- ") for ln in lines):
            items = [ln[2:].strip() for ln in lines]
            blocks.append({"text": " ".join(items), "lines": lines, "items": items,
                           "achievements": ids, "no_claim": flags["no_claim"]})
        else:
            joined = re.sub(r"\s+", " ", " ".join(lines)).strip()
            blocks.append({"text": joined, "lines": lines, "items": None,
                           "achievements": ids, "no_claim": flags["no_claim"]})
    salutation = ""
    if blocks and LETTER_OPEN.match(blocks[0]["text"]):
        salutation = blocks.pop(0)["text"]
    closing_lines: list[str] = []
    if blocks and LETTER_CLOSE.match(blocks[-1]["text"]) and word_count(blocks[-1]["text"]) <= 8:
        closing_lines = blocks.pop()["lines"]
    elif len(blocks) >= 2 and LETTER_CLOSE.match(blocks[-2]["text"]) and word_count(blocks[-2]["text"]) <= 8 \
            and word_count(blocks[-1]["text"]) <= 4:
        # A closing phrase followed by a bare name line in its own block.
        tail = blocks[-2:]
        blocks = blocks[:-2]
        closing_lines = [ln for block in tail for ln in block["lines"]]
    return {"salutation": salutation, "paragraphs": blocks, "closing_lines": closing_lines}


# --- content normalisation -------------------------------------------------------------------------------------------

def _strs(values) -> list:
    return [str(v).strip() for v in (values or []) if str(v).strip()]


def normalise_cv(raw: dict, ach_langs: dict | None) -> dict:
    summary_raw = raw.get("summary")
    if isinstance(summary_raw, dict):
        summary_text, summary_ids = str(summary_raw.get("text") or "").strip(), _strs(summary_raw.get("achievements"))
    else:
        summary_text, summary_ids = str(summary_raw or "").strip(), []
    content = {
        "language": str(raw.get("language") or "en").strip(),
        "summary": summary_text,
        "summary_achievements": summary_ids,
        "career_gap": str(raw.get("career_gap") or "").strip(),
        "transferable_skills": _strs(raw.get("transferable_skills")),
        "experience": [],
        "projects": [],
        "skills": [],
        "education": [],
        "languages": [],
    }
    for job in raw.get("experience") or []:
        if not isinstance(job, dict):
            continue
        bullets = []
        for item in job.get("bullets") or []:
            bullet = {"text": item} if isinstance(item, str) else item
            if not isinstance(bullet, dict) or not str(bullet.get("text") or "").strip():
                continue
            entry = {"text": str(bullet["text"]).strip(), "achievements": _strs(bullet.get("achievements"))}
            if bullet.get("keep") is True:
                entry["keep"] = True
            if str(bullet.get("stretch") or "").strip():
                entry["stretch"] = str(bullet["stretch"]).strip()
            bullets.append(entry)
        content["experience"].append({"title": str(job.get("title") or "").strip(),
                                      "company": str(job.get("company") or "").strip(),
                                      "dates": str(job.get("dates") or "").strip(), "bullets": bullets})
    for proj in raw.get("projects") or []:
        if isinstance(proj, dict):
            content["projects"].append({"name": str(proj.get("name") or "").strip(),
                                        "url": str(proj.get("url") or "").strip(),
                                        "text": str(proj.get("text") or "").strip(),
                                        "achievements": _strs(proj.get("achievements"))})
    for skill in raw.get("skills") or []:
        if isinstance(skill, dict) and str(skill.get("name") or "").strip():
            content["skills"].append({"name": str(skill["name"]).strip(), "level": str(skill.get("level") or "").strip()})
    for edu in raw.get("education") or []:
        if isinstance(edu, dict):
            content["education"].append({"degree": str(edu.get("degree") or "").strip(),
                                         "institution": str(edu.get("institution") or "").strip(),
                                         "year": str(edu.get("year") or "").strip()})
    for lang in raw.get("languages") or []:
        if isinstance(lang, dict) and str(lang.get("language") or "").strip():
            content["languages"].append({"language": str(lang["language"]).strip(),
                                         "level": str(lang.get("level") or "").strip()})
    return content


def cv_header(raw: dict, contact: dict, facts: dict, language: str) -> dict:
    h = raw.get("header") if isinstance(raw.get("header"), dict) else {}

    def pick(key: str) -> str:
        return str(h.get(key) or contact.get(key) or "").strip()

    contact_parts = [x for x in (pick("email"), pick("phone"), pick("location")) if x]
    if facts["age_line"] is not None:
        contact_parts.append(f"{phrases_for(language)['age']} {facts['age_line']}")
    links = _strs(h.get("links") or contact.get("links"))
    return {"name": pick("name"), "headline": str(h.get("headline") or "").strip(),
            "contact": contact_parts, "links": links}


def contact_header(contact: dict) -> dict:
    parts = [str(contact.get(k) or "").strip() for k in ("email", "phone", "location")]
    return {"name": str(contact.get("name") or "").strip(), "headline": "",
            "contact": [p for p in parts if p], "links": _strs(contact.get("links"))}


# --- document model --------------------------------------------------------------------------------------------------

def section_order(stage: str | None) -> list:
    return STAGE_ORDER.get(stage or "", DEFAULT_ORDER)


def cv_order(stage: str | None) -> list:
    # the stage order, then any section the CV holds that the order does not name: a transferable block is never lost
    order = list(section_order(stage))
    return order + [key for key in DEFAULT_ORDER if key not in order]


def skill_label(skill: dict) -> str:
    return f"{skill['name']} ({skill['level']})" if skill.get("level") else skill["name"]


def cv_blocks(work: dict, ctx: dict) -> list:
    words = ctx["words"]

    def head(key: str) -> dict:
        return {"t": "h2", "text": words[key]}

    sec: dict = {}
    if work["summary"]:
        sec["summary"] = [head("summary"), {"t": "para", "text": work["summary"], "cls": ""}]
    if work["transferable_skills"]:
        sec["transferable"] = [head("transferable"), {"t": "ul", "items": work["transferable_skills"]}]
    exp = []
    if work["career_gap"]:
        exp.append({"t": "para", "text": work["career_gap"], "cls": "gap"})
    for job in work["experience"]:
        exp.append({"t": "job", "title": job["title"], "org": job["company"], "dates": ascii_dash(job["dates"]),
                    "bullets": [b["text"] for b in job["bullets"]]})
    if exp:
        sec["experience"] = [head("experience")] + exp
    if work["projects"]:
        sec["projects"] = [head("projects")] + [{"t": "project", "name": p["name"], "url": p["url"], "text": p["text"]}
                                                for p in work["projects"]]
    if work["skills"]:
        sec["skills"] = [head("skills"), {"t": "chips", "items": [skill_label(s) for s in work["skills"]]}]
    if work["education"]:
        sec["education"] = [head("education")] + [
            {"t": "edu", "degree": e["degree"], "institution": e["institution"], "year": ascii_dash(e["year"])}
            for e in work["education"]]
    if work["languages"]:
        sec["languages"] = [head("languages"), {"t": "chips", "items": [skill_label(
            {"name": x["language"], "level": x["level"]}) for x in work["languages"]]}]
    blocks: list = []
    for key in ctx["order"]:
        blocks += sec.get(key, [])
    if ctx["references_line"]:
        blocks.append({"t": "para", "text": phrases_for(ctx["language"])["references"], "cls": "refline"})
    return blocks


def letter_blocks(letter: dict) -> list:
    blocks = []
    if letter["salutation"]:
        blocks.append({"t": "para", "text": letter["salutation"], "cls": "salutation"})
    for para in letter["paragraphs"]:
        if para.get("items"):
            blocks.append({"t": "ul", "items": para["items"]})
        else:
            blocks.append({"t": "para", "text": para["text"], "cls": "body"})
    for i, line in enumerate(letter["closing_lines"]):
        blocks.append({"t": "para", "text": line, "cls": "closing" if i == 0 else "signature"})
    return blocks


def build_document(work: dict, ctx: dict) -> dict:
    blocks = cv_blocks(work, ctx) if ctx["kind"] == "cv" else letter_blocks(work)
    return {"kind": ctx["kind"], "language": ctx["language"], "header": ctx["header"], "blocks": blocks}


# --- renderers -------------------------------------------------------------------------------------------------------

def render_txt(doc: dict) -> str:
    h = doc["header"]
    if doc["kind"] == "letter":
        out = [x for x in (h["name"], " | ".join(h["contact"])) if x]
        if out:
            out.append("")
        for b in doc["blocks"]:
            if b["t"] == "ul":
                out += [f"- {x}" for x in b["items"]] + [""]
            else:
                out += [b["text"], ""]
        return "\n".join(out).strip() + "\n"
    out = [x for x in (h["name"], h["headline"], " | ".join(h["contact"]), " | ".join(h["links"])) if x]

    def gap() -> None:
        if out and out[-1] != "":
            out.append("")

    for b in doc["blocks"]:
        t = b["t"]
        if t == "h2":
            gap()
            out.append(b["text"].upper())
        elif t == "para":
            out.append(b["text"])
        elif t == "job":
            out.append(" | ".join(x for x in (b["title"], b["org"], b["dates"]) if x))
            out += [f"- {x}" for x in b["bullets"]]
        elif t == "project":
            out.append(" | ".join(x for x in (b["name"], b["url"]) if x))
            if b["text"]:
                out.append(b["text"])
        elif t == "edu":
            left = ", ".join(x for x in (b["degree"], b["institution"]) if x)
            out.append(" | ".join(x for x in (left, b["year"]) if x))
        elif t == "ul":
            out += [f"- {x}" for x in b["items"]]
        elif t == "chips":
            out.append(", ".join(b["items"]))
    return "\n".join(out).strip() + "\n"


def _link(url: str) -> str:
    if re.match(r"^https?://", url, re.I):
        return f'<a href="{esc(url)}">{esc(url)}</a>'
    return esc(url)


def html_body(doc: dict) -> str:
    h = doc["header"]
    out = ['<header class="top">', f'<h1 class="name">{esc(h["name"])}</h1>']
    if h["headline"]:
        out.append(f'<p class="headline">{esc(h["headline"])}</p>')
    if h["contact"]:
        out.append(f'<p class="contact">{esc(" | ".join(h["contact"]))}</p>')
    if h["links"]:
        out.append('<p class="links">' + " | ".join(_link(u) for u in h["links"]) + "</p>")
    out.append("</header>")
    if doc["kind"] == "letter":
        out.append('<div class="letter">')
    for b in doc["blocks"]:
        t = b["t"]
        if t == "h2":
            out.append(f'<h2>{esc(b["text"])}</h2>')
        elif t == "para":
            cls = f' class="{esc(b["cls"])}"' if b.get("cls") else ""
            out.append(f"<p{cls}>{esc(b['text'])}</p>")
        elif t == "job":
            head = esc(b["title"]) + (f' <span class="org">{esc(b["org"])}</span>' if b["org"] else "")
            out.append(f'<article class="job"><h3>{head}</h3>')
            if b["dates"]:
                out.append(f'<p class="dates">{esc(b["dates"])}</p>')
            if b["bullets"]:
                out.append("<ul>" + "".join(f"<li>{esc(x)}</li>" for x in b["bullets"]) + "</ul>")
            out.append("</article>")
        elif t == "project":
            out.append(f'<article class="project"><h3>{esc(b["name"])}</h3>')
            if b["url"]:
                out.append(f'<p class="url">{_link(b["url"])}</p>')
            if b["text"]:
                out.append(f"<p>{esc(b['text'])}</p>")
            out.append("</article>")
        elif t == "edu":
            detail = " | ".join(x for x in (b["institution"], b["year"]) if x)
            out.append(f'<article class="edu"><h3>{esc(b["degree"])}</h3>'
                       + (f"<p>{esc(detail)}</p>" if detail else "") + "</article>")
        elif t == "ul":
            out.append("<ul>" + "".join(f"<li>{esc(x)}</li>" for x in b["items"]) + "</ul>")
        elif t == "chips":
            out.append('<ul class="chips">' + "".join(f"<li>{esc(x)}</li>" for x in b["items"]) + "</ul>")
    if doc["kind"] == "letter":
        out.append("</div>")
    return "\n".join(out)


def render_html(doc: dict, template_text: str, page_size: str) -> str:
    h = doc["header"]
    title = " ".join(x for x in (h["name"], h["headline"]) if x) or ("CV" if doc["kind"] == "cv" else "Cover letter")
    values = {"LANG": esc(doc["language"][:2].lower() or "en"), "TITLE": esc(title), "PAGE_SIZE": page_size,
              "CONTENT": html_body(doc)}
    # One pass over the template: a value containing "{{...}}" is never expanded a second time.
    return re.sub(r"\{\{(LANG|TITLE|PAGE_SIZE|CONTENT)\}\}", lambda m: values[m.group(1)], template_text)


def render_docx(doc: dict, path: Path, warnings: list) -> str:
    # DOCX is optional: without python-docx the PDF and the text still stand, and the warning says so.
    if importlib.util.find_spec("docx") is None:
        warnings.append("docx_skipped: python-docx is not installed, so no DOCX was written "
                        "(pip install python-docx to add it)")
        return "none"
    try:
        from docx import Document  # imported late: --help must not need it
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"docx_skipped: python-docx failed to import ({exc}), so no DOCX was written"[:300])
        return "none"
    h = doc["header"]
    word_doc = Document()

    def heading(text: str) -> None:
        try:
            word_doc.add_heading(text, level=2)
        except Exception:  # noqa: BLE001 - a template without heading styles still gets the text
            word_doc.add_paragraph(text)

    word_doc.add_heading(h["name"] or ("CV" if doc["kind"] == "cv" else "Cover letter"), level=0)
    for line in (h["headline"], " | ".join(h["contact"]), " | ".join(h["links"])):
        if line:
            word_doc.add_paragraph(line)
    for b in doc["blocks"]:
        t = b["t"]
        if t == "h2":
            heading(b["text"])
        elif t == "para":
            word_doc.add_paragraph(b["text"])
        elif t == "job":
            word_doc.add_paragraph().add_run(" | ".join(x for x in (b["title"], b["org"], b["dates"]) if x)).bold = True
            for item in b["bullets"]:
                _bullet(word_doc, item)
        elif t == "project":
            word_doc.add_paragraph(" | ".join(x for x in (b["name"], b["url"]) if x))
            if b["text"]:
                word_doc.add_paragraph(b["text"])
        elif t == "edu":
            head = ", ".join(x for x in (b["degree"], b["institution"]) if x)
            word_doc.add_paragraph(" | ".join(x for x in (head, b["year"]) if x))
        elif t == "ul":
            for item in b["items"]:
                _bullet(word_doc, item)
        elif t == "chips":
            word_doc.add_paragraph(", ".join(b["items"]))
    word_doc.save(str(path))
    return "python-docx"


def _bullet(word_doc, text: str) -> None:
    try:
        word_doc.add_paragraph(text, style="List Bullet")
    except Exception:  # noqa: BLE001
        word_doc.add_paragraph(f"- {text}")


# --- PDF engines -----------------------------------------------------------------------------------------------------

def weasyprint_available() -> bool:
    return importlib.util.find_spec("weasyprint") is not None


def chromium_binary() -> str | None:
    for candidate in CHROMIUM_CANDIDATES:
        found = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if found:
            return found
    return None


def pdf_pages(path: Path) -> int | None:
    """Page count: pdfinfo, then pypdf, then a byte scan of /Type /Page objects (uncompressed Chromium output)."""
    if shutil.which("pdfinfo"):
        try:
            out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=30).stdout
            match = re.search(r"^Pages:\s+(\d+)", out, re.M)
            if match:
                return int(match.group(1))
        except (OSError, subprocess.SubprocessError):
            pass
    if importlib.util.find_spec("pypdf") is not None:
        try:
            from pypdf import PdfReader
            return len(PdfReader(str(path)).pages)
        except Exception:  # noqa: BLE001 - fall through to the byte scan
            pass
    try:
        found = len(re.findall(rb"/Type\s*/Page(?![a-zA-Z])", path.read_bytes()))
    except OSError:
        return None
    return found or None


def render_pdf(html_text: str, html_path: Path, pdf_path: Path, engine: str, defects: list) -> tuple[str, int | None]:
    """(engine used, page count). A missing engine is a defect, never a crash."""
    pdf_path.unlink(missing_ok=True)  # a stale PDF must never be shipped after a failed render
    if engine in ("auto", "weasyprint") and weasyprint_available():
        try:
            from weasyprint import HTML  # imported late
            rendered = HTML(filename=str(html_path)).render()
            rendered.write_pdf(str(pdf_path))
            return "weasyprint", len(rendered.pages)
        except Exception as exc:  # noqa: BLE001 - the report carries the reason
            defects.append({"code": "pdf_failed", "message": f"weasyprint: {type(exc).__name__}: {exc}"[:300]})
            return "none", None
    if engine == "weasyprint":
        defects.append({"code": "engine_missing",
                        "message": "weasyprint is not installed: pip install weasyprint"})
        return "none", None
    binary = chromium_binary()
    if binary:
        profile_dir = tempfile.mkdtemp(prefix="chrome-profile-")
        try:
            subprocess.run([binary, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-first-run",
                            "--no-pdf-header-footer", f"--user-data-dir={profile_dir}",
                            f"--print-to-pdf={pdf_path.resolve()}", html_path.resolve().as_uri()],
                           capture_output=True, text=True, timeout=180, check=True)
        except (OSError, subprocess.SubprocessError) as exc:
            defects.append({"code": "pdf_failed", "message": f"chromium: {exc}"[:300]})
            return "none", None
        finally:
            shutil.rmtree(profile_dir, ignore_errors=True)
        if not pdf_path.is_file():
            defects.append({"code": "pdf_failed", "message": "chromium ran but wrote no PDF"})
            return "none", None
        return "chromium", pdf_pages(pdf_path)
    defects.append({"code": "engine_missing",
                    "message": "no PDF engine: install weasyprint (pip) or Chromium/Chrome, then re-run"})
    return "none", None


def detect_engine(choice: str) -> str:
    if choice in ("auto", "weasyprint") and weasyprint_available():
        return "weasyprint"
    if choice != "weasyprint" and chromium_binary():
        return "chromium"
    return "none"


# --- page budget and relevance-weighted cutting ----------------------------------------------------------------------

def estimate_pages(doc: dict) -> int:
    """Rough line count for when no engine can measure the page. Used for reporting only, never for cutting."""
    lines = 4.0

    def wrap(text) -> int:
        text = str(text or "")
        return max(1, math.ceil(len(text) / CHARS_PER_LINE)) if text.strip() else 0

    for b in doc["blocks"]:
        t = b["t"]
        if t == "h2":
            lines += 2
        elif t == "para":
            lines += wrap(b["text"])
        elif t == "job":
            lines += 1.5 + sum(wrap(x) for x in b["bullets"])
        elif t == "project":
            lines += 1 + wrap(b.get("text"))
        elif t == "edu":
            lines += 1.5
        elif t == "ul":
            lines += sum(wrap(x) for x in b["items"])
        elif t == "chips":
            lines += wrap(", ".join(b["items"]))
    return max(1, math.ceil(lines / LINES_PER_PAGE))


def relevance_terms(analysis: dict) -> list:
    req = analysis.get("requirements") if isinstance(analysis.get("requirements"), dict) else {}
    seen, terms = set(), []
    for key in ("keywords", "tools"):
        for term in req.get(key) or []:
            text = str(term).strip()
            if text and norm(text) not in seen:
                seen.add(norm(text))
                terms.append(text)
    return terms


def bullet_score(text: str, cited: list, terms: list, cite_counts: Counter, letter_ids: set) -> float:
    """Relevance to this posting (0.5), uniqueness of the cited claims (0.3), narrative load (0.2). 0 to 1."""
    if terms:
        haystack = f" {norm(text)} "
        relevance = sum(1 for t in terms if f" {norm(t)} " in haystack) / len(terms)
    else:
        relevance = 0.5
    if not cited:
        uniqueness = 0.0
    elif all(cite_counts[c] == 1 for c in cited):
        uniqueness = 1.0
    else:
        uniqueness = 0.5
    narrative = 1.0 if letter_ids and set(cited) & letter_ids else 0.0
    return round(0.5 * relevance + 0.3 * uniqueness + 0.2 * narrative, 3)


def cut_candidate(work: dict, terms: list, letter_ids: set):
    """The bullet to remove next: lowest score, then the oldest job, then the last bullet. None when nothing may go."""
    counts = Counter(c for job in work["experience"] for b in job["bullets"] for c in b["achievements"])
    best = None
    for ji, job in enumerate(work["experience"]):
        if len(job["bullets"]) <= 1:
            continue  # every job keeps at least one bullet
        for bi, bullet in enumerate(job["bullets"]):
            if bullet.get("keep") is True:
                continue
            score = bullet_score(bullet["text"], bullet["achievements"], terms, counts, letter_ids)
            key = (score, -ji, -bi)
            if best is None or key < best[0]:
                best = (key, ji, bi, score)
    return best


# --- claim-to-source and privacy checks -----------------------------------------------------------------------------
# A CV or letter may name an employer, title, date, number, degree, skill or tool only when achievements.yaml
# (experiences, achievements, education, skills) or profile.md holds it. A check runs when its source list exists.
# A missing list, or an achievement without text, cannot be verified: that is a warning, not a pass and not a defect.

PROFICIENCY = ("led", "did", "participated", "familiar")
CURRENT = frozenset(("current", "present", "actual", "actualidad", "now", "hoy"))
MONTH_NAMES = frozenset(("january", "february", "march", "april", "may", "june", "july", "august", "september",
                         "october", "november", "december", "enero", "febrero", "marzo", "abril", "mayo", "junio",
                         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre", "januar", "februar",
                         "marz", "juni", "juli", "oktober", "dezember", "janeiro", "fevereiro", "maio", "junho",
                         "julho", "setembro", "outubro", "novembro", "dezembro"))
NUMBER_WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
                "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
                "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30,
                "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
                "thousand": 1000, "million": 1000000, "billion": 1000000000,
                "cero": 0, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6, "siete": 7,
                "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12, "quince": 15, "veinte": 20,
                "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80,
                "noventa": 90, "cien": 100, "ciento": 100, "mil": 1000, "millon": 1000000, "millones": 1000000}
# Technology names checked wherever they appear in a claim. The posting's own tools are added at run time.
TECH_TERMS = ("python", "sql", "power bi", "tableau", "looker", "dbt", "airflow", "spark", "apache spark", "kafka",
              "docker", "kubernetes", "terraform", "aws", "gcp", "azure", "snowflake", "bigquery", "redshift",
              "postgresql", "mysql", "mongodb", "pandas", "numpy", "scikit-learn", "tensorflow", "pytorch",
              "javascript", "typescript", "java", "git", "jira", "salesforce", "sap", "hubspot", "matlab", "stata",
              "spss", "figma", "langchain", "databricks", "google cloud", "hugging face", "keras", "qlik",
              "metabase", "superset", "github", "gitlab", "linux", "django", "flask", "fastapi", "node.js", "dask",
              "mlflow", "redis", "elasticsearch", "jenkins", "ansible", "hadoop")
# A CamelCase token (LangChain, PyTorch, GitHub) is a technology name even when the fixed list lacks it. Degree
# abbreviations and a platform name are not technologies.
CAMEL_TECH = re.compile(r"(?<![\w.])[A-Z][a-z]+[A-Z][A-Za-z]*(?![\w])")
CAMEL_EXEMPT = frozenset(("phd", "mba", "linkedin"))
CLAIM_NUMBER = re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?!\d)")
SOURCE_SKIP_KEYS = frozenset(("id", "experience", "proficiency", "verified", "source", "evidence", "achievements", "url"))
# Degree levels in EN, ES, PT and DE. A claim names a level; the education source must hold a degree of that level.
DEGREE_LEVELS = (
    ("doctorate", re.compile(r"(?<![a-z])(?:ph\.?\s?d\.?|doctor(?:ate|al|ado|ada)|doutor(?:ado|ada)?|doktor(?:grad|titel|arbeit)?)"
                             r"(?![a-z])", re.I)),
    ("master", re.compile(r"(?<![a-z])(?:master'?s?\s+(?:degree|in|of|studies|program)|master'?s|msc|m\.sc\.?|mba|"
                          r"maestr[ií]a|mestrado|mag[ií]ster|masterstudium|masterabschluss)(?![a-z])", re.I)),
    ("bachelor", re.compile(r"(?<![a-z])(?:bachelor'?s?|b\.?sc\.?|licenciad[oa]|licenciatura|diplomado|bacharel\w*|"
                            r"diplom-\w+)(?![a-z])", re.I)),
)
DEGREE_WORDS = re.compile("|".join(pattern.pattern for _, pattern in DEGREE_LEVELS), re.I)
# Number words that stand for a quantity, compared like digits: "a third" is 1/3, "doubled" is 2x. A hyphenated
# compound ("double-check", "half-time") is not a quantity.
SCALE_PHRASES = (
    (re.compile(r"(?<![a-z])(?:a|one|un|um)\s+(?:third|tercio|terço)(?![a-z-])", re.I), "1/3"),
    (re.compile(r"(?<![a-z])(?:half|mitad|metade)(?![a-z-])", re.I), "1/2"),
    (re.compile(r"(?<![a-z])(?:doubl(?:e|ed|es|ing)|twice|duplic\w*|dobr\w*|dos\s+veces|duas\s+vezes)(?![a-z-])", re.I),
     "2x"),
    (re.compile(r"(?<![a-z])(?:tripl(?:e|ed|es|ing)|triplic\w*|tres\s+veces)(?![a-z-])", re.I), "3x"),
)
# Ownership verbs. A claim with one is checked against the cited achievement's proficiency or text.
OWNERSHIP_VERB = re.compile(r"(?<![a-z])(?:led|leading|managed|managing|owned|owning|headed|heading|directed|oversaw)"
                            r"(?![a-z])", re.I)
# Seniority and leadership words a headline may use only when a matching title holds them.
RANK_WORDS = ("senior", "sr", "junior", "jr", "lead", "principal", "staff", "head", "chief", "director", "manager",
              "lider", "líder", "jefe", "jefa", "gerente")
# Role nouns (EN, ES, PT, DE). A headline's role nouns must be the title's: 'Data Scientist' is not 'Data Analyst'.
ROLE_NOUNS = ("analyst", "scientist", "engineer", "developer", "architect", "consultant", "specialist", "designer",
              "researcher", "administrator", "technician", "analista", "cientifico", "ingeniero", "desarrollador",
              "arquitecto", "consultor", "cientista", "engenheiro", "desenvolvedor", "arquiteto", "entwickler",
              "ingenieur", "wissenschaftler")
COMPANY_CLAIM = re.compile(r"(?<![A-Za-z])(?i:at|from)\s+((?:[A-Z][\w&.\-]*)(?:\s+(?:[A-Z][\w&.\-]*|&))*)")
PRIVATE_PATTERNS = (
    # age: "34 years old", "34 años," (a number of years closing a clause, not "4 años de experiencia")
    ("age", re.compile(r"\b\d{1,2}\s*(?:years?\s+old|yo\b|y/o|jahre\s+alt)|"
                       r"\b\d{1,2}\s*(?:a[ñn]os|anos)\s*(?:[,;)]|$)|"
                       r"\b(?:age|edad|idade|alter)\s*[:\-]?\s*\d{1,2}\b", re.I | re.M)),
    ("date of birth", re.compile(r"fecha\s+de\s+nacimiento|date\s+of\s+birth|\bDOB\b|data\s+de\s+nascimento|"
                                 r"geburtsdatum|geburtstag|\bborn\s+on\b|nacido\s+el", re.I)),
    ("marital status", re.compile(r"\b(?:married|divorced|widowed|casad[oa]|solter[oa]|divorciad[oa]|viud[oa]|"
                                  r"solteir[oa]|viúv[oa]|verheiratet|ledig|geschieden|verwitwet)\b|"
                                  r"\b(?:marital|civil)\s+status\b|\bestado\s+civil\b|\bfamilienstand\b", re.I)),
    ("photo", re.compile(r"\b(?:photo|foto|fotograf[ií]a|lichtbild|headshot)\s*:|!\[|<img\b", re.I)),
    ("nationality", re.compile(r"\b(?:nationality|nacionalidad|nacionalidade|nationalit[aä]t|citizenship|"
                               r"ciudadan[ií]a)\s*[:\-]", re.I)),
)


def num_norm(token) -> str:
    text = str(token).strip().rstrip(".")
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", text):
        text = text.replace(",", "")
    elif re.fullmatch(r"\d+,\d{1,2}", text):
        text = text.replace(",", ".")
    try:
        value = float(text)
    except ValueError:
        return text
    return str(int(value)) if value == int(value) else str(value)


QUANTITY_UNITS = frozenset((
    "years", "year", "months", "month", "weeks", "week", "days", "day", "hours", "hour", "minutes", "minute",
    "seconds", "people", "persons", "engineers", "analysts", "developers", "members", "team", "teams", "staff",
    "employees", "users", "customers", "clients", "reports", "dashboards", "pipelines", "models", "projects", "units",
    "countries", "languages", "percent", "times", "million", "thousand", "billion", "tables", "markets",
    "a\u00f1os", "meses", "semanas", "dias", "d\u00edas", "horas", "minutos", "personas", "ingenieros", "analistas",
    "empleados", "usuarios", "clientes", "proyectos", "equipo", "equipos", "idiomas", "reportes", "informes"))
NUMBER_WORD_CLAIM = re.compile(r"\b(" + "|".join(sorted(NUMBER_WORDS, key=len, reverse=True)) + r")\s+("
                               + "|".join(sorted(QUANTITY_UNITS, key=len, reverse=True)) + r")\b", re.I)


def claim_numbers(text) -> list:
    """Digits anywhere, and number words that name a quantity ('six hours', 'twenty engineers')."""
    found = [num_norm(m.group(0)) for m in CLAIM_NUMBER.finditer(str(text or ""))]
    found += [str(NUMBER_WORDS[m.group(1).lower()]) for m in NUMBER_WORD_CLAIM.finditer(str(text or ""))]
    return found


def source_numbers(text) -> set:
    found = set(claim_numbers(text))
    for word in re.findall(r"[^\W\d_]+", str(text or "").lower()):
        if word in NUMBER_WORDS:
            found.add(str(NUMBER_WORDS[word]))
    return found


def record_numbers(value, found: set) -> set:
    """Every number an achievement record holds: digits and number words in its text, and its metric values."""
    if value is None or isinstance(value, bool):
        return found
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) not in SOURCE_SKIP_KEYS:
                record_numbers(item, found)
    elif isinstance(value, list):
        for item in value:
            record_numbers(item, found)
    elif isinstance(value, (int, float)):
        found.add(num_norm(value))
    else:
        found |= source_numbers(value)
    return found


def record_has_text(rec: dict) -> bool:
    return any(str(rec.get(k) or "").strip() for k in ("en", "es", "text")) or isinstance(rec.get("metric"), dict)


def key_of(text) -> str:
    return norm(text).strip(" .") if text else ""


def span_tokens(text) -> list:
    return re.findall(r"\d{4}(?:-\d{1,2})?|current|present|actual|actualidad|now|hoy", ascii_dash(text).lower())


def same_point(a, b) -> bool:
    a, b = str(a or "").strip().lower(), str(b or "").strip().lower()
    if a in CURRENT or b in CURRENT:
        return a in CURRENT and b in CURRENT
    return bool(a) and bool(b) and (a.startswith(b) or b.startswith(a))


def first_year(text):
    found = re.search(r"\d{4}", str(text or ""))
    return found.group(0) if found else None


def education_matches(entry: dict, record: dict) -> bool:
    degree = str(entry.get("degree") or "").strip()
    degree_ok = bool(degree) and (key_of(degree) == key_of(record.get("degree"))
                                  or jc.word_in(degree, record.get("degree") or ""))
    institution = str(entry.get("institution") or "").strip()
    institution_ok = (not institution or key_of(institution) == key_of(record.get("institution"))
                      or jc.word_in(institution, record.get("institution") or ""))
    year_ok = not entry.get("year") or first_year(entry.get("year")) == first_year(record.get("year"))
    return degree_ok and institution_ok and year_ok


def _objects(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else None


def build_sources(ach: dict, profile_raw: str, analysis: dict, target_roles=(), key_skills=()) -> dict:
    """What a CV or letter may name: achievements.yaml and profile.md. The opening (analysis) feeds only the letter's
    company names and the tool terms the posting asks for; a posting never supplies a candidate fact.
    The tool terms are the fixed technology list, the posting's tools, and the skills and tags the achievements hold.
    target_roles (profile.md) is the other title source, next to the experience titles."""
    records = {}
    for rec in _objects(ach.get("achievements")) or []:
        cid = str(rec.get("id") or "").strip()
        if cid:
            records[cid] = rec
    all_numbers = source_numbers(profile_raw)
    for rec in records.values():
        all_numbers = record_numbers(rec, all_numbers)
    fact_text = profile_raw + "\n" + json.dumps(ach, ensure_ascii=False)
    req = analysis.get("requirements") if isinstance(analysis.get("requirements"), dict) else {}
    skills = _objects(ach.get("skills")) or []
    # The tool universe: the fixed technology list, the posting's tools, and the skills and tags the sources name.
    tags = [str(t).strip() for rec in records.values() if isinstance(rec.get("tags"), list) for t in rec["tags"]]
    tools = list(TECH_TERMS) + [str(t).strip() for t in (req.get("tools") or []) if str(t).strip()]
    tools += [str(s.get("name") or "").strip() for s in skills] + tags + list(key_skills or ())
    return {"experiences": _objects(ach.get("experiences")), "education": _objects(ach.get("education")),
            "skills": skills if ach.get("skills") is not None else None, "records": records,
            "has_text": any(record_has_text(r) for r in records.values()), "all_numbers": all_numbers,
            "fact_text": fact_text, "letter_text": fact_text + "\n" + json.dumps(analysis or {}, ensure_ascii=False),
            "tool_terms": list(dict.fromkeys(t.lower() for t in tools if t)),
            "target_roles": [str(r).strip() for r in target_roles or [] if str(r).strip()]}


def unknown_companies(text: str, corpus: str) -> list:
    """Names after 'at' or 'from' (an employer or a school) that no source holds."""
    names: list = []
    for match in COMPANY_CLAIM.finditer(text):
        tokens = [t.rstrip(".") for t in match.group(1).split() if t not in ("I", "A")]
        tokens = [t for t in tokens if t]
        if not tokens or tokens[0].lower() in MONTH_NAMES:
            continue
        name = " ".join(tokens)
        if not jc.word_in(name, corpus) and name not in names:
            names.append(name)
    return names


def scale_claims(text) -> dict:
    """Quantity words a claim uses ('a third', 'doubled', 'half'), as {token: the words written}. They are checked
    like digits: the token is the quantity, so 'doubled' and 'twice' are the same claim."""
    found: dict = {}
    for pattern, token in SCALE_PHRASES:
        for match in pattern.finditer(str(text or "")):
            found.setdefault(token, match.group(0))
    return found


def record_text(rec: dict) -> str:
    return " ".join(str(rec.get(k) or "") for k in ("en", "es", "text"))


def check_numbers(label: str, text: str, cited: list, src: dict, defects: list, warnings: list) -> None:
    """A number or quantity word in a cited claim must be one of the cited achievement. A record without text cannot be
    checked."""
    if not text or not cited:
        return
    allowed: set = set()
    allowed_scales: set = set()
    for cid in cited:
        rec = src["records"].get(cid)
        if rec is None:
            continue  # an unknown id is already an unverified_achievement defect
        if record_has_text(rec):
            allowed = record_numbers(rec, allowed)
            allowed_scales |= set(scale_claims(record_text(rec)))
        else:
            warnings.append(f"numbers in {label} not checked: {cid} has no text in achievements.yaml")
            return
    for token in sorted(set(claim_numbers(text)) - allowed):
        defects.append({"code": "unsupported_number",
                        "message": f"{label}: number {token} is not in the cited achievement(s) "
                                   f"{', '.join(cited)}: {text[:60]!r}"})
    for token, words in scale_claims(text).items():
        if token not in allowed_scales:
            defects.append({"code": "unsupported_number",
                            "message": f"{label}: the quantity {words!r} ({token}) is not in the cited achievement(s) "
                                       f"{', '.join(cited)}: {text[:60]!r}"})


def skill_held(name: str, src: dict) -> bool:
    """A skills-line entry is held when the sources name it, or each of its parts ("SQL (PostgreSQL, Azure SQL)") is
    held or a related member of a held tool's family (recorded as related_tool)."""
    if jc.word_in(name, src["fact_text"]):
        return True
    parts = [p.strip() for p in re.split(r"[(),/]|\band\b|\by\b", str(name or "")) if p.strip()]
    if not parts:
        return False
    for part in parts:
        if jc.word_in(part, src["fact_text"]):
            continue
        held = jc.related_held(part, src["fact_text"])
        if not held:
            return False
        src.setdefault("related", {})[part.lower()] = held
    return True


def check_tools(label: str, text: str, src: dict, defects: list) -> None:
    """A tool or technology named in a claim must appear in achievements.yaml or profile.md. Capitalised technology
    tokens outside the fixed list (CamelCase such as LangChain) are checked the same way."""
    names = list(src["tool_terms"])
    for token in dict.fromkeys(CAMEL_TECH.findall(str(text or ""))):
        if token.lower() not in CAMEL_EXEMPT and token.lower() not in names:
            names.append(token.lower())
    for term in names:
        if jc.word_in(term, text) and not jc.word_in(term, src["fact_text"]):
            held = jc.related_held(term, src["fact_text"])
            if held:  # same family as a held tool (PostgreSQL next to SQL): named on purpose, said in the report
                src.setdefault("related", {})[term] = held
                continue
            defects.append({"code": "unsupported_tool",
                            "message": f"{label} names {term!r}, which achievements.yaml and profile.md do not hold: "
                                       f"{text[:60]!r}"})


def check_ownership(label: str, text: str, cited: list, src: dict, defects: list) -> None:
    """An ownership verb ('led', 'managed', 'owned') needs a cited achievement that records it: proficiency led, or
    achievement text with the verb. A participated or did record does not carry ownership."""
    verbs = list(dict.fromkeys(v.lower() for v in OWNERSHIP_VERB.findall(str(text or ""))))
    if not verbs or not cited:
        return
    records = [src["records"][cid] for cid in cited if cid in src["records"]]
    if not records:
        return  # unknown ids are already defects
    for rec in records:
        if str(rec.get("proficiency") or "") == "led" or OWNERSHIP_VERB.search(record_text(rec)):
            return
    defects.append({"code": "unsupported_claim",
                    "message": f"{label} claims ownership ({', '.join(verbs)}) that no cited achievement "
                               f"({', '.join(cited)}) records as led: {str(text)[:60]!r}"})


def degree_levels_of(text) -> set:
    return {level for level, pattern in DEGREE_LEVELS if pattern.search(str(text or ""))}


SUBJECT_STOP = frozenset(("the", "a", "an", "de", "la", "el", "los", "las", "of", "my", "and", "at", "from", "with",
                          "who", "that", "which", "for", "do", "da", "des", "der", "die", "das", "im", "in", "en"))


DEGREE_SUBJECT = re.compile(r"\b(?:in|en|em|im)\s+([^\W\d_][\w'-]*)", re.I)


def degree_claims(text) -> list:
    """(level, words written, subject) for each degree a claim names. The subject is the field of study: the word
    after 'in' or 'en' in the same clause, when there is one."""
    claims = []
    raw = str(text or "")
    for level, pattern in DEGREE_LEVELS:
        for match in pattern.finditer(raw):
            clause = re.split(r"[,;|.()]", raw[match.end():], maxsplit=1)[0][:80]
            tail = DEGREE_SUBJECT.search(clause)
            subject = tail.group(1) if tail and tail.group(1).lower() not in SUBJECT_STOP else None
            claims.append((level, match.group(0), subject))
    return claims


def check_degree_claims(label: str, text: str, src: dict, code: str, defects: list) -> None:
    """A degree a claim names must be a degree of the same level in achievements.yaml education, with the field of
    study when the claim gives one. No education list means no degree can be checked: a defect."""
    claims = degree_claims(text)
    if not claims:
        return
    education = src["education"]
    for level, words, subject in claims:
        if education is None:
            defects.append({"code": code,
                            "message": f"{label} names the degree {words!r}, but achievements.yaml has no education "
                                       f"list, so it cannot be checked: {text[:60]!r}"})
            continue
        same_level = [r for r in education if level in degree_levels_of(r.get("degree"))]
        if not same_level:
            defects.append({"code": code,
                            "message": f"{label} names the {level} degree {words!r}, which achievements.yaml "
                                       f"education does not hold: {text[:60]!r}"})
        elif subject and not any(jc.word_in(subject, f"{r.get('degree') or ''} {r.get('institution') or ''}")
                                 for r in same_level):
            defects.append({"code": code,
                            "message": f"{label} names {words!r} in {subject!r}, which achievements.yaml education "
                                       f"does not hold: {text[:60]!r}"})


def check_headline(headline: str, src: dict, defects: list) -> None:
    """The headline must match an experience title or a target role. Its words must be the title's words or a subset
    of them, and a seniority word in it must be in that title. With no source title at all, the headline is refused."""
    if not headline.strip():
        return
    titles = [str(e.get("title") or "").strip() for e in src["experiences"] or []] + list(src["target_roles"])
    titles = [t for t in titles if t]
    if not titles:
        defects.append({"code": "title_mismatch",
                        "message": f"headline {headline[:60]!r} cannot be checked: achievements.yaml has no experiences "
                                   "and profile.md has no target_roles"})
        return
    head_words = set(norm(headline).split())
    head_ranks = {norm(w) for w in RANK_WORDS} & head_words
    head_roles = {norm(w) for w in ROLE_NOUNS} & head_words
    for title in titles:
        words = set(norm(title).split())
        if not words:
            continue
        ranks = {norm(w) for w in RANK_WORDS} & words
        roles = {norm(w) for w in ROLE_NOUNS} & words
        # The headline may drop a seniority word (less claimed) but never add one; its role nouns are the title's.
        if head_ranks <= ranks and (head_roles == roles if roles else words <= head_words):
            return
    defects.append({"code": "title_mismatch",
                    "message": f"headline {headline[:60]!r} matches no experience title or target role "
                               f"({'; '.join(titles)[:120]})"})


def check_job(job: dict, experiences: list, defects: list) -> None:
    name = key_of(job["company"])
    same_company = [e for e in experiences if name and key_of(e.get("company")) == name]
    if not same_company:
        defects.append({"code": "unknown_employer",
                        "message": f"employer {job['company']!r} is not in achievements.yaml experiences"})
        return
    match = next((e for e in same_company if key_of(job["title"]) == key_of(e.get("title"))), same_company[0])
    if key_of(job["title"]) != key_of(match.get("title")):
        defects.append({"code": "title_mismatch",
                        "message": f"title {job['title']!r} at {job['company']!r}: achievements.yaml says "
                                   f"{match.get('title')!r}"})
    tokens = span_tokens(job["dates"])
    end = match.get("to") or "current"
    if len(tokens) != 2 or not same_point(tokens[0], match.get("from")) or not same_point(tokens[1], end):
        defects.append({"code": "date_mismatch",
                        "message": f"dates {job['dates']!r} at {job['company']!r} do not match achievements.yaml "
                                   f"({match.get('from')} to {end})"})


def check_cv_facts(work: dict, headline: str, src, defects: list, warnings: list) -> None:
    if src is None:
        return  # no achievements file: the render already warns that claims were not checked
    for token in sorted(set(claim_numbers(headline)) - src["all_numbers"]):
        defects.append({"code": "unsupported_number",
                        "message": f"headline: number {token} is in no achievement or profile: {headline[:60]!r}"})
    check_numbers("summary", work["summary"], work["summary_achievements"], src, defects, warnings)
    for proj in work["projects"]:
        check_numbers(f"project {proj['name']!r}", proj["text"], proj["achievements"], src, defects, warnings)
    for job in work["experience"]:
        for bullet in job["bullets"]:
            check_numbers("bullet", bullet["text"], bullet["achievements"], src, defects, warnings)
    # Tools are checked against every source the file holds (text, skills, tags, profile), so no gap is a pass.
    texts = [("headline", headline), ("summary", work["summary"])]
    texts += [(f"project {p['name']!r}", p["text"]) for p in work["projects"]]
    texts += [("bullet", b["text"]) for job in work["experience"] for b in job["bullets"]]
    for label, text in texts:
        check_tools(label, text, src, defects)
    if src["experiences"] is None:
        for job in work["experience"]:
            defects.append({"code": "unknown_employer",
                            "message": f"employer {job['company']!r} and title {job['title']!r} cannot be checked: "
                                       "achievements.yaml has no experiences list"})
    else:
        for job in work["experience"]:
            check_job(job, src["experiences"], defects)
    check_headline(headline, src, defects)
    if src["education"] is None:
        # An education entry with no education list to check it against is refused, never passed or skipped.
        for entry in work["education"]:
            defects.append({"code": "unknown_education",
                            "message": f"{entry['degree']!r} at {entry['institution']!r} ({entry['year']}) cannot be "
                                       "checked: achievements.yaml has no education list"})
    else:
        for entry in work["education"]:
            if not any(education_matches(entry, rec) for rec in src["education"]):
                defects.append({"code": "unknown_education",
                                "message": f"{entry['degree']!r} at {entry['institution']!r} ({entry['year']}) is not "
                                           "in achievements.yaml education"})
    for proj in work["projects"]:
        check_degree_claims(f"project {proj['name']!r}", proj["text"], src, "unsupported_claim", defects)
        check_ownership(f"project {proj['name']!r}", proj["text"], proj["achievements"], src, defects)
    check_degree_claims("summary", work["summary"], src, "unsupported_claim", defects)
    check_ownership("summary", work["summary"], work["summary_achievements"], src, defects)
    for job in work["experience"]:
        for bullet in job["bullets"]:
            check_degree_claims("bullet", bullet["text"], src, "unsupported_claim", defects)
            check_ownership("bullet", bullet["text"], bullet["achievements"], src, defects)
    if src["skills"] is None:
        for skill in work["skills"]:
            defects.append({"code": "unknown_skill",
                            "message": f"skill or tool {skill['name']!r} cannot be checked: achievements.yaml has no "
                                       "skills list"})
    else:
        for skill in work["skills"]:
            if not skill_held(skill["name"], src):
                defects.append({"code": "unknown_skill",
                                "message": f"skill or tool {skill['name']!r} is in neither achievements.yaml nor "
                                           "profile.md"})
            if skill["level"] and skill["level"] not in PROFICIENCY:
                defects.append({"code": "unknown_skill_level",
                                "message": f"{skill['name']!r} shows level {skill['level']!r}; the record holds "
                                           f"{', '.join(PROFICIENCY)}"})


def check_letter_facts(letter: dict, src, defects: list, warnings: list) -> None:
    for para in letter["paragraphs"]:
        text = para["text"]
        if para.get("no_claim"):
            # <!-- achievements: none --> exempts a paragraph from citation only: it may not hold a fact
            reasons = []
            if claim_numbers(text) or scale_claims(text):
                reasons.append("a number")
            if DEGREE_WORDS.search(text):
                reasons.append("a degree")
            if src is not None and src["experiences"] is not None:
                names = unknown_companies(text, src["letter_text"])
                if names:
                    reasons.append("an employer or school (" + ", ".join(names) + ")")
            if reasons:
                defects.append({"code": "uncited_claim",
                                "message": "none is only for greeting and closing: the paragraph holds "
                                           f"{' and '.join(reasons)}: {text[:60]!r}"})
        if src is None:
            continue
        if not para.get("no_claim"):
            check_numbers("letter paragraph", text, para["achievements"], src, defects, warnings)
            check_degree_claims("letter paragraph", text, src, "unsupported_claim", defects)
            # A named employer or school is checked against the sources; a missing education or experiences list
            # leaves it unverifiable, so it is named here as a defect too.
            for name in unknown_companies(text, src["letter_text"]):
                defects.append({"code": "unsupported_claim",
                                "message": f"company or school {name!r} is in neither the profile, the "
                                           f"achievements nor the opening: {text[:60]!r}"})
        check_tools("letter paragraph", text, src, defects)


def privacy_defects(pairs: list, defects: list, confidential: list | None = None) -> None:
    """Age, date of birth, marital status, photo and nationality never appear in a CV or letter, in any market, and
    neither does a profile.md `confidential_terms` entry (a client, a brand, an internal project)."""
    for label, text in pairs:
        text = str(text or "")
        for term in jc.confidential_hits(text, confidential or []):
            defects.append({"code": "confidential_term",
                            "message": f"{term!r} in {label} is confidential (profile.md confidential_terms): describe "
                                       "it by sector and scope instead"})
        for kind, pattern in PRIVATE_PATTERNS:
            if text.strip() and pattern.search(text):
                defects.append({"code": "private_data",
                                "message": f"{kind} in {label}: {text[:50]!r}; personal data stays out of the "
                                           "documents"})


def cv_pairs(work: dict, header: dict) -> list:
    pairs = [("name", header["name"]), ("headline", header["headline"]), ("summary", work["summary"]),
             ("career gap", work["career_gap"])]
    pairs += [("transferable skills", x) for x in work["transferable_skills"]]
    for job in work["experience"]:
        pairs += [("job title", job["title"]), ("employer", job["company"])]
        pairs += [("bullet", b["text"]) for b in job["bullets"]]
    pairs += [("project", f"{p['name']} {p['text']}") for p in work["projects"]]
    pairs += [("skill", s["name"]) for s in work["skills"]]
    pairs += [("education", f"{e['degree']} {e['institution']} {e['year']}") for e in work["education"]]
    pairs += [("language", x["language"]) for x in work["languages"]]
    return pairs


def work_mode_defects(pairs: list, ach_data, defects: list) -> None:
    """"working remotely from <country>" says how the current job is done: only a current experience in
    achievements.yaml with work_mode: remote backs it. profile.md work_mode is the search preference (what the user
    wants), so a first draft built from it passed four reviews before one caught it."""
    if ach_data is None or "remote" in jc.current_work_modes(ach_data):
        return
    for where, text in pairs:
        for hit in jc.remote_now_claims(text):
            defects.append({"code": "work_mode_unbacked",
                            "message": f"{where} says {hit!r}, and no current experience in achievements.yaml "
                                       "records work_mode: remote (profile.md work_mode is the search preference): "
                                       "write where the user is based (\"based in <country>\")"})


def letter_pairs(letter: dict) -> list:
    pairs = [("salutation", letter["salutation"])] + [("closing", x) for x in letter["closing_lines"]]
    pairs += [("letter paragraph", para["text"]) for para in letter["paragraphs"]]
    return pairs


# --- checks ----------------------------------------------------------------------------------------------------------

def cite_check(label: str, text: str, cited: list, ach_index, defects: list) -> None:
    """Every claim cites achievement ids, and every cited id exists and is verified."""
    if not text:
        return
    if not cited:
        defects.append({"code": "uncited_claim", "message": f"{label} cites no achievement: {text[:60]!r}"})
    for cid in cited:
        if ach_index is None:
            continue
        record = ach_index.get(cid)
        if record is None:
            defects.append({"code": "unverified_achievement", "message": f"{cid} is not in achievements.yaml"})
        elif record.get("verified") is not True:
            defects.append({"code": "unverified_achievement",
                            "message": f"{cid} is not verified: the user has not confirmed this text"})


def check_cv(work: dict, ctx: dict, analysis: dict, ach_index, ach_langs, defects: list, warnings: list) -> list:
    stretch = []
    cite_check("summary", work["summary"], work["summary_achievements"], ach_index, defects)
    for proj in work["projects"]:
        cite_check(f"project {proj['name']!r}", proj["text"], proj["achievements"], ach_index, defects)
    for job in work["experience"]:
        label = f"{job['title']} at {job['company']}".strip()
        for bullet in job["bullets"]:
            text = bullet["text"]
            cited = bullet["achievements"]
            cite_check("bullet", text, cited, ach_index, defects)
            n = word_count(text)
            if not BULLET_WORDS[0] <= n <= BULLET_WORDS[1]:
                warnings.append(f"bullet has {n} words, the range is {BULLET_WORDS[0]} to {BULLET_WORDS[1]}: {text[:50]!r}")
            if has_em_dash(text):
                defects.append({"code": "style_em_dash", "message": f"em dash in bullet: {text[:50]!r}"})
            reason = bullet.get("stretch")
            if not reason and ach_index is not None and strong_verb(text):
                for cid in cited:
                    rec = ach_index.get(cid) or {}
                    if str(rec.get("proficiency") or "") in WEAK_PROFICIENCY:
                        reason = f"{cid} is recorded as {rec.get('proficiency')}"
                        break
            if reason:
                stretch.append({"job": label, "text": text, "reason": reason,
                                "question": f"stretch because {reason}: keep, soften or drop"})
    summary_words = word_count(work["summary"] or "")
    if summary_words > SUMMARY_WORDS_MAX:
        defects.append({"code": "too_long", "message": f"summary has {summary_words} words, the limit is "
                                                       f"{SUMMARY_WORDS_MAX}: who you are, what you do, for whom"})
    for i, job in enumerate(work["experience"]):
        cap = ROLE_BULLETS_MAX[0] if i == 0 else ROLE_BULLETS_MAX[1]
        if len(job["bullets"]) > cap:
            defects.append({"code": "too_long", "message": f"{len(job['bullets'])} bullets under {job['title']!r}, "
                                                           f"the limit is {cap}: keep the ones that match the posting"})
    for text in [work["summary"]] + [p["text"] for p in work["projects"]]:
        if text and has_em_dash(text):
            defects.append({"code": "style_em_dash", "message": f"em dash in text: {text[:50]!r}"})
        for hit in style_hits(text, ctx["avoid"]):
            defects.append({"code": "style_cliche", "message": f"cliche or avoided phrase {hit!r}: {text[:50]!r}"})
    for job in work["experience"]:
        for bullet in job["bullets"]:
            for hit in style_hits(bullet["text"], ctx["avoid"]):
                defects.append({"code": "style_cliche",
                                "message": f"cliche or avoided phrase {hit!r}: {bullet['text'][:50]!r}"})
    stage = ctx["stage_name"]
    if stage == "returning" and not work["career_gap"]:
        defects.append({"code": "stage_requirement",
                        "message": "returning stage: an honest career-gap line is required (career_gap)"})
    if stage == "career_change" and not work["transferable_skills"]:
        warnings.append("career_change stage: a transferable-skills summary is recommended (transferable_skills)")
    if stage and stage not in STAGES:
        warnings.append(f"unknown candidate.stage {stage!r}: default section order used")
    for lang in work["languages"]:
        if ach_langs is None:
            warnings.append("language levels not checked: pass --achievements")
            break
        declared = ach_langs.get(lang["language"].lower())
        if declared is None:
            defects.append({"code": "language_undeclared",
                            "message": f"{lang['language']} is not declared in achievements.yaml"})
            continue
        want, have = jc.cefr_index(lang["level"]), jc.cefr_index(declared.get("level"))
        if want is not None and have is not None and want > have:
            defects.append({"code": "language_level_raised",
                            "message": f"{lang['language']} shown as {lang['level']}, declared {declared.get('level')}"})
    return stretch


def check_keywords(text: str, terms: list, warnings: list) -> None:
    haystack = f" {norm(text)} "
    for term in terms:
        count = haystack.count(f" {norm(term)} ")
        if count > KEYWORD_REPEAT_MAX:
            warnings.append(f"keyword {term!r} appears {count} times: keep coverage without stuffing")


def check_letter(letter: dict, ach_index, defects: list, warnings: list, avoid: list) -> None:
    body_words = 0
    for para in letter["paragraphs"]:
        body_words += word_count(para["text"])
        if not para["achievements"] and not para.get("no_claim"):
            defects.append({"code": "uncited_claim",
                            "message": f"paragraph cites no achievement (or <!-- achievements: none -->): "
                                       f"{para['text'][:60]!r}"})
        for cid in para["achievements"]:
            if ach_index is None:
                continue
            record = ach_index.get(cid)
            if record is None or record.get("verified") is not True:
                defects.append({"code": "unverified_achievement", "message": f"{cid} is missing or not verified"})
        if has_em_dash(para["text"]):
            defects.append({"code": "style_em_dash", "message": f"em dash in letter: {para['text'][:50]!r}"})
        for hit in style_hits(para["text"], avoid):
            defects.append({"code": "style_cliche", "message": f"cliche or avoided phrase {hit!r}: {para['text'][:50]!r}"})
    if body_words > LETTER_WORDS_MAX:
        defects.append({"code": "too_long",
                        "message": f"letter body has {body_words} words, the limit is {LETTER_WORDS_MAX}"})
    if not letter["closing_lines"]:
        warnings.append("no closing line found (a closing phrase as the last block)")


# --- main ------------------------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="render_cv.py", description=(__doc__ or "").split("\n\n")[0],
        epilog="Exit 0 clean, 1 defects, 2 usage or input error.", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--content", required=True, type=Path,
                        help="cv_content.json (--kind cv) or cover_letter.md (--kind letter)")
    parser.add_argument("--output", required=True, type=Path, help="output directory (created if missing)")
    parser.add_argument("--kind", choices=("cv", "letter"), default="cv", help="cv (default) or cover letter")
    parser.add_argument("--template", default=None,
                        help="template name: a project template <P>/templates/<name>.html that passed template_check.py "
                             "(its gate record must match), else a shipped one: classic, compact, modern "
                             "(default: profile cv_template, else classic). A name that differs from profile "
                             "cv_template is refused unless --template-override-by-user is given")
    parser.add_argument("--template-override-by-user", action="store_true",
                        help="allow a --template that differs from profile cv_template: pass it only after the user "
                             "agreed to the change")
    parser.add_argument("--project", type=Path, help="project folder P; project templates are read from P/templates")
    parser.add_argument("--templates-dir", type=Path, help="project templates folder, instead of <P>/templates")
    parser.add_argument("--analysis", type=Path, help="analysis.json; adds keyword coverage and relevance scores")
    parser.add_argument("--profile", type=Path, help="profile.md; stage, age and photo flags, market and page limit")
    parser.add_argument("--achievements", type=Path, help="achievements.yaml; checks cited ids and language levels")
    parser.add_argument("--contact", type=Path, help="contact.yaml; fills the header (CV and letter)")
    parser.add_argument("--letter", type=Path, help="cover_letter.md; its citations raise narrative load when cutting")
    parser.add_argument("--language", help="document language (default: the content's language, else en)")
    parser.add_argument("--pages", type=int, help="exact expected PDF page count; a mismatch is a defect")
    parser.add_argument("--engine", choices=("auto", "weasyprint", "chromium"), default="auto",
                        help="PDF engine (default auto: weasyprint, then Chromium)")
    parser.add_argument("--no-fit", action="store_true", help="never cut bullets to meet the page budget")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    return parser


def run(args: argparse.Namespace, gate: bool = True) -> int:
    kind = args.kind
    profile = load_profile(args.profile) if args.profile else {}
    facts = profile_facts(profile)
    ach_index, ach_langs, ach_data = (None, None, None)
    if args.achievements:
        ach_data = read_yaml_file(args.achievements, "achievements")
        ach_index, ach_langs = achievement_index(ach_data)
    contact = read_yaml_file(args.contact, "contact") if args.contact else {}
    analysis = read_json_object(args.analysis, "analysis") if args.analysis else {}
    profile_raw = read_text(args.profile, "profile") if args.profile else ""
    # A headline may use any title of a role family the candidate is recognised in (role_families.json): companies
    # name the same work many ways. Experience entries keep their real titles (check_job).
    headline_roles = (jc.positioning_titles(facts["profile_meta"], profile_raw + "\n" + json.dumps(ach_data, ensure_ascii=False))
                      if ach_data is not None else facts["target_roles"])
    sources = (build_sources(ach_data, profile_raw, analysis, headline_roles, facts["key_skills"])
               if ach_data is not None else None)
    letter_ids = letter_citations(read_text(args.letter, "letter")) if args.letter else set()
    requested_template = args.template
    changed = bool(requested_template and facts["cv_template"] and requested_template != facts["cv_template"])
    if changed and not args.template_override_by_user:
        raise InputError(f"template {requested_template} differs from profile cv_template {facts['cv_template']}: "
                         "a template change needs the user's yes. Ask the user; after a yes, re-run with "
                         "--template-override-by-user")
    if args.template is None:
        args.template = facts["cv_template"] or "classic"
    template_path, template_source, template_meta, gate_record = resolve_template(
        args.template, args.templates_dir, args.project, kind, gate)
    template_text = read_text(template_path, "template")
    if "{{CONTENT}}" not in template_text:
        raise InputError(f"template {args.template} has no {{{{CONTENT}}}} slot")

    warnings: list[str] = []
    if changed:
        warnings.append(f"template {requested_template} differs from profile cv_template {facts['cv_template']}: "
                        "the user agreed to the change (--template-override-by-user)")
    gates = (gate_record or {}).get("gates") or {}
    if gate_record is not None and gates.get("pdf") != "pass":
        warnings.append(f"template {args.template}: the PDF gate was not run at registration ({gates.get('pdf')}): "
                        "its layout is not verified")
    if kind == "cv":
        raw_cv = read_json_object(args.content, "cv_content")
        work = normalise_cv(raw_cv, ach_langs)
        language = str(args.language or work["language"] or "en")
        header = cv_header(raw_cv, contact, facts, language)
    else:
        work = parse_letter(read_text(args.content, "cover letter"))
        language = str(args.language or "en")
        header = contact_header(contact) if contact else {"name": "", "headline": "", "contact": [], "links": []}
    if language[:2].lower() not in HEADINGS:
        warnings.append(f"no heading table for {language!r}: section headings fall back to English")
    if ach_index is None:
        warnings.append("achievement ids not checked: pass --achievements")
    if facts["photo_requested"]:
        warnings.append("photo_in_cv is set, but the ATS-safe templates carry no image: none rendered")

    template_limit = template_meta.get("page_limit") if template_meta else None
    if args.pages is not None:
        budget, budget_source = args.pages, "flag"
    elif kind == "letter":
        budget, budget_source = (template_limit or 1), ("template" if template_limit else "default")
    elif facts["page_limit"] or template_limit:
        # the tighter of the market limit (profile) and the limit the template was designed for
        budget, budget_source = min((v, s) for v, s in ((facts["page_limit"], "profile"),
                                                         (template_limit, "template")) if v)
    else:
        budget, budget_source = 2, "default"

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    prefix = "cv_ats" if kind == "cv" else "letter_ats"
    html_path, txt_path, pdf_path = out / f"{prefix}.html", out / f"{prefix}.txt", out / f"{prefix}.pdf"
    docx_path = out / ("cv.docx" if kind == "cv" else "letter.docx")
    page_size = "Letter" if facts["country"] in LETTER_PAPER_COUNTRIES else "A4"
    ctx = {"kind": kind, "language": language, "header": header, "words": headings_for(language),
           "order": cv_order(facts["stage"]) if kind == "cv" else [],
           "references_line": facts["references_line"], "stage_name": facts["stage"], "avoid": facts["avoid"]}
    terms = relevance_terms(analysis)

    def emit(current) -> dict:
        doc = build_document(current, ctx)
        html_text = render_html(doc, template_text, page_size)
        text = render_txt(doc)
        html_path.write_text(html_text, encoding="utf-8")
        txt_path.write_text(text, encoding="utf-8")
        scratch: list = []
        engine_used, pages = render_pdf(html_text, html_path, pdf_path, args.engine, scratch)
        return {"doc": doc, "text": text, "engine": engine_used, "pages": pages, "defects": scratch}

    # Cutting only starts from a measured page count over budget; the last emit always matches `work`.
    engine = detect_engine(args.engine)
    cuts: list = []
    result = emit(work)
    if kind == "cv" and not args.no_fit and engine != "none":
        for _ in range(MAX_CUTS):
            if result["pages"] is None or result["pages"] <= budget:
                break
            candidate = cut_candidate(work, terms, letter_ids)
            if candidate is None:
                break
            _, ji, bi, score = candidate
            removed = work["experience"][ji]["bullets"].pop(bi)
            cuts.append({"section": "experience", "job": f"{work['experience'][ji]['title']} at "
                         f"{work['experience'][ji]['company']}".strip(), "text": removed["text"], "score": score,
                         "rule": "lowest relevance-weighted score, removed while the measured CV was over budget"})
            result = emit(work)

    if cuts:
        warnings.append(f"{len(cuts)} bullet(s) cut to fit the page budget: tighten the wording instead, or ask the user")
    defects = list(result["defects"])
    pages = result["pages"]
    estimated = None
    if pages is None:
        estimated = estimate_pages(result["doc"])
        warnings.append(f"pages estimated (no PDF measurement here): about {estimated}; install an engine to measure")
    if args.pages is not None:
        if pages is not None and pages != args.pages:
            defects.append({"code": "pages_mismatch",
                            "message": f"{pages} pages rendered, {args.pages} expected: adjust the content or design"})
        elif pages is None:
            warnings.append("page count not measurable here (no PDF engine or pdfinfo): --pages not enforced")
    if pages is not None and pages > budget and args.pages is None:
        defects.append({"code": "page_budget_exceeded",
                        "message": f"{pages} pages rendered, budget {budget}: the page budget is a hard limit. "
                                   "Tighten the wording first (shorter bullets, fewer low-relevance lines); the "
                                   f"template {args.template} stays unless the user chooses another"})

    if kind == "cv":
        stretch = check_cv(work, ctx, analysis, ach_index, ach_langs, defects, warnings)
        check_keywords(result["text"], terms, warnings)
        check_cv_facts(work, ctx["header"]["headline"], sources, defects, warnings)
        privacy_defects(cv_pairs(work, ctx["header"]), defects, facts["confidential"])
        work_mode_defects(cv_pairs(work, ctx["header"]), ach_data, defects)
    else:
        stretch = []
        check_letter(work, ach_index, defects, warnings, facts["avoid"])
        check_letter_facts(work, sources, defects, warnings)
        privacy_defects(letter_pairs(work), defects, facts["confidential"])
        work_mode_defects(letter_pairs(work), ach_data, defects)

    docx_engine = render_docx(result["doc"], docx_path, warnings)
    files = [str(html_path), str(txt_path)]
    if result["engine"] != "none":
        files.append(str(pdf_path))
    if kind == "cv":
        for old in out.glob("CV_*.pdf"):
            old.unlink(missing_ok=True)  # a copy of an earlier render (or an earlier name) is never uploaded
        upload = jc.cv_upload_name(header.get("name") or "", str(contact.get("short_name") or ""))
        if upload and pdf_path.is_file():
            shutil.copyfile(pdf_path, out / upload)
            files.append(str(out / upload))
        elif pdf_path.is_file():
            warnings.append("no name on the CV: the upload copy CV_<Name>_<Surname>.pdf was not written")
    if docx_engine != "none":
        files.append(str(docx_path))

    for term, held in sorted((sources or {}).get("related", {}).items()) if sources else []:
        warnings.append(f"related_tool: {term!r} is named from the held {held!r} (same family, skill_families.json)")
    warnings = list(dict.fromkeys(warnings))
    coverage, missing = keyword_report(result["text"], analysis)
    keywords = [str(k) for k in ((analysis.get("requirements") or {}).get("keywords") or []) if str(k).strip()]
    shown = {b["text"] for b in result["doc"]["blocks"] if b["t"] == "h2"}
    order_names = [k for k in ctx["order"] if ctx["words"][k] in shown]
    report = {
        "kind": kind, "content": str(args.content), "output": str(out), "language": language,
        "template": args.template, "template_source": template_source,
        "template_gate": gates or None, "market": {"country": facts["country"], "paper": page_size},
        "stage": facts["stage"], "section_order": order_names,
        "files": files, "engines": {"pdf": result["engine"], "docx": docx_engine},
        "page_budget": budget, "page_budget_source": budget_source,
        "pages_expected": args.pages, "pages_actual": pages,
        "pages_estimated": estimated, "page_method": "measured" if pages is not None else "estimate",
        "cuts": cuts,
        "selectable_text": None if result["engine"] == "none" else True,
        "reading_order_ok": True,  # one document model, one linear block order for HTML, PDF and text
        "links": header["links"],
        "keyword_coverage": coverage, "missing_keywords": missing, "keywords_total": len(keywords),
        "stretch_flags": stretch,
        "defects": defects, "warnings": warnings,
    }
    write = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    report_name = "render_report.json" if args.kind == "cv" else "render_report_letter.json"
    (out / report_name).write_text(write, encoding="utf-8")
    if args.json:
        print(write, end="")
    else:
        print(f"rendered {len(files)} files into {out} (pdf: {result['engine']}, docx: {docx_engine})")
        for defect in defects:
            print(f"defect {defect['code']}: {defect['message']}")
        for warning in warnings:
            print(f"warning: {warning}")
        for cut in cuts:
            print(f"cut to fit budget: {cut['text'][:70]!r} (score {cut['score']})")
        for flag in stretch:
            print(f"stretch: {flag['question']} ({flag['text'][:60]!r})")
        if coverage is not None:
            print(f"keyword coverage {coverage:.1%}" + (f", missing: {', '.join(missing)}" if missing else ""))
    return 1 if defects else 0


def keyword_report(cv_text: str, analysis: dict) -> tuple[float | None, list]:
    keywords = [str(k) for k in ((analysis.get("requirements") or {}).get("keywords") or []) if str(k).strip()]
    if not keywords:
        return None, []
    haystack = norm(cv_text)
    missing = [k for k in keywords if norm(k) not in haystack]
    return round((len(keywords) - len(missing)) / len(keywords), 4), missing


def main(argv: list | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except UnknownTemplate as exc:
        parser.error(str(exc))  # exits 2
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
