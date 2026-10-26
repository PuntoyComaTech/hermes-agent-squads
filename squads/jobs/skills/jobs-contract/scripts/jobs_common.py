#!/usr/bin/env python3
"""Shared helpers for the jobs squad scripts: YAML subset reader, front matter, slugs, atomic writes, project paths.

Import from a sibling skill's script with:

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jobs-contract" / "scripts"))
    import jobs_common as jc

The bots' bare `python3` has no PyYAML, so `load_yaml` tries the Hermes runtime module, then PyYAML, then the
built-in reader. The built-in reader handles the subset the squad writes: nested maps by indentation, block lists
(scalars, `- key: value` maps, `- {inline: map}`), flow `{}` and `[]`, quoted strings, null/bool/int/float, comments.
Anchors, tags, multi-line scalars and multiple documents are out of scope and raise `YamlError`.

Run `jobs_common.py FILE` to print a YAML file or a Markdown front matter block as JSON.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import re
import sys
import tempfile
import unicodedata
from datetime import date, datetime
from pathlib import Path


class YamlError(ValueError):
    """The text is outside the supported YAML subset or malformed."""


# --- scalars -----------------------------------------------------------------------------------------------------

_INT = re.compile(r"[-+]?\d+$")
_FLOAT = re.compile(r"[-+]?(\d+\.\d*|\.\d+)([eE][-+]?\d+)?$")


def _unquote(token: str):
    if token[0] == '"':
        try:
            return json.loads(token)
        except ValueError:
            return token[1:-1]
    return token[1:-1].replace("''", "'")


def scalar(token: str):
    token = token.strip()
    if token == "":
        return None
    if token[0] in "\"'" and len(token) >= 2 and token[-1] == token[0]:
        return _unquote(token)
    low = token.lower()
    if low in ("null", "~"):
        return None
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if _INT.match(token):
        return int(token)
    if _FLOAT.match(token):
        return float(token)
    return token


def _strip_comment(line: str) -> str:
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
            elif ch == "\\" and quote == '"':
                continue
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def _split_top(text: str, sep: str = ",") -> list[str]:
    parts, depth, quote, cur = [], 0, "", []
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch in "[{":
            depth += 1
            cur.append(ch)
        elif ch in "]}":
            depth -= 1
            cur.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    tail = "".join(cur)
    if tail.strip() or parts:
        parts.append(tail)
    return [p for p in parts if p.strip() != ""]


def _find_key_colon(text: str) -> int:
    quote, depth = "", 0
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == ":" and depth == 0 and (i + 1 == len(text) or text[i + 1] in " \t"):
            return i
    return -1


def flow(token: str):
    token = token.strip()
    if token.startswith("[") and token.endswith("]"):
        return [flow(p) for p in _split_top(token[1:-1])]
    if token.startswith("{") and token.endswith("}"):
        out = {}
        for part in _split_top(token[1:-1]):
            at = _find_key_colon(part)
            if at < 0:
                raise YamlError(f"bad flow map entry: {part!r}")
            out[scalar(part[:at].strip())] = flow(part[at + 1:])
        return out
    if token[:1] in "[{":
        raise YamlError(f"unbalanced flow collection: {token!r}")
    return scalar(token)


# --- block structure ---------------------------------------------------------------------------------------------

def _lines(text: str) -> list[tuple[int, str]]:
    rows = []
    for raw in text.replace("\t", "    ").splitlines():
        body = _strip_comment(raw).rstrip()
        if body.strip() in ("", "---"):
            continue
        rows.append((len(body) - len(body.lstrip(" ")), body.strip()))
    return rows


def _block(rows: list[tuple[int, str]], i: int, indent: int):
    if rows[i][1].startswith("- ") or rows[i][1] == "-":
        return _block_list(rows, i, indent)
    return _block_map(rows, i, indent)


def _value_after_key(rest: str, rows, i: int, indent: int):
    """Value of `key: rest` where the block (if rest is empty) starts at row i; returns (value, next row)."""
    rest = rest.strip()
    if rest:
        if rest[0] in "|>&*!":
            raise YamlError(f"unsupported YAML construct: {rest!r}")
        return flow(rest), i
    if i < len(rows) and (rows[i][0] > indent or (rows[i][0] == indent and rows[i][1].startswith("- "))):
        return _block(rows, i, rows[i][0])
    return None, i


def _block_map(rows, i: int, indent: int):
    out = {}
    while i < len(rows) and rows[i][0] == indent and not rows[i][1].startswith("- "):
        text = rows[i][1]
        at = _find_key_colon(text)
        if at < 0:
            raise YamlError(f"expected 'key: value', got {text!r}")
        key = scalar(text[:at])
        out[key], i = _value_after_key(text[at + 1:], rows, i + 1, indent)
    if i < len(rows) and rows[i][0] > indent:
        raise YamlError(f"bad indentation near {rows[i][1]!r}")
    return out, i


def _block_list(rows, i: int, indent: int):
    out = []
    while i < len(rows) and rows[i][0] == indent and (rows[i][1].startswith("- ") or rows[i][1] == "-"):
        item = rows[i][1][1:].strip()
        i += 1
        if not item:
            if i < len(rows) and rows[i][0] > indent:
                value, i = _block(rows, i, rows[i][0])
            else:
                value = None
            out.append(value)
            continue
        at = _find_key_colon(item)
        if at > 0 and item[0] not in "[{\"'":
            # "- key: value" opens a map whose further keys sit two columns right of the dash
            inner_indent = indent + 2
            sub = [(inner_indent, item)]
            while i < len(rows) and rows[i][0] >= inner_indent:
                sub.append(rows[i])
                i += 1
            value, _ = _block_map(sub, 0, inner_indent)
            out.append(value)
        else:
            out.append(flow(item))
    return out, i


def mini_yaml(text: str):
    rows = _lines(text)
    if not rows:
        return {}
    value, end = _block(rows, 0, rows[0][0])
    if end != len(rows):
        raise YamlError(f"unparsed content near {rows[end][1]!r}")
    return value


def load_yaml(text: str):
    """Parse YAML text with the best parser available; the built-in subset reader is the last resort."""
    for name in ("hermes_yaml", "yaml"):
        try:
            module = __import__(name)
        except ImportError:
            continue
        try:
            return module.safe_load(text) if text.strip() else {}
        except Exception as exc:  # noqa: BLE001 - a different parser may still read it
            last = exc
            continue
    return mini_yaml(text)


# --- front matter and files --------------------------------------------------------------------------------------

_FRONT = re.compile(r"\A\ufeff?---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)


def split_front_matter(text: str) -> tuple[dict, str]:
    """(metadata, body). No front matter or a broken one gives ({}, text); never raises."""
    match = _FRONT.match(text)
    if not match:
        return {}, text
    try:
        meta = load_yaml(match.group(1))
    except Exception:  # noqa: BLE001 - a broken profile must not stop a gate
        return {}, text[match.end():]
    return (meta if isinstance(meta, dict) else {}), text[match.end():]


def read_front_matter(path) -> dict:
    p = Path(path)
    if not p.is_file():
        return {}
    return split_front_matter(p.read_text(encoding="utf-8", errors="ignore"))[0]


def read_data(path):
    """A .json or .yaml/.yml file as data; a missing file gives {}."""
    p = Path(path)
    if not p.is_file():
        return {}
    text = p.read_text(encoding="utf-8")
    return json.loads(text) if p.suffix == ".json" else load_yaml(text)


def atomic_write(path, text: str) -> None:
    """Write text so a reader never sees a half-written file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(p.parent), prefix=f".{p.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_json(path, data) -> None:
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False, sort_keys=False) + "\n")


