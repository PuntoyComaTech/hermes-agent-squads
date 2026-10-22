#!/usr/bin/env python3
"""talent.com Colombia: job listing and one offer, as JSON, on the standard library only.

  cli.py search --query "analista de datos" [--location "Bogota"] [--jobage 1] [--limit 5]
                [--country co] [--today 2026-10-22] [--fixture-dir DIR] --format json
  cli.py detail <id|url> [--fixture-dir DIR] --format json

One HTTP GET per page: the cards are server-rendered with title, company, place and timestamp.
`--jobage N` maps to the board's `date=N` window (1 = last 24 hours). The board returned nothing for `p=2`, so
there is no page flag. Result urls are the talent.com view pages; the board aggregates other sites, and the
employer's own apply page is not followed here.

Offline: TALENT_FIXTURE_DIR (or --fixture-dir) points at a directory holding `listing.html` and `detail.html`;
the CLI then reads those files and never opens a socket.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

PORTAL = "talent"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
ACCEPT_LANGUAGE = "es-CO,es;q=0.9"
TIMEOUT_S = 25
RETRY_SLEEP_S = 2
MARKET_RE = re.compile(r"^[a-z]{2}$")
CARD_RE = re.compile(r"<div[^>]*\bdata-new-id=\"(\d+)\"", re.I)
BLOCK_END_RE = re.compile(r"(?i)<\s*(?:br|/p|/div|/li|/h[1-6]|/tr|/section)\s*/?>")
SPACES_RE = re.compile(r"[ \t\u00a0]+")
AGE_RE = re.compile(
    r"hace\s+(m[aá]s\s+de\s+)?(\d+)?\s*(minuto|hora|d[ií]a|semana|mes|a[nñ]o)", re.I)
COUNTRY_NAMES = {"co": "Colombia", "mx": "México", "ar": "Argentina", "cl": "Chile", "pe": "Perú",
                 "ec": "Ecuador", "es": "España", "us": "Estados Unidos"}
TAG_RE = re.compile(r"<[^>]*>")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
CONTROL_KEEP_NL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
BIDI_RE = re.compile("[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
MAX_LIMIT = 100  # the page ceiling: a larger --limit is clamped here, never passed through
URL_HOSTS = ("talent.com",)  # this portal's url_hosts in portal.json


class CliError(Exception):
    """A failure reported as {"error", "code"} on stderr with exit 1."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        sys.stderr.write(json.dumps({"error": message, "code": "BAD_ARG"}) + "\n")
        sys.exit(1)


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")


def fail(error, code):
    sys.stderr.write(json.dumps({"error": error, "code": code}, ensure_ascii=False) + "\n")
    return 1


# --- text ---------------------------------------------------------------------------------------------------------

def clean(value):
    """One line of decoded text, or None when nothing is left.

    The board escapes its text once for HTML, so it is unescaped once: a title that already carries entities keeps
    them instead of losing the words inside them. Newlines, control characters and bidi/zero-width marks are
    collapsed, because every result field is one line.
    """
    if value is None:
        return None
    text = TAG_RE.sub(" ", str(value))
    text = html.unescape(text)
    text = BIDI_RE.sub(" ", CONTROL_RE.sub(" ", text))
    text = SPACES_RE.sub(" ", text).strip()
    return text or None


