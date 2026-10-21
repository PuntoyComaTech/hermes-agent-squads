#!/usr/bin/env python3
"""Canonical dedupe key for a job posting, a canonical URL, an opening folder id, and an audit of a seen-state file.

The key is a pure function of the posting, so two runs that see the same job produce the same string and a
seen-state file cannot hold one job under two spellings. Company and title become lowercase ASCII slugs joined by
an underscore: "<company-slug>_<title-slug>". Slugs are capped in length; a capped slug gets a hash of the full
slug appended, so a long title is stable across runs and two different long titles never collide.

A company or title that the ASCII fold cannot represent (a non-Latin script) keeps any readable fragment, and its
identity comes from a hash of the name or, for a title, from the portal's numeric id in the URL. A fragment never
stands alone, so a non-Latin title can never collapse onto another one.

A company value that is an identifier rather than a name (16 or more hex digits, or a UUID) never feeds the key as
text: the key uses "unknown-company" with a hash of the canonical URL, so one posting keeps one key and two postings
do not share one.

The opening id is JOB-YYYYMMDD-<company>-<role>: the readable company name and the short role title. A hash of the
key is appended only when the readable id is already owned by another opening of the project, so a re-run of the
same opening gets the same id, and two openings never share a folder.

Usage:
  python3 job_key.py --company "Acme Corp" --title "SOC Analyst (L2)" [--url URL]
  python3 job_key.py --company "Acme" --title "Data analyst" --opening-id --date 2026-10-20 [--project DIR] [--url URL]
  python3 job_key.py --url-canonical "https://jobs.example.com/view/42/?utm_source=x#apply"
  python3 job_key.py --audit searches/seen.json

Exit 0 when a key, id or URL is printed, or when an audit finds nothing wrong. Exit 1 when an audit finds malformed
keys or one URL under two keys. Exit 2 on usage errors or an unreadable state file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jobs_common import ascii_fold, read_front_matter  # noqa: E402  - one fold table for every key and slug

COMPANY_MAX = 40
TITLE_MAX = 60
HASH_LEN = 6
TRACKING_PARAMS = ("gclid", "fbclid", "mc_cid", "mc_eid")

# Anything outside this set becomes a separator. Strict on purpose: "/" and "," break file paths, and an allowlist
# is not surprised by the next punctuation mark a job board invents.
_NON_SLUG = re.compile(r"[^a-z0-9]+")
_JOB_ID = re.compile(r"(\d{6,})")
# A canonical key: lowercase alphanumerics and hyphens on either side of exactly one underscore.
_CANONICAL = re.compile(r"^[a-z0-9][a-z0-9-]*_[a-z0-9][a-z0-9-]*$")
_LEGACY_PART = re.compile(r"[a-z0-9][a-z0-9-]*")
_HASH_NAME = re.compile(r"^(?:[0-9a-f]{16,}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$", re.IGNORECASE)

# The opening id: "JOB-" + 8 digits + "-" + the body, at most OPENING_ID_MAX characters in all.
OPENING_ID_MAX = 50
COMPANY_READABLE_MAX = 17
UNKNOWN_COMPANY = "unknown-company"
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Bracketed notes ("(L2)", "[Remote]") and the text after a separator ("Data Analyst - Lima") are not the role.
_BRACKETS = re.compile(r"[\(\[\{][^\)\]\}]*[\)\]\}]")
_ROLE_SPLIT = re.compile(
    r"\s+[-\u2013\u2014|]\s+|\s+/\s+|\s*\|\s*|,\s+|\s+@\s+|\s+(?:at|in|en|para)\s+",
    re.IGNORECASE,
)


def is_hash_like(name) -> bool:
    """A company value that is an identifier rather than a name: 16 or more hex digits, or a UUID."""
    return bool(_HASH_NAME.match(str(name or "").strip()))


def slugify(text) -> str:
    """Lowercase ASCII slug. A non-Latin script reduces to an empty string."""
    if not text:
        return ""
    return _NON_SLUG.sub("-", ascii_fold(str(text)).lower()).strip("-")


def _lost_letters(text) -> bool:
    """True when the ASCII fold dropped non-Latin letters, so the slug under-identifies the name.

    NFKD turns "u" with a diaeresis into "u" plus a combining mark, so most Latin text keeps every letter. A
    Cyrillic, Greek, CJK or Arabic letter has no ASCII form and vanishes. Latin letters with no decomposition
    (the Nordic letters, the sharp s, the Polish l with stroke) are folded by `jobs_common.LATIN_FOLD`, so they
    are not lost and not counted here.
    """
    if not text:
        return False
    for ch in unicodedata.normalize("NFKD", str(text)):
        if ord(ch) < 128 or not ch.isalpha():
            continue
        if not unicodedata.name(ch, "LATIN").startswith("LATIN"):
            return True
    return False


def _cap(slug: str, limit: int) -> str:
    """Cap a slug length without making the truncation lossy across runs (hash of the full slug)."""
    if len(slug) <= limit:
        return slug
    digest = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:HASH_LEN]
    head = slug[:max(1, limit - HASH_LEN - 1)].rstrip("-")
    return f"{head}-{digest}"  # the result never exceeds `limit`, hash included


def _cut_words(slug: str, limit: int) -> str:
    """A slug cut to at most `limit` characters at a word boundary. Only one word longer than the limit is cut."""
    if limit <= 0:
        return ""
    if len(slug) <= limit:
        return slug
    if slug[limit] == "-":
        return slug[:limit].rstrip("-")
    head = slug[:limit]
    if "-" in head:
        head = head.rsplit("-", 1)[0]
    return head.strip("-")


def canonical_url(url) -> str:
    """The posting URL without tracking parameters or fragment; scheme and host lowercased, trailing slash dropped."""
    text = str(url or "").strip()
    if not text:
        return ""
    parts = urlsplit(text)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    path = parts.path.rstrip("/") if len(parts.path) > 1 else parts.path
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def _company_identity(company, url: str = "") -> str:
    """The company half of the key: a readable slug, or a hashed one where the name has no ASCII form."""
    if is_hash_like(company) or not str(company or "").strip():
        # No usable name: the posting's own URL keeps two unnamed postings apart. No URL: the plain placeholder.
        basis = canonical_url(url)
        if not basis:
            return UNKNOWN_COMPANY
        return f"{UNKNOWN_COMPANY}-{hashlib.sha1(basis.encode('utf-8')).hexdigest()[:HASH_LEN]}"
    company_slug = _cap(slugify(company), COMPANY_MAX)
    if not company_slug or _lost_letters(company):
        name = unicodedata.normalize("NFC", str(company or "").strip().casefold())
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:HASH_LEN]
        if not name:
            company_slug = UNKNOWN_COMPANY
        else:
            company_slug = f"{company_slug}-{digest}" if company_slug else f"company-{digest}"
    return company_slug


def _title_identity(title, url: str = "") -> str:
    """The title half of the key: a readable slug, or the portal id / a hash where the title has no ASCII form."""
    title_slug = _cap(slugify(title), TITLE_MAX)
    if not title_slug or _lost_letters(title):
        fragment = title_slug
        match = _JOB_ID.search(url or "")
        if match:
            return f"{fragment}-{match.group(1)}" if fragment else match.group(1)
        # The URL is the posting's identity when there is one; the title is not (a re-listing with an altered
        # title must keep its key). Without a URL the title is all there is to key on.
        digest_basis = str(url) if url else str(title)
        digest = hashlib.sha1(digest_basis.encode("utf-8")).hexdigest()[:HASH_LEN]
        basis = slugify(unicodedata.normalize("NFKD", str(title or url or "")))
        return f"{fragment}-{digest}" if fragment else (basis or f"untitled-{digest}")
    return title_slug


def _slugs(company, title, url: str = ""):
    """(company slug, title slug) for one posting; the two halves of make_key."""
    return _company_identity(company, url), _title_identity(title, url)


def make_key(company, title, url: str = "") -> str:
    """The canonical dedupe key for one posting: "<company-slug>_<title-slug>"."""
    company_slug, title_slug = _slugs(company, title, url)
    return f"{company_slug}_{title_slug}"


def _short_role(title) -> str:
    """The role without bracketed notes or a trailing place, reference or date.

    "Data Analyst II (Lima) - 11892" -> "Data Analyst II"; "AI Engineer - Python R" -> "AI Engineer".
    """
    text = " ".join(str(title or "").split())
    trimmed = " ".join(_BRACKETS.sub(" ", text).split())
    base = trimmed or text
    return _ROLE_SPLIT.split(base, maxsplit=1)[0].strip() or base


def _readable_company(company, url: str) -> str:
    """The company part of an opening id: the name as a slug, cut on a word boundary."""
    if is_hash_like(company) or not str(company or "").strip():
        return UNKNOWN_COMPANY
    slug = slugify(company)
    if not slug or _lost_letters(company):
        return _cap(_company_identity(company, url), COMPANY_READABLE_MAX)
    return _cut_words(slug, COMPANY_READABLE_MAX)


def _readable_role(title, url: str, room: int) -> str:
    """The role part of an opening id, at most `room` characters; empty when there is no room for it."""
    if room <= 0:
        return ""
    role = slugify(_short_role(title))
    if not role or _lost_letters(title):
        ident = _title_identity(title, url)
        return _cap(ident, room) if room > HASH_LEN + 1 else ""
    return _cut_words(role, room)


def _opening_body(company, title, url: str, limit: int) -> str:
    """"<company>-<role>" within `limit` characters. Never empty: the company part is always present."""
    readable = _readable_company(company, url)
    role = _readable_role(title, url, limit - len(readable) - 1)
    return f"{readable}-{role}" if role else readable


def make_opening_id(company, title, day: str, url: str = "", taken=None) -> str:
    """The opening folder id: JOB-YYYYMMDD-<company>-<role>, lowercase ASCII, at most OPENING_ID_MAX characters.

    The date is the day the opening was first found (YYYY-MM-DD). `taken` maps each opening id already in the
    project to the dedupe key that owns it (see existing_openings). The readable id is returned unless another
    opening owns it; then a hash of this posting's key is appended, so the id is the same on every run for this
    posting and never the same as another opening's.
    """
    if not _DATE.match(day or ""):
        raise ValueError(f"date must be YYYY-MM-DD, got {day!r}")
    prefix = "JOB-" + day.replace("-", "") + "-"
    room = OPENING_ID_MAX - len(prefix)
    key = make_key(company, title, url)
    owners = taken or {}
    base = prefix + _opening_body(company, title, url, room)
    if owners.get(base, key) == key:
        return base
    for length in range(HASH_LEN, 13):
        digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:length]
        candidate = f"{prefix}{_opening_body(company, title, url, room - length - 1)}-{digest}"
        if owners.get(candidate, key) == key:
            return candidate
    raise ValueError(f"no free opening id for this posting ({key})")


def existing_openings(project: Path) -> dict:
    """Opening id -> the dedupe key that owns it, from the project's openings/ folders and searches/seen.json.

    Raises OSError or ValueError when seen.json cannot be read, so a collision check never runs blind.
    """
    owners: dict = {}
    folders = project / "openings"
    if folders.is_dir():
        for folder in sorted(p for p in folders.iterdir() if p.is_dir()):
            try:
                key = read_front_matter(folder / "opening.md").get("key")
            except (OSError, ValueError):
                key = None
            owners[folder.name] = key if isinstance(key, str) else ""
    state = project / "searches" / "seen.json"
    if state.is_file():
        for key, entry in _load_seen(state).items():
            opening = entry.get("opening_id")
            if isinstance(opening, str) and opening and not owners.get(opening):
                owners[opening] = key
    return owners


def is_canonical(key: str) -> bool:
    """Structurally safe as a dedupe key and as a folder name."""
    return bool(key) and bool(_CANONICAL.match(key))


def is_legacy_shape(key: str) -> bool:
    """Old three-part "company_title_location" keys: harmless characters, but make_key never produces them."""
    return bool(key) and key.count("_") > 1 and all(_LEGACY_PART.fullmatch(part) for part in key.split("_") if part)


def _load_seen(path: Path):
    """The entries of a state file: {"seen": {...}} or a flat object. Raises OSError or ValueError on a bad shape."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise OSError(f"cannot read {path}: {exc}") from exc
    seen = doc.get("seen", doc) if isinstance(doc, dict) else doc
    if not isinstance(seen, dict):
        raise ValueError(f"{path}: expected an object of job entries")
    for key, entry in seen.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{path}: entry is not an object: {key}")
        if entry.get("url") is not None and not isinstance(entry["url"], str):
            raise ValueError(f"{path}: entry url is not a string: {key}")
    return seen