# The analysis gates score_analysis.decide() reads and the submit gate re-checks: one list in the contract every bot
# holds, so the applier never needs the scout's analyzing-jobs skill to know them.
GATE_NAMES = ("eligibility", "language", "location", "seniority")

# Every opening status, in pipeline order. status.py, tracker.py and the skills read this one list.
STATUSES = (
    "found", "discarded", "analyzed", "in_preparation", "in_review", "not_approved", "ready", "delivered",
    "applying", "applied", "manual_application", "skipped", "waiting", "followed_up", "screening", "interview",
    "offer", "hired", "rejected", "no_response", "withdrawn", "closed",
)

# Latin letters that have no NFKD decomposition and would vanish in an ASCII fold.
LATIN_FOLD = str.maketrans({
    "ø": "o", "Ø": "O", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ß": "ss", "ẞ": "SS", "ł": "l", "Ł": "L",
    "đ": "d", "Đ": "D", "ð": "d", "Ð": "D", "þ": "th", "Þ": "TH", "ı": "i", "ħ": "h", "Ħ": "H", "ŋ": "ng",
})


def ascii_fold(text: str) -> str:
    """Latin text to ASCII without losing letters: the fold table first, then NFKD without combining marks."""
    flat = unicodedata.normalize("NFKD", str(text).translate(LATIN_FOLD))
    return "".join(c for c in flat if not unicodedata.combining(c)).encode("ascii", "ignore").decode("ascii")