def html_to_text(fragment):
    """Readable text from an HTML description: block ends become line breaks, tags and entities go.

    Real markup is removed before the single unescape. A tag that arrives escaped (`&lt;script&gt;`) is text, not
    markup, so it is stripped afterwards as text: a description never carries anything tag-shaped.
    """
    if not fragment:
        return None
    text = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", str(fragment))
    text = BLOCK_END_RE.sub("\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = TAG_RE.sub(" ", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = BIDI_RE.sub("", CONTROL_KEEP_NL_RE.sub(" ", text))
    lines = [SPACES_RE.sub(" ", line).strip() for line in text.splitlines()]
    kept, blank = [], False
    for line in lines:
        if line in ("-",):
            line = ""
        if line:
            kept.append(line)
            blank = False
        elif kept and not blank:
            kept.append("")
            blank = True
    while kept and not kept[-1]:
        kept.pop()
    return "\n".join(kept) or None


def parse_day(value):
    if value is None:
        return dt.date.today()
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise CliError("BAD_ARG", f"--today must be YYYY-MM-DD, got {value!r}")


def parse_age(text, today):
    """The day a relative age names. A floor ("more than 30 days") is not a date: None."""
    value = clean(text)
    if not value:
        return None
    low = value.lower()
    if re.search(r"\bayer\b", low):
        return today - dt.timedelta(days=1)
    if re.search(r"\bhoy\b|\bmomento\b|\breci[eé]n\b|\bjusto ahora\b", low):
        return today
    found = AGE_RE.search(low)
    if not found or found.group(1):
        return None
    count = int(found.group(2) or 1)
    unit = found.group(3).lower()
    if unit.startswith(("minuto", "hora")):
        return today
    if unit.startswith("d"):
        return today - dt.timedelta(days=count)
    if unit.startswith("semana"):
        return today - dt.timedelta(days=7 * count)
    if unit.startswith("mes"):
        return today - dt.timedelta(days=30 * count)
    return today - dt.timedelta(days=365 * count)


def iso_day(value):
    """The date part of an ISO timestamp such as 2026-10-22T01:52:10Z."""
    text = clean(value)
    if not text:
        return None
    found = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return found.group(1) if found else None


def numeric_id(value):
    """The board's own job id: digits only, so it can be put back into a `view?id=` address."""
    text = str(value or "").strip()
    return text if re.fullmatch(r"\d{6,}", text) else None


def offer_id(url):
    """The id of a talent.com view address, for a page whose JSON-LD id is missing or unusable."""
    found = re.search(r"(?:^|&)id=(\d+)", urlparse(url or "").query)
    return found.group(1) if found else None


def host_matches(host, hosts):
    host = (host or "").lower()
    return any(host == entry or host.endswith("." + entry) for entry in hosts)


def portal_url(value, base=None):
    """An https URL on this portal's own hosts, or None.

    The board aggregates other sites, and its JSON-LD sometimes carries the employer's own page or a `javascript:`
    href. Only an https address on url_hosts is a result this CLI may print.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or re.search(r"[\s\\\x00-\x1f]", text):
        return None
    if base:
        text = urljoin(base, text)
    parts = urlparse(text)
    if parts.scheme.lower() != "https" or not host_matches(parts.hostname, URL_HOSTS):
        return None
    return text


# --- HTTP ---------------------------------------------------------------------------------------------------------

def _get(url):
    request = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Language": ACCEPT_LANGUAGE,
        "Accept": "text/html,application/xhtml+xml",
    })
    for attempt in (0, 1):
        try:
            with urlopen(request, timeout=TIMEOUT_S) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, "replace")
        except HTTPError as exc:
            if (exc.code == 429 or 500 <= exc.code < 600) and attempt == 0:
                time.sleep(RETRY_SLEEP_S)
                continue
            if exc.code == 429:
                raise CliError("RATE_LIMITED", f"HTTP 429 from {url}; the board asked for fewer requests")
            raise CliError("HTTP_ERROR", f"HTTP {exc.code} from {url}")
        except URLError as exc:
            raise CliError("FETCH_FAILED", f"cannot reach {url}: {exc.reason}")
        except OSError as exc:
            raise CliError("FETCH_FAILED", f"cannot reach {url}: {exc}")
    raise CliError("FETCH_FAILED", f"cannot reach {url}")


def fixture_dir(ns):
    return ns.fixture_dir or os.environ.get("TALENT_FIXTURE_DIR") or ""


def read_page(ns, kind):
    directory = fixture_dir(ns)
    if directory:
        name = "listing.html" if kind == "listing" else "detail.html"
        path = Path(directory) / name
        if not path.is_file():
            raise CliError("FIXTURE_MISSING", f"no {name} in the fixture directory {directory}")
        return path.read_text(encoding="utf-8", errors="replace")
    return _get(ns.url)


# --- search -------------------------------------------------------------------------------------------------------

def build_search_url(query, location=None, jobage=None, country="co"):
    if not MARKET_RE.match(country or ""):
        raise CliError("BAD_ARG", f"--country must be a two-letter code, got {country!r}")
    params = []
    if query:
        params.append(("k", query))
    if location:
        params.append(("l", location))
    if jobage:
        params.append(("date", str(int(jobage))))
    params.append(("radius", "25"))
    return f"https://{country}.talent.com/jobs?{urlencode(params)}"


def parse_listing(page_html, today, country):
    starts = [match for match in CARD_RE.finditer(page_html)]
    rows, seen = [], set()
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(page_html)
        block = page_html[match.start():end]
        ident = match.group(1)
        if ident in seen:
            continue
        seen.add(ident)
        title_tag = re.search(r"<h2[^>]*class=\"[^\"]*JobCard_title[^\"]*\"[^>]*>(.*?)</h2>", block, re.S)
        title = clean(title_tag.group(1)) if title_tag else None
        if not title:
            continue
        company = re.search(r"<span[^>]*class=\"[^\"]*JobCard_company[^\"]*\"[^>]*>(.*?)</span>", block, re.S)
        place = re.search(r"<span[^>]*class=\"[^\"]*JobCard_location[^\"]*\"[^>]*>(.*?)</span>", block, re.S)
        stamp = re.search(r"<time[^>]*class=\"[^\"]*JobCard_timeText[^\"]*\"[^>]*\bdatetime=\"([^\"]+)\"",
                          block, re.I)
        day = None
        if stamp:
            day = iso_day(stamp.group(1))
        if day is None:
            age = re.search(r"<time[^>]*class=\"[^\"]*JobCard_timeText[^\"]*\"[^>]*>(.*?)</time>", block, re.S)
            parsed = parse_age(age.group(1), today) if age else None
            day = parsed.isoformat() if parsed else None
        url = portal_url(f"https://{country}.talent.com/view?id={ident}")
        if not url:
            continue  # the market did not give an https address on this portal's host
        rows.append({
            "id": ident,
            "title": title,
            "company": clean(company.group(1)) if company else None,
            "location": clean(place.group(1)) if place else None,
            "date": day,
            "url": url,
            "portal": PORTAL,
        })
    return rows


def cmd_search(ns):
    query = (ns.query or "").strip()
    if not query:
        raise CliError("BAD_ARG", "--query is required: the board's search needs keywords")
    if ns.limit < 1:
        raise CliError("BAD_ARG", "--limit must be a whole number of at least 1")
    limit = min(ns.limit, MAX_LIMIT)  # the page holds MAX_LIMIT cards; asking for more is clamped, not refused
    jobage = None
    if ns.jobage is not None:
        if ns.jobage < 1 or ns.jobage > 60:
            raise CliError("BAD_ARG", "--jobage must be a whole number of days between 1 and 60")
        jobage = ns.jobage
    today = parse_day(ns.today)
    ns.url = build_search_url(query, ns.location, jobage, ns.country)
    rows = parse_listing(read_page(ns, "listing"), today, ns.country)
    rows.sort(key=lambda row: row["date"] or "", reverse=True)  # newest first, undated last
    return {"meta": {"portal": PORTAL, "query": query, "location": clean(ns.location), "jobage": jobage,
                     "page": 1, "limit": limit, "count": min(len(rows), limit), "url": ns.url},
            "results": rows[:limit]}


# --- detail -------------------------------------------------------------------------------------------------------

def build_detail_url(target, country="co"):
    value = (target or "").strip()
    if re.match(r"^https?://", value, re.I):
        host = (urlparse(value).hostname or "").lower()
        if not (host == "talent.com" or host.endswith(".talent.com")):
            raise CliError("BAD_ID", f"{host or value} is not a talent.com host")
        query = urlparse(value).query
        found = re.search(r"(?:^|&)id=(\d+)", query)
        if not found:
            raise CliError("BAD_ID", "a talent.com job address carries ?id=<number>")
        # the board is https only, so an http address pasted by hand is read over https on the same address
        url = portal_url("https://" + value.split("://", 1)[1])
        if not url:
            raise CliError("BAD_ID", f"{value} is not a readable talent.com address")
        return url
    if re.fullmatch(r"\d{6,}", value):
        if not MARKET_RE.match(country or ""):
            raise CliError("BAD_ARG", f"--country must be a two-letter code, got {country!r}")
        url = portal_url(f"https://{country}.talent.com/view?id={value}")
        if not url:
            raise CliError("BAD_ARG", f"--country {country!r} does not give a talent.com address")
        return url
    raise CliError("BAD_ID", "detail needs a numeric job id or a talent.com view URL")


def _first(mapping, *path, default=None):
    value = mapping
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return value if value not in (None, "") else default


def find_job_posting(page_html):
    for match in re.finditer(r"(?is)<script[^>]*application/ld\+json[^>]*>(.*?)</script>", page_html):
        try:
            document = json.loads(match.group(1).strip())
        except ValueError:
            continue
        found = _walk_job_posting(document)
        if found:
            return found
    return None


def _walk_job_posting(node):
    if isinstance(node, dict):
        kind = node.get("@type")
        if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
            return node
        for value in node.values():
            found = _walk_job_posting(value)
            if found:
                return found
    elif isinstance(node, list):
        for value in node:
            found = _walk_job_posting(value)
            if found:
                return found
    return None


def place_text(address):
    locality = clean(address.get("addressLocality"))
    region = clean(address.get("addressRegion"))
    country = clean(address.get("addressCountry"))
    country_name = COUNTRY_NAMES.get(str(country or "").lower(), country)
    parts = [part for part in (locality, country_name) if part]
    if not parts and region:
        parts = [region]
    return ", ".join(parts) or None


def description_block(page_html):
    """The visible description container on a posting page that carries no JSON-LD."""
    marker = re.search(r'class="[^"]*styles_jobInfoContent[^"]*"[^>]*>', page_html, re.I)
    if not marker:
        return None
    end = page_html.find("</article>", marker.end())
    segment = page_html[marker.end(): end if end != -1 else marker.end() + 20000]
    return html_to_text(segment)


def page_heading(page_html):
    """(title, company, place) from the page's <title>: 'Title – Company – Oferta de trabajo Place'."""
    tag = re.search(r"(?is)<title>(.*?)</title>", page_html)
    if not tag:
        return None, None, None
    parts = [part for part in (clean(piece) for piece in re.split(r"\s+[–—-]\s+", clean(tag.group(1)) or ""))
             if part]
    if not parts:
        return None, None, None
    if len(parts) == 1:
        return parts[0], None, None
    tail = parts[-1]
    if not tail.lower().startswith("oferta de trabajo"):
        return " – ".join(parts[:-1]), parts[-1], None
    place = clean(re.sub(r"(?i)^oferta de trabajo\s*", "", tail))
    rest = parts[:-1]
    if len(rest) == 1:
        return rest[0], None, place
    return " – ".join(rest[:-1]), rest[-1], place


def fallback_detail(page_html, url):
    """A posting page without JobPosting (stale offers) still shows its heading and body. Read those, and say so."""
    title, company, place = page_heading(page_html)
    description = description_block(page_html)
    if not title and not description:
        return None
    return {
        "id": offer_id(url) or url,
        "title": title,
        "company": company,
        "location": place,
        "date": None,
        "url": url,
        "portal": PORTAL,
        "description": description,
        "details": {"structured_data": False},
    }


def parse_detail(page_html, url):
    posting = find_job_posting(page_html)
    if not posting:
        job = fallback_detail(page_html, url)
        if job:
            if not job["description"]:
                raise CliError("NOT_FOUND", "the page carries no readable description; the offer has closed")
            return job
        raise CliError("NOT_FOUND", "the page carries no JobPosting; the offer may have closed")
    address = _first(posting, "jobLocation", "address", default={}) or {}
    ident = numeric_id(_first(posting, "identifier", "value")) or offer_id(url)
    if not ident:
        raise CliError("BAD_ID", "the page carries no numeric job id; detail needs one for a view address")
    row = {
        "id": ident,
        "title": clean(posting.get("title")),
        "company": clean(_first(posting, "hiringOrganization", "name")),
        "location": place_text(address),
        "date": iso_day(posting.get("datePosted")),
        "url": portal_url(posting.get("url"), base=url) or url,
        "portal": PORTAL,
        "description": html_to_text(posting.get("description")),
        "details": {
            "structured_data": True,
            "employment_type": clean(posting.get("employmentType")),
            "valid_through": iso_day(posting.get("validThrough")),
            "industry": clean(posting.get("industry")),
            "job_location_type": clean(posting.get("jobLocationType")),
            "occupational_category": clean(posting.get("occupationalCategory")),
        },
    }
    if str(row["details"]["job_location_type"] or "").upper() == "TELECOMMUTE":
        row["work_mode"] = "remote"
    return row


def cmd_detail(ns):
    ns.url = build_detail_url(ns.target, ns.country)
    job = parse_detail(read_page(ns, "detail"), ns.url)
    if not job["title"]:
        raise CliError("NOT_FOUND", "the page carries no job title; the offer may have closed")
    return job


# --- entry point --------------------------------------------------------------------------------------------------

def build_parser():
    parser = _Parser(
        prog="cli.py",
        description="talent.com Colombia portal CLI. Prints JSON on stdout; errors are JSON on stderr.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=("Offline: TALENT_FIXTURE_DIR (or --fixture-dir) names a directory holding listing.html and\n"
                "detail.html; the CLI reads those instead of the network."),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="{search,detail}")

    search = sub.add_parser("search", help="one listing page")
    search.add_argument("--query", "-q", help="keywords, e.g. 'analista de datos'")
    search.add_argument("--location", "-l", help="place, e.g. 'Bogota'")
    search.add_argument("--jobage", type=int, help="posted within N days (1 = last 24 hours)")
    search.add_argument("--limit", type=int, default=20, help="rows to print (default 20, at most 100)")
    search.add_argument("--country", default="co", help="market subdomain, two letters (default co)")
    search.add_argument("--today", help="YYYY-MM-DD used for relative ages (default: today)")
    search.add_argument("--fixture-dir", help="read captured HTML from this directory instead of the network")
    search.add_argument("--format", choices=["json"], default="json", help="output format (json)")
    search.set_defaults(func=cmd_search)

    detail = sub.add_parser("detail", help="one offer by id or URL")
    detail.add_argument("target", help="numeric job id, or a talent.com view URL")
    detail.add_argument("--country", default="co", help="market used for a bare id (default co)")
    detail.add_argument("--fixture-dir", help="read captured HTML from this directory instead of the network")
    detail.add_argument("--format", choices=["json"], default="json", help="output format (json)")
    detail.set_defaults(func=cmd_detail)
    return parser


def main(argv=None):
    ns = build_parser().parse_args(argv)
    try:
        emit(ns.func(ns))
        return 0
    except CliError as exc:
        return fail(str(exc), exc.code)
    except KeyboardInterrupt:
        return fail("interrupted", "INTERRUPTED")
    except Exception as exc:  # noqa: BLE001 - the contract wants JSON on stderr, never a traceback
        return fail(f"{type(exc).__name__}: {exc}", "INTERNAL_ERROR")


if __name__ == "__main__":
    sys.exit(main())
