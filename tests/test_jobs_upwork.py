"""Upwork is written by the user, never by a bot: its terms ban scripts acting on an account. The writer drafts within
Upwork's own limits and judges the result from the page text the user copies back (paste-kit mode). Fictional data.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "squads" / "jobs" / "skills" / "optimizing-profiles" / "scripts"
COPY, DIFF = SCRIPTS / "check_profile_copy.py", SCRIPTS / "profile_diff.py"
SKILLS = ["SQL", "Python", "Power BI", "Excel"]


def run(script, *args):
    return subprocess.run([sys.executable, "-B", str(script), *map(str, args)], capture_output=True, text=True,
                          timeout=60)


def write(path: Path, data) -> Path:
    path.write_text(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def project(tmp_path) -> Path:
    folder = tmp_path / "ana"
    folder.mkdir()
    (folder / "profile.md").write_text("---\nkey_skills: [SQL, Python, Power BI, Excel]\n"
                                       "target_roles: [\"Data analyst\"]\napplication_languages: [en]\n---\n")
    (folder / "achievements.yaml").write_text(
        "achievements:\n"
        "  - {id: ACH-001, en: \"Automated the weekly sales report with Python and Power BI.\", verified: true}\n"
        "skills:\n  - {name: SQL, achievements: [ACH-001]}\n  - {name: Python, achievements: [ACH-001]}\n")
    return folder


def upwork_copy(title="Data Analyst | SQL, Python, Power BI Dashboards", portfolio="Weekly sales report in Power BI."):
    return {"platform": "upwork", "language": "en", "skills": list(SKILLS),
            "blocks": [{"section": "headline", "text": title, "achievements": ["ACH-001"]},
                       {"section": "about", "text": "I turn weekly sales data into Python and Power BI reports.",
                        "achievements": ["ACH-001"]},
                       {"section": "portfolio", "label": "Sales report", "text": portfolio,
                        "achievements": ["ACH-001"]}]}


def defects(tmp_path, copy):
    folder = tmp_path / "ana" if (tmp_path / "ana").exists() else project(tmp_path)
    p = run(COPY, write(tmp_path / "copy.json", copy), "--project", folder, "--json")
    assert p.returncode in (0, 1), p.stderr
    return p.returncode, [(d["defect"], d["where"]) for d in json.loads(p.stdout)["defects"]]


def test_upwork_limits_are_built_in_without_a_platforms_file(tmp_path):
    assert defects(tmp_path, upwork_copy()) == (0, [])
    code, found = defects(tmp_path, upwork_copy(title="Data Analyst | " + "SQL, Python, Power BI " * 3))
    assert code == 1 and ("over_limit", "headline") in found, found
    code, found = defects(tmp_path, upwork_copy(portfolio="Weekly sales report in Power BI. " * 20))
    assert code == 1 and ("over_limit", "Sales report") in found, found
    many = upwork_copy()
    many["skills"] = SKILLS + [f"Skill {i}" for i in range(17)]
    assert ("skills_over_limit", "skills") in defects(tmp_path, many)[1]


TITLE = "Data Analyst | SQL, Python, Power BI Dashboards"
OVERVIEW = ("I turn weekly sales data into Python and Power BI reports that a store manager reads in one minute.\n\n"
            "Every report is rebuilt automatically each Monday, with the SQL views kept in sync.")
APPROVED = {"fields": [{"field": "headline", "after": TITLE}, {"field": "about", "after": OVERVIEW},
                       {"field": "skills", "after": SKILLS}]}


def verify(tmp_path, page):
    p = run(DIFF, "verify-paste", write(tmp_path / "approved.json", APPROVED), write(tmp_path / "page.txt", page),
            "--json")
    assert p.returncode in (0, 1), p.stderr
    return p.returncode, {f["field"]: f["reason"] for f in json.loads(p.stdout)["failures"]}


def test_verify_paste_passes_the_page_the_user_copied_after_pasting(tmp_path):
    page = (f"Ana Example\nBogota, Colombia\n{TITLE}\n$40.00/hr\n{OVERVIEW.replace(chr(10) * 2, chr(10))}\n"
            "Skills\nsql\nPython\nPower BI\nExcel\nPortfolio\n")
    assert verify(tmp_path, page) == (0, {})


def test_verify_paste_reports_a_cut_overview_a_missing_skill_and_an_old_title(tmp_path):
    page = (f"Ana Example\nData Analyst\n{OVERVIEW[:150]}... more\nSkills\nSQL\nPython\nExcel\n")
    code, failures = verify(tmp_path, page)
    assert code == 1
    assert set(failures) == {"headline", "about", "skills"}, failures
    assert failures["about"].startswith("cut") and "Power BI" in failures["skills"]
