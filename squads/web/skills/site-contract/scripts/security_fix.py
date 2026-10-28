#!/usr/bin/env python3
"""Install the fix of every known vulnerability in a site repo, without waiting for the release-age rule.

osv-scanner reads the lockfile. A vulnerable direct dependency first moves to its newest release old enough for the
repo's minimumReleaseAge (`pnpm add <name>`, no version), even across a major: a major bump is listed under `majors`
for the release-notes review in project-base.md. Whatever is still vulnerable after that gets the lowest release that
clears every advisory on its installed line: a direct dependency `pnpm add <name>@^<fixed>`, a transitive one an
override in pnpm-workspace.yaml. When the fix is younger than the repo's minimumReleaseAge, that exact release, and the
packages released with it under the same version (next@16.4.1 brings @next/env@16.4.1 and its @next/swc-*
binaries), go under minimumReleaseAgeExclude. Never a package name alone, never an unrelated young package: that
would open the door the rule exists to close. Exceptions whose release has aged past the rule are removed. Each
fix is logged in the site's decisions.md. The lockfile is scanned again at the end.

Exit 0 no known vulnerability left, 1 one is left (unfixed or no fix exists: the JSON says which), 2 could not scan.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from toolpath import augment_path  # noqa: E402

YOUNG_RE = re.compile(r"(@?[^\s@]+)@(\d[^\s,]*) was published")
TAIL = 1500


def vkey(version: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", version.split("-", 1)[0])[:3]) or (0,)


def fixed_for(vuln: dict, name: str, installed: str) -> str | None:
    """The `fixed` event of the advisory range that holds `installed`; None when the range has no fix."""
    have = vkey(installed)
    for affected in vuln.get("affected") or []:
        if (affected.get("package") or {}).get("name") != name:
            continue
        for rng in affected.get("ranges") or []:
            introduced, fixed = "0", None
            for event in rng.get("events") or []:
                if "introduced" in event:
                    introduced, fixed = event["introduced"], None
                elif "fixed" in event:
                    fixed = event["fixed"]
                    if vkey(introduced) <= have < vkey(fixed):
                        return fixed
            if fixed is None and vkey(introduced) <= have:
                return None
    return None


def plan_fixes(osv: dict) -> tuple[list[dict], list[dict]]:
    """([{name, installed, fixed, advisories}], [{name, installed, advisories}] with no fix)."""
    fixes, unfixable = [], []
    for result in osv.get("results") or []:
        for row in result.get("packages") or []:
            pkg = row.get("package") or {}
            name, installed = pkg.get("name"), pkg.get("version", "0")
            if pkg.get("ecosystem") != "npm" or not name:
                continue
            ids = sorted(v.get("id", "?") for v in row.get("vulnerabilities") or [])
            needed = [fixed_for(v, name, installed) for v in row.get("vulnerabilities") or []]
            found = [f for f in needed if f is not None]
            if len(found) < len(needed):
                unfixable.append({"name": name, "installed": installed, "advisories": ids})
            elif found:
                fixes.append({"name": name, "installed": installed, "fixed": max(found, key=vkey), "advisories": ids})
    return fixes, unfixable


def siblings(young: list[tuple[str, str]], name: str, version: str) -> tuple[list[str], list[str]]:
    """(allowed, refused) young releases pnpm named: only the fix itself and packages of its family released with
    it at the same version (same scope, or the `@<name>/` scope of an unscoped package)."""
    family = name.split("/")[0] if name.startswith("@") else f"@{name}"
    allowed, refused = [], []
    for pkg, ver in young:
        same = pkg == name or pkg.startswith(family + "/")
        (allowed if same and ver == version else refused).append(f"{pkg}@{ver}")
    return allowed, refused


# ---------------------------------------------------------------- pnpm-workspace.yaml, edited line by line
# (bots' system python has no YAML module; the base writes this file in this exact shape)

def block(lines: list[str], key: str) -> tuple[int, int] | None:
    start = next((i for i, ln in enumerate(lines) if ln.split("#", 1)[0].rstrip() == f"{key}:"), None)
    if start is None:
        return None
    end = next((j for j in range(start + 1, len(lines)) if lines[j] and not lines[j][0].isspace()), len(lines))
    return start, end


def add_to_block(lines: list[str], key: str, rows: list[str]) -> None:
    span = block(lines, key)
    if span is None:
        lines.extend([f"{key}:", *rows])
    else:
        have = {ln.strip() for ln in lines[span[0] + 1:span[1]]}
        lines[span[1]:span[1]] = [r for r in rows if r.strip() not in have]


def set_override(lines: list[str], name: str, spec: str) -> None:
    span = block(lines, "overrides")
    row = f"  '{name}': \"{spec}\""
    if span:
        for i in range(span[0] + 1, span[1]):
            if lines[i].strip().split(":", 1)[0].strip("'\"") == name:
                lines[i] = row
                return
    add_to_block(lines, "overrides", [row])


def excluded(lines: list[str]) -> list[str]:
    span = block(lines, "minimumReleaseAgeExclude")
    if not span:
        return []
    return [ln.strip().lstrip("-").strip().strip("'\"") for ln in lines[span[0] + 1:span[1]] if ln.strip()]


def drop_excluded(lines: list[str], specs: set[str]) -> None:
    span = block(lines, "minimumReleaseAgeExclude")
    if not span:
        return
    keep = [ln for ln in lines[span[0] + 1:span[1]] if ln.strip().lstrip("-").strip().strip("'\"") not in specs]
    lines[span[0]:span[1]] = ["minimumReleaseAgeExclude:", *keep] if keep else []


# ---------------------------------------------------------------- the registry and the tools

def run(argv: list[str], cwd: Path, timeout: int = 900, stdout_only: bool = False) -> tuple[int, str]:
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc)
    return done.returncode, done.stdout if stdout_only else done.stdout + done.stderr


def published(name: str, version: str, cwd: Path) -> float | None:
    code, out = run(["npm", "view", f"{name}@{version}", "time", "--json"], cwd, 120, stdout_only=True)
    try:
        stamp = json.loads(out).get(version) if code == 0 else None
        return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp() if stamp else None
    except (ValueError, AttributeError):
        return None


def min_age_minutes(lines: list[str]) -> int:
    hit = next((ln for ln in lines if ln.startswith("minimumReleaseAge:")), "minimumReleaseAge: 0")
    return int(re.sub(r"\D", "", hit.split("#", 1)[0]) or 0)


def scan(repo: Path) -> tuple[dict | None, str]:
    osv = shutil.which("osv-scanner")
    if not osv:
        return None, "osv-scanner is not installed: run security_tools.py ensure osv-scanner"
    code, out = run([osv, "scan", "source", "--lockfile", "pnpm-lock.yaml", "--format", "json"], repo, 300,
                    stdout_only=True)
    if code > 1:
        return None, f"osv-scanner exit {code}: {out[-TAIL:]}"
    try:
        return json.loads(out[out.index("{"):]) if code == 1 else {"results": []}, ""
    except ValueError:
        return None, f"osv-scanner gave no JSON: {out[-TAIL:]}"


def direct_group(repo: Path, name: str) -> str | None:
    pkg = json.loads((repo / "package.json").read_text(encoding="utf-8"))
    for group in ("dependencies", "devDependencies", "optionalDependencies"):
        if name in (pkg.get(group) or {}):
            return group
    return None


def declared(repo: Path, name: str) -> str:
    group = direct_group(repo, name)
    spec = (json.loads((repo / "package.json").read_text(encoding="utf-8")).get(group) or {}).get(name, "")
    return spec.lstrip("^~=v") if group else ""


def newest(repo: Path, fixes: list[dict], held: list[str]) -> list[dict]:
    """Move each vulnerable direct dependency to its newest release old enough to install; a release already let in
    early (held under minimumReleaseAgeExclude) is never pulled back to an older one."""
    moved = []
    for fix in fixes:
        group = direct_group(repo, fix["name"])
        if not group or f"{fix['name']}@{fix['installed']}" in held:
            continue
        code, _ = run(["pnpm", "add", *(["-D"] if group == "devDependencies" else []), fix["name"]], repo)
        now = declared(repo, fix["name"])
        if code == 0 and now and vkey(now) > vkey(fix["installed"]):
            moved.append({**fix, "fixed": now, "ok": True, "how": "newest", "excepted": [],
                          "major": vkey(now)[:1] != vkey(fix["installed"])[:1]})
    return moved


def apply_fix(repo: Path, fix: dict, ws: Path) -> dict:
    """Install one fix; young releases of its own family go under minimumReleaseAgeExclude, retried until pnpm
    accepts or names a young release outside the family."""
    group = direct_group(repo, fix["name"])
    argv = (["pnpm", "add", *(["-D"] if group == "devDependencies" else []), f"{fix['name']}@^{fix['fixed']}"]
            if group else ["pnpm", "install"])
    if not group:
        lines = ws.read_text(encoding="utf-8").splitlines()
        set_override(lines, fix["name"], f"^{fix['fixed']}")
        ws.write_text("\n".join(lines) + "\n", encoding="utf-8")
    excepted: list[str] = []
    for _ in range(4):
        code, out = run(argv, repo)
        if code == 0:
            return {**fix, "ok": True, "how": "direct" if group else "override", "excepted": excepted}
        young = YOUNG_RE.findall(out)
        allowed, refused = siblings(young, fix["name"], fix["fixed"])
        new = [spec for spec in allowed if spec not in excepted]
        if refused or not new:
            return {**fix, "ok": False, "excepted": excepted, "refused": refused, "tail": out[-TAIL:]}
        lines = ws.read_text(encoding="utf-8").splitlines()
        add_to_block(lines, "minimumReleaseAgeExclude", [f"  - '{spec}'" for spec in new])
        ws.write_text("\n".join(lines) + "\n", encoding="utf-8")
        excepted += new
    return {**fix, "ok": False, "excepted": excepted, "tail": "pnpm kept asking for more young releases"}


def prune(repo: Path, ws: Path, now: float) -> list[str]:
    """Exceptions whose exact release is now older than the rule: they are no longer needed."""
    lines = ws.read_text(encoding="utf-8").splitlines()
    age = min_age_minutes(lines) * 60
    old = set()
    for spec in excluded(lines):
        name, _, version = spec.rpartition("@")
        stamp = published(name, version, repo) if name and version[:1].isdigit() else None
        if stamp is not None and now - stamp >= age:
            old.add(spec)
    if old:
        drop_excluded(lines, old)
        ws.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return sorted(old)


def log_decisions(repo: Path, rows: list[dict]) -> Path | None:
    """One line per fix in the site's decisions.md (the folder holding site.yaml: the repo's parent or itself)."""
    site = next((d for d in (repo.parent, repo) if (d / "site.yaml").is_file()), None)
    if site is None or not rows:
        return None
    path = site / "decisions.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else "# Decisions\n"
    for row in rows:
        early = (f"; installed before the release-age rule as {', '.join(row['excepted'])} (exact releases, removed "
                 "once old enough)") if row["excepted"] else ""
        early += "; major bump, release notes reviewed per project-base.md before the card closes" if row.get("major") else ""
        text = text.rstrip("\n") + (f"\n- {date.today().isoformat()} security fix: {row['name']} {row['installed']} -> "
                                    f"{row['fixed']} ({', '.join(row['advisories'])}){early}.\n")
    path.write_text(text, encoding="utf-8")
    return path


def fix_repo(repo: Path) -> dict:
    augment_path()
    ws = repo / "pnpm-workspace.yaml"
    if not (repo / "pnpm-lock.yaml").is_file() or not ws.is_file():
        return {"ok": False, "exit": 2, "error": "pnpm-lock.yaml or pnpm-workspace.yaml missing: run site_base.py"}
    pruned = prune(repo, ws, time.time())
    if pruned:
        run(["pnpm", "install"], repo)
    osv, error = scan(repo)
    if osv is None:
        return {"ok": False, "exit": 2, "error": error, "pruned": pruned}
    fixes, unfixable = plan_fixes(osv)
    moved = newest(repo, fixes, excluded(ws.read_text(encoding="utf-8").splitlines()))
    if moved:
        osv, error = scan(repo)
        if osv is None:
            return {"ok": False, "exit": 2, "error": error, "fixed": moved, "pruned": pruned}
        fixes, unfixable = plan_fixes(osv)
    done = [*moved, *(apply_fix(repo, fix, ws) for fix in fixes)]
    log = log_decisions(repo, [d for d in done if d["ok"]])
    after, error = scan(repo) if fixes or moved else (osv, "")
    left = plan_fixes(after)[0] + plan_fixes(after)[1] if after is not None else []
    ok = after is not None and not left
    return {"ok": ok, "exit": 0 if ok else (2 if after is None else 1), "fixed": [d for d in done if d["ok"]],
            "failed": [d for d in done if not d["ok"]], "unfixable": unfixable, "left": left, "pruned": pruned,
            "majors": [{"name": d["name"], "from": d["installed"], "to": d["fixed"]} for d in done if d.get("major")],
            "decisions": str(log) if log else None, **({"error": error} if error else {})}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0],
                                epilog="Exit 0 clean, 1 a vulnerability is left, 2 could not scan.")
    p.add_argument("--repo", required=True, help="the site repo (holds pnpm-lock.yaml)")
    args = p.parse_args(argv)
    result = fix_repo(Path(args.repo).expanduser().resolve())
    print(json.dumps(result, indent=2))
    return result["exit"]


if __name__ == "__main__":
    raise SystemExit(main())
