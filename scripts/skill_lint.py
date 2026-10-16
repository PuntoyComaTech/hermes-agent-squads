#!/usr/bin/env python3
"""Format gate for skills and SOUL files.

Checks every skill dir (SKILL.md plus references/, scripts/, templates/, assets/, evals/) and every SOUL file
against RULES (`--rules` lists every rule id and its budget).

Exit codes: 0 clean, 1 findings, 2 usage error.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
DEFAULT_ROLES = SCRIPTS_DIR / "data" / "model-roles.yaml"


def _yaml():
    """YAML module on first use, never at import: `--help` must work without PyYAML (scripts/hpy provides
    hermes_yaml; a bare python3 falls back to PyYAML when a command actually reads YAML)."""
    try:
        import hermes_yaml as y  # the Hermes runtime's YAML module
    except ImportError:
        try:
            import yaml as y
        except ImportError:
            raise SystemExit("error: no YAML module: run scripts/hpy skill_lint.py (Hermes runtime) or install PyYAML") from None
    return y

RULES = {
    "frontmatter-required": "SKILL.md has no YAML frontmatter with name and description",
    "name-kebab": "name is not lowercase kebab-case",
    "name-gerund": "first token of name does not end in -ing (exempt: *-contract, hermes-platform, "
                   "hermes-local-notes, marketing-*)",
    "name-dir-mismatch": "frontmatter name differs from the skill directory name",
    "name-length": "name longer than 40 characters",
    "desc-third-person": "description does not open with a third-person verb",
    "desc-capability-length": "capability clause before 'Use when' longer than 57 characters",
    "desc-use-when": "description has no 'Use when' clause",
    "desc-length": "description longer than 250 characters",
    "skill-lines": "SKILL.md longer than its budget (manager/builder 150, worker 120)",
    "manager-naming": "manifest naming: one manager named <key> with title '<Name> manager', workers <key>-<role>, at most 5 required bots",
    "index-lines": "hermes-platform SKILL.md longer than 80 lines",
    "ref-lines": "references/*.md longer than 200 lines",
    "ref-depth": "references nested more than one level deep",
    "ref-toc": "references file over 100 lines without a Contents heading in its first 20 lines",
    "children-allowed": "skill dir has a child outside SKILL.md, references/, scripts/, templates/, assets/, evals/evals.json",
    "script-help": "a script exits non-zero on --help",
    "script-py-compile": "a Python script fails to compile (--help is not checked for it)",
    "script-bash-n": "a shell script fails bash -n (shellcheck and --help are not checked for it)",
    "script-shellcheck": "a shell script has shellcheck findings",
    "language-english": "Spanish stopword ratio above 3%",
    "model-ids": "a model id appears outside model-roles.yaml and installed.yaml",
    "body-sections": "body lacks one of When to Use, Procedure, Pitfalls, Verification",
    "evals-count": "evals/evals.json does not hold exactly 3 scenarios",
    "soul-lines": "SOUL file longer than 6 lines",
    "soul-chars": "SOUL file longer than 800 characters",
}

NAME_MAX = 40
DESC_MAX = 250
CAPABILITY_MAX = 57
MANAGER_LINES, WORKER_LINES, INDEX_LINES = 150, 120, 80
REF_MAX, REF_TOC_AFTER, TOC_WINDOW = 200, 100, 20
SOUL_LINES, SOUL_CHARS = 6, 800
SPANISH_MAX = 0.03
EVALS_COUNT = 3
HELP_TIMEOUT = 20

INDEX_SKILL = "hermes-platform"
# Names the Hermes platform itself requires (the `hermes-platform` index, the local notes skill every profile
# installs) do not follow the verb-ing shape; the vetted marketing skills are exempt too.
GERUND_ALLOWLIST = {INDEX_SKILL, "hermes-local-notes", "marketing-plan", "product-marketing", "marketing-council",
                    "marketing-psychology"}
ALLOWED_CHILDREN = {"references", "scripts", "templates", "assets", "evals"}
IGNORED = {".DS_Store", "__pycache__"}
SKIP_DIRS = {".git", "node_modules", "tests", "docs", "__pycache__", "_schema", ".github"}
BODY_SECTIONS = ("when to use", "procedure", "pitfalls", "verification")
NOT_THIRD_PERSON = {"you", "your", "i", "we", "our", "my", "this", "these", "use"}

# Spanish stopwords minus English homographs (a, no, me, he, son, sin, come, con, ten, sea, van, es, se, si, su, mi, al,
# ya, tan, lo, les, un, y, o).
SPANISH_STOPWORDS = frozenset("""
el la los las una unos unas del de en por para pero porque como cuando donde que quien cual cuales cada
nunca siempre tambien tampoco aqui alli ahora entonces cuyo muy mas menos todo todos toda todas otro otra otros otras
mismo misma esto esta estos estas ese esa esos esas aquel aquella este
tiene tienen tener hay fue fueron ser eres somos sois sido esta estan estar estamos
sobre entre hasta desde hacia segun durante mediante contra ante bajo tras
nosotros ustedes ellos ellas usted nuestro nuestra vuestro tus sus
aunque sino mientras ademas incluso antes despues
puede pueden debe deben hacer hace hacen
""".split())
WORD_RE = re.compile(r"[a-zA-Z\u00c0-\u00ff]{2,}")
FENCE_RE = re.compile(r"^(```|~~~).*?^\1\s*$", re.M | re.S)
GENERIC_MODEL_RE = (
    r"claude-(?:opus|sonnet|haiku|fable)-\d[\w.\[\]-]*|gpt-\d[\w.-]*|gemini-\d[\w.-]*|deepseek-v\d[\w.-]*"
    r"|kimi-k\d[\w.-]*|glm-\d[\w.-]*|mimo-v\d[\w.-]*"
)


class Linter:
    def __init__(self, roles_path: Path, role: str | None, require_shellcheck: bool, run_scripts: bool):
        self.findings: list[dict] = []
        self.skipped: list[str] = []
        self.targets: list[str] = []
        self.role = role
        self.require_shellcheck = require_shellcheck
        self.run_scripts = run_scripts
        self.model_re = self._model_regex(roles_path)
        self.shellcheck = shutil.which("shellcheck")
        self.home = tempfile.mkdtemp(prefix="skill-lint-")

    @staticmethod
    def _model_regex(roles_path: Path) -> re.Pattern:
        parts = [GENERIC_MODEL_RE]
        if roles_path.is_file():
            roles = _yaml().safe_load(roles_path.read_text(encoding="utf-8")) or {}
            for lane in (roles.get("lanes") or {}).values():
                parts += [c["match"] for c in lane.get("candidates", []) if c.get("match")]
        return re.compile(r"(?<![\w.-])(?:" + "|".join(parts) + r")(?![\w.])", re.I)

    def add(self, rule: str, path: Path, message: str, line: int | None = None) -> None:
        finding = {"rule": rule, "path": str(path), "message": message}
        if line:
            finding["line"] = line
        self.findings.append(finding)

    # --- shared text checks -----------------------------------------------------------------------------------------

    def check_language(self, path: Path, text: str) -> None:
        words = WORD_RE.findall(FENCE_RE.sub(" ", text).replace("`", " ").lower())
        if len(words) < 10:
            return
        ratio = sum(w in SPANISH_STOPWORDS for w in words) / len(words)
        if ratio > SPANISH_MAX:
            self.add("language-english", path, f"Spanish stopword ratio {ratio:.1%} exceeds {SPANISH_MAX:.0%}")

    def check_model_ids(self, path: Path, text: str) -> None:
        for number, line in enumerate(text.splitlines(), 1):
            hit = self.model_re.search(line)
            if hit:
                self.add("model-ids", path, f"model id '{hit.group(0)}' belongs in model-roles.yaml or installed.yaml", number)
                return

    # --- SOUL ---------------------------------------------------------------------------------------------------------

    def lint_soul(self, path: Path) -> None:
        self.targets.append(str(path))
        text = path.read_text(encoding="utf-8")
        lines = len(text.splitlines())
        if lines > SOUL_LINES:
            self.add("soul-lines", path, f"{lines} lines, budget {SOUL_LINES}")
        if len(text.rstrip("\n")) > SOUL_CHARS:
            self.add("soul-chars", path, f"{len(text.rstrip(chr(10)))} characters, budget {SOUL_CHARS}")
        self.check_language(path, text)
        self.check_model_ids(path, text)

    def lint_squad_yaml(self, path: Path) -> None:
        self.targets.append(str(path))
        text = path.read_text(encoding="utf-8")
        self.check_model_ids(path, text)
        if path.name == "builder.yaml":
            return  # the builder's profile name follows `--builder`, not the squad naming rules
        try:
            doc = _yaml().safe_load(text) or {}
        except Exception:
            return
        bots, key = doc.get("bots") or {}, doc.get("key")
        name = doc.get("name") or key
        problems = []
        if "lead" in doc and "manager" not in doc:
            problems.append("field 'lead' was renamed to 'manager'")
        managers = [b for b, s in bots.items() if (s or {}).get("role") == "manager"]
        if bots and managers != [doc.get("manager")]:
            problems.append(f"exactly one bot must have role manager and match the manager field (got {managers})")
        elif bots and doc.get("manager") != key:
            problems.append(f"manager {doc.get('manager')!r} must be named after the squad key {key!r}")
        elif bots and (bots.get(key) or {}).get("title") != f"{name} manager":
            problems.append(f"manager title must be {name} manager")
        unprefixed = [b for b, s in bots.items()
                      if (s or {}).get("role") == "worker" and not str(b).startswith(f"{key}-")]
        if unprefixed:
            problems.append(f"workers must be named {key}-<role>: {', '.join(unprefixed)}")
        required = [b for b, s in bots.items() if not (s or {}).get("optional")]
        if len(required) > 5:
            problems.append(f"{len(required)} required bots: at most 5 (extra bots set optional: true)")
        for problem in problems:
            self.add("manager-naming", path, problem)

    # --- skill --------------------------------------------------------------------------------------------------------

    def lint_skill(self, skill: Path) -> None:
        self.targets.append(str(skill))
        text = (skill / "SKILL.md").read_text(encoding="utf-8")
        meta = self.frontmatter(text)
        skill_md = skill / "SKILL.md"
        if meta is None:
            self.add("frontmatter-required", skill_md, "no YAML frontmatter with string name and description")
        else:
            self.check_name(skill, skill_md, meta["name"])
            self.check_description(skill_md, " ".join(meta["description"].split()))
        self.check_size(skill, skill_md, text, meta["name"] if meta else skill.name)
        self.check_sections(skill_md, text)
        self.check_children(skill)
        self.check_references(skill)
        self.check_evals(skill)
        if self.run_scripts:
            self.check_scripts(skill)
        for md in [skill_md, *sorted((skill / "references").glob("*.md"))]:
            self.check_language(md, md.read_text(encoding="utf-8"))
        for f in sorted(skill.rglob("*")):
            if f.is_file() and not set(f.relative_to(skill).parts) & IGNORED:
                try:
                    self.check_model_ids(f, f.read_text(encoding="utf-8"))
                except UnicodeDecodeError:
                    continue

    @staticmethod
    def frontmatter(text: str) -> dict | None:
        match = re.match(r"---\r?\n(.*?)\r?\n---\s*(?:\r?\n|$)", text, re.S)
        if not match:
            return None
        try:
            meta = _yaml().safe_load(match.group(1))
        except Exception:
            return None
        if isinstance(meta, dict) and all(isinstance(meta.get(k), str) and meta[k].strip() for k in ("name", "description")):
            return meta
        return None

    def check_name(self, skill: Path, path: Path, name: str) -> None:
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
            self.add("name-kebab", path, f"name '{name}' is not lowercase kebab-case")
        if len(name) > NAME_MAX:
            self.add("name-length", path, f"name is {len(name)} characters, budget {NAME_MAX}")
        if name != skill.name:
            self.add("name-dir-mismatch", path, f"name '{name}' differs from directory '{skill.name}'")
        exempt = name in GERUND_ALLOWLIST or name.endswith("-contract")
        if not exempt and not name.split("-")[0].lower().endswith("ing"):
            self.add("name-gerund", path, f"'{name}' does not start with a gerund")

    def check_description(self, path: Path, desc: str) -> None:
        first = desc.split(" ", 1)[0].strip(",.:;").lower()
        if first in NOT_THIRD_PERSON or not (first.endswith("s") and first.isalpha()):
            self.add("desc-third-person", path, f"description opens with '{first}', not a third-person verb")
        if len(desc) > DESC_MAX:
            self.add("desc-length", path, f"description is {len(desc)} characters, budget {DESC_MAX}")
        head, sep, _ = desc.partition("Use when")
        if not sep:
            self.add("desc-use-when", path, "description has no 'Use when' clause")
        elif len(head.strip()) > CAPABILITY_MAX:
            self.add("desc-capability-length", path,
                     f"capability clause is {len(head.strip())} characters, budget {CAPABILITY_MAX}")

    def manager_budget(self, skill: Path, name: str) -> int:
        """150 for builder skills and skills used only by manager bots, else 120."""
        if self.role:
            return MANAGER_LINES if self.role == "manager" else WORKER_LINES
        container = skill.parent.parent
        if (container / "builder.yaml").is_file():
            return MANAGER_LINES
        manifest = container / "squad.yaml"
        if container.parent.name != "squads" or not manifest.is_file():
            return WORKER_LINES
        try:
            bots = (_yaml().safe_load(manifest.read_text(encoding="utf-8")) or {}).get("bots") or {}
            roles = [b.get("role") for b in bots.values() if name in ((b.get("skills") or {}).get("squad") or [])]
        except Exception:
            return WORKER_LINES
        return MANAGER_LINES if roles and set(roles) == {"manager"} else WORKER_LINES

    def check_size(self, skill: Path, path: Path, text: str, name: str) -> None:
        lines = len(text.splitlines())
        if name == INDEX_SKILL:
            if lines > INDEX_LINES:
                self.add("index-lines", path, f"{lines} lines, budget {INDEX_LINES}")
            return
        budget = self.manager_budget(skill, name)
        if lines > budget:
            self.add("skill-lines", path, f"{lines} lines, budget {budget}")

    def check_sections(self, path: Path, text: str) -> None:
        body = re.sub(r"\A---.*?\n---\s*\n", "", text, count=1, flags=re.S)
        headings = {m.group(1).strip().lower() for m in re.finditer(r"^#{2,6}\s+(.+?)\s*#*\s*$", body, re.M)}
        missing = [s for s in BODY_SECTIONS if s not in headings]
        if missing:
            self.add("body-sections", path, "missing sections: " + ", ".join(missing))

    def check_children(self, skill: Path) -> None:
        for child in sorted(skill.iterdir()):
            if child.name in IGNORED or child.name == "SKILL.md" and child.is_file():
                continue
            if not (child.is_dir() and child.name in ALLOWED_CHILDREN):
                self.add("children-allowed", child, f"'{child.name}' is not an allowed child of a skill dir")
        evals = skill / "evals"
        for child in sorted(evals.iterdir()) if evals.is_dir() else []:
            if child.name not in IGNORED and not (child.is_file() and child.name == "evals.json"):
                self.add("children-allowed", child, "evals/ may only hold evals.json")

    def check_references(self, skill: Path) -> None:
        refs = skill / "references"
        if not refs.is_dir():
            return
        for child in sorted(refs.iterdir()):
            if child.name in IGNORED:
                continue
            if child.is_dir():
                self.add("ref-depth", child, "references must be one level deep")
            elif child.suffix == ".md":
                text = child.read_text(encoding="utf-8")
                lines = text.splitlines()
                if len(lines) > REF_MAX:
                    self.add("ref-lines", child, f"{len(lines)} lines, budget {REF_MAX}")
                has_toc = any(re.match(r"#{1,6}\s*contents\s*$", ln, re.I) for ln in lines[:TOC_WINDOW])
                if len(lines) > REF_TOC_AFTER and not has_toc:
                    self.add("ref-toc", child, f"{len(lines)} lines and no Contents heading in the first {TOC_WINDOW}")

    def check_evals(self, skill: Path) -> None:
        path = skill / "evals" / "evals.json"
        try:
            count = len(json.loads(path.read_text(encoding="utf-8"))["evals"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.add("evals-count", path, f"evals/evals.json missing or unreadable ({type(exc).__name__})")
            return
        if count != EVALS_COUNT:
            self.add("evals-count", path, f"{count} scenarios, expected {EVALS_COUNT}")

    # --- scripts ------------------------------------------------------------------------------------------------------

    @staticmethod
    def script_kind(path: Path) -> str | None:
        if path.suffix == ".py":
            return "py"
        if path.suffix in {".sh", ".bash"}:
            return "sh"
        try:
            shebang = path.open(encoding="utf-8").readline()
        except (OSError, UnicodeDecodeError):
            return None
        if shebang.startswith("#!"):
            return "py" if "python" in shebang else "sh" if re.search(r"\b(ba|z)?sh\b", shebang) else None
        return None

    def run(self, argv: list[str]) -> subprocess.CompletedProcess:
        env = {**os.environ, "HERMES_HOME": self.home, "PYTHONDONTWRITEBYTECODE": "1"}
        return subprocess.run(argv, capture_output=True, text=True, timeout=HELP_TIMEOUT, cwd=self.home, env=env,
                              stdin=subprocess.DEVNULL)

    def check_scripts(self, skill: Path) -> None:
        scripts = skill / "scripts"
        for path in sorted(scripts.rglob("*")) if scripts.is_dir() else []:
            if not path.is_file() or set(path.relative_to(scripts).parts) & IGNORED:
                continue
            kind = self.script_kind(path)
            if kind == "py":
                try:
                    compile(path.read_text(encoding="utf-8"), str(path), "exec")
                except (SyntaxError, ValueError) as exc:
                    self.add("script-py-compile", path, f"does not compile: {exc}")
                    continue
                argv = [sys.executable, "-B", str(path.resolve()), "--help"]
            elif kind == "sh":
                syntax = self.run(["bash", "-n", str(path.resolve())])
                if syntax.returncode:
                    self.add("script-bash-n", path, f"bash -n failed: {syntax.stderr.strip()}")
                    continue
                self.check_shellcheck(path)
                argv = ["bash", str(path.resolve()), "--help"]
            else:
                continue
            if path.name.startswith("_"):
                continue
            try:
                done = self.run(argv)
            except subprocess.TimeoutExpired:
                self.add("script-help", path, f"--help did not exit within {HELP_TIMEOUT}s")
                continue
            if done.returncode:
                self.add("script-help", path, f"--help exited {done.returncode}: {done.stderr.strip()[-200:]}")

    def check_shellcheck(self, path: Path) -> None:
        if not self.shellcheck:
            if self.require_shellcheck:
                self.add("script-shellcheck", path, "shellcheck is not installed")
            else:
                self.skipped.append(f"script-shellcheck: shellcheck not installed, skipped {path}")
            return
        done = self.run([self.shellcheck, "-f", "gcc", str(path.resolve())])
        if done.returncode:
            report = done.stdout.strip() or done.stderr.strip()
            self.add("script-shellcheck", path, "; ".join(ln.split(": ", 1)[-1] for ln in report.splitlines()))


# --- discovery -----------------------------------------------------------------------------------------------------

def discover(root: Path) -> dict[str, list[Path]]:
    found: dict[str, list[Path]] = {"skill": [], "soul": [], "squad": []}
    if root.is_file():
        kind = "soul" if root.suffix == ".md" else "squad" if root.suffix in {".yaml", ".yml"} else None
        if kind:
            found[kind].append(root)
        return found
    if (root / "SKILL.md").is_file():
        found["skill"].append(root)
        return found
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        if "SKILL.md" in filenames:
            found["skill"].append(here)
            dirnames[:] = []
            continue
        for name in sorted(filenames):
            if name == "SOUL.md" or (here.name == "souls" and name.endswith(".md")):
                found["soul"].append(here / name)
            elif name in {"squad.yaml", "builder.yaml"}:
                found["squad"].append(here / name)
    return found


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="skill_lint.py",
        description="Lint skills and SOUL files against the size and format rules (--rules).",
        epilog="Exit 0 clean, 1 findings, 2 usage error.",
    )
    parser.add_argument("paths", nargs="*", type=Path,
                        help="skill dir, SOUL file, squad.yaml, or a tree to scan (default: the repo root)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument("--rules", action="store_true", help="list rule ids and exit")
    parser.add_argument("--roles", type=Path, default=DEFAULT_ROLES, help="model-roles.yaml for model-id detection")
    parser.add_argument("--role", choices=["manager", "worker"], help="force the SKILL.md budget instead of inferring it")
    parser.add_argument("--require-shellcheck", action="store_true", help="fail when shellcheck is not installed")
    parser.add_argument("--no-scripts", action="store_true", help="skip the scripts/ checks (compile, --help, shellcheck)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.rules:
        if args.json:
            print(json.dumps(RULES, indent=2))
        else:
            print("\n".join(f"{rule}: {text}" for rule, text in RULES.items()))
        return 0
    paths = args.paths or [SCRIPTS_DIR.parent]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        print("error: no such path: " + ", ".join(missing), file=sys.stderr)
        return 2
    linter = Linter(args.roles, args.role, args.require_shellcheck, not args.no_scripts)
    try:
        for path in paths:
            found = discover(path)
            for skill in found["skill"]:
                linter.lint_skill(skill)
            for soul in found["soul"]:
                linter.lint_soul(soul)
            for squad in found["squad"]:
                linter.lint_squad_yaml(squad)
    finally:
        shutil.rmtree(linter.home, ignore_errors=True)
    counts: dict[str, int] = {}
    for f in linter.findings:
        counts[f["rule"]] = counts.get(f["rule"], 0) + 1
    report = {"ok": not linter.findings, "targets": linter.targets, "findings": linter.findings,
              "counts": counts, "skipped": linter.skipped}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for f in linter.findings:
            where = f"{f['path']}:{f['line']}" if "line" in f else f["path"]
            print(f"FAIL {f['rule']} {where}: {f['message']}")
        for note in linter.skipped:
            print(f"skip {note}")
        print(f"{'ok' if report['ok'] else 'fail'}: {len(linter.targets)} targets, {len(linter.findings)} findings")
    if not linter.targets:
        print("warning: no skills or SOUL files found", file=sys.stderr)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
