"""Documents truthfulness: a CV or letter names only what achievements.yaml or profile.md holds.

Fixtures are fictional (Ana Example, Example Co, Sample Works, Example U). Each test runs the real render_cv.py, as a
subprocess (python3 -I) or through its command line, and asserts the defect the user would see. No network, no PDF
engine is needed: the forced engine is absent and the defects checked here are text defects.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "squads" / "jobs" / "skills"
RENDER = SKILLS / "rendering-cv" / "scripts" / "render_cv.py"
DOC = SKILLS / "writing-applications" / "references" / "cv-tailoring.md"

TRUTH_CODES = {"unknown_employer", "title_mismatch", "date_mismatch", "unknown_education", "unknown_skill",
               "unknown_skill_level", "unsupported_number", "unsupported_tool", "unsupported_claim", "private_data",
               "uncited_claim"}

PROFILE = """\
---
candidate:
  stage: mid
  include_age_in_cv: false
market:
  country: PE
  cv_page_limit: 2
  conventions: {photo: false, age: false, marital_status: false, references_line: false}
cv_template: classic
writing_style: {tone: warm_direct, formality: medium, avoid_phrases: []}
---
# Ana Example

Data analyst with eight years of reporting work, mostly for small finance teams.
"""

ACHIEVEMENTS = """\
experiences:
  - {id: EXP-001, title: "Data analyst", company: "Example Co", from: 2022-03, to: current}
  - {id: EXP-002, title: "Analyst", company: "Sample Works", from: 2019-01, to: 2022-02}
achievements:
  - id: ACH-007
    experience: EXP-001
    proficiency: did
    en: "Automated the weekly sales report with Python and Power BI, from six hours to twenty minutes."
    metric: {name: report_time, from: 360, to: 20, unit: min}
    verified: true
  - id: ACH-008
    experience: EXP-001
    proficiency: did
    en: "Built SQL views that the finance team uses to close the monthly ledger without manual extracts."
    verified: true
  - id: ACH-009
    experience: EXP-002
    proficiency: participated
    en: "Participated in the migration of legacy reports to a shared dashboard for three units."
    verified: true
  - id: ACH-010
    experience: EXP-001
    proficiency: did
    en: "Maintained the forecast model that the planning team reviews every month."
    verified: false
education:
  - {id: EDU-001, degree: "Industrial Engineering", institution: "Example U", year: 2018, verified: true}
skills:
  - {name: SQL, proficiency: did, years: 4, achievements: [ACH-008]}
  - {name: Python, proficiency: did, years: 4, achievements: [ACH-007]}
  - {name: Power BI, proficiency: did, achievements: [ACH-007]}
languages:
  - {language: english, level: B2, verified: true}
"""

CONTACT = """\
name: "Ana Example"
email: "ana@example.com"
phone: "+51 900 000 000"
location: "Lima, Peru"
links: []
"""

ANALYSIS = {"requirements": {"keywords": ["Python", "SQL", "Power BI"], "tools": ["Power BI"]}}

BASE_CV = {
    "language": "en",
    "header": {"name": "Ana Example", "headline": "Data analyst, reporting automation"},
    "summary": {"text": "Data analyst who automates reporting for small finance teams.", "achievements": ["ACH-007"]},
    "experience": [
        {"title": "Data analyst", "company": "Example Co", "dates": "2022-03 - current", "bullets": [
            {"text": "Automated the weekly sales report with Python and Power BI, cutting run time from six hours "
                      "to twenty minutes.", "achievements": ["ACH-007"]},
            {"text": "Built SQL views that the finance team uses to close the monthly ledger without manual "
                      "extracts.", "achievements": ["ACH-008"]},
        ]},
        {"title": "Analyst", "company": "Sample Works", "dates": "2019-01 - 2022-02", "bullets": [
            {"text": "Participated in the migration of legacy reports to a shared dashboard for three units.",
             "achievements": ["ACH-009"]},
        ]},
    ],
    "projects": [{"name": "Sales dashboard", "url": "", "text": "A shared sales dashboard that the regional team "
                                                              "reviews every Monday.", "achievements": ["ACH-008"]}],
    "skills": [{"name": "SQL", "level": "did"}, {"name": "Python", "level": ""}],
    "education": [{"degree": "Industrial Engineering", "institution": "Example U", "year": "2018"}],
    "languages": [{"language": "english", "level": "B2"}],
}

LETTER_CLEAN = """\
Dear Hiring Team,

