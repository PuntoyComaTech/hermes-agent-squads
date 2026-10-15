#!/usr/bin/env python3
"""Daily upstream gate for the builder: zero LLM tokens unless something changed.

Checks three signals and prints ONE cron gate line (last stdout line, see gate_lib.py):
  {"wakeAgent": false}                          nothing new, the tick ends
  {"wakeAgent": true, "context": {...}}         the digest agent runs on the filtered files

Signals:
  1. Hermes releases: GitHub releases API with a stored ETag (unchanged list = HTTP 304, no body),
     releases.atom as fallback. Only final vX.Y.Z tags count; rc.*, +canary and calver tags are skipped.
  2. Local Hermes: `hermes --version` differs from the last reviewed version.
  3. Squads repo: `distribution.yaml` on main has a version other than the installed and the last reviewed one.

On a change the full release bodies go to <state>/releases/<tag>.md and a keyword-filtered copy
(profile, skill, kanban, cron, plugin, MCP, deprecations, config keys ...) to <state>/releases/<tag>.filtered.md.
The filtered output of one run is capped at --max-chars (default 15000) in total.

State: $HERMES_HOME/local/state/watch.json (override with --state-dir). First run seeds the baseline from the
local Hermes and the installed squads version. Use --dry-run to check without writing state or files.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gate_lib  # noqa: E402

RELEASES_URL = "https://api.github.com/repos/NousResearch/hermes-agent/releases?per_page=5"
ATOM_URL = "https://github.com/NousResearch/hermes-agent/releases.atom"
SQUADS_RAW = "https://raw.githubusercontent.com/PuntoyComaTech/hermes-agent-squads/main"
FINAL_TAG = re.compile(r"^v(\d{1,3})\.(\d+)\.(\d+)$")  # v0.22.1; calver (v2026.9.24), rc.N-v0.22.1, +canary excluded
MAX_NEW_RELEASES = 3
ERROR_WAKE_AFTER = 3  # consecutive failed runs before a silent gate wakes the agent with the error
USER_AGENT = "hermes-squads-watch"

_KEYS = (r"agent|auxiliary|delegation|kanban|cron|security|terminal|display|memory|skills|plugins|mcp_servers|"
         r"toolsets|platform_toolsets|ui_meta|profiles|gateway|model|approvals|projects")
CONFIG_KEY = rf"\b(?:{_KEYS})\.(?!(?:py|md|ts|tsx|js|json|ya?ml|db|sh)\b)[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*"
PRIORITY = re.compile(rf"\b(?:kanban|cron)\b|\b(?:deprecat|remov|renam)\w*|\bbreaking\b|{CONFIG_KEY}", re.I)
KEYWORDS = re.compile(
    rf"\b(?:profile|skill|kanban|cron|plugin|mcp|connector|desktop|bot|toolset|project|gateway)s?\b|"
    rf"\b(?:deprecat|remov|renam)\w*|\bbreaking\b|{CONFIG_KEY}", re.I)
LINK_NOISE = re.compile(r"\s*\(\[`?[0-9a-f]{7,40}`?\]\([^)]*\)\)|\s+[\u2014-]\s+@[\w-]+\s*$")
MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
BULLET = re.compile(r"^\s*[-*]\s+(.*\S)")
HEADING = re.compile(r"^(#{1,6})\s+(.*\S)")
MAX_LINE = 300


# --- HTTP -------------------------------------------------------------------------------------------------------

def http_get(url: str, headers: dict | None = None, timeout: int = 20) -> tuple[int, dict, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers or {}), b""


# --- releases ---------------------------------------------------------------------------------------------------

def is_final(tag: str) -> bool:
    return bool(FINAL_TAG.match(tag))


class _Html2Md(HTMLParser):
    """Just enough of HTML to turn a GitHub release body back into headings and bullets."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.buf: list[str] = []
        self.prefix = ""

    def _flush(self) -> None:
        text = " ".join("".join(self.buf).split())
        if text:
            self.out.append(f"{self.prefix}{text}")
        self.buf, self.prefix = [], ""

    def handle_starttag(self, tag, attrs):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush()
            self.prefix = "#" * int(tag[1]) + " "
        elif tag == "li":
            self._flush()
            self.prefix = "- "
        elif tag in ("p", "ul", "ol", "br"):
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "li", "p"):
            self._flush()

    def handle_data(self, data):
        self.buf.append(data)

    def markdown(self) -> str:
        self._flush()
        return "\n".join(self.out)