def audit(path: Path) -> int:
    try:
        seen = _load_seen(path)
    except (OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    malformed = [k for k in seen if not is_canonical(k) and not is_legacy_shape(k)]
    legacy = [k for k in seen if is_legacy_shape(k)]
    by_url: dict = {}
    for key, entry in seen.items():
        url = (entry.get("url") or "").rstrip("/")
        if url:
            by_url.setdefault(url, []).append(key)
    duplicates = {u: ks for u, ks in by_url.items() if len(ks) > 1}
    # Drift is a key that differs from what make_key gives today. Reported as a count: a rename is a decision.
    drift = [
        k for k, v in seen.items()
        if is_canonical(k) and k != make_key(v.get("company", ""), v.get("title", ""), v.get("url", ""))
    ]
    print(json.dumps({
        "entries": len(seen),
        "malformed_keys": malformed,
        "legacy_three_part_keys": legacy,
        "duplicate_urls": duplicates,
        "keys_not_matching_current_rule": len(drift),
    }, indent=2, ensure_ascii=False))
    return 1 if (malformed or duplicates) else 0


def _force_utf8_output() -> None:
    """Write UTF-8 whatever the host's default code page is."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


def main(argv=None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(description="Canonical dedupe key for a job posting, canonical URL, seen-state audit.")
    parser.add_argument("--company")
    parser.add_argument("--title")
    parser.add_argument("--url", default="")
    parser.add_argument("--url-canonical", metavar="URL", help="print the canonical form of one URL and exit")
    parser.add_argument("--audit", metavar="STATE_JSON", help="audit a seen-state file and exit")
    parser.add_argument("--opening-id", action="store_true", help="print the opening folder id instead of the key")
    parser.add_argument("--date", help="with --opening-id: the day first found, YYYY-MM-DD")
    parser.add_argument("--project", type=Path, metavar="DIR",
                        help="with --opening-id: the project folder; an id another opening owns gets a hash suffix")
    args = parser.parse_args(argv)

    if args.audit:
        return audit(Path(args.audit))
    if args.url_canonical is not None:
        print(canonical_url(args.url_canonical))
        return 0
    if args.company is None or args.title is None:
        parser.error("give --company and --title, --url-canonical, or --audit")
    if args.project is not None and not args.opening_id:
        parser.error("--project is used with --opening-id")
    if args.opening_id:
        if not args.date:
            parser.error("--opening-id needs --date YYYY-MM-DD")
        taken: dict = {}
        if args.project is not None:
            try:
                taken = existing_openings(args.project)
            except (OSError, ValueError) as exc:
                print(f"job_key: {exc}", file=sys.stderr)
                return 2
        try:
            print(make_opening_id(args.company, args.title, args.date, args.url, taken=taken))
        except ValueError as exc:
            print(f"job_key: {exc}", file=sys.stderr)
            return 2
        return 0
    print(make_key(args.company, args.title, args.url))
    return 0


if __name__ == "__main__":
    sys.exit(main())
