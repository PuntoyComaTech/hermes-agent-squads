#!/usr/bin/env python3
"""Lay the strict project base of a site repo: the stack skeleton (empty repo) plus the quality gate, then install it.

The gate (`pnpm quality`) is the bar every bot's code must pass from the first commit: strict TypeScript, Biome (lint,
format, complexity, no `any`), SonarJS rules run locally (cognitive complexity, duplication, bug patterns),
dependency-cruiser (architecture layers, no cycles), jscpd (copy-paste), knip (dead code and unused dependencies) and
Vitest coverage on logic. lefthook runs Biome on every commit and the whole gate before every push.

Files come from stacks.json and ../templates/quality beside this script. An existing repo keeps every file it already
has (each kept file is listed under `kept`); package.json gains the missing scripts and pins; a weaker pnpm
supply-chain setting is raised to the base's (listed under `strengthened`). With --install it also
runs pnpm (through corepack when pnpm is not on PATH), the quality toolchain install, `git init` on main when there
is no repository, `lefthook install`, the gate itself, and the first commit of a repo it created.

Exit 0 base ready (or dry run), 1 a step failed (the JSON names it and its output tail) or a strict option needs a
hand edit (`manual`), 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates" / "quality"
sys.path.insert(0, str(HERE))
import scaffold_site as sc  # noqa: E402  - same folder: stacks.json and the stack skeletons
from toolpath import augment_path  # noqa: E402
import security_tools  # noqa: E402

SEED_TEST = {
    "src/lib/slug.ts": 'export function slugify(text: string): string {\n'
                       '  const words = text.toLowerCase().split(/[^a-z0-9]/);\n'
                       '  return words.filter((word) => word.length > 0).join("-");\n}\n',
    "src/lib/slug.test.ts": 'import { describe, expect, it } from "vitest";\nimport { slugify } from "./slug";\n\n'
                            'describe("slugify", () => {\n  it("makes a url-safe slug", () => {\n'
                            '    expect(slugify("  Hola Mundo! ")).toBe("hola-mundo");\n  });\n});\n',
}

STRICT_TS = {
    "strict": True, "noUncheckedIndexedAccess": True, "exactOptionalPropertyTypes": True,
    "noImplicitOverride": True, "noImplicitReturns": True, "noFallthroughCasesInSwitch": True,
    "noUnusedLocals": True, "noUnusedParameters": True, "noPropertyAccessFromIndexSignature": True,
    "useUnknownInCatchVariables": True, "allowUnreachableCode": False, "allowUnusedLabels": False,
    "forceConsistentCasingInFileNames": True, "isolatedModules": True, "verbatimModuleSyntax": True,
}
GATE = ("types", "lint", "sonar", "arch", "dupes", "unused", "typecov", "secrets", "licenses", "deps", "test")
SCRIPTS = {
    "lint": "biome check .",
    "format": "biome check --write .",
    "test": "vitest run",
    "e2e": "playwright test",
    "quality": " && ".join(f"pnpm run quality:{step}" for step in GATE),
    "quality:lint": "biome ci --error-on-warnings .",
    "quality:sonar": "tools/quality/node_modules/.bin/eslint --config tools/quality/eslint.config.mjs "
                     "--max-warnings=0 .",
    "quality:arch": "tools/quality/node_modules/.bin/depcruise src --config tools/quality/dependency-cruiser.cjs",
    "quality:dupes": "jscpd --config .jscpd.json",
    "quality:unused": "knip",
    "quality:secrets": "node tools/quality/security.mjs secrets",
    "quality:licenses": "node tools/quality/security.mjs licenses",
    "quality:deps": "node tools/quality/security.mjs deps",
    "quality:test": "vitest run --coverage",
    "prepare": "lefthook install",
}
TAIL = 1500


def typecov_command(stack: dict) -> str:
    """type-coverage over the whole project, strict, 100 %. The generated route file and what the stack lists under
    typecov_ignore are the only exceptions (their `any` comes from generated code, not from the builders)."""
    ignore = ["src/routeTree.gen.ts", *stack.get("typecov_ignore", [])]
    return ("tools/quality/node_modules/.bin/type-coverage -p tsconfig.json --strict --at-least 100"
            + "".join(f" --ignore-files {path}" for path in ignore))


def knip_config(stack: dict, provider: str) -> str:
    """knip.json for the stack: its entry files and source tree (CSS included, so `@import "tailwindcss"` counts as
    a use). Lighthouse and axe-core are run by the QA script through npx, wrangler by the deployer: never imported."""
    doc = {
        "$schema": "https://unpkg.com/knip@6/schema.json",
        "entry": stack.get("entry") or [],
        "project": [f"src/**/*.{{ts,tsx,{'astro,' if stack.get('type') == 'static' else ''}css}}"],
        "ignoreDependencies": ["lighthouse", "axe-core"] + (["wrangler"] if provider == "cloudflare" else []),
        "rules": {"files": "error", "dependencies": "error", "devDependencies": "error", "exports": "error",
                  "types": "error", "duplicates": "error", "unlisted": "error", "unresolved": "error"},
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


def workspace_yaml(stacks: dict, current: str | None, changes: list[str] | None = None) -> str:
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
    header = "# pnpm supply-chain settings of the strict base (site_base.py); see references/project-base.md\n"
    if current is None:
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
    add = [ln for key, rows in block.items() if key not in have for ln in rows]
    return "\n".join(lines + add) + "\n"


def quality_package(stacks: dict) -> str:
    pins = {k: v for k, v in stacks["quality_tools"].items() if not k.startswith("_")}
    doc = {"name": "site-quality", "private": True, "type": "module",
           "description": "SonarJS and dependency-cruiser need the TypeScript JavaScript API (TypeScript 6).",
           "devDependencies": dict(sorted(pins.items()))}
    return json.dumps(doc, indent=2) + "\n"


def merged_package(current: dict, stacks: dict, stack_key: str, provider: str) -> dict:
    """package.json with the gate scripts and pins added; anything the repo already declares wins."""
    stack = stacks["stacks"][stack_key]
    dev = {**stacks["devDependencies"], **stack["devDependencies"]}
    if provider == "cloudflare":
        dev["wrangler"] = stacks["cloudflare"]["wrangler"]  # cf runs through npx at its pin, never a dependency
    out = dict(current)
    theirs = current.get("scripts") or {}
    ours = {**SCRIPTS, "quality:types": stack["scripts"]["check"], "quality:typecov": typecov_command(stack)}
    # the gate is the squad's: a repo's own quality* script is replaced (listed under replaced_scripts)
    out["scripts"] = {**ours, **{k: v for k, v in theirs.items() if not k.startswith("quality")}}
    out["devDependencies"] = dict(sorted({**dev, **(current.get("devDependencies") or {})}.items()))
    out.setdefault("packageManager", stacks["package_manager"])
    pnpm = dict(out.get("pnpm") or {})
    pnpm.setdefault("onlyBuiltDependencies", list(stacks["built_dependencies"]))
    out["pnpm"] = pnpm
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
    if not missing:
        return text, "already strict"
    opts.update(missing)
    note = f"strict options set: {len(missing)}" + (
        "; tsconfig.json had comments, rewritten without them" if commented else "")
    return json.dumps(doc, indent=2) + "\n", note


def plan_files(repo: Path, stacks: dict, stack_key: str, name: str, provider: str,
               report: dict | None = None) -> tuple[dict, list[str], bool]:
    """(path -> text to write, kept paths, fresh). A fresh (empty) repo gets the skeleton as well. `report` collects
    `manual` items (a strict option that could not be set) and `replaced_scripts`."""
    report = report if report is not None else {}
    fresh = not sc.busiest(repo)
    files: dict[str, str] = {}
    if fresh:
        files.update(sc.files_for(stacks, stack_key, name))
        files.update(SEED_TEST)
        files.update(sc.header_files(stack_key, provider))
    for src in sorted(p for p in TEMPLATES.rglob("*") if p.is_file()):
        files[str(src.relative_to(TEMPLATES))] = src.read_text(encoding="utf-8")
    files["knip.json"] = knip_config(stacks["stacks"][stack_key], provider)
    files["tools/quality/package.json"] = quality_package(stacks)
    kept = []
    if not fresh:
        for rel in list(files):
            if (repo / rel).exists():
                kept.append(rel)
                del files[rel]
        if (repo / "biome.json").exists():
            files.pop("biome.jsonc", None)
            kept.append("biome.json")
    # the quality toolchain is its own pnpm root (a root workspace file would make `--dir tools/quality` install the
    # site instead), so it carries the same supply-chain settings
    for rel in ("pnpm-workspace.yaml", "tools/quality/pnpm-workspace.yaml"):
        ws_path = repo / rel
        files[rel] = workspace_yaml(stacks, ws_path.read_text(encoding="utf-8") if ws_path.is_file() else None,
                                    report.setdefault("strengthened", []))
    pkg_path = repo / "package.json"
    current = json.loads(pkg_path.read_text(encoding="utf-8")) if pkg_path.is_file() and not fresh else (
        json.loads(files["package.json"]) if "package.json" in files else {"name": name, "private": True})
    files["package.json"] = json.dumps(merged_package(current, stacks, stack_key, provider), indent=2) + "\n"
    report["replaced_scripts"] = sorted(k for k in (current.get("scripts") or {}) if k.startswith("quality")
                                        and (current["scripts"][k] != json.loads(files["package.json"])["scripts"].get(k)))
    ts_path = repo / "tsconfig.json"
    ts_text, note = strict_tsconfig(files.get("tsconfig.json") if fresh else (
        ts_path.read_text(encoding="utf-8") if ts_path.is_file() else None))
    if ts_text is not None:
        files["tsconfig.json"] = ts_text
        if "comments" in note:
            report.setdefault("notes", []).append(note)
    else:
        kept.append("tsconfig.json")
        report.setdefault("manual", []).append(note)
    return files, sorted(set(kept)), fresh


def run(argv: list[str], cwd: Path, step: str, timeout: int = 900) -> dict:
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"step": step, "ok": False, "tail": str(exc)}
    tail = (done.stdout + done.stderr)[-TAIL:]
    return {"step": step, "ok": done.returncode == 0, "exit": done.returncode, "tail": tail}


def pnpm_argv() -> list[str] | None:
    """`pnpm` on PATH. Without it, `corepack enable pnpm` puts the shim beside node (the gate's scripts and the git
    hooks call `pnpm` by name, so it must be on PATH, not only reachable as `corepack pnpm`); npm's global install of
    the pinned pnpm is the fallback when corepack cannot write there."""
    if shutil.which("pnpm"):
        return ["pnpm"]
    if shutil.which("corepack"):
        quiet = subprocess.run(["corepack", "enable", "pnpm"], capture_output=True, text=True, timeout=300,
                               stdin=subprocess.DEVNULL)
        if quiet.returncode == 0 and shutil.which("pnpm"):
            return ["pnpm"]
    if shutil.which("npm"):
        pin = sc.load_stacks()["package_manager"].split("@", 1)[-1]
        subprocess.run(["npm", "install", "-g", f"pnpm@{pin}"], capture_output=True, text=True, timeout=600,
                       stdin=subprocess.DEVNULL)
        if shutil.which("pnpm"):
            return ["pnpm"]
    return None


def install(repo: Path, fresh_git: bool) -> list[dict]:
    pnpm = pnpm_argv()
    if not pnpm:
        return [{"step": "pnpm", "ok": False, "tail": "neither pnpm nor corepack is on PATH: install Node.js 22+"}]
    steps = []
    if fresh_git:
        steps.append(run(["git", "init", "-q", "-b", "main"], repo, "git init"))
    scanners = [security_tools.ensure(tool) for tool in ("osv-scanner", "gitleaks")]
    steps.append({"step": "security tools", "ok": all(r["ready"] for r in scanners),
                  "tail": "; ".join(r["detail"] for r in scanners if not r["ready"])})
    for argv, step in ((pnpm + ["install"], "pnpm install"),
                       (pnpm + ["install", "--dir", "tools/quality"], "quality tools install"),
                       (pnpm + ["exec", "lefthook", "install"], "lefthook install"),
                       (pnpm + ["exec", "biome", "check", "--write", "."], "format the base"),
                       (pnpm + ["run", "quality"], "pnpm quality")):
        if steps and not steps[-1]["ok"]:
            break
        steps.append(run(argv, repo, step))
    if fresh_git and all(s["ok"] for s in steps):
        steps.append(run(["git", "add", "-A"], repo, "git add"))
        steps.append(run(["git", "commit", "-q", "-m", "chore: strict project base"], repo, "first commit"))
    return steps


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0],
                                epilog="Exit 0 base ready or dry run, 1 a step failed, 2 usage error.")
    p.add_argument("--repo", required=True, help="the site repo folder (<site>/<site.yaml repo.path>)")
    p.add_argument("--stack", required=True, help="astro | nextjs | tanstack (stacks.json)")
    p.add_argument("--name", required=True, help="project slug, lowercase kebab-case")
    p.add_argument("--provider", default="cloudflare", help="site.yaml provider (cloudflare adds wrangler)")
    p.add_argument("--install", action="store_true", help="install, init git, hooks, run the gate, first commit")
    p.add_argument("--dry-run", action="store_true", help="list what would be written, change nothing")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args(argv)
    augment_path()
    stacks = sc.load_stacks()
    if args.stack not in stacks["stacks"] or not sc.NAME_RE.match(args.name):
        print(f"error: unknown stack {args.stack!r} or bad --name", file=sys.stderr)
        return 2
    repo = Path(args.repo).expanduser().resolve()
    report: dict = {}
    files, kept, fresh = plan_files(repo, stacks, args.stack, args.name, args.provider, report)
    fresh_git = not (repo / ".git").exists()
    result = {"repo": str(repo), "stack": args.stack, "fresh": fresh, "dry_run": args.dry_run,
              "written": sorted(files), "kept": kept, "steps": [], **report}
    if not args.dry_run:
        sc.write_tree(repo, files, False)
        if args.install:
            result["steps"] = install(repo, fresh_git and fresh)
    ok = all(s["ok"] for s in result["steps"]) and not result.get("manual")
    result["ok"] = ok
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"{'would write' if args.dry_run else 'wrote'} {len(files)} files, kept {len(kept)}")
        for s in result["steps"]:
            print(f"{'ok  ' if s['ok'] else 'FAIL'} {s['step']}" + ("" if s["ok"] else f"\n{s['tail']}"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
