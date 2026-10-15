#!/usr/bin/env python3
"""Render a CV content file to the files an application submits, and report defects.

Usage:
  render_cv.py --content application/cv_content.json --output application [options]

Writes into --output:
  cv_ats.html        one-column, ATS-safe HTML (always)
  cv_ats.txt         plain text in reading order (always)
  cv_ats.pdf         when weasyprint or Chromium is available (--engine picks one)
  cv.docx            when python-docx is available
  render_report.json pages, keyword coverage, links, defects and the engines used

cv_content.json shape: skill rendering-cv.

Exit codes: 0 clean, 1 the report holds defects, 2 usage or input error. No network.
"""
from __future__ import annotations

import argparse
import html
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

HEADINGS = {
    "en": {"summary": "Summary", "experience": "Experience", "projects": "Projects", "skills": "Skills",
           "education": "Education", "languages": "Languages"},
    "es": {"summary": "Perfil", "experience": "Experiencia", "projects": "Proyectos", "skills": "Habilidades",
           "education": "Formación", "languages": "Idiomas"},
}
CHROMIUM_CANDIDATES = (
    "chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)


class InputError(Exception):
    pass


# --- text helpers -----------------------------------------------------------------------------------------------

def norm(text: str) -> str:
    """Lowercase, accent-free, punctuation-light: the ATS comparison alphabet."""
    flat = unicodedata.normalize("NFKD", text.lower())
    flat = "".join(c for c in flat if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9+#.]+", " ", flat)


def headings(language: str) -> dict:
    return HEADINGS.get((language or "en").lower()[:2], HEADINGS["en"])


def fit(content: dict) -> tuple[str, dict]:
    language = str(content.get("language") or "en")
    return language, headings(language)


# --- plain text and HTML ---------------------------------------------------------------------------------------

def header_block(content: dict) -> tuple[str, str, str, list[str]]:
    h = content.get("header") or {}
    name = str(h.get("name") or "").strip()
    headline = str(h.get("headline") or "").strip()
    contact = " · ".join(str(x).strip() for x in (h.get("email"), h.get("phone"), h.get("location")) if x)
    links = [str(x).strip() for x in (h.get("links") or []) if x]
    return name, headline, contact, links


def render_txt(content: dict) -> str:
    language, words = fit(content)
    name, headline, contact, links = header_block(content)
    lines = [name, headline, contact, " · ".join(links), ""]
    if content.get("summary"):
        lines += [words["summary"].upper(), str(content["summary"]).strip(), ""]
    if content.get("experience"):
        lines += [words["experience"].upper()]
        for job in content["experience"]:
            lines.append(f"{job.get('title', '')} — {job.get('company', '')} ({job.get('dates', '')})".strip())
            lines += [f"- {b.get('text', '')}" for b in job.get("bullets") or []]
            lines.append("")
    if content.get("projects"):
        lines += [words["projects"].upper()]
        for p in content["projects"]:
            lines.append(f"{p.get('name', '')} — {p.get('url', '')}".strip(" —"))
            if p.get("text"):
                lines.append(str(p["text"]).strip())
        lines.append("")
    if content.get("skills"):
        lines += [words["skills"].upper(),
                  ", ".join(f"{s.get('name', '')} ({s.get('level')})" if s.get("level") else str(s.get("name", ""))
                            for s in content["skills"]), ""]
    if content.get("education"):
        lines += [words["education"].upper(),
                  "\n".join(f"{e.get('degree', '')}, {e.get('institution', '')} ({e.get('year', '')})"
                            for e in content["education"]), ""]
    if content.get("languages"):
        lines += [words["languages"].upper(),
                  ", ".join(f"{l.get('language', '')}: {l.get('level', '')}" for l in content["languages"]), ""]
    return "\n".join(lines).strip() + "\n"


def render_html(content: dict) -> str:
    language, words = fit(content)
    name, headline, contact, links = header_block(content)
    out = ['<!DOCTYPE html>', f'<html lang="{html.escape(language[:2])}">', "<head>", '<meta charset="utf-8">',
           f"<title>{html.escape(' '.join(x for x in (name, headline) if x) or 'CV')}</title>", "<style>",
           "body{font-family:Helvetica,Arial,sans-serif;font-size:10.5pt;line-height:1.35;color:#111;margin:0}",
           "h1{font-size:16pt;margin:0 0 2pt}h2{font-size:11pt;margin:12pt 0 4pt;text-transform:uppercase}",
           "p{margin:0 0 4pt}ul{margin:0 0 6pt;padding-left:16pt}li{margin:0 0 2pt}a{color:#111}",
           "</style>", "</head>", "<body>"]

    def p(text: str) -> str:
        return f"<p>{html.escape(str(text))}</p>"

    out.append(f"<h1>{html.escape(name)}</h1>")
    if headline:
        out.append(p(headline))
    if contact:
        out.append(p(contact))
    if links:
        out.append("<p>" + " · ".join(f'<a href="{html.escape(u)}">{html.escape(u)}</a>' for u in links) + "</p>")
    if content.get("summary"):
        out += [f"<h2>{words['summary']}</h2>", p(str(content["summary"]))]
    if content.get("experience"):
        out.append(f"<h2>{words['experience']}</h2>")
        for job in content["experience"]:
            out.append(f"<p><strong>{html.escape(str(job.get('title', '')))}</strong> — "
                       f"{html.escape(str(job.get('company', '')))}, {html.escape(str(job.get('dates', '')))}</p>")
            bullets = [f"<li>{html.escape(str(b.get('text', '')))}</li>" for b in job.get("bullets") or []]
            if bullets:
                out.append("<ul>" + "".join(bullets) + "</ul>")
    if content.get("projects"):
        out.append(f"<h2>{words['projects']}</h2>")
        for proj in content["projects"]:
            label = html.escape(str(proj.get("name", "")))
            url = str(proj.get("url") or "")
            out.append(p(f"{label} — {url}" if url else label))
            if proj.get("text"):
                out.append(p(str(proj["text"])))
    if content.get("skills"):
        out += [f"<h2>{words['skills']}</h2>",
                p(", ".join(str(s.get("name", "")) + (f" ({s['level']})" if s.get("level") else "")
                            for s in content["skills"]))]
    if content.get("education"):
        out.append(f"<h2>{words['education']}</h2>")
        for edu in content["education"]:
            out.append(p(f"{edu.get('degree', '')}, {edu.get('institution', '')} ({edu.get('year', '')})"))
    if content.get("languages"):
        out += [f"<h2>{words['languages']}</h2>",
                p(", ".join(f"{l.get('language', '')}: {l.get('level', '')}" for l in content["languages"]))]
    out.append("</body></html>")
    return "\n".join(out) + "\n"


# --- optional engines ------------------------------------------------------------------------------------------

def weasyprint_available() -> bool:
    return importlib.util.find_spec("weasyprint") is not None


def chromium_binary() -> str | None:
    for candidate in CHROMIUM_CANDIDATES:
        found = shutil.which(candidate) or (candidate if Path(candidate).is_file() else None)
        if found:
            return found
    return None


def pdf_pages(path: Path) -> int | None:
    if not shutil.which("pdfinfo"):
        return None
    try:
        out = subprocess.run(["pdfinfo", str(path)], capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return int(match.group(1)) if match else None


def render_pdf(html_text: str, html_path: Path, pdf_path: Path, engine: str, defects: list[dict]) -> tuple[str, int | None]:
    """(engine used, page count). A missing engine is a defect, never a crash."""
    if engine in ("auto", "weasyprint") and weasyprint_available():
        try:
            from weasyprint import HTML  # imported late: --help must not need it
            document = HTML(filename=str(html_path)).render()
            document.write_pdf(str(pdf_path))
            return "weasyprint", len(document.pages)
        except Exception as exc:  # noqa: BLE001 - the report carries the reason
            defects.append({"code": "pdf_failed", "message": f"weasyprint: {type(exc).__name__}: {exc}"[:300]})
            return "none", None
    if engine == "weasyprint":
        defects.append({"code": "engine_missing",
                        "message": "weasyprint is not installed: pip install weasyprint (ask the builder)"})
        return "none", None
    binary = chromium_binary()
    if binary:
        try:
            subprocess.run([binary, "--headless=new", "--disable-gpu", "--no-sandbox", "--no-pdf-header-footer",
                            f"--print-to-pdf={pdf_path.resolve()}", html_path.resolve().as_uri()],
                           capture_output=True, text=True, timeout=180, check=True)
            return "chromium", pdf_pages(pdf_path)
        except (OSError, subprocess.SubprocessError) as exc:
            defects.append({"code": "pdf_failed", "message": f"chromium: {exc}"[:300]})
            return "none", None
    defects.append({"code": "engine_missing",
                    "message": "no PDF engine: install weasyprint (pip) or Chromium/Chrome, then re-run"})
    return "none", None


def render_docx(content: dict, path: Path, defects: list[dict]) -> str:
    if importlib.util.find_spec("docx") is None:
        defects.append({"code": "docx_missing",
                        "message": "python-docx is not installed: pip install python-docx (ask the builder)"})
        return "none"
    try:
        from docx import Document  # imported late
    except Exception as exc:  # noqa: BLE001
        defects.append({"code": "docx_missing", "message": f"python-docx failed to import: {exc}"[:300]})
        return "none"
    language, words = fit(content)
    name, headline, contact, links = header_block(content)
    doc = Document()

    def heading(text: str, level: int = 2) -> None:
        try:
            doc.add_heading(text, level=level)
        except Exception:  # noqa: BLE001 - a template without heading styles still gets the text
            doc.add_paragraph(text)

    doc.add_heading(name or "CV", level=0)
    for line in (headline, contact, " · ".join(links)):
        if line:
            doc.add_paragraph(line)
    if content.get("summary"):
        heading(words["summary"])
        doc.add_paragraph(str(content["summary"]))
    if content.get("experience"):
        heading(words["experience"])
        for job in content["experience"]:
            doc.add_paragraph(f"{job.get('title', '')} — {job.get('company', '')}, {job.get('dates', '')}")
            for bullet in job.get("bullets") or []:
                try:
                    doc.add_paragraph(str(bullet.get("text", "")), style="List Bullet")
                except Exception:  # noqa: BLE001
                    doc.add_paragraph(f"- {bullet.get('text', '')}")
    if content.get("projects"):
        heading(words["projects"])
        for proj in content["projects"]:
            doc.add_paragraph(f"{proj.get('name', '')} — {proj.get('url', '')}".strip(" —"))
            if proj.get("text"):
                doc.add_paragraph(str(proj["text"]))
    if content.get("skills"):
        heading(words["skills"])
        doc.add_paragraph(", ".join(str(s.get("name", "")) for s in content["skills"]))
    if content.get("education"):
        heading(words["education"])
        for edu in content["education"]:
            doc.add_paragraph(f"{edu.get('degree', '')}, {edu.get('institution', '')} ({edu.get('year', '')})")
    if content.get("languages"):
        heading(words["languages"])
        doc.add_paragraph(", ".join(f"{l.get('language', '')}: {l.get('level', '')}" for l in content["languages"]))
    doc.save(str(path))
    return "python-docx"


# --- report ----------------------------------------------------------------------------------------------------

def keyword_report(cv_text: str, analysis: dict) -> tuple[float | None, list[str]]:
    keywords = [str(k) for k in ((analysis.get("requirements") or {}).get("keywords") or []) if str(k).strip()]
    if not keywords:
        return None, []
    haystack = norm(cv_text)
    missing = [k for k in keywords if norm(k) not in haystack]
    return round((len(keywords) - len(missing)) / len(keywords), 4), missing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="render_cv.py", description=(__doc__ or "").split("\n\n")[0],
        epilog="Exit 0 clean, 1 defects, 2 usage or input error.", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--content", required=True, type=Path, help="cv_content.json")
    parser.add_argument("--output", required=True, type=Path, help="output directory (created if missing)")
    parser.add_argument("--analysis", type=Path, help="analysis.json; adds keyword coverage to the report")
    parser.add_argument("--pages", type=int, help="expected PDF page count; a mismatch is a defect")
    parser.add_argument("--engine", choices=("auto", "weasyprint", "chromium"), default="auto",
                        help="PDF engine (default auto: weasyprint, then Chromium)")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        content = json.loads(args.content.read_text(encoding="utf-8"))
        if not isinstance(content, dict):
            raise InputError(f"{args.content}: top level must be an object")
    except OSError as exc:
        print(f"error: cannot read {args.content}: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {args.content} is not valid JSON: {exc}", file=sys.stderr)
        return 2
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    analysis = {}
    if args.analysis:
        try:
            analysis = json.loads(args.analysis.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"error: cannot read {args.analysis}: {exc}", file=sys.stderr)
            return 2

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    defects: list[dict] = []
    warnings: list[str] = []

    text = render_txt(content)
    html_text = render_html(content)
    files = [str(out / "cv_ats.html"), str(out / "cv_ats.txt")]
    (out / "cv_ats.html").write_text(html_text, encoding="utf-8")
    (out / "cv_ats.txt").write_text(text, encoding="utf-8")

    pdf_path = out / "cv_ats.pdf"
    engine, pages = render_pdf(html_text, out / "cv_ats.html", pdf_path, args.engine, defects)
    if engine != "none":
        files.append(str(pdf_path))
    docx_engine = render_docx(content, out / "cv.docx", defects)
    if docx_engine != "none":
        files.append(str(out / "cv.docx"))

    if args.pages is not None:
        if pages is None and engine != "none":
            warnings.append("page count not measurable here (install poppler for pdfinfo); --pages not enforced")
        elif pages is not None and pages != args.pages:
            defects.append({"code": "pages_mismatch",
                            "message": f"{pages} pages rendered, {args.pages} expected: adjust the content or design"})

    coverage, missing = keyword_report(text, analysis)
    report = {
        "content": str(args.content), "output": str(out), "language": str(content.get("language") or "en"),
        "files": files, "engines": {"pdf": engine, "docx": docx_engine},
        "pages_expected": args.pages, "pages_actual": pages,
        "selectable_text": None if engine == "none" else True,
        "reading_order_ok": True,  # one renderer, one linear section order for HTML, PDF and text
        "links": header_block(content)[3],
        "keyword_coverage": coverage, "missing_keywords": missing,
        "defects": defects, "warnings": warnings,
    }
    (out / "render_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"rendered {len(files)} files into {out} (pdf: {engine}, docx: {docx_engine})")
        for defect in defects:
            print(f"defect {defect['code']}: {defect['message']}")
        for warning in warnings:
            print(f"warning: {warning}")
        if coverage is not None:
            print(f"keyword coverage {coverage:.1%}" + (f", missing: {', '.join(missing)}" if missing else ""))
    return 1 if defects else 0


if __name__ == "__main__":
    sys.exit(main())
