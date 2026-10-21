#!/usr/bin/env python3
"""Gate a custom CV or letter template before render_cv.py may use it: static ATS and layout checks, then a render smoke.

Input:  a template HTML file. The renderer fills four placeholders once: {{LANG}}, {{TITLE}}, {{PAGE_SIZE}} and
        {{CONTENT}}. An optional manifest sits beside it as <name>.json: {"kind": "cv" | "letter", "page_limit": 1-3,
        "notes": "..."}.
Static checks (no browser): name, manifest, placeholders, no_tables, images, scripts, external_requests,
        local_references, multi_column, float_layout, absolute_position, generated_text, background_images,
        contact_text, body_font_size.
Render smoke: the template is filled with a fictional fixture through render_cv.py. When a PDF engine renders it,
        verify_pdf.py (text layer: name, email and phone as text; ASCII date ranges) and verify_layout.py (page
        geometry) run on the PDF. Without an engine the PDF gate is "skipped": reported, never a pass.
        --require-pdf turns a skip into a failure.
Register: --register writes <name>.gate.json beside the template when the verdict is pass, and removes it otherwise.
        render_cv.py uses a template outside the shipped set only with a passing record whose fingerprint still
        matches the template and its manifest.

Exit codes: 0 pass, 1 fail (every reason listed), 2 usage error. Stdlib only. No network.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
from html.parser import HTMLParser
from pathlib import Path

HERE = Path(__file__).resolve().parent
RENDER = HERE / "render_cv.py"
VERIFY_PDF = HERE / "verify_pdf.py"
VERIFY_LAYOUT = HERE / "verify_layout.py"

PLACEHOLDERS = ("LANG", "TITLE", "PAGE_SIZE", "CONTENT")
PLACEHOLDER_TEXT = "{{LANG}}, {{TITLE}}, {{PAGE_SIZE}} and {{CONTENT}}"
KINDS = ("cv", "letter")
PAGE_LIMITS = (1, 2, 3)
SHIPPED = ("classic", "compact", "modern")
MANIFEST_KEYS = ("kind", "page_limit", "notes")
NAME_MAX = 40
NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
BODY_TAGS = ("html", "body", "p", "li", "ul", "article")
# Small metadata lines (contact, dates, links, references) may be smaller than body text.
META_CLASSES = frozenset(("contact", "links", "dates", "url", "refline"))
MIN_BODY_PT = 9.0
MIN_META_PT = 7.0  # contact, dates, links and references lines: smaller than body, never unreadable
DEFAULT_PT = 12.0
VOID_TAGS = frozenset(("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param",
                       "source", "track", "wbr"))
IMAGE_TAGS = ("img", "svg", "picture", "canvas", "object", "embed", "iframe", "video", "audio")
TABLE_TAGS = ("table", "tr", "td", "th")
TABLE_DISPLAY = frozenset(("table", "inline-table", "table-cell", "table-row", "table-column", "table-row-group"))
RESOURCE_ATTRS = ("src", "srcset", "poster", "data", "action", "formaction")
ICON_CLASS = re.compile(r"(?:^|[\s_-])(?:icons?|glyphicon|material-icons|fa|fas|fab|far)(?!\w)"
                        r"|\b(?:fa|bi|ri|mdi)-[\w-]+", re.I)
BACKGROUND_PROPS = frozenset(("background", "background-image", "list-style", "list-style-image", "border-image",
                              "border-image-source", "mask", "mask-image", "-webkit-mask-image"))
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
CONTACT_SELECTOR = re.compile(r"\.(?:contact|links)(?![\w-])")
STATIC_CHECKS = ("name", "manifest", "placeholders", "no_tables", "images", "scripts", "external_requests",
                 "local_references", "multi_column", "float_layout", "absolute_position", "generated_text",
                 "background_images", "contact_text", "body_font_size")
IGNORED_RENDER_DEFECTS = frozenset(("engine_missing",))
RENDER_TIMEOUT_S = 240
TOOL_TIMEOUT_S = 120
FIXTURE_NAME = "Jordan Example"
FIXTURE_EMAIL = "jordan@example.com"
FIXTURE_PHONE = "+1 555 010 0100"

FIXTURE_PROFILE = """---
candidate:
  stage: mid
market:
  country: US
writing_style: {tone: direct, formality: medium}
---
# Jordan Example
"""

FIXTURE_ACHIEVEMENTS = """achievements:
  - {id: ACH-001, proficiency: did, verified: true}
  - {id: ACH-002, proficiency: built, verified: true}
  - {id: ACH-003, proficiency: did, verified: true}
