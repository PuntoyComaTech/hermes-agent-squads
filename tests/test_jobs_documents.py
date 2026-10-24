"""Documents area of the jobs squad: CV and letter rendering, PDF verifiers, templates, and the skill contracts.

Fixtures are fictional (Ana Example, Lima). Nothing here needs the network. Tests that need a PDF text extractor
or Poppler skip cleanly when it is absent. The renderer tests inject a fake PDF engine, so the page-budget and
cutting behaviour is checked without Chromium; one test uses the real Chrome binary when it is installed.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "squads" / "jobs" / "skills"
SCRIPTS = SKILLS / "rendering-cv" / "scripts"
TEMPLATES = SKILLS / "rendering-cv" / "templates"
DOC_SKILLS = ("writing-applications", "rendering-cv", "preparing-interviews")


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses looks the module up while the class is built
    spec.loader.exec_module(module)
    return module


render = load("render_cv_under_test", SCRIPTS / "render_cv.py")
verify_pdf = load("verify_pdf_under_test", SCRIPTS / "verify_pdf.py")
verify_layout = load("verify_layout_under_test", SCRIPTS / "verify_layout.py")

HAS_PDFTOTEXT = bool(shutil.which("pdftotext") and shutil.which("pdfinfo"))
HAS_CHROME = render.chromium_binary() is not None
needs_poppler = pytest.mark.skipif(not HAS_PDFTOTEXT, reason="pdftotext/pdfinfo (poppler) not installed")
needs_chrome = pytest.mark.skipif(not HAS_CHROME, reason="no Chromium or Google Chrome binary")

PROFILE = """\
---
candidate:
  stage: mid
  age: 34
  include_age_in_cv: false
market:
  country: PE
  cv_page_limit: 2
  conventions: {photo: false, age: false, marital_status: false, references_line: false}
writing_style: {tone: "warm_direct", formality: medium, avoid_phrases: ["open to opportunities"]}
---
# Ana Example
"""

ACHIEVEMENTS = """\
achievements:
  - {id: ACH-007, proficiency: led, verified: true}
  - {id: ACH-008, proficiency: did, verified: true}
  - {id: ACH-009, proficiency: participated, verified: true}
  - {id: ACH-010, proficiency: did, verified: false}
languages:
  - {language: english, level: B2, verified: true}
