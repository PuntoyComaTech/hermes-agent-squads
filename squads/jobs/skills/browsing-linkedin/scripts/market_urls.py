#!/usr/bin/env python3
"""Builds, checks and budgets the one LinkedIn page the jobs scout may open: the hiring-posts search.

Job listings are not read in the browser: the public portal tool (`searching-portals`, guest endpoints, its own
jobage window) is the only source of them. What the shared signed-in browser adds is the hiring-posts search, which
is what people write when they are hiring. This tool is the only place that URL is written, so it always carries the
Boolean string, the recency window and the newest-first sort, and it refuses every other LinkedIn page before one is
opened.

Usage:
  market_urls.py posts  --any T [--any T ...] [--all T ...] [--not T ...] [--window past-24h|past-week]
  market_urls.py check  URL
  market_urls.py budget --file FILE --kind posts --run RUN_ID [--date YYYY-MM-DD] [--peek]

Each term is one phrase. `--any` terms are OR-ed inside one group, `--all` terms are AND-ed, `--not` terms are
excluded. The operators AND, OR and NOT are written in capitals by this tool; a term may not be an operator word.
Output is one JSON object on stdout. `check` exits 0 only for `allowed` and 1 for every other verdict, including a
page that is not LinkedIn; `budget` exits 1 when a cap is reached; a malformed argument exits 2 with {"error", "code"}
on stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import posixpath
import re
import sys
from urllib.parse import parse_qs, quote, unquote, urlsplit

MAX_QUERY = 256
MAX_TERM = 60
OPERATORS = {"and", "or", "not"}
POST_WINDOWS = ("past-24h", "past-week")

# Caps per calendar day and per run. They keep the volume of a person browsing by hand; they are not options.
DAY_CAPS = {"posts": 6}
RUN_CAPS = {"posts": 2}


class UsageError(ValueError):
    def __init__(self, message, code="BAD_ARG"):
        super().__init__(message)
        self.code = code


# --- Boolean strings -------------------------------------------------------------------------------------------------

def clean_term(raw) -> str:
    term = re.sub(r"\s+", " ", str(raw).replace('"', " ")).strip()
    if not term:
        raise UsageError("a search term is empty")
    if len(term) > MAX_TERM:
        raise UsageError(f"term {term[:20]!r}... is longer than {MAX_TERM} characters")
    if re.search(r"[()]", term):
        raise UsageError(f"term {term!r} holds a parenthesis; write one plain phrase per term")
    if term.lower() in OPERATORS:
        raise UsageError(f"term {term!r} is a Boolean operator word, not a phrase")
    return term


def group(terms: list[str]) -> str:
    quoted = [f'"{t}"' for t in terms]
    return quoted[0] if len(quoted) == 1 else "(" + " OR ".join(quoted) + ")"


def boolean(any_terms, all_terms, not_terms) -> str:
    anys = list(dict.fromkeys(clean_term(t) for t in any_terms or []))
    alls = list(dict.fromkeys(clean_term(t) for t in all_terms or []))
    nots = list(dict.fromkeys(clean_term(t) for t in not_terms or []))
    if not anys and not alls:
        raise UsageError("give at least one --any or --all term")
    parts = ([group(anys)] if anys else []) + [f'"{t}"' for t in alls]
    text = " AND ".join(parts)
    if nots:
        text += " NOT " + group(nots)
    if len(text) > MAX_QUERY:
        raise UsageError(f"the Boolean string is {len(text)} characters; LinkedIn reads up to {MAX_QUERY}. "
                         "Split it into two searches.")
    return text


def enc(value) -> str:
    return quote(str(value), safe="")


def build_posts(ns) -> dict:
    keywords = boolean(ns.any, ns.all, ns.not_)
    url = ("https://www.linkedin.com/search/results/content/?keywords=" + enc(keywords)
           + "&origin=FACETED_SEARCH"
           + "&sortBy=" + enc('"date_posted"') + "&datePosted=" + enc(f'"{ns.window}"'))
    return {"kind": "posts", "url": url, "keywords": keywords, "window": ns.window}


# --- the allowed surface --------------------------------------------------------------------------------------------

LINKEDIN_ALLOWED = (
    ("posts_search", re.compile(r"^/search/results/content/?$")),
)
LINKEDIN_REFUSED = (
    ("profile", re.compile(r"^/(in|pub|sales/people|talent/profile)/")),
    ("company_or_school", re.compile(r"^/(company|school|showcase)/")),
    ("messaging", re.compile(r"^/(messaging|inbox|mwlite/messaging)(/|$)")),
    ("network", re.compile(r"^/(mynetwork|connect|invitation-manager|groups|events)(/|$)")),
    ("account", re.compile(r"^/(settings|psettings|premium|help|notifications|me|learning|sales|talent)(/|$)")),
    ("jobs_search", re.compile(r"^/jobs/search")),
    ("jobs_page", re.compile(r"^/jobs/")),
    ("post_page", re.compile(r"^/(feed/update|posts)/")),
    ("login_wall", re.compile(r"^/(login|uas|checkpoint|authwall|signup|m/login)(/|$)")),
    ("feed", re.compile(r"^/(feed/?$|feed/(?!update/)|company-beta)")),
)


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def is_linkedin(host: str) -> bool:
    return host == "linkedin.com" or host.endswith(".linkedin.com")


def check_url(url: str) -> dict:
    """allowed for the one posts search; refused for everything else, including a page that is not LinkedIn at all.

    This runs before a navigation and again on `location.href` after it, so anything that is not `allowed` has to
    read as "do not read this page". A near-miss host (`linkedin.com.evil.example`), a user name in front of the real
    host (`https://www.linkedin.com:443@evil.example/`) and LinkedIn's own shortener all land there.
    """
    parts = urlsplit(str(url).strip())
    host = (parts.hostname or "").lower().rstrip(".")
    netloc = parts.netloc or ""
    path = posixpath.normpath(re.sub(r"/{2,}", "/", unquote(parts.path or "/"))) or "/"
    if path != "/" and unquote(parts.path or "/").endswith("/"):
        path += "/"
    if not path.startswith("/"):
        path = "/" + path
    base = {"url": url, "host": host, "path": path}
    if parts.scheme != "https":
        return {**base, "verdict": "refused", "reason": "not_https", "stop": False}
    if parts.username or parts.password or "\\" in netloc:
        return {**base, "verdict": "refused", "reason": "userinfo", "stop": True}
    if is_linkedin(host):
        for reason, rx in LINKEDIN_REFUSED:
            if rx.search(path.lower()):
                return {**base, "verdict": "refused", "reason": reason, "stop": reason == "login_wall"}
        for scope, rx in LINKEDIN_ALLOWED:
            if rx.match(path):
                if scope == "posts_search" and not parse_qs(parts.query).get("keywords"):
                    return {**base, "verdict": "refused", "reason": "posts_search_without_keywords", "stop": False}
                return {**base, "verdict": "allowed", "scope": scope}
        return {**base, "verdict": "refused", "reason": "not_an_allowed_surface", "stop": False}
    return {**base, "verdict": "refused", "reason": "not_linkedin", "stop": True,
            "note": "the page is not LinkedIn: go back and read nothing from it"}


# --- the daily and per-run budget -----------------------------------------------------------------------------------

def today() -> str:
    import datetime as dt
    return dt.date.today().isoformat()


def spend(path: str, kind: str, run: str, date: str, peek: bool) -> dict:
    state = {"schema": 1, "days": {}}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as handle:
                state = json.load(handle)
        except (OSError, ValueError) as exc:
            raise UsageError(f"{path} is not readable JSON ({exc}); move it aside, do not edit it by hand",
                             "BAD_STATE") from exc
    day = state.setdefault("days", {}).setdefault(date, {"total": {}, "runs": {}})
    used_day = int(day["total"].get(kind, 0))
    used_run = int(day["runs"].get(run, {}).get(kind, 0))
    allowed = used_day < DAY_CAPS[kind] and used_run < RUN_CAPS[kind]
    if allowed and not peek:
        day["total"][kind] = used_day + 1
        day["runs"].setdefault(run, {})[kind] = used_run + 1
        for old in sorted(state["days"])[:-14]:   # keep two weeks of history
            del state["days"][old]
        tmp = f"{path}.tmp{os.getpid()}"
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=1, sort_keys=True)
        os.replace(tmp, path)
        used_day, used_run = used_day + 1, used_run + 1
    return {"allowed": allowed, "kind": kind, "date": date, "run": run,
            "used_today": used_day, "cap_today": DAY_CAPS[kind], "used_run": used_run, "cap_run": RUN_CAPS[kind],
            **({} if allowed else {"code": "BUDGET_EXHAUSTED",
                                   "say": "Stop browsing for this run and say which cap was reached."})}


# --- command line ---------------------------------------------------------------------------------------------------

class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message)


def build_parser():
    p = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    s = sub.add_parser("posts")
    s.add_argument("--any", action="append", default=[])
    s.add_argument("--all", action="append", default=[])
    s.add_argument("--not", dest="not_", action="append", default=[])
    s.add_argument("--window", choices=POST_WINDOWS, default="past-24h")
    c = sub.add_parser("check")
    c.add_argument("url")
    b = sub.add_parser("budget")
    b.add_argument("--file", required=True)
    b.add_argument("--kind", required=True, choices=tuple(DAY_CAPS))
    b.add_argument("--run", required=True)
    b.add_argument("--date")
    b.add_argument("--peek", action="store_true", help="report the counters without spending")
    return p


def main(argv=None) -> int:
    try:
        ns = build_parser().parse_args(argv)
        if ns.cmd == "posts":
            out = build_posts(ns)
        elif ns.cmd == "check":
            out = check_url(ns.url)
        else:
            if not re.fullmatch(r"[A-Za-z0-9:_.-]{1,80}", ns.run):
                raise UsageError("--run is a short id such as the card id")
            out = spend(ns.file, ns.kind, ns.run, ns.date or today(), ns.peek)
    except UsageError as exc:
        sys.stderr.write(json.dumps({"error": str(exc), "code": exc.code}) + "\n")
        return 2
    print(json.dumps(out, ensure_ascii=False))
    if "verdict" in out and out["verdict"] != "allowed":
        return 1
    if out.get("allowed") is False:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
