---
name: rendering-cv
description: "Renders a CV or letter to PDF, DOCX and ATS text. Use when cv_content.json or cover_letter.md is ready and the application needs its files and a defects report."
---

# Rendering the CV

Deterministic rendering: `cv_content.json` or `cover_letter.md` in; the files an application submits, a checked text
layer and `render_report.json` out. Run the scripts. Never edit them.

## When to Use

- After `cv_content.json` or `cover_letter.md` exists (NEW, CORRECTION or CHANGE card), before the reviewer's card.
- When the card needs the page count, keyword coverage, stretch flags or the layout check.

## Procedure

1. Render the CV. `<P>` is the project folder named in your card.

   ```bash
   python3 "$HERMES_HOME/skills/squad-jobs/rendering-cv/scripts/render_cv.py" \
     --content <P>/openings/<ID>/application/cv_content.json \
     --output <P>/openings/<ID>/application --analysis <P>/openings/<ID>/analysis.json \
     --profile <P>/profile.md --achievements <P>/achievements.yaml --contact <P>/contact.yaml \
     --letter <P>/openings/<ID>/application/cover_letter.md --project <P> --template <T> --json
   ```

   `<T>` is `profile.md -> cv_template` (default `classic`). A different template is refused (exit 2) unless the user
   said yes; after that yes, add `--template-override-by-user`. Never add it on your own.
   Add `--pages N` only when the card sets an exact count. `--template` picks the design: `classic|compact|modern`, or a
   registered project template name with `--project <P>` (Mode: TEMPLATE; `references/templates-and-budget.md`). `--engine` forces a PDF engine; `--no-fit` turns off cutting; `--help`
   lists everything.
2. Render the cover letter: the same command with `--kind letter --content <P>/openings/<ID>/application/cover_letter.md`.
   It writes `letter_ats.html`, `letter_ats.txt`, `letter_ats.pdf` and `letter.docx`.
3. Check the PDFs. `verify_pdf.py` reads the text layer as an applicant tracking system does; `verify_layout.py`
   reads the page geometry:

   ```bash
   python3 "$HERMES_HOME/skills/squad-jobs/rendering-cv/scripts/verify_pdf.py" <pdf> --pages <N> --ascii-dates \
     --contains "<name as printed>" --dump-text <dir>/cv_ats.txt
   python3 "$HERMES_HOME/skills/squad-jobs/rendering-cv/scripts/verify_layout.py" <pdf>
   ```

   Exit 2 with `skipped:` means the check did not run. Say so in the card; it is not a pass.
4. Read `render_report.json`: `defects`, `pages_actual` against `page_budget`, `cuts`, `stretch_flags`,
   `keyword_coverage` and `missing_keywords`. Quote its numbers in the card; never estimate them.
5. Fix and re-run, at most three attempts in total. Change the wording or the template before anything else. Never
   change a fact. A keyword no achievement supports stays missing and is recorded as a gap.
6. A missing engine or package is never installed by you. Write the install line in the card summary: `pip install
   weasyprint python-docx pypdf`, and Poppler for `pdfinfo`, `pdftotext` and `-bbox`.

## Mode: TEMPLATE

The user brings their own CV or letter design, as an HTML file, a description or a screenshot. It becomes a project
template only after the ATS and layout gate passes. Full procedure: `references/custom-templates.md`.

1. The writer (or the manager, when the user drops a file) saves the design as `<P>/templates/<name>.html`, with
   `<name>.json` beside it: `{"kind": "cv" | "letter", "page_limit": 1-3}`. Never write it into the skill folder.
2. Gate it. This is deterministic; run it, do not reason about the file:

   ```bash
   python3 "$HERMES_HOME/skills/squad-jobs/rendering-cv/scripts/template_check.py" <P>/templates/<name>.html \
     --kind cv --register --json
   ```

3. Exit 0: the template is registered and renders with `--project <P> --template <name>`. Exit 1: quote each
   `fail [check]` line in the card, fix the HTML, re-run. Three attempts in total, then stop and report.
4. `pdf_gate: skipped` means no PDF engine: `--register` then needs `--allow-unmeasured`, and every render says the
   layout was not verified. Say so in the card; it is not a pass.
5. A registered template that is edited again is refused by render_cv.py until the gate runs again.

## Pitfalls

- Never edit `cv_content.json` to raise keyword coverage with a claim no achievement supports.
- Never remove bullets by hand to meet the budget. The renderer cuts the lowest relevance-weighted bullet first, and
  lists every cut. A bullet marked `keep` is not removed.
- The renderer refuses (exit 1) an employer, title, date, number, degree, skill or tool that `achievements.yaml` or
  `profile.md` does not hold, a number that differs from the cited achievement, and personal data (age, marital
  status, date of birth, photo, nationality). Fix the wording or the citation; never weaken a source.
- A missing source list is a defect, never a pass: a degree, skill or employer with no education, skills or
  experiences list in `achievements.yaml` blocks the render. Add the record, or remove the claim.
- A headline must match an experience title or a target role. Quantity words ('a third', 'doubled', 'half') are
  checked like digits. An ownership verb ('led', 'managed') needs a cited achievement recorded as led.
- A `page_budget_exceeded` defect is an overflow: tighten the wording first. A template change is a question to the
  user: the renderer refuses `--template` that differs from the profile unless `--template-override-by-user` is given.
- python-docx is optional. Without it the report carries a `docx_skipped` warning; the PDF and the text still count.
- Never ship a PDF from an earlier render. A failed render deletes the old PDF first; check the report's `files`.
- Without a PDF engine the page count is an estimate: the report says `page_method: estimate` and nothing is cut.
- Never register a template that fails a check, and never edit a registered template's `.gate.json` by hand.
- A user template lives in the project, never in the skill folder. Its name may match a shipped one; the gate warns.

## Verification

- `render_report.json` `files` matches what is on disk, and every required file is listed, including the upload copy
  `CV_<Name>_<Surname>.pdf` (byte-identical to `cv_ats.pdf`; contact.yaml `short_name` sets the name).
- `pages_actual` equals `pages_expected` when the card sets one, and is within `page_budget` otherwise.
- `verify_pdf.py` passes with `--ascii-dates` and the printed name; `verify_layout.py` reports clean, or the card lists
  each problem.
- Dates in the output are hyphen ranges (`2022-03 - current`).