def html_to_md(html: str) -> str:
    parser = _Html2Md()
    parser.feed(html)
    return parser.markdown()


def parse_api(raw: bytes) -> list[dict]:
    out = []
    for item in json.loads(raw):
        tag = item.get("tag_name") or ""
        if item.get("draft") or item.get("prerelease") or not is_final(tag):
            continue
        out.append({"tag": tag, "body": item.get("body") or "", "published": item.get("published_at")})
    return out


def parse_atom(raw: bytes) -> list[dict]:
    ns = "{http://www.w3.org/2005/Atom}"
    out = []
    for entry in ET.fromstring(raw).findall(f"{ns}entry"):
        link = entry.find(f"{ns}link")
        href = link.get("href", "") if link is not None else ""
        tag = urllib.parse.unquote(href.rsplit("/tag/", 1)[-1])
        if not is_final(tag):
            continue
        content = entry.find(f"{ns}content")
        out.append({"tag": tag, "body": html_to_md(content.text or "") if content is not None else "",
                    "published": (entry.findtext(f"{ns}updated") or None)})
    out.sort(key=lambda r: r["published"] or "", reverse=True)  # atom order is not strictly by date
    return out


def fetch_releases(opts, state: dict, force: bool = False) -> dict:
    """{source, releases, etag, not_modified}. API first (conditional), atom when the API fails or is rate limited."""
    headers = {"Accept": "application/vnd.github+json"}
    if state.get("etag") and not (force or opts.force):
        headers["If-None-Match"] = state["etag"]
    api_error = ""
    try:
        status, resp_headers, body = http_get(opts.releases_url, headers, opts.timeout)
        if status == 304:
            return {"source": "api", "releases": [], "etag": state.get("etag"), "not_modified": True}
        if status == 200:
            etag = next((v for k, v in resp_headers.items() if k.lower() == "etag"), None)
            return {"source": "api", "releases": parse_api(body), "etag": etag, "not_modified": False}
        api_error = f"api HTTP {status}"
    except (OSError, ValueError) as exc:
        api_error = f"api {type(exc).__name__}: {exc}"[:200]
    status, _, body = http_get(opts.atom_url, {}, opts.timeout)
    if status != 200:
        raise RuntimeError(f"{api_error}; atom HTTP {status}")
    return {"source": "atom", "releases": parse_atom(body), "etag": state.get("etag"), "not_modified": False,
            "api_error": api_error}


def version_tuple(tag: str | None) -> tuple[int, ...] | None:
    match = FINAL_TAG.match(tag or "")
    return tuple(int(n) for n in match.groups()) if match else None


def new_releases(releases: list[dict], reviewed: str | None) -> list[dict]:
    """Final releases newer than `reviewed`, newest first (list order), at most MAX_NEW_RELEASES."""
    fresh = []
    for rel in releases:
        if rel["tag"] == reviewed:
            break
        fresh.append(rel)
    else:
        fresh = releases[:1]  # reviewed tag not in the page: only the newest is certainly new
    return fresh[:MAX_NEW_RELEASES]


# --- filter -----------------------------------------------------------------------------------------------------

def _clean(line: str) -> str:
    line = LINK_NOISE.sub("", line)
    line = MD_LINK.sub(r"\1", line)
    line = " ".join(line.split())
    return line if len(line) <= MAX_LINE else line[: MAX_LINE - 3] + "..."


