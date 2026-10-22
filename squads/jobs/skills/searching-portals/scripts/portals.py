#!/usr/bin/env python3
"""Job-portal search for the jobs squad: list, search, detail and health across the installed portal CLIs.

A portal is a directory beside this script holding a `portal.json` manifest and its CLI. Adding a board means
adding a directory; this script does not change. The contract is in references/portal-contract.md.

  portals.py [--root DIR] list
  portals.py [--root DIR] search [-q TEXT] [-l TEXT] [--remote MODE] [--portal NAME ...]
                                 [--max-age-days N] [--limit N] [--page N] [--today YYYY-MM-DD] [-- PORTAL-FLAGS]
  portals.py [--root DIR] detail <id|url> [--portal NAME]
  portals.py [--root DIR] health [--portal NAME ...] [--detail] [--today YYYY-MM-DD]
  portals.py prefilter --profile profile.md --input rows.json [--input more.json ...] [--project P] [--today YYYY-MM-DD]
    (no network: keeps the rows whose title matches the profile terms, newest first, within the profile's caps;
     reports the analysis cap state for the project today)

stdout is JSON. Errors go to stderr as {"error": ..., "code": ...} and exit 1. A search in which some portals
failed exits 1 and still prints the results that worked (meta.failed names the rest). Health exits 0; its
verdicts are in the JSON. Stdlib only, Python 3.9+. Never reads .env files or credentials.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
DEFAULT_MAX_AGE_DAYS = 14
DEFAULT_LIMIT = 20
SENTINEL_LIMIT = 3
RETRY_QUERY_DEFAULT = "manager"
CLI_TIMEOUT_S = 120
MAX_WORKERS = 4
MANIFEST_KEYS = ("name", "hosts", "enabled", "markets", "cmd", "search_flags", "example_query")
SEARCH_KEYS = ("query", "location", "jobage", "jobage_minutes", "limit", "page", "remote", "format")
BASE_RESULT_KEYS = ("id", "title", "company", "location", "date", "url", "work_mode")
NAME_RE = re.compile(r"[a-z][a-z0-9-]*$")
# A 429, a block page, a server error after retries, or a network failure says nothing about the parser.
RATE_OR_BLOCK_RE = re.compile(
    r"\b429\b|too many requests|rate.?limit|\b403\b|forbidden|captcha|blocked|challenge|"
    r"\b5\d\d\b|could not reach|unreachable|timed? ?out|ECONN|ENOTFOUND",
    re.I,
)
ENTITY_OR_TAG_RE = re.compile(r"&(?:[a-zA-Z]+|#\d+|#[xX][0-9a-fA-F]+);|<[a-zA-Z/!][^>]*>")
INCONCLUSIVE_CODES = {"BUN_MISSING", "CLI_MISSING", "TIMEOUT"}
WORK_MODES = ("remote", "hybrid", "onsite")
# Search rows carry a description preview of at most this many characters; the rest is read with detail.
DESCRIPTION_PREVIEW_MAX = 1200
# A company value that is an identifier rather than a name (16 or more hex digits, or a UUID) is not a company.
HASH_NAME_RE = re.compile(r"^(?:[0-9a-f]{16,}|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12})$", re.I)
# Workplace type from the words a title, place or description carries (Spanish, Portuguese, English).
ONSITE_RE = re.compile(r"\b(?:presencial(?:mente)?|on[- ]?site|in[- ]office|in[- ]person|no remoto)\b", re.I)
REMOTE_RE = re.compile(
    r"\b(?:remote|remoto|remota|teletrabajo|home[- ]office|work[- ]from[- ]home|trabalho remoto|100% remoto)\b",
    re.I,
)
HYBRID_RE = re.compile(r"\b(?:h[ií]brid[oa]s?|hybrid)\b", re.I)


class PortalError(Exception):
    """A failure with a stable code, reported on stderr as JSON."""

    def __init__(self, code, message, portal=None):
        super().__init__(message)
        self.code = code
        self.portal = portal


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # usage errors use the same JSON shape as every other error
        sys.stderr.write(json.dumps({"error": message, "code": "BAD_ARG"}) + "\n")
        sys.exit(1)


def emit(obj):
    sys.stdout.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def fail(message, code, portal=None):
    err = {"error": message, "code": code}
    if portal:
        err["portal"] = portal
    sys.stderr.write(json.dumps(err, ensure_ascii=False) + "\n")
    return 1


# --- manifests ----------------------------------------------------------------------------------------------------

def _string_list(value):
    return isinstance(value, list) and all(isinstance(v, str) and v.strip() for v in value)


def validate_manifest(spec, directory):
    """Return the manifest or raise PortalError(BAD_PORTAL) naming what is wrong."""
    def bad(why):
        raise PortalError("BAD_PORTAL", f"{directory.name}: {why}", directory.name)

    if not isinstance(spec, dict):
        bad("portal.json must hold a JSON object")
    missing = [k for k in MANIFEST_KEYS if k not in spec]
    if missing:
        bad("portal.json lacks " + ", ".join(missing))
    name = spec["name"]
    if not isinstance(name, str) or not NAME_RE.match(name) or name != directory.name:
        bad("name must equal the directory name (lowercase letters, digits, dashes)")
    if not _string_list(spec["hosts"]) or not spec["hosts"]:
        bad("hosts must be a non-empty list of host names")
    if "url_hosts" in spec and not (isinstance(spec["url_hosts"], list)
                                    and all(isinstance(h, str) and h.strip() for h in spec["url_hosts"])):
        bad("url_hosts must be a list of host names (an empty list means any http(s) address)")
    if not isinstance(spec["enabled"], bool):
        bad("enabled must be true or false")
    if not _string_list(spec["markets"]) or not spec["markets"]:
        bad("markets must be a non-empty list")
    if not _string_list(spec["cmd"]) or not spec["cmd"]:
        bad("cmd must be a non-empty argument list")
    flags = spec["search_flags"]
    if not isinstance(flags, dict):
        bad("search_flags must be an object")
    unknown = sorted(set(flags) - set(SEARCH_KEYS))
    if unknown:
        bad("search_flags has unknown keys: " + ", ".join(unknown))
    for key, flag in flags.items():
        if not (isinstance(flag, str) and flag.startswith("--")):
            bad(f"search_flags.{key} must be a long flag such as --query")
    if "format" not in flags:
        bad("search_flags must map format (the CLI has to print JSON)")
    required = spec.get("required_search", [])
    if not _string_list(required) and required != []:
        bad("required_search must be a list of search keys")
    if not set(required) <= set(flags):
        bad("required_search names a key that search_flags does not map")
    if "location" in required and not spec.get("example_location"):
        bad("example_location is required when location is required (the health sentinel needs one)")
    if not _string_list(spec.get("search_defaults", [])):
        bad("search_defaults must be a list of strings")
    if not isinstance(spec["example_query"], str) or not spec["example_query"].strip():
        bad("example_query must be a query known to return results")
    retry = spec.get("retry_query", RETRY_QUERY_DEFAULT)
    if not isinstance(retry, str) or not retry.strip():
        bad("retry_query must be a non-empty word")
    return spec


class Portal:
    def __init__(self, spec, directory):
        self.spec = spec
        self.dir = directory
        self.name = spec["name"]
        self.enabled = spec["enabled"]
        self.hosts = [h.lower() for h in spec["hosts"]]
        self.url_hosts = [h.lower() for h in spec.get("url_hosts", spec["hosts"])]
        self.flags = spec["search_flags"]
        self.required = list(spec.get("required_search", []))
        self.defaults = list(spec.get("search_defaults", []))
        self.example_query = spec["example_query"]
        self.example_location = spec.get("example_location")
        self.retry_query = spec.get("retry_query", RETRY_QUERY_DEFAULT)


def load_portals(root):
    """Return (portals by name, problems). A broken manifest is a problem, never silently skipped."""
    if not root.is_dir():
        raise PortalError("BAD_ROOT", f"not a directory: {root}")
    portals, problems = {}, []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        manifest = directory / "portal.json"
        if directory.name.startswith((".", "_")) or not manifest.is_file():
            continue
        try:
            spec = validate_manifest(json.loads(manifest.read_text(encoding="utf-8")), directory)
        except (OSError, ValueError, PortalError) as exc:
            problems.append({"portal": directory.name, "error": str(exc)})
            continue
        portals[spec["name"]] = Portal(spec, directory)
    return portals, problems


def get_portal(portals, problems, name):
    if name in portals:
        return portals[name]
    if any(p["portal"] == name for p in problems):
        raise PortalError("BAD_PORTAL", f"portal {name!r} has an invalid portal.json; run list", name)
    raise PortalError("UNKNOWN_PORTAL", f"no installed portal named {name!r}; run list", name)


def host_matches(host, hosts):
    return any(host == h or host.endswith("." + h) for h in hosts)


# --- running a portal CLI -----------------------------------------------------------------------------------------

def user_blocklist(env=None) -> list:
    """Hosts the user refused in JOBS_BLOCKLIST (comma or space separated). Portals obey this list; the built-in
    linkedin.com entry that keeps browsers away from LinkedIn does not apply to the portal CLI, which is the one
    sanctioned reader of public LinkedIn listings."""
    source = os.environ if env is None else env
    return [item.strip().lower().lstrip("*.") for item in re.split(r"[\s,]+", source.get("JOBS_BLOCKLIST", ""))
            if item.strip()]


def blocked_portal(portal, entries):
    """The blocklist entry that covers one of the portal's hosts, or None."""
    for host in portal.hosts:
        for entry in entries:
            if host == entry or host.endswith("." + entry):
                return entry
    return None