def slugify(text: str, limit: int = 40) -> str:
    flat = unicodedata.normalize("NFKD", str(text).translate(LATIN_FOLD).lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    flat = re.sub(r"[^a-z0-9]+", "-", flat).strip("-")
    return flat[:limit].strip("-")


KIT_FILES = ("cv_ats.pdf", "cv.docx", "letter_ats.pdf", "letter.docx", "cover_letter.md", "answers.md")


def kit_sha256(application):
    """sha256 over the sorted (name, bytes) of the kit files present in application/; None without cv_ats.pdf.
    The manager writes it into consent.json; the submit gate recomputes it."""
    import hashlib
    application = Path(application)
    if not (application / "cv_ats.pdf").is_file():
        return None
    digest = hashlib.sha256()
    for name in sorted(n for n in KIT_FILES if (application / n).is_file()):
        data = (application / name).read_bytes()
        digest.update(f"{name}\n{len(data)}\n".encode("utf-8"))
        digest.update(data)
    return digest.hexdigest()


_FAMILIES = None


def skill_families() -> list:
    """The tool families of skill_families.json: [{id, terms}] with lower-case terms; [] when the file is missing."""
    global _FAMILIES
    if _FAMILIES is None:
        try:
            raw = json.loads((Path(__file__).resolve().parent / "skill_families.json").read_text(encoding="utf-8"))
            _FAMILIES = [{"id": f["id"], "terms": [str(t).lower() for t in f["terms"]]} for f in raw["families"]]
        except (OSError, ValueError, KeyError, TypeError):
            _FAMILIES = []
    return _FAMILIES


_ROLE_FAMILIES = None


def role_families() -> list:
    """The role families of role_families.json: [{id, label, emerging, titles, signals, min_signals, ...}] with
    lower-case titles and signals; [] when the file is missing."""
    global _ROLE_FAMILIES
    if _ROLE_FAMILIES is None:
        try:
            raw = json.loads((Path(__file__).resolve().parent / "role_families.json").read_text(encoding="utf-8"))
            _ROLE_FAMILIES = [dict(f, titles=[str(t).lower() for t in f["titles"]],
                                   signals=[str(t).lower() for t in f.get("signals") or []],
                                   min_signals=int(f.get("min_signals") or 3)) for f in raw["families"]]
        except (OSError, ValueError, KeyError, TypeError):
            _ROLE_FAMILIES = []
    return _ROLE_FAMILIES


def _list(value) -> list:
    if isinstance(value, dict):
        value = [x for v in value.values() for x in (v if isinstance(v, list) else [v])]
    if isinstance(value, str):
        value = [value]
    return [str(x).strip() for x in value or [] if str(x).strip()]


def family_of(title) -> dict | None:
    """The role family a job title belongs to: 'Senior Forward Deployed Engineer' -> forward-deployed."""
    t = ascii_fold(str(title or "")).lower()
    best = None
    for fam in role_families():
        for name in fam["titles"]:
            if word_in(name, t) and (best is None or len(name) > best[1]):
                best = (fam, len(name))
    return best[0] if best else None


def recognised_roles(meta, evidence_text) -> list:
    """The role families this candidate can be positioned in, with why: a title the user named (target_roles,
    acceptable_roles, positioning_titles) or at least `min_signals` of the family's signals in their own evidence
    (achievements, skills). Companies name the same work many ways; a family is recognised by the work, not the word.
    Returns [{id, label, emerging, by: 'named'|'evidence', signals: [...]}]."""
    meta = meta if isinstance(meta, dict) else {}
    named = [ascii_fold(t).lower() for k in ("target_roles", "acceptable_roles", "positioning_titles")
             for t in _list(meta.get(k))]
    out = []
    for fam in role_families():
        hits = [s for s in fam["signals"] if word_in(s, evidence_text)]
        # named: one of the family's titles sits inside a title the user gave ("senior forward deployed engineer");
        # the reverse ("ai engineer" inside "applied ai engineer") would name a family the user never chose
        if any(word_in(name, t) for t in named for name in fam["titles"]):
            out.append({"id": fam["id"], "label": fam["label"], "emerging": bool(fam.get("emerging")),
                        "by": "named", "signals": hits})
        elif len(hits) >= fam["min_signals"]:
            out.append({"id": fam["id"], "label": fam["label"], "emerging": bool(fam.get("emerging")),
                        "by": "evidence", "signals": hits})
    return out


def positioning_titles(meta, evidence_text) -> list:
    """Every title the candidate may be presented under: their own target and positioning titles plus every title of a
    recognised family. Used for headlines, About, skills and search terms; never for a job title in an experience."""
    meta = meta if isinstance(meta, dict) else {}
    titles = _list(meta.get("target_roles")) + _list(meta.get("positioning_titles")) + _list(meta.get("acceptable_roles"))
    ids = {r["id"] for r in recognised_roles(meta, evidence_text)}
    for fam in role_families():
        if fam["id"] in ids:
            titles += [fam["label"]] + fam["titles"]
    return list(dict.fromkeys(titles))


def related_held(term, sources_text) -> str:
    """The member of `term`'s tool family the sources name ('' when none): PostgreSQL -> 'sql' when the candidate's
    files say SQL, GitLab CLI -> 'gh'. A term the sources hold itself returns ''; that is direct evidence."""
    t = ascii_fold(str(term or "")).lower().strip()
    if not t or word_in(t, sources_text):
        return ""
    for fam in skill_families():
        if any(t == m or word_in(m, t) for m in fam["terms"]):
            held = next((m for m in fam["terms"] if m != t and word_in(m, sources_text)), "")
            if held:
                return held
    return ""


CV_FILE = "cv_ats.pdf"  # the canonical render: the kit hash, the gates and the review read this one


def cv_upload_name(full_name: str, short_name: str = "") -> str:
    """The file name a recruiter sees: `CV_<Name>_<Surname>.pdf`, ASCII, from the name printed on the CV.

    `short_name` (contact.yaml) wins. Otherwise four or more words read as two given names and two surnames (Latin
    convention: first given name + first surname); fewer read as given name + last word. '' without a usable name."""
    words = [w for w in re.split(r"\s+", ascii_fold(short_name or full_name).strip()) if re.sub(r"[^A-Za-z]", "", w)]
    if not words:
        return ""
    picked = words if short_name else ([words[0], words[2]] if len(words) >= 4 else [words[0], words[-1]][:len(words)])
    parts = ["-".join(s.capitalize() for s in re.sub(r"[^A-Za-z0-9-]", "", w).split("-")) for w in picked]
    return "CV_" + "_".join(p for p in parts if p) + ".pdf"


def cv_upload_path(application) -> Path:
    """The CV to upload and to show: the named copy when it is byte-identical to cv_ats.pdf, else cv_ats.pdf."""
    app = Path(application)
    canonical = app / CV_FILE
    for named in sorted(app.glob("CV_*.pdf")):
        try:
            if canonical.is_file() and named.read_bytes() == canonical.read_bytes():
                return named
        except OSError:
            continue
    return canonical


def now_iso() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M")


def today() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def project_dir(arg: str | None) -> Path:
    """The project folder: --project, else $JOBS_PROJECT, else the current directory when it holds profile.md."""
    candidate = arg or os.environ.get("JOBS_PROJECT") or "."
    p = Path(candidate).expanduser().resolve()
    if not (p / "profile.md").is_file():
        raise SystemExit(f"error: {p} has no profile.md (pass --project <folder>)")
    return p


def tree_entries(root: Path, skip=frozenset()) -> list:
    """Every entry under root as (posix path relative to root, kind, bytes); kind is file, dir or link.

    Symbolic links are listed as links and never followed, so nothing outside root is read or counted. A relative
    path in skip is not entered (for example ".trash" at the top level).
    """
    out = []
    stack = [Path(root)]
    while stack:
        here = stack.pop()
        with os.scandir(here) as it:
            for entry in it:
                rel = Path(entry.path).relative_to(root).as_posix()
                if rel in skip:
                    continue
                if entry.is_symlink():
                    out.append((rel, "link", 0))
                elif entry.is_dir(follow_symlinks=False):
                    out.append((rel, "dir", 0))
                    stack.append(Path(entry.path))
                else:
                    out.append((rel, "file", entry.stat(follow_symlinks=False).st_size))
    return sorted(out)


def inside(root: Path, path: Path) -> bool:
    """True when the real location of path's parent is root or below it. root must already be resolved."""
    real = Path(os.path.realpath(path.parent))
    return real == root or root in real.parents


@contextlib.contextmanager
def locked(path):
    """Hold an exclusive lock on <path>.lock for a read-modify-write of path (seen.json, tracker.csv).

    Atomic replace prevents torn files; this lock prevents lost updates when two bots write at once.
    """
    lock_path = Path(str(path) + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


OPENING_ID_RE = re.compile(r"^JOB-\d{8}-[a-z0-9][a-z0-9-]{0,80}$")


def valid_opening_id(value) -> bool:
    """An opening id is JOB-YYYYMMDD-<slug>: no slash, no dot, so it can never leave openings/."""
    return bool(OPENING_ID_RE.match(str(value or "")))


# Language names as users and postings write them, to ISO 639-1.
LANGUAGE_ALIASES = {
    "en": "en", "english": "en", "ingles": "en", "inglés": "en", "englisch": "en", "anglais": "en", "inglese": "en",
    "es": "es", "spanish": "es", "espanol": "es", "español": "es", "castellano": "es", "spanisch": "es",
    "espagnol": "es", "spagnolo": "es", "espanhol": "es",
    "pt": "pt", "portuguese": "pt", "portugues": "pt", "português": "pt", "portugiesisch": "pt",
    "de": "de", "german": "de", "aleman": "de", "alemán": "de", "deutsch": "de", "allemand": "de", "alemao": "de",
    "fr": "fr", "french": "fr", "frances": "fr", "francés": "fr", "francais": "fr", "français": "fr",
    "franzosisch": "fr", "französisch": "fr", "frances_": "fr",
    "it": "it", "italian": "it", "italiano": "it", "italien": "it", "italienisch": "it",
    "nl": "nl", "dutch": "nl", "neerlandes": "nl", "nederlands": "nl", "holandes": "nl",
}


def normalize_language(name) -> str:
    """'Inglés', 'English', 'en' and 'EN' all become 'en'; an unknown name is returned folded and lower-cased."""
    token = str(name or "").strip().lower()
    if token in LANGUAGE_ALIASES:
        return LANGUAGE_ALIASES[token]
    folded = ascii_fold(token)
    return LANGUAGE_ALIASES.get(folded, folded)


def word_in(needle, haystack) -> bool:
    """True when needle occurs in haystack as whole words: 'Java' is not in 'JavaScript', 'Lima' not in 'Limassol'."""
    n = ascii_fold(str(needle or "")).lower().strip()
    if not n:
        return False
    h = ascii_fold(str(haystack or "")).lower()
    return re.search(r"(?<![a-z0-9])" + re.escape(n) + r"(?![a-z0-9])", h) is not None


def confidential_terms(meta) -> list:
    """profile.md `confidential_terms`: names and phrases (clients, brands, internal projects, a second job) that no
    outward text may carry: CV, letter, form answers, recruiter message, public profile copy."""
    raw = meta.get("confidential_terms") if isinstance(meta, dict) else None
    return [str(t).strip() for t in raw if str(t).strip()] if isinstance(raw, list) else []


def public_profile_terms(meta) -> list:
    """profile.md `keep_off_public_profile`: names and phrases allowed in a CV, letter or form answer sent to one
    employer, but never on a public profile (LinkedIn): clients of the current employer, team size."""
    raw = meta.get("keep_off_public_profile") if isinstance(meta, dict) else None
    return [str(t).strip() for t in raw if str(t).strip()] if isinstance(raw, list) else []


def confidential_hits(text, terms) -> list:
    """The confidential terms found in text as whole words (accent- and case-insensitive)."""
    return [t for t in terms if word_in(t, text)]


CURRENT_WORDS = ("", "current", "present", "now", "actual", "actualidad", "hoy")  # an experience's `to` when ongoing


def _month_index(value, today_value):
    text = str(value or "").strip().lower()
    if text in CURRENT_WORDS:
        return today_value.year * 12 + today_value.month - 1
    m = re.match(r"^(\d{4})(?:-(\d{1,2}))?", text)
    if not m:
        return None
    return int(m.group(1)) * 12 + (int(m.group(2) or 1) - 1)


def experience_years(experiences, on=None) -> dict:
    """Years of experience computed from achievements.yaml experiences (from/to dates).

    total: union of all periods (overlaps counted once). by_title: {lower-cased title: years}. Months are counted
    inclusively, so 2026-06 to 2026-10 is 5 months. Entries without a parseable 'from' are ignored.
    """
    when = on or date.today()
    spans, by_title = [], {}
    for exp in experiences or []:
        if not isinstance(exp, dict):
            continue
        start = _month_index(exp.get("from"), when)
        end = _month_index(exp.get("to"), when)
        if start is None or end is None or end < start:
            continue
        spans.append((start, end))
        title = str(exp.get("title") or "").strip().lower()
        if title:
            by_title[title] = by_title.get(title, 0) + (end - start + 1)
    months = 0
    last = None
    for start, end in sorted(spans):
        if last is not None and start <= last:
            if end > last:
                months += end - last
                last = end
            continue
        months += end - start + 1
        last = end
    return {"total": round(months / 12, 1), "by_title": {k: round(v / 12, 1) for k, v in by_title.items()}}


CEFR = ["A1", "A2", "B1", "B2", "C1", "C2"]


def cefr_index(level) -> int | None:
    """Position of a CEFR level (A1=0 ... C2=5); None when unknown."""
    token = str(level or "").strip().upper()
    return CEFR.index(token) if token in CEFR else None


# A form's language-level option -> the lowest CEFR level the label asserts. The ILR/LinkedIn scale reads one step
# above its literal words: "Professional Working Proficiency" is ILR 3, about C1, so it overstates a B2 (the reviewer
# ruled this on a real application). Order matters: the first pattern that matches decides.
LEVEL_LABELS = (
    (re.compile(r"\b(native|bilingual|nativo|nativa|biling[uü]e|lengua materna|mother tongue)\b", re.I), "C2"),
    (re.compile(r"\b(full professional|competencia profesional completa)\b", re.I), "C2"),
    (re.compile(r"\b(professional working|competencia profesional)\b", re.I), "C1"),
    (re.compile(r"\b(limited working|competencia b[aá]sica limitada)\b", re.I), "B1"),
    (re.compile(r"\b(elementary|competencia b[aá]sica elemental|elemental)\b", re.I), "A1"),
    (re.compile(r"\b(fluent|fluido|fluida|fluency)\b", re.I), "C1"),
    (re.compile(r"\b(upper[- ]intermediate|intermedio[- ]alto|intermedio avanzado)\b", re.I), "B2"),
    (re.compile(r"\b(advanced|avanzado|proficient)\b", re.I), "C1"),
    (re.compile(r"\b(intermediate|intermedio|conversational|conversacional)\b", re.I), "B1"),
    (re.compile(r"\b(basic|beginner|basico|básico|principiante)\b", re.I), "A1"),
)
ILR_LABELS = LEVEL_LABELS[:5]  # the "... proficiency" scale: unambiguous wherever it appears in a sentence
CEFR_TOKEN = re.compile(r"\b([ABC][12])\b")


def label_level(label) -> str | None:
    """The CEFR level a language option claims ("B2", "Upper-intermediate", "Professional Working Proficiency");
    None when the label states no level."""
    text = str(label or "")
    found = CEFR_TOKEN.findall(text.upper())
    if found:
        return max(found, key=CEFR.index)
    for pattern, level in LEVEL_LABELS:
        if pattern.search(text):
            return level
    return None


def language_option(options, declared) -> dict:
    """The option to pick for a declared CEFR level: the highest option whose claim is not above it. Returns
    {"answer", "level", "why"}; answer is None when every option claims more (or none states a level)."""
    have = cefr_index(declared)
    if have is None:
        return {"answer": None, "level": None, "why": f"declared level {declared!r} is not a CEFR level"}
    best = None
    for option in options or []:
        level = label_level(option)
        idx = cefr_index(level)
        if idx is None or idx > have:
            continue
        if best is None or idx > best[0]:
            best = (idx, option, level)
    if best is None:
        return {"answer": None, "level": None, "why": f"every option claims more than {declared} or states no level"}
    return {"answer": best[1], "level": best[2], "why": f"the highest option not above the declared {declared}"}


HEADING = re.compile(r"^\s*#{1,6}\s+(.*)$")


def language_named(text) -> str:
    """The ISO code of the first language named in text ("English level" -> en), else ""."""
    for token in re.findall(r"[A-Za-zÀ-ÿ]+", str(text or "")):
        code = LANGUAGE_ALIASES.get(token.lower()) or LANGUAGE_ALIASES.get(ascii_fold(token.lower()))
        if code and len(token) > 2:
            return code
    return ""


NEGATION_BEFORE = re.compile(r"\b(?:never|not|no|don't|do not|avoid|instead of|rather than|nunca|evita|evitar|"
                             r"no usar|en lugar de)\b[^;.]{0,40}$", re.I)


def last_language_before(text: str) -> str:
    """The ISO code of the last language named in text, else ""."""
    code = ""
    for token in re.findall(r"[A-Za-zÀ-ÿ]+", str(text or "")):
        found = LANGUAGE_ALIASES.get(token.lower()) or LANGUAGE_ALIASES.get(ascii_fold(token.lower()))
        if found and len(token) > 2:
            code = found
    return code


def language_label_overclaims(text, levels: dict) -> list:
    """ILR/LinkedIn labels above the declared level of the language they are about.

    levels: {iso code: CEFR}. Every label on a line is checked. Its language is the last one named before it on the
    line ("English: B2; Spanish: native" binds "native" to Spanish), else the first one named after it on the line
    ("Native Spanish"), else the nearest heading, else the previous non-empty line ("English level:" then the option).
    A label after "never", "not", "instead of" is a prohibition, not a claim. Returns [{line, label, language,
    declared, claims}]."""
    hits, heading, previous = [], "", ""
    for line in str(text or "").splitlines():
        match = HEADING.match(line)
        if match:
            heading, previous = match.group(1), ""
            continue
        taken = []
        for pattern, level in ILR_LABELS:
            for found in pattern.finditer(line):
                if any(found.start() < end and start < found.end() for start, end in taken):
                    continue  # "competencia profesional completa" is one label, not two
                taken.append((found.start(), found.end()))
                before = line[:found.start()]
                if NEGATION_BEFORE.search(before):
                    continue
                lang = (last_language_before(before) or language_named(line[found.end():found.end() + 30])
                        or language_named(heading) or language_named(previous))
                declared = levels.get(lang)
                if declared and (cefr_index(level) or 0) > (cefr_index(declared) or 0):
                    hits.append({"line": line.strip(), "label": found.group(0), "language": lang,
                                 "declared": declared, "claims": level})
        if line.strip():
            previous = line
    return hits


def declared_levels(achievements) -> dict:
    """{iso code: CEFR} from achievements.yaml languages."""
    out = {}
    for row in (achievements or {}).get("languages") or []:
        if isinstance(row, dict) and row.get("language") and cefr_index(row.get("level")) is not None:
            out[normalize_language(row["language"])] = str(row["level"]).upper()
    return out


def ilr_overclaims(text, declared) -> list:
    """ILR/LinkedIn scale labels in text that claim more than the declared CEFR level ("Professional Working
    Proficiency" for a B2)."""
    have = cefr_index(declared)
    if have is None:
        return []
    hits = []
    for pattern, level in ILR_LABELS:
        for match in pattern.finditer(str(text or "")):
            if (cefr_index(level) or 0) > have:
                hits.append(match.group(0))
    return hits


# A sentence that says how the user works TODAY ("working remotely from Colombia", "want to keep working remotely").
# It is a fact about the current job, so only achievements.yaml experiences[].work_mode can back it; profile.md
# work_mode is the search preference (what the user wants), never what the current job is.
_REMOTE_ES = r"(?:de\s+(?:forma|manera)\s+|en\s+)?remot[oa](?:mente)?"
REMOTE_NOW = re.compile(
    r"\b(?:keep|continue|still)\s+(?:working|to work|work)\s+remotely"           # "want to keep working remotely"
    r"|\bI(?:'m|\s+am)\s+(?:currently\s+|now\s+|still\s+)?working\s+remotely"    # "I'm working remotely"
    r"|\bI\s+(?:currently\s+|now\s+|still\s+)?work\s+remotely"                  # "I work remotely for ..."
    r"|\b(?:currently|now)\s+working\s+remotely"
    r"|\bworking\s+remotely\s+(?:from|out of)\b"                                  # summary: "... working remotely
    r"|\b(?:sigo|seguir|continuar|contin[uú]o)\s+trabajando\s+" + _REMOTE_ES +      #  from Colombia"
    r"|\b(?:actualmente|ahora|hoy)\s+trabajo\s+" + _REMOTE_ES +
    r"|\btrabaj(?:o|ando)\s+" + _REMOTE_ES + r"\s+desde\b", re.I)
WISH_BEFORE = re.compile(r"\b(?:want|wish|prefer|interested in|looking for|seeking|open to|would like|hope|aim|"
                         r"eager|ready|keen|happy|able|comfortable|start|begin|"
                         r"quiero|busco|prefiero|me interesa|empezar|comenzar)\b[^.;:!?]{0,30}$", re.I)
CONTINUING = re.compile(r"\b(?:keep|continue|still|seguir|continuar|sigo|contin[uú]o)\b", re.I)
# Not about the user's current job: a past role ("was working remotely from Bogotá until 2023") or someone else
# ("the team works remotely from Lisbon", "engineers working remotely from three countries").
NOT_NOW_BEFORE = re.compile(r"\b(?:was|were|had been|used to|previous(?:ly)?|former(?:ly)?|until|before|"
                            r"team|teams|engineers|developers|people|employees|staff|company|companies|they|who|"
                            r"estaba|estuve|anterior|equipo|ellos)\b[^.;!?]{0,50}$", re.I)
PAST_AFTER = re.compile(r"^[^.;!?]{0,60}\b(?:until|hasta)\s+(?:19|20)\d\d\b", re.I)


def remote_now_claims(text) -> list:
    """Spans that state the user works remotely now. "I want to work remotely" is a wish and passes; "I want to keep
    working remotely" says he does today and is a claim. A past role or another subject is not a claim."""
    out, text = [], str(text or "")
    for match in REMOTE_NOW.finditer(text):
        before = text[max(0, match.start() - 60):match.start()]
        if WISH_BEFORE.search(before) and not CONTINUING.search(match.group(0)):
            continue
        if NOT_NOW_BEFORE.search(before) or PAST_AFTER.search(text[match.end():]):
            continue
        out.append(match.group(0))
    return out


def current_work_modes(achievements) -> set:
    """work_mode of the current experiences in achievements.yaml (remote | hybrid | onsite)."""
    modes = set()
    for exp in (achievements or {}).get("experiences") or []:
        if isinstance(exp, dict) and str(exp.get("to") or "").strip().lower() in CURRENT_WORDS:
            mode = str(exp.get("work_mode") or "").strip().lower()
            if mode:
                modes.add(mode)
    return modes


SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def sentences(text) -> list:
    return [s.strip() for s in SENTENCE_SPLIT.split(str(text or "")) if s.strip()]


def same_claim_hits(text, terms) -> list:
    """Sentences of text that hold every term as whole words: the instances of one recurring claim."""
    words = [t for t in (str(x).strip() for x in terms or []) if t]
    if not words:
        return []
    return [s for s in sentences(text) if all(word_in(w, s) for w in words)]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Print a YAML file or a Markdown front matter block as JSON.")
    parser.add_argument("file", help="a .yaml/.yml/.json file or a Markdown file with front matter")
    args = parser.parse_args(argv)
    path = Path(args.file)
    if not path.is_file():
        print(f"error: {path} not found", file=sys.stderr)
        return 2
    try:
        data = read_front_matter(path) if path.suffix == ".md" else read_data(path)
    except (YamlError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
