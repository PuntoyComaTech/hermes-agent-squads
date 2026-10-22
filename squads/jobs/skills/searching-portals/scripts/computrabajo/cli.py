#!/usr/bin/env python3
"""Computrabajo Colombia: job listing and one offer, as JSON, on the standard library only.

  cli.py search --query "analista de datos" [--location "Bogota"] [--jobage 1] [--limit 5] [--page 1]
                [--country co] [--today 2026-10-22] [--fixture-dir DIR] --format json
  cli.py detail <offer url> [--fixture-dir DIR] --format json

One HTTP GET per page: the listing carries every row. `--jobage N` maps to the board's `pubdate=N` window
(1 = last 24 hours). `--today` fixes the day relative ages ("Hace 2 horas", "Ayer") are counted back from.

Offline: COMPUTRABAJO_FIXTURE_DIR (or --fixture-dir) points at a directory holding `listing.html`,
`listing-p<N>.html` and `detail.html`; the CLI then reads those files and never opens a socket.
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
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

PORTAL = "computrabajo"
USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
ACCEPT_LANGUAGE = "es-CO,es;q=0.9"
TIMEOUT_S = 25
RETRY_SLEEP_S = 2
MARKET_RE = re.compile(r"^[a-z]{2}$")
CARD_START_RE = re.compile(r"<article\b[^>]*class=\"[^\"]*\bbox_offer\b[^\"]*\"[^>]*>", re.I)
BLOCK_END_RE = re.compile(r"(?i)<\s*(?:br|/p|/div|/li|/h[1-6]|/tr|/section)\s*/?>")
SPACES_RE = re.compile(r"[ \t\u00a0]+")
AGE_RE = re.compile(
    r"hace\s+(m[aá]s\s+de\s+)?(\d+)?\s*(minuto|hora|d[ií]a|semana|mes|a[nñ]o)", re.I)
TAG_RE = re.compile(r"<[^>]*>")
CONTROL_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
CONTROL_KEEP_NL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
BIDI_RE = re.compile("[\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff]")
MAX_LIMIT = 100  # the page ceiling: a larger --limit is clamped here, never passed through
URL_HOSTS = ("computrabajo.com",)  # this portal's url_hosts in portal.json


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


def company_name(value):
    """The company as the board states it. A label such as 'Empresa confidencial' is kept: it is the board's own
    answer that the employer is hidden, not missing text."""
    return clean(value)


def slug(text, drop_dots=False):
    """The board's URL word: lowercase, accent-free, dashes for punctuation."""
    value = str(text or "").strip().lower()
    if drop_dots:
        value = value.replace(".", "")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


def parse_day(value):
    if value is None:
        return dt.date.today()
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise CliError("BAD_ARG", f"--today must be YYYY-MM-DD, got {value!r}")


def normalize_date(value):
    """The board writes dates as 2026-9-4 as well as 2026-09-04; both become YYYY-MM-DD."""
    text = clean(value)
    if not text:
        return None
    found = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if not found:
        return None
    year, month, day = (int(part) for part in found.groups())
    try:
        return dt.date(year, month, day).isoformat()
    except ValueError:
        return None


def host_matches(host, hosts):
    host = (host or "").lower()
    return any(host == entry or host.endswith("." + entry) for entry in hosts)


