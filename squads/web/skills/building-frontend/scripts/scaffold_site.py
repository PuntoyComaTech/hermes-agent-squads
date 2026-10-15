#!/usr/bin/env python3
"""Write a pinned project skeleton for one of the squad's stacks, from stacks.json beside this script.

Writes files only: no package install, no git, no network. Exit 0 written or dry run, 1 target not empty
without --force, 2 usage or data error.
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

BIOME_JSON = """{
  "$schema": "https://biomejs.dev/schemas/2.5.15/schema.json",
  "formatter": { "enabled": true, "indentStyle": "space", "indentWidth": 2, "lineEnding": "lf", "lineWidth": 100 },
  "javascript": { "formatter": { "quoteStyle": "double", "semicolons": "always", "trailingCommas": "all" } },
  "linter": { "enabled": true, "rules": { "recommended": true } },
  "vcs": { "enabled": true, "clientKind": "git", "useIgnoreFile": true }
}
"""

TSCONFIG = """{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "forceConsistentCasingInFileNames": true,
    "isolatedModules": true,
    "verbatimModuleSyntax": true,
    "noEmit": true,
    "skipLibCheck": false,
    "target": "ES2022",
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
  use: { baseURL: process.env.PREVIEW_URL ?? "http://127.0.0.1:4321" },
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
    scripts = {**spec["scripts"], "test": "vitest run --passWithNoTests", "e2e": "playwright test",
               "lint": "biome check .", "format": "biome format --write ."}
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
        "biome.json": BIOME_JSON,
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
            "---\nimport \"../styles/global.css\";\nconst title = \"" + name + "\";\n---\n"
            "<!doctype html>\n<html lang=\"en\">\n  <head>\n    <meta charset=\"utf-8\" />\n"
            "    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />\n"
            "    <meta name=\"description\" content=\"Replace with the site's own description.\" />\n"
            "    <title>{title}</title>\n  </head>\n  <body>\n    <main>\n      <h1>{title}</h1>\n"
            "      <p>Replace this skeleton with the milestone's pages.</p>\n    </main>\n  </body>\n</html>\n"
        )
    elif stack == "nextjs":
        files["next.config.ts"] = "import type { NextConfig } from \"next\";\n\nconst config: NextConfig = {};\n\nexport default config;\n"
        files["postcss.config.mjs"] = "export default { plugins: { \"@tailwindcss/postcss\": {} } };\n"
        files["src/app/globals.css"] = "@import \"tailwindcss\";\n"
        files["src/app/layout.tsx"] = (
            "import type { ReactNode } from \"react\";\nimport \"./globals.css\";\n\n"
            "export const metadata = { title: \"" + name + "\", description: \"\" };\n\n"
            "export default function RootLayout({ children }: { children: ReactNode }) {\n"
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
    p = argparse.ArgumentParser(
        description="Write a pinned project skeleton for one of the squad's stacks.",
        epilog="Exit 0 written or dry run, 1 target not empty without --force, 2 usage or data error.")
    p.add_argument("--stack", help="astro | nextjs | tanstack (see stacks.json)")
    p.add_argument("--name", help="project name (lowercase, dashes)")
    p.add_argument("--dir", default=".", help="target directory (default: current)")
    p.add_argument("--force", action="store_true", help="write into a directory that already has files")
    p.add_argument("--dry-run", action="store_true", help="list the files, write nothing")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--list", action="store_true", help="list the available stacks and exit")
    args = p.parse_args(argv)

    stacks = load_stacks()
    if args.list:
        rows = [{"stack": key, "type": spec.get("type"), "why": spec.get("why"),
                 "dependencies": spec.get("dependencies")} for key, spec in sorted(stacks["stacks"].items())]
        print(json.dumps(rows, indent=2) if args.json else "\n".join(f"  {r['stack']}: {r['type']} - {r['why']}" for r in rows))
        return 0
    if not args.stack or not args.name:
        print("error: --stack and --name are required (or --list)", file=sys.stderr)
        return 2
    if args.stack not in stacks["stacks"]:
        print(f"error: unknown stack {args.stack!r}; available: {', '.join(sorted(stacks['stacks']))}", file=sys.stderr)
        return 2
    if not NAME_RE.match(args.name):
        print("error: --name must be lowercase kebab-case, 40 characters or less", file=sys.stderr)
        return 2

    target = Path(args.dir).expanduser().resolve()
    occupied = busiest(target)
    if occupied and not args.force:
        print(f"error: {target} is not empty ({', '.join(occupied[:5])}); pass --force to write anyway", file=sys.stderr)
        return 1

    files = files_for(stacks, args.stack, args.name)
    written = write_tree(target, files, args.dry_run)
    result = {"stack": args.stack, "name": args.name, "dir": str(target), "dry_run": args.dry_run,
              "files": written, "next": ["pnpm install", "pnpm build"]}
    print(json.dumps(result, indent=2) if args.json else
          "\n".join([f"{'would write' if args.dry_run else 'wrote'} {rel}" for rel in written])
          + "\nnext: pnpm install && pnpm build")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
