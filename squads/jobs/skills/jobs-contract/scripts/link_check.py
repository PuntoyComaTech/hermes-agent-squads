#!/usr/bin/env python3
"""Classify a job link before any work is spent on it: verified, official_ats or unverified.

Pure classification on URL parsing. Nothing is fetched, resolved or opened, and no network is used. The reviewed
host and board data is official_hosts.json, next to this file.

Verdicts:
  verified      a listed ATS host, a board path, and the board is in reviewed_boards (https only).
  official_ats  a listed ATS host with a board path whose board is not reviewed yet, or a listed portal's posting
                page (the squad's own portal CLIs: read them through `portals.py detail`). The output lists the
                manual checks to do before any data is entered.
  job_board     a reviewed job board's posting page (job_boards in official_hosts.json: aggregators that are not
                employers). The board is recognised, but it is not the employer: the manual checks find the
                employer's own posting before any application.
  new_platform  a host the reviewed list does not name (an employer's own site, an ATS not listed yet) with no sign of
                fraud: applied to like any employer ATS, and named in the report.
  unverified    a sign of fraud: look-alike hosts, shorteners, forms, chat links, bare apex domains,
                IP literals, non-http(s) schemes, userinfo, non-ASCII or punycode hosts. The output carries
                anti-scam guidance. A flag is a fact about the link; a hard flag forces unverified. The soft flags
                (http_not_https, board_company_mismatch) only add a FLAG to a verdict.

Host patterns: an exact host, or `*.domain` for every subdomain of a domain (`*.linkedin.com` covers mx., br., co.,
cl., uk. and www.). The apex itself needs its own entry. A look-alike is a host that carries a listed brand name
inside a domain the list does not own (boards-greenhouse.io, linkedin.com.evil.example).

Usage:
  link_check.py URL [--company NAME] [--json]

Output: one verdict line, then its reasons and its checks or guidance. --json prints one object with the same
fields. Exit 0 for every classification (unverified included); exit 2 on a usage error.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jobs_common  # noqa: E402  - the squad's one slug fold, shared with job_key.py

DATA_FILE = HERE / "official_hosts.json"
MAX_LEN = 2048
ATS_SHAPES = ("path", "subdomain", "workday")
DATA_LISTS = ("ats", "portals", "job_boards", "shorteners", "forms", "messaging", "reviewed_boards")
SOFT_FLAGS = frozenset({"http_not_https", "board_company_mismatch"})
# A platform the reviewed list does not name yet, with no sign of fraud: the squad applies there like on any ATS and
# names the platform in its report. The list is a record of what was seen, never a gate.
NEW_PLATFORM_FLAGS = frozenset({"unknown_host", "unlisted_ats_host"})
SCHEME_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*):")
CONTROL_RE = re.compile(r"[\s\x00-\x1f\x7f]")
NUMERIC_HOST_RE = re.compile(r"^(?:[0-9.]+|(?:0x[0-9a-f]+\.?)+)$")
HOST_RE = re.compile(r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+$")
BOARD_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,99}$")
WORKDAY_LABEL_RE = re.compile(r"^([a-z0-9][a-z0-9-]{0,62})(?:\.wd[0-9]{1,3})?$")
LOCALE_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$", re.IGNORECASE)
LEGAL_WORDS = frozenset({
    "the", "inc", "corp", "corporation", "co", "company", "ltd", "limited", "llc", "gmbh", "sa", "sas", "srl",
    "plc", "ag", "bv", "nv", "oy", "ab", "as", "group", "holdings",
})

REASONS = {
    "empty": "no link given",
    "too_long": "the link is longer than {max} characters",
    "whitespace_or_control": "spaces or control characters inside the link",
    "invisible_char": "invisible formatting characters inside the link",
    "backslash": "a backslash: browsers and checkers can read the host differently",
    "no_scheme": "no http:// or https:// scheme",
    "scheme_not_http": "the scheme is not http or https",
    "no_authority": "no host after the scheme",
    "bad_port": "the port is not a valid number",
    "no_host": "no host",
    "userinfo": "text before '@' in the link; the real host is {host}",
    "unusual_port": "port {port} is not the default port",
    "ip_literal": "an IP address instead of a company domain",
    "non_ascii_host": "non-ASCII letters in the host: possible look-alike characters",
    "punycode_host": "a punycode host (xn--): a look-alike domain in disguise",
    "bad_host": "the host has characters outside a-z, 0-9, '.' and '-'",
    "shortener": "a URL shortener hides the real destination",
    "form": "a form, not a job posting",
    "messaging": "a chat link, not a job posting",
    "bare_apex": "the ATS domain itself, with no board",
    "unlisted_ats_host": "an ATS domain the reviewed list does not cover",
    "lookalike_host": "the host uses the name '{brand}' but is not a listed {brand} domain",
    "unknown_host": "the host is not on the reviewed ATS or portal list",
    "no_board_path": "no board name in the path",
    "reserved_board": "'{board}' is an ATS system path, not a board",
    "bad_board": "the board name has unexpected characters",
    "host_shape": "the host does not have this ATS's board address shape",
    "not_a_posting": "the link is not a posting page of this portal or job board",
    "http_not_https": "plain http: the link can be changed in transit",
    "board_company_mismatch": "board '{owner}' does not match company '{company}'",
    "official_hosts_unreadable": "the reviewed list is unreadable: nothing can be verified",
}
COMMON_GUIDANCE: tuple[str, ...] = (
    "Do not open, fill in, log in to or send documents through this link; the bots fetch no unverified link.",
    "Search the company name and open its own careers page: the same role must be listed there.",
    "A job that asks for a fee, bank details, an ID scan or chat-only contact is a scam: discard it (filter gate 1).",
)
KIND_GUIDANCE = {
    "shortener": "Expand it yourself in a browser and check the final host; the bots never follow short links.",
    "form": "A form is not a job posting: ask the user for the employer's posting text instead of filling it in.",
    "messaging": "A chat link is not a posting: ask the recruiter for the posting on the employer's own domain.",
}


class DataError(ValueError):
    """The reviewed list cannot be read; every link then stays unverified."""


# --- the reviewed list ------------------------------------------------------------------------------------------

def _pattern_hit(host, pattern):
    if pattern.startswith("*."):
        return host.endswith(pattern[1:])
    return host == pattern


def _host_hit(host, patterns):
    """True when the host is one of the exact names or inside one of the `*.domain` wildcards."""
    return any(_pattern_hit(host, pattern) for pattern in patterns)


def _board_rows(items, name):
    """Entries of portals or job_boards: id, brand, hosts and a case-insensitive path regex. Raises DataError."""
    rows = []
    for item in items:
        if not (isinstance(item, dict) and isinstance(item.get("hosts"), list) and item["hosts"]
                and all(isinstance(h, str) and h for h in item["hosts"])):
            raise DataError(f"{name}: each entry needs id, brand, hosts and a path regex")
        try:
            rows.append({
                "id": item["id"], "brand": item["brand"].lower(),
                "hosts": [h.lower() for h in item["hosts"]], "path_re": re.compile(item["path"], re.IGNORECASE),
            })
        except (KeyError, TypeError, AttributeError, re.error):
            raise DataError(f"{name}: each entry needs id, brand, hosts and a path regex") from None
    return rows


def _rules(entries, name):
    out = []
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("host"), str) or not item["host"]:
            raise DataError(f"{name}: each entry needs a host")
        out.append({"host": item["host"].lower(), "path_prefix": str(item.get("path_prefix") or "/").lower()})
    return out


def load_data(path=DATA_FILE):
    """The parsed reviewed list. Raises DataError when the file or its shape is broken (fail safe)."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise DataError(f"{Path(path).name} is unreadable ({type(exc).__name__})") from None
    if not isinstance(raw, dict) or any(not isinstance(raw.get(key), list) for key in DATA_LISTS):
        raise DataError(f"{Path(path).name}: expected the lists {', '.join(DATA_LISTS)}")
    ats = []
    for item in raw["ats"]:
        if not (isinstance(item, dict) and isinstance(item.get("id"), str) and isinstance(item.get("brand"), str)
                and item.get("shape") in ATS_SHAPES and isinstance(item.get("hosts"), list) and item["hosts"]
                and all(isinstance(h, str) and h for h in item["hosts"])):
            raise DataError("ats: each entry needs id, brand, shape and hosts")
        ats.append({
            "id": item["id"], "brand": item["brand"].lower(), "shape": item["shape"],
            "hosts": [h.lower() for h in item["hosts"]],
            "reserved": [str(r).lower() for r in item.get("reserved") or []],
            "path_prefix": str(item.get("path_prefix") or "").lower(),
        })
    portals = _board_rows(raw["portals"], "portals")
    job_boards = _board_rows(raw["job_boards"], "job_boards")
    apex = {}
    for entry in ats:
        for pattern in entry["hosts"]:
            base = pattern[2:] if pattern.startswith("*.") else pattern
            apex[".".join(base.split(".")[-2:])] = entry["id"]
    data = {
        "ats": ats, "portals": portals, "job_boards": job_boards, "apex": apex,
        "brands": sorted({e["brand"] for e in ats} | {p["brand"] for p in portals + job_boards}),
        # every listed registrable domain with its brand, for look-alikes that embed a whole domain
        "domains": sorted({(".".join((h[2:] if h.startswith("*.") else h).split(".")[-2:]), e["brand"])
                           for e in ats + portals + job_boards for h in e["hosts"]}),
        "shorteners": _rules(raw["shorteners"], "shorteners"),
        "forms": _rules(raw["forms"], "forms"),
        "messaging": _rules(raw["messaging"], "messaging"),
        "reviewed": set(), "warnings": [],
    }
    for item in raw["reviewed_boards"]:
        url = item.get("url") if isinstance(item, dict) else None
        found = analyze(url, data)
        # Only the board itself counts: a reviewed entry with a posting path would bless every posting under it.
        exact = bool(found["board_url"]) and _same_board_url(url, found["board_url"])
        if exact and found["board_key"] and not [f for f in found["flags"] if f not in SOFT_FLAGS]:
            data["reviewed"].add(found["board_key"])
        else:
            data["warnings"].append(f"reviewed_boards entry ignored (needs the https board URL alone): {url!r}")
    return data


