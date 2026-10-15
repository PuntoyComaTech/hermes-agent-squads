---
name: rendering-cv
description: "Renders cv_content.json to PDF, DOCX and ATS text. Use when a CV content file is ready and the application needs its rendered files and a defects report."
---

# Rendering the CV

Deterministic rendering: `cv_content.json` in, submit-ready files out, defects reported in `render_report.json`.
The script ships with this skill; never rewrite it, run it.

## When to Use

- After `cv_content.json` exists (NEW, CORRECTION or CHANGE card), before the reviewer's card.
- When you need page count, keyword coverage or the link list of the CV for the card summary.

## Procedure

1. Run the script (from the writer profile, `$HERMES_HOME` is that profile):

   ```bash
   python3 "$HERMES_HOME/skills/squad-jobs/rendering-cv/scripts/render_cv.py" \
     --content <P>/openings/<ID>/application/cv_content.json \
     --output <P>/openings/<ID>/application \
     --analysis <P>/openings/<ID>/analysis.json \
     --pages <expected pages>
   ```

   `--json` prints the report; `--engine weasyprint|chromium` forces one PDF engine; `--help` lists everything.
2. Files written to `--output`: `cv_ats.html` and `cv_ats.txt` always; `cv_ats.pdf` when WeasyPrint or Chromium is
   present; `cv.docx` when python-docx is present; `render_report.json` always. Exit 0 clean, 1 with defects
   (a missing engine is a defect), 2 usage error.
3. Read `render_report.json`: `defects`, `pages_actual` against `pages_expected`, `keyword_coverage` and
   `missing_keywords`. Quote its numbers in the card; never estimate them yourself.
4. A missing engine or package is never installed by you: write it in the card summary (`pip install weasyprint
   python-docx`, poppler for `pdfinfo`) so the builder or the user can do it.
5. Fix and re-run: at most 3 attempts. When space runs short, change the design, never a fact. A keyword no
   achievement supports stays missing and is recorded as a gap.

## cv_content.json shape

```json
{"language": "en",
 "header": {"name": "", "headline": "", "email": "", "phone": "", "location": "", "links": []},
 "summary": "",
 "experience": [{"title": "", "company": "", "dates": "", "bullets": [{"text": "", "achievements": ["ACH-007"]}]}],
 "projects": [{"name": "", "url": "", "text": ""}],
 "skills": [{"name": "", "level": ""}],
 "education": [{"degree": "", "institution": "", "year": 2021}],
 "languages": [{"language": "", "level": ""}]}
```

Section headings follow `language` (English and Spanish; anything else uses English). Contact fields come from
`contact.yaml` and appear only in the rendered files.

## Pitfalls

- Never edit `cv_content.json` to raise keyword coverage with a claim no achievement supports.
- Keep the ATS file one column, no icons, no tables, real clickable links: that is what the template renders.
- Never write contact data into a card, comment or file outside `application/`.
- The PDF is only as many pages as the renderer reports; do not guess from the source.

## Verification

- `render_report.json` -> `files` matches what is on disk; defects cover every file the card requires.
- `pages_actual` equals `pages_expected` when the card sets one.
- `cv_ats.txt` section order equals `cv_content.json` order.
- The reviewer's card quotes the report's numbers, not yours.
