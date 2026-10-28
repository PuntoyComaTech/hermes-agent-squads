#!/usr/bin/env python3
"""Lay the strict project base of a site repo with the official installers, then the squad's quality gate on top.

Nothing is written by hand that an installer owns. An empty repo starts from the stack's own create CLI (stacks.json:
create-astro, create-next-app, the TanStack CLI), run through `pnpm dlx` under the 3-day release-age rule. Then
`pnpm add <name>@<major>` resolves every package the template named to its newest release that is at least 3 days old,
`pnpm add -D <name>` adds the squad's tools with no version, framework additions go through the framework's own
command (`astro add tailwind`), and Biome starts from its own `biome init`. The squad adds only its policy: the gate
scripts, the strict rule files (Biome's is extended, not copied), the pnpm supply-chain settings, the strict
TypeScript options, the security headers and one seed test.

The gate (`pnpm quality`) is the bar every bot's code must pass from the first commit: strict TypeScript, type
coverage, Biome, oxlint, SonarJS and security lint, dependency-cruiser, jscpd, knip, gitleaks, licenses, osv-scanner
and pnpm audit, the per-file ratchet (zero findings and zero comments on a new file) and the repo-wide regression
baseline, Vitest at 100 % coverage on logic. lefthook runs Biome and the ratchet on every commit and the whole gate
before every push.

An existing repo keeps every file it has (listed under `kept`); a weaker pnpm supply-chain setting is raised to the
base's (`strengthened`). Exit 0 base ready (or dry run), 1 a step failed (the JSON names it and its output tail) or a
strict option needs a hand edit (`manual`), 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates" / "quality"
sys.path.insert(0, str(HERE))
import scaffold_site as sc  # noqa: E402  - same folder: stacks.json and the stack facts
from toolpath import augment_path  # noqa: E402
import security_fix  # noqa: E402
import security_tools  # noqa: E402

BIOME_POLICY = "./tools/quality/biome.strict.jsonc"
QUALITY_PACKAGE = '{\n  "name": "site-quality",\n  "private": true,\n  "type": "module"\n}\n'

SEED_TEST = {
    "src/lib/slug.ts": 'const NON_WORD = /[^a-z0-9]/u;\n\n'
                       'export function slugify(text: string): string {\n'
                       '  const words = text.toLowerCase().split(NON_WORD);\n'
                       '  return words.filter((word) => word.length > 0).join("-");\n}\n',
    "src/lib/slug.test.ts": 'import { describe, expect, it } from "vitest";\nimport { slugify } from "./slug.ts";\n\n'
                            'describe("a url-safe slug", () => {\n  it("makes a url-safe slug", () => {\n'
                            '    expect.hasAssertions();\n'
                            '    expect(slugify("  Hola Mundo! ")).toBe("hola-mundo");\n  }, 5000);\n});\n',
}

STRICT_TS = {
    "strict": True, "noUncheckedIndexedAccess": True, "exactOptionalPropertyTypes": True,
    "noImplicitOverride": True, "noImplicitReturns": True, "noFallthroughCasesInSwitch": True,
    "noUnusedLocals": True, "noUnusedParameters": True, "noPropertyAccessFromIndexSignature": True,
    "useUnknownInCatchVariables": True, "allowUnreachableCode": False, "allowUnusedLabels": False,
    "forceConsistentCasingInFileNames": True, "isolatedModules": True, "verbatimModuleSyntax": True,
    "erasableSyntaxOnly": True, "noUncheckedSideEffectImports": True, "allowImportingTsExtensions": True,
}
GATE = ("types", "lint", "oxlint", "sonar", "arch", "dupes", "unused", "typecov", "secrets", "licenses", "deps",
        "fresh", "ratchet", "regressions", "test")
SCRIPTS = {
    "lint": "biome check .",
    "format": "biome check --write .",
    "test": "vitest run",
    "e2e": "playwright test",
    "quality": " && ".join(f"pnpm run quality:{step}" for step in GATE),
    "quality:lint": "biome ci --error-on-warnings .",
    "quality:oxlint": "node_modules/.bin/oxlint --deny-warnings --config tools/quality/oxlintrc.json "
                      "--ignore-pattern \"**/*.gen.ts\" --ignore-pattern \"src/paraglide/**\" src e2e",
    "quality:sonar": "tools/quality/node_modules/.bin/eslint --config tools/quality/eslint.config.mjs "
                     "--max-warnings=0 .",
    "quality:arch": "tools/quality/node_modules/.bin/depcruise src --config tools/quality/dependency-cruiser.cjs",
    "quality:dupes": "jscpd --config .jscpd.json && jscpd --config .jscpd-css.json",
    "quality:unused": "knip",
    "quality:secrets": "node tools/quality/security.mjs secrets",
    "quality:licenses": "node tools/quality/security.mjs licenses",
    "quality:deps": "node tools/quality/security.mjs deps",
    "quality:fresh": "node tools/quality/fresh.mjs",
    "quality:ratchet": "node tools/quality/ratchet.mjs check",
    "quality:regressions": "node tools/quality/regressions.mjs check",
    "quality:baseline": "node tools/quality/ratchet.mjs record",
    "quality:regressions:record": "node tools/quality/regressions.mjs record",
    "quality:test": "vitest run --coverage",
}
ZERO_RATCHET = "{}\n"
ZERO_REGRESSIONS = '{\n  "clones": 0,\n  "depcruise": 0,\n  "knip": 0\n}\n'
TAIL = 1500


def typecov_command(stack: dict) -> str:
    """type-coverage over the whole project, strict, 100 %. The generated route file and what the stack lists under
    typecov_ignore are the only exceptions (their `any` comes from generated code, not from the builders)."""
    ignore = ["src/routeTree.gen.ts", *stack.get("typecov_ignore", [])]
    # quoted: the script runs in sh, which would expand a glob before type-coverage sees it
    return ("tools/quality/node_modules/.bin/type-coverage -p tsconfig.json --strict --at-least 100"
            + "".join(f" --ignore-files '{path}'" for path in ignore))


def knip_config(stack: dict, provider: str, repo: Path | None = None) -> str:
    """knip.json for the stack: its entry files and source tree (CSS included, so `@import "tailwindcss"` counts as
    a use). Every rule is an error, entry exports included and configuration hints too.
    Lighthouse and axe-core are run by the QA script through npx, wrangler by the deployer: never imported. A
    package the create CLI declared itself (wrangler on a Cloudflare TanStack site) is not ignored: knip's
    configuration-hint check fails an ignore it does not need."""
    pkg_path = (repo / "package.json") if repo else None
    pkg = json.loads(pkg_path.read_text(encoding="utf-8")) if pkg_path and pkg_path.is_file() else {}
    scripts = " ".join((pkg.get("scripts") or {}).values())
    ignored = ["lighthouse", "axe-core", "@babel/parser"]
    if provider == "cloudflare" and "wrangler" not in scripts:
        ignored.append("wrangler")
    doc = {
        "$schema": "https://unpkg.com/knip@6/schema.json",
        "entry": [*(stack.get("entry") or []), "e2e/**/*.e2e.ts"],
        "project": [f"src/**/*.{{ts,tsx,{'astro,' if stack.get('type') == 'static' else ''}css}}", "e2e/**/*.ts"],
        "ignoreDependencies": ignored,
        "ignoreExportsUsedInFile": False,
        "includeEntryExports": True,
        "treatConfigHintsAsErrors": True,
        "ignoreIssues": {
            "src/app/**": ["exports"],
            "src/routes/**": ["exports"],
            "src/pages/**": ["exports"],
            "src/router.tsx": ["exports"],
        },
        "rules": {"binaries": "error", "catalog": "error", "catalogReferences": "error", "cycles": "error",
                  "dependencies": "error", "devDependencies": "error", "duplicates": "error", "enumMembers": "error",
                  "exports": "error", "files": "error", "namespaceMembers": "error", "nsExports": "error",
                  "nsTypes": "error", "optionalPeerDependencies": "error", "types": "error", "unlisted": "error",
                  "unresolved": "error"},
    }
    return json.dumps(doc, indent=2) + "\n"


def stricter(key: str, theirs: str, ours: str) -> str:
    """The stricter of two values of one supply-chain setting: the larger age or window, `true` for the boolean
    guards, the base's trust policy over any other."""
    if key in ("minimumReleaseAge", "trustPolicyIgnoreAfter"):
        try:
            return theirs if int(theirs) >= int(ours) else ours
        except ValueError:
            return ours
    return ours


