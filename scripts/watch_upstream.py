#!/usr/bin/env python3
"""Daily upstream gate for the builder: zero LLM tokens unless something changed.

Checks three signals and prints ONE cron gate line (last stdout line, see gate_lib.py):
  {"wakeAgent": false}                          nothing new, the tick ends
  {"wakeAgent": true, "context": {...}}         the digest agent runs on the filtered files

Signals:
  1. Hermes releases: GitHub releases API with a stored ETag (unchanged list = HTTP 304, no body),
     releases.atom as fallback. Only final vX.Y.Z tags count; rc.*, +canary and calver tags are skipped.
  2. Local Hermes: `hermes --version` differs from the last reviewed version.
  3. Local Hermes docs: the docs each hermes-platform reference was verified against
     (scripts/data/doc-sources.json, paths under <source root>/website/docs) changed since the last review, or a new
     docs page appeared. The source root is the `Install directory:` line of `hermes --version` (or --hermes-src);
     an install without website/docs skips this signal. The wake names the affected references and writes a
     unified diff against the reviewed copy to <state>/docs/<date>.diff.md (capped at --max-chars; the rest goes
     to <date>.overflow.md, never dropped). Reviewed copies live content-addressed in <state>/docs/blobs/.
     The first run seeds the baseline silently.
The squads repo is not watched here: cron builder-update (scripts/auto_update.py) applies it with no agent.

On a change the full release bodies go to <state>/releases/<tag>.md and a keyword-filtered copy
(profile, skill, kanban, cron, plugin, MCP, goal, delegation, memory, credentials, deprecations, config keys ...)
to <state>/releases/<tag>.filtered.md. Keywords match the bullet and its heading; every bullet under
Upgrade notes, Kanban, Cron, Delegation, Plugin system, Skills and Profiles is priority. The filtered output of one
run is capped at --max-chars (default 15000) in total; priority bullets over the cap go to <tag>.overflow.md
(listed in `context.overflow`), never dropped.

State: $HERMES_HOME/local/state/watch.json (override with --state-dir). First run seeds the baseline from the
local Hermes. A wake only marks the change `pending`: it becomes `reviewed` once a
digest file (<state>/digests/*.json, skill tracking-updates) is newer than the wake, so a failed digest turn wakes
the agent again on the next run. Use --dry-run to check without writing state or files.
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
FINAL_TAG = re.compile(r"^v(\d{1,3})\.(\d+)\.(\d+)$")  # v0.22.1; calver (v2026.9.24), rc.N-v0.22.1, +canary excluded
MAX_NEW_RELEASES = 3
ERROR_WAKE_AFTER = 3  # consecutive failed runs before a silent gate wakes the agent with the error
USER_AGENT = "hermes-squads-watch"

_KEYS = (r"agent|auxiliary|delegation|kanban|cron|security|terminal|display|memory|skills|plugins|mcp_servers|"
         r"toolsets|platform_toolsets|ui_meta|profiles|gateway|model|approvals|projects")
CONFIG_KEY = rf"\b(?:{_KEYS})\.(?!(?:py|md|ts|tsx|js|json|ya?ml|db|sh)\b)[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*"
PRIORITY = re.compile(
    rf"\b(?:kanban|cron|goals?|subagents?|credential pools?|connectors?|tool_search|auxiliary)\b|"
    rf"/goal\b|\bdelegat\w*|\bmemory providers?\b|\bprovider plugins?\b|\bproviders as plugins\b|\bplugin catalog\b|"
    rf"\b(?:deprecat|remov|renam)\w*|\bbreaking\b|{CONFIG_KEY}", re.I)
KEYWORDS = re.compile(
    rf"\b(?:profile|skill|kanban|cron|plugin|mcp|connector|desktop|bot|toolset|project|gateway|goal|memory|"
    rf"subagent|credential|provider)s?\b|\bdelegat\w*|\b(?:deprecat|remov|renam)\w*|\bbreaking\b|{CONFIG_KEY}", re.I)
# Sections whose every bullet is prio 0, matched against the nearest heading.
PRIORITY_HEADING = re.compile(r"\b(?:kanban|cron|delegation|plugin system|skills|profiles|upgrade notes)\b", re.I)
SKIP_SECTION = re.compile(r"\b(?:contributors|tests)\b", re.I)  # top-level sections with nothing to digest
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


def _render(head: str, title: str, items: list[dict], footer: str = "") -> str:
    lines = [head]
    if title:
        lines.append(title)
    last = ""
    for c in items:
        if c["heading"] and c["heading"] != last and c["heading"] != title:
            lines += ["", c["heading"]]
            last = c["heading"]
        lines.append(c["text"])
    if footer:
        lines += ["", footer]
    return "\n".join(lines) + "\n"


def filter_release(body: str, tag: str, max_chars: int) -> tuple[str, str]:
    """(filtered, overflow) for one release body.

    A bullet matches when its heading or its text names a Hermes surface squads depend on (KEYWORDS). It is prio 0
    when its text matches PRIORITY or its nearest heading matches PRIORITY_HEADING (Kanban, Cron, Delegation, ...).
    `filtered` holds prio-0 bullets first, then prio-1 bullets, within max_chars. A prio-0 bullet never drops: what
    does not fit goes to `overflow` (empty string when everything fit). Prio-1 bullets that do not fit drop.
    Bullets under Contributors and Tests sections are skipped."""
    section = heading = title = ""
    cands: list[dict] = []  # {i, heading, text, prio}
    total = 0
    for raw in body.splitlines():
        h = HEADING.match(raw)
        if h:
            text = _clean(raw.strip())
            title = title or text
            if len(h.group(1)) <= 2:
                section = text
            heading = text
            continue
        b = BULLET.match(raw)
        if not b or SKIP_SECTION.search(section):
            continue
        total += 1
        text = _clean(f"- {b.group(1)}")
        if KEYWORDS.search(f"{heading} {text}"):
            prio = 0 if PRIORITY.search(text) or PRIORITY_HEADING.search(heading) else 1
            cands.append({"i": len(cands), "heading": heading, "text": text, "prio": prio})

    head = f"# {tag} filtered release notes"
    budget = max_chars - len(head) - len(title) - 160  # 160 reserved for the footer
    chosen: list[dict] = []
    spilled: list[dict] = []
    used_headings: set[str] = set()
    for c in sorted(cands, key=lambda c: (c["prio"], c["i"])):
        cost = len(c["text"]) + 1 + (0 if c["heading"] in used_headings or not c["heading"] else len(c["heading"]) + 2)
        if cost <= budget:
            budget -= cost
            used_headings.add(c["heading"])
            chosen.append(c)
        elif c["prio"] == 0:
            spilled.append(c)
    chosen.sort(key=lambda c: c["i"])
    footer = f"kept {len(chosen)} of {len(cands)} matching bullets ({total} bullets in the release)"
    if spilled:
        footer += f"; {len(spilled)} priority bullets in {tag}.overflow.md"
    out = _render(head, title, chosen, footer)
    if len(out) > max_chars:
        out = out[: max_chars - 4].rstrip() + "...\n"
    overflow = _render(f"# {tag} priority bullets over the cap", "", spilled) if spilled else ""
    return out, overflow


# --- local signal ------------------------------------------------------------------------------------------------

def hermes_version_info(hermes_bin: str) -> tuple[str | None, str | None]:
    """(version, install directory) from `hermes --version`; (None, None) when the binary cannot run."""
    try:
        proc = subprocess.run([hermes_bin, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None, None
    out = proc.stdout or ""
    match = re.search(r"\bv(\d+\.\d+\.\d+\S*)", out.splitlines()[0] if out else "")
    where = re.search(r"^Install directory:\s*(\S.*?)\s*$", out, re.M)
    return (match.group(1) if match else None), (where.group(1) if where else None)


def local_hermes_version(hermes_bin: str) -> str | None:
    return hermes_version_info(hermes_bin)[0]


# --- docs signal --------------------------------------------------------------------------------------------------

DOC_MAP = Path(__file__).resolve().parent / "data" / "doc-sources.json"
DOC_SUFFIXES = (".md", ".mdx")
DOC_SKIP = ("user-guide/skills/",)  # generated skill catalog pages: one per bundled skill, not platform behavior


def load_doc_map(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    refs = data.get("references")
    if not isinstance(refs, dict) or not all(isinstance(v, list) for v in refs.values()):
        raise ValueError(f"{path}: `references` must map a reference file to a list of docs paths")
    return data


def docs_snapshot(docs: Path, doc_map: dict) -> dict:
    """{files: {path: sha256 | None}, pages: [every docs page]} for the mapped docs under `docs`."""
    mapped = sorted({p for paths in doc_map["references"].values() for p in paths})
    files = {}
    for rel in mapped:
        f = docs / rel
        files[rel] = gate_lib.fingerprint(f.read_text(encoding="utf-8", errors="replace")) if f.is_file() else None
    pages = sorted(p.relative_to(docs).as_posix() for p in docs.rglob("*")
                   if p.suffix in DOC_SUFFIXES and p.is_file()
                   and not p.relative_to(docs).as_posix().startswith(DOC_SKIP))
    return {"files": files, "pages": pages}


def _blob(blobs: Path, sha: str) -> Path:
    return blobs / f"{sha}.md"


def store_blobs(docs: Path, snap: dict, blobs: Path) -> None:
    """Keep a copy of every mapped doc by content hash, so the next change can be diffed against it."""
    blobs.mkdir(parents=True, exist_ok=True)
    for rel, sha in snap["files"].items():
        if sha and not _blob(blobs, sha).is_file():
            _blob(blobs, sha).write_text((docs / rel).read_text(encoding="utf-8", errors="replace"), encoding="utf-8")


def prune_blobs(blobs: Path, *snaps: dict | None) -> None:
    keep = {sha for s in snaps if s for sha in s.get("files", {}).values() if sha}
    for f in blobs.glob("*.md") if blobs.is_dir() else []:
        if f.stem not in keep:
            f.unlink(missing_ok=True)


def refs_for(path: str, doc_map: dict) -> list[str]:
    if path in doc_map["references"].get("_shared", []):
        return ["*"]
    return sorted(ref for ref, paths in doc_map["references"].items() if ref != "_shared" and path in paths)


def docs_changes(old: dict, new: dict, doc_map: dict) -> dict:
    """What changed between two snapshots: changed/removed mapped docs (with the references they feed) and new
    or deleted docs pages. Empty lists everywhere = nothing to review."""
    before = old.get("files") or {}
    changed = [{"path": p, "refs": refs_for(p, doc_map), "status": "removed" if new["files"].get(p) is None else
                ("added" if before.get(p) is None else "changed")}
               for p in sorted(new["files"]) if new["files"].get(p) != before.get(p)]
    old_pages, new_pages = set(old.get("pages", [])), set(new["pages"])
    return {"changed": changed, "new_pages": sorted(new_pages - old_pages),
            "deleted_pages": sorted(old_pages - new_pages)}


def render_docs_diff(docs: Path, old: dict, delta: dict, blobs: Path, max_chars: int, label: str) -> tuple[str, str]:
    """(diff, overflow) markdown: one unified diff per changed mapped doc against its reviewed copy, then the new
    and deleted pages. A section that does not fit the cap goes whole to the overflow text."""
    import difflib
    head = [f"# Hermes docs changed since the last review ({label})", "",
            "Each section names the hermes-platform references the doc feeds (`*` = every reference).", ""]
    sections = []
    for item in delta["changed"]:
        p = item["path"]
        before_sha = old.get("files", {}).get(p)
        before = _blob(blobs, before_sha).read_text(encoding="utf-8") if before_sha and _blob(
            blobs, before_sha).is_file() else ""
        after = (docs / p).read_text(encoding="utf-8", errors="replace") if (docs / p).is_file() else ""
        note = "" if before or not before_sha else " (reviewed copy missing: full text shown)"
        diff = "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                            f"reviewed/{p}", f"current/{p}", n=2))
        sections.append(f"## {p} ({item['status']}){note}\n\nReferences: {', '.join(item['refs']) or 'none'}\n\n"
                        f"```diff\n{diff.rstrip()}\n```\n")
    if delta["new_pages"]:
        sections.append("## New docs pages (not mapped to any reference yet)\n\n"
                        + "".join(f"- {p}\n" for p in delta["new_pages"]))
    if delta["deleted_pages"]:
        sections.append("## Deleted docs pages\n\n" + "".join(f"- {p}\n" for p in delta["deleted_pages"]))
    out, spilled, used = "\n".join(head), [], len("\n".join(head))
    for s in sections:
        if used + len(s) + 200 <= max_chars:
            out += s + "\n"
            used += len(s) + 1
        else:
            spilled.append(s)
    if spilled:
        out += f"\n{len(spilled)} sections over the cap are in the overflow file.\n"
    return out, ("# Hermes docs sections over the cap\n\n" + "\n".join(spilled) if spilled else "")


def base_version(version: str | None) -> str | None:
    """A git install reports `0.22.0+2.gd97007c`; only the release part is a change, so a build bump
    (every `hermes update`) never wakes the digest agent."""
    return version.split("+")[0] if version else version


# --- run --------------------------------------------------------------------------------------------------------

def digest_written_since(sdir: Path, since: float) -> bool:
    """True when the digest agent wrote <state>/digests/*.json at or after `since` (epoch seconds)."""
    digests = sdir / "digests"
    return digests.is_dir() and any(p.stat().st_mtime >= since for p in digests.glob("*.json"))


def run(opts) -> dict:
    sdir = gate_lib.state_dir(opts.state_dir)
    state = gate_lib.load_state("watch", sdir)
    errors: list[str] = []
    pending = state.pop("pending", None)
    if isinstance(pending, dict) and digest_written_since(sdir, float(pending.get("since") or 0)):
        # the digest of the last wake exists: what that wake reported is now reviewed
        state["reviewed"] = pending.get("reviewed") or state.get("reviewed")

    if opts.hermes_version:
        local, install_dir = opts.hermes_version, None
    else:
        local, install_dir = hermes_version_info(opts.hermes_bin)
    src = opts.hermes_src or install_dir
    docs_dir = Path(src).expanduser() / "website" / "docs" if src else None
    snap = doc_map = None
    if docs_dir and docs_dir.is_dir():
        try:
            doc_map = load_doc_map(Path(opts.doc_map))
            snap = docs_snapshot(docs_dir, doc_map)
        except (OSError, ValueError) as exc:
            errors.append(f"docs: {exc}"[:300])
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
    }
    delta = None
    if snap is not None:
        old_snap = reviewed.get("docs")
        # no reviewed snapshot yet (first run, or a state from before this signal): seed the baseline silently
        delta = docs_changes(old_snap, snap, doc_map) if isinstance(old_snap, dict) else None
        changes["docs"] = bool(delta and (delta["changed"] or delta["new_pages"] or delta["deleted_pages"]))
    wake = any(changes.values())

    context: dict = {"gate": "watch_upstream", "source": rel["source"], "changed": [k for k, v in changes.items() if v]}
    files: list[dict] = []
    if fresh:
        budget = opts.max_chars // len(fresh)
        for item in fresh:
            full = sdir / "releases" / f"{item['tag']}.md"
            filt = sdir / "releases" / f"{item['tag']}.filtered.md"
            over = sdir / "releases" / f"{item['tag']}.overflow.md"
            filtered, overflow = filter_release(item["body"], item["tag"], budget)
            if not opts.dry_run:
                full.parent.mkdir(parents=True, exist_ok=True)
                full.write_text(item["body"])
                filt.write_text(filtered)
                if overflow:
                    over.write_text(overflow)
                else:
                    over.unlink(missing_ok=True)
            entry = {"tag": item["tag"], "full": str(full), "filtered": str(filt),
                     "full_chars": len(item["body"]), "filtered_chars": len(filtered)}
            if overflow:
                entry.update(overflow=str(over), overflow_chars=len(overflow))
            files.append(entry)
        context["tags"] = [f["tag"] for f in files]
        context["release_from"] = reviewed.get("release")
        context["filtered"] = [f["filtered"] for f in files]
        if any("overflow" in f for f in files):
            context["overflow"] = [f["overflow"] for f in files if "overflow" in f]
        context["release_files"] = files
    if changes["hermes"]:
        context["hermes"] = {"from": reviewed.get("hermes"), "to": local}
    blobs = sdir / "docs" / "blobs"
    if changes.get("docs"):
        assert docs_dir is not None and doc_map is not None and delta is not None  # a docs change implies a snapshot
        stamp = time.strftime("%Y-%m-%d")
        diff_file, over_file = sdir / "docs" / f"{stamp}.diff.md", sdir / "docs" / f"{stamp}.overflow.md"
        diff, overflow = render_docs_diff(docs_dir, reviewed["docs"], delta, blobs, opts.max_chars,
                                          f"verified against {doc_map.get('verified_against', '?')}")
        if not opts.dry_run:
            diff_file.parent.mkdir(parents=True, exist_ok=True)
            diff_file.write_text(diff, encoding="utf-8")
            if overflow:
                over_file.write_text(overflow, encoding="utf-8")
            else:
                over_file.unlink(missing_ok=True)
        refs = sorted({r for c in delta["changed"] for r in c["refs"]})
        context["docs"] = {"diff": str(diff_file), "references": refs, "changed": delta["changed"],
                           "new_pages": delta["new_pages"], "deleted_pages": delta["deleted_pages"],
                           "verified_against": doc_map.get("verified_against")}
        if overflow:
            context["docs"]["overflow"] = str(over_file)

    error_count = 0 if (wake or not errors) else int(state.get("error_count", 0)) + 1
    if errors and not wake and error_count >= ERROR_WAKE_AFTER:
        wake, error_count = True, 0
        context["gate_error"] = "; ".join(errors)[:400]
    elif errors:
        context["errors"] = errors

    advanced = {
        "release": newest if changes["release"] else reviewed.get("release"),
        "hermes": local or reviewed.get("hermes"),
    }
    if snap is not None:
        advanced["docs"] = snap
        changes.setdefault("docs", False)
        if not opts.dry_run:
            store_blobs(docs_dir, snap, blobs)  # the copy the next change is diffed against
            prune_blobs(blobs, snap, reviewed.get("docs") if changes["docs"] else None)
    elif isinstance(reviewed.get("docs"), dict):
        advanced["docs"] = reviewed["docs"]  # docs unreadable this run: keep the reviewed snapshot
        changes.setdefault("docs", False)
    now = int(time.time())
    new_state = {
        **state,
        "etag": rel["etag"],
        "latest_tag": newest or cached_latest,
        "checked_at": now,
        "error_count": error_count,
        # a reported change stays unreviewed until its digest exists (see digest_written_since)
        "reviewed": {k: reviewed.get(k) if changes[k] else v for k, v in advanced.items()},
    }
    if any(changes.values()):
        new_state["pending"] = {"since": now, "reviewed": advanced}
    if not opts.dry_run:
        gate_lib.save_state("watch", new_state, sdir)
    report = {"wake": wake, "source": rel["source"], "not_modified": rel["not_modified"], "newest": newest,
              "reviewed": reviewed, "pending": new_state.get("pending"), "local": local,
              "changes": changes, "errors": errors, "first_run": first_run, "dry_run": opts.dry_run,
              "docs": str(docs_dir) if snap is not None else "skipped (no website/docs found)"}
    for key in ("reviewed", "pending"):  # snapshots are bulky state, not report material
        if isinstance(report[key], dict):
            report[key] = {k: v for k, v in report[key].items() if k != "docs"}
    return {"wake": wake, "context": context, "report": report}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=__doc__.split("\n\n", 1)[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="add a `report` object to the gate line")
    ap.add_argument("--dry-run", action="store_true", help="check only: write no state and no files")
    ap.add_argument("--force", action="store_true", help="ignore the stored ETag")
    ap.add_argument("--home", default=str(gate_lib.default_home()), help="builder profile home (default $HERMES_HOME)")
    ap.add_argument("--state-dir", help="state directory (default <home>/local/state)")
    ap.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN", "hermes"),
                    help="hermes executable (default: $HERMES_BIN, else hermes)")
    ap.add_argument("--hermes-version", help="use this local version instead of running `hermes --version`")
    ap.add_argument("--hermes-src", help="Hermes source root for the docs signal (default: the `Install directory:` "
                    "line of `hermes --version`; with --hermes-version and no --hermes-src the docs signal is off)")
    ap.add_argument("--doc-map", default=str(DOC_MAP), help="reference -> docs map (default scripts/data/doc-sources.json)")
    ap.add_argument("--releases-url", default=RELEASES_URL, help="GitHub releases API URL (tests)")
    ap.add_argument("--atom-url", default=ATOM_URL, help="releases.atom fallback URL (tests)")
    ap.add_argument("--max-chars", type=int, default=15000, help="cap for the filtered output of one run")
    ap.add_argument("--timeout", type=int, default=20, help="HTTP timeout in seconds (default 20)")
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