Your posting asks for a reporting analyst who can own the weekly numbers. I have automated that report already. <!-- achievements: ACH-007 -->

Motivation: your team publishes its numbers openly, which suits how I work. <!-- achievements: none -->

Kind regards,
Ana Example
"""

LETTER_TOO_MUCH = """\
Dear Hiring Team,

Your posting asks for a reporting analyst who can own the weekly numbers. I have automated that report already. <!-- achievements: ACH-007 -->

I led a team of 20 engineers at Google and grew revenue by 300 percent while holding a PhD from MIT. <!-- achievements: none -->

Kind regards,
Ana Example
"""

LETTER_CITED_COMPANY = """\
Dear Hiring Team,

At Google I automated the weekly sales report with Python and Power BI. <!-- achievements: ACH-007 -->

Kind regards,
Ana Example
"""


def cv(**edits) -> dict:
    content = copy.deepcopy(BASE_CV)
    for key, value in edits.items():
        content[key] = value
    return content


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def inputs(folder: Path, *, profile: str = PROFILE, content=None, letter=None) -> dict:
    paths = {"profile": write(folder / "profile.md", profile),
             "achievements": write(folder / "achievements.yaml", ACHIEVEMENTS),
             "contact": write(folder / "contact.yaml", CONTACT),
             "analysis": write(folder / "analysis.json", json.dumps(ANALYSIS))}
    if letter is not None:
        paths["content"] = write(folder / "cover_letter.md", letter)
    else:
        paths["content"] = write(folder / "cv_content.json", json.dumps(content or BASE_CV, indent=1))
    return paths


def argv_for(paths: dict, out: Path, kind: str, engine: str, extra) -> list:
    return ["--kind", kind, "--content", str(paths["content"]), "--output", str(out), "--profile", str(paths["profile"]),
            "--achievements", str(paths["achievements"]), "--contact", str(paths["contact"]),
            "--analysis", str(paths["analysis"]), "--engine", engine, "--json", *extra]


def run_render(tmp_path: Path, *, content=None, letter=None, profile: str = PROFILE, kind: str = "cv",
               engine: str = "weasyprint", extra=(), launcher=None):
    """The real script in a subprocess. Returns (process, report or None, output folder)."""
    out = tmp_path / "out"
    paths = inputs(tmp_path / "in", profile=profile, content=content, letter=letter)
    cmd = [sys.executable, "-I"]
    if launcher is not None:
        cmd += [str(launcher), str(RENDER)]
    else:
        cmd += [str(RENDER)]
    cmd += argv_for(paths, out, kind, engine, list(extra))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    report_file = out / ("render_report.json" if kind == "cv" else "render_report_letter.json")
    report = json.loads(report_file.read_text(encoding="utf-8")) if report_file.is_file() else None
    return proc, report, out


def codes(report: dict) -> set:
    return {d["code"] for d in report["defects"]}


def messages(report: dict, code: str) -> list:
    return [d["message"] for d in report["defects"] if d["code"] == code]


def load_render():
    spec = importlib.util.spec_from_file_location("render_cv_truthfulness", RENDER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


render = load_render()


# --- the clean fixtures and the employer, title, date, number, degree, skill and tool checks -------------------------

def test_clean_cv_and_letter_raise_no_truthfulness_defect(tmp_path):
    proc, report, _ = run_render(tmp_path / "cv")
    assert TRUTH_CODES.isdisjoint(codes(report)), json.dumps(report["defects"], indent=1)
    assert report["section_order"] == ["summary", "experience", "skills", "projects", "education", "languages"]
    letter_proc, letter_report, _ = run_render(tmp_path / "letter", kind="letter", letter=LETTER_CLEAN)
    assert TRUTH_CODES.isdisjoint(codes(letter_report)), json.dumps(letter_report["defects"], indent=1)


def qa_cases():
    head_of_data = copy.deepcopy(BASE_CV["experience"])
    head_of_data[0]["title"], head_of_data[0]["company"] = "Head of Data", "Google"
    wrong_title = copy.deepcopy(BASE_CV["experience"])
    wrong_title[0]["title"] = "Head of Data"
    wrong_dates = copy.deepcopy(BASE_CV["experience"])
    wrong_dates[0]["dates"] = "2021-03 - current"
    bullets = copy.deepcopy(BASE_CV["experience"])
    bullets[0]["bullets"][0]["text"] = ("Automated the weekly sales report with Python and Power BI, cutting run time "
                                        "from six hours to two minutes.")
    team = copy.deepcopy(BASE_CV["experience"])
    team[0]["bullets"][0]["text"] = "Led a team of 15 analysts who automated the weekly sales report with Python and Power BI."
    budget = copy.deepcopy(BASE_CV["experience"])
    budget[0]["bullets"][1]["text"] = "Managed a 2M USD budget for the SQL views the finance team relies on each month."
    airflow = copy.deepcopy(BASE_CV["experience"])
    airflow[0]["bullets"][1]["text"] = "Built SQL views scheduled in Airflow for the finance team each month."
    return [
        ("head of data at google", cv(experience=head_of_data), "unknown_employer", "Google"),
        ("head of data at example co", cv(experience=wrong_title), "title_mismatch", "Head of Data"),
        ("example co from 2021-03", cv(experience=wrong_dates), "date_mismatch", "2021-03"),
        ("12 years in the summary", cv(summary={"text": "Data analyst with 12 years of reporting automation for small "
                                                        "finance teams.", "achievements": ["ACH-007"]}),
         "unsupported_number", "12"),
        ("team of 15", cv(experience=team), "unsupported_number", "15"),
        ("2M USD", cv(experience=budget), "unsupported_number", "2"),
        ("six hours to two minutes", cv(experience=bullets), "unsupported_number", "2"),
        ("kubernetes (expert)", cv(skills=[{"name": "Kubernetes", "level": "expert"}]), "unknown_skill", "Kubernetes"),
        ("airflow", cv(experience=airflow), "unsupported_tool", "airflow"),
        ("PhD Computer Science, MIT | 2014",
         cv(education=[{"degree": "PhD Computer Science", "institution": "MIT", "year": "2014"}]),
         "unknown_education", "MIT"),
    ]


@pytest.mark.parametrize("label, content, code, needle", qa_cases(), ids=[c[0] for c in qa_cases()])
def test_qa_claim_lines_are_refused_by_the_real_script(tmp_path, label, content, code, needle):
    proc, report, _ = run_render(tmp_path, content=content)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert code in codes(report), json.dumps(report["defects"], indent=1)
    assert any(needle in d["message"] for d in report["defects"] if d["code"] == code)


def test_skill_level_must_be_a_recorded_proficiency(tmp_path):
    proc, report, _ = run_render(tmp_path, content=cv(skills=[{"name": "SQL", "level": "expert"}]))
    assert "unknown_skill_level" in codes(report)


# --- letters: <!-- achievements: none --> exempts greeting and closing only -------------------------------------------

def test_letter_none_exempts_only_greeting_and_closing(tmp_path):
    proc, report, _ = run_render(tmp_path, kind="letter", letter=LETTER_TOO_MUCH, extra=())
    assert proc.returncode == 1, proc.stdout + proc.stderr
    found = messages(report, "uncited_claim")
    assert any("greeting and closing" in m and "a number" in m and "a degree" in m for m in found), found
    assert any("Google" in m for m in found), found


def test_letter_company_and_degree_must_come_from_the_sources(tmp_path):
    proc, report, _ = run_render(tmp_path, kind="letter", letter=LETTER_CITED_COMPANY)
    assert "unsupported_claim" in codes(report)
    assert any("Google" in m for m in messages(report, "unsupported_claim"))


# --- privacy: age, marital status, date of birth, photo and nationality stay out of free text ------------------------

PRIVATE_CASES = [
    ("en headline, age and marital status", "Senior Data Lead, 34 years old, married", "age"),
    ("es summary, age and marital status", "Analista de datos, 34 años, casado, con experiencia en reporting.",
     "marital status"),
    ("es summary, date of birth", "Fecha de nacimiento: 1991-04-02. Analista de datos.", "date of birth"),
    ("pt summary, marital status", "Analista de dados. Estado civil: casado.", "marital status"),
    ("de summary, marital status", "Datenanalystin. Familienstand: verheiratet.", "marital status"),
    ("es summary, nationality", "Analista de datos. Nacionalidad: peruana.", "nationality"),
]


@pytest.mark.parametrize("label, text, kind", PRIVATE_CASES, ids=[c[0] for c in PRIVATE_CASES])
def test_private_data_in_free_text_is_a_defect(tmp_path, label, text, kind):
    if label.startswith("en headline"):
        content = cv(header={"name": "Ana Example", "headline": text})
    else:
        content = cv(summary={"text": text, "achievements": ["ACH-007"]})
    proc, report, out = run_render(tmp_path, content=content)
    assert proc.returncode == 1
    found = messages(report, "private_data")
    assert any(m.startswith(kind + " in ") for m in found), found


def test_years_of_experience_are_not_private_data(tmp_path):
    content = cv(summary={"text": "Analista con 4 años de experiencia en reporting.", "achievements": ["ACH-007"]})
    _, report, _ = run_render(tmp_path, content=content)
    assert "private_data" not in codes(report)


# --- stage order: the documented table and the code agree for every stage (returning included) ----------------------

LABEL_TO_KEY = {"transferable skills": "transferable"}  # the table names the heading, the report names the section


def documented_orders() -> dict:
    orders = {}
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or "summary" not in line:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        order = [LABEL_TO_KEY.get(s.strip(), s.strip()) for s in cells[1].split(",")]
        for stage in cells[0].split(","):
            orders[stage.strip()] = order
    return orders


@pytest.mark.parametrize("stage", ["first_job", "junior", "mid", "lead", "senior", "career_change", "returning", "unset"])
def test_stage_order_is_the_documented_order(tmp_path, stage):
    profile = PROFILE.replace("  stage: mid\n", "") if stage == "unset" else PROFILE.replace("stage: mid", f"stage: {stage}")
    extra = {}
    if stage == "career_change":
        extra["transferable_skills"] = ["Process audits applied to reporting quality"]
    if stage == "returning":
        extra["career_gap"] = "Career break in 2023 to care for a family member; completed two data courses."
    _, report, _ = run_render(tmp_path, content=cv(**extra), profile=profile)
    assert report["section_order"] == documented_orders()[stage], (stage, report["section_order"])


def test_first_job_keeps_a_transferable_block(tmp_path):
    profile = PROFILE.replace("stage: mid", "stage: first_job")
    _, report, out = run_render(tmp_path, content=cv(transferable_skills=["Process audits for reporting quality"]),
                                profile=profile)
    text = (out / "cv_ats.txt").read_text(encoding="utf-8")
    assert "TRANSFERABLE SKILLS" in text and "Process audits" in text


# --- DOCX is optional: a warning, the PDF and the text still count ------------------------------------------------------

LAUNCHER = """\
import runpy
import sys

