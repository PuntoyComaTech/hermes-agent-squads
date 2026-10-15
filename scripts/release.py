#!/usr/bin/env python3
"""Release gate: push to main only with every check green.

Checks before any release: a `distribution.yaml` version bump over `<remote>/main` and a `## <version>`
CHANGELOG.md entry, then the gates `pytest`, `skill_lint.py skills squads`, the squad schema (builder.yaml
and every squads/<key>/squad.yaml against squads/_schema/squad.schema.json) and `squadctl plan` for every
squad plus `--self`, all against a temporary HERMES_HOME (nothing of the real ~/.hermes is read or written).

Every check green: `git push <remote> HEAD:main`. Any check red: main is left alone and the work is
proposed with `gh pr create --push` instead, listing the red checks. Maintainer notes go to
`local/upstream-notes/<date>-<slug>.yaml` (skill contributing-upstream).

Exit codes: 0 released (or --dry-run with every check green), 1 a check is red (a PR was opened),
2 usage or environment error.
"""
import argparse
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

def meta_checks(new: str | None, old: str | None, changelog: str, remote: str) -> list[tuple[str, bool, str]]:
    """`distribution.yaml` bump over <remote>/main and a CHANGELOG.md entry for the new version."""
    out: list[tuple[str, bool, str]] = []
    if not new:
        out.append(("bump", False, "distribution.yaml has no x.y.z version"))
        return out
    if old is None:
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
    p = run_cmd([py, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    tail = (p.stdout or p.stderr).strip().splitlines()
    return "pytest", p.returncode == 0, tail[-1] if tail else f"exit {p.returncode}"


def gate_skill_lint(py: str) -> tuple[str, bool, str]:
    p = run_cmd([py, "scripts/skill_lint.py", "skills", "squads"])
    tail = (p.stdout or p.stderr).strip().splitlines()
    return "skill_lint", p.returncode == 0, tail[-1] if tail else f"exit {p.returncode}"


def gate_schema() -> tuple[str, bool, str]:
    try:
        import yaml
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        return "schema", False, f"needs pyyaml + jsonschema (pip install pyyaml jsonschema): {exc}"
    import json

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
    ap.add_argument("--python", metavar="PATH", help="interpreter for the pytest/skill_lint gates "
                    "(default: .venv/bin/python, else the one running this script)")
    ap.add_argument("--remote", default="origin", help="git remote holding main (default: origin)")
    ap.add_argument("--only", action="append", metavar="GATE", choices=["pytest", "skill_lint", "schema", "plan"],
                    help="run only this gate (repeatable); the bump and changelog checks always run")
    a = ap.parse_args(argv)

    try:
        old = dist_version(run_cmd(["git", "show", f"{a.remote}/main:distribution.yaml"],
                                   env={**os.environ}).stdout)
    except (OSError, subprocess.SubprocessError):
        old = None
    new = dist_version((SRC / "distribution.yaml").read_text())
    checks = meta_checks(new, old, (SRC / "CHANGELOG.md").read_text(), a.remote)
    py = pick_python(a.python)
    for name, fn in (("pytest", lambda: gate_pytest(py)), ("skill_lint", lambda: gate_skill_lint(py)),
                     ("schema", gate_schema), ("plan", lambda: gate_plan(py))):
        if a.only and name not in a.only:
            continue
        checks.append(fn())
    for name, ok, detail in checks:
        print(f"{'ok   ' if ok else 'RED  '} {name}: {detail}")
    red = [c for c in checks if not c[1]]
    if a.dry_run:
        print(f"dry-run: {'would push HEAD to main' if not red else 'would open a PR (checks red)'}")
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