def portal_url(value, base=None):
    """An https URL on this portal's own hosts, or None.

    The listing links to employers, to the candidate site and sometimes to `javascript:`. Only an https address on
    url_hosts is a result this CLI may print, so anything else is dropped rather than passed through.
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
    return ns.fixture_dir or os.environ.get("COMPUTRABAJO_FIXTURE_DIR") or ""


def read_page(ns, kind, page=1):
    """One listing (or detail) document: from the fixture directory when one is set, else one GET."""
    directory = fixture_dir(ns)
    if directory:
        name = "listing.html" if page == 1 else f"listing-p{page}.html"
        if kind == "detail":
            name = "detail.html"
        path = Path(directory) / name
        if not path.is_file():
            raise CliError("FIXTURE_MISSING", f"no {name} in the fixture directory {directory}")
        return path.read_text(encoding="utf-8", errors="replace")
    return _get(ns.url)


# --- search -------------------------------------------------------------------------------------------------------

def build_search_url(query, location=None, jobage=None, page=1, country="co"):
    if not MARKET_RE.match(country or ""):
        raise CliError("BAD_ARG", f"--country must be a two-letter code, got {country!r}")
    words = slug(query)
    if not words:
        raise CliError("BAD_ARG", f"--query {query!r} has no letters or digits the board's address can use")
    path = f"/trabajo-de-{words}"
    place = slug(location, drop_dots=True) if location else ""
    if place:
        path += f"-en-{place}"
    params = []
    if jobage:
        params.append(f"pubdate={int(jobage)}")
    if page and page > 1:
        params.append(f"p={int(page)}")
    query_string = "&".join(params)
    return f"https://{country}.computrabajo.com{path}" + (f"?{query_string}" if query_string else "")


def card_id(opening_tag):
    found = re.search(r"data-id=['\"]([^'\"]+)['\"]", opening_tag)
    if found:
        return found.group(1)
    found = re.search(r"\bid=['\"]([^'\"]+)['\"]", opening_tag)
    return found.group(1) if found else None


def parse_listing(page_html, today, base):
    starts = [match.start() for match in CARD_START_RE.finditer(page_html)]
    rows, seen = [], set()
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(page_html)
        block = page_html[start:end]
        opening_match = CARD_START_RE.match(block)
        if not opening_match:
            continue
        opening = opening_match.group(0)
        link = re.search(r"<a[^>]*class=\"[^\"]*js-o-link[^\"]*\"[^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>",
                         block, re.S)
        if not link:
            continue
        href, title = link.group(1), clean(link.group(2))
        if not title:
            continue
        url = portal_url(html.unescape(href).split("#")[0], base=base + "/")
        if not url:
            continue  # a link the board anchors off its own https host is not a result
        card_key = card_id(opening) or url
        if card_key in seen:
            continue
        seen.add(card_key)
        company = re.search(r"<a[^>]*class=\"[^\"]*\bt_ellipsis\b[^\"]*\"[^>]*>(.*?)</a>", block, re.S)
        place = re.search(
            r"<p[^>]*class=\"fs16 fc_base mt5\"[^>]*>\s*<span[^>]*class=\"mr10\"[^>]*>(.*?)</span>", block, re.S)
        age = re.search(r"<p[^>]*class=\"[^\"]*\bfc_aux\b[^\"]*\"[^>]*>(.*?)</p>", block, re.S)
        day = parse_age(age.group(1), today) if age else None
        rows.append({
            "id": url,
            "title": title,
            "company": company_name(company.group(1)) if company else None,
            "location": clean(place.group(1)) if place else None,
            "date": day.isoformat() if day else None,
            "url": url,
            "portal": PORTAL,
        })
    return rows


def cmd_search(ns):
    query = (ns.query or "").strip()
    if not query:
        raise CliError("BAD_ARG", "--query is required: the listing address is built from it")
    if ns.limit < 1:
        raise CliError("BAD_ARG", "--limit must be a whole number of at least 1")
    limit = min(ns.limit, MAX_LIMIT)  # a page holds MAX_LIMIT rows; asking for more is clamped, not refused
    if ns.page < 1:
        raise CliError("BAD_ARG", "--page must be 1 or more")
    jobage = None
    if ns.jobage is not None:
        if ns.jobage < 1 or ns.jobage > 60:
            raise CliError("BAD_ARG", "--jobage must be a whole number of days between 1 and 60")
        jobage = ns.jobage
    today = parse_day(ns.today)
    ns.url = build_search_url(query, ns.location, jobage, ns.page, ns.country)
    rows = parse_listing(read_page(ns, "listing", ns.page), today, ns.url)
    rows.sort(key=lambda row: row["date"] or "", reverse=True)  # newest first, undated last
    return {"meta": {"portal": PORTAL, "query": query, "location": clean(ns.location), "jobage": jobage,
                     "page": ns.page, "limit": limit, "count": min(len(rows), limit), "url": ns.url},
            "results": rows[:limit]}


# --- detail -------------------------------------------------------------------------------------------------------

def build_detail_url(target):
    value = (target or "").strip()
    if re.match(r"^https?://", value, re.I):
        host = (urlparse(value).hostname or "").lower()
        if not (host == "computrabajo.com" or host.endswith(".computrabajo.com")):
            raise CliError("BAD_ID", f"{host or value} is not a Computrabajo host")
        # the board is https only, so an http address pasted by hand is read over https on the same address
        url = portal_url("https://" + value.split("://", 1)[1])
        if not url:
            raise CliError("BAD_ID", f"{value} is not a readable Computrabajo address")
        return url
    if re.fullmatch(r"[0-9A-Fa-f]{32}", value):
        raise CliError("BAD_ID", "this offer id has no page of its own; pass the offer URL")
    raise CliError("BAD_ID", "detail needs a Computrabajo offer URL")


def _first(mapping, *path, default=None):
    value = mapping
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return value if value not in (None, "") else default


def salary_text(salary):
    if not isinstance(salary, dict):
        return None
    amount = _first(salary, "value", "value")
    currency = salary.get("currency")
    unit = _first(salary, "value", "unitText")
    if amount is None or isinstance(amount, (dict, list)):
        return None
    try:
        amount_text = f"{int(float(amount)):,}".replace(",", ".")
    except (TypeError, ValueError):
        amount_text = str(amount)
    parts = [str(currency)] if currency else []
    parts.append(amount_text)
    if isinstance(unit, str) and unit.upper() == "MONTH":
        parts.append("(mensual)")
    elif isinstance(unit, str) and unit.upper() == "YEAR":
        parts.append("(anual)")
    return " ".join(parts) or None


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


def parse_detail(page_html, url=None):
    posting = find_job_posting(page_html)
    if not posting:
        raise CliError("NOT_FOUND", "the page carries no JobPosting; the offer may have closed")
    address = _first(posting, "jobLocation", "address", default={}) or {}
    locality = clean(address.get("addressLocality"))
    region = clean(address.get("addressRegion"))
    location = locality or region
    if locality and region and region != locality:
        location = f"{locality}, {region}"
    # The JSON-LD url may point at an employer's site or be a `javascript:` href: only an https address on this
    # portal's own host is printed, and the offer that was asked for is the fallback.
    offer_url = portal_url(posting.get("url"), base=url)
    return {
        "id": offer_url or url,
        "title": clean(posting.get("title")),
        "company": company_name(_first(posting, "hiringOrganization", "name")),
        "location": location,
        "date": normalize_date(posting.get("datePosted")),
        "url": offer_url or url,
        "portal": PORTAL,
        "description": html_to_text(posting.get("description")),
        "details": {
            "employment_type": clean(posting.get("employmentType")),
            "valid_through": normalize_date(posting.get("validThrough")),
            "salary": salary_text(posting.get("baseSalary")),
            "direct_apply": posting.get("directApply"),
            "industry": clean(posting.get("industry")),
            "job_location_type": clean(posting.get("jobLocationType")),
        },
    }


def cmd_detail(ns):
    ns.url = build_detail_url(ns.target)
    job = parse_detail(read_page(ns, "detail"), ns.url)
    if not job["title"]:
        raise CliError("NOT_FOUND", "the page carries no job title; the offer may have closed")
    job["id"] = job["id"] or ns.url
    job["url"] = job["url"] or ns.url
    return job


# --- entry point --------------------------------------------------------------------------------------------------

def build_parser():
    parser = _Parser(
        prog="cli.py",
        description="Computrabajo Colombia portal CLI. Prints JSON on stdout; errors are JSON on stderr.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=("Offline: COMPUTRABAJO_FIXTURE_DIR (or --fixture-dir) names a directory holding listing.html,\n"
                "listing-p<N>.html and detail.html; the CLI reads those instead of the network."),
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="{search,detail}")

    search = sub.add_parser("search", help="one listing page")
    search.add_argument("--query", "-q", help="keywords, e.g. 'analista de datos'")
    search.add_argument("--location", "-l", help="place, e.g. 'Bogota'")
    search.add_argument("--jobage", type=int, help="posted within N days (1 = last 24 hours)")
    search.add_argument("--limit", type=int, default=20, help="rows to print (default 20)")
    search.add_argument("--page", type=int, default=1, help="1-indexed page")
    search.add_argument("--country", default="co", help="market subdomain, two letters (default co)")
    search.add_argument("--today", help="YYYY-MM-DD used for relative ages (default: today)")
    search.add_argument("--fixture-dir", help="read captured HTML from this directory instead of the network")
    search.add_argument("--format", choices=["json"], default="json", help="output format (json)")
    search.set_defaults(func=cmd_search)

    detail = sub.add_parser("detail", help="one offer by its URL")
    detail.add_argument("target", help="offer URL on a computrabajo.com host")
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