def filter_release(body: str, tag: str, max_chars: int) -> str:
    """Headings and bullets about Hermes surfaces squads depend on, kanban/cron/removals first, capped at max_chars."""
    heading = ""
    title = ""
    cands: list[dict] = []  # {i, heading, text, prio}; prio 0 = kanban, cron, removals, renames, config keys
    total = 0
    for raw in body.splitlines():
        h = HEADING.match(raw)
        if h:
            heading = _clean(raw.strip())
            title = title or heading
            continue
        b = BULLET.match(raw)
        if not b:
            continue
        total += 1
        text = _clean(f"- {b.group(1)}")
        if KEYWORDS.search(text):
            cands.append({"i": len(cands), "heading": heading, "text": text, "prio": 0 if PRIORITY.search(text) else 1})

    head = f"# {tag} filtered release notes\n"
    budget = max_chars - len(head) - len(title) - 120  # 120 reserved for the footer
    chosen: list[dict] = []
    used_headings: set[str] = set()
    for c in sorted(cands, key=lambda c: (c["prio"], c["i"])):
        cost = len(c["text"]) + 1 + (0 if c["heading"] in used_headings or not c["heading"] else len(c["heading"]) + 2)
        if cost <= budget:
            budget -= cost
            used_headings.add(c["heading"])
            chosen.append(c)
    chosen.sort(key=lambda c: c["i"])
    lines = [head.rstrip()]
    if title:
        lines.append(title)
    last = ""
    for c in chosen:
        if c["heading"] and c["heading"] != last and c["heading"] != title:
            lines += ["", c["heading"]]
            last = c["heading"]
        lines.append(c["text"])
    lines += ["", f"kept {len(chosen)} of {len(cands)} matching bullets ({total} bullets in the release)"]
    out = "\n".join(lines) + "\n"
    return out if len(out) <= max_chars else out[: max_chars - 4].rstrip() + "...\n"


# --- local and squads signals -----------------------------------------------------------------------------------