def _block(lines: list[str], start: int) -> tuple[int, list[str]]:
    """(end, entry names) of the YAML block whose key sits on line `start`."""
    end = next((j for j in range(start + 1, len(lines)) if lines[j] and not lines[j][0].isspace()), len(lines))
    names = [ln.strip().lstrip("-").strip().split(":", 1)[0].strip().strip("'\"") for ln in lines[start + 1:end]
             if ln.strip() and not ln.strip().startswith("#")]
    return end, names


def workspace_yaml(stacks: dict, current: str | None, changes: list[str] | None = None, pnpm_major: int = 12) -> str:
    """pnpm-workspace.yaml with the supply-chain settings (stacks.json -> pnpm). An existing file keeps everything
    else it has; a setting it lacks is appended, a weaker value is raised to the base's and listed in `changes`, and
    a missing override is added to its `overrides:` block (written by hand: bots' system python has no YAML module).
    """
    changes = changes if changes is not None else []
    cfg = stacks["pnpm"]
    settings = {"minimumReleaseAge": str(cfg["minimumReleaseAge"]), "trustPolicy": cfg["trustPolicy"],
                "blockExoticSubdeps": str(cfg["blockExoticSubdeps"]).lower(),
                "strictDepBuilds": str(cfg["strictDepBuilds"]).lower()}
    overrides = cfg.get("overrides") or {}
    settings["trustPolicyIgnoreAfter"] = str(cfg["trustPolicyIgnoreAfter"])
    block = {key: [f"{key}: {value}"] for key, value in settings.items()}
    block["trustPolicyExclude"] = ["trustPolicyExclude:", *[f"  - {name}" for name in cfg["trustPolicyExclude"]]]
    if overrides:
        block["overrides"] = ["overrides:", *[f'  {name}: "{spec}"' for name, spec in sorted(overrides.items())]]
    young = cfg.get("minimumReleaseAgeExclude") or []
    if young:
        block["minimumReleaseAgeExclude"] = ["minimumReleaseAgeExclude:", *[f"  - '{spec}'" for spec in young]]
    built = list(stacks.get("built_dependencies") or [])
    header = "# pnpm supply-chain settings of the strict base (site_base.py); see references/project-base.md\n"
    # pnpm 11 replaced onlyBuiltDependencies with allowBuilds, and pnpm 12 fails on a setting it does not know
    builds = (("allowBuilds", "  '{}': true") if pnpm_major >= 11 else ("onlyBuiltDependencies", "  - '{}'"))
    if current is None:
        block[builds[0]] = [f"{builds[0]}:", *[builds[1].format(name) for name in built]]
        return header + "\n".join(ln for rows in block.values() for ln in rows) + "\n"
    lines = current.rstrip("\n").split("\n")
    have = {}
    for i, ln in enumerate(lines):
        if ln and not ln[0].isspace() and ":" in ln and not ln.startswith("#"):
            have[ln.split(":", 1)[0].strip()] = i
    for key, value in settings.items():
        if key not in have:
            continue
        theirs = lines[have[key]].split(":", 1)[1].split("#", 1)[0].strip().strip("'\"")
        want = stricter(key, theirs, value)
        if theirs != want:
            lines[have[key]] = f"{key}: {want}"
            changes.append(f"pnpm-workspace.yaml {key}: {theirs} -> {want}")
    if "overrides" in have:
        start = have["overrides"]
        end = next((j for j in range(start + 1, len(lines)) if lines[j] and not lines[j][0].isspace()), len(lines))
        named = {ln.strip().split(":", 1)[0].strip("'\"") for ln in lines[start + 1:end] if ln.strip()}
        extra = [f'  {name}: "{spec}"' for name, spec in sorted(overrides.items()) if name not in named]
        if extra:
            lines[end:end] = extra
            changes.append("pnpm-workspace.yaml overrides: added " + ", ".join(sorted(set(overrides) - named)))
    if "minimumReleaseAgeExclude" in have and young:
        start = have["minimumReleaseAgeExclude"]
        end = next((j for j in range(start + 1, len(lines)) if lines[j] and not lines[j][0].isspace()), len(lines))
        listed = {ln.strip().lstrip("-").strip().strip("'\"") for ln in lines[start + 1:end] if ln.strip()}
        extra = [spec for spec in young if spec not in listed]
        if extra:
            lines[end:end] = [f"  - '{spec}'" for spec in extra]
            changes.append("pnpm-workspace.yaml minimumReleaseAgeExclude: added " + ", ".join(extra))
    # install scripts the base needs (lefthook, esbuild, ...): in whichever form the file already uses (`allowBuilds`
    # from a recent create CLI, else `onlyBuiltDependencies`), never for a package the project chose to ignore
    ignored = _block(lines, have["ignoredBuiltDependencies"])[1] if "ignoredBuiltDependencies" in have else []
    wanted = [name for name in built if name not in ignored]
    for key, entry in (("allowBuilds", "  '{}': true"), ("onlyBuiltDependencies", "  - '{}'")):
        if key in have:
            end, listed = _block(lines, have[key])
            extra = [name for name in wanted if name not in listed]
            if extra:
                lines[end:end] = [entry.format(name) for name in extra]
                changes.append(f"pnpm-workspace.yaml {key}: added " + ", ".join(extra))
            break
    else:
        block[builds[0]] = [f"{builds[0]}:", *[builds[1].format(name) for name in wanted]]
    add = [ln for key, rows in block.items() if key not in have for ln in rows]
    return "\n".join(lines + add) + "\n"