def find_bun():
    configured = os.environ.get("BUN", "").strip()
    if configured:
        resolved = shutil.which(configured)
        if resolved:
            return resolved
        raise PortalError("BUN_MISSING", f"BUN is set to {configured!r}, which is not an executable")
    found = shutil.which("bun")
    if found:
        return found
    fallback = Path.home() / ".bun" / "bin" / "bun"
    if fallback.is_file():
        return str(fallback)
    raise PortalError("BUN_MISSING", "bun is not installed; install it or set BUN to its path")


def portal_argv(portal):
    argv = [part.replace("{dir}", str(portal.dir)).replace("{python}", sys.executable) for part in portal.spec["cmd"]]
    if argv[0] == "bun":
        argv[0] = find_bun()
    return argv


def run_cli(portal, args):
    argv = portal_argv(portal) + list(args)
    try:
        proc = subprocess.run(
            argv,
            cwd=str(portal.dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CLI_TIMEOUT_S,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise PortalError("CLI_MISSING", f"the command {argv[0]!r} was not found", portal.name)
    except subprocess.TimeoutExpired:
        raise PortalError("TIMEOUT", f"no answer within {CLI_TIMEOUT_S} seconds", portal.name)
    except OSError as exc:
        raise PortalError("CLI_MISSING", str(exc), portal.name)
    return proc.returncode, proc.stdout, proc.stderr


def cli_error(stderr):
    """(code, message) from the CLI's last stderr JSON line; falls back to the raw text."""
    for line in reversed(stderr.strip().splitlines()):
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict) and "error" in obj:
            return str(obj.get("code") or "PORTAL_FAILED"), str(obj["error"])
    return "PORTAL_FAILED", (stderr.strip() or "the CLI exited non-zero with no message")[-300:]


def parse_cli_json(stdout, portal):
    try:
        payload = json.loads(stdout)
    except ValueError:
        raise PortalError("BAD_OUTPUT", "the CLI did not print JSON", portal.name)
    results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results, list):
        raise PortalError("BAD_OUTPUT", "the CLI JSON has no results list", portal.name)
    return [r for r in results if isinstance(r, dict)]