sys.modules["docx"] = None  # python-docx is unavailable: the import fails the way a missing package does
path = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(path, run_name="__main__")
"""


def test_missing_python_docx_is_a_warning_and_the_render_still_passes(tmp_path):
    launcher = write(tmp_path / "launch" / "without_docx.py", LAUNCHER)
    proc, report, out = run_render(tmp_path / "run", engine="auto", launcher=launcher)
    assert report["engines"]["docx"] == "none"
    assert "docx_missing" not in codes(report)
    assert any(w.startswith("docx_skipped") for w in report["warnings"]), report["warnings"]
    assert not (out / "cv.docx").exists()
    if report["engines"]["pdf"] != "none":
        assert (out / "cv_ats.pdf").is_file() and (out / "cv_ats.txt").is_file()
        assert proc.returncode == 0, json.dumps(report["defects"], indent=1)
    else:
        assert codes(report) <= {"engine_missing"}, json.dumps(report["defects"], indent=1)


# --- templates: the profile decides; a change is a question to the user -------------------------------------------------

def test_the_profile_template_is_used_when_no_template_is_passed(tmp_path):
    profile = PROFILE.replace("cv_template: classic", "cv_template: modern")
    _, report, _ = run_render(tmp_path, profile=profile)
    assert report["template"] == "modern" and report["template_source"] == "shipped"


def test_a_template_change_is_refused_without_the_users_yes(tmp_path):
    # Real sequence: the writer asks for `compact` while the profile says `classic`. Without the user's yes the
    # renderer refuses (exit 2), writes no report and no PDF, and says why.
    proc, report, out = run_render(tmp_path, extra=["--template", "compact"])
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert report is None and not (out / "cv_ats.pdf").exists()
    assert "differs from profile cv_template classic" in proc.stderr and "user's yes" in proc.stderr, proc.stderr


def test_a_template_change_with_the_users_yes_renders_and_says_so(tmp_path):
    proc, report, _ = run_render(tmp_path, extra=["--template", "compact", "--template-override-by-user"])
    assert report is not None and report["template"] == "compact", proc.stderr
    assert any("differs from profile cv_template classic" in w and "--template-override-by-user" in w
               for w in report["warnings"]), report["warnings"]


def test_the_profile_template_needs_no_override(tmp_path):
    proc, report, _ = run_render(tmp_path, extra=["--template", "classic"])
    assert report is not None and report["template"] == "classic", proc.stderr


def test_overflow_is_a_defect_that_keeps_the_profile_template(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(render, "detect_engine", lambda choice: "fake")

    def fake_pdf(html_text, html_path, pdf_path, engine, defects):
        pdf_path.write_bytes(b"%PDF-1.4 stub\n")
        return "fake", 3  # three measured pages against a budget of two

    monkeypatch.setattr(render, "render_pdf", fake_pdf)
    profile = PROFILE.replace("cv_template: classic", "cv_template: compact")
    paths = inputs(tmp_path / "in", profile=profile, content=BASE_CV)
    out = tmp_path / "out"
    code = render.main(argv_for(paths, out, "cv", "auto", []))
    report = json.loads((out / "render_report.json").read_text(encoding="utf-8"))
    assert code == 1
    assert report["template"] == "compact"
    overflow = messages(report, "page_budget_exceeded")
    assert overflow and "template compact stays" in overflow[0], overflow


# --- a missing source list blocks; degree levels; quantity words; tools; headline; ownership -----------------------

def run_with(tmp_path: Path, *, content, achievements: str, kind: str = "cv", letter: str | None = None, extra=()):
    """The real script with a chosen achievements.yaml (the fixture default has every list; these cases need gaps)."""
    paths = inputs(tmp_path / "in", content=content, letter=letter)
    write(paths["achievements"], achievements)
    out = tmp_path / "out"
    cmd = [sys.executable, "-I", str(RENDER)] + argv_for(paths, out, kind, "auto", list(extra))
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    name = "render_report.json" if kind == "cv" else "render_report_letter.json"
    report = json.loads((out / name).read_text(encoding="utf-8")) if (out / name).is_file() else None
    return proc, report


# A CV with a PhD, a doctorate in the summary and a skill, and an achievements file that holds no education and no
# skills list. Fictional person.
ACH_NO_LISTS = """\
experiences:
  - {id: EXP-001, title: "Data Analyst", company: "Example Co", from: 2019-03, to: current}