def merged_package(current: dict, stacks: dict, stack_key: str) -> dict:
    """package.json with the gate scripts set. Dependencies are never written here: they arrive through `pnpm add`."""
    stack = stacks["stacks"][stack_key]
    out = dict(current)
    theirs = current.get("scripts") or {}
    ours = {**SCRIPTS, "quality:types": stack["scripts"]["check"], "quality:typecov": typecov_command(stack)}
    # the gate is the squad's: a repo's own quality* script is replaced (listed under replaced_scripts)
    out["scripts"] = {**ours, **{k: v for k, v in theirs.items() if not k.startswith("quality")}}
    return out


def strip_jsonc(text: str) -> str:
    """JSON from JSONC: comments and trailing commas removed, strings left intact."""
    out, i, n, in_str = [], 0, len(text), False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
            out.append(ch)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        else:
            out.append(ch)
        i += 1
    return re.sub(r",(\s*[}\]])", r"\1", "".join(out))


TS_EXCLUDE = ("tools/quality", "coverage", "playwright-report", "test-results", "dist")


def strict_tsconfig(text: str | None) -> tuple[str | None, str]:
    """(new text, note). The strict options are set in plain JSON and in JSONC alike. JSONC that is already strict is
    left untouched; JSONC that needs an option is rewritten as plain JSON and the note says its comments are gone."""
    if text is None:
        doc = {"compilerOptions": {**STRICT_TS, "noEmit": True, "skipLibCheck": True, "target": "ES2022",
                                   "module": "ESNext", "moduleResolution": "bundler", "jsx": "react-jsx"}}
        return json.dumps(doc, indent=2) + "\n", "written"
    commented = False
    try:
        doc = json.loads(text)
    except ValueError:
        try:
            doc = json.loads(strip_jsonc(text))
            commented = True
        except ValueError:
            return None, "tsconfig.json could not be parsed: set the strict options by hand (references/project-base.md)"
    opts = doc.setdefault("compilerOptions", {})
    missing = {k: v for k, v in STRICT_TS.items() if opts.get(k) != v}
    # the gate's scripts and the reports it writes are not project code: a template that includes `**/*` with
    # allowJs would type-check and type-cover them (an explicit exclude replaces TypeScript's default, so
    # node_modules stays listed)
    exclude = list(doc.get("exclude") or ["node_modules"])
    extra = [d for d in TS_EXCLUDE if d not in exclude]
    if extra:
        doc["exclude"] = [*exclude, *extra]
        missing["exclude"] = doc["exclude"]
    if not missing:
        return text, "already strict"
    opts.update({k: v for k, v in missing.items() if k != "exclude"})
    note = f"strict options set: {len(missing)}" + (
        "; tsconfig.json had comments, rewritten without them" if commented else "")
    return json.dumps(doc, indent=2) + "\n", note