def local_hermes_version(hermes_bin: str) -> str | None:
    try:
        proc = subprocess.run([hermes_bin, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"\bv(\d+\.\d+\.\d+\S*)", (proc.stdout or "").splitlines()[0] if proc.stdout else "")
    return match.group(1) if match else None


def manifest_version(text: str) -> str | None:
    match = re.search(r"^version:\s*[\"']?(\d+\.\d+\.\d+[^\s\"']*)", text, re.M)
    return match.group(1) if match else None


def base_version(version: str | None) -> str | None:
    """A git install reports `0.22.0+2.gd97007c`; only the release part is a change, so a build bump
    (every `hermes update`) never wakes the digest agent."""
    return version.split("+")[0] if version else version


def installed_squads_version(home: Path) -> str | None:
    try:
        return manifest_version((home / "distribution.yaml").read_text())
    except OSError:
        return None


def remote_squads_version(opts) -> str | None:
    status, _, body = http_get(f"{opts.squads_url}/distribution.yaml", {}, opts.timeout)
    if status == 404:
        return None  # not published yet
    if status != 200:
        raise RuntimeError(f"squads distribution.yaml HTTP {status}")
    return manifest_version(body.decode("utf-8", "replace"))


def changelog_excerpt(opts, version: str, limit: int = 1500) -> str:
    try:
        status, _, body = http_get(f"{opts.squads_url}/CHANGELOG.md", {}, opts.timeout)
    except OSError:
        return ""
    if status != 200:
        return ""
    text = body.decode("utf-8", "replace")
    match = re.search(rf"^##[^\n]*\b{re.escape(version)}\b[^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    return (match.group(0) if match else text)[:limit].strip()


# --- run --------------------------------------------------------------------------------------------------------

def run(opts) -> dict:
    sdir = gate_lib.state_dir(opts.state_dir)
    state = gate_lib.load_state("watch", sdir)
    errors: list[str] = []

    local = opts.hermes_version or local_hermes_version(opts.hermes_bin)
    installed_sq = installed_squads_version(Path(opts.home))
    try:
        remote_sq = remote_squads_version(opts)
    except (OSError, RuntimeError) as exc:
        remote_sq, errors = None, [*errors, f"squads: {exc}"[:200]]
    rel = {"source": None, "releases": [], "etag": state.get("etag"), "not_modified": False}
    try:
        rel = fetch_releases(opts, state)
    except (OSError, RuntimeError, ValueError, ET.ParseError) as exc:
        errors.append(f"releases: {exc}"[:300])

    cached_latest = state.get("latest_tag")
    newest = rel["releases"][0]["tag"] if rel["releases"] else (cached_latest if rel["not_modified"] else None)
    first_run = "reviewed" not in state
    reviewed = state.get("reviewed") or {
        "release": f"v{local.split('+')[0]}" if local else newest,
        "hermes": local,
        "squads": installed_sq,
    }
    seen, ahead = reviewed.get("release"), version_tuple(newest)
    is_newer = bool(newest and newest != seen and (not version_tuple(seen) or (ahead and ahead > version_tuple(seen))))
    if is_newer and rel["not_modified"]:
        # A change is pending but this response has no body; refetch unconditionally.
        try:
            rel = fetch_releases(opts, state, force=True)
        except (OSError, RuntimeError, ValueError, ET.ParseError) as exc:
            errors.append(f"releases: {exc}"[:300])
    fresh = new_releases(rel["releases"], seen) if is_newer else []
    changes = {
        "release": bool(fresh),
        "hermes": bool(local and base_version(local) != base_version(reviewed.get("hermes"))),
        "squads": bool(remote_sq and installed_sq and remote_sq != installed_sq and remote_sq != reviewed.get("squads")),
    }
    wake = any(changes.values())

    context: dict = {"gate": "watch_upstream", "source": rel["source"], "changed": [k for k, v in changes.items() if v]}
    files: list[dict] = []
    if fresh:
        budget = opts.max_chars // len(fresh)
        for item in fresh:
            full = sdir / "releases" / f"{item['tag']}.md"
            filt = sdir / "releases" / f"{item['tag']}.filtered.md"
            filtered = filter_release(item["body"], item["tag"], budget)
            if not opts.dry_run:
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(item["body"])
                filt.write_text(filtered)
            files.append({"tag": item["tag"], "full": str(full), "filtered": str(filt),
                          "full_chars": len(item["body"]), "filtered_chars": len(filtered)})
        context["tags"] = [f["tag"] for f in files]
        context["release_from"] = reviewed.get("release")
        context["filtered"] = [f["filtered"] for f in files]
        context["release_files"] = files
    if changes["hermes"]:
        context["hermes"] = {"from": reviewed.get("hermes"), "to": local}
    if changes["squads"]:
        context["squads"] = {"from": installed_sq, "to": remote_sq, "changelog_excerpt": changelog_excerpt(opts, remote_sq)}

    error_count = 0 if (wake or not errors) else int(state.get("error_count", 0)) + 1
    if errors and not wake and error_count >= ERROR_WAKE_AFTER:
        wake, error_count = True, 0
        context["gate_error"] = "; ".join(errors)[:400]
    elif errors:
        context["errors"] = errors

    new_state = {
        **state,
        "etag": rel["etag"],
        "latest_tag": newest or cached_latest,
        "checked_at": int(time.time()),
        "error_count": error_count,
        "reviewed": {
            "release": newest if changes["release"] else reviewed.get("release"),
            "hermes": local or reviewed.get("hermes"),
            "squads": remote_sq if changes["squads"] else reviewed.get("squads"),
        },
    }
    if not opts.dry_run:
        gate_lib.save_state("watch", new_state, sdir)
    report = {"wake": wake, "source": rel["source"], "not_modified": rel["not_modified"], "newest": newest,
              "reviewed": reviewed, "local": local, "squads_installed": installed_sq, "squads_remote": remote_sq,
              "changes": changes, "errors": errors, "first_run": first_run, "dry_run": opts.dry_run}
    return {"wake": wake, "context": context, "report": report}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0], epilog=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="add a `report` object to the gate line")
    ap.add_argument("--dry-run", action="store_true", help="check only: write no state and no files")
    ap.add_argument("--force", action="store_true", help="ignore the stored ETag")
    ap.add_argument("--home", default=str(gate_lib.default_home()), help="builder profile home (default $HERMES_HOME)")
    ap.add_argument("--state-dir", help="state directory (default <home>/local/state)")
    ap.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN", "hermes"))
    ap.add_argument("--hermes-version", help="use this local version instead of running `hermes --version`")
    ap.add_argument("--releases-url", default=RELEASES_URL)
    ap.add_argument("--atom-url", default=ATOM_URL)
    ap.add_argument("--squads-url", default=SQUADS_RAW, help="raw base URL of the squads repo main branch")
    ap.add_argument("--max-chars", type=int, default=15000, help="cap for the filtered output of one run")
    ap.add_argument("--timeout", type=int, default=20)
    return ap


def main(argv: list[str] | None = None) -> int:
    opts = build_parser().parse_args(argv)
    if opts.state_dir is None:
        opts.state_dir = str(Path(opts.home) / "local" / "state")

    def body() -> int:
        result = run(opts)
        extra = {"report": result["report"]} if opts.json else {}
        return gate_lib.emit(result["wake"], result["context"], **extra)

    return gate_lib.guarded("watch_upstream", body)


if __name__ == "__main__":
    sys.exit(main())