# --- analysis -----------------------------------------------------------------------------------------------------

def _blank(raw):
    return {
        "url": raw if isinstance(raw, str) else "", "scheme": None, "host": None, "port": None, "kind": None,
        "ats": None, "brand": None, "board": None, "owner": None, "board_url": None, "board_key": None, "flags": [],
    }


def _ats_entry(host, entries):
    """(entry, suffix): an exact host first, then a wildcard host; suffix is the wildcard's domain or None."""
    for entry in entries:
        if host in [h for h in entry["hosts"] if not h.startswith("*.")]:
            return entry, None
    for entry in entries:
        for pattern in entry["hosts"]:
            if pattern.startswith("*.") and host.endswith(pattern[1:]):
                return entry, pattern[2:]
    return None, None


def _same_board_url(url, board_url):
    """True when a reviewed URL is exactly the board URL: https, same host, same path, no query or fragment."""
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    given, expected = urlsplit(url.strip()), urlsplit(board_url)
    return (given.netloc.lower() == expected.netloc and given.path.rstrip("/").lower() == expected.path.lower()
            and not given.query and not given.fragment)


def _brand_in(host, brands, domains=()):
    """The listed brand an unlisted host borrows: a brand word among its labels (boards-greenhouse.io), or a whole
    listed domain inside it (careers-page.com.jobs-offer.example, which splits the hyphenated brand apart)."""
    tokens = set(re.split(r"[.\-_]", host))
    hit = next((brand for brand in brands if brand in tokens or brand in host.split(".")), None)
    if hit:
        return hit
    for domain, brand in domains:
        if host == domain or host.endswith("." + domain):
            continue
        if re.search(r"(?:^|[.-])" + re.escape(domain) + r"(?:[.-]|$)", host):
            return brand
    return None