def plan_files(repo: Path, stacks: dict, stack_key: str, name: str, provider: str,
               report: dict | None = None, created: bool = False, pnpm_major: int = 12) -> tuple[dict, list[str]]:
    """(path -> text to write, kept paths): the squad's policy on top of what the create CLI wrote (`created`) or of
    an existing repo. `report` collects `manual` items, `replaced_scripts`, `strengthened` and `notes`."""
    report = report if report is not None else {}
    files: dict[str, str] = {}
    if created:
        files.update(SEED_TEST)
        files["playwright.config.ts"] = sc.PLAYWRIGHT
        files["e2e/home.e2e.ts"] = sc.TEST_SPEC
        # a new repo starts at zero: no baseline debt, zero comments allowed anywhere
        files["tools/quality/baseline.json"] = ZERO_RATCHET
        files["tools/quality/regression-baseline.json"] = ZERO_REGRESSIONS
    files.update(sc.header_files(stack_key, provider, repo))
    for src in sorted(p for p in TEMPLATES.rglob("*") if p.is_file()):
        files[str(src.relative_to(TEMPLATES))] = src.read_text(encoding="utf-8")
    files["knip.json"] = knip_config(stacks["stacks"][stack_key], provider, repo)
    files["tools/quality/package.json"] = QUALITY_PACKAGE
    kept = []
    for rel in list(files):
        if (repo / rel).exists() and rel != "next.config.ts":
            kept.append(rel)
            del files[rel]
    ignore = repo / ".gitignore"
    merged_ignore = sc.gitignore(ignore.read_text(encoding="utf-8") if ignore.is_file() else None)
    if merged_ignore:
        files[".gitignore"] = merged_ignore
    if stack_key == "nextjs" and "next.config.ts" not in files and not _has_headers(repo / "next.config.ts"):
        report.setdefault("manual", []).append("next.config.ts: add the security headers by hand "
                                               "(references/project-base.md); the config object was not found")
    pkg_path = repo / "package.json"
    current = json.loads(pkg_path.read_text(encoding="utf-8")) if pkg_path.is_file() else {"name": name, "private": True}
    # pnpm 11 stopped reading package.json's `pnpm` field: its build approvals move to allowBuilds
    legacy = current.get("pnpm") if isinstance(current.get("pnpm"), dict) else {}
    if pnpm_major >= 11 and legacy:
        stacks = {**stacks, "built_dependencies": list(dict.fromkeys(
            [*stacks["built_dependencies"], *(legacy.get("onlyBuiltDependencies") or [])]))}
        current = {k: v for k, v in current.items() if k != "pnpm"}
        report.setdefault("notes", []).append("package.json `pnpm` field removed (pnpm 11+ ignores it); its build "
                                              "approvals moved to allowBuilds in pnpm-workspace.yaml")
    # the quality toolchain is its own pnpm root (a root workspace file would make `--dir tools/quality` install the
    # site instead), so it carries the same supply-chain settings
    for rel in ("pnpm-workspace.yaml", "tools/quality/pnpm-workspace.yaml"):
        ws_path = repo / rel
        files[rel] = workspace_yaml(stacks, ws_path.read_text(encoding="utf-8") if ws_path.is_file() else None,
                                    report.setdefault("strengthened", []), pnpm_major)
    files["package.json"] = json.dumps(merged_package(current, stacks, stack_key), indent=2) + "\n"
    report["replaced_scripts"] = sorted(k for k in (current.get("scripts") or {}) if k.startswith("quality")
                                        and (current["scripts"][k] != json.loads(files["package.json"])["scripts"].get(k)))
    ts_path = repo / "tsconfig.json"
    ts_text, note = strict_tsconfig(ts_path.read_text(encoding="utf-8") if ts_path.is_file() else None)
    if ts_text is not None:
        if not ts_path.is_file() or ts_text != ts_path.read_text(encoding="utf-8"):
            files["tsconfig.json"] = ts_text
        if "comments" in note:
            report.setdefault("notes", []).append(note)
    else:
        kept.append("tsconfig.json")
        report.setdefault("manual", []).append(note)
    return files, sorted(set(kept))


def _has_headers(path: Path) -> bool:
    return path.is_file() and "Content-Security-Policy" in path.read_text(encoding="utf-8")


def biome_extends(text: str) -> str | None:
    """The project's biome.json extending the squad's strict rules; None when nothing changes. A project file with
    its own `files.includes` replaces the policy's list, so the policy's exclusions (dependencies, build output,
    static assets, generated routes) are added to it. The formatter is the squad's too: `biome init` and the create
    CLIs default to tabs and the project's own formatter block would override the policy's spaces."""
    doc = json.loads(strip_jsonc(text))
    before = json.dumps(doc)
    extends = doc.get("extends") or []
    extends = [extends] if isinstance(extends, str) else list(extends)
    if BIOME_POLICY not in extends:
        doc["extends"] = [*extends, BIOME_POLICY]
    includes = (doc.get("files") or {}).get("includes")
    if isinstance(includes, list):
        policy = json.loads(strip_jsonc((TEMPLATES / BIOME_POLICY).read_text(encoding="utf-8")))
        excluded = [p for p in policy["files"]["includes"] if p.startswith("!")]
        doc["files"]["includes"] = [*includes, *(p for p in excluded if p not in includes)]
    formatter = doc.setdefault("formatter", {})
    for key, value in (("indentStyle", "space"), ("indentWidth", 2), ("lineWidth", 100)):
        if formatter.get(key) != value:
            formatter[key] = value
    return None if json.dumps(doc) == before else json.dumps(doc, indent=2) + "\n"