# --- search -------------------------------------------------------------------------------------------------------

def build_search_args(portal, *, query=None, location=None, remote=None, page=1, limit=None, max_age_days=None,
                      max_age_hours=None, passthrough=()):
    """The CLI argument list for one search. Raises before anything runs when the request cannot be honoured."""
    explicit = [("query", query), ("location", location), ("remote", remote)]
    if page > 1:
        explicit.append(("page", str(page)))
    for key, value in explicit:
        if value is None:
            continue
        if not value.strip():
            raise PortalError("BAD_ARG", f"--{key} needs a value", portal.name)
        if value.startswith("-"):
            raise PortalError("BAD_ARG", f"the value for --{key} must not start with '-'", portal.name)
        if key not in portal.flags:
            raise PortalError(
                "UNSUPPORTED_FLAG",
                f"{portal.name} has no --{key}; pass its own facet flags after -- (see its SKILL)",
                portal.name,
            )
    supplied = dict(explicit)
    for key in portal.required:
        if not supplied.get(key):
            raise PortalError("MISSING_ARG", f"{portal.name} needs --{key}", portal.name)
    ordered = [
        ("query", query),
        ("location", location),
        ("remote", remote),
        ("page", str(page) if page > 1 else None),
        # An hour window goes to the portal in minutes when it can take them, else as whole days (rounded up);
        # the date filter below and prefilter --since keep only the window either way.
        ("jobage_minutes", str(max_age_hours * 60) if max_age_hours else None),
        ("jobage", None if max_age_hours and "jobage_minutes" in portal.flags
         else str(-(-max_age_hours // 24)) if max_age_hours else str(max_age_days) if max_age_days else None),
        ("limit", str(limit) if limit else None),
        ("format", "json"),
    ]
    args = ["search"]
    for key, value in ordered:
        if value is not None and key in portal.flags:
            args += [portal.flags[key], value]
    return args + portal.defaults + list(passthrough)


def parse_date(value):
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def parse_day(value):
    if value is None:
        return dt.date.today()
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise PortalError("BAD_ARG", f"--today must be YYYY-MM-DD, got {value!r}")


def _text(value):
    if value is None:
        return None
    text = str(value)
    return text if text.strip() else None


def company_name(value):
    """The company as a name. An identifier (a hash or UUID some boards put there) is not a name: null."""
    text = _text(value)
    if text is None or HASH_NAME_RE.match(text.strip()):
        return None
    return text


def infer_work_mode(text):
    """The one workplace type the text states, or None when it states none or more than one (an unclear posting
    is never presented as a single type)."""
    found = {mode for mode, pattern in (("onsite", ONSITE_RE), ("remote", REMOTE_RE), ("hybrid", HYBRID_RE))
             if pattern.search(text or "")}
    return found.pop() if len(found) == 1 else None


def normalise(item, portal_name):
    """The squad's result shape. `id` is kept because detail needs it (some urls are employer pages)."""
    day = parse_date(item.get("date"))
    row = {
        "id": _text(item.get("id")),
        "title": _text(item.get("title")),
        "company": company_name(item.get("company")),
        "location": _text(item.get("location")),
        "date": day.isoformat() if day else None,
        "url": _text(item.get("url")),
        "portal": portal_name,
    }
    # The portal's own label wins. Without one (LinkedIn's search shows no workplace field), the title and place are
    # read first, then the description preview. "Presencial" and "On-site" rows are labelled onsite here, so a
    # remote filter can drop them.
    label = str(item.get("work_mode") or "").strip().lower()
    description = _text(item.get("description")) or ""
    mode = label if label in WORK_MODES else (
        infer_work_mode(f"{row['title'] or ''} {row['location'] or ''}") or infer_work_mode(description[:DESCRIPTION_PREVIEW_MAX]))
    if mode:
        row["work_mode"] = mode
    return row


def apply_window(rows, today, max_age_days):
    """Keep rows inside the window. Undated rows are kept and counted; their date is never guessed."""
    kept, dropped, undated = [], 0, 0
    for row in rows:
        day = parse_date(row["date"])
        if day is None:
            undated += 1
            kept.append(row)
        elif max_age_days and (today - day).days > max_age_days:
            dropped += 1
        else:
            kept.append(row)
    return kept, dropped, undated


def apply_work_mode(rows, requested):
    """(rows kept, counts) for a --remote request. A row of another confirmed type is dropped and counted by that
    type. A row whose type is not stated is kept with `work_mode_unconfirmed: true` and counted: most LinkedIn rows
    state nothing, and dropping them loses real remote openings; the location gate reads the posting body later."""
    if not requested:
        return rows, {"dropped": {}, "unconfirmed": 0}
    kept, dropped, unconfirmed = [], {}, 0
    for row in rows:
        mode = row.get("work_mode")
        if mode == requested:
            kept.append(row)
        elif mode is None:
            unconfirmed += 1
            kept.append({**row, "work_mode_unconfirmed": True})
        else:
            dropped[mode] = dropped.get(mode, 0) + 1
    return kept, {"dropped": dropped, "unconfirmed": unconfirmed}


def _attempt(portal, args):
    try:
        rc, out, err = run_cli(portal, args)
        if rc:
            code, message = cli_error(err)
            raise PortalError(code, message, portal.name)
        return portal.name, parse_cli_json(out, portal), None
    except PortalError as exc:
        return portal.name, None, exc


def cmd_search(ns, passthrough):
    portals, problems = load_portals(ns.root)
    if ns.limit < 1 or ns.max_age_days < 1 or ns.page < 1 or (ns.max_age_hours is not None and ns.max_age_hours < 1):
        raise PortalError("BAD_ARG", "--limit, --max-age-days, --max-age-hours and --page must be whole numbers of at "
                                     "least 1")
    if ns.max_age_hours is not None:
        ns.max_age_days = -(-ns.max_age_hours // 24)  # the date filter works on whole days
    for key, value in (("query", ns.query), ("location", ns.location)):
        if value is not None and (not value.strip() or value.startswith("-")):
            raise PortalError("BAD_ARG", f"--{key} needs a non-empty value that does not start with '-'")
    names = ns.portal or sorted(n for n, p in portals.items() if p.enabled)
    if not names:
        raise PortalError("NO_PORTALS", "no enabled portal is installed; run list")
    selected = [get_portal(portals, problems, n) for n in names]
    today = parse_day(ns.today)
    plans, failed, skipped, per_portal, rows_out = [], [], [], [], []
    blocked = user_blocklist()
    for portal in selected:
        hit = blocked_portal(portal, blocked)
        if hit:
            entry = {"portal": portal.name, "code": "BLOCKED",
                     "error": f"{portal.name} is on the JOBS_BLOCKLIST (entry {hit})"}
            (failed if ns.portal else skipped).append(entry)
            continue
        try:
            plans.append((portal, build_search_args(
                portal, query=ns.query, location=ns.location, remote=ns.remote, page=ns.page,
                limit=ns.limit, max_age_days=ns.max_age_days, max_age_hours=ns.max_age_hours,
                passthrough=passthrough,
            )))
        except PortalError as exc:
            # A portal named with --portal that cannot take the request is a failure. A portal picked by
            # default is skipped and listed in meta.skipped, so a location-only search is never silently narrowed.
            entry = {"portal": portal.name, "code": exc.code, "error": str(exc)}
            (failed if ns.portal else skipped).append(entry)
    if not plans:
        if failed:
            return _emit_search(ns, today, [], [], failed, skipped)
        reasons = "; ".join(f"{s['portal']}: {s['code']}" for s in skipped)
        return fail(f"no selected portal accepts this search ({reasons})", "NO_PORTALS")
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, min(MAX_WORKERS, len(plans)))) as pool:
        attempts = {name: (rows, err) for name, rows, err in pool.map(lambda plan: _attempt(*plan), plans)}

    for portal, _args in plans:
        rows, err = attempts[portal.name]
        if err is not None:
            failed.append({"portal": portal.name, "code": err.code, "error": str(err)})
            sys.stderr.write(json.dumps({"error": str(err), "code": err.code, "portal": portal.name}) + "\n")
            continue
        raw_rows = rows or []
        windowed, dropped, undated = apply_window([normalise(r, portal.name) for r in raw_rows], today,
                                                  ns.max_age_days)
        kept, mode = apply_work_mode(windowed, ns.remote)
        kept = kept[: ns.limit]
        rows_out += kept
        per_portal.append({
            "portal": portal.name,
            "asked": ns.limit,
            "returned": len(raw_rows),
            "count": len(kept),
            "shortfall": max(0, ns.limit - len(kept)),
            "dropped_older": dropped,
            "dropped_work_mode": mode["dropped"],
            "unconfirmed_work_mode": mode["unconfirmed"],
            "undated": undated,
            "server_recency": "jobage" in portal.flags or "jobage_minutes" in portal.flags,
        })
    return _emit_search(ns, today, rows_out, per_portal, failed, skipped)


def _emit_search(ns, today, rows_out, per_portal, failed, skipped):
    rows_out.sort(key=lambda r: (r["portal"], r["id"] or ""))
    rows_out.sort(key=lambda r: r["date"] or "", reverse=True)
    emit({
        "meta": {
            "count": len(rows_out),
            "today": today.isoformat(),
            "max_age_days": ns.max_age_days,
            "max_age_hours": ns.max_age_hours,
            "portals": per_portal,
            "failed": failed,
            "skipped": skipped,
        },
        "results": rows_out,
    })
    return 1 if failed else 0


# --- prefilter ----------------------------------------------------------------------------------------------------

PREFILTER_CANDIDATES = 60   # profile key max_candidates_per_run: rows read in one search card, newest first
PREFILTER_DETAILS = 15      # profile key max_detail_calls: detail calls in one search card
PROFILE_WORK_MODES = {"remote_global": "remote", "remote_region": "remote", "remote_country": "remote",
                      "hybrid": "hybrid", "onsite": "onsite"}
TOKEN_STOP = frozenset(("de", "del", "la", "el", "los", "las", "y", "e", "en", "da", "do", "das", "dos", "para",
                        "of", "the", "and", "for", "in", "a", "an", "und", "der", "die"))


def title_tokens(text) -> frozenset:
    """The significant words of a title or a profile term, accent-free and lowercase. Stop words are not words."""
    flat = jc_module().ascii_fold(str(text or "")).lower()
    return frozenset(t for t in re.findall(r"[a-z0-9]+", flat) if len(t) > 1 and t not in TOKEN_STOP)


def jc_module():
    """jobs_common from the jobs-contract skill, beside this one. Imported only by the prefilter."""
    sibling = str(HERE.parents[1] / "jobs-contract" / "scripts")
    if sibling not in sys.path:
        sys.path.insert(0, sibling)
    import jobs_common  # noqa: E402 - the sibling path is added just above
    return jobs_common


def _terms(value) -> list:
    """Profile terms as a flat list of text. search_keywords is a mapping of language to list; a string is one term."""
    if value is None:
        return []
    if isinstance(value, dict):
        items = [x for v in value.values() for x in (v if isinstance(v, list) else [v])]
    elif isinstance(value, list):
        items = value
    else:
        items = [value]
    return [str(x).strip() for x in items if str(x).strip()]


def profile_int(meta: dict, key: str, default: int) -> int:
    value = meta.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PortalError("BAD_PROFILE", f"profile {key} must be a whole number of at least 1, got {value!r}")
    return value


def analysis_cap_state(project: Path, limit: int, today: dt.date) -> dict:
    """Analysis cards filed today for this project: one `found` line dated today in its openings' status.json. A
    card from another project, or from an earlier day, is not counted. The count resets at the next day."""
    day = today.isoformat()
    filed, unreadable = [], []
    for status in sorted((project / "openings").glob("*/status.json")):
        try:
            doc = json.loads(status.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unreadable.append(status.parent.name)
            continue
        history = doc.get("history") if isinstance(doc, dict) else None
        if any(isinstance(e, dict) and e.get("status") == "found" and str(e.get("date") or "")[:10] == day
               for e in history or []):
            filed.append(status.parent.name)
    used = len(filed)
    left = max(0, limit - used)
    if left:
        summary = f"{used} of {limit} used today; {left} left"
    else:
        summary = f"{used} of {limit} used today; next: tomorrow or ask me to analyze <id>"
    return {"date": day, "max": limit, "used_today": used, "left": left, "summary": summary, "openings": filed,
            "unreadable": unreadable}


def prefilter_rows(meta: dict, rows: list, today: dt.date, max_candidates: int, max_details: int,
                   since: dt.date | None = None) -> dict:
    """Keep the rows worth a read: title, company, work mode and posted date are checked on the search row, before any
    detail call. A row is kept when its title shares a significant word with a profile term (search_keywords,
    target_roles, acceptable_roles). Newest first; at most max_candidates are kept and at most max_details of them are
    named for a detail call."""
    pairs = []
    for term in dict.fromkeys(_terms(meta.get("search_keywords")) + _terms(meta.get("target_roles"))
                              + _terms(meta.get("acceptable_roles"))):
        tokens = title_tokens(term)
        if tokens:
            pairs.append((term, tokens))
    if not pairs:
        raise PortalError("NO_TERMS", "the profile has no search_keywords, target_roles or acceptable_roles to match")
    avoid = _terms(meta.get("avoid_companies"))
    modes = {PROFILE_WORK_MODES[m] for m in _terms(meta.get("work_mode")) if m in PROFILE_WORK_MODES}
    search_days = profile_int(meta, "search_days", DEFAULT_MAX_AGE_DAYS)
    jc = jc_module()
    counts = {"title": 0, "company": 0, "work_mode": 0, "date": 0, "duplicate": 0}
    unconfirmed = undated = 0
    seen, kept = set(), []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise PortalError("BAD_INPUT", f"row {index} is not an object")
        ident = (str(row.get("portal") or ""), str(row.get("id") or row.get("url") or ""))
        if not ident[1]:
            counts["title"] += 1  # a row with neither id nor url cannot be read again: not a candidate
            continue
        if ident in seen:
            counts["duplicate"] += 1
            continue
        seen.add(ident)
        title = title_tokens(row.get("title"))
        matched = [term for term, tokens in pairs if tokens & title]
        if not matched:
            counts["title"] += 1
            continue
        company = str(row.get("company") or "")
        if any(jc.word_in(name, company) for name in avoid):
            counts["company"] += 1
            continue
        mode = row.get("work_mode")
        if modes and mode in WORK_MODES and mode not in modes:
            counts["work_mode"] += 1
            continue
        if modes and mode not in WORK_MODES:
            unconfirmed += 1
        day = parse_date(row.get("date"))
        if day is None:
            undated += 1
        elif (today - day).days > search_days or (since and day < since):
            counts["date"] += 1  # older than the card's window (since) or than search_days
            continue
        kept.append({**row, "matched": matched[:3]})
    kept.sort(key=lambda r: (parse_date(r.get("date")) is None, -(parse_date(r.get("date")) or dt.date.min).toordinal()))
    candidates = kept[:max_candidates]
    details = [{"portal": c.get("portal"), "target": c.get("id") or c.get("url")} for c in candidates[:max_details]]
    return {"candidates": candidates, "detail_targets": details, "dropped": counts,
            "over_candidate_cap": max(0, len(kept) - max_candidates), "unconfirmed_work_mode": unconfirmed,
            "undated": undated, "search_days": search_days, "since": since.isoformat() if since else None,
            "max_candidates": max_candidates,
            "max_detail_calls": max_details}


def cmd_prefilter(ns, passthrough):
    if passthrough:
        raise PortalError("BAD_ARG", "prefilter takes no portal flags")
    jc = jc_module()
    profile_path = Path(ns.profile)
    if not profile_path.is_file():
        raise PortalError("BAD_ARG", f"profile not found: {ns.profile}")
    meta = jc.read_front_matter(profile_path)
    if not meta:
        raise PortalError("BAD_PROFILE", "profile.md has no readable front matter")
    rows = []
    for name in ns.input:
        try:
            data = json.loads(Path(name).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise PortalError("BAD_INPUT", f"cannot read rows from {name}: {exc}")
        part = data.get("results") if isinstance(data, dict) else data
        if not isinstance(part, list):
            raise PortalError("BAD_INPUT", f"{name} holds no list of rows (a list, or an object with results)")
        rows.extend(part)
    today = parse_day(ns.today)
    cap = profile_int(meta, "max_candidates_per_run", PREFILTER_CANDIDATES)
    details = profile_int(meta, "max_detail_calls", PREFILTER_DETAILS)
    since = parse_day(ns.since) if ns.since else None
    plan = prefilter_rows(meta, rows, today, cap, details, since)
    analysis = None
    if ns.project:
        limit = profile_int(meta, "max_analyses_per_day", 5)
        analysis = analysis_cap_state(Path(ns.project), limit, today)
    emit({"meta": {"input": len(rows), "today": today.isoformat(), "candidates": len(plan["candidates"]),
                   "dropped": plan["dropped"], "over_candidate_cap": plan["over_candidate_cap"],
                   "unconfirmed_work_mode": plan["unconfirmed_work_mode"], "undated": plan["undated"],
                   "search_days": plan["search_days"], "since": plan["since"],
                   "max_candidates": plan["max_candidates"],
                   "max_detail_calls": plan["max_detail_calls"]},
          "detail_targets": plan["detail_targets"], "analysis_cap": analysis, "candidates": plan["candidates"]})
    return 0


# --- detail -------------------------------------------------------------------------------------------------------

def url_host(target):
    if "/" not in target and "." not in target:
        return None
    candidate = target if re.match(r"https?://", target) else "https://" + target
    host = urlparse(candidate).hostname
    return host.lower() if host else None


def resolve_target(target, portals, problems, portal_name):
    host = url_host(target)
    if portal_name:
        portal = get_portal(portals, problems, portal_name)
        if host is not None and not host_matches(host, portal.hosts):
            raise PortalError("BAD_ID", f"{host} is not a host of {portal.name}", portal.name)
        return portal, target
    if host is None:
        raise PortalError("BAD_ARG", "detail needs --portal for a bare id")
    for portal in sorted(portals.values(), key=lambda p: p.name):
        if host_matches(host, portal.hosts):
            return portal, target
    raise PortalError("BAD_ID", f"no installed portal serves the host {host}")


def cmd_detail(ns, passthrough):
    if passthrough:
        raise PortalError("BAD_ARG", "detail takes no portal flags")
    portals, problems = load_portals(ns.root)
    portal, ident = resolve_target(ns.target, portals, problems, ns.portal)
    hit = blocked_portal(portal, user_blocklist())
    if hit:
        raise PortalError("BLOCKED", f"{portal.name} is on the JOBS_BLOCKLIST (entry {hit})", portal.name)
    rc, out, err = run_cli(portal, ["detail", ident, "--format", "json"])
    if rc:
        code, message = cli_error(err)
        raise PortalError(code, message, portal.name)
    try:
        job = json.loads(out)
    except ValueError:
        raise PortalError("BAD_OUTPUT", "the CLI did not print JSON", portal.name)
    if not isinstance(job, dict):
        raise PortalError("BAD_OUTPUT", "the CLI detail is not an object", portal.name)
    row = normalise(job, portal.name)
    row["description"] = _text(job.get("description"))
    row["details"] = {k: v for k, v in job.items() if k not in BASE_RESULT_KEYS and k != "description"}
    emit(row)
    return 0


# --- health -------------------------------------------------------------------------------------------------------

def probe(portal, query, report):
    """(verdict, rows, message) for one search. verdict is ok, inconclusive or broken."""
    report["probes"] += 1
    try:
        args = build_search_args(portal, query=query, location=portal.example_location, limit=SENTINEL_LIMIT)
        rc, out, err = run_cli(portal, args)
    except PortalError as exc:
        if exc.code in INCONCLUSIVE_CODES:
            return "inconclusive", None, f"inconclusive ({exc.code}): {exc}"
        return "broken", None, f"{exc.code}: {exc}"
    if rc:
        code, message = cli_error(err)
        if RATE_OR_BLOCK_RE.search(f"{code} {message}"):
            return "inconclusive", None, f"rate-limited, blocked or unreachable: {message[:200]}"
        return "broken", None, f"{code}: {message[:200]}"
    try:
        return "ok", parse_cli_json(out, portal), ""
    except PortalError as exc:
        return "broken", None, str(exc)


def url_on_portal(portal, url):
    if not isinstance(url, str):
        return False
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return False
    return not portal.url_hosts or host_matches(parts.hostname.lower(), portal.url_hosts)


def scan_results(portal, rows):
    """Degraded-scan flags on a sample. Any flag makes the portal degraded; an empty list is clean."""
    reasons = []
    total = len(rows)
    if all(not str(r.get("company") or "").strip() for r in rows):
        reasons.append(f"company null or empty on all {total} results")
    hashed = sum(1 for r in rows if HASH_NAME_RE.match(str(r.get("company") or "").strip()))
    if hashed:
        reasons.append(f"company is an identifier, not a name, on {hashed} result(s)")
    empty = sum(1 for r in rows if not str(r.get("title") or "").strip())
    if empty:
        reasons.append(f"empty title on {empty} result(s)")
    garbled = sum(1 for r in rows if ENTITY_OR_TAG_RE.search(str(r.get("title") or "")))
    if garbled:
        reasons.append(f"undecoded HTML in {garbled} title(s)")
    off = sum(1 for r in rows if not url_on_portal(portal, r.get("url")))
    if off:
        where = ", ".join(portal.url_hosts) if portal.url_hosts else "an http(s) address"
        reasons.append(f"{off} result URL(s) not on {where}")
    return reasons


def detail_check(portal, rows, report):
    """One detail fetch on the first result. Returns (verdict or None, reason)."""
    target = rows[0].get("id") or rows[0].get("url")
    if not target:
        return "degraded", "detail: the first result has no id or url"
    report["probes"] += 1
    try:
        rc, out, err = run_cli(portal, ["detail", str(target), "--format", "json"])
    except PortalError as exc:
        verdict = "inconclusive" if exc.code in INCONCLUSIVE_CODES else "degraded"
        return verdict, f"detail: {exc.code}: {exc}"
    if rc:
        code, message = cli_error(err)
        if RATE_OR_BLOCK_RE.search(f"{code} {message}"):
            return "inconclusive", "detail: rate-limited, blocked or unreachable"
        return "degraded", f"detail failed: {code}: {message[:160]}"
    try:
        job = json.loads(out)
    except ValueError:
        return "degraded", "detail output is not JSON"
    description = job.get("description") if isinstance(job, dict) else None
    if not isinstance(description, str) or not description.strip():
        return "degraded", "detail has no description"
    if ENTITY_OR_TAG_RE.search(description):
        return "degraded", "detail description contains HTML tags or entities"
    return None, ""


def finish(report, status, reasons):
    report["status"] = status
    report["reasons"] = reasons
    return report


def health_one(portal, want_detail):
    report = {"portal": portal.name, "enabled": portal.enabled, "status": "", "reasons": [], "notes": [],
              "probes": 0}
    verdict, rows, message = probe(portal, portal.example_query, report)
    if verdict != "ok":
        return finish(report, verdict, [message])
    if not rows:
        verdict, rows, message = probe(portal, portal.retry_query, report)
        if verdict != "ok":
            return finish(report, verdict, [message])
        if not rows:
            return finish(report, "broken", [
                f"0 results for example_query {portal.example_query!r} and retry_query {portal.retry_query!r}"])
        report["notes"].append(
            f"example_query returned 0 results; retry_query {portal.retry_query!r} returned {len(rows)}")
    reasons = scan_results(portal, rows)
    if reasons:
        return finish(report, "degraded", reasons)
    if want_detail:
        verdict, reason = detail_check(portal, rows, report)
        if verdict:
            return finish(report, verdict, [reason])
    return finish(report, "healthy", [])


def cmd_health(ns, passthrough):
    if passthrough:
        raise PortalError("BAD_ARG", "health takes no portal flags")
    portals, problems = load_portals(ns.root)
    names = ns.portal or sorted(n for n, p in portals.items() if p.enabled)
    if not names:
        raise PortalError("NO_PORTALS", "no enabled portal is installed; run list")
    selected = [get_portal(portals, problems, n) for n in names]
    today = parse_day(ns.today)
    blocked = user_blocklist()
    reports = [
        {"portal": p.name, "enabled": p.enabled, "status": "blocked", "probes": 0,
         "reasons": [f"on the JOBS_BLOCKLIST (entry {hit})"], "notes": []}
        if (hit := blocked_portal(p, blocked)) else health_one(p, ns.detail)
        for p in selected
    ]
    emit({
        "meta": {"today": today.isoformat(), "checked": len(reports), "detail": ns.detail, "problems": problems},
        "portals": reports,
    })
    return 0


# --- list and entry point -----------------------------------------------------------------------------------------

def cmd_list(ns, passthrough):
    if passthrough:
        raise PortalError("BAD_ARG", "list takes no portal flags")
    portals, problems = load_portals(ns.root)
    emit({
        "portals": [
            {
                "name": p.name,
                "enabled": p.enabled,
                "markets": p.spec["markets"],
                "hosts": p.spec["hosts"],
                "description": p.spec.get("description", ""),
            }
            for p in sorted(portals.values(), key=lambda p: p.name)
        ],
        "problems": problems,
    })
    return 0


def build_parser():
    parser = _Parser(
        prog="portals.py",
        description="Portal search for the jobs squad: list, search, detail and health.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Arguments after -- go to the portal CLI unchanged (search only).",
    )
    parser.add_argument("--root", type=Path, default=HERE,
                        help="directory that holds the portal directories (default: beside this script)")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=_Parser,
                                metavar="{list,search,detail,health}")

    sub.add_parser("list", help="show installed portals").set_defaults(func=cmd_list)

    search = sub.add_parser("search", help="search enabled portals (or --portal NAME)")
    search.add_argument("-q", "--query", help="keywords")
    search.add_argument("-l", "--location", help="place string, for portals that take one (LinkedIn)")
    search.add_argument("--remote", choices=["remote", "hybrid", "onsite"], help="workplace type")
    search.add_argument("--portal", action="append", default=[], help="portal to search (repeatable)")
    search.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS,
                        help="posted within N days (default 14)")
    search.add_argument("--max-age-hours", type=int, help="posted within N hours: the search card's window; "
                                                          "overrides --max-age-days")
    search.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="results per portal (default 20)")
    search.add_argument("--page", type=int, default=1, help="1-indexed page")
    search.add_argument("--today", help="YYYY-MM-DD for a reproducible window (default: today)")
    search.set_defaults(func=cmd_search)

    detail = sub.add_parser("detail", help="one posting, by id or URL")
    detail.add_argument("target", help="posting id, or a URL on an installed portal's host")
    detail.add_argument("--portal", help="portal that owns a bare id")
    detail.set_defaults(func=cmd_detail)

    health = sub.add_parser("health", help="diagnose portals with a bounded sentinel probe")
    health.add_argument("--portal", action="append", default=[], help="portal to check (repeatable)")
    health.add_argument("--detail", action="store_true", help="also fetch one detail on healthy portals")
    health.add_argument("--today", help="YYYY-MM-DD recorded in the report (default: today)")
    health.set_defaults(func=cmd_health)

    pre = sub.add_parser("prefilter", help="keep the search rows worth a read, before any detail call")
    pre.add_argument("--profile", required=True, help="profile.md of the project")
    pre.add_argument("--input", required=True, action="append", help="search output file (repeatable): a JSON list, "
                                                                     "or an object with results")
    pre.add_argument("--project", help="project folder: its analysis cap state for today is reported")
    pre.add_argument("--today", help="YYYY-MM-DD for the posted-date window (default: today)")
    pre.add_argument("--since", help="YYYY-MM-DD: drop rows posted before it (the search card's Window line)")
    pre.set_defaults(func=cmd_prefilter)
    return parser


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    passthrough = []
    if "--" in argv:
        cut = argv.index("--")
        argv, passthrough = argv[:cut], argv[cut + 1:]
    ns = build_parser().parse_args(argv)
    if passthrough and ns.command != "search":
        return fail("arguments after -- are only accepted by search", "BAD_ARG")
    try:
        return ns.func(ns, passthrough)
    except PortalError as exc:
        return fail(str(exc), exc.code, exc.portal)


if __name__ == "__main__":
    sys.exit(main())
