#!/usr/bin/env python3
"""Guards the one LinkedIn surface the writer may open: the user's own profile.

The writer drives the shared signed-in browser, so the only thing that keeps it on the user's own profile is a check
that runs before every navigation. `check` allows exactly the own profile, its `/details/<section>/` pages and its
`/edit/` forms, and refuses every other LinkedIn page: another person's profile, the feed, messaging, companies,
jobs, search, settings and the contact-info overlay. Only an `https` address on `www.linkedin.com` (or a two-letter
locale subdomain such as `es.linkedin.com`) is considered, and its path is percent-decoded with its dot segments
resolved before the match: `/in/<own>/edit/../../../in/bob/` is judged as the `/in/bob/` Chrome would load. `record`
stores the slug `/in/me/` resolved to, so the next run knows it without opening the redirect again.

Usage:
  own_profile.py check  URL --own me|<slug> [--json]
  own_profile.py record URL --project P [--today YYYY-MM-DD] [--json]

`--own me` means the slug is not known yet: only `https://www.linkedin.com/in/me/` passes until `record` has stored
it. `record` accepts a URL only when LinkedIn marked it as the viewer's own page (`isSelfProfile=true`, which the
`/in/me/` redirect adds) or when it repeats the slug already stored in `<P>/documents/linkedin/own.json`.

Output is one JSON object on stdout. `check` exits 0 when the page may be opened and 1 when it may not; `record`
exits 0 when the file was written and 1 when the URL was not proof of the own profile; a malformed argument exits 2
with {"error", "code"} on stderr.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, unquote, urlencode, urlsplit

HOSTS = {"www.linkedin.com", "linkedin.com"}
LOCALE_HOST = re.compile(r"^[a-z]{2}\.linkedin\.com$")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,100}$", re.I)
DETAILS = {"experience", "education", "skills", "certifications", "projects", "courses", "honors", "languages",
           "publications", "volunteering", "patents", "featured", "recommendations", "interests", "causes",
           "organizations", "test-scores"}
# The only forms the writer edits: the sections approved rows can name. Every other section is read, never edited.
EDITABLE_DETAILS = {"experience", "education", "skills", "languages"}
# Words that may not appear anywhere under /edit/: the modal and the contact-info form carry the user's private data
# (e-mail, phone, address) and are never needed to rewrite a headline, an About or a role description.
REFUSED_TAIL = ("contact-info", "overlay")
# Under /in/<own>/edit/ only these forms pass: the intro (headline), the About, a position and the section forms. The
# photo, the banner, the public-profile URL settings, the Featured pill and the follow-up prompts LinkedIn opens after a
# save (`forms/next-action/...`: share the new position, people you may know, a Premium upsell) are all refused, so a
# redirect after Save can never lead the writer into a post, an invitation or a setting.
EDIT_ALLOWED = re.compile(r"^(?:intro(?:/new)?|forms/(?:intro|summary)(?:/new)?"
                          r"|forms/(?:position|education|skills?)/(?:new|[0-9]{1,20}))$", re.I)
FORM_ID = re.compile(r"^(?:new|[0-9]{1,20})$")
# The query keys LinkedIn puts on the own profile and its forms (the language tab, the entry point, the self marker).
# Anything else (a redirect target, another profile's URN) is refused rather than passed to the page.
QUERY_KEYS = {"language", "country", "profileformentrypoint", "isselfprofile"}


class UsageError(ValueError):
    def __init__(self, message: str, code: str = "BAD_ARG"):
        super().__init__(message)
        self.code = code


def linkedin_host(host: str) -> bool:
    return host in HOSTS or bool(LOCALE_HOST.match(host))


def parse_url(url: str) -> tuple[str, str, str, str, str]:
    """(scheme, host, resolved path, query, problem) of a LinkedIn URL; a missing scheme is https.

    `problem` names what makes the address unusable before its path is read: not https, a user name before the host,
    a backslash where the host should be, a control character in the path. The path is percent-decoded and its dot
    segments are resolved first, so `/in/<own>/edit/../../../in/bob/` is judged as `/in/bob/` — the page Chrome
    would load — and not as an edit form that starts with the own slug.
    """
    raw = str(url or "").strip()
    if not raw:
        raise UsageError("the URL is empty")
    if "://" not in raw:
        raw = "https://" + raw
    parts = urlsplit(raw)
    scheme = (parts.scheme or "").lower()
    netloc = parts.netloc or ""
    host = (parts.hostname or "").lower().rstrip(".")
    decoded = unquote(parts.path or "/")
    if CONTROL.search(decoded):
        raise UsageError("the path carries a control character", "BAD_URL")
    problem = ""
    if scheme != "https":
        problem = f"{scheme or 'no scheme'}:// is not an https address"
    elif parts.username or parts.password:
        problem = "the address carries a user name before the host"
    elif "\\" in netloc:
        problem = "the address carries a backslash before the host"
    elif re.search(r"%(?:2f|5c|2e)", parts.path or "", re.I):
        problem = "the path carries an encoded slash, backslash or dot"
    path = posixpath.normpath(re.sub(r"/{2,}", "/", decoded))
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and decoded.endswith("/"):
        path += "/"
    return scheme, host, path, parts.query, problem


def segments(path: str) -> list[str]:
    return [seg for seg in path.split("/") if seg]


def refusal(reason: str, kind: str = "other") -> dict:
    return {"allow": False, "reason": reason, "kind": kind}


def check(url: str, own: str) -> dict:
    """Allow the own profile, its details pages and its edit forms; refuse anything else.

    An allowed verdict carries `url`: the address rebuilt from the checked parts (https, the host, the resolved path,
    the allowed query), which is what a caller navigates to, never the raw input.
    """
    try:
        _scheme, host, path, query, problem = parse_url(url)
    except UsageError as exc:
        return refusal(str(exc), "url")
    if problem:
        return refusal(problem, "url")
    if not linkedin_host(host):
        return refusal(f"{host or 'no host'} is not linkedin.com", "host")
    pairs = parse_qsl(query, keep_blank_values=True)
    odd = sorted({k for k, _v in pairs if k.lower() not in QUERY_KEYS})
    if odd:
        return refusal(f"the query carries {', '.join(odd)}: only the language tab and LinkedIn's own markers pass",
                       "url")
    verdict = check_path(host, path, own)
    if verdict.get("allow"):
        verdict["url"] = f"https://{host}{path}" + (f"?{urlencode(pairs)}" if pairs else "")
    return verdict


def check_path(host: str, path: str, own: str) -> dict:
    segs = segments(path)
    if not segs:
        return refusal("the LinkedIn home feed is not a profile", "feed")
    if segs[0].lower() != "in" or len(segs) < 2:
        kind = {"feed": "feed", "messaging": "messaging", "company": "company", "jobs": "jobs",
                "search": "search", "mynetwork": "network", "notifications": "notifications",
                "settings": "settings"}.get(segs[0].lower(), "other")
        return refusal(f"/{segs[0]}/ is not the user's own profile", kind)
    slug, tail = segs[1], segs[2:]
    if slug.lower() == "me":
        if tail:
            return refusal("only /in/me/ itself resolves the own profile; open the recorded slug instead",
                           "unresolved")
        return {"allow": True, "kind": "bootstrap", "own": "me", "path": "/in/me/",
                "reason": "/in/me/ redirects to the user's own profile"}
    if not SLUG_RE.match(slug):
        return refusal(f"{slug!r} is not a profile slug", "other")
    own = str(own or "").strip().strip("/")
    if own.lower() in ("", "me"):
        return refusal("the own profile slug is not recorded yet: open /in/me/ and record it first", "unresolved")
    if slug.lower() != own.lower():
        return refusal(f"/in/{slug}/ is someone else's profile", "other-profile")
    base = f"/in/{own}/"
    if not tail:
        return {"allow": True, "kind": "own_profile", "own": own, "path": base,
                "reason": "the user's own profile"}
    if tail[0].lower() == "details":
        what = (tail[1] if len(tail) > 1 else "").lower()
        if what not in DETAILS:
            return refusal(f"/details/{what or ''}/ is not a section of the own profile", "other")
        rest = [seg.lower() for seg in tail[2:]]
        if not rest:
            return {"allow": True, "kind": "own_details", "own": own, "path": path,
                    "reason": f"the own profile's {what} page"}
        if (what in EDITABLE_DETAILS and len(rest) == 3 and rest[:2] == ["edit", "forms"]
                and FORM_ID.match(rest[2])):
            return {"allow": True, "kind": "own_edit", "own": own, "path": path,
                    "reason": f"the own profile's {what} form"}
        return refusal(f"/details/{what}/{'/'.join(rest)}/ is not a form this skill edits", "not-editable")
    if [seg.lower() for seg in tail] == ["skills", "edit", "forms", "new"]:
        # the skills page's own "Add a skill" link (measured 2026-10-25); its follow-up prompt stays refused
        return {"allow": True, "kind": "own_edit", "own": own, "path": path, "reason": "the own add-skill form"}
    if tail[0].lower() == "edit":
        rest = "/".join(tail[1:]).lower()
        if any(word in rest for word in REFUSED_TAIL):
            return refusal("contact info is private and is never needed to optimise a profile", "private")
        if not EDIT_ALLOWED.match(rest):
            return refusal(f"/edit/{rest}/ is not a profile field: photo, banner, URL settings, Featured and the "
                           "follow-up prompts after a save (share, invitations, upsell) are never opened",
                           "not-editable")
        return {"allow": True, "kind": "own_edit", "own": own, "path": path,
                "reason": "an edit form on the own profile"}
    if tail[0].lower() == "overlay":
        return refusal("overlays carry contact details or other people's data; the edit forms are enough", "private")
    return refusal(f"/in/{own}/{'/'.join(tail)}/ is not a page this skill reads", "other")


def own_file(project: Path) -> Path:
    return project / "documents" / "linkedin" / "own.json"


def read_own(project: Path) -> dict:
    try:
        data = json.loads(own_file(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def record(url: str, project: Path, today: str) -> dict:
    """Store the slug /in/me/ resolved to; only proof of the own profile is accepted."""
    _scheme, host, path, query, problem = parse_url(url)
    if problem:
        raise UsageError(problem, "BAD_URL")
    if not linkedin_host(host):
        raise UsageError(f"{host or 'no host'} is not linkedin.com", "BAD_URL")
    segs = segments(path)
    if len(segs) != 2 or segs[0].lower() != "in" or not SLUG_RE.match(segs[1]):
        return refusal("only /in/<slug>/ is recorded", "other")
    slug = segs[1]
    if slug.lower() == "me":
        return refusal("/in/me/ is the redirect: record the address it landed on", "unresolved")
    marked = str((parse_qs(query).get("isSelfProfile") or [""])[0]).lower() == "true"
    stored = str(read_own(project).get("slug") or "")
    if not marked and slug.lower() != stored.lower():
        return refusal("the URL carries no isSelfProfile marker and does not match the stored slug", "unproven")
    data = {"slug": slug, "path": f"/in/{slug}/", "url": f"https://www.linkedin.com/in/{slug}/",
            "recorded": today}
    target = own_file(project)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return {"allow": True, "kind": "recorded", "own": slug, **data, "file": str(target)}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="may this page be opened?")
    c.add_argument("url")
    c.add_argument("--own", required=True, help="`me` before the slug is recorded, else the own profile slug")
    c.add_argument("--json", action="store_true")
    r = sub.add_parser("record", help="store the slug /in/me/ resolved to")
    r.add_argument("url")
    r.add_argument("--project", required=True)
    r.add_argument("--today", default=date.today().isoformat())
    r.add_argument("--json", action="store_true")
    ns = p.parse_args(argv)
    try:
        if ns.cmd == "check":
            out = check(ns.url, ns.own)
        else:
            if not Path(ns.project).is_dir():
                raise UsageError("--project must be an existing folder")
            out = record(ns.url, Path(ns.project), ns.today)
    except UsageError as exc:
        sys.stderr.write(json.dumps({"error": str(exc), "code": exc.code}) + "\n")
        return 2
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    elif out["allow"]:
        print(f"allow {out['kind']}: {out.get('path') or out.get('url')}")
    else:
        print(f"refuse {out['kind']}: {out['reason']}")
    return 0 if out["allow"] else 1


if __name__ == "__main__":
    sys.exit(main())
