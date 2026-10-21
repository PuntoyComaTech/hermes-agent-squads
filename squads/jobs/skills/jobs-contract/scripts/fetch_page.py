#!/usr/bin/env python3
"""GET a job page with browser headers, after the robots.txt check. The retry for a 403 from a plain fetch.

Plain fetchers send a bot-identifying user agent, and many corporate, bank and recruiter sites answer that with 403
while serving the same page to a browser. This is the retry, and it is a script rather than a documented curl
command so the grant names one fixed program that can only GET.

Properties (each pinned by tests/test_jobs_intake.py and tests/test_jobs_network.py):
  * GET only. The curl argv is fixed; no request body, form or file is ever sent, and the URL comes after `--` so it
    cannot be parsed as an option.
  * http(s) only. Any other scheme exits 2 before anything else happens.
  * Network guard (robots_check.py): every hop, the first request and each redirect, is checked before it is sent.
    A host on the blocklist is refused by name. A host whose address is loopback, private, link-local (the cloud
    metadata address included), unspecified or otherwise not public is refused. The connection is pinned to the
    address that was checked, and redirects are followed by this script, one checked hop at a time.
  * Blocklist: linkedin.com is always refused here. JOBS_BLOCKLIST (comma-separated host names) and repeatable
    --blocklist HOST add more. The LinkedIn portal CLI (searching-portals) is the only sanctioned reader of LinkedIn.
  * robots.txt is enforced, not advised. robots_check.gate() runs first; a refusal exits 1 with its message. There
    is no flag that skips it.
  * Fetched content never lands in the squad's code. --out defaults to the system temp directory, and a path that
    resolves inside the squad skills tree is refused.
  * Bounded: 45 s, 5 redirects, 10 MB; the size cap is applied after Content-Encoding is undone. curl is required.

Usage:
  python3 fetch_page.py <url> [--out PATH] [--text] [--max-chars N] [--blocklist HOST ...]

Prints `HTTP <code> size=<bytes> saved=<path>` and exits 0 whatever the HTTP status: the status is information for
the escalation order, not a failure. With --text, also prints the tag-stripped text (script, style, noscript, svg and
comments removed, entities unescaped, whitespace folded), capped at --max-chars (default 6000), after a
`--- text ---` line.

Exit codes: 0 fetched; 1 refused (robots policy, blocklist or the network guard: try the employer's own posting);
2 usage or transport error.
"""

import argparse
import hashlib
import html
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from page_decode import decode_page  # noqa: E402
from robots_check import (  # noqa: E402
    BROWSER, GuardError, gate, guarded_fetch, hop_argv, load_blocklist,
)

# The squad's skills tree (…/skills/<squad>/): fetched content must never be written inside it.
CODE_ROOT = HERE.parents[1]
ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
ACCEPT_LANGUAGE = "en-GB,en;q=0.9"
TIMEOUT_SECONDS = 45
MAX_REDIRECTS = 5
MAX_BYTES = 10 * 1024 * 1024


def build_curl_argv(url: str, out: Path) -> list:
    """The curl invocation for one hop of this script: GET, bounded, no redirect following, `--` before the URL."""
    return hop_argv(url, out, ua=BROWSER, accept=ACCEPT, accept_language=ACCEPT_LANGUAGE, target=None,
                    timeout=TIMEOUT_SECONDS, max_bytes=MAX_BYTES)


def fetch(url: str, out: Path, blocklist) -> tuple:
    """(status code, saved bytes). Every hop is guarded; raises GuardError on a refused hop."""
    return guarded_fetch(
        url, out, ua=BROWSER, accept=ACCEPT, accept_language=ACCEPT_LANGUAGE, blocklist=blocklist,
        timeout=TIMEOUT_SECONDS, max_bytes=MAX_BYTES, max_redirects=MAX_REDIRECTS,
    )


def strip_tags(markup: str, limit: int) -> str:
    """Plain text from HTML: drop script, style, noscript, svg and comments; strip tags; unescape; fold whitespace.

    Modern sites embed copy inside JSON blobs, so stray attribute fragments around real text are normal.
    """
    text = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>", " ", markup)
    text = re.sub(r"(?s)<!--.*?-->", " ", text)
    text = html.unescape(re.sub(r"(?s)<[^>]+>", " ", text))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return text[:limit]


def _default_out(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"fetch_page_{digest}.html"


def _inside_code_root(path: Path) -> bool:
    try:
        path.resolve().relative_to(CODE_ROOT)
    except ValueError:
        return False
    return True


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


def main(argv=None) -> int:
    _force_utf8_output()
    parser = argparse.ArgumentParser(
        prog="fetch_page.py",
        description="GET a job page with browser headers, robots.txt enforced; see module docstring.",
    )
    parser.add_argument("url")
    parser.add_argument("--out", type=Path, default=None,
                        help="where to save the body (default: system temp dir; never inside the squad skills tree)")
    parser.add_argument("--text", action="store_true", help="also print the tag-stripped text")
    parser.add_argument("--max-chars", type=int, default=6000, help="cap for --text (default 6000)")
    parser.add_argument("--blocklist", action="append", default=[],
                        help="a host to refuse, in addition to linkedin.com and JOBS_BLOCKLIST (repeatable)")
    args = parser.parse_args(argv)

    scheme = urlsplit(args.url).scheme.lower()
    if scheme not in ("http", "https"):
        print(f"fetch_page: only http(s) URLs are fetched, got scheme {scheme!r}", file=sys.stderr)
        return 2
    try:
        blocklist = load_blocklist(args.blocklist)
    except ValueError as exc:
        print(f"fetch_page: {exc}", file=sys.stderr)
        return 2
    if shutil.which("curl") is None:
        print("fetch_page: curl is required: the network guard pins each request to the address it checked",
              file=sys.stderr)
        return 2

    out = args.out if args.out is not None else _default_out(args.url)
    if _inside_code_root(out):
        print(
            f"fetch_page: refusing to write inside the squad skills tree ({out}); fetched content is untrusted "
            "and belongs in the session scratch directory or the temp directory",
            file=sys.stderr,
        )
        return 2

    rc, message = gate(args.url, blocklist)
    print(message)
    if rc != 0:
        print("fetch_page: refused - this URL is not fetched and the browser-header retry does not run. "
              "Search for the employer's own posting instead.")
        return 1

    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        code, size = fetch(args.url, out, blocklist)
    except GuardError as exc:
        print(f"fetch_page: refused by the network guard: {exc}. Search for the employer's own posting instead.",
              file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - transport failures of any shape: report, exit 2
        print(f"fetch_page: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    print(f"HTTP {code} size={size} saved={out}")
    if args.text:
        print("--- text ---")
        print(strip_tags(decode_page(out.read_bytes()), args.max_chars))
    return 0


if __name__ == "__main__":
    sys.exit(main())
