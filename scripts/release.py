#!/usr/bin/env python3
"""Release gate: push to main only with every check green.

Checks: a clean working tree (the gates test what HEAD pushes), a `distribution.yaml` version bump over
`<remote>/main` (fetched first; no main on the remote = first release) and a `## <version>` CHANGELOG.md entry.
Gates: `pytest`, `skill_lint.py skills squads`, the squad schema (builder.yaml and every squads/<key>/squad.yaml
against squads/_schema/squad.schema.json) and `squadctl plan` for every squad plus `--self` on a temporary
HERMES_HOME. pytest, skill_lint and the schema run under --python, which needs pytest, pyyaml and
jsonschema: under scripts/hpy the default is the Hermes runtime, which has none of them, so pass
`--python .venv/bin/python` (the pytest gate says so when they are missing).

Every check green: `git push <remote> HEAD:main`. Any check red: main is left alone and the work is proposed
with `gh pr create --push`, listing the red checks. `--dry-run` and `--only` never push and never open a PR.

Exit codes: 0 released (or every check green without pushing), 1 a check is red, 2 the push failed.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^version:\s*[\"']?(\d+\.\d+\.\d+)[\"']?\s*$", re.M)
CHANGELOG_RE = r"^##\s+{version}\b"


# --- helpers ----------------------------------------------------------------------------------------------------------

def run_cmd(argv: list[str], env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, cwd=SRC, env=env, timeout=1800)


def pick_python(explicit: str | None) -> str:
    """Interpreter for the pytest and skill_lint gates: --python, else .venv/bin/python, else this one."""
    if explicit:
        return explicit
    venv = SRC / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def dist_version(text: str | None) -> str | None:
    m = VERSION_RE.search(text or "")
    return m.group(1) if m else None


def version_tuple(v: str) -> tuple[int, ...]:
    return tuple(int(p) for p in v.split("."))


# --- checks -----------------------------------------------------------------------------------------------------------

def remote_main_version(remote: str) -> tuple[str | None, str | None]:
    """(version on <remote>/main, error). No main branch, or no distribution.yaml on it, is a first release
    (None, None); an unreachable remote is an error, never a first release."""
    probe = run_cmd(["git", "ls-remote", "--exit-code", "--heads", remote, "main"])
    if probe.returncode == 2:
        return None, None
    if probe.returncode != 0:
        return None, f"cannot read {remote}/main: {(probe.stderr or probe.stdout).strip()[-200:]}"
    fetch = run_cmd(["git", "fetch", "--quiet", remote, "main"])
    if fetch.returncode != 0:
        return None, f"git fetch {remote} main failed: {(fetch.stderr or fetch.stdout).strip()[-200:]}"
    shown = run_cmd(["git", "show", "FETCH_HEAD:distribution.yaml"])
    return (dist_version(shown.stdout) if shown.returncode == 0 else None), None


def clean_check() -> tuple[str, bool, str]:
    p = run_cmd(["git", "status", "--porcelain"])
    dirty = [ln for ln in p.stdout.splitlines() if ln.strip()]
    if p.returncode != 0:
        return "clean", False, f"git status failed: {p.stderr.strip()[-200:]}"
    return ("clean", not dirty, "working tree clean" if not dirty
            else f"{len(dirty)} uncommitted change(s): commit them so the gates test what HEAD pushes")


def meta_checks(new: str | None, old: str | None, changelog: str, remote: str,
                error: str | None = None) -> list[tuple[str, bool, str]]:
    """`distribution.yaml` bump over <remote>/main and a CHANGELOG.md entry for the new version."""
    out: list[tuple[str, bool, str]] = []
    if not new:
        out.append(("bump", False, "distribution.yaml has no x.y.z version"))
        return out
    if error:
        out.append(("bump", False, error))
    elif old is None:
        out.append(("bump", True, f"{new}: no distribution.yaml on {remote}/main (first release)"))
    elif version_tuple(new) > version_tuple(old):
        out.append(("bump", True, f"{old} -> {new}"))
    else:
        out.append(("bump", False, f"distribution.yaml version {new} is not a bump over {remote}/main ({old})"))
    entry = re.search(CHANGELOG_RE.format(version=re.escape(new)), changelog, re.M)
    out.append(("changelog", bool(entry),
                f"CHANGELOG.md has '## {new}'" if entry else f"CHANGELOG.md needs a '## {new}' entry"))
    return out


def gate_pytest(py: str) -> tuple[str, bool, str]:
    probe = run_cmd([py, "-c", "import pytest, yaml, jsonschema"])
    if probe.returncode != 0:
        return ("pytest", False, f"{py} lacks pytest, pyyaml or jsonschema (the Hermes runtime under scripts/hpy "
                "has none): pass --python .venv/bin/python")
    p = run_cmd([py, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    tail = (p.stdout or p.stderr).strip().splitlines()
    return "pytest", p.returncode == 0, tail[-1] if tail else f"exit {p.returncode}"


def gate_skill_lint(py: str) -> tuple[str, bool, str]:
    p = run_cmd([py, "scripts/skill_lint.py", "skills", "squads"])
    tail = (p.stdout or p.stderr).strip().splitlines()
    return "skill_lint", p.returncode == 0, tail[-1] if tail else f"exit {p.returncode}"


def gate_schema(py: str | None = None) -> tuple[str, bool, str]:
    """In this process, or under `py` when given (the interpreter that has pyyaml and jsonschema)."""
    if py:
        code = "import json, runpy, sys; print(json.dumps(runpy.run_path(sys.argv[1])['gate_schema']()))"
        try:
            p = run_cmd([py, "-c", code, str(Path(__file__).resolve())])
        except OSError as exc:
            return "schema", False, f"cannot run {py}: {exc}"[:200]
        try:
            name, ok, detail = json.loads(p.stdout.strip().splitlines()[-1])
            return name, ok, detail
        except (ValueError, IndexError):
            return "schema", False, f"schema gate failed under {py}: {(p.stderr or p.stdout).strip()[-200:]}"
    try:
        import yaml
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        return "schema", False, f"needs pyyaml + jsonschema (pip install pyyaml jsonschema): {exc}"
    validator = Draft202012Validator(json.loads((SRC / "squads" / "_schema" / "squad.schema.json").read_text()))
    bad = []
    for path in [SRC / "builder.yaml", *sorted((SRC / "squads").glob("*/squad.yaml"))]:
        for err in validator.iter_errors(yaml.safe_load(path.read_text())):
            bad.append(f"{path.name}: {'/'.join(map(str, err.absolute_path))}: {err.message}")
    return ("schema", not bad, "; ".join(bad[:3]) if bad else "builder.yaml and every squads/<key>/squad.yaml valid")


def gate_plan(py: str) -> tuple[str, bool, str]:
    """`squadctl plan` for every squad plus --self against a temporary HERMES_HOME."""
    plans = [["plan", "--self", "--json"], *[["plan", key, "--json"] for key in squad_keys()]]
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "HERMES_HOME": tmp, "HPY_PYTHON": py}
        ran = []
        for args in plans:
            p = run_cmd([str(SRC / "scripts" / "squadctl"), *args], env=env)
            ran.append((args, p))
            if p.returncode != 0:
                tail = (p.stdout or p.stderr).strip().splitlines()
                return "plan", False, f"squadctl {' '.join(args)} failed: {tail[-1] if tail else p.returncode}"
    return "plan", True, f"{len(ran)} plans green on a temp root ({', '.join(squad_keys())}, --self)"


def squad_keys() -> list[str]:
    return sorted(p.parent.name for p in (SRC / "squads").glob("*/squad.yaml"))


# --- release actions --------------------------------------------------------------------------------------------------

def push_to_main(remote: str) -> tuple[bool, str]:
    p = run_cmd(["git", "push", remote, "HEAD:main"])
    return p.returncode == 0, (p.stderr or p.stdout).strip()[-400:]


def open_pr(remote: str, checks: list[tuple[str, bool, str]]) -> tuple[bool, str]:
    red = [f"- {name}: {detail}" for name, ok, detail in checks if not ok]
    body = "Release checks red; main untouched.\n\n" + "\n".join(red)
    p = run_cmd(["gh", "pr", "create", "--push", "--base", "main", "--title",
                 f"release: {dist_version((SRC / 'distribution.yaml').read_text()) or 'unknown'} (checks red)",
                 "--body", body])
    return p.returncode == 0, (p.stdout or p.stderr).strip()[-400:]


# --- main -------------------------------------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(prog="release.py", description=doc.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog=doc.split("\n\n", 1)[1])
    ap.add_argument("--dry-run", action="store_true", help="run every check but never push or open a PR")
    ap.add_argument("--python", metavar="PATH", help="interpreter with pytest, pyyaml and jsonschema for the "
                    "pytest, skill_lint and schema gates (default: .venv/bin/python, else the one running "
                    "this script; under scripts/hpy that is the Hermes runtime, which lacks pytest)")
    ap.add_argument("--remote", default="origin", help="git remote holding main (default: origin)")
    ap.add_argument("--only", action="append", metavar="GATE", choices=["pytest", "skill_lint", "schema", "plan"],
                    help="run only this gate (repeatable; implies --dry-run); the tree, bump and changelog "
                         "checks always run")
    a = ap.parse_args(argv)

    try:
        old, error = remote_main_version(a.remote)
    except (OSError, subprocess.SubprocessError) as exc:
        old, error = None, f"cannot read {a.remote}/main: {exc}"
    new = dist_version((SRC / "distribution.yaml").read_text())
    checks = [clean_check(), *meta_checks(new, old, (SRC / "CHANGELOG.md").read_text(), a.remote, error)]
    py = pick_python(a.python)
    for name, fn in (("pytest", lambda: gate_pytest(py)), ("skill_lint", lambda: gate_skill_lint(py)),
                     ("schema", lambda: gate_schema(py)), ("plan", lambda: gate_plan(py))):
        if a.only and name not in a.only:
            continue
        try:
            checks.append(fn())
        except (OSError, subprocess.SubprocessError) as exc:  # a missing interpreter or tool is a red gate
            checks.append((name, False, f"{type(exc).__name__}: {exc}"[:200]))
    for name, ok, detail in checks:
        print(f"{'ok   ' if ok else 'RED  '} {name}: {detail}")
    red = [c for c in checks if not c[1]]
    if a.dry_run or a.only:
        mode = "partial run (--only)" if a.only else "dry-run"
        print(f"{mode}: {'would push HEAD to main' if not red and not a.only else 'nothing pushed'}"
              + (" (checks red: would open a PR)" if red else ""))
        return 1 if red else 0
    if not red:
        ok, detail = push_to_main(a.remote)
        print(f"push {a.remote} HEAD:main: {'done' if ok else detail}")
        return 0 if ok else 2
    ok, detail = open_pr(a.remote, checks)
    print(f"PR (checks red): {'opened' if ok else detail}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
