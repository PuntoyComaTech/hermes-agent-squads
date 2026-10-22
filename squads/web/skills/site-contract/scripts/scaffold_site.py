#!/usr/bin/env python3
"""Stack skeletons (pinned in stacks.json beside this script), used by site_base.py.

Not a tool for the bots: run site_base.py, which writes the skeleton together with the strict quality gate. Run
directly, this prints that and exits 2.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STACKS_FILE = HERE / "stacks.json"
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

GITIGNORE = """node_modules/
dist/
build/
.next/
.astro/
coverage/
playwright-report/
.env
.env.*
.dev.vars
*.local
.DS_Store
"""

TSCONFIG = """{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noImplicitReturns": true,
    "noPropertyAccessFromIndexSignature": true,
    "noFallthroughCasesInSwitch": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "forceConsistentCasingInFileNames": true,
    "isolatedModules": true,
    "verbatimModuleSyntax": true,
    "noEmit": true,
    "skipLibCheck": true,
    "target": "ES2024",
    "lib": ["ES2024", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx"
  }
}
"""

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


def header_files(stack: str, provider: str) -> dict[str, str]:
    """The response headers every site ships, in the form its host reads: Next in next.config.ts, a static site as
    `public/_headers` (Cloudflare) or vercel.json (Vercel). TanStack Start renders on the server: its headers belong
    in the server middleware, the first card of that stack (site-contract references/project-base.md)."""
    if stack == "nextjs":
        rows = ",\n".join(f'          {{ key: "{k}", value: "{v}" }}' for k, v in SECURITY_HEADERS.items())
        return {"next.config.ts": 'import type { NextConfig } from "next";\n\nconst config: NextConfig = {\n'
                                  "  async headers() {\n    return [\n      {\n        source: \"/:path*\",\n"
                                  f"        headers: [\n{rows},\n        ],\n      }},\n    ];\n  }},\n}};\n\n"
                                  "export default config;\n"}
    if stack != "astro":
        return {}
    if provider == "vercel":
        doc = {"headers": [{"source": "/(.*)", "headers": [{"key": k, "value": v}
                                                           for k, v in SECURITY_HEADERS.items()]}]}
        return {"vercel.json": json.dumps(doc, indent=2) + "\n"}
    return {"public/_headers": "/*\n" + "".join(f"  {k}: {v}\n" for k, v in SECURITY_HEADERS.items())}


WELCOME = "# {name}\n\nScaffolded by the web squad's `scaffold_site.py` from `stacks.json`.\n"


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


def package_json(stacks: dict, stack: str, name: str) -> str:
    spec = stacks["stacks"][stack]
    scripts = {**spec["scripts"], "test": "vitest run", "e2e": "playwright test",
               "lint": "biome check .", "format": "biome check --write ."}
    doc = {
        "name": name,
        "private": True,
        "type": "module",
        "scripts": scripts,
        "dependencies": dict(sorted(spec["dependencies"].items())),
        "devDependencies": dict(sorted({**stacks["devDependencies"], **spec["devDependencies"]}.items())),
    }
    return json.dumps(doc, indent=2) + "\n"


def astro_config() -> str:
    return "import { defineConfig } from \"astro/config\";\nimport tailwindcss from \"@tailwindcss/vite\";\n\nexport default defineConfig({\n  vite: { plugins: [tailwindcss()] },\n});\n"


def files_for(stacks: dict, stack: str, name: str) -> dict[str, str]:
    files: dict[str, str] = {
        ".gitignore": GITIGNORE,
        "tsconfig.json": TSCONFIG,
        "playwright.config.ts": PLAYWRIGHT,
        "e2e/home.e2e.ts": TEST_SPEC,
        "package.json": package_json(stacks, stack, name),
        "README.md": WELCOME.format(name=name),
    }
    if stack == "astro":
        files["astro.config.mjs"] = astro_config()
        files["src/styles/global.css"] = "@import \"tailwindcss\";\n"
        files["src/pages/index.astro"] = (
            "---\nimport \"../styles/global.css\";\n---\n"
            "<!doctype html>\n<html lang=\"en\">\n  <head>\n    <meta charset=\"utf-8\" />\n"
            "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
            "    <meta name=\"description\" content=\"Replace with the site's own description.\" />\n"
            "    <title>" + name + "</title>\n  </head>\n  <body>\n    <main>\n      <h1>" + name + "</h1>\n"
            "      <p>Replace this skeleton with the milestone's pages.</p>\n    </main>\n  </body>\n</html>\n"
        )
    elif stack == "nextjs":
        files["next.config.ts"] = "import type { NextConfig } from \"next\";\n\nconst config: NextConfig = {};\n\nexport default config;\n"
        files["postcss.config.mjs"] = "export default { plugins: { \"@tailwindcss/postcss\": {} } };\n"
        files["src/app/globals.css"] = "@import \"tailwindcss\";\n"
        files["src/app/layout.tsx"] = (
            "import type { ReactNode } from \"react\";\nimport \"./globals.css\";\n\n"
            "export const metadata = { title: \"" + name + "\", description: \"\" };\n\n"
            "export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {\n"
            "  return (\n    <html lang=\"en\">\n      <body>{children}</body>\n    </html>\n  );\n}\n"
        )
        files["src/app/page.tsx"] = (
            "export default function Home() {\n  return (\n    <main>\n      <h1>" + name + "</h1>\n"
            "      <p>Replace this skeleton with the milestone's pages.</p>\n    </main>\n  );\n}\n"
        )
    elif stack == "tanstack":
        files["vite.config.ts"] = (
            "import { defineConfig } from \"vite\";\nimport tailwindcss from \"@tailwindcss/vite\";\n"
            "import { tanstackStart } from \"@tanstack/react-start/plugin/vite\";\n"
            "import viteReact from \"@vitejs/plugin-react\";\n\n"
            "export default defineConfig({ plugins: [tailwindcss(), tanstackStart(), viteReact()] });\n"
        )
        files["src/router.tsx"] = (
            "import { createRouter } from \"@tanstack/react-router\";\nimport { routeTree } from \"./routeTree.gen\";\n\n"
            "export function getRouter() {\n  return createRouter({ routeTree, scrollRestoration: true });\n}\n"
        )
        files["src/styles/app.css"] = "@import \"tailwindcss\";\n"
        files["src/routes/__root.tsx"] = (
            "/// <reference types=\"vite/client\" />\n"
            "import { HeadContent, Outlet, Scripts, createRootRoute } from \"@tanstack/react-router\";\n"
            "import appCss from \"../styles/app.css?url\";\n\n"
            "export const Route = createRootRoute({\n  head: () => ({\n"
            "    meta: [{ charSet: \"utf-8\" }, { name: \"viewport\", content: \"width=device-width, initial-scale=1\" }, "
            "{ title: \"" + name + "\" }],\n    links: [{ rel: \"stylesheet\", href: appCss }],\n  }),\n"
            "  component: RootComponent,\n});\n\n"
            "function RootComponent() {\n  return (\n    <html lang=\"en\">\n      <head>\n        <HeadContent />\n      </head>\n"
            "      <body>\n        <Outlet />\n        <Scripts />\n      </body>\n    </html>\n  );\n}\n"
        )
        files["src/routes/index.tsx"] = (
            "import { createFileRoute } from \"@tanstack/react-router\";\n\n"
            "export const Route = createFileRoute(\"/\")({ component: Home });\n\n"
            "function Home() {\n  return (\n    <main>\n      <h1>" + name + "</h1>\n"
            "      <p>Replace this skeleton with the milestone's pages.</p>\n    </main>\n  );\n}\n"
        )
    return files


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
          "(skeleton plus the strict quality gate)", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
