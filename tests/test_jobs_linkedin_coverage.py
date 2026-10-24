"""A LinkedIn optimisation covers the whole profile, in every language the profile has.

The real run that prompted these tests drafted 6 roles from achievements.yaml, but only 3 of them had the same title
on LinkedIn: the other 3 never paired, so 3 roles on the page kept no description. Education got no copy at all, the
skills under each role were never touched, and the profile's two languages were verified against a single capture of
a page that mixes them field by field, so `verify` reported 4 of 12 and the run called it noise. Each test below
replays one of those failures with fictitious data (Ana Example).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "squads" / "jobs" / "skills" / "optimizing-profiles" / "scripts"
COPY, PARSE, DIFF = SCRIPTS / "check_profile_copy.py", SCRIPTS / "parse_profile.py", SCRIPTS / "profile_diff.py"


def run(script, *args):
    return subprocess.run([sys.executable, "-B", str(script), *map(str, args)], capture_output=True, text=True,
                          timeout=60)


def write(path: Path, data) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def project(tmp_path) -> Path:
    folder = tmp_path / "ana"
    folder.mkdir()
    (folder / "profile.md").write_text("---\nkey_skills: [SQL, Python, Power BI, Excel]\n"
                                       "target_roles: [\"Data analyst\"]\napplication_languages: [es, en]\n---\n")
    (folder / "achievements.yaml").write_text(
        "achievements:\n"
        "  - {id: ACH-001, en: \"Automated the weekly sales report with Python and Power BI.\", verified: true}\n"
        "  - {id: ACH-002, en: \"Kept the store's SQL inventory views in sync.\", verified: true}\n"
        "  - {id: ACH-003, en: \"Cleaned supplier data in Excel.\", verified: true}\n"
        "education:\n"
        "  - {id: EDU-001, degree: \"Data analytics bootcamp\", institution: \"Example Institute\", year: 2021,"
        " verified: true}\n"
        "  - {id: EDU-002, degree: \"Courses, Statistics\", institution: \"Sample University\", year: 2019,"
        " verified: true}\n"
        "skills:\n  - {name: SQL, achievements: [ACH-002]}\n  - {name: Python, achievements: [ACH-001]}\n")
    return folder


# The profile as LinkedIn holds it: the newest role matches achievements.yaml, the older employer split one job into
# two titles, and two schools.
CURRENT = {
    "platform": "linkedin", "profile_languages": ["es", "en"], "primary_language": "es", "language": "es",
    "headline": "Analista", "about": "Hola", "skills": ["SQL", "Python", "Excel"], "top_skills": ["Excel"],
    "experience": [
        {"company": "Northwind", "title": "Data Analyst", "description": "", "skills": []},
        {"company": "Contoso", "title": "Junior Analyst", "description": "", "skills": ["Excel"]},
        {"company": "Contoso", "title": "Analyst Trainee", "description": "", "skills": []}],
    "education": [{"institution": "Example Institute", "degree": "Bootcamp", "description": ""},
                  {"institution": "Sample University", "degree": "Courses", "description": "C++"}],
}


def block(section, text, ach, **extra):
    return {"section": section, "text": text, "achievements": ach, **extra}


def full_copy(language="es"):
    return {"platform": "linkedin", "language": language, "skills": ["SQL", "Python", "Power BI", "Excel"],
            "top_skills": ["SQL", "Python", "Power BI"],
            "blocks": [
                block("headline", "Data analyst | SQL, Python, Power BI", ["ACH-001"]),
                block("about", "Turn weekly sales data into reports with Python and Power BI.", ["ACH-001"]),
                block("experience", "• Automated the weekly sales report with Python and Power BI.", ["ACH-001"],
                      company="Northwind", title="Data Analyst", role_skills=["Python", "Power BI"]),
                block("experience", "• Kept the store's SQL inventory views in sync.", ["ACH-002"],
                      company="Contoso", title="Junior Analyst", role_skills=["SQL"]),
                block("experience", "• Cleaned supplier data in Excel.", ["ACH-003"],
                      company="Contoso", title="Analyst Trainee", role_skills=["Excel"]),
                block("education", "Full-stack data analytics: SQL, Python and dashboards.", ["EDU-001"],
                      institution="Example Institute"),
                block("education", "Statistics and programming courses.", ["EDU-002"],
                      institution="Sample University")]}


def check(tmp_path, copy, current=CURRENT):
    folder = tmp_path / "ana" if (tmp_path / "ana").exists() else project(tmp_path)
    args = [write(tmp_path / "copy.json", copy), "--project", folder, "--json",
            "--current", write(tmp_path / "current.json", current)]
    p = run(COPY, *args)
    assert p.returncode in (0, 1), p.stderr
    return p.returncode, json.loads(p.stdout)


def test_a_copy_that_skips_the_roles_whose_title_differs_and_the_education_is_refused(tmp_path):
    copy = full_copy()
    # the real draft: one block for the merged older job under its achievements.yaml title, no education at all
    copy["blocks"] = [b for b in copy["blocks"] if b["section"] != "education" and b.get("company") != "Contoso"]
    copy["blocks"].append(block("experience", "• Cleaned supplier data in Excel.", ["ACH-003"],
                                company="Contoso", title="Analyst"))
    code, report = check(tmp_path, copy)
    found = sorted((d["defect"], d["where"]) for d in report["defects"])
    assert code == 1 and found == [
        ("education_not_covered", "Example Institute"), ("education_not_covered", "Sample University"),
        ("role_not_covered", "Analyst Trainee at Contoso"), ("role_not_covered", "Junior Analyst at Contoso"),
        ("unknown_role", "analyst at contoso")], found


def test_a_copy_that_covers_every_role_and_school_passes(tmp_path):
    code, report = check(tmp_path, full_copy())
    assert code == 0, report


def test_a_copy_in_a_language_the_profile_does_not_have_is_refused(tmp_path):
    code, report = check(tmp_path, full_copy("pt"))
    assert code == 1 and [d["defect"] for d in report["defects"]] == ["wrong_language"]
    assert check(tmp_path, full_copy("en"))[0] == 0


def test_role_skills_and_top_skills_are_held_to_what_the_user_has_and_what_linkedin_allows(tmp_path):
    copy = full_copy()
    copy["blocks"][2]["role_skills"] = ["Python", "Power BI", "SQL", "Excel", "Python", "Tableau"]
    copy["top_skills"] = ["SQL", "Excel", "Python", "Power BI", "Excel", "Looker"]
    code, report = check(tmp_path, copy)
    codes = sorted(d["defect"] for d in report["defects"])
    assert code == 1 and codes == ["skills_over_limit", "skills_over_limit", "top_skill_not_listed",
                                   "unsupported_skill"], codes


def capture(**extra):
    base = {"url": "https://www.linkedin.com/in/ana-example/", "name": "Ana Example", "headline": "Data analyst",
            "about": "I build reports.\n\nTop skills\n\nSQL • Python • Excel",
            "experience": {"found": True, "groups": [{"company": "Northwind", "all": ["Northwind"], "roles": [
                ["Data Analyst", "Jan 2024 - Present · 10 mos",
                 "• Automated the weekly sales report with Python and Power BI.", "• Kept SQL views in sync."]]}]},
            "education": {"found": True, "items": [["Example Institute", "Bootcamp", "2021"]]},
            "skills": {"count": 3, "items": ["SQL", "Python", "Excel"]},
            "profile_languages": ["Español", "English"]}
    base.update(extra)
    return base


def parse(tmp_path, data):
    out = tmp_path / "current.json"
    p = run(PARSE, write(tmp_path / "capture.json", data), "--output", out, "--today", "2026-10-24")
    assert p.returncode == 0, p.stderr
    return json.loads(out.read_text())


def test_the_top_skills_line_is_not_about_text_and_a_role_without_a_place_keeps_its_first_bullet(tmp_path):
    current = parse(tmp_path, capture())
    assert current["about"] == "I build reports."
    assert current["top_skills"] == ["SQL", "Python", "Excel"]
    role = current["experience"][0]
    assert role["location"] == "" and role["description"].startswith("• Automated the weekly sales report")
    assert current["profile_languages"] == ["es", "en"] and current["language"] == "es"
    assert "profile_languages" not in current["missing"]


def test_a_capture_without_the_profile_language_card_says_so(tmp_path):
    data = capture()
    del data["profile_languages"]
    assert "profile_languages" in parse(tmp_path, data)["missing"]


def test_verify_reads_each_language_from_its_own_capture_and_skills_as_a_set(tmp_path):
    es = dict(CURRENT, headline="Analista de datos", about="Hola", language="es",
              skills=["excel", "Python", "SQL"])
    en = dict(CURRENT, headline="Data analyst", about="Hi", language="en")
    approved = write(tmp_path / "approved.json", {"fields": [
        {"field": "headline", "language": "es", "after": "Analista de datos"},
        {"field": "headline", "language": "en", "after": "Data analyst"},
        {"field": "skills", "language": "es", "after": ["SQL", "Python", "Excel"]}]})
    p = run(DIFF, "verify", approved, write(tmp_path / "es.json", es), write(tmp_path / "en.json", en), "--json")
    assert p.returncode == 0, p.stdout
    # with only the Spanish capture, the English row cannot be proven: it fails instead of being compared to Spanish
    p = run(DIFF, "verify", approved, tmp_path / "es.json", "--json")
    failed = json.loads(p.stdout)["failures"]
    assert p.returncode == 1 and [(f["field"], f["language"]) for f in failed] == [("headline", "en")]
    assert "no capture in en" in failed[0]["reason"]


def test_the_diff_offers_education_and_role_skills_and_ignores_skill_order(tmp_path):
    draft = full_copy()
    draft["skills"] = ["Excel", "sql", "Python"]
    draft["blocks"][3]["role_skills"] = ["excel"]  # LinkedIn keeps its own casing for a skill already there
    p = run(DIFF, "diff", write(tmp_path / "current.json", CURRENT), write(tmp_path / "draft.json", draft), "--json")
    data = json.loads(p.stdout)
    fields = {f["field"]: f for f in data["fields"]}
    assert fields["skills"]["changed"] is False
    assert fields["education:Example Institute"]["matched"] is True
    assert fields["education:Sample University"]["before"] == "C++"
    assert fields["role_skills:Contoso:Junior Analyst"]["changed"] is False
    assert fields["role_skills:Northwind:Data Analyst"]["changed"] is True
    assert data["unmatched"] == []