def _ats_board(st, entry, suffix, host, path):
    """Board shape for one ATS host: sets board, owner, board_url and board_key, or adds the problem flag."""
    st["ats"], st["kind"], st["brand"] = entry["id"], "ats", entry["brand"]
    segs = [s for s in path.split("/") if s]
    problem, board, owner, board_url = None, "", "", None
    if entry["shape"] == "path":
        # a path ATS may keep its boards under a fixed prefix (Dover: app.dover.com/apply/<board>/<posting>)
        pre = [x for x in entry["path_prefix"].split("/") if x]
        if pre and [x.lower() for x in segs[: len(pre)]] != pre:
            problem = "no_board_path"
        rest = segs[len(pre):] if pre else segs
        board = unquote(rest[0]) if rest else ""
        owner = board
        board_url = f"https://{host}/{'/'.join(pre + [rest[0]])}" if rest else None
    elif suffix is None:
        problem = "host_shape"
    elif entry["shape"] == "subdomain":
        label = host[: -(len(suffix) + 1)]
        prefix, lowered = entry["path_prefix"], path.lower()
        board = owner = label
        board_url = f"https://{host}{prefix}"
        if "." in label:
            problem = "host_shape"
        elif prefix and lowered != prefix and not lowered.startswith(prefix + "/"):
            problem = "no_board_path"
    else:  # workday: <tenant>[.wdN].myworkdayjobs.com/[<locale>/]<site>/...
        found = WORKDAY_LABEL_RE.match(host[: -(len(suffix) + 1)])
        if not found:
            problem = "host_shape"
        else:
            if len(segs) > 1 and LOCALE_RE.match(segs[0]):
                segs = segs[1:]
            board = segs[0] if segs else ""
            owner = found.group(1)
            board_url = f"https://{host}/{board}" if board else None
    if problem is None:
        if not board:
            problem = "no_board_path"
        elif board.lower() in entry["reserved"]:
            problem = "reserved_board"
        elif not BOARD_RE.match(board):
            problem = "bad_board"
    st["board"], st["owner"], st["board_url"] = board.lower() or None, owner.lower() or None, board_url
    if problem:
        st["flags"].append(problem)
    else:
        st["board_key"] = f"{entry['id']}|{host}|{board.lower()}"


