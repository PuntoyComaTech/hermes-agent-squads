"""Custom templates: the ATS and layout gate (template_check.py) and the project template lookup in render_cv.py.

Fixtures are fictional (Jordan Example, Example Co). Every check runs the real scripts as subprocesses, except the
no-engine path, which is forced in-process so it is deterministic on any machine. Tests that need Chrome or Poppler
skip cleanly when they are absent: a skip is not a pass, and the tests say so.
"""
from __future__ import annotations

import html as html_lib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "squads" / "jobs" / "skills" / "rendering-cv" / "scripts"
TEMPLATES = REPO / "squads" / "jobs" / "skills" / "rendering-cv" / "templates"
TOOL_TIMEOUT = 600


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # dataclasses looks the module up while the class is built
    spec.loader.exec_module(module)
    return module


tc = load("template_check_under_test", SCRIPTS / "template_check.py")
rc = load("render_cv_templates_under_test", SCRIPTS / "render_cv.py")

HAS_CHROME = rc.chromium_binary() is not None
HAS_WEASYPRINT = rc.weasyprint_available()
HAS_POPPLER = bool(shutil.which("pdftotext") and shutil.which("pdfinfo"))
needs_chrome = pytest.mark.skipif(not HAS_CHROME, reason="no Chromium or Google Chrome binary: PDF gate not run")
needs_no_weasyprint = pytest.mark.skipif(HAS_WEASYPRINT, reason="WeasyPrint is installed: it would be the engine")

# --- fictional fixtures ----------------------------------------------------------------------------------------------

CLEAN = """<!DOCTYPE html>
<html lang="{{LANG}}">
<head>
<meta charset="utf-8">
<title>{{TITLE}}</title>
<style>
@page { size: {{PAGE_SIZE}}; margin: 15mm 17mm; }
html { font-family: Arial, Helvetica, sans-serif; font-size: 10pt; line-height: 1.35; color: #1a1a1a; }
body { margin: 0; }
h1.name { font-size: 20pt; line-height: 1.15; margin: 0 0 2pt; }
p.contact, p.links { margin: 0 0 4pt; font-size: 9pt; }
h2 { font-size: 12pt; margin: 10pt 0 3pt; break-after: avoid; page-break-after: avoid; }
h3 { font-size: 10pt; margin: 6pt 0 0; font-weight: bold; break-after: avoid; page-break-after: avoid; }
p.dates, p.url { margin: 0 0 2pt; font-size: 9pt; }
p { margin: 0 0 4pt; }
ul { margin: 0 0 4pt; padding-left: 14pt; }
li { margin: 0 0 2pt; break-inside: avoid; page-break-inside: avoid; }
.letter p.body { margin-bottom: 8pt; }
.letter p.salutation, .letter p.closing { margin-top: 10pt; }
.letter p.signature { margin: 0; }
</style>
</head>
<body>
{{CONTENT}}
</body>
</html>
"""

PROFILE = """---
candidate:
  stage: mid
market:
  country: US
  cv_page_limit: 2
writing_style: {tone: direct, formality: medium}
---
# Jordan Example
"""
PROFILE_NO_LIMIT = "---\nmarket: {country: US}\n---\n# Jordan Example\n"

ACHIEVEMENTS = """achievements:
  - {id: ACH-001, proficiency: did, verified: true}
  - {id: ACH-002, proficiency: built, verified: true}
  - {id: ACH-003, proficiency: did, verified: true}
languages:
  - {language: english, level: B2, verified: true}
experiences:
  - {id: EXP-001, title: "Data analyst", company: "Example Co", from: 2022-03, to: current}
  - {id: EXP-002, title: "Analyst", company: "Sample Works", from: 2019-01, to: 2022-02}
skills:
  - {name: SQL, proficiency: did, achievements: [ACH-001]}
  - {name: Python, proficiency: did, achievements: [ACH-001]}
  - {name: Power BI, proficiency: built, achievements: [ACH-002]}
education:
  - {id: EDU-001, degree: "Industrial Engineering", institution: "Example University", year: 2018, verified: true}
"""