achievements:
  - id: ACH-001
    experience: EXP-001
    proficiency: did
    en: "Automated the weekly sales report with Python."
    verified: true
languages:
  - {language: english, level: B2, verified: true}
"""

CV_NO_LISTS = {
    "language": "en",
    "header": {"name": "Ana Example", "headline": "Data Analyst"},
    "summary": {"text": "Data analyst with a doctorate in statistics who automated reporting.",
                "achievements": ["ACH-001"]},
    "experience": [{"title": "Data Analyst", "company": "Example Co", "dates": "2019-03 - current",
                    "bullets": [{"text": "Automated the weekly sales report with Python.", "achievements": ["ACH-001"]}]}],
    "skills": [{"name": "Kubernetes", "level": "did"}],
    "education": [{"degree": "PhD Computer Science", "institution": "MIT", "year": "2014"}],
    "languages": [{"language": "English", "level": "B2"}],
}


def test_cv_with_no_education_or_skills_list_is_blocked_not_skipped(tmp_path):
    # A named degree or skill with no list to check it against is a defect, never a skipped check.
    proc, report = run_with(tmp_path, content=CV_NO_LISTS, achievements=ACH_NO_LISTS)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert {"unknown_education", "unsupported_claim", "unknown_skill"} <= codes(report), report["defects"]
    assert any("PhD Computer Science" in m for m in messages(report, "unknown_education")), report["defects"]
    assert any("Kubernetes" in m for m in messages(report, "unknown_skill")), report["defects"]
    assert not any("not checked" in w and ("education" in w or "skills" in w) for w in report["warnings"]), \
        report["warnings"]


@pytest.mark.parametrize("claim, education, expected", [
    ("I hold a doctoral degree in statistics.", [("BSc Statistics", "Example U")], "unsupported_claim"),
    ("Doctorado en Estadística por la Example U.", [("PhD Estadística", "Example U")], None),
    ("Cuento con una maestría en datos.", [("BSc Datos", "Example U")], "unsupported_claim"),
    ("He completed a PhD in statistics.", [("MBA", "Example U")], "unsupported_claim"),
    ("I completed a PhD in statistics.", [("PhD Statistics", "Example U")], None),
    ("I completed a PhD in biology.", [("PhD Statistics", "Example U")], "unsupported_claim"),
])
def test_degree_claims_match_by_level_and_field(tmp_path, claim, education, expected):
    # A degree claim matches a source degree of the same level (doctoral is not a bachelor's) and of the same field.
    letter = ("Dear Hiring Team,\n\n" + claim + " <!-- achievements: ACH-001 -->\n\nKind regards,\nAna Example\n")
    ach = ACH_NO_LISTS.replace("languages:", "education:\n" + "".join(
        f"  - {{id: EDU-00{i + 1}, degree: \"{d}\", institution: \"{s}\", year: 2016, verified: true}}\n"
        for i, (d, s) in enumerate(education)) + "languages:")
    proc, report = run_with(tmp_path, content=None, kind="letter", letter=letter, achievements=ach)
    found = codes(report) & {"unsupported_claim", "unknown_education"}
    if expected:
        assert expected in found, report["defects"]
    else:
        assert not found, report["defects"]


def test_quantity_words_are_checked_like_digits(tmp_path):
    # Quantity words are checked like digits: a cited achievement that holds neither quantity is a defect.
    content = cv(experience=[{"title": "Data analyst", "company": "Example Co", "dates": "2022-03 - current", "bullets": [
        {"text": "Reduced costs by a third and doubled revenue with SQL queries for the finance team.",
         "achievements": ["ACH-008"]}]}])
    _, report, _ = run_render(tmp_path, content=content)
    messages_found = " ".join(messages(report, "unsupported_number"))
    assert "a third" in messages_found and "doubled" in messages_found, report["defects"]


def test_a_quantity_the_cited_achievement_holds_is_not_a_defect(tmp_path):
    # The same quantity word, in the cited achievement's own text, is supported: no unsupported_number for it.
    ach = ACHIEVEMENTS.replace("without manual extracts.", "and cut the close time by half.")
    content = cv(experience=[{"title": "Data analyst", "company": "Example Co", "dates": "2022-03 - current", "bullets": [
        {"text": "Built SQL views that the finance team uses to close the monthly ledger, and cut the close time by half.",
         "achievements": ["ACH-008"]}]}])
    proc, report = run_with(tmp_path, content=content, achievements=ach)
    assert not any("half" in m for m in messages(report, "unsupported_number")), report["defects"]
    # The same claim against the fixture achievement (which says nothing of half) is a defect: the test is not vacuous.
    _, report2, _ = run_render(tmp_path / "again", content=content)
    assert any("half" in m for m in messages(report2, "unsupported_number")), report2["defects"]


def test_tools_outside_the_fixed_list_are_checked_by_their_capitalised_name(tmp_path):
    # NimbusDB is a fictional technology name that is not in the fixed list: only the CamelCase rule can flag it.
    content = cv(experience=[{"title": "Data analyst", "company": "Example Co", "dates": "2022-03 - current", "bullets": [
        {"text": "Automated the weekly sales report with Python and NimbusDB, cutting run time from six hours "
                 "to twenty minutes.", "achievements": ["ACH-007"]}]}])
    _, report, _ = run_render(tmp_path, content=content)
    assert any("nimbusdb" in m for m in messages(report, "unsupported_tool")), report["defects"]


def test_a_headline_must_match_an_experience_title(tmp_path):
    # A headline must match an experience title or a target role: a different role noun is a mismatch.
    content = cv(header={"name": "Ana Example", "headline": "Lead Data Scientist and Machine Learning Engineer"})
    _, report, _ = run_render(tmp_path, content=content)
    assert "title_mismatch" in codes(report), report["defects"]
    assert any("Lead Data Scientist" in m for m in messages(report, "title_mismatch")), report["defects"]


def test_a_headline_that_matches_a_title_passes(tmp_path):
    content = cv(header={"name": "Ana Example", "headline": "Data analyst, reporting automation"})
    _, report, _ = run_render(tmp_path, content=content)
    assert "title_mismatch" not in codes(report), report["defects"]


def test_an_ownership_claim_needs_a_cited_led_achievement(tmp_path):
    # An ownership verb needs a cited achievement recorded as led; a participated record does not carry ownership.
    content = cv(experience=[{"title": "Data analyst", "company": "Example Co", "dates": "2022-03 - current", "bullets": [
        {"text": "Led the migration of forty reports to Power BI across the region.", "achievements": ["ACH-009"]}]}])
    _, report, _ = run_render(tmp_path, content=content)
    assert any("ownership" in m for m in messages(report, "unsupported_claim")), report["defects"]


def test_a_cv_headline_may_use_a_positioning_title_the_user_chose_but_not_one_they_did_not(tmp_path):
    # Companies name the same work many ways: a headline under a title the user positions under is theirs.
    content = cv(header={"name": "Ana Example", "headline": "Forward Deployed Engineer"})
    _, report, _ = run_render(tmp_path / "a", content=content)
    assert "title_mismatch" in codes(report)
    chosen = PROFILE.replace("cv_template: classic", 'cv_template: classic\npositioning_titles: ["Forward Deployed Engineer"]')
    _, report, _ = run_render(tmp_path / "b", content=content, profile=chosen)
    assert "title_mismatch" not in codes(report), report["defects"]
    # its synonyms come with it: the family's own titles
    content = cv(header={"name": "Ana Example", "headline": "Forward Deployed Software Engineer"})
    _, report, _ = run_render(tmp_path / "c", content=content, profile=chosen)
    assert "title_mismatch" not in codes(report), report["defects"]