def analyze(raw, data):
    """Every fact about one link, from its text alone. Never raises; a flag names each problem found."""
    st = _blank(raw)
    flags = st["flags"]
    text = raw.strip() if isinstance(raw, str) else ""
    if not text:
        flags.append("empty")
        return st
    if len(text) > MAX_LEN:
        flags.append("too_long")
        return st
    if CONTROL_RE.search(text):
        flags.append("whitespace_or_control")
    if any(unicodedata.category(ch) == "Cf" for ch in text):
        flags.append("invisible_char")
    if "\\" in text:
        flags.append("backslash")
    scheme_match = SCHEME_RE.match(text)
    if not scheme_match:
        flags.append("no_scheme")
        return st
    scheme = scheme_match.group(1).lower()
    if scheme not in ("http", "https"):
        flags.append("scheme_not_http")
        return st
    st["scheme"] = scheme
    if scheme == "http":
        flags.append("http_not_https")
    if not text[scheme_match.end():].startswith("//"):
        flags.append("no_authority")
        return st
    try:
        parts = urlsplit(text)
        port = parts.port
    except ValueError:
        flags.append("bad_port")
        return st
    host = (parts.hostname or "").rstrip(".")
    if not host:
        flags.append("no_host")
        return st
    st["host"], st["port"] = host, port
    if "@" in parts.netloc:
        flags.append("userinfo")
    if port not in (None, 80, 443):
        flags.append("unusual_port")
    if ":" in host or NUMERIC_HOST_RE.match(host):
        flags.append("ip_literal")
        return st
    if not host.isascii():
        flags.append("non_ascii_host")
        return st
    if any(label.startswith("xn--") for label in host.split(".")):
        flags.append("punycode_host")
        return st
    if not HOST_RE.match(host):
        flags.append("bad_host")
        return st
    path = parts.path or "/"
    if any(_pattern_hit(host, r["host"]) for r in data["shorteners"]):
        st["kind"] = "shortener"
        flags.append("shortener")
        return st
    if any(_pattern_hit(host, r["host"]) and path.lower().startswith(r["path_prefix"]) for r in data["forms"]):
        st["kind"] = "form"
        flags.append("form")
        return st
    if any(_pattern_hit(host, r["host"]) for r in data["messaging"]):
        st["kind"] = "messaging"
        flags.append("messaging")
        return st
    entry, suffix = _ats_entry(host, data["ats"])
    if entry:
        _ats_board(st, entry, suffix, host, path)
        return st
    for kind, rows in (("portal", data["portals"]), ("job_board", data["job_boards"])):
        for row in rows:
            if _host_hit(host, row["hosts"]):
                st["kind"], st["ats"], st["brand"] = kind, row["id"], row["brand"]
                if not row["path_re"].search(path):
                    flags.append("not_a_posting")
                return st
    last_two = ".".join(host.split(".")[-2:])
    if host in data["apex"]:
        st["kind"], st["ats"] = "ats", data["apex"][host]
        flags.append("bare_apex")
        return st
    if last_two in data["apex"]:
        st["kind"], st["ats"] = "ats", data["apex"][last_two]
        flags.append("unlisted_ats_host")
        return st
    brand = _brand_in(host, data["brands"], data["domains"])
    if brand:
        st["brand"] = brand
        flags.append("lookalike_host")
    else:
        flags.append("unknown_host")
    st["kind"] = "unknown"
    return st