"""

CONTACT = """\
name: "Ana Example"
email: "ana@example.com"
phone: "+51 900 000 000"
location: "Lima, Peru"
links: ["https://github.com/example"]
"""

ANALYSIS = {"requirements": {"keywords": ["Python", "SQL", "Power BI", "dbt"], "tools": ["Power BI"]}}


def cv_content(**overrides) -> dict:
    content = {
        "language": "en",
        "header": {"name": "Ana Example", "headline": "Data analyst, reporting automation"},
        "summary": {"text": "Data analyst with four years of reporting automation in Lima.",
                    "achievements": ["ACH-007"]},
        "experience": [
            {"title": "Data analyst", "company": "Example Co", "dates": "2022\u201303 \u2013 current",
             "bullets": [
                 {"text": "Automated the weekly sales report with Python and Power BI, cutting run time from six "
                          "hours to twenty minutes.", "achievements": ["ACH-007"]},
                 {"text": "Built SQL views that the finance team uses to close the monthly ledger without manual "
                          "extracts.", "achievements": ["ACH-008"]},
             ]},
            {"title": "Analyst", "company": "Older Co", "dates": "2019-01 - 2022-02",
             "bullets": [
                 {"text": "Participated in the migration of legacy reports to a shared dashboard for three units.",
                  "achievements": ["ACH-009"]},
             ]},
        ],
        "skills": [{"name": "SQL", "level": "did"}, {"name": "Python", "level": ""}],
        "education": [{"degree": "Industrial Engineering", "institution": "Example U", "year": "2021"}],
        "languages": [{"language": "english", "level": "B2"}],
    }
    content.update(overrides)
    return content


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def render_cv_case(tmp_path: Path, content: dict | None = None, *, profile: str = PROFILE, extra=(),
                   analysis: dict | None = ANALYSIS, template: str = "classic"):
    """Run render_cv.main in-process on fixtures under tmp_path. Returns (exit code, report, output dir)."""
    src = tmp_path / "in"
    out = tmp_path / "out"
    argv = ["--content", str(write(src / "cv_content.json", json.dumps(content or cv_content(), indent=1))),
            "--output", str(out), "--profile", str(write(src / "profile.md", profile)),
            "--achievements", str(write(src / "achievements.yaml", ACHIEVEMENTS)),
            "--contact", str(write(src / "contact.yaml", CONTACT)), "--template", template, "--json"]
    if analysis is not None:
        argv += ["--analysis", str(write(src / "analysis.json", json.dumps(analysis)))]
    argv += list(extra)
    code = render.main(argv)
    report = json.loads((out / "render_report.json").read_text(encoding="utf-8"))
    return code, report, out


def jc_upload(out: Path) -> Path:
    return render.jc.cv_upload_path(out)


def codes(report: dict) -> list:
    return [d["code"] for d in report["defects"]]


@pytest.fixture
def no_engine(monkeypatch):
    """No PDF engine at all: deterministic on any machine."""
    monkeypatch.setattr(render, "chromium_binary", lambda: None)
    monkeypatch.setattr(render, "weasyprint_available", lambda: False)


@pytest.fixture
def fake_engine(monkeypatch):
    """A PDF engine whose page count is a function of the HTML. Writes a stub PDF file."""
    def install(pages_of):
        monkeypatch.setattr(render, "detect_engine", lambda choice: "fake")

        def fake_render_pdf(html_text, html_path, pdf_path, engine, defects):
            pdf_path.write_bytes(b"%PDF-1.4 stub\n")
            return "fake", pages_of(html_text)

        monkeypatch.setattr(render, "render_pdf", fake_render_pdf)
    return install


# --- PDF fixtures ----------------------------------------------------------------------------------------------------

def make_pdf(path: Path, pages: list) -> Path:
    """A minimal valid PDF. pages: list of pages, each a list of (top_pt, text) lines in Helvetica 10pt."""
    width, height = 595, 842

    def escape(text: str) -> str:
        out = []
        for byte in text.encode("cp1252"):
            ch = chr(byte)
            if ch in "()\\":
                out.append("\\" + ch)
            elif 32 <= byte < 127:
                out.append(ch)
            else:
                out.append("\\%03o" % byte)
        return "".join(out)

    parts: list = [b"%PDF-1.4\n"]
    offsets: list = []

    def add(body: bytes) -> None:
        offsets.append(sum(len(p) for p in parts))
        parts.append(f"{len(offsets)} 0 obj\n".encode() + body + b"\nendobj\n")

    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    add(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    for i, lines in enumerate(pages):
        stream = "\n".join(f"BT /F1 10 Tf 72 {height - top:.2f} Td ({escape(text)}) Tj ET" for top, text in lines)
        data = stream.encode("ascii")
        add(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>".encode())
        add(f"<< /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream")
    xref_at = sum(len(p) for p in parts)
    xref = f"xref\n0 {len(offsets) + 1}\n0000000000 65535 f \n" + "".join(f"{o:010d} 00000 n \n" for o in offsets)
    trailer = f"trailer\n<< /Size {len(offsets) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    parts.append((xref + trailer).encode("ascii"))
    path.write_bytes(b"".join(parts))
    return path


def full_page(top_start: float = 40, top_end: float = 660, step: float = 14, text: str = "Line of text") -> list:
    lines, top = [], top_start
    while top <= top_end:
        lines.append((top, text))
        top += step
    return lines


# --- scripts and help ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("script", ["render_cv.py", "verify_pdf.py", "verify_layout.py"])
def test_every_document_script_answers_help(script):
    proc = subprocess.run([sys.executable, "-I", str(SCRIPTS / script), "--help"], capture_output=True, text=True,
                          timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()


def test_render_cv_keeps_its_original_flags_and_gains_new_ones():
    help_text = render.build_parser().format_help()
    for flag in ("--content", "--output", "--analysis", "--pages", "--engine", "--json"):
        assert flag in help_text
    for flag in ("--template", "--kind", "--profile", "--achievements", "--contact", "--letter", "--no-fit"):
        assert flag in help_text


# --- CV rendering ----------------------------------------------------------------------------------------------------

def test_report_keeps_the_original_shape(tmp_path, no_engine):
    _, report, _ = render_cv_case(tmp_path)
    original = {"content", "output", "language", "files", "engines", "pages_expected", "pages_actual",
                "selectable_text", "reading_order_ok", "links", "keyword_coverage", "missing_keywords",
                "defects", "warnings"}
    assert original <= set(report)
    assert set(report["engines"]) == {"pdf", "docx"}


def test_cv_renders_text_and_html_with_hyphen_dates_and_no_dashes(tmp_path, no_engine):
    _, report, out = render_cv_case(tmp_path)
    txt = (out / "cv_ats.txt").read_text(encoding="utf-8")
    html_text = (out / "cv_ats.html").read_text(encoding="utf-8")
    assert "Ana Example" in txt and "Data analyst" in txt
    assert "2022-03 - current" in txt
    assert "2022\u201303" not in txt  # the en-dash date was converted
    assert "\u2014" not in txt and "\u2014" not in html_text
    assert "<html" in html_text and "{{" not in html_text


def test_uncited_and_unverified_claims_are_defects(tmp_path, no_engine):
    content = cv_content()
    content["experience"][1]["bullets"].append({"text": "Reviewed dashboards for the planning team.",
                                                "achievements": []})
    content["experience"][1]["bullets"].append({"text": "Ran a forecast model for the ledger close.",
                                                "achievements": ["ACH-010"]})
    _, report, _ = render_cv_case(tmp_path, content)
    assert "uncited_claim" in codes(report)
    assert any(d["code"] == "unverified_achievement" and "ACH-010" in d["message"] for d in report["defects"])


def test_ownership_verb_on_participated_work_is_a_stretch_flag(tmp_path, no_engine):
    content = cv_content()
    content["experience"][1]["bullets"] = [{"text": "Led the migration of legacy reports to a shared dashboard.",
                                            "achievements": ["ACH-009"]}]
    _, report, _ = render_cv_case(tmp_path, content)
    assert len(report["stretch_flags"]) == 1
    flag = report["stretch_flags"][0]
    assert flag["question"].startswith("stretch because ") and flag["question"].endswith("keep, soften or drop")


def test_cliches_profile_avoid_phrases_and_em_dashes_are_defects(tmp_path, no_engine):
    content = cv_content(summary={"text": "I am passionate about data \u2014 and open to opportunities.",
                                  "achievements": ["ACH-007"]})
    _, report, _ = render_cv_case(tmp_path, content)
    found = codes(report)
    assert "style_em_dash" in found
    messages = " ".join(d["message"] for d in report["defects"])
    assert "passionate about" in messages
    assert "open to opportunities" in messages


def test_language_level_cannot_be_raised_and_undeclared_is_flagged(tmp_path, no_engine):
    content = cv_content(languages=[{"language": "english", "level": "C1"}, {"language": "french", "level": "B1"}])
    _, report, _ = render_cv_case(tmp_path, content)
    found = codes(report)
    assert "language_level_raised" in found and "language_undeclared" in found


def test_age_is_printed_only_when_the_profile_asks(tmp_path, no_engine):
    _, _, out_hidden = render_cv_case(tmp_path / "hidden")
    assert "34" not in (out_hidden / "cv_ats.txt").read_text(encoding="utf-8")
    shown = PROFILE.replace("include_age_in_cv: false", "include_age_in_cv: true")
    _, _, out_shown = render_cv_case(tmp_path / "shown", profile=shown)
    assert "Age 34" in (out_shown / "cv_ats.txt").read_text(encoding="utf-8")


def test_report_and_stdout_never_carry_contact_details(tmp_path, no_engine, capsys):
    code, report, out = render_cv_case(tmp_path)
    printed = capsys.readouterr().out
    assert "ana@example.com" not in printed
    assert "ana@example.com" not in json.dumps(report)
    assert "ana@example.com" in (out / "cv_ats.txt").read_text(encoding="utf-8")


@pytest.mark.parametrize("stage, first, second", [
    ("first_job", "EDUCATION", "EXPERIENCE"),
    ("senior", "EXPERIENCE", "SKILLS"),
])
def test_stage_sets_the_section_order(tmp_path, no_engine, stage, first, second):
    profile = PROFILE.replace("stage: mid", f"stage: {stage}")
    _, report, out = render_cv_case(tmp_path, profile=profile)
    txt = (out / "cv_ats.txt").read_text(encoding="utf-8")
    assert txt.index(first) < txt.index(second)
    assert report["stage"] == stage


def test_returning_stage_requires_an_honest_gap_line(tmp_path, no_engine):
    profile = PROFILE.replace("stage: mid", "stage: returning")
    _, report, _ = render_cv_case(tmp_path, profile=profile)
    assert "stage_requirement" in codes(report)
    content = cv_content(career_gap="Career break of 2023 for family reasons; completed two data courses.")
    _, report, out = render_cv_case(tmp_path / "gap", content, profile=profile)
    assert "stage_requirement" not in codes(report)
    assert "Career break of 2023" in (out / "cv_ats.txt").read_text(encoding="utf-8")


def test_career_change_renders_the_transferable_skills_block(tmp_path, no_engine):
    profile = PROFILE.replace("stage: mid", "stage: career_change")
    content = cv_content(transferable_skills=["Process audits, now applied to reporting quality"])
    _, report, out = render_cv_case(tmp_path, content, profile=profile)
    txt = (out / "cv_ats.txt").read_text(encoding="utf-8")
    assert "TRANSFERABLE SKILLS" in txt and "Process audits" in txt
    assert report["section_order"][0] == "summary"


def test_spanish_headings_and_english_fallback_with_a_warning(tmp_path, no_engine):
    _, _, out = render_cv_case(tmp_path / "es", cv_content(language="es"))
    txt = (out / "cv_ats.txt").read_text(encoding="utf-8")
    assert "EXPERIENCIA" in txt and "PERFIL" in txt and "EXPERIENCE" not in txt
    _, report, out_fr = render_cv_case(tmp_path / "fr", cv_content(language="fr"))
    assert "EXPERIENCE" in (out_fr / "cv_ats.txt").read_text(encoding="utf-8")
    assert any("fall back to English" in w for w in report["warnings"])


def test_references_line_only_when_the_market_convention_says_so(tmp_path, no_engine):
    _, _, out = render_cv_case(tmp_path / "off")
    assert "Referencias" not in (out / "cv_ats.txt").read_text(encoding="utf-8")
    on = PROFILE.replace("references_line: false", "references_line: true")
    _, _, out_on = render_cv_case(tmp_path / "on", profile=on)
    assert "Referencias disponibles" not in (out_on / "cv_ats.txt").read_text(encoding="utf-8")
    assert "References available upon request." in (out_on / "cv_ats.txt").read_text(encoding="utf-8")


def test_page_budget_comes_from_the_profile_limit(tmp_path, no_engine):
    one = PROFILE.replace("cv_page_limit: 2", "cv_page_limit: 1")
    _, report, _ = render_cv_case(tmp_path, profile=one)
    assert report["page_budget"] == 1 and report["page_budget_source"] == "profile"
    _, report, _ = render_cv_case(tmp_path / "default", profile="---\nmarket: {country: PE}\n---\n")
    assert report["page_budget"] == 2 and report["page_budget_source"] == "default"


def test_without_an_engine_nothing_is_cut_and_the_page_count_is_an_estimate(tmp_path, no_engine):
    _, report, _ = render_cv_case(tmp_path, extra=["--pages", "1"])
    assert report["cuts"] == []
    assert report["page_method"] == "estimate" and isinstance(report["pages_estimated"], int)
    assert "engine_missing" in codes(report)
    assert any("not measurable" in w or "estimated" in w for w in report["warnings"])


def test_the_cv_a_recruiter_receives_is_named_after_the_candidate(tmp_path, fake_engine):
    """A recruiter's ATS and the owner's phone show the file name: cv_ats.pdf says nothing; CV_Ana_Example.pdf does."""
    fake_engine(lambda html_text: 1)
    code, report, out = render_cv_case(tmp_path)
    named = out / "CV_Ana_Example.pdf"
    assert named.read_bytes() == (out / "cv_ats.pdf").read_bytes(), "the upload copy is the reviewed render, byte for byte"
    assert str(named) in report["files"]
    assert jc_upload(out) == named


def test_a_rerender_under_a_new_name_leaves_no_old_copy_to_upload(tmp_path, fake_engine):
    fake_engine(lambda html_text: 1)
    _, _, out = render_cv_case(tmp_path)
    (out / "CV_Old_Name.pdf").write_bytes(b"%PDF-1.4 earlier render\n")
    render_cv_case(tmp_path)
    assert sorted(p.name for p in out.glob("CV_*.pdf")) == ["CV_Ana_Example.pdf"]


@pytest.mark.parametrize("full, short, expected", [
    ("José María Pérez García", "", "CV_Jose_Perez.pdf"),        # two given names + two surnames: first of each
    ("Søren Kierkegaard", "", "CV_Soren_Kierkegaard.pdf"),
    ("Jean-Luc Picard", "", "CV_Jean-Luc_Picard.pdf"),
    ("José María Pérez García", "José Pérez G", "CV_Jose_Perez_G.pdf"),  # contact.yaml short_name wins
    ("", "", ""),
])
def test_the_upload_name_is_ascii_and_reads_as_name_and_surname(full, short, expected):
    assert render.jc.cv_upload_name(full, short) == expected


def test_a_related_tool_plays_for_the_candidate_and_an_unrelated_one_is_still_refused(tmp_path, no_engine):
    """The owner works with SQL on Azure and AWS; a posting asks for PostgreSQL. Naming it next to SQL is the
    adaptation the owner wants, not a fabrication; Kubernetes, with no held tool in its family, stays a defect."""
    ach = ACHIEVEMENTS + "skills:\n  - {name: SQL}\n  - {name: Azure}\n"
    content = cv_content()
    content["skills"] = [{"name": "SQL (PostgreSQL, Azure SQL)", "level": "did"}]
    src = tmp_path / "in"
    out = tmp_path / "out"
    argv = ["--content", str(write(src / "cv_content.json", json.dumps(content))), "--output", str(out),
            "--profile", str(write(src / "profile.md", PROFILE)),
            "--achievements", str(write(src / "achievements.yaml", ach)),
            "--contact", str(write(src / "contact.yaml", CONTACT)), "--template", "classic", "--json"]
    render.main(argv)
    report = json.loads((out / "render_report.json").read_text())
    named = [d["message"] for d in report["defects"] if d["code"] in ("unsupported_tool", "unknown_skill")]
    assert not any("postgresql" in m.lower() for m in named), named
    assert any(w.startswith("related_tool: 'postgresql'") for w in report["warnings"])
    content["experience"][0]["bullets"][1]["text"] = "Built SQL views on Kubernetes for the finance team every month."
    write(src / "cv_content.json", json.dumps(content))
    render.main(argv)
    after = json.loads((out / "render_report.json").read_text())
    assert any("'kubernetes'" in d["message"] for d in after["defects"] if d["code"] == "unsupported_tool")




@pytest.mark.parametrize("asked, held, expected", [
    ("PostgreSQL", "SQL on Azure and AWS", "sql"),
    ("GitLab CLI", "GitHub and gh every day", "github"),
    ("Angular", "React and Next.js", ""),          # another paradigm is never one family
    ("SQL", "SQL", ""),                            # held itself: direct evidence, not a relation
])
def test_tool_families(asked, held, expected):
    assert render.jc.related_held(asked, held) == expected


def test_a_failed_render_never_leaves_a_stale_pdf(tmp_path, no_engine):
    out = tmp_path / "out"
    out.mkdir()
    (out / "cv_ats.pdf").write_bytes(b"%PDF-1.4 old render\n")
    (out / "CV_Ana_Example.pdf").write_bytes(b"%PDF-1.4 old render\n")
    render_cv_case(tmp_path)
    assert not (out / "cv_ats.pdf").exists()
    assert not list(out.glob("CV_*.pdf")), "the named upload copy of a failed render is gone too"


def test_cut_removes_the_lowest_relevance_bullet_and_keeps_protected_ones(tmp_path, fake_engine):
    fake_engine(lambda html_text: 2 if html_text.count("<li>") > 6 else 1)
    content = cv_content()
    content["experience"][0]["bullets"] = [
        {"text": f"Delivered reporting item {i} for the regional sales team across three units every week, "
                 "keeping the figures consistent.", "achievements": ["ACH-008"]}
        for i in range(1, 7)
    ]
    content["experience"][0]["bullets"].append({"text": "Automated the weekly report with Power BI for sales.",
                                                "achievements": ["ACH-007"], "keep": True})
    _, report, out = render_cv_case(tmp_path, content, extra=["--pages", "1"], analysis={
        "requirements": {"keywords": ["Power BI"], "tools": ["Power BI"]}})
    assert report["pages_actual"] == 1
    assert len(report["cuts"]) >= 1
    assert all(cut["score"] <= 0.5 for cut in report["cuts"])
    txt = (out / "cv_ats.txt").read_text(encoding="utf-8")
    assert "Automated the weekly report with Power BI" in txt  # keep:true survives the cut


def test_cut_candidate_prefers_the_low_relevance_shared_claim(tmp_path):
    raw = cv_content()
    raw["experience"][0]["bullets"] = [
        {"text": "Automated reporting with Power BI for sales.", "achievements": ["ACH-007"]},
        {"text": "Maintained legacy models for planning.", "achievements": ["ACH-009"]},
    ]
    raw["experience"][1]["bullets"] = [
        {"text": "Participated in the migration of legacy reports.", "achievements": ["ACH-009"]},
        {"text": "Documented the legacy formulas for handover.", "achievements": ["ACH-008"]},
    ]
    work = render.normalise_cv(raw, None)
    best = render.cut_candidate(work, ["Power BI"], set())
    _, job_index, bullet_index, score = best
    assert score == pytest.approx(0.15)
    assert work["experience"][job_index]["bullets"][bullet_index]["text"].startswith(("Maintained", "Participated"))


def test_pages_mismatch_is_a_defect_under_the_flag(tmp_path, fake_engine):
    fake_engine(lambda html_text: 1)
    _, report, _ = render_cv_case(tmp_path, extra=["--pages", "2"])
    assert "pages_mismatch" in codes(report)


def test_keyword_coverage_names_the_missing_terms(tmp_path, no_engine):
    _, report, _ = render_cv_case(tmp_path)
    assert "dbt" in report["missing_keywords"]
    assert report["keyword_coverage"] == pytest.approx(0.75)


def test_docx_absence_is_a_warning_and_never_a_defect(tmp_path, no_engine, monkeypatch):
    real_find_spec = render.importlib.util.find_spec
    monkeypatch.setattr(render.importlib.util, "find_spec",
                        lambda name, *a, **k: None if name == "docx" else real_find_spec(name, *a, **k))
    _, report, _ = render_cv_case(tmp_path)
    assert "docx_missing" not in codes(report)
    assert any(w.startswith("docx_skipped") for w in report["warnings"])
    assert report["engines"]["docx"] == "none"


def test_unknown_template_is_a_usage_error(tmp_path):
    with pytest.raises(SystemExit) as caught:
        render.main(["--content", "x.json", "--output", str(tmp_path), "--template", "nope"])
    assert caught.value.code == 2


def test_missing_input_is_exit_two(tmp_path):
    assert render.main(["--content", str(tmp_path / "absent.json"), "--output", str(tmp_path)]) == 2


# --- templates -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["classic", "compact", "modern"])
def test_templates_are_single_column_ats_safe_html(name):
    text = (TEMPLATES / f"{name}.html").read_text(encoding="utf-8")
    assert "{{CONTENT}}" in text and "<!DOCTYPE html>" in text
    for banned in ("<table", "<img", "<svg", "column-count", "display: grid", "display:grid", "display: flex",
                   "display:flex", "float:", "<iframe", "<object"):
        assert banned not in text, f"{name}.html uses {banned!r}"


@pytest.mark.parametrize("name", ["classic", "compact", "modern"])
def test_every_template_renders_the_same_content_without_leftover_tokens(tmp_path, no_engine, name):
    _, report, out = render_cv_case(tmp_path, template=name)
    html_text = (out / "cv_ats.html").read_text(encoding="utf-8")
    assert "{{" not in html_text
    assert report["template"] == name
    assert "Ana Example" in html_text and "Example Co" in html_text


def test_template_tokens_in_user_text_are_never_expanded(tmp_path, no_engine):
    content = cv_content(summary={"text": "Writes {{TITLE}} and {{CONTENT}} in reports.",
                                  "achievements": ["ACH-007"]})
    _, _, out = render_cv_case(tmp_path, content)
    html_text = (out / "cv_ats.html").read_text(encoding="utf-8")
    assert "{{TITLE}}" in html_text and "{{CONTENT}}" in html_text


# --- cover letter ----------------------------------------------------------------------------------------------------

LETTER = """\
---
language: en
---
# Cover letter