CONTACT = ('name: "Jordan Example"\nemail: "jordan@example.com"\nphone: "+1 555 010 0100"\n'
           'location: "Springfield"\nlinks: []\n')

BULLETS = [
    "Automated the weekly sales report with Python and SQL, cutting run time from six hours to twenty minutes.",
    "Built a Power BI dashboard that the finance team uses to close the monthly ledger without manual extracts.",
    "Documented the reporting pipeline so two colleagues could maintain it during leave periods.",
    "Maintained legacy reports for three business units and moved them to a shared folder.",
]

CV = {
    "language": "en",
    "header": {"name": "Jordan Example", "headline": "Data analyst, reporting automation"},
    "summary": {"text": "Data analyst with four years of reporting automation for small finance teams.",
                "achievements": ["ACH-001"]},
    "experience": [
        {"title": "Data analyst", "company": "Example Co", "dates": "2022-03 - current", "bullets": [
            {"text": BULLETS[0], "achievements": ["ACH-001"]},
            {"text": BULLETS[1], "achievements": ["ACH-002"]},
            {"text": BULLETS[2], "achievements": ["ACH-003"]},
        ]},
        {"title": "Analyst", "company": "Sample Works", "dates": "2019-01 - 2022-02", "bullets": [
            {"text": BULLETS[3], "achievements": ["ACH-003"]},
        ]},
    ],
    "skills": [{"name": "SQL", "level": "did"}, {"name": "Python", "level": ""}],
    "education": [{"degree": "Industrial Engineering", "institution": "Example University", "year": "2018"}],
    "languages": [{"language": "english", "level": "B2"}],
}

LETTER = """Dear Hiring Manager,

I analyse sales reporting for small teams, and I want to bring that work to your data group. <!-- achievements: none -->

At Example Co I automated the weekly sales report with Python and SQL, which cut run time from six hours to twenty minutes. <!-- achievements: ACH-001 -->

Kind regards,
Jordan Example
"""


def page(css: str = "", content: str = "{{CONTENT}}", head: str = "") -> str:
    """The clean single-column template, with extra CSS, body content and head markup spliced in."""
    out = CLEAN.replace("</style>", css + "\n</style>", 1)
    out = out.replace("<head>\n", "<head>\n" + head, 1)
    return out.replace("{{CONTENT}}", content, 1)


