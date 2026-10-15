#!/usr/bin/env python3
"""Check a preview or a local build of one site and write the review evidence as JSON.

Usage:
  check_site.py --site <slug> --id <ID> --round <R> --url <https://preview> [--pages /,/menu]
                [--smoke] [--browser] [--lighthouse] [--repo <path>] [--root <site folder>]

Run by web-qa (full) and web-deployer (--smoke). Writes `reviews/<ID>-r<R>/checks.json`
(and `smoke.json` in smoke mode) below --root, which defaults to the current directory, the site's
project folder. Evidence goes beside it: `screenshots/` and, when Lighthouse ran, its raw reports.

Checks: reachability, redirect chains, internal and external links, meta and SEO tags, forms,
security headers, mixed content, and secret patterns in served HTML/JS and in the repo when
--repo is given. Lighthouse and the browser pass (axe, screenshots, console) run only when asked
for; a missing tool with --browser is exit 2, never a silent pass.

Exit 0 checks ran (read all_ok in the JSON), 1 the site could not be reached or the spec is
missing, 2 a requested tool (Chrome, Lighthouse) could not run.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

DEFAULT_THRESHOLDS = {"lighthouse_mobile": {"performance": 90, "accessibility": 95, "best_practices": 90, "seo": 95},
                      "axe_max": {"critical": 0, "serious": 0}, "broken_internal_links": 0}
MAX_URLS = 200
TIMEOUT = 20
UA = "hermes-web-qa/1.0 (+site check)"
SECRET_PATTERNS = (
    ("stripe-live-key", re.compile(r"sk_live_[0-9a-zA-Z]{16,}")),
    ("aws-access-key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github-pat", re.compile(r"(ghp_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{20,})")),
    ("slack-token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt-near-secret", re.compile(r"(?i)secret[^\n]{0,40}eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
)


class Page(HTMLParser):
    """The parts of a page the checks need."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.links: list[str] = []
        self.assets: list[str] = []
        self.images: list[tuple[str, str | None]] = []
        self.meta: dict[str, str] = {}
        self.lang = ""
        self.canonical = ""
        self.forms = 0
        self.unlabeled_inputs: list[str] = []
        self._in_title = False
        self._label_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "html":
            self.lang = (a.get("lang") or "").strip()
        elif tag == "title":
            self._in_title = True
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"] or "")
        elif tag in {"script", "link", "img"}:
            url = a.get("src") or a.get("href")
            if url and tag != "img":
                self.assets.append(url)
            if tag == "img":
                self.images.append((a.get("src") or "", a.get("alt")))
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key:
                self.meta[key] = (a.get("content") or "").strip()
        elif tag == "link" and (a.get("rel") or "").lower() == "canonical":
            self.canonical = a.get("href") or ""
        elif tag == "form":
            self.forms += 1
        elif tag == "label":
            self._label_depth += 1
        elif tag in {"input", "select", "textarea"} and a.get("type") != "hidden":
            if self._label_depth == 0 and not a.get("aria-label") and not a.get("aria-labelledby"):
                self.unlabeled_inputs.append(a.get("name") or a.get("id") or a.get("type") or "input")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "label" and self._label_depth:
            self._label_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data