Dear Hiring Team,

Your posting asks for a reporting analyst who can own the weekly numbers. I have automated that report already. <!-- achievements: ACH-007 -->

I would start by moving the monthly ledger close onto the SQL views I built for finance. <!-- achievements: ACH-008 -->

- Owned weekly reporting with Python and Power BI <!-- achievements: ACH-007 -->
- Built SQL views the finance team uses each month <!-- achievements: ACH-008 -->

Motivation: your product team publishes its numbers openly, which suits how I work. <!-- achievements: none -->

Kind regards,
Ana Example
"""


def test_letter_parses_salutation_citations_list_and_closing():
    parsed = render.parse_letter(LETTER)
    assert parsed["salutation"] == "Dear Hiring Team,"
    assert parsed["closing_lines"] == ["Kind regards,", "Ana Example"]
    assert [p["achievements"] for p in parsed["paragraphs"][:2]] == [["ACH-007"], ["ACH-008"]]
    assert parsed["paragraphs"][2]["items"] == ["Owned weekly reporting with Python and Power BI",
                                                "Built SQL views the finance team uses each month"]
    assert parsed["paragraphs"][3]["no_claim"] is True
    assert all("<!--" not in p["text"] for p in parsed["paragraphs"])


def test_letter_uncited_paragraph_is_a_defect_and_none_is_accepted(tmp_path, no_engine):
    letter = write(tmp_path / "letter.md", LETTER + "\nI am a fast learner who would love to join.\n")
    out = tmp_path / "out"
    code = render.main(["--kind", "letter", "--content", str(letter), "--output", str(out),
                        "--template", "compact", "--json"])
    report = json.loads((out / "render_report_letter.json").read_text(encoding="utf-8"))
    assert code == 1
    found = codes(report)
    assert "uncited_claim" in found and "style_cliche" in found
    assert report["page_budget"] == 1
    txt = (out / "letter_ats.txt").read_text(encoding="utf-8")
    assert "Dear Hiring Team," in txt and "Kind regards," in txt and "<!--" not in txt


@pytest.mark.parametrize("name", ["classic", "compact", "modern"])
def test_letter_renders_in_each_template(tmp_path, no_engine, name):
    letter = write(tmp_path / "letter.md", LETTER)
    out = tmp_path / name
    render.main(["--kind", "letter", "--content", str(letter), "--output", str(out), "--template", name,
                 "--achievements", str(write(tmp_path / "a.yaml", ACHIEVEMENTS)), "--json"])
    report = json.loads((out / "render_report_letter.json").read_text(encoding="utf-8"))
    assert report["kind"] == "letter" and report["template"] == name
    assert (out / "letter_ats.html").read_text(encoding="utf-8").count("class=\"body\"") >= 2
    assert "uncited_claim" not in codes(report) and "unverified_achievement" not in codes(report)


# --- PDF checks ------------------------------------------------------------------------------------------------------

def test_normalize_text_folds_typography_and_whitespace():
    assert verify_pdf.normalize_text("Master\u2019s \u2013 degree\u00a0now") == "Master's - degree now"


@pytest.mark.parametrize("line, flagged", [
    ("Analyst 2016\u20132024", True),
    ("Mar 2016 \u2013 Jul 2016", True),
    ("2016 \u2013 Present", True),
    ("03/2016\u201307/2024", True),
    ("2019\u201320 season", True),
    ("EUR 1500\u20132000 budget", False),
    ("2000\u20135000 requests/s", False),
    ("EUR 600k\u20131M", False),
    ("Analyst 2016-2024", False),
])
def test_ascii_date_check_reads_the_raw_layer(line, flagged):
    assert bool(verify_pdf.find_non_ascii_date_ranges(line)) is flagged


def test_verify_pdf_skips_cleanly_without_an_extractor(tmp_path):
    pdf = make_pdf(tmp_path / "cv.pdf", [full_page()])
    env_python = sys.executable
    probe = (
        "import runpy, sys\n"
        "class Block:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name.split('.')[0] == 'pypdf':\n"
        "            raise ModuleNotFoundError('blocked', name=name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "sys.argv = sys.argv[1:]\n"
        "runpy.run_path(sys.argv[0], run_name='__main__')\n"
    )
    proc = subprocess.run([env_python, "-I", "-c", probe, str(SCRIPTS / "verify_pdf.py"), str(pdf)],
                          capture_output=True, text=True, env={"PATH": ""}, timeout=60)
    assert proc.returncode == 2
    assert "skipped:" in proc.stderr


@needs_poppler
def test_verify_pdf_passes_and_fails_on_the_text_layer(tmp_path):
    pdf = make_pdf(tmp_path / "cv.pdf", [[(40, "Ana Example"), (54, "Master\u2019s in Industrial Engineering"),
                                          (68, "Analyst 2016\u20132024")]])
    ok = verify_pdf.verify(pdf, pages=1, contains=["Ana Example", "Master's in Industrial Engineering"])
    assert ok["failures"] == [] and ok["pages"] == 1
    dumped = tmp_path / "dump.txt"
    verify_pdf.verify(pdf, dump_text=dumped)
    assert "2016\u20132024" in dumped.read_text(encoding="utf-8")  # the raw layer keeps the en dash
    bad = verify_pdf.verify(pdf, pages=2, contains=["Not on the page"], ascii_dates=True)
    assert len(bad["failures"]) == 3
    assert any("date range joined by U+2013" in f for f in bad["failures"])


@needs_poppler
def test_verify_pdf_command_exit_codes(tmp_path):
    pdf = make_pdf(tmp_path / "cv.pdf", [[(40, "Ana Example")]])
    ok = subprocess.run([sys.executable, str(SCRIPTS / "verify_pdf.py"), str(pdf), "--pages", "1",
                         "--contains", "Ana Example"], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stderr
    wrong = subprocess.run([sys.executable, str(SCRIPTS / "verify_pdf.py"), str(pdf), "--pages", "3"],
                           capture_output=True, text=True)
    assert wrong.returncode == 1 and "expected 3 page(s)" in wrong.stderr


# --- layout checks ---------------------------------------------------------------------------------------------------

def line(top, left=72.0, height=10.0, text="Line of text"):
    return verify_layout.Line(top=top, bottom=top + height, left=left, height=height, text=text)


def test_layout_clean_pages_report_no_problem():
    pages = [verify_layout.Page(842, [line(t) for t in range(40, 661, 14)]) for _ in range(2)]
    assert verify_layout.report(Path("clean.pdf"), pages) == []


def test_layout_reports_a_hole_over_100pt():
    page = verify_layout.Page(842, [line(40), line(60), line(260)])
    problems = verify_layout.report(Path("hole.pdf"), [page])
    assert any("hole" in p for p in problems)


def test_layout_reports_an_early_page_end_and_a_thin_last_page():
    early = verify_layout.Page(842, [line(t) for t in range(40, 301, 14)])
    full = verify_layout.Page(842, [line(t) for t in range(40, 661, 14)])
    problems = verify_layout.report(Path("early.pdf"), [early, full])
    assert any("ends" in p and "early" in p for p in problems)
    thin = verify_layout.Page(842, [line(40)])
    problems = verify_layout.report(Path("thin.pdf"), [full, thin])
    assert any("unfinished" in p for p in problems)


def test_layout_reports_a_stranded_heading_and_a_split_entry():
    heading = verify_layout.Page(842, [line(t) for t in range(40, 644, 14)] + [line(656, height=20, text="EXPERIENCE")])
    problems = verify_layout.report(Path("heading.pdf"), [heading, verify_layout.Page(842, [line(40)])])
    assert any("heading" in p for p in problems)
    job = verify_layout.Page(842, [line(t) for t in range(40, 650, 14)] + [line(656, left=72, text="Data analyst")])
    nxt = verify_layout.Page(842, [line(40, left=90, text="Built the SQL views")])
    problems = verify_layout.report(Path("split.pdf"), [job, nxt])
    assert any("bullets resume" in p for p in problems)


@needs_poppler
def test_layout_flags_a_thin_last_page_in_a_real_pdf(tmp_path):
    pdf = make_pdf(tmp_path / "thin.pdf", [full_page(), [(40, "Only line")]])
    proc = subprocess.run([sys.executable, str(SCRIPTS / "verify_layout.py"), str(pdf)], capture_output=True,
                          text=True)
    assert proc.returncode == 1
    assert "unfinished" in proc.stdout


def test_layout_skips_without_poppler(tmp_path):
    pdf = make_pdf(tmp_path / "any.pdf", [full_page()])
    proc = subprocess.run([sys.executable, str(SCRIPTS / "verify_layout.py"), str(pdf)], capture_output=True,
                          text=True, env={"PATH": ""}, timeout=60)
    assert proc.returncode == 2
    assert "skipped:" in proc.stderr


@needs_chrome
@needs_poppler
def test_real_chrome_render_is_measured_and_checked(tmp_path):
    code, report, out = render_cv_case(tmp_path, extra=["--pages", "1", "--engine", "chromium"])
    assert report["engines"]["pdf"] == "chromium"
    assert report["pages_actual"] == 1 and report["page_method"] == "measured"
    pdf = out / "cv_ats.pdf"
    assert verify_pdf.verify(pdf, pages=1, contains=["Ana Example"], ascii_dates=True)["failures"] == []
    proc = subprocess.run([sys.executable, str(SCRIPTS / "verify_layout.py"), str(pdf)], capture_output=True,
                          text=True)
    assert proc.returncode == 0, proc.stdout


# --- the skill contracts ---------------------------------------------------------------------------------------------

# Base64 so that this file never contains the foreign names it guards against.
_ENCODED_TRACES = (
    "Y2xhdWRl", "YW50aHJvcGlj", "bWFkcw==", "bG9yZW50emVu", "YWktam9iLXNlYXJjaA==", "ZGFuaXNo", "ZGVubWFyaw==",
    "ZGFuc2s=", "am9iaW5kZXg=", "am9ibmV0", "am9iYmFuaw==", "am9iZGFubWFyaw==", "bGF0ZXg=", "bW9kZXJuY3Y=",
    "bHVhbGF0ZXg=", "eGVsYXRleA==", "bm90aW9u", "Q0xBVURFLm1k", "ZnJhbWV3b3JrX3ZlcnNpb24=", "LmNsYXVkZQ==",
    "L2FwcGx5", "L3NjcmFwZQ==", "L3NldHVw", "L2ludGVydmlldw==", "L291dGNvbWU=", "L2FkZC10ZW1wbGF0ZQ==",
)


def test_document_skills_carry_no_foreign_traces():
    import base64

    traces = [base64.b64decode(t).decode() for t in _ENCODED_TRACES]
    slash = [t for t in traces if t.startswith("/")]  # slash commands only at the start of a token, never in a path
    words = [t for t in traces if not t.startswith("/")]
    pattern = re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(t) for t in words) + r")(?![\w-])"
                         r"|(?:^|[\s`\"'(])(?:" + "|".join(re.escape(t) for t in slash) + r")(?![\w-])",
                         re.I | re.M)
    checked = 0
    for skill in DOC_SKILLS:
        for path in (SKILLS / skill).rglob("*"):
            if path.is_file() and path.suffix in {".md", ".py", ".json", ".html", ".yaml", ".txt"} \
                    and "__pycache__" not in path.parts:
                checked += 1
                hit = pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
                assert hit is None, f"{path.relative_to(REPO)} contains {hit.group(0)!r}"
    assert checked > 20


def test_each_document_skill_has_three_evals_and_the_procedure_sections():
    for skill in DOC_SKILLS:
        base = SKILLS / skill
        evals = json.loads((base / "evals" / "evals.json").read_text(encoding="utf-8"))["evals"]
        assert len(evals) == 3
        text = (base / "SKILL.md").read_text(encoding="utf-8")
        for heading in ("## When to Use", "## Procedure", "## Pitfalls", "## Verification"):
            assert heading in text
        assert len(text.splitlines()) <= 120


def test_reference_files_stay_within_the_size_budget():
    for skill in DOC_SKILLS:
        for ref in (SKILLS / skill / "references").glob("*.md") if (SKILLS / skill / "references").is_dir() else []:
            lines = ref.read_text(encoding="utf-8").splitlines()
            assert len(lines) <= 200, ref.name
            if len(lines) > 100:
                assert any(re.match(r"#{1,6}\s*contents\s*$", ln, re.I) for ln in lines[:20]), ref.name
