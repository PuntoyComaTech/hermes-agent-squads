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


def confidential_hits(text, terms) -> list:
    """The confidential terms found in text as whole words (accent- and case-insensitive)."""
    return [t for t in terms if word_in(t, text)]


def _month_index(value, today_value):
    text = str(value or "").strip().lower()
    if text in ("", "current", "present", "now", "actual", "actualidad", "hoy"):
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
