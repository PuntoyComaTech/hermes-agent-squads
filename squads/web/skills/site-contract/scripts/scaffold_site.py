#!/usr/bin/env python3
"""Stack facts for site_base.py: the official create command of each stack (stacks.json beside this script), the
response headers every site ships, and the few squad files the create CLIs do not write (an end-to-end smoke test).

Not a tool for the bots: run site_base.py, which runs the create CLI and lays the strict quality gate on top. Run
directly, this prints that and exits 2.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STACKS_FILE = HERE / "stacks.json"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

# lines the squad needs ignored; appended to the create CLI's own .gitignore when missing
GITIGNORE_EXTRA = ("coverage/", "playwright-report/", "test-results/", ".env*", ".dev.vars", ".wrangler/",
                   ".hermes-live/", ".DS_Store")

PLAYWRIGHT = """import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/*.e2e.ts",
  use: { baseURL: process.env["PREVIEW_URL"] ?? "http://127.0.0.1:4321" },
  reporter: [["list"]],
});
"""

TEST_SPEC = """import { expect, test } from "@playwright/test";

test("home page answers with a title", async ({ page }) => {
  const response = await page.goto("/");
  expect(response?.status()).toBe(200);
  await expect(page).toHaveTitle(/.+/);
});
"""

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    # a baseline that blocks third-party scripts, plugins, framing and form hijacking; inline script and style stay
    # allowed because the stacks inline small bootstraps. Tighten with nonces when a spec needs it.
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' "
                               "'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:; connect-src "
                               "'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'",
}
NEXT_CONFIG_OPEN = re.compile(r"^(const \w+\s*:\s*NextConfig\s*=\s*\{)[ \t]*$", re.M)


def load_stacks() -> dict:
    if not STACKS_FILE.is_file():
        raise SystemExit(f"error: {STACKS_FILE} not found next to this script")
    try:
        data = json.loads(STACKS_FILE.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise SystemExit(f"error: {STACKS_FILE} is not valid JSON: {exc}")
    if not isinstance(data, dict) or not data.get("stacks"):
        raise SystemExit(f"error: {STACKS_FILE} has no stacks: map")
    return data


def dlx(stacks: dict) -> list[str]:
    """`pnpm dlx` under the squad's release-age rule: a create CLI is resolved like any dependency, never newer
    than 3 days."""
    return ["pnpm", f"--config.minimum-release-age={stacks['pnpm']['minimumReleaseAge']}", "dlx"]


def create_argv(stacks: dict, stack: str, target: str, name: str, provider: str) -> list[str]:
    """The stack's official create command, non-interactive, writing into `target`."""
    fill = {"dir": target, "name": name, "provider": provider}
    return dlx(stacks) + [part.format(**fill) for part in stacks["stacks"][stack]["create"]]


def next_headers(config: str) -> str | None:
    """next.config.ts with the security headers added to the config object the create CLI wrote; None when that
    object is not where the CLI puts it (the manager adds them by hand then)."""
    if "async headers()" in config:
        return config
    rows = "".join(f'          {{ key: "{k}", value: "{v}" }},\n' for k, v in SECURITY_HEADERS.items())
    block = ("\n  async headers() {\n    return [\n      {\n        source: \"/:path*\",\n        headers: [\n"
             f"{rows}        ],\n      }},\n    ];\n  }},")
    new, count = NEXT_CONFIG_OPEN.subn(lambda m: m.group(1) + block, config, count=1)
    return new if count else None


def header_files(stack: str, provider: str, repo: Path | None = None) -> dict[str, str]:
    """The response headers every site ships, in the form its host reads: Next in next.config.ts (added to the
    create CLI's file), a static site as `public/_headers` (Cloudflare) or vercel.json (Vercel). TanStack Start
    renders on the server: its headers go in the server middleware, the first api card of that stack."""
    if stack == "nextjs":
        path = (repo / "next.config.ts") if repo else None
        current = path.read_text(encoding="utf-8") if path and path.is_file() else None
        new = next_headers(current) if current is not None else None
        return {"next.config.ts": new} if new and new != current else {}
    if stack != "astro":
        return {}
    if provider == "vercel":
        doc = {"headers": [{"source": "/(.*)", "headers": [{"key": k, "value": v}
                                                           for k, v in SECURITY_HEADERS.items()]}]}
        return {"vercel.json": json.dumps(doc, indent=2) + "\n"}
    return {"public/_headers": "/*\n" + "".join(f"  {k}: {v}\n" for k, v in SECURITY_HEADERS.items())}


def astro_styles(repo: Path) -> dict[str, str]:
    """The home page importing the stylesheet `astro add tailwind` wrote, as Tailwind's Astro guide says: until a
    page imports it, the stylesheet and tailwindcss are unused code (knip fails the gate)."""
    page, sheet = repo / "src" / "pages" / "index.astro", repo / "src" / "styles" / "global.css"
    if not (page.is_file() and sheet.is_file()):
        return {}
    text = page.read_text(encoding="utf-8")
    if "styles/global.css" in text or not text.startswith("---\n"):
        return {}
    return {"src/pages/index.astro": '---\nimport "../styles/global.css";\n' + text[len("---\n"):]}


def gitignore(current: str | None) -> str | None:
    """The create CLI's .gitignore plus the lines the squad needs; None when nothing is missing."""
    have = {ln.strip() for ln in (current or "").splitlines()}
    missing = [ln for ln in GITIGNORE_EXTRA if ln not in have and "/" + ln not in have]
    if not missing:
        return None
    return (current or "").rstrip("\n") + "\n\n# web squad\n" + "\n".join(missing) + "\n"


def write_tree(target: Path, files: dict[str, str], dry: bool) -> list[str]:
    written = []
    for rel, text in sorted(files.items()):
        path = target / rel
        written.append(rel)
        if not dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
    return written


def busiest(target: Path) -> list[str]:
    return sorted(p.name for p in target.iterdir() if p.name != ".git") if target.is_dir() else []


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print("usage: scaffold_site.py (library of site_base.py)\n\n" + (__doc__ or "").strip())
        print("\nExit 2 when run with any other arguments: use site_base.py.")
        return 0
    print("scaffold_site.py is a library: run site_base.py --repo <repo> --stack <stack> --name <slug> --install "
          "(the stack's official create CLI plus the strict quality gate)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