def run(argv: list[str], cwd: Path, step: str, timeout: int = 900) -> dict:
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"step": step, "ok": False, "tail": str(exc)}
    tail = (done.stdout + done.stderr)[-TAIL:]
    return {"step": step, "ok": done.returncode == 0, "exit": done.returncode, "argv": argv, "tail": tail}


def pnpm_argv() -> list[str] | None:
    """`pnpm` on PATH. Without it, `corepack enable pnpm` puts the official shim beside node (the gate's scripts and
    the git hooks call `pnpm` by name); npm's own `npm install -g pnpm` is the fallback when corepack cannot."""
    if shutil.which("pnpm"):
        return ["pnpm"]
    if shutil.which("corepack"):
        quiet = subprocess.run(["corepack", "enable", "pnpm"], capture_output=True, text=True, timeout=300,
                               stdin=subprocess.DEVNULL)
        if quiet.returncode == 0 and shutil.which("pnpm"):
            return ["pnpm"]
    if shutil.which("npm"):
        subprocess.run(["npm", "install", "-g", "pnpm"], capture_output=True, text=True, timeout=600,
                       stdin=subprocess.DEVNULL)
        if shutil.which("pnpm"):
            return ["pnpm"]
    return None


def newest_mature(times: dict, min_age_minutes: int, now: float | None = None) -> str | None:
    """The newest stable release (x.y.z, no prerelease) published at least `min_age_minutes` ago, from the
    registry's `time` map (`npm view <package> time --json`)."""
    cutoff = (time.time() if now is None else now) - min_age_minutes * 60
    best = None
    for version, stamp in times.items():
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            continue
        try:
            published = datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
        except (AttributeError, ValueError):
            continue
        key = tuple(int(x) for x in version.split("."))
        if published <= cutoff and (best is None or key > best[0]):
            best = (key, version)
    return best[1] if best else None


def declared_pnpm(repo: Path) -> str | None:
    """The pnpm version the repo pins (packageManager, else devEngines.packageManager)."""
    path = repo / "package.json"
    pkg = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    pinned = str(pkg.get("packageManager") or "")
    if pinned.startswith("pnpm@"):
        return pinned[5:].split("+", 1)[0]
    dev = ((pkg.get("devEngines") or {}).get("packageManager") or {})
    return str(dev.get("version")) if isinstance(dev, dict) and dev.get("name") == "pnpm" else None


def major(version: str | None) -> int:
    found = re.search(r"\d+", version or "")
    return int(found.group()) if found else 0


def mature_pnpm(stacks: dict) -> str | None:
    """The newest pnpm release at least 3 days old, from the registry (`npm view pnpm time --json`)."""
    npm = shutil.which("npm")
    if not npm:
        return None
    try:
        out = subprocess.run([npm, "view", "pnpm", "time", "--json"], capture_output=True, text=True, timeout=120,
                             stdin=subprocess.DEVNULL).stdout
        return newest_mature(json.loads(out), int(stacks["pnpm"]["minimumReleaseAge"]))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


def pin_pnpm(repo: Path, version: str) -> dict:
    """Pin pnpm with `npm pkg set packageManager`: inside the repo pnpm and corepack both switch to that version, so
    every bot and hook runs the same pnpm. A create CLI pins the pnpm that ran it, often an old one. Not `corepack
    use`: it installs at once, before `pnpm up --latest` has moved the template's ranges to releases 3 days old."""
    return run(["npm", "pkg", "set", f"packageManager=pnpm@{version}"], repo, f"pin pnpm@{version}")


def create(repo: Path, stacks: dict, stack: str, name: str, provider: str) -> dict:
    """Run the stack's official create CLI into a sibling folder, then move its files into the repo (the CLIs want
    a folder of their own; the repo may already hold `.git`)."""
    holder = Path(tempfile.mkdtemp(prefix=".create-", dir=repo.parent))
    work = holder / name  # the CLIs take the folder name as the package name
    step = run(sc.create_argv(stacks, stack, str(work), name, provider), holder, "create (official CLI)")
    if step["ok"] and not (work / "package.json").is_file():
        step = {**step, "ok": False, "tail": step["tail"] + "\nthe create CLI wrote no package.json"}
    if step["ok"]:
        for child in work.iterdir():
            if child.name != ".git":
                shutil.move(str(child), str(repo / child.name))
    shutil.rmtree(holder, ignore_errors=True)
    return step


TRUST_RE = re.compile(r'trust downgrade for "(@?[^"@]+)@([^"]+)"')


def trusted_before(name: str, flagged: str, min_age_minutes: int, repo: Path) -> str | None:
    """The newest stable release older than the one pnpm's trustPolicy flagged, itself old enough to install."""
    done = subprocess.run(["npm", "view", name, "time", "--json"], cwd=repo, capture_output=True, text=True,
                          timeout=120, stdin=subprocess.DEVNULL)
    try:
        times = json.loads(done.stdout or "{}")
        flagged_at = datetime.fromisoformat(times[flagged].replace("Z", "+00:00")).timestamp()
    except (ValueError, KeyError, AttributeError):
        return None
    earlier = {v: s for v, s in times.items() if re.fullmatch(r"\d+\.\d+\.\d+", v)
               and datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() < flagged_at}
    return newest_mature(earlier, min_age_minutes)