languages:
  - {language: english, level: B2, verified: true}
experiences:
  - {id: EXP-001, title: "Data analyst", company: "Example Co", from: 2022-03, to: current}
  - {id: EXP-002, title: "Analyst", company: "Sample Works", from: 2019-01, to: 2022-02}
skills:
  - {name: SQL, proficiency: did, achievements: [ACH-001]}
  - {name: Python, proficiency: did, achievements: [ACH-001]}
  - {name: Power BI, proficiency: built, achievements: [ACH-002]}
education:
  - {id: EDU-001, degree: "Industrial Engineering", institution: "Example University", year: 2018, verified: true}
"""

FIXTURE_CONTACT = """name: "Jordan Example"
email: "jordan@example.com"
phone: "+1 555 010 0100"
location: "Springfield"
links: []
"""

FIXTURE_CV = {
    "language": "en",
    "header": {"name": FIXTURE_NAME, "headline": "Data analyst, reporting automation"},
    "summary": {"text": "Data analyst with four years of reporting automation for small finance teams.",
                "achievements": ["ACH-001"]},
    "experience": [
        {"title": "Data analyst", "company": "Example Co", "dates": "2022-03 - current", "bullets": [
            {"text": "Automated the weekly sales report with Python and SQL, cutting run time from six hours "
                     "to twenty minutes.", "achievements": ["ACH-001"]},
            {"text": "Built a Power BI dashboard that the finance team uses to close the monthly ledger without "
                     "manual extracts.", "achievements": ["ACH-002"]},
            {"text": "Documented the reporting pipeline so two colleagues could maintain it during leave "
                     "periods.", "achievements": ["ACH-003"]},
        ]},
        {"title": "Analyst", "company": "Sample Works", "dates": "2019-01 - 2022-02", "bullets": [
            {"text": "Maintained legacy reports for three business units and moved them to a shared folder.",
             "achievements": ["ACH-003"]},
        ]},
    ],
    "skills": [{"name": "SQL", "level": "did"}, {"name": "Python", "level": ""}],
    "education": [{"degree": "Industrial Engineering", "institution": "Example University", "year": "2018"}],
    "languages": [{"language": "english", "level": "B2"}],
}

FIXTURE_LETTER = """Dear Hiring Manager,

I analyse sales reporting for small teams, and I want to bring that work to your data group. <!-- achievements: none -->

At Example Co I automated the weekly sales report with Python and SQL, which cut run time from six hours to twenty minutes. <!-- achievements: ACH-001 -->

