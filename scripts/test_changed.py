#!/usr/bin/env python3
"""Run only the tests a change can break, in parallel; the whole suite when the change is too wide to scope.

The change is every path that differs from the merge-base of HEAD and <remote>/main (`--base` overrides it):
committed, staged, unstaged and untracked. Each path selects tests by these rules, first match wins:

  full        shared harness or wide-blast files (tests/conftest.py, tests/_real.py, tests/fakes/, squads/_base/,
              squads/_schema/, scripts/squadctl.py and the modules it imports, scripts/hpy): the whole suite.
  test file   tests/test_x.py selects itself and every test module that imports it.
  fixture     tests/fixtures/<x> or tests/golden/<x> selects the tests that name <x>.
  docs        README.md, AGENTS.md, llms.txt, CONTRIBUTING.md, docs/: test_docs.py and test_contracts.py.
  release     distribution.yaml and CHANGELOG.md: test_contracts.py and test_release.py.
  builder     builder.yaml: the squadctl tests (test_squadctl.py and the tests built on its harness),
              test_contracts.py and test_update_path.py.
  ignored     LICENSE, .gitignore, .github/: no test (CI runs the whole suite on every push).
  source      any other file: the tests that name it (file name, module import, owning skill, plugin or squad
              folder), plus the tests that name any script which imports or runs it, transitively; when squadctl
              is one of those scripts, the squadctl tests too (the walk stops there). A file under
              squads/<key>/ also selects every test of squad <key>; its squad.yaml or souls/ also select the
              tests that read every shipped manifest or SOUL and the squadctl tests; a builder skill's text is covered by the
              repo-wide checks below.

Every change adds the cheap repo-wide checks (test_contracts.py, test_docs.py, test_help_no_yaml.py); a change
under squads/ adds test_skill_ownership.py. A path no rule ties to a test, or a base that cannot be resolved,
runs the whole suite: the selector never answers "nothing to test" for a source change.

pytest runs with `-n auto` when pytest-xdist is installed (`pip install pytest-xdist`), else serially.
Exit code: pytest's (0 green), 2 usage error. `--list` prints the selection and runs nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
TESTS = "tests"

FULL_FILES = {"tests/conftest.py", "tests/_real.py", "scripts/squadctl.py", "scripts/squadctl", "scripts/hpy",
              "scripts/gate_lib.py", "scripts/_profile_apply.py", "scripts/hermes_home.py", "scripts/merge3.py"}
FULL_DIRS = ("tests/fakes/", "squads/_base/", "squads/_schema/")
IGNORED_FILES = {"LICENSE", ".gitignore"}
IGNORED_DIRS = (".github/",)
DOC_FILES = {"README.md", "AGENTS.md", "llms.txt", "CONTRIBUTING.md"}
DOC_TESTS = {"test_docs.py", "test_contracts.py"}
RELEASE_FILES = {"distribution.yaml": {"test_contracts.py", "test_release.py"},
                 "CHANGELOG.md": {"test_contracts.py", "test_release.py", "test_watch_upstream.py"}}
REPO_WIDE = {"test_contracts.py", "test_docs.py", "test_help_no_yaml.py"}
SQUADS_WIDE = {"test_skill_ownership.py"}
CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".sh", ".ts"}
# folder names too common to tie a file to a test on their own
GENERIC_DIRS = {"scripts", "skills", "squads", "references", "templates", "souls", "src", "lib", "tests", "desktop",
                "quality", "tools", "data", "assets", "fixtures", "golden", "_plugins"}


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=SRC)


def tracked() -> list[str]:
    return [p for p in git("ls-files").stdout.splitlines() if p]


def merge_base(base: str | None, remote: str = "origin") -> str | None:
    ref = base or f"{remote}/main"
    p = git("merge-base", "HEAD", ref)
    return p.stdout.strip() or None if p.returncode == 0 else None


def changed_paths(base: str | None, remote: str = "origin") -> list[str] | None:
    """Paths that differ from the merge-base (working tree included) plus untracked files; None = no base."""
    mb = merge_base(base, remote)
    if not mb:
        return None
    diff = git("diff", "--name-only", "--no-renames", mb)
    if diff.returncode != 0:
        return None
    untracked = git("ls-files", "--others", "--exclude-standard").stdout.splitlines()
    return sorted({p for p in [*diff.stdout.splitlines(), *untracked] if p})


# --- the repo model -----------------------------------------------------------------------------------------------

class Repo:
    def __init__(self, root: Path = SRC, files: list[str] | None = None):
        self.root = root
        self.files = files if files is not None else tracked()
        self.tests = sorted(p.name for p in (root / TESTS).glob("test_*.py"))
        raw = {t: (root / TESTS / t).read_text(encoding="utf-8", errors="replace") for t in self.tests}
        self.imports = {t: set(re.findall(r"^(?:from|import)\s+(test_\w+)", raw[t], re.M)) for t in self.tests}
        # a test sees the helpers it imports from other test modules: their paths are its paths too
        self.text = {}
        for t in self.tests:
            seen, todo, parts = set(), [t], []
            while todo:
                cur = todo.pop()
                if cur in seen or cur not in raw:
                    continue
                seen.add(cur)
                parts.append(raw[cur])
                todo += [f"{m}.py" for m in self.imports.get(cur, ())]
            self.text[t] = "\n".join(parts)
        names = Counter(Path(p).name for p in self.files)
        self.ambiguous = {n for n, c in names.items() if c > 1}
        stems = Counter(Path(p).stem for p in self.files if p.endswith(".py"))
        self._ambiguous_stems = {s for s, c in stems.items() if c > 1}
        self.code = [p for p in self.files if p.split("/")[0] in ("scripts", "squads", "skills")
                     and (Path(p).suffix in CODE_EXT or (p.startswith("scripts/") and "." not in Path(p).name))]
        self._code_text: dict[str, str] = {}
        self.reaches_hub = False

    def code_text(self, path: str) -> str:
        if path not in self._code_text:
            f = self.root / path
            self._code_text[path] = f.read_text(encoding="utf-8", errors="replace") if f.is_file() else ""
        return self._code_text[path]

    # tokens: how a test or a script names a file -----------------------------------------------------------------

    def tokens(self, path: str) -> set[str]:
        p = Path(path)
        out = set()
        if p.name not in self.ambiguous:
            out.add(p.name)
        if p.suffix == ".py" and p.stem not in self.ambiguous_stems():
            # import forms only: a bare quoted stem ("status") is also a CLI word and would match unrelated tests
            out |= {f"import {p.stem}\n", f"import {p.stem} ", f"from {p.stem} import"}
        for d in p.parts[:-1]:
            if d not in GENERIC_DIRS and d not in self.squad_keys() and not d.startswith("."):
                out |= {f'"{d}"', f"'{d}'", f"/{d}/"}
        return out

    def ambiguous_stems(self) -> set[str]:
        return self._ambiguous_stems

    def squad_keys(self) -> set[str]:
        if not hasattr(self, "_squad_keys"):
            self._squad_keys = {p.split("/")[1] for p in self.files if p.startswith("squads/")
                                and p.endswith("/squad.yaml") and p.count("/") == 2}
        return self._squad_keys

    def tests_naming(self, tokens: set[str]) -> set[str]:
        return {t for t in self.tests if any(tok in self.text[t] for tok in tokens)}

    def importers_of(self, test: str) -> set[str]:
        out, todo = set(), [test]
        while todo:
            cur = todo.pop()
            for t, mods in self.imports.items():
                if f"{cur[:-3]}" in mods and t not in out:
                    out.add(t)
                    todo.append(t)
        return out

    def dependents(self, path: str) -> set[str]:
        """Code files that import or run `path`, transitively (`path` included). The walk stops at the squadctl
        hub (FULL_FILES): squadctl names nearly every script, so walking through it would select the whole suite
        for any change; the tests of what squadctl does with a script name that script themselves."""
        out, todo = {path}, [path]
        while todo:
            cur = Path(todo.pop())
            if str(cur) in FULL_FILES and str(cur) != path:
                self.reaches_hub = True
                continue
            needles = set()
            if cur.name not in self.ambiguous:
                needles.add(cur.name)
            if cur.suffix == ".py":
                needles |= {f"import {cur.stem}\n", f"import {cur.stem} ", f"from {cur.stem} import"}
            for f in self.code:
                if f in out:
                    continue
                if cur.suffix == ".py" and cur.stem in self.ambiguous_stems() and Path(f).parent != cur.parent:
                    # a shared stem (cli, __init__) binds only inside its own folder
                    if not (cur.name not in self.ambiguous and cur.name in self.code_text(f)):
                        continue
                if any(n in self.code_text(f) for n in needles):
                    out.add(f)
                    todo.append(f)
        return out

    def hub_tests(self) -> set[str]:
        """test_squadctl.py and every test built on its fake-hermes harness."""
        return ({"test_squadctl.py"} & set(self.tests)) | self.importers_of("test_squadctl.py")

    def every_squad_tests(self) -> set[str]:
        """Tests that read every shipped manifest or SOUL through a glob or a per-key path."""
        marks = ('"*/squad.yaml"', '"*/souls/', '/ key / "squad.yaml"', 'squads/{key}/squad.yaml')
        return {t for t in self.tests if any(m in self.text[t] for m in marks)}

    def squad_tests(self, key: str) -> set[str]:
        marks = (f'"squads" / "{key}"', f"squads/{key}/", f"squad-{key}")
        return {t for t in self.tests if t.startswith(f"test_{key}_") or any(m in self.text[t] for m in marks)}


# --- selection ----------------------------------------------------------------------------------------------------

def select(paths: list[str], repo: Repo | None = None) -> dict:
    """{"full": bool, "reason": str, "tests": [...], "why": {path: [tests]}}."""
    repo = repo or Repo()
    picked: set[str] = set()
    why: dict[str, list[str]] = {}
    relevant = False
    for path in paths:
        if path in FULL_FILES or path.startswith(FULL_DIRS):
            return {"full": True, "reason": f"{path} is shared by the whole suite", "tests": [], "why": {}}
        if path in IGNORED_FILES or path.startswith(IGNORED_DIRS):
            why[path] = []
            continue
        relevant = True
        got: set[str] = set()
        name = Path(path).name
        if path.startswith(f"{TESTS}/") and path.count("/") == 1 and name.startswith("test_") and name.endswith(".py"):
            got = ({name} if name in repo.tests else set()) | repo.importers_of(name)
            if name not in repo.tests:  # a deleted test file: nothing left of it to run
                why[path] = sorted(got)
                picked |= got
                continue
        elif path.startswith((f"{TESTS}/fixtures/", f"{TESTS}/golden/")):
            sub = path.split("/")[2]
            sub_tokens = {f'"{sub}"', f"'{sub}'", f"/{sub}/", f"/ {sub!r}".replace("'", '"')}
            got = repo.tests_naming(sub_tokens | {Path(sub).name})
        elif path in DOC_FILES or path.startswith("docs/"):
            got = set(DOC_TESTS)
        elif path in RELEASE_FILES:
            got = set(RELEASE_FILES[path])
        elif path == "builder.yaml":
            got = repo.hub_tests() | {"test_contracts.py", "test_update_path.py"}
        else:
            repo.reaches_hub = False
            for dep in repo.dependents(path):
                got |= repo.tests_naming(repo.tokens(dep))
            if repo.reaches_hub:  # squadctl runs or imports it: squadctl's own tests exercise that path
                got |= repo.hub_tests()
            parts = path.split("/")
            if parts[0] == "squads" and len(parts) > 2 and not parts[1].startswith("_"):
                got |= repo.squad_tests(parts[1]) | SQUADS_WIDE
                if parts[2] == "squad.yaml" or parts[2] == "souls":
                    # shipped-manifest tests loop over every squad (`glob("*/squad.yaml")`, `squads / key /`)
                    got |= repo.every_squad_tests() | repo.hub_tests() | {"test_release.py", "test_update_path.py"}
            elif parts[0] == "squads" and len(parts) > 3 and parts[1] == "_plugins":
                got |= repo.tests_naming({f'"{parts[2]}"', f"/{parts[2]}/", f"{parts[2]}/"}) | SQUADS_WIDE
            elif parts[0] == "skills" and len(parts) > 2:
                got |= repo.tests_naming({f'"{parts[1]}"', f"skills/{parts[1]}"})
                if Path(path).suffix in (".md", ".json", ".yaml"):
                    got |= REPO_WIDE  # skill text: the repo-wide contracts read every builder skill
            elif parts[0] == "squads" and parts[1:2] and parts[1].startswith("_"):
                got |= SQUADS_WIDE
        if not got:
            return {"full": True, "reason": f"no test is tied to {path}", "tests": [], "why": {}}
        why[path] = sorted(got)
        picked |= got
    if relevant:
        picked |= REPO_WIDE
    return {"full": False, "reason": f"{len(paths)} changed path(s)", "tests": sorted(picked & set(repo.tests)),
            "why": why}


# --- running ------------------------------------------------------------------------------------------------------

def has_xdist(py: str) -> bool:
    return subprocess.run([py, "-c", "import xdist"], capture_output=True).returncode == 0


def pytest_argv(py: str, selection: dict, extra: list[str] | None = None, parallel: bool | None = None) -> list[str]:
    files = [] if selection["full"] else [f"{TESTS}/{t}" for t in selection["tests"]]
    par = has_xdist(py) if parallel is None else parallel
    return [py, "-m", "pytest", "-q", "-p", "no:cacheprovider", *(["-n", "auto"] if par else []), *files,
            *(extra or [])]


def plan(base: str | None, remote: str, full: bool) -> dict:
    if full:
        return {"full": True, "reason": "--full", "tests": [], "why": {}}
    paths = changed_paths(base, remote)
    if paths is None:
        return {"full": True, "reason": f"no merge-base with {base or remote + '/main'}", "tests": [], "why": {}}
    if not paths:
        return {"full": False, "reason": "no change", "tests": [], "why": {}}
    return select(paths)


def main(argv: list[str] | None = None) -> int:
    doc = __doc__ or ""
    ap = argparse.ArgumentParser(prog="test_changed.py", description=doc.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=doc.split("\n\n", 1)[1])
    ap.add_argument("--base", metavar="REF", help="compare with the merge-base of HEAD and REF (default: <remote>/main)")
    ap.add_argument("--remote", default="origin", help="remote whose main is the default base (default: origin)")
    ap.add_argument("--full", action="store_true", help="run the whole suite")
    ap.add_argument("--list", action="store_true", help="print the selection as JSON and run nothing")
    ap.add_argument("--serial", action="store_true", help="never pass -n auto, even with pytest-xdist installed")
    ap.add_argument("--python", metavar="PATH", default=None,
                    help="interpreter with pytest (default: .venv/bin/python, else the one running this script)")
    ap.add_argument("pytest_args", nargs="*", help="extra pytest arguments, after --")
    a = ap.parse_args(argv)
    sel = plan(a.base, a.remote, a.full)
    if a.list:
        print(json.dumps(sel, indent=2))
        return 0
    if not sel["full"] and not sel["tests"]:
        print(f"test_changed: {sel['reason']}: nothing to run")
        return 0
    venv = SRC / ".venv" / "bin" / "python"
    py = a.python or (str(venv) if venv.is_file() else sys.executable)
    cmd = pytest_argv(py, sel, a.pytest_args, parallel=False if a.serial else None)
    scope = "whole suite" if sel["full"] else f"{len(sel['tests'])} test file(s)"
    print(f"test_changed: {scope} ({sel['reason']}){'' if '-n' in cmd else ' serially: pip install pytest-xdist'}",
          flush=True)
    return subprocess.run(cmd, cwd=SRC).returncode


if __name__ == "__main__":
    sys.exit(main())