def add_holding_untrusted(argv: list[str], repo: Path, step: str, min_age_minutes: int) -> dict:
    """`pnpm add` that, when pnpm's trustPolicy flags a release it would pick (published without the provenance its
    earlier releases had: a possible takeover), adds that package at its last trusted release instead and says so
    under `held`. The flagged release is never let in; the lockfile keeps the trusted one, and pnpm refuses the
    flagged one again on any later update."""
    held: list[str] = []
    argv = list(argv)
    for _ in range(5):
        result = run(argv, repo, step)
        # pnpm wraps its error box: join the lines before reading the package it named
        hit = TRUST_RE.search(re.sub(r"\s*\n[\s│]*", " ", result["tail"])) if not result["ok"] else None
        if not hit:
            return {**result, "held": held} if held else result
        name, flagged = hit.group(1), hit.group(2)
        named = [i for i, a in enumerate(argv) if a == name or a.startswith(name + "@")]
        trusted = trusted_before(name, flagged, min_age_minutes, repo) if named else None
        if not trusted:
            return {**result, "tail": result["tail"] + f"\n{name}@{flagged} lost its publisher trust and no earlier "
                                                       "trusted release fits: a manager decision"}
        argv[named[0]] = f"{name}@{trusted}"  # exact: a ^ range would pick the flagged release again
        held.append(f"{name}@{trusted} (pnpm trustPolicy flagged {flagged}: published without the provenance of "
                    "earlier releases)")
    return {**result, "held": held}


def template_majors(repo: Path) -> dict[str, list[str]]:
    """{"dependencies": [...], "devDependencies": [...]} as `name@<major>` for every registry range the create CLI
    wrote. A template names the newest release of each package, often days old; `pnpm add name@<major>` keeps the
    major the framework's authors chose and lets pnpm pick the newest release of it that is 3 days old
    (`pnpm up --latest` would ask for the newest release of all, which the release-age rule refuses)."""
    pkg = json.loads((repo / "package.json").read_text(encoding="utf-8"))
    out: dict[str, list[str]] = {}
    for group in ("dependencies", "devDependencies"):
        specs = []
        for name, spec in (pkg.get(group) or {}).items():
            found = re.fullmatch(r"[\^~>=v]*(\d+)(?:\.(\d+))?(?:\.[\dx*]+)?(?:-[\w.]+)?", str(spec).strip())
            if found:  # leave workspace:, catalog:, git and file specs as they are
                # a 0.x package breaks on minor releases, so its compatible line is 0.<minor>
                line = found.group(1) if found.group(1) != "0" else f"0.{found.group(2) or 0}"
                specs.append(f"{name}@{line}")
        if specs:
            out[group] = specs
    return out


def add_steps(repo: Path, stacks: dict, stack: str, provider: str, pnpm: list[str]) -> list[tuple]:
    """The official commands that bring in the squad's tools: (argv, step name). No version anywhere."""
    spec = stacks["stacks"][stack]
    dev = [*stacks["devDependencies"], *spec.get("devDependencies", [])]
    if provider == "cloudflare":
        dev += stacks["cloudflare"]["devDependencies"]
    steps = [(pnpm + ["exec", *argv], " ".join(argv)) for argv in spec.get("after_install", [])]
    steps.append((pnpm + ["add", "-D", *dict.fromkeys(dev)], "pnpm add -D (squad tools)"))
    steps.append((pnpm + ["add", "-D", "--dir", "tools/quality", *stacks["quality_tools"]["packages"]],
                  "pnpm add -D (quality tools)"))
    return steps


def fresh_allow(repo: Path, stacks: dict, stack: str, template: dict[str, list[str]],
                held: list[str] | None = None) -> dict:
    """tools/quality/fresh-allow.json: the packages the versions gate lets stay behind the newest major, each with its
    reason. Only three sources: a stated constraint of the stack, a stacks.json entry (`fresh_allow`), and a major the
    stack's create CLI chose itself (the official installer's decision, never the bot's). Anything else behind fails."""
    path = repo / "tools" / "quality" / "fresh-allow.json"
    try:  # a second run (after the template's code was fixed) keeps what the first run recorded
        allow = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        allow = {}
    allow.update(stacks.get("fresh_allow") or {})
    for row in held or []:  # held at its last trusted release on purpose: the exact pin carries the reason
        allow[row.split(" ", 1)[0].rsplit("@", 1)[0]] = "held at " + row
    for spec in stacks["stacks"][stack].get("devDependencies", []):
        if spec in stacks.get("constraints", {}):
            allow[spec.rsplit("@", 1)[0]] = stacks["constraints"][spec]
    done = subprocess.run(["node", "tools/quality/fresh.mjs", "--json"], cwd=repo, capture_output=True, text=True,
                          timeout=600, stdin=subprocess.DEVNULL)
    try:
        findings = json.loads(done.stdout or "[]")
    except ValueError:
        return {"step": "versions gate", "ok": False, "tail": (done.stdout + done.stderr)[-TAIL:]}
    chosen = {spec.rsplit("@", 1)[0]: spec.rsplit("@", 1)[1] for specs in template.values() for spec in specs}
    cli = stacks["stacks"][stack]["create"][0].rsplit("@", 1)[0]
    for row in findings:
        if row.get("kind") == "behind" and row["name"] in chosen and row["name"] not in allow:
            allow[row["name"]] = f"{cli} chose {row['name']}@{chosen[row['name']]} for this stack"
    path.write_text(json.dumps(dict(sorted(allow.items())), indent=2) + "\n", encoding="utf-8")
    return {"step": "versions allowed behind", "ok": True, "tail": "", "allowed": sorted(allow)}