Kind regards,
Jordan Example
"""


class UsageError(Exception):
    """Unusable input: exit 2."""


# --- names, manifest, record, fingerprint ----------------------------------------------------------------------------

def is_valid_name(name: str) -> bool:
    return len(name) <= NAME_MAX and NAME_RE.fullmatch(name) is not None


def manifest_path(path: Path) -> Path:
    return path.with_name(path.stem + ".json")


def record_path(path: Path) -> Path:
    return path.with_name(path.stem + ".gate.json")


def fingerprint(path: Path) -> str:
    """sha256 of the template bytes and its manifest bytes: any edit after registration changes it."""
    digest = hashlib.sha256(Path(path).read_bytes())
    mp = manifest_path(path)
    if mp.is_file():
        digest.update(b"\0manifest\0" + mp.read_bytes())
    return digest.hexdigest()


def read_manifest(path: Path, kind, fail, warnings: list):
    """(manifest or None, effective kind or None). Raises UsageError only when no kind is known and the manifest is
    fine: a broken manifest is a failure of the manifest check, not a usage error."""
    mp = manifest_path(path)
    manifest = None
    broken = False
    if not mp.is_file():
        warnings.append(f"no manifest {mp.name}: the page budget comes from the profile or the default")
    else:
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            data = None
            broken = True
            fail("manifest", f"{mp.name} is not valid JSON: {exc}")
        if data is not None and not isinstance(data, dict):
            broken = True
            fail("manifest", f"{mp.name}: the top level must be a JSON object")
        elif isinstance(data, dict):
            manifest = data
            declared = data.get("kind")
            if declared is not None and declared not in KINDS:
                broken = True
                fail("manifest", f"{mp.name}: kind {declared!r} is not cv or letter")
            if declared in KINDS and kind is not None and declared != kind:
                broken = True
                fail("manifest", f"{mp.name} says kind {declared}, the check was run with kind {kind}")
            limit = data.get("page_limit")
            if limit is not None and (isinstance(limit, bool) or limit not in PAGE_LIMITS):
                broken = True
                fail("manifest", f"{mp.name}: page_limit {limit!r} must be 1, 2 or 3")
            unknown = sorted(set(data) - set(MANIFEST_KEYS))
            if unknown:
                warnings.append(f"{mp.name}: unknown keys ignored: {', '.join(unknown)}")
    declared = manifest.get("kind") if manifest else None
    effective = kind or (declared if declared in KINDS else None)
    if effective is None and not broken:
        raise UsageError("no kind: pass --kind cv|letter, or set \"kind\" in the manifest")
    return manifest, effective


# --- static checks ---------------------------------------------------------------------------------------------------

CONTACT_HINT = re.compile(r"(?<![a-z])(?:e-?mail|envelope|mail|phone|mobile|tel|contact|location|address|map|"
                          r"linkedin|github|website|portfolio|www|link|globe|whatsapp)", re.I)


def is_icon(tag: str, attrs: dict) -> bool:
    """An icon element: an <i>, or an element whose class names an icon font or icon set."""
    return tag not in IMAGE_TAGS and (tag == "i" or ICON_CLASS.search(attrs.get("class", "")) is not None)


def describe(tag: str, attrs: dict) -> str:
    cls = attrs.get("class", "").strip()
    href = attrs.get("href", "")[:40]
    return f"<{tag}" + (f' class="{cls}"' if cls else "") + (f' href="{href}"' if href else "") + ">"


class Scan(HTMLParser):
    """One pass over the template: elements, <style> text, inline styles, and contact icons with no text beside them.

    Each open element is a frame: tag, attributes, the text length inside it, and the description of a text-less
    contact icon it holds. A contact icon is one with a contact hint in its own or its parent's class, title, label
    or href. Text counts toward every open element, so an element holding only an icon has length 0.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list = []     # (tag, attrs)
        self.inline: list = []       # (selector, style text)
        self.css: list = []          # text of <style> elements
        self.icon_only: list = []    # descriptions of elements whose contact is only an icon
        self._open: list = []        # frames of elements still open
        self._raw = None             # "style" or "script" while inside one

    def handle_starttag(self, tag, attrs):
        self._start(tag, {k.lower(): (v or "") for k, v in attrs}, empty=False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, {k.lower(): (v or "") for k, v in attrs}, empty=True)

    def _start(self, tag, attrs, empty):
        self.elements.append((tag, attrs))
        if attrs.get("style"):
            self.inline.append((selector_of(tag, attrs), attrs["style"]))
        frame = {"tag": tag, "attrs": attrs, "text": 0, "icon": None}
        if empty or tag in VOID_TAGS:
            self._close(frame)
            return
        if tag in ("style", "script"):
            self._raw = tag
        self._open.append(frame)

    def handle_endtag(self, tag):
        if tag in ("style", "script") and self._raw == tag:
            self._raw = None
        for i in range(len(self._open) - 1, -1, -1):
            if self._open[i]["tag"] == tag:
                frame = self._open[i]
                del self._open[i:]
                self._close(frame)
                return

    def _close(self, frame) -> None:
        parent = self._open[-1] if self._open else None
        tag, attrs = frame["tag"], frame["attrs"]
        if is_icon(tag, attrs) and frame["text"] == 0:
            values = [attrs.get("class", ""), attrs.get("title", ""), attrs.get("aria-label", "")]
            if parent is not None:
                values += [parent["attrs"].get("class", ""), parent["attrs"].get("href", "")]
            if any(CONTACT_HINT.search(v) for v in values if v):
                if parent is None:
                    self.icon_only.append(describe(tag, attrs))
                elif parent["icon"] is None:
                    parent["icon"] = describe(tag, attrs)
            return
        if frame["text"] == 0 and frame["icon"] is not None:
            self.icon_only.append(f"{describe(tag, attrs)} holds only the icon {frame['icon']}")

    def handle_data(self, data):
        if self._raw == "style":
            self.css.append(data)
            return
        if self._raw == "script":
            return
        stripped = len(data.strip())
        for frame in self._open:
            frame["text"] += stripped


def selector_of(tag: str, attrs: dict) -> str:
    return tag + "".join("." + c for c in attrs.get("class", "").split())


def parse_decls(block: str) -> list:
    decls = []
    for part in block.split(";"):
        if ":" in part:
            prop, _, value = part.partition(":")
            decls.append((prop.strip().lower(), " ".join(value.split())))
    return decls


