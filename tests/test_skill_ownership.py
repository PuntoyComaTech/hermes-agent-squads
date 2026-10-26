"""Every script a bot's skill tells it to run is installed on that bot.

Each bot gets only the skills its squad.yaml lists. A manager skill once said "run check_profile_copy.py", a script of
the writer's skill; the manager could not find it in its own profile, searched the home folder, and macOS raised a
privacy prompt per private folder. This walks every bot of every squad and every `$HERMES_HOME/skills/squad-<key>/
<skill>/scripts/<tool>` path its skills give it, and fails when <skill> is not one of that bot's skills.
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
RUN_PATH = re.compile(r"\$HERMES_HOME/skills/squad-([a-z0-9-]+)/([a-z0-9-]+)/scripts/([A-Za-z0-9_./-]+)")


def bots():
    for manifest in sorted((ROOT / "squads").glob("*/squad.yaml")):
        squad = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        for name, bot in (squad.get("bots") or {}).items():
            if bot:
                yield manifest.parent, name, ((bot.get("skills") or {}).get("squad") or [])


def where(doc: Path) -> str:
    return str(doc.relative_to(ROOT)) if doc.is_relative_to(ROOT) else doc.name


def foreign_runs(squad_dir: Path, skills: list):
    """(file:line, skill, tool) for every run path in the bot's skills that points at a skill it does not hold."""
    held = set(skills)
    for skill in skills:
        for doc in sorted((squad_dir / "skills" / skill).rglob("*")):
            if doc.suffix not in (".md", ".py", ".json", ".yaml") or not doc.is_file():
                continue
            for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                for key, owner, tool in RUN_PATH.findall(line):
                    if key == squad_dir.name and owner not in held:
                        yield f"{where(doc)}:{number}", owner, tool


@pytest.mark.parametrize("squad_dir, bot, skills", list(bots()), ids=lambda v: v if isinstance(v, str) else None)
def test_every_script_a_bot_is_told_to_run_is_installed_on_that_bot(squad_dir, bot, skills):
    missing = list(foreign_runs(squad_dir, skills))
    assert not missing, f"{bot} is told to run scripts of skills it does not hold: {missing}"


# A script reaching a sibling skill's folder: SKILLS / "<skill>", HERE.parents[1] / "<skill>", parents[2] / "<skill>".
SIBLING = re.compile(r"""(?:\bSKILLS|parents?\[\d\]|\.parent\.parent)\s*\)?\s*/\s*["']([a-z0-9]+(?:-[a-z0-9]+)+)["']""")


def foreign_imports(squad_dir: Path, skills: list):
    """(file:line, skill) for every sibling-skill path a held skill's script reads that the bot does not hold."""
    held = set(skills)
    names = {p.name for p in (squad_dir / "skills").iterdir() if (p / "SKILL.md").is_file()}
    for skill in skills:
        for script in sorted((squad_dir / "skills" / skill).rglob("*.py")):
            for number, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
                for owner in SIBLING.findall(line):
                    if owner in names and owner not in held:
                        yield f"{where(script)}:{number}", owner


@pytest.mark.parametrize("squad_dir, bot, skills", list(bots()), ids=lambda v: v if isinstance(v, str) else None)
def test_every_sibling_skill_a_bots_script_loads_is_installed_on_that_bot(squad_dir, bot, skills):
    missing = list(foreign_imports(squad_dir, skills))
    assert not missing, f"{bot}'s scripts load skills it does not hold: {missing}"


def test_the_import_check_catches_the_applier_gate_reading_score_analysis(tmp_path):
    """The case that stopped every auto-apply: check_submission.py loads analyzing-jobs/scripts/score_analysis.py."""
    squad = tmp_path / "jobs"
    for name in ("submitting-applications", "analyzing-jobs", "jobs-contract"):
        (squad / "skills" / name / "scripts").mkdir(parents=True)
        (squad / "skills" / name / "SKILL.md").write_text("x\n")
    (squad / "skills" / "submitting-applications" / "scripts" / "check_submission.py").write_text(
        'SKILLS = Path(__file__).resolve().parents[2]\n'
        'LINK = SKILLS / "jobs-contract" / "scripts" / "link_check.py"\n'
        'SCORE = SKILLS / "analyzing-jobs" / "scripts" / "score_analysis.py"\n')
    assert [m[1] for m in foreign_imports(squad, ["submitting-applications", "jobs-contract"])] == ["analyzing-jobs"]
    assert list(foreign_imports(squad, ["submitting-applications", "analyzing-jobs", "jobs-contract"])) == []


RUN_VERB = re.compile(r"\b(?:run|rerun|re-run|runs|execute)\b[^.;|]{0,60}?`(?:python3 )?([a-z_][a-z0-9_]+\.(?:py|mjs))",
                      re.IGNORECASE)


def told_to_run_by_name(squad_dir: Path, skills: list):
    """A bare `tool.py` after "run" that only another skill ships: the form check_profile_copy.py once took."""
    held = set(skills)
    owner = {p.name: p.parents[1].name for p in (squad_dir / "skills").glob("*/scripts/*") if p.is_file()}
    shared = {p.name for p in (squad_dir / "scripts").glob("*")}
    for skill in skills:
        for doc in sorted((squad_dir / "skills" / skill).rglob("*.md")):
            for number, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
                for tool in RUN_VERB.findall(line):
                    if tool in owner and owner[tool] not in held and tool not in shared:
                        yield f"{where(doc)}:{number}", owner[tool], tool


@pytest.mark.parametrize("squad_dir, bot, skills", list(bots()), ids=lambda v: v if isinstance(v, str) else None)
def test_no_bot_is_told_to_run_another_bots_script_by_name(squad_dir, bot, skills):
    missing = list(told_to_run_by_name(squad_dir, skills))
    assert not missing, f"{bot} is told to run scripts it does not hold: {missing}"


@pytest.mark.parametrize("squad_dir, bot, skills", list(bots()), ids=lambda v: v if isinstance(v, str) else None)
def test_every_squad_skill_a_bot_lists_exists(squad_dir, bot, skills):
    assert [s for s in skills if not (squad_dir / "skills" / s / "SKILL.md").is_file()] == []


def test_the_check_catches_the_manager_running_the_writers_script(tmp_path):
    """The case that reached the home folder: a manager skill naming the writer's check script."""
    squad = tmp_path / "jobs"
    (squad / "skills" / "leading-job-search").mkdir(parents=True)
    (squad / "skills" / "leading-job-search" / "SKILL.md").write_text(
        'Run `python3 "$HERMES_HOME/skills/squad-jobs/optimizing-profiles/scripts/check_profile_copy.py"`.\n')
    assert [m[1:] for m in foreign_runs(squad, ["leading-job-search"])] == [("optimizing-profiles",
                                                                             "check_profile_copy.py")]
    assert list(foreign_runs(squad, ["leading-job-search", "optimizing-profiles"])) == []
    (squad / "skills" / "optimizing-profiles" / "scripts").mkdir(parents=True)
    (squad / "skills" / "optimizing-profiles" / "scripts" / "check_profile_copy.py").write_text("")
    (squad / "skills" / "leading-job-search" / "SKILL.md").write_text("Then rerun `check_profile_copy.py` on it.\n")
    assert [m[1:] for m in told_to_run_by_name(squad, ["leading-job-search"])] == [("optimizing-profiles",
                                                                                   "check_profile_copy.py")]