# --- verdict ------------------------------------------------------------------------------------------------------

def company_matches(company, owner):
    """True or False for a company name against a board owner; None when either has no Latin letters."""
    left, right = _squash(company), _squash(owner)
    if not left or not right:
        return None
    if left == right:
        return True
    if min(len(left), len(right)) >= 3 and (left in right or right in left):
        return True
    return difflib.SequenceMatcher(None, left, right).ratio() >= 0.75


def _squash(name):
    words = jobs_common.slugify(name, limit=200).split("-")
    return "".join(word for word in words if word and word not in LEGAL_WORDS)


def _manual_checks(st):
    if st["kind"] == "unknown" or "unlisted_ats_host" in st["flags"]:
        return [f"A platform not on the reviewed list ({st['host']}): apply as on any employer ATS and name it in the "
                "report, so the user sees it and it can be added to official_hosts.json."]
    if st["kind"] in ("portal", "job_board"):
        return ["A portal or job board listing is not the employer's page: find the employer's own posting by "
                "searching the company name, and use the same role and reference id from there."]
    return [
        "Search the company name and open its own careers page: the same role and reference id must be listed there.",
        f"The board must belong to the employer: its page names '{st['owner']}'. Any other name is a stop.",
        "Enter no data and create no account on the board until both checks hold.",
    ]


def _guidance(st):
    lines = list(COMMON_GUIDANCE)
    if st["kind"] in KIND_GUIDANCE:
        lines.append(KIND_GUIDANCE[st["kind"]])
    flags = set(st["flags"])
    if "lookalike_host" in flags:
        lines.append(f"The {st['brand']} boards are on the listed {st['brand']} hosts only; this host only uses the name.")
    if "unlisted_ats_host" in flags:
        lines.append("A real ATS domain that the reviewed list does not cover yet: it can only be checked by hand.")
    if "unknown_host" in flags:
        lines.append("A company domain that is not on the reviewed list: confirm it on the employer's own careers page.")
    if flags & {"userinfo", "ip_literal", "punycode_host", "non_ascii_host", "invisible_char"}:
        lines.append("The host hides or copies a real name: do not use this link.")
    return lines


