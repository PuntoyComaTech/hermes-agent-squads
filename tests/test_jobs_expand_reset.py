"""Expansion and reset of a job-search project: real runs of expand_candidates.py and reset_project.py.

Every test builds a fictional project (Ana Example, Lima) under pytest's tmp_path, runs the scripts as subprocesses and
checks the files on disk. Nothing touches the network or the real home folder: HOME is pointed at a temporary folder
whenever a symbolic link could reach the home folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "squads" / "jobs" / "skills"
CONTRACT = SKILLS / "jobs-contract" / "scripts"
EXPAND = CONTRACT / "expand_candidates.py"
RESET = CONTRACT / "reset_project.py"
PROFILE_SKILL = SKILLS / "profiling-candidates"
FINDING = SKILLS / "finding-jobs" / "SKILL.md"
LEADING = SKILLS / "leading-job-search" / "SKILL.md"
CONTRACT_SKILL = SKILLS / "jobs-contract" / "SKILL.md"

PROFILE_FILES = ["profile.md", "achievements.yaml", "contact.yaml", "application-data.yaml", "calibration.md"]
GITKEEPS = {f"documents/{sub}/.gitkeep" for sub in ("cv", "linkedin", "diplomas", "references", "projects")}
SALES_SUMMARY = ("Loads CSV sales files, cleans them with pandas and stores them in SQLite; the weekly report "
                 "reads it with SQL. An Airflow DAG schedules the run.")

ACHIEVEMENTS = """\
experiences:
  - {id: EXP-001, title: "Data analyst", company: "Example Co", from: 2022-03, to: current}
achievements:
  - id: ACH-007
    experience: EXP-001
    proficiency: did
    en: "Automated the weekly sales report with Python."
    source: "documents/cv/cv-2026.txt"
    verified: true
skills:
  - {name: Python, proficiency: did, years: 4, achievements: [ACH-007]}
  - {name: SQL, proficiency: did, years: 3, achievements: [ACH-007]}
certifications:
  - {id: CERT-001, name: "Data Analysis Certificate", issuer: "Example Academy", year: 2024, verified: true}
languages:
  - {language: spanish, level: C2, verified: true}