def biome_setup(repo: Path, pnpm: list[str]) -> list[dict]:
    """Biome's own config from `biome init` (unless the create CLI wrote one), extending the squad's rules, then
    `biome migrate` so the config matches the installed Biome."""
    steps = []
    if not any((repo / n).is_file() for n in ("biome.json", "biome.jsonc")):
        steps.append(run(pnpm + ["exec", "biome", "init"], repo, "biome init"))
        if not steps[-1]["ok"]:
            return steps
    path = repo / "biome.json" if (repo / "biome.json").is_file() else repo / "biome.jsonc"
    try:
        new = biome_extends(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        return steps + [{"step": "biome extends", "ok": False, "tail": f"{path.name} is not JSON: {exc}"}]
    if new:
        path.write_text(new, encoding="utf-8")
    steps.append(run(pnpm + ["exec", "biome", "migrate", "--write"], repo, "biome migrate"))
    return steps


def record_baselines(repo: Path) -> list[dict]:
    """The ratchet and regression baselines of a repo adopting the base, recorded once from its current totals: old
    debt is tolerated, a regression is not. A new repo starts at zero (plan_files writes the zero baselines) and a
    later run never re-records (a baseline is lowered by a cleanup round, never raised by a rerun)."""
    out = []
    for script, name in (("ratchet.mjs", "tools/quality/baseline.json"),
                         ("regressions.mjs", "tools/quality/regression-baseline.json")):
        if (repo / name).is_file():
            continue
        out.append(run(["node", f"tools/quality/{script}", "record"], repo, f"record {name}"))
        if not out[-1]["ok"]:
            break
    return out


def install(repo: Path, stacks: dict, stack: str, provider: str, created: bool, fresh_git: bool,
            pin: str | None = None) -> list[dict]:
    pnpm = pnpm_argv()
    if not pnpm:
        return [{"step": "pnpm", "ok": False, "tail": "neither pnpm nor corepack is on PATH: install Node.js 22+"}]
    steps = [pin_pnpm(repo, pin)] if pin else []
    if fresh_git and all(s["ok"] for s in steps):
        steps.append(run(["git", "init", "-q", "-b", "main"], repo, "git init"))
    if not all(s["ok"] for s in steps):
        return steps
    scanners = [security_tools.ensure(tool) for tool in ("osv-scanner", "gitleaks")]
    steps.append({"step": "security tools", "ok": all(r["ready"] for r in scanners),
                  "tail": "; ".join(r["detail"] for r in scanners if not r["ready"])})
    majors = template_majors(repo) if created else {}
    if created:
        # drop the template's exact ranges first: a lockfile resolved from them keeps their versions
        resolve = [(["npm", "pkg", "delete", *majors], "clear the template's ranges")] if majors else []
        resolve += [(pnpm + ["add", *(["-D"] if group == "devDependencies" else []), *specs],
                    f"pnpm add (template {group}, 3-day releases)") for group, specs in majors.items()]
    else:
        resolve = [(pnpm + ["install"], "pnpm install")]
    age = int(stacks["pnpm"]["minimumReleaseAge"])
    for argv, step in [*resolve, *add_steps(repo, stacks, stack, provider, pnpm)]:
        if not steps[-1]["ok"]:
            return steps
        is_add = argv[len(pnpm):len(pnpm) + 1] == ["add"]
        steps.append(add_holding_untrusted(argv, repo, step, age) if is_add else run(argv, repo, step))
    if steps[-1]["ok"]:
        # the hooks install themselves on every later `pnpm install` (a fresh clone), now that lefthook is there
        steps.append(run(["npm", "pkg", "set", "scripts.prepare=lefthook install"], repo, "prepare script"))
        if created and stack == "astro":
            sc.write_tree(repo, sc.astro_styles(repo), False)
        # a known vulnerability is fixed now, its fix let in early when younger than the release-age rule
        fixed = security_fix.fix_repo(repo)
        steps.append({"step": "security fixes", "ok": fixed["ok"], "fixed": fixed.get("fixed", []),
                      "tail": "" if fixed["ok"] else json.dumps({k: fixed.get(k) for k in
                                                                ("error", "failed", "unfixable", "left")})[-TAIL:]})
    if all(s["ok"] for s in steps):
        steps.append(fresh_allow(repo, stacks, stack, majors, [h for s in steps for h in s.get("held", [])]))
    if all(s["ok"] for s in steps):
        steps += biome_setup(repo, pnpm)
    if all(s["ok"] for s in steps):
        steps += record_baselines(repo)
    for argv, step in ((pnpm + ["exec", "lefthook", "install"], "lefthook install"),
                       (pnpm + ["exec", "biome", "check", "--write", "."], "format the base"),
                       (pnpm + ["run", "quality"], "pnpm quality")):
        if not all(s["ok"] for s in steps):
            break
        steps.append(run(argv, repo, step))
        if step == "format the base" and not steps[-1]["ok"]:
            # the safe fixes landed; what Biome cannot fix in the template's code is the gate's to report, with
            # `next`, so the manager fixes that code
            steps[-1].update(ok=True, note="findings left for the gate")
    # the first commit lands once the gate is green, also on a second run after the template's code was fixed
    if all(s["ok"] for s in steps) and not has_commits(repo):
        steps.append(run(["git", "add", "-A"], repo, "git add"))
        steps.append(run(["git", "commit", "-q", "-m", "chore: strict project base"], repo, "first commit"))
    return steps


def has_commits(repo: Path) -> bool:
    return subprocess.run(["git", "rev-parse", "--verify", "-q", "HEAD"], cwd=repo, capture_output=True,
                          stdin=subprocess.DEVNULL).returncode == 0


GATE_FAILED = ("The base is installed, but `pnpm quality` fails on the code shown in its output (often code the "
               "create CLI wrote). Fix that code so it meets the rule; never relax a rule, raise a threshold or add "
               "an ignore. Then run site_base.py again with the same arguments: it keeps every file, runs the gate "
               "and makes the first commit.")


def read_site(site: Path) -> dict:
    """stack, slug, provider and the repo folder from <site>/site.yaml (top-level keys and `repo: path:`; bots'
    system python has no YAML module)."""
    path = site / "site.yaml"
    if not path.is_file():
        raise ValueError(f"{path} not found: the manager writes site.yaml first")
    top, repo_path, in_repo = {}, "repo", False
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split(" #", 1)[0].rstrip()
        hit = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if hit:
            top[hit.group(1)] = hit.group(2).strip().strip("'\"")
            in_repo = hit.group(1) == "repo"
        elif in_repo and re.match(r"^\s+path:", line):
            repo_path = line.split(":", 1)[1].strip().strip("'\"") or "repo"
    missing = [k for k in ("slug", "stack") if not top.get(k)]
    if missing:
        raise ValueError(f"{path} has no {', '.join(missing)}")
    return {"repo": str((site / repo_path).resolve()), "stack": top["stack"], "slug": top["slug"],
            "provider": top.get("provider") or "cloudflare"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0],
                                epilog="Exit 0 base ready or dry run, 1 a step failed, 2 usage error.")
    p.add_argument("--site", help="the site folder: reads stack, slug, provider and repo.path from its site.yaml and "
                                   "installs (the manager's one command)")
    p.add_argument("--repo", help="the site repo folder (<site>/<site.yaml repo.path>)")
    p.add_argument("--stack", help="astro | nextjs | tanstack (stacks.json)")
    p.add_argument("--name", help="project slug, lowercase kebab-case")
    p.add_argument("--provider", help="site.yaml provider: cloudflare (default) | vercel")
    p.add_argument("--install", action="store_true", help="install, init git, hooks, run the gate, first commit")
    p.add_argument("--dry-run", action="store_true", help="list what would run and be written, change nothing")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)
    if args.site:
        try:
            spec = read_site(Path(args.site).expanduser().resolve())
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        args.repo, args.stack, args.name = args.repo or spec["repo"], args.stack or spec["stack"], args.name or spec["slug"]
        args.provider = args.provider or spec["provider"]
        args.install = args.install or not args.dry_run
    args.provider = args.provider or "cloudflare"
    if not (args.repo and args.stack and args.name):
        print("error: give --site <folder>, or --repo, --stack and --name", file=sys.stderr)
        return 2
    augment_path()
    stacks = sc.load_stacks()
    if args.stack not in stacks["stacks"] or not sc.NAME_RE.match(args.name):
        print(f"error: unknown stack {args.stack!r} or bad --name", file=sys.stderr)
        return 2
    repo = Path(args.repo).expanduser().resolve()
    repo.mkdir(parents=True, exist_ok=True)
    fresh = not sc.busiest(repo)
    fresh_git = not (repo / ".git").exists()
    result: dict = {"repo": str(repo), "stack": args.stack, "fresh": fresh, "dry_run": args.dry_run, "steps": []}
    if fresh:
        result["create"] = sc.create_argv(stacks, args.stack, str(repo), args.name, args.provider)
    if args.dry_run:
        result["ok"] = True
        print(json.dumps(result, indent=2) if args.json else "would run: " + " ".join(result.get("create", [])))
        return 0
    if fresh:
        result["steps"].append(create(repo, stacks, args.stack, args.name, args.provider))
    report: dict = {}
    # a new site runs the newest pnpm that is 3 days old; a repo that already pins pnpm keeps its pin
    declared = declared_pnpm(repo)
    pin = None
    if args.install and (fresh or not declared):
        pin = mature_pnpm(stacks)
        if not pin:
            result["steps"].append({"step": "resolve pnpm", "ok": False,
                                    "tail": "npm view pnpm time failed: no registry answer"})
    if all(s["ok"] for s in result["steps"]):
        files, kept = plan_files(repo, stacks, args.stack, args.name, args.provider, report, created=fresh,
                                 pnpm_major=major(pin or declared or "12"))
        sc.write_tree(repo, files, False)
        result.update({"written": sorted(files), "kept": kept, **report, "pnpm": pin or declared})
        if args.install:
            result["steps"] += install(repo, stacks, args.stack, args.provider, fresh, fresh_git, pin)
    ok = all(s["ok"] for s in result["steps"]) and not result.get("manual")
    result["ok"] = ok
    if any(s["step"] == "pnpm quality" and not s["ok"] for s in result["steps"]):
        result["next"] = GATE_FAILED
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for s in result["steps"]:
            print(f"{'ok  ' if s['ok'] else 'FAIL'} {s['step']}" + ("" if s["ok"] else f"\n{s['tail']}"))
        if result.get("next"):
            print("\nnext: " + result["next"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