def _reason(flag, st, company):
    fields = {"host": st["host"] or "", "port": st["port"] or "", "brand": st["brand"] or "",
              "board": st["board"] or "", "owner": st["owner"] or "", "company": company or "", "max": MAX_LEN}
    return REASONS.get(flag, flag).format(**fields)


def _result(st, verdict, company, reviewed, warnings):
    flags = list(st["flags"])
    return {
        "verdict": verdict, "url": st["url"], "host": st["host"], "scheme": st["scheme"], "kind": st["kind"],
        "ats": st["ats"], "board": st["board"], "owner": st["owner"],
        "board_url": st["board_url"] if verdict in ("verified", "official_ats") else None,
        "reviewed": reviewed, "flags": flags,
        "reasons": [_reason(flag, st, company) for flag in flags],
        "manual_checks": _manual_checks(st) if verdict in ("official_ats", "job_board", "new_platform")
        or "board_company_mismatch" in flags else [],
        "guidance": _guidance(st) if verdict == "unverified" else [],
        "data_warnings": list(warnings),
    }


def classify(raw, data, company=None):
    st = analyze(raw, data)
    flags = st["flags"]
    reviewed = bool(st["board_key"]) and st["board_key"] in data["reviewed"]
    hard = [flag for flag in flags if flag not in SOFT_FLAGS and flag not in NEW_PLATFORM_FLAGS]
    if hard:
        verdict = "unverified"  # a sign of fraud: look-alike, shortener, form, chat link, hidden host...
    elif NEW_PLATFORM_FLAGS & set(flags):
        verdict = "new_platform"
    elif st["kind"] == "portal":
        verdict = "official_ats"
    elif st["kind"] == "job_board":
        verdict = "job_board"
    else:
        verdict = "verified" if reviewed and st["scheme"] == "https" else "official_ats"
    if verdict == "verified" and company and st["owner"] and company_matches(company, st["owner"]) is False:
        flags.append("board_company_mismatch")
    return _result(st, verdict, company, reviewed, data["warnings"])


def unreadable_result(raw, message):
    st = _blank(raw)
    st["flags"].append("official_hosts_unreadable")
    st["kind"] = "unknown"
    return _result(st, "unverified", None, False, [message])


def render(result):
    flags = ",".join(result["flags"]) or "none"
    lines = [f"verdict: {result['verdict']} | host: {result['host'] or '-'} | "
             f"ats: {result['ats'] or result['kind'] or '-'} | flags: {flags}"]
    lines += [f"  why: {reason}" for reason in result["reasons"]]
    if result["verdict"] == "verified":
        lines.append(f"  board: {result['board_url']} (reviewed)")
    lines += [f"  manual check: {check}" for check in result["manual_checks"]]
    lines += [f"  guidance: {line}" for line in result["guidance"]]
    lines += [f"  data warning: {warning}" for warning in result["data_warnings"]]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Classify a job link before any work is spent on it: verified, official_ats or unverified. "
                    "Offline: nothing is fetched.")
    parser.add_argument("url", help="the job link, as pasted or found (the text is classified, never opened)")
    parser.add_argument("--company", help="the employer's name; a verified board that does not match it gets the "
                                          "FLAG board_company_mismatch")
    parser.add_argument("--json", action="store_true", help="print one JSON object instead of the verdict line")
    args = parser.parse_args(argv)
    try:
        data = load_data(DATA_FILE)
    except DataError as exc:
        result = unreadable_result(args.url, str(exc))
    else:
        result = classify(args.url, data, company=args.company)
    print(json.dumps(result, indent=2, ensure_ascii=False) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