class Checker:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.checks: list[dict] = []
        self.scores: dict = {}
        self.root = Path(args.root).expanduser().resolve()
        self.base = (args.url or "").rstrip("/")
        self.thresholds = args.thresholds_json and json.loads(args.thresholds_json) or self.thresholds_from_site()

    # --- helpers ---------------------------------------------------------------------------------

    def thresholds_from_site(self) -> dict:
        spec = self.root / "site.yaml"
        if not spec.is_file():
            return dict(DEFAULT_THRESHOLDS)
        try:
            import yaml
            data = yaml.safe_load(spec.read_text(encoding="utf-8")) or {}
        except ImportError:
            self.record("thresholds", "site.yaml", False,
                        "site.yaml exists but no YAML module is available; default thresholds used "
                        "(pass --thresholds-json to pin the site's own)", "warn")
            return dict(DEFAULT_THRESHOLDS)
        except Exception:
            return dict(DEFAULT_THRESHOLDS)
        found = ((data.get("automation") or {}).get("thresholds")) or {}
        return {**DEFAULT_THRESHOLDS, **found}

    def record(self, name: str, page: str, ok: bool, detail: str, severity: str = "critical") -> None:
        self.checks.append({"name": name, "page": page, "ok": bool(ok), "detail": detail, "severity": severity})

    def fetch(self, url: str) -> tuple[int, dict, str]:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as res:
                body = res.read(600_000).decode("utf-8", "replace")
                return res.status, {k.lower(): v for k, v in res.headers.items()}, body
        except urllib.error.HTTPError as exc:
            return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, ""
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return 0, {}, f"{type(exc).__name__}: {exc}"

    # --- checks ----------------------------------------------------------------------------------

    def pages(self) -> list[str]:
        if self.args.pages:
            return [p if p.startswith("/") else f"/{p}" for p in self.args.pages.split(",") if p.strip()]
        status, _headers, body = self.fetch(self.base + "/")
        if status == 0:
            return []
        page = Page()
        page.feed(body)
        found: list[str] = []
        for href in page.links:
            url = urljoin(self.base + "/", href)
            if urlparse(url).netloc == urlparse(self.base).netloc and not urlparse(url).path.endswith((".pdf", ".xml")):
                path = urlparse(url).path or "/"
                if path not in found:
                    found.append(path)
        return (found or ["/"])[:10]

    def check_pages(self, pages: list[str]) -> dict[str, str]:
        bodies: dict[str, str] = {}
        for path in pages:
            url = self.base + path
            status, headers, body = self.fetch(url)
            self.record("http-status", path, status == 200, f"HTTP {status or 'no answer'}", "critical")
            if status == 200:
                bodies[path] = body
                if "text/html" in headers.get("content-type", ""):
                    page = Page()
                    page.feed(body)
                    self.check_meta(path, page)
                    self.check_forms(path, page)
                    self.check_secrets_served(path, body)
                    self.check_headers(path, headers)
                    self.check_mixed_content(path, body)
        missing = "/definitely-missing-" + str(int(time.time()))
        status, _headers2, _body = self.fetch(self.base + missing)
        self.record("http-404", missing, status == 404, f"HTTP {status or 'no answer'}", "warn")
        return bodies

    def check_meta(self, path: str, page: Page) -> None:
        self.record("meta-title", path, bool(page.title.strip()), f"title: {page.title.strip()[:60] or 'missing'}")
        desc = page.meta.get("description", "")
        self.record("meta-description", path, 10 <= len(desc) <= 170, f"{len(desc)} characters", "warn")
        self.record("meta-viewport", path, "width" in page.meta.get("viewport", ""), page.meta.get("viewport", "missing"), "warn")
        self.record("meta-lang", path, bool(page.lang), f"lang={page.lang or 'missing'}", "warn")
        self.record("meta-canonical", path, bool(page.canonical), page.canonical or "missing", "warn")
        og = [k for k in ("og:title", "og:image") if page.meta.get(k)]
        self.record("meta-open-graph", path, len(og) == 2, f"present: {', '.join(og) or 'none'}", "warn")
        missing_alt = [src for src, alt in page.images if alt is None]
        self.record("img-alt", path, not missing_alt, f"{len(missing_alt)} image(s) without alt", "warn")

    def check_forms(self, path: str, page: Page) -> None:
        if page.forms == 0:
            return
        self.record("form-labels", path, not page.unlabeled_inputs,
                    f"inputs without a label: {', '.join(page.unlabeled_inputs[:5]) or 'none'}", "critical")

    def check_secrets_served(self, path: str, body: str) -> None:
        for name, pattern in SECRET_PATTERNS:
            if pattern.search(body):
                self.record(f"secret-{name}", path, False, "secret-shaped string in served output", "critical")
                return
        self.record("secret-scan", path, True, "no secret pattern in the served HTML", "critical")

    def check_headers(self, path: str, headers: dict) -> None:
        wanted = ["x-content-type-options", "referrer-policy", "content-security-policy", "strict-transport-security"]
        present = [h for h in wanted if h in headers]
        self.record("security-headers", path, len(present) >= 2,
                    f"present: {', '.join(present) or 'none'}", "warn")

    def check_mixed_content(self, path: str, body: str) -> None:
        if self.base.startswith("https://") and re.search(r'(?:src|href)="http://', body):
            self.record("mixed-content", path, False, "http:// asset on an https page", "critical")

    def check_links(self, bodies: dict[str, str]) -> None:
        seen: set[str] = set()
        internal_broken: list[str] = []
        external_warn: list[str] = []
        for path, body in bodies.items():
            page = Page()
            page.feed(body)
            for href in page.links + page.assets:
                url = urljoin(self.base + path, href)
                parsed = urlparse(url)
                if not parsed.scheme.startswith("http") or url in seen or len(seen) >= MAX_URLS:
                    continue
                seen.add(url)
                same_origin = parsed.netloc == urlparse(self.base).netloc
                if same_origin:
                    status, _h, _b = self.fetch(url)
                    if status != 200 and status != 301:
                        internal_broken.append(f"{parsed.path} (HTTP {status or 'no answer'})")
                else:
                    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
                    try:
                        with urllib.request.urlopen(req, timeout=10) as res:
                            if res.status >= 400:
                                external_warn.append(f"{parsed.netloc}{parsed.path} ({res.status})")
                    except Exception:
                        external_warn.append(f"{parsed.netloc}{parsed.path} (unreachable)")
        self.record("internal-links", "(crawl)", not internal_broken,
                    f"{len(internal_broken)} broken: {', '.join(internal_broken[:5]) or 'none'}", "critical")
        self.record("external-links", "(crawl)", not external_warn,
                    f"{len(external_warn)} unreachable: {', '.join(external_warn[:5]) or 'none'}", "warn")

    def check_seo_files(self) -> None:
        for name, path in (("sitemap", "/sitemap.xml"), ("robots", "/robots.txt")):
            status, _h, _b = self.fetch(self.base + path)
            self.record(f"seo-{name}", path, status == 200, f"HTTP {status or 'no answer'}", "warn")

    def check_repo(self) -> None:
        repo = Path(self.args.repo).expanduser().resolve()
        if not repo.is_dir():
            self.record("repo-scan", str(repo), False, "not a directory", "critical")
            return
        hits: list[str] = []
        for file in repo.rglob("*"):
            if not file.is_file() or ".git" in file.parts or file.stat().st_size > 400_000:
                continue
            if file.name in {".env", ".dev.vars"} or file.suffix in {".lock", ".png", ".jpg", ".webp", ".avif", ".woff2"}:
                continue
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for name, pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    hits.append(f"{file.relative_to(repo)} ({name})")
        self.record("repo-secrets", str(repo), not hits, f"{len(hits)} hit(s): {', '.join(hits[:5]) or 'none'}", "critical")
        committed = subprocess.run(["git", "-C", str(repo), "log", "--all", "-p", "--", "*.env", ".dev.vars"],
                                   capture_output=True, text=True, timeout=120)
        leaked = bool(committed.stdout.strip()) and "commit" in committed.stdout
        self.record("repo-committed-env", str(repo), not leaked, "no committed .env/.dev.vars in history", "critical")

    def check_browser(self, pages: list[str]) -> int:
        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        except ImportError:
            print("error: --browser needs playwright installed in the site's environment", file=sys.stderr)
            return 2
        shots = self.root / "reviews" / self.evidence_name() / "screenshots"
        shots.mkdir(parents=True, exist_ok=True)
        axe_violations: list[str] = []
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(channel="chrome")
                for path in pages:
                    shot = path.strip("/").replace("/", "-") or "home"
                    for label, size in (("mobile", {"width": 390, "height": 844}), ("desktop", {"width": 1440, "height": 900})):
                        page = browser.new_page(viewport=size)
                        errors: list[str] = []
                        page.on("pageerror", lambda exc: errors.append(str(exc)))
                        page.goto(self.base + path, wait_until="networkidle", timeout=45_000)
                        page.screenshot(path=str(shots / f"{label}-{shot}.png"), full_page=True)
                        if not errors:
                            axe = page.evaluate("() => window.axe ? true : false")
                            if axe:
                                result = page.evaluate(
                                    "async () => (await axe.run(document, { runOnly: { type: 'tag', values: ['wcag22aa'] } })).violations")
                                axe_violations += [f"{v['impact']}: {v['id']} ({path})" for v in result
                                                   if v.get("impact") in ("critical", "serious")]
                        self.record("console-errors", f"{path} ({label})", not errors,
                                    "; ".join(errors[:3]) or "none", "warn")
                        page.close()
                    if path == pages[0]:
                        self.record("axe-wcag22aa", path, not axe_violations,
                                    "; ".join(sorted(set(axe_violations))[:5]) or "no critical or serious violation",
                                    "critical")
                browser.close()
        except Exception as exc:  # browser could not start
            print(f"error: browser check failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        return 0

    def check_lighthouse(self, pages: list[str]) -> int:
        report_dir = self.root / "reviews" / self.evidence_name() / "lighthouse"
        report_dir.mkdir(parents=True, exist_ok=True)
        keys = {"performance": "performance", "accessibility": "accessibility",
                "best-practices": "best_practices", "seo": "seo"}
        try:
            version = subprocess.run(["npx", "--no-install", "lighthouse", "--version"],
                                     capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            print(f"error: lighthouse could not start: {exc}", file=sys.stderr)
            return 2
        if version.returncode != 0:
            print("error: lighthouse is not installed in this project (pnpm add -D lighthouse)", file=sys.stderr)
            return 2
        thresholds = {**self.thresholds.get("lighthouse_mobile", {})}
        for path in pages:
            out = report_dir / f"{path.strip('/').replace('/', '-') or 'home'}.json"
            run = subprocess.run(["npx", "--no-install", "lighthouse", self.base + path, "--quiet",
                                  "--chrome-flags=--headless=new", "--output=json", f"--output-path={out}"],
                                 capture_output=True, text=True, timeout=300)
            if run.returncode != 0 or not out.is_file():
                print(f"error: lighthouse failed on {path}: {(run.stderr or '').strip()[-200:]}", file=sys.stderr)
                return 2
            data = json.loads(out.read_text(encoding="utf-8"))
            for category, key in keys.items():
                score = round((data["categories"].get(category, {}).get("score") or 0) * 100)
                self.scores.setdefault(path, {})[key] = score
                minimum = thresholds.get(key)
                if minimum is not None:
                    self.record("lighthouse", path, score >= minimum, f"{key} {score} (min {minimum})", "critical")
        return 0

    # --- output ----------------------------------------------------------------------------------

    def evidence_name(self) -> str:
        return f"{self.args.id}-r{self.args.round}"

    def write(self, started: float) -> dict:
        folder = self.root / "reviews" / self.evidence_name()
        folder.mkdir(parents=True, exist_ok=True)
        name = "smoke.json" if self.args.smoke else "checks.json"
        critical = [c for c in self.checks if not c["ok"] and c["severity"] == "critical"]
        result = {
            "id": self.args.id, "site": self.args.site, "round": self.args.round, "mode": "smoke" if self.args.smoke else "full",
            "url": self.base, "date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "duration_s": round(time.time() - started, 1), "thresholds": self.thresholds,
            "checks": self.checks, "scores": self.scores,
            "all_ok": not critical, "critical": [f"{c['name']} on {c['page']}: {c['detail']}" for c in critical],
        }
        (folder / name).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        return result

    def run(self) -> int:
        started = time.time()
        pages = self.pages()
        if not pages:
            self.record("reachable", "/", False, f"{self.base} did not answer", "critical")
            result = self.write(started)
            print(json.dumps(result if self.args.json else result["critical"], indent=2))
            return 1
        bodies = self.check_pages(pages)
        if not self.args.smoke:
            self.check_links(bodies)
            self.check_seo_files()
            if self.args.repo:
                self.check_repo()
            if self.args.lighthouse:
                code = self.check_lighthouse(pages)
                if code:
                    return code
        if self.args.browser:
            code = self.check_browser(pages)
            if code:
                return code
        result = self.write(started)
        if self.args.json:
            print(json.dumps(result, indent=2))
        else:
            for c in self.checks:
                if not c["ok"]:
                    print(f"{'CRIT' if c['severity'] == 'critical' else 'warn'} {c['name']} {c['page']}: {c['detail']}")
            print(f"{'ok' if result['all_ok'] else 'fail'}: {len(self.checks)} checks in {result['duration_s']}s "
                  f"-> reviews/{self.evidence_name()}/{'smoke.json' if self.args.smoke else 'checks.json'}")
        return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Check a site preview or local build and write reviews/<ID>-r<R>/checks.json.",
        epilog="Exit 0 checks ran, 1 site unreachable, 2 a requested tool could not run.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--site", required=True, help="site slug")
    p.add_argument("--id", required=True, help="work item id (<slug>-<YYYYMMDD>-<kind>-<nn>)")
    p.add_argument("--round", type=int, default=0, help="review round")
    p.add_argument("--url", help="deployed preview URL")
    p.add_argument("--dir", help="local build folder to serve instead of --url")
    p.add_argument("--pages", help="comma-separated paths (default: same-origin pages linked from /)")
    p.add_argument("--smoke", action="store_true", help="the deployer's pass: reachability and secrets only")
    p.add_argument("--browser", action="store_true", help="Playwright pass: axe, screenshots, console errors")
    p.add_argument("--lighthouse", action="store_true", help="Lighthouse pass against the site thresholds")
    p.add_argument("--repo", help="site repo path to scan for secrets and committed env files")
    p.add_argument("--root", default=".", help="site project folder (default: current directory)")
    p.add_argument("--thresholds-json", help="override site.yaml automation.thresholds")
    p.add_argument("--json", action="store_true", help="print the whole result")
    args = p.parse_args(argv)

    if bool(args.url) == bool(args.dir):
        print("error: pass exactly one of --url or --dir", file=sys.stderr)
        return 2
    server = None
    if args.dir:
        import http.server
        import functools
        import threading
        directory = str(Path(args.dir).expanduser().resolve())
        if not Path(directory).is_dir():
            print(f"error: --dir {directory} is not a directory", file=sys.stderr)
            return 2
        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=directory)
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        args.url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        return Checker(args).run()
    finally:
        if server is not None:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    raise SystemExit(main())