def parse_rules(css: str) -> list:
    """(selector, declarations) for every innermost block; at-rule heads such as @media are not selectors."""
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    return [(" ".join(m.group(1).split()), parse_decls(m.group(2)))
            for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", css)]


def split_top(value: str) -> list:
    parts, depth, cur = [], 0, ""
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch.isspace() and depth == 0:
            if cur:
                parts.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        parts.append(cur)
    return parts


def track_count(value: str) -> int:
    count = 0
    for token in split_top(value):
        low = token.lower()
        if low == "none":
            continue
        if low.startswith("repeat("):
            match = re.match(r"repeat\(\s*(\d+)\s*,", low)
            count += int(match.group(1)) if match else 2  # auto-fill and auto-fit: more than one track
        else:
            count += 1
    return count


def first_row_columns(value: str) -> int:
    """Columns in the first row of grid-template-areas: the quoted strings, each a row of cell names."""
    rows = re.findall(r'"([^"]*)"', value)
    return len(rows[0].split()) if rows else 0


def to_pt(value: str, base: float):
    match = re.fullmatch(r"(\d*\.?\d+)\s*(pt|px|em|rem|%)?", value.strip(), re.I)
    if not match:
        return None  # keywords such as small or larger
    number, unit = float(match.group(1)), (match.group(2) or "px").lower()
    if unit == "pt":
        return number
    if unit == "px":
        return number * 0.75
    if unit == "%":
        return number * base / 100
    return number * base  # em and rem


def hides(prop: str, value: str) -> bool:
    if prop == "display":
        return value == "none"
    if prop == "visibility":
        return value == "hidden"
    if prop == "opacity":
        return value == "0"
    if prop == "color":
        return value == "transparent"
    if prop == "font-size":
        return re.fullmatch(r"0+(\.0+)?(px|pt|em|rem|%)?", value) is not None
    if prop == "text-indent":
        return re.match(r"-\d{3,}", value) is not None
    if prop in ("clip", "clip-path"):
        return value not in ("none", "auto")
    return False


def classify_ref(ref: str):
    if not ref or ref.startswith("#") or ref.lower().startswith(("data:", "mailto:", "tel:")):
        return None
    if re.match(r"(?i)(?:https?:|//)", ref):
        return "external"
    return "local"


def check_placeholders(text: str, fail) -> None:
    allowed = {"{{" + name + "}}" for name in PLACEHOLDERS}
    for token in sorted({t for t in re.findall(r"\{\{.*?\}\}", text, re.S) if t not in allowed}):
        fail("placeholders", f"unknown placeholder {token}: the renderer fills only {PLACEHOLDER_TEXT}, "
                             "spelled exactly")
    for name in PLACEHOLDERS:
        if "{{" + name + "}}" not in text:
            fail("placeholders", f"missing {{{{{name}}}}}: the renderer fills it once; without it the document "
                                 "loses its language, title, paper size or content")
    count = text.count("{{CONTENT}}")
    if count > 1:
        fail("placeholders", f"{{{{CONTENT}}}} appears {count} times: the CV would print {count} times")


def check_structure(scan: Scan, fail) -> None:
    tags = {tag for tag, _ in scan.elements}
    tables = [t for t in TABLE_TAGS if t in tags]
    if tables:
        fail("no_tables", "table markup (" + ", ".join(f"<{t}>" for t in tables) + "): the ATS reads cells across "
             "rows, so the reading order breaks; use headings and paragraphs")
    for tag in IMAGE_TAGS:
        if tag in tags:
            fail("images", f"<{tag}> element: text inside a graphic or an embedded frame is invisible to the ATS; "
                           "write the text as text")
    if "script" in tags:
        fail("scripts", "<script> element: code runs in the reader's browser; the template must be static HTML")
    handlers = sorted({f"{k} on <{tag}>" for tag, attrs in scan.elements for k, v in attrs.items()
                       if k.startswith("on") or v.strip().lower().startswith("javascript:")})
    for item in handlers:
        fail("scripts", f"script attribute {item}: the template must be static HTML")
    for desc in scan.icon_only:
        fail("contact_text", f"contact only as icons: {desc} has no text; write each email, phone and link as text")


def check_references(scan: Scan, raw_css: str, fail) -> None:
    refs = []
    for tag, attrs in scan.elements:
        for name in RESOURCE_ATTRS + (("href",) if tag in ("link", "base") else ()):
            if name in attrs:
                value = attrs[name].strip()
                refs.append(value.split()[0] if value else "")
    refs += [m.group(2) for m in re.finditer(r"url\(\s*(['\"]?)(.*?)\1\s*\)", raw_css, re.I | re.S)]
    refs += [m.group(2) for m in re.finditer(r"@import\s+(?:url\(\s*)?(['\"]?)([^'\")\s;]+)", raw_css, re.I)]
    for ref in sorted({r for r in refs if r}):
        kind = classify_ref(ref)
        if kind == "external":
            fail("external_requests", f"external request to {ref[:80]}: the file loads over the network when the "
                                      "CV renders; the template must work offline and private: embed it as a "
                                      "data: URL or use a font installed on the system")
        elif kind == "local":
            fail("local_references", f"local file {ref[:80]}: the renderer writes the HTML into the output folder, "
                                     "which does not hold this file; embed it as a data: URL")


def check_layout(rules: list, fail) -> None:
    for selector, decls in rules:
        flex_column = any(p in ("flex-direction", "flex-flow") and "column" in v.lower() for p, v in decls)
        for prop, value in decls:
            v = value.lower().strip()
            if prop == "display" and v in ("flex", "inline-flex") and not flex_column:
                fail("multi_column", f"row flex container (display: {value} in {selector}): two columns scramble "
                                     "ATS reading order; stack the blocks in one column")
            elif prop == "display" and v in TABLE_DISPLAY:
                fail("no_tables", f"table layout by CSS (display: {value} in {selector}): the ATS reads cells "
                                  "across rows")
            elif prop == "grid-template-areas" and first_row_columns(value) > 1:
                fail("multi_column", f"grid areas with {first_row_columns(value)} columns (grid-template-areas: "
                                     f"{value} in {selector}): two columns scramble ATS reading order")
            elif prop == "grid-template-columns" and track_count(value) > 1:
                fail("multi_column", f"grid with {track_count(value)} columns (grid-template-columns: {value} in "
                                     f"{selector}): two columns scramble ATS reading order")
            elif prop in ("grid-template", "grid") and "/" in value and track_count(value.split("/", 1)[1]) > 1:
                fail("multi_column", f"grid with several columns ({prop}: {value} in {selector}): two columns "
                                     "scramble ATS reading order")
            elif prop in ("column-count", "-webkit-column-count", "-moz-column-count") and v not in ("auto", "1"):
                fail("multi_column", f"multi-column text (column-count: {value} in {selector}): two columns "
                                     "scramble ATS reading order")
            elif prop in ("column-width", "-webkit-column-width", "columns", "-webkit-columns") \
                    and v not in ("auto", "none", "normal", "1"):
                fail("multi_column", f"multi-column text ({prop}: {value} in {selector}): two columns scramble "
                                     "ATS reading order")
            elif prop == "float" and v in ("left", "right", "inline-start", "inline-end"):
                fail("float_layout", f"float: {value} in {selector}: content beside other content: two columns "
                                     "scramble ATS reading order")
            elif prop == "position" and v in ("absolute", "fixed"):
                fail("absolute_position", f"position: {value} in {selector} moves text out of reading order")
            elif prop == "content" and v not in ('""', "''", "none", "normal"):
                fail("generated_text", f"content: {value} in {selector}: generated text is not in the document "
                                       "the ATS reads")
            elif prop in BACKGROUND_PROPS and "url(" in v:
                fail("background_images", f"background image in {selector} ({prop}): text in a background graphic "
                                          "is not read by the ATS")


def check_contact(rules: list, fail) -> None:
    for selector, decls in rules:
        if CONTACT_SELECTOR.search(selector):
            for prop, value in decls:
                if hides(prop, value.lower().strip()):
                    fail("contact_text", f"{prop}: {value} hides the contact line ({selector}): the email and "
                                         "phone must be readable text")


def is_body_selector(selector: str) -> bool:
    """True when some comma-separated part targets body text: its last compound is a body tag, not a metadata line."""
    for part in selector.split(","):
        compound = part.strip().lower().split()[-1:] or [""]
        tag = re.match(r"[a-z0-9]*", compound[0]).group(0)
        classes = set(re.findall(r"\.([\w-]+)", compound[0]))
        if tag in BODY_TAGS and not classes & META_CLASSES:
            return True
    return False


def check_body_font(rules: list, fail) -> None:
    base = DEFAULT_PT
    for selector, decls in rules:
        if any(part.strip().lower() == "html" for part in selector.split(",")):
            for prop, value in decls:
                pt = to_pt(value, DEFAULT_PT) if prop == "font-size" else None
                if pt is not None:
                    base = pt
    reported = set()
    for selector, decls in rules:
        body = is_body_selector(selector)
        meta = any(CONTACT_SELECTOR.search(part) or re.search(r"\.(dates|url|refline)(?![\w-])", part)
                   for part in selector.split(","))
        if not body and not meta:
            continue
        floor = MIN_BODY_PT if body else MIN_META_PT
        for prop, value in decls:
            pt = to_pt(value, base) if prop == "font-size" else None
            if pt is not None and pt < floor and selector not in reported:
                reported.add(selector)
                fail("body_font_size", f"{'body' if body else 'metadata'} text at {pt:.1f}pt in {selector}: under "
                                       f"{floor:g}pt; use {floor:g}pt or more")


def check_static(path: Path, kind=None) -> dict:
    """The static gate. Returns failures, warnings, the effective kind, the manifest and the fingerprint."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    failures: list = []
    warnings: list = []

    def fail(check: str, message: str) -> None:
        failures.append({"check": check, "message": message})

    if not is_valid_name(path.stem):
        fail("name", f"template name {path.stem!r}: use lowercase letters, digits and single hyphens, up to "
                     f"{NAME_MAX} characters (for example modern-serif)")
    elif path.stem in SHIPPED:
        warnings.append(f"name {path.stem!r} shadows the shipped template of the same name in this project")
    manifest, effective = read_manifest(path, kind, fail, warnings)
    scan = Scan()
    scan.feed(text)
    scan.close()
    raw_css = "\n".join(scan.css + [style for _, style in scan.inline])
    rules = parse_rules("\n".join(scan.css)) + [(sel, parse_decls(style)) for sel, style in scan.inline]
    check_placeholders(text, fail)
    for address in sorted(set(EMAIL_RE.findall(text))):
        warnings.append(f"email address {address} is written into the template: personal details belong in "
                        "contact.yaml; a template is shared and must hold placeholders only")
    check_structure(scan, fail)
    check_references(scan, raw_css, fail)
    check_layout(rules, fail)
    check_contact(rules, fail)
    check_body_font(rules, fail)
    return {"failures": failures, "warnings": warnings, "kind": effective, "manifest": manifest,
            "fingerprint": fingerprint(path)}


# --- render smoke ----------------------------------------------------------------------------------------------------

def item(check: str, message: str) -> dict:
    return {"check": check, "message": message}


def write_fixture(work: Path, kind: str, template: Path) -> dict:
    tdir = work / "templates"
    tdir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, tdir / "candidate.html")
    mp = manifest_path(template)
    if mp.is_file():
        shutil.copyfile(mp, tdir / "candidate.json")
    inputs = work / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    (inputs / "profile.md").write_text(FIXTURE_PROFILE, encoding="utf-8")
    (inputs / "achievements.yaml").write_text(FIXTURE_ACHIEVEMENTS, encoding="utf-8")
    (inputs / "contact.yaml").write_text(FIXTURE_CONTACT, encoding="utf-8")
    if kind == "cv":
        content = inputs / "cv_content.json"
        content.write_text(json.dumps(FIXTURE_CV, indent=1, ensure_ascii=False), encoding="utf-8")
    else:
        content = inputs / "cover_letter.md"
        content.write_text(FIXTURE_LETTER, encoding="utf-8")
    return {"templates": tdir, "content": content, "profile": inputs / "profile.md",
            "achievements": inputs / "achievements.yaml", "contact": inputs / "contact.yaml"}


def verifier_outcome(proc, check: str, failures: list):
    """(status, reason) for a verifier run: pass, fail (messages collected), skipped (reason) or a usage fault."""
    if proc.returncode == 0:
        return "pass", None
    if proc.returncode == 1:
        found = 0
        for line in proc.stdout.splitlines() + proc.stderr.splitlines():
            if line.startswith("fail: "):
                failures.append(item(check, line[len("fail: "):]))
                found += 1
            elif line.startswith("  - "):
                failures.append(item(check, line.strip()[2:]))
                found += 1
        if not found:
            failures.append(item(check, "the check failed without a message"))
        return "fail", None
    for line in proc.stderr.splitlines():
        if line.startswith("skipped: "):
            return "skipped", line[len("skipped: "):]
    last = (proc.stderr.strip().splitlines() or ["no output"])[-1]
    script = next(str(a) for a in proc.args if str(a).endswith(".py"))
    failures.append(item(check, f"{Path(script).name} usage error (exit {proc.returncode}): {last}"))
    return "fail", None


_RENDER_MODULE = None


def render_module():
    """render_cv.py loaded once, in-process: the smoke render goes through the same code as the real render."""
    global _RENDER_MODULE
    if _RENDER_MODULE is None:
        spec = importlib.util.spec_from_file_location("render_cv_gate", RENDER)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module  # dataclasses and the late imports look the module up by name
        spec.loader.exec_module(module)
        _RENDER_MODULE = module
    return _RENDER_MODULE


def run_smoke(path: Path, kind: str, engine: str, keep) -> dict:
    work = Path(keep) if keep else Path(tempfile.mkdtemp(prefix="template-check-"))
    work.mkdir(parents=True, exist_ok=True)
    try:
        return _smoke(work, path, kind, engine)
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)


def _smoke(work: Path, path: Path, kind: str, engine: str) -> dict:
    failures: list = []
    info = {"render": "fail", "pdf": "not run", "pdf_reason": None, "pdf_engine": None, "pages": None,
            "page_budget": None}
    fx = write_fixture(work, kind, path)
    out = work / "out"
    render = render_module()
    argv = ["--kind", kind, "--content", str(fx["content"]), "--output", str(out), "--profile", str(fx["profile"]),
            "--achievements", str(fx["achievements"]), "--contact", str(fx["contact"]),
            "--templates-dir", str(fx["templates"]), "--template", "candidate", "--engine", engine, "--json"]
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            render.run(render.build_parser().parse_args(argv), gate=False)
    except render.InputError as exc:
        failures.append(item("render_smoke", f"render_cv refused the template: {exc}"))
        return {"failures": failures, "warnings": [], "info": info}
    except Exception as exc:  # noqa: BLE001 - a crash in the renderer is a failed gate, with its reason
        failures.append(item("render_smoke", f"render_cv crashed: {type(exc).__name__}: {exc}"[:300]))
        return {"failures": failures, "warnings": [], "info": info}
    report_file = out / ("render_report.json" if kind == "cv" else "render_report_letter.json")
    if not report_file.is_file():
        failures.append(item("render_smoke", f"render_cv wrote no {report_file.name}"))
        return {"failures": failures, "warnings": [], "info": info}
    report = json.loads(report_file.read_text(encoding="utf-8"))
    for defect in report.get("defects", []):
        if defect.get("code") not in IGNORED_RENDER_DEFECTS:
            failures.append(item("render_smoke", f"render_cv reports {defect.get('code')}: "
                                                 f"{defect.get('message')}"))
    info["render"] = "fail" if failures else "pass"
    info["pdf_engine"] = (report.get("engines") or {}).get("pdf", "none")
    info["pages"] = report.get("pages_actual")
    info["page_budget"] = report.get("page_budget")
    if info["pdf_engine"] == "none":
        info["pdf"] = "skipped"
        info["pdf_reason"] = "no PDF engine: install WeasyPrint or Google Chrome, or the forced engine is missing"
        return {"failures": failures, "warnings": [], "info": info}
    pdf = out / ("cv_ats.pdf" if kind == "cv" else "letter_ats.pdf")
    if not pdf.is_file():
        failures.append(item("pdf_text", "the engine reported a PDF but none was written"))
        info["pdf"] = "fail"
        return {"failures": failures, "warnings": [], "info": info}
    text_run = subprocess.run(
        [sys.executable, str(VERIFY_PDF), str(pdf), "--ascii-dates", "--contains", FIXTURE_NAME,
         "--contains", FIXTURE_EMAIL, "--contains", FIXTURE_PHONE], capture_output=True, text=True,
        timeout=TOOL_TIMEOUT_S)
    layout_run = subprocess.run([sys.executable, str(VERIFY_LAYOUT), str(pdf)], capture_output=True, text=True,
                                timeout=TOOL_TIMEOUT_S)
    outcomes = [verifier_outcome(text_run, "pdf_text", failures), verifier_outcome(layout_run, "layout", failures)]
    if any(status == "fail" for status, _ in outcomes):
        info["pdf"] = "fail"
    elif any(status == "skipped" for status, _ in outcomes):
        info["pdf"] = "skipped"
        info["pdf_reason"] = next(reason for status, reason in outcomes if status == "skipped")
    else:
        info["pdf"] = "pass"
    return {"failures": failures, "warnings": [], "info": info}


def check_template(path: Path, kind=None, smoke: bool = True, require_pdf: bool = False, engine: str = "auto",
                   keep=None) -> dict:
    static = check_static(path, kind)
    failures = list(static["failures"])
    warnings = list(static["warnings"])
    info = {"render": "not run", "pdf": "not run", "pdf_reason": None, "pdf_engine": None, "pages": None,
            "page_budget": None}
    ran = False
    if smoke and not failures:
        outcome = run_smoke(path, static["kind"], engine, keep)
        failures += outcome["failures"]
        warnings += outcome["warnings"]
        info = outcome["info"]
        ran = True
    if ran and require_pdf and info["pdf"] == "skipped":
        failures.append(item("pdf_gate", f"PDF gate not run ({info['pdf_reason']}): --require-pdf needs a PDF "
                                         "engine and Poppler (pdfinfo, pdftotext)"))
    checks = {name: ("fail" if any(f["check"] == name for f in failures) else "pass") for name in STATIC_CHECKS}
    if ran:
        checks["render_smoke"] = "fail" if any(f["check"] == "render_smoke" for f in failures) else "pass"
        pdf_state = info["pdf"]  # pass, fail, skipped or not run: a skipped check is never a pass
        for name in ("pdf_text", "layout"):
            if pdf_state == "skipped":
                checks[name] = "skipped"
            elif pdf_state == "not run":
                checks[name] = "not run"
            else:
                checks[name] = "fail" if any(f["check"] == name for f in failures) else "pass"
        if pdf_state == "skipped":
            checks["pdf_gate"] = "fail" if require_pdf else "skipped"
        else:
            checks["pdf_gate"] = pdf_state if pdf_state in ("pass", "fail") else "not run"
    return {"template": str(path), "name": path.stem, "kind": static["kind"], "fingerprint": static["fingerprint"],
            "manifest": static["manifest"], "checks": checks, "failures": failures, "warnings": warnings,
            "smoke": dict(info, ran=ran), "pdf_gate": info["pdf"], "verdict": "fail" if failures else "pass"}


# --- CLI -------------------------------------------------------------------------------------------------------------

def write_record(path: Path, report: dict) -> None:
    record = {"template": path.stem, "kind": report["kind"], "fingerprint": report["fingerprint"], "verdict": "pass",
              "gates": {"static": "pass", "render": report["smoke"].get("render", "not run"),
                        "pdf": report["pdf_gate"]},
              "pdf_engine": report["smoke"].get("pdf_engine"), "checked_by": "template_check.py"}
    record_path(path).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def render_text(report: dict) -> str:
    lines = [f"{report['verdict']}: {report['template']} (kind {report['kind']})"]
    for f in report["failures"]:
        lines.append(f"  fail [{f['check']}] {f['message']}")
    for w in report["warnings"]:
        lines.append(f"  warning: {w}")
    smoke = report["smoke"]
    if smoke["ran"]:
        reason = f" ({smoke['pdf_reason']})" if smoke.get("pdf_reason") else ""
        lines.append(f"  render smoke: {smoke['render']}; PDF gate: {report['pdf_gate']}{reason}; "
                     f"pages {smoke['pages']} of budget {smoke['page_budget']}")
    else:
        lines.append("  render smoke: not run")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="template_check.py", description=(__doc__ or "").split("\n\n")[0],
        epilog="Exit 0 pass, 1 fail (reasons listed), 2 usage error.", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("template", type=Path, help="template HTML file; its manifest <name>.json sits beside it")
    parser.add_argument("--kind", choices=KINDS, help="cv or letter; optional when the manifest sets kind")
    parser.add_argument("--no-smoke", action="store_true", help="static checks only: no render, no PDF")
    parser.add_argument("--require-pdf", action="store_true",
                        help="a PDF gate that cannot run (no engine, no Poppler) is a failure")
    parser.add_argument("--engine", choices=("auto", "weasyprint", "chromium"), default="auto",
                        help="PDF engine for the render smoke (default auto)")
    parser.add_argument("--register", action="store_true",
                        help="when the verdict is pass, write <name>.gate.json beside the template; otherwise "
                             "remove it. Implies --require-pdf")
    parser.add_argument("--allow-unmeasured", action="store_true",
                        help="with --register: accept a PDF gate that cannot run (no engine); the record says so and "
                             "render_cv.py warns on every render")
    parser.add_argument("--keep-smoke", type=Path, metavar="DIR",
                        help="keep the smoke render (fixture, HTML, PDF, report) in DIR")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.no_smoke and (args.require_pdf or args.register):
        parser.error("--require-pdf and --register need the render smoke: drop --no-smoke")
    if args.allow_unmeasured and not args.register:
        parser.error("--allow-unmeasured only applies with --register")
    if not args.template.is_file():
        print(f"error: template not found: {args.template}", file=sys.stderr)
        return 2
    try:
        require_pdf = args.require_pdf or (args.register and not args.allow_unmeasured)
        report = check_template(args.template, args.kind, smoke=not args.no_smoke,
                                require_pdf=require_pdf, engine=args.engine, keep=args.keep_smoke)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read {args.template}: {exc}", file=sys.stderr)
        return 2
    if args.register:
        if report["verdict"] == "pass":
            write_record(args.template, report)
            report["registered"] = True
        else:
            record_path(args.template).unlink(missing_ok=True)
            report["registered"] = False
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render_text(report))
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