def write(folder: Path, html: str, name: str = "mine", manifest=None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.html"
    path.write_text(html, encoding="utf-8")
    if manifest is not None:
        text = manifest if isinstance(manifest, str) else json.dumps(manifest)
        (folder / f"{name}.json").write_text(text, encoding="utf-8")
    return path


def run_tool(script: str, *args, timeout: int = TOOL_TIMEOUT):
    return subprocess.run([sys.executable, "-I", str(SCRIPTS / script), *map(str, args)], capture_output=True,
                          text=True, timeout=timeout)


def gate(path: Path, *args, smoke: bool = False):
    """template_check.py as a user runs it. (exit code, JSON report or None, process)."""
    extra = [] if smoke else ["--no-smoke"]
    proc = run_tool("template_check.py", path, "--json", *extra, *args)
    report = json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else None
    return proc.returncode, report, proc


def failed(report: dict, check: str) -> list:
    return [f["message"] for f in report["failures"] if f["check"] == check]


def visible(html_text: str) -> str:
    """The reading order an applicant tracking system sees: the tags dropped, the entities decoded."""
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", html_text)).split())


def fixture_inputs(folder: Path, profile: str = PROFILE) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    paths = {"profile": folder / "profile.md", "achievements": folder / "achievements.yaml",
             "contact": folder / "contact.yaml", "content": folder / "cv_content.json",
             "letter": folder / "cover_letter.md"}
    paths["profile"].write_text(profile, encoding="utf-8")
    paths["achievements"].write_text(ACHIEVEMENTS, encoding="utf-8")
    paths["contact"].write_text(CONTACT, encoding="utf-8")
    paths["content"].write_text(json.dumps(CV, indent=1), encoding="utf-8")
    paths["letter"].write_text(LETTER, encoding="utf-8")
    return paths


def render(project: Path, template: str, inputs: dict, *extra, kind: str = "cv"):
    """render_cv.py from the command line, the way the writer's card runs it. (process, report or None)."""
    out = project / "out"
    content = inputs["content"] if kind == "cv" else inputs["letter"]
    proc = run_tool("render_cv.py", "--kind", kind, "--content", content, "--output", out,
                    "--profile", inputs["profile"], "--achievements", inputs["achievements"],
                    "--contact", inputs["contact"], "--project", project, "--template", template, "--json", *extra)
    report_file = out / ("render_report.json" if kind == "cv" else "render_report_letter.json")
    report = json.loads(report_file.read_text(encoding="utf-8")) if report_file.is_file() else None
    return proc, report


def register_args(*extra) -> list:
    """--register needs the PDF gate. Without an engine the record says so, and only --allow-unmeasured accepts it."""
    return ["--register", *([] if HAS_CHROME else ["--allow-unmeasured"]), *extra]


# --- scripts and help ------------------------------------------------------------------------------------------------

def test_template_check_answers_help_and_render_cv_has_no_gate_bypass():
    proc = run_tool("template_check.py", "--help")
    assert proc.returncode == 0, proc.stderr
    for flag in ("--kind", "--no-smoke", "--require-pdf", "--register", "--allow-unmeasured", "--json"):
        assert flag in proc.stdout
    help_text = rc.build_parser().format_help()
    assert "--project" in help_text and "--templates-dir" in help_text
    for flag in ("--skip-gate", "--no-gate", "--allow-unverified", "--force-template"):
        assert flag not in help_text


# --- static gate: passes -----------------------------------------------------------------------------------------------

def test_clean_single_column_template_passes_the_static_gate(tmp_path):
    path = write(tmp_path, page(), manifest={"kind": "cv", "page_limit": 2, "notes": "fictional probe"})
    code, report, proc = gate(path)
    assert code == 0, proc.stdout + proc.stderr
    assert report["verdict"] == "pass" and report["failures"] == []
    assert all(v == "pass" for v in report["checks"].values())
    assert report["fingerprint"] and report["kind"] == "cv"


def test_data_url_font_and_a_small_contact_line_are_allowed(tmp_path):
    css = ('@font-face { font-family: "Probe"; src: url(data:font/woff2;base64,AAAA) format("woff2"); }\n'
           "p.contact { font-size: 8pt; }\n")
    code, report, proc = gate(write(tmp_path, page(css)), "--kind", "cv")
    assert code == 0, proc.stdout


@pytest.mark.parametrize("name", ["classic", "compact", "modern"])
@pytest.mark.parametrize("kind", ["cv", "letter"])
def test_every_shipped_template_passes_the_static_gate(name, kind):
    code, report, proc = gate(TEMPLATES / f"{name}.html", "--kind", kind)
    assert code == 0, proc.stdout
    assert report["failures"] == []


# --- static gate: the ATS rejections -----------------------------------------------------------------------------------

TWO_COLUMN_CASES = {
    "flex sidebar": (
        "", '<div style="display: flex; gap: 12pt"><aside style="width: 28%">Skills and tools</aside>'
            '<main style="flex: 1">{{CONTENT}}</main></div>'),
    "grid sidebar": (
        ".wrap { display: grid; grid-template-columns: 28% 1fr; }",
        '<div class="wrap"><aside>Skills and tools</aside><main>{{CONTENT}}</main></div>'),
    "grid areas": (
        '.wrap { display: grid; grid-template-areas: "side main"; }',
        '<div class="wrap"><aside>Skills</aside><main>{{CONTENT}}</main></div>'),
    "floated sidebar": (
        ".side { float: left; width: 28%; }", '<aside class="side">Skills and tools</aside>{{CONTENT}}'),
    "css columns": (".body { column-count: 2; }", '<div class="body">{{CONTENT}}</div>'),
}


@pytest.mark.parametrize("label", sorted(TWO_COLUMN_CASES))
def test_a_two_column_template_is_rejected_for_the_ats_reading_order(tmp_path, label):
    css, content = TWO_COLUMN_CASES[label]
    code, report, proc = gate(write(tmp_path, page(css, content)), "--kind", "cv")
    assert code == 1, proc.stdout
    messages = failed(report, "multi_column") + failed(report, "float_layout")
    assert messages and all("two columns scramble ATS reading order" in m for m in messages), messages
    assert report["smoke"]["ran"] is False  # a failed static gate never reaches the render


def test_a_template_that_loads_google_fonts_is_rejected_as_an_external_request(tmp_path):
    head = '<link href="https://fonts.googleapis.com/css2?family=Inter" rel="stylesheet">\n'
    code, report, proc = gate(write(tmp_path / "link", page(head=head)), "--kind", "cv")
    assert code == 1
    assert any("fonts.googleapis.com" in m for m in failed(report, "external_requests"))

    code, report, _ = gate(write(tmp_path / "import", page('@import url("https://fonts.example.org/x.css");')),
                           "--kind", "cv")
    assert code == 1 and failed(report, "external_requests")


def test_a_local_font_file_is_rejected_because_the_output_folder_does_not_hold_it(tmp_path):
    css = '@font-face { font-family: "Probe"; src: url(fonts/probe.woff2); }'
    code, report, _ = gate(write(tmp_path, page(css)), "--kind", "cv")
    assert code == 1
    assert failed(report, "local_references")


def test_contact_shown_only_as_icons_is_rejected(tmp_path):
    content = ('<p class="contact"><i class="fa fa-envelope"></i> <i class="fa fa-phone"></i> '
               '<i class="fa fa-map-marker"></i></p>\n{{CONTENT}}')
    code, report, _ = gate(write(tmp_path / "icons", page(content=content)), "--kind", "cv")
    assert code == 1
    assert any("contact only as icons" in m for m in failed(report, "contact_text"))

    anchored = ('<p class="contact"><a href="mailto:jordan@example.com"><i class="fa fa-envelope"></i></a></p>'
                "\n{{CONTENT}}")
    code, report, _ = gate(write(tmp_path / "anchor", page(content=anchored)), "--kind", "cv")
    assert code == 1 and failed(report, "contact_text")


def test_contact_icon_beside_its_text_passes(tmp_path):
    content = '<p class="contact"><i class="fa fa-envelope"></i> jordan@example.com</p>\n{{CONTENT}}'
    code, report, proc = gate(write(tmp_path, page(content=content)), "--kind", "cv")
    assert code == 0, proc.stdout


def test_a_contact_line_hidden_by_css_is_rejected(tmp_path):
    code, report, _ = gate(write(tmp_path, page("p.contact { display: none; }")), "--kind", "cv")
    assert code == 1 and failed(report, "contact_text")


@pytest.mark.parametrize("label, css, content, check", [
    ("table", "", "<table><tr><td>Skills</td></tr></table>{{CONTENT}}", "no_tables"),
    ("table layout by css", ".grid { display: table; }", '<div class="grid">{{CONTENT}}</div>', "no_tables"),
    ("image", "", '<img src="data:image/png;base64,AAAA" alt="logo">{{CONTENT}}', "images"),
    ("svg", "", '<svg width="10" height="10"></svg>{{CONTENT}}', "images"),
    ("script", "", "<script>document.title = 'x';</script>{{CONTENT}}", "scripts"),
    ("inline handler", "", '<p onclick="go()">{{CONTENT}}</p>', "scripts"),
    ("absolute text", ".stamp { position: absolute; top: 0; }", '<p class="stamp">Mark</p>{{CONTENT}}',
     "absolute_position"),
    ("background image", ".band { background-image: url(data:image/png;base64,AAAA); }",
     '<div class="band">{{CONTENT}}</div>', "background_images"),
    ("generated text", 'h2::before { content: "Section "; }', "{{CONTENT}}", "generated_text"),
    ("body text at 8pt", "p { font-size: 8pt; }", "{{CONTENT}}", "body_font_size"),
])
def test_ats_hazards_are_rejected_with_their_check(tmp_path, label, css, content, check):
    code, report, proc = gate(write(tmp_path, page(css, content)), "--kind", "cv")
    assert code == 1, f"{label}: {proc.stdout}"
    assert failed(report, check), f"{label}: expected {check}, got {report['failures']}"


def test_body_text_exactly_at_nine_points_passes_and_metadata_may_go_to_seven(tmp_path):
    css = "p { font-size: 9pt; } p.dates { font-size: 7pt; }"
    code, _, proc = gate(write(tmp_path, page(css)), "--kind", "cv")
    assert code == 0, proc.stdout


# --- placeholders, manifest and name ---------------------------------------------------------------------------------

def test_placeholders_are_required_exact_and_single(tmp_path):
    code, report, _ = gate(write(tmp_path / "none", page(content="Static text only")), "--kind", "cv")
    assert code == 1 and any("missing {{CONTENT}}" in m for m in failed(report, "placeholders"))

    code, report, _ = gate(write(tmp_path / "typo", page(content="{{CONTENT}}<p>{{NAME}}</p>")), "--kind", "cv")
    assert code == 1 and any("unknown placeholder {{NAME}}" in m for m in failed(report, "placeholders"))

    code, report, _ = gate(write(tmp_path / "twice", page(content="{{CONTENT}}{{CONTENT}}")), "--kind", "cv")
    assert code == 1 and any("appears 2 times" in m for m in failed(report, "placeholders"))


@pytest.mark.parametrize("manifest, message", [
    ({"kind": "cv", "page_limit": 5}, "page_limit 5 must be 1, 2 or 3"),
    ({"kind": "banana"}, "kind 'banana' is not cv or letter"),
    ("{not json", "is not valid JSON"),
    ({"kind": "letter"}, "says kind letter, the check was run with kind cv"),
])
def test_a_bad_manifest_is_a_manifest_failure(tmp_path, manifest, message):
    code, report, _ = gate(write(tmp_path, page(), manifest=manifest), "--kind", "cv")
    assert code == 1
    assert any(message in m for m in failed(report, "manifest")), report["failures"]


def test_unknown_manifest_keys_are_warned_not_failed(tmp_path):
    code, report, _ = gate(write(tmp_path, page(), manifest={"kind": "cv", "colour": "red"}), "--kind", "cv")
    assert code == 0 and any("colour" in w for w in report["warnings"])


def test_a_template_name_must_be_lowercase_kebab_case(tmp_path):
    code, report, _ = gate(write(tmp_path, page(), name="My_Template"), "--kind", "cv")
    assert code == 1 and failed(report, "name")


def test_a_personal_email_written_into_the_template_is_warned_not_failed(tmp_path):
    content = '<p>Write to jordan@example.com</p>\n{{CONTENT}}'
    code, report, proc = gate(write(tmp_path, page(content=content)), "--kind", "cv")
    assert code == 0, proc.stdout
    assert any("jordan@example.com" in w and "contact.yaml" in w for w in report["warnings"])


def test_a_project_template_named_like_a_shipped_one_is_warned(tmp_path):
    code, report, proc = gate(write(tmp_path, page(), name="classic"), "--kind", "cv")
    assert code == 0
    assert any("shadows the shipped template" in w for w in report["warnings"])


def test_a_missing_kind_is_a_usage_error_and_a_missing_file_is_exit_two(tmp_path):
    proc = run_tool("template_check.py", write(tmp_path, page()), "--no-smoke")
    assert proc.returncode == 2 and "no kind" in proc.stderr
    proc = run_tool("template_check.py", tmp_path / "absent.html", "--no-smoke")
    assert proc.returncode == 2 and "template not found" in proc.stderr


def test_register_without_the_render_smoke_is_a_usage_error(tmp_path):
    proc = run_tool("template_check.py", write(tmp_path, page()), "--kind", "cv", "--no-smoke", "--register")
    assert proc.returncode == 2


# --- render smoke (real engine) --------------------------------------------------------------------------------------

@needs_chrome
def test_clean_cv_template_passes_the_pdf_and_layout_gates(tmp_path):
    code, report, proc = gate(write(tmp_path, page()), "--kind", "cv", smoke=True)
    assert code == 0, proc.stdout + proc.stderr
    assert report["smoke"]["ran"] is True and report["smoke"]["pdf_engine"] == "chromium"
    assert report["pdf_gate"] == "pass"
    assert report["checks"]["pdf_text"] == "pass" and report["checks"]["layout"] == "pass"


@needs_chrome
def test_clean_letter_template_passes_the_smoke_with_the_letter_fixture(tmp_path):
    path = write(tmp_path, page(), manifest={"kind": "letter", "page_limit": 1})
    code, report, proc = gate(path, smoke=True)
    assert code == 0, proc.stdout + proc.stderr
    assert report["kind"] == "letter" and report["pdf_gate"] == "pass"


@needs_chrome
def test_the_smoke_render_keeps_its_fixture_when_asked(tmp_path):
    keep = tmp_path / "kept"
    code, report, _ = gate(write(tmp_path / "t", page()), "--kind", "cv", "--keep-smoke", str(keep), smoke=True)
    assert code == 0
    text = (keep / "out" / "cv_ats.txt").read_text(encoding="utf-8")
    assert "Jordan Example" in text and BULLETS[0] in text


@needs_no_weasyprint
def test_forced_engine_that_is_absent_skips_the_pdf_gate_and_never_passes_it(tmp_path):
    path = write(tmp_path, page())
    code, report, proc = gate(path, "--kind", "cv", "--engine", "weasyprint", smoke=True)
    assert code == 0, proc.stdout
    assert report["pdf_gate"] == "skipped" and report["smoke"]["render"] == "pass"
    assert "no PDF engine" in report["smoke"]["pdf_reason"]
    code, report, proc = gate(path, "--kind", "cv", "--engine", "weasyprint", "--require-pdf", smoke=True)
    assert code == 1 and failed(report, "pdf_gate")


def test_without_any_engine_the_pdf_gate_is_skipped_in_process(tmp_path, monkeypatch):
    engine = tc.render_module()
    monkeypatch.setattr(engine, "chromium_binary", lambda: None)
    monkeypatch.setattr(engine, "weasyprint_available", lambda: False)
    path = write(tmp_path, page())
    report = tc.check_template(path, "cv")
    assert report["verdict"] == "pass" and report["pdf_gate"] == "skipped"
    assert report["checks"]["render_smoke"] == "pass"
    strict = tc.check_template(path, "cv", require_pdf=True)
    assert strict["verdict"] == "fail" and strict["checks"]["pdf_gate"] == "fail"


def test_a_skipped_verifier_is_not_a_pass_or_a_failure():
    failures: list = []
    skipped = subprocess.CompletedProcess(args=[sys.executable, str(tc.VERIFY_PDF)], returncode=2, stdout="",
                                          stderr="skipped: no extractor: install pypdf or Poppler\n")
    assert tc.verifier_outcome(skipped, "pdf_text", failures) == ("skipped", "no extractor: install pypdf or Poppler")
    broken = subprocess.CompletedProcess(args=[sys.executable, str(tc.VERIFY_LAYOUT)], returncode=1, stdout="",
                                         stderr="fail: text layer is missing 'Jordan Example'\n")
    assert tc.verifier_outcome(broken, "pdf_text", failures) == ("fail", None)
    assert failures == [{"check": "pdf_text", "message": "text layer is missing 'Jordan Example'"}]


# --- registration: the record and the project lookup -----------------------------------------------------------------

@needs_chrome
def test_a_passing_template_registers_and_a_failing_one_leaves_no_record(tmp_path):
    path = write(tmp_path, page(), name="mine", manifest={"kind": "cv", "page_limit": 1})
    code, report, proc = gate(path, "--kind", "cv", "--register", smoke=True)
    assert code == 0, proc.stdout + proc.stderr
    record = json.loads((tmp_path / "mine.gate.json").read_text(encoding="utf-8"))
    assert record["verdict"] == "pass" and record["kind"] == "cv"
    assert record["fingerprint"] == rc.template_fingerprint(path)
    assert record["gates"]["pdf"] == "pass"

    sidebar = write(tmp_path, page(TWO_COLUMN_CASES["flex sidebar"][0], TWO_COLUMN_CASES["flex sidebar"][1]),
                    name="mine")
    code, _, _ = gate(sidebar, "--kind", "cv", "--register", smoke=True)
    assert code == 1
    assert not (tmp_path / "mine.gate.json").exists(), "a failed registration must remove the old record"


def test_project_template_is_used_by_name_and_renders_every_bullet_in_reading_order(tmp_path):
    project = tmp_path / "P"
    write(project / "templates", page(), name="mine", manifest={"kind": "cv", "page_limit": 1, "notes": "probe"})
    proc = run_tool("template_check.py", project / "templates" / "mine.html", "--kind", "cv", "--register",
                    *([] if HAS_CHROME else ["--allow-unmeasured"]), "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    inputs = fixture_inputs(tmp_path / "in")
    proc, report = render(project, "mine", inputs)
    assert report is not None, proc.stderr
    # python-docx and a PDF engine are environment, not template faults: anything else must be absent.
    environment = {"docx_missing"} if HAS_CHROME else {"docx_missing", "engine_missing"}
    assert {d["code"] for d in report["defects"]} <= environment, json.dumps(report["defects"])
    assert report["template"] == "mine" and report["template_source"] == "project"
    assert report["template_gate"] == {"static": "pass", "render": "pass", "pdf": report["template_gate"]["pdf"]}
    assert report["page_budget"] == 1 and report["page_budget_source"] == "template"  # profile 2, template 1

    text = visible((project / "out" / "cv_ats.html").read_text(encoding="utf-8"))
    assert "Jordan Example" in text
    positions = [text.find(b) for b in BULLETS]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions), "bullets must read in document order"
    if HAS_CHROME:
        assert (project / "out" / "cv_ats.pdf").read_bytes().startswith(b"%PDF")


def test_a_letter_project_template_renders_the_salutation_and_the_closing(tmp_path):
    project = tmp_path / "P"
    write(project / "templates", page(), name="letter-mine", manifest={"kind": "letter", "page_limit": 1})
    proc = run_tool("template_check.py", project / "templates" / "letter-mine.html", "--kind", "letter",
                    *register_args(), "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    inputs = fixture_inputs(tmp_path / "in")
    proc, report = render(project, "letter-mine", inputs, kind="letter")
    assert report is not None and report["template_source"] == "project"
    text = visible((project / "out" / "letter_ats.html").read_text(encoding="utf-8"))
    assert "Dear Hiring Manager," in text and "Kind regards," in text and "Jordan Example" in text


def test_a_project_template_without_a_passing_gate_is_refused(tmp_path):
    project = tmp_path / "P"
    write(project / "templates", page(), name="mine")
    proc, report = render(project, "mine", fixture_inputs(tmp_path / "in"))
    assert proc.returncode == 2 and report is None
    assert "has not passed the ATS and layout gates" in proc.stderr


def test_a_template_edited_after_it_passed_is_refused_until_it_registers_again(tmp_path):
    project = tmp_path / "P"
    path = write(project / "templates", page(), name="mine", manifest={"kind": "cv"})
    assert run_tool("template_check.py", path, "--kind", "cv", *register_args(), "--json").returncode == 0
    path.write_text(path.read_text(encoding="utf-8") + "<!-- edited after the gate -->\n", encoding="utf-8")
    proc, report = render(project, "mine", fixture_inputs(tmp_path / "in"))
    assert proc.returncode == 2 and "changed after it passed the gates" in proc.stderr


def test_the_gate_record_is_per_kind(tmp_path):
    project = tmp_path / "P"
    path = write(project / "templates", page(), name="mine")
    assert run_tool("template_check.py", path, "--kind", "letter", *register_args(), "--json").returncode == 0
    proc, _ = render(project, "mine", fixture_inputs(tmp_path / "in"))
    assert proc.returncode == 2 and "passed the gates as letter, not cv" in proc.stderr


def test_a_pdf_gate_not_run_at_registration_is_warned_on_every_render(tmp_path):
    project = tmp_path / "P"
    write(project / "templates", page(), name="mine", manifest={"kind": "cv"})
    proc = run_tool("template_check.py", project / "templates" / "mine.html", "--kind", "cv", "--engine",
                    "weasyprint", "--allow-unmeasured", "--register", "--json")
    if HAS_WEASYPRINT:
        pytest.skip("WeasyPrint is installed: the forced engine would pass the PDF gate")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads((project / "templates" / "mine.gate.json").read_text())["gates"]["pdf"] == "skipped"
    _, report = render(project, "mine", fixture_inputs(tmp_path / "in"))
    assert any("PDF gate was not run at registration" in w for w in report["warnings"])


def test_manifest_page_limit_sets_the_budget_when_the_profile_has_none(tmp_path):
    project = tmp_path / "P"
    write(project / "templates", page(), name="mine", manifest={"kind": "cv", "page_limit": 3})
    proc = run_tool("template_check.py", project / "templates" / "mine.html", "--kind", "cv", *register_args(),
                    "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    inputs = fixture_inputs(tmp_path / "in", profile=PROFILE_NO_LIMIT)
    _, report = render(project, "mine", inputs)
    assert report["page_budget"] == 3 and report["page_budget_source"] == "template"


def test_unknown_and_unsafe_template_names_are_usage_errors(tmp_path):
    project = tmp_path / "P"
    project.mkdir()
    inputs = fixture_inputs(tmp_path / "in")
    proc, _ = render(project, "nope", inputs)
    assert proc.returncode == 2 and "unknown template 'nope'" in proc.stderr
    proc, _ = render(project, "../escape", inputs)
    assert proc.returncode == 2 and "is not valid" in proc.stderr


def test_a_shipped_template_still_renders_without_a_project(tmp_path):
    inputs = fixture_inputs(tmp_path / "in")
    proc, report = render(tmp_path / "bare", "modern", inputs)
    assert report is not None and report["template_source"] == "shipped" and report["template_gate"] is None
    assert "Jordan Example" in (tmp_path / "bare" / "out" / "cv_ats.html").read_text(encoding="utf-8")


# --- verifier output stays in the report's words ---------------------------------------------------------------------

def test_verifier_check_names_match_the_gate_checks():
    assert set(tc.STATIC_CHECKS) <= {"name", "manifest", "placeholders", "no_tables", "images", "scripts",
                                     "external_requests", "local_references", "multi_column", "float_layout",
                                     "absolute_position", "generated_text", "background_images", "contact_text",
                                     "body_font_size"}
    assert tc.VERIFY_PDF.is_file() and tc.VERIFY_LAYOUT.is_file() and tc.RENDER.is_file()