"""

PROFILE = """\
---
updated: 2026-10-01
search: active
occupation: "Data analyst, business reporting and automation"
target_roles: ["Data analyst"]
seniority: mid-level
years_experience: {total: 4, in_role: 3}
work_mode: [hybrid]
search_keywords: {en: ["data analyst"]}
---
Fictional candidate: Ana Example.
"""

CV = """\
Ana Example, Data analyst at Example Co (2022-2025).
Built pandas workflows that replaced a manual report. Reports in Power BI.
Languages: Spanish (native), English (B2).
Certificate: Data Analysis Certificate
"""


def run(script: Path, *args, home: Path | None = None):
    env = os.environ.copy()
    if home is not None:
        env["HOME"] = str(home)
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, env=env)


def walk(root: Path) -> tuple:
    """(files, links, dirs) under root as relative posix paths. Symbolic links are listed, never followed."""
    files, links, dirs = set(), set(), set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        for name in dirnames:
            rel = (here / name).relative_to(root).as_posix()
            (links if (here / name).is_symlink() else dirs).add(rel)
        for name in filenames:
            rel = (here / name).relative_to(root).as_posix()
            (links if (here / name).is_symlink() else files).add(rel)
    return files, links, dirs


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "ana-example-search"
    write(root / "profile.md", PROFILE)
    write(root / "achievements.yaml", ACHIEVEMENTS)
    write(root / "contact.yaml", 'name: "Ana Example"\nemail: "ana@example.com"\n')
    write(root / "application-data.yaml", 'start_availability: "2 weeks"\n')
    write(root / "calibration.md", "Not enough resolved applications yet.\n")
    write(root / "documents" / "README.md", "Drop your files here.\n")
    for sub in ("cv", "linkedin", "diplomas", "references", "projects"):
        write(root / "documents" / sub / ".gitkeep", "")
    write(root / "documents" / "cv" / "cv-2026.txt", CV)
    write(root / "documents" / "cv" / "Data-Analysis-Certificate.pdf", "%PDF-1.4 fictional\n")
    write(root / "documents" / "projects" / "Google-Cloud-Certificate.pdf", "%PDF-1.4 fictional\n")
    write(root / "documents" / "projects" / "Power-BI-Fundamentals.pdf", "%PDF-1.4 fictional\n")
    write(root / "openings" / "JOB-20261001-acme-data-analyst" / "status.json", '{"history": []}\n')
    write(root / "openings" / "JOB-20261001-acme-data-analyst" / "opening.md", "---\nid: JOB-20261001\n---\n")
    write(root / "tracker.csv", "date,id,company\n2026-10-01,JOB-20261001,Acme\n")
    write(root / "searches" / "seen.json", '{"schema": 1, "seen": {}}\n')
    write(root / "reports" / "upskill-2026-10-20.md", "Skill gaps.\n")
    return root


@pytest.fixture
def evidence(tmp_path):
    data = {"sources": [
        {"url": "https://github.com/ana-example/sales-etl", "title": "sales-etl", "fetched": True,
         "technologies": ["Python", "pandas", "SQLite"], "project_summary": SALES_SUMMARY},
        {"url": "https://github.com/ana-example/empty-copy", "title": "empty-copy", "fetched": True,
         "technologies": [], "project_summary": ""},
        {"url": "https://github.com/ana-example/offline", "title": "offline", "fetched": False,
         "technologies": ["Kubernetes"], "project_summary": ""},
    ]}
    return write(tmp_path / "evidence.json", json.dumps(data))


def expand_json(project, evidence, *extra):
    proc = run(EXPAND, "--project", str(project), "--evidence", str(evidence), *extra)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def trash_dirs(project):
    base = project / ".trash"
    return sorted(base.iterdir()) if base.is_dir() else []


# --- expand_candidates: the scenario ------------------------------------------------------------------------------

def test_expansion_proposes_pandas_and_the_etl_project_once(project, evidence):
    out = expand_json(project, evidence)
    skills = {s["name"]: s for s in out["candidates"]["skills"]}
    assert list(skills).count("pandas") == 1
    assert skills["pandas"]["tag"] == "stated"
    assert set(skills["pandas"]["sources"]) == {"https://github.com/ana-example/sales-etl",
                                                 "documents/cv/cv-2026.txt"}
    projects = out["candidates"]["projects"]
    assert [p["name"] for p in projects] == ["sales-etl"]
    assert projects[0]["url"] == "https://github.com/ana-example/sales-etl"
    assert projects[0]["summary"] == SALES_SUMMARY


def test_expansion_skips_the_skills_achievements_already_declares(project, evidence):
    out = expand_json(project, evidence)
    names = {s["name"] for s in out["candidates"]["skills"]}
    assert "Python" not in names and "SQL" not in names
    skipped = {s["name"] for s in out["skipped"] if s["kind"] == "skill"}
    assert {"Python", "SQL"} <= skipped


def test_expansion_skips_a_declared_certificate(project, evidence):
    out = expand_json(project, evidence)
    certs = [c["name"] for c in out["candidates"]["certifications"]]
    assert "Data Analysis Certificate" not in certs
    assert any(s["kind"] == "certification" and s["name"] == "Data Analysis Certificate" for s in out["skipped"])


def test_expansion_skips_the_empty_copy_and_the_unfetched_source(project, evidence):
    out = expand_json(project, evidence)
    reasons = {s["name"]: s["reason"] for s in out["skipped"] if s["kind"] == "source"}
    assert reasons["https://github.com/ana-example/empty-copy"].startswith("empty stub")
    assert reasons["https://github.com/ana-example/offline"] == "not fetched"
    assert "Kubernetes" not in json.dumps(out["candidates"])
    assert all(p["url"] != "https://github.com/ana-example/empty-copy" for p in out["candidates"]["projects"])


def test_expansion_tags_stated_and_inferred(project, evidence):
    out = expand_json(project, evidence)
    skills = {s["name"]: s for s in out["candidates"]["skills"]}
    assert skills["SQLite"]["tag"] == "stated"
    assert skills["Power BI"]["tag"] == "stated"
    assert skills["Apache Airflow"]["tag"] == "inferred"


def test_expansion_lists_a_certificate_file_as_an_inferred_candidate(project, evidence):
    out = expand_json(project, evidence)
    certs = {c["name"]: c for c in out["candidates"]["certifications"]}
    assert set(certs) == {"Google Cloud Certificate"}
    assert certs["Google Cloud Certificate"]["tag"] == "inferred"
    assert certs["Google Cloud Certificate"]["sources"] == ["documents/projects/Google-Cloud-Certificate.pdf"]
    assert "Power BI Fundamentals" not in json.dumps(out["candidates"]), "a plain PDF is not a certificate"


def test_expansion_groups_each_candidate_once_under_its_first_source(project, evidence):
    out = expand_json(project, evidence)
    grouped = [(g["source"], item["name"]) for g in out["groups"] for item in g["items"]]
    assert len(grouped) == len(set(grouped))
    assert out["groups"][0]["source"] == "https://github.com/ana-example/sales-etl"
    assert ("https://github.com/ana-example/sales-etl", "pandas") in grouped
    assert ("documents/cv/cv-2026.txt", "Power BI") in grouped


def test_expansion_is_read_only_and_repeatable(project, evidence):
    before_files = {p: sha(project / p) for p in PROFILE_FILES}
    before_tree = walk(project)
    first = expand_json(project, evidence)
    second = expand_json(project, evidence)
    assert first == second
    assert {p: sha(project / p) for p in PROFILE_FILES} == before_files
    assert walk(project) == before_tree


def test_expansion_refuses_an_evidence_file_without_sources(project, tmp_path):
    bad = write(tmp_path / "bad.json", '{"not": "sources"}')
    proc = run(EXPAND, "--project", str(project), "--evidence", str(bad))
    assert proc.returncode == 1 and "sources" in proc.stderr


def test_expansion_reads_pasted_text_without_evidence(project, tmp_path):
    pasted = write(tmp_path / "pasted.txt", "Used Docker and pandas daily.\n")
    proc = run(EXPAND, "--project", str(project), "--text", str(pasted))
    assert proc.returncode == 0, proc.stderr
    skills = {s["name"] for s in json.loads(proc.stdout)["candidates"]["skills"]}
    assert {"Docker", "pandas"} <= skills


def test_expansion_never_follows_a_symlink_into_another_folder(project, evidence, tmp_path):
    outside = write(tmp_path / "outside" / "notes.txt", "Kubernetes and Terraform in every project.\n")
    os.symlink(outside.parent, project / "documents" / "cv" / "shared-link")
    out = expand_json(project, evidence)
    assert "Kubernetes" not in json.dumps(out["candidates"])
    link = next(d for d in out["documents"] if d["path"] == "documents/cv/shared-link")
    assert link["kind"] == "link" and link["readable"] is False and "not followed" in link["note"]


def test_expansion_help_exits_zero():
    assert run(EXPAND, "--help").returncode == 0


# --- reset_project: preview, confirm, scopes ----------------------------------------------------------------------

def test_reset_preview_without_confirm_deletes_nothing(project):
    before = walk(project)
    proc = run(RESET, "--project", str(project), "--scope", "profile")
    assert proc.returncode == 0, proc.stderr
    assert "profile.md" in proc.stdout and "achievements.yaml" in proc.stdout and " bytes" in proc.stdout
    assert "--confirm RESET" in proc.stdout
    assert walk(project) == before and trash_dirs(project) == []


def test_reset_preview_json_lists_the_plan_and_keeps_the_scaffold(project):
    proc = run(RESET, "--project", str(project), "--scope", "documents", "--json")
    plan = json.loads(proc.stdout)
    assert plan["executed"] is False and plan["trash"] is None
    paths = {e["path"] for e in plan["entries"]}
    assert "documents/cv/cv-2026.txt" in paths
    assert not (paths & (GITKEEPS | {"documents/README.md"}))
    assert set(plan["kept"]) == GITKEEPS | {"documents/README.md"}
    assert (project / "documents" / "cv" / "cv-2026.txt").is_file()


def test_reset_profile_moves_exactly_the_profile_files_and_the_search_keeps_openings(project):
    before = walk(project)
    proc = run(RESET, "--project", str(project), "--scope", "profile", "--confirm", "RESET")
    assert proc.returncode == 0, proc.stderr
    assert {p for p in os.listdir(project) if (project / p).is_file()} == {"tracker.csv"}
    (trash,) = trash_dirs(project)
    assert sorted(os.listdir(trash)) == sorted(PROFILE_FILES + ["RESET-MANIFEST.json"])
    manifest = json.loads((trash / "RESET-MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["complete"] is True and manifest["scope"] == "profile"
    assert sorted(e["path"] for e in manifest["entries"]) == sorted(PROFILE_FILES)
    after = walk(project)
    assert {p for p in after[0] if p.startswith(("openings", "documents"))} == \
        {p for p in before[0] if p.startswith(("openings", "documents"))}
    assert (project / "openings" / "JOB-20261001-acme-data-analyst" / "status.json").is_file()


def test_reset_profile_then_documents_still_works_without_a_profile(project):
    assert run(RESET, "--project", str(project), "--scope", "profile", "--confirm", "RESET").returncode == 0
    proc = run(RESET, "--project", str(project), "--scope", "documents")
    assert proc.returncode == 0, proc.stderr
    assert "documents/cv/cv-2026.txt" in proc.stdout


def test_reset_documents_keeps_readme_gitkeep_folders_and_openings(project):
    proc = run(RESET, "--project", str(project), "--scope", "documents", "--confirm", "RESET")
    assert proc.returncode == 0, proc.stderr
    docs = project / "documents"
    assert (docs / "README.md").is_file()
    for sub in ("cv", "linkedin", "diplomas", "references", "projects"):
        assert (docs / sub / ".gitkeep").is_file()
    assert not (docs / "cv" / "cv-2026.txt").exists()
    assert not (docs / "projects" / "Power-BI-Fundamentals.pdf").exists()
    assert (project / "profile.md").is_file() and (project / "achievements.yaml").is_file()
    assert (project / "openings" / "JOB-20261001-acme-data-analyst" / "status.json").is_file()
    (trash,) = trash_dirs(project)
    assert (trash / "documents" / "cv" / "cv-2026.txt").is_file()


def test_reset_all_moves_everything_except_the_scaffold_and_trash(project):
    files_before, _links, _dirs = walk(project)
    proc = run(RESET, "--project", str(project), "--scope", "all", "--confirm", "RESET")
    assert proc.returncode == 0, proc.stderr
    (trash,) = trash_dirs(project)
    trashed, _tl, _td = walk(trash)
    trashed.discard("RESET-MANIFEST.json")
    assert trashed == files_before - GITKEEPS - {"documents/README.md"}
    files_after, _l, dirs_after = walk(project)
    files_after = {p for p in files_after if not p.startswith(".trash/")}
    assert files_after == GITKEEPS | {"documents/README.md"}
    assert {"openings", "searches", "reports"} <= dirs_after, "top-level folders stay, empty"
    assert not any(p.startswith("openings/") for p in dirs_after), "emptied subfolders are pruned"
    assert json.loads((trash / "RESET-MANIFEST.json").read_text(encoding="utf-8"))["complete"] is True


def test_reset_all_after_documents_gets_a_second_trash_folder(project):
    assert run(RESET, "--project", str(project), "--scope", "documents", "--confirm", "RESET").returncode == 0
    assert run(RESET, "--project", str(project), "--scope", "all", "--confirm", "RESET").returncode == 0
    assert len(trash_dirs(project)) == 2


@pytest.mark.parametrize("value", ["reset", "yes", "RESET ", ""])
def test_reset_refuses_any_confirm_value_but_RESET(project, value):
    before = walk(project)
    proc = run(RESET, "--project", str(project), "--scope", "all", "--confirm", value)
    assert proc.returncode == 2
    assert walk(project) == before and trash_dirs(project) == []


def test_reset_needs_a_scope(project):
    assert run(RESET, "--project", str(project)).returncode == 2


def test_reset_refuses_a_folder_without_profile_that_holds_foreign_entries(tmp_path):
    folder = tmp_path / "not-a-project"
    write(folder / "vacation-photos" / "a.jpg", "x")
    proc = run(RESET, "--project", str(folder), "--scope", "all", "--confirm", "RESET")
    assert proc.returncode == 1 and "pass the project folder" in proc.stderr
    assert (folder / "vacation-photos" / "a.jpg").is_file() and not (folder / ".trash").exists()


def test_reset_refuses_the_home_folder(tmp_path):
    home = tmp_path / "home"
    write(home / "profile.md", "---\nsearch: active\n---\n")
    proc = run(RESET, "--project", str(home), "--scope", "all", "--confirm", "RESET", home=home)
    assert proc.returncode == 1 and "home folder" in proc.stderr
    assert (home / "profile.md").is_file()


def test_reset_moves_a_link_to_home_as_a_link_and_never_follows_it(project, tmp_path):
    home = tmp_path / "home"
    write(home / "private" / "tax-return.txt", "not for any search\n")
    os.symlink(home, project / "documents" / "cv" / "home-link")
    preview = run(RESET, "--project", str(project), "--scope", "documents", home=home)
    assert preview.returncode == 0, preview.stderr
    assert "documents/cv/home-link" in preview.stdout and "not followed" in preview.stdout
    assert "tax-return" not in preview.stdout
    proc = run(RESET, "--project", str(project), "--scope", "documents", "--confirm", "RESET", home=home)
    assert proc.returncode == 0, proc.stderr
    assert (home / "private" / "tax-return.txt").read_text(encoding="utf-8") == "not for any search\n"
    assert not os.path.lexists(project / "documents" / "cv" / "home-link")
    (trash,) = trash_dirs(project)
    assert os.path.islink(trash / "documents" / "cv" / "home-link")
    assert os.readlink(trash / "documents" / "cv" / "home-link") == str(home)


def test_reset_refuses_a_documents_folder_that_is_itself_a_link(project, tmp_path):
    elsewhere = write(tmp_path / "elsewhere" / "cv.txt", "keep me\n")
    shutil.rmtree(project / "documents")
    os.symlink(elsewhere.parent, project / "documents")
    before = walk(project)
    proc = run(RESET, "--project", str(project), "--scope", "documents", "--confirm", "RESET")
    assert proc.returncode == 1 and "symbolic link" in proc.stderr
    assert walk(project) == before and elsewhere.is_file()


def test_reset_help_exits_zero():
    assert run(RESET, "--help").returncode == 0


# --- skill text: the modes and rules the manager follows ----------------------------------------------------------

def test_profiling_candidates_declares_both_modes_within_budget():
    text = (PROFILE_SKILL / "SKILL.md").read_text(encoding="utf-8")
    assert "Mode: EXPAND" in text and "Mode: RESET" in text
    assert len(text.splitlines()) <= 150
    assert "references/expansion.md" in text
    assert "reset_project.py" in text and "--confirm RESET" in text


def test_expansion_reference_stays_within_budget_and_states_the_rules():
    ref = PROFILE_SKILL / "references" / "expansion.md"
    lines = ref.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 200
    text = "\n".join(lines)
    for phrase in ("expand_candidates.py", "inferred", "stated", "verified: false", "evidence-YYYY-MM-DD.json",
                   "support card", "jobs-scout", "nothing is written", "source:"):
        assert phrase in text, phrase


def test_finding_jobs_has_the_evidence_mode_within_its_budget():
    text = FINDING.read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 120
    assert "Mode: EVIDENCE" in text and "evidence-YYYY-MM-DD.json" in text
    assert "public_evidence" in text


def test_leading_job_search_has_one_route_line_per_new_mode():
    rows = [ln for ln in LEADING.read_text(encoding="utf-8").splitlines() if ln.startswith("   | ")]
    expand = [r for r in rows if "not declared" in r]
    reset = [r for r in rows if "reset" in r.lower()]
    assert len(expand) == 1 and "Mode: EXPAND" in expand[0]
    assert len(reset) == 1 and "Mode: RESET" in reset[0]


def test_jobs_contract_names_both_tools_and_the_evidence_file():
    text = CONTRACT_SKILL.read_text(encoding="utf-8")
    assert "expand_candidates.py" in text and "reset_project.py" in text
    assert "evidence-YYYY-MM-DD.json" in text


def test_new_files_use_no_slash_commands():
    slash = re.compile(r"(?<![\w/])/(expand|reset)\b")
    new = [CONTRACT / "expand_candidates.py", CONTRACT / "reset_project.py",
           PROFILE_SKILL / "references" / "expansion.md", PROFILE_SKILL / "SKILL.md", FINDING, LEADING]
    for path in new:
        assert not slash.search(path.read_text(encoding="utf-8")), path.name
