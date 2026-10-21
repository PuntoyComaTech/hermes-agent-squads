# Content schema

Inputs and outputs of `render_cv.py`. Keys not listed here are ignored, and unknown keys never fail a render.

## Contents

- cv_content.json
- cover_letter.md
- render_report.json

## cv_content.json

    {"language": "en",
     "header": {"name": "", "headline": "", "links": []},
     "summary": {"text": "", "achievements": ["ACH-001"]},
     "career_gap": "",
     "transferable_skills": [],
     "experience": [{"title": "", "company": "", "dates": "2022-03 - current",
                     "bullets": [{"text": "", "achievements": ["ACH-007"], "keep": false, "stretch": ""}]}],
     "projects": [{"name": "", "url": "", "text": "", "achievements": []}],
     "skills": [{"name": "SQL", "level": "did"}],
     "education": [{"degree": "", "institution": "", "year": "2021"}],
     "languages": [{"language": "english", "level": "B2"}]}

Notes:

- `summary` may be a plain string. A plain string has no citation, so it is reported as `uncited_claim`.
- `header.name`, `email`, `phone` and `location` are read from `contact.yaml` when absent here. The header never holds
  more than the contact file says.
- A bullet may be a plain string. It then has no citation and is reported as `uncited_claim`.
- `keep: true` protects a bullet from cutting. `stretch` holds the reason a bullet is flagged; leave it empty otherwise.
- Dates and years take hyphens. En or em dashes are converted to hyphens on render.
- `languages` levels must not exceed the level declared in `achievements.yaml`.
- Every employer, title, date range, number, degree, institution, skill and tool must match `achievements.yaml`
  (experiences, achievements, education, skills) or `profile.md`. A number must equal the cited achievement's number.
  A checked list missing from the source file is a warning, not a pass.
- `skills[].level` is optional: the recorded proficiency (led, did, participated, familiar).

## cover_letter.md

Markdown with an optional front matter block (`language: en`), one salutation paragraph starting with Dear, Hi, Estimado
or Hola, body paragraphs that each end with an achievement comment, an optional list block, and a closing block starting
with Kind regards, Best regards, Sincerely, Atentamente or Saludos cordiales, followed by the name line.

    Dear Hiring Team,

    Paragraph one. <!-- achievements: ACH-007 -->

    - Item one <!-- achievements: ACH-008 -->
    - Item two <!-- achievements: ACH-009 -->

    Kind regards,
    Ana Example

Lines starting with `#` are skipped. Pass the same file to `--letter` when rendering the CV: its citations then count as
narrative load when cutting, because the CV and the letter tell one story.

## render_report.json

Written on every run, including a run stopped by a defect. Keys:

| Key | Meaning |
|---|---|
| kind, template, language | what was rendered |
| market.country, market.paper | from the profile; Letter for US, CA, MX and PH; A4 otherwise |
| stage, section_order | the stage and the heading order that was used |
| files | every file written by the run that exists on disk |
| engines.pdf, engines.docx | `weasyprint`, `chromium`, `python-docx` or `none` |
| page_budget, page_budget_source | the budget and where it came from: flag, profile or default |
| pages_expected, pages_actual | the flag and the measured count (null when no engine can measure) |
| pages_estimated, page_method | an estimate when nothing can be measured; `measured` or `estimate` |
| cuts | bullets removed to meet the budget: section, job, text, score, rule |
| selectable_text, reading_order_ok | true when a PDF exists; one linear block order for HTML, PDF and text |
| links | header links |
| keyword_coverage, missing_keywords, keywords_total | share of analysis keywords and tools found in the text |
| stretch_flags | bullets to show the user: job, text, reason, question |
| defects | each as {code, message}; any defect makes the exit code 1 |
| warnings | advice that does not fail the render |

Exit codes: 0 clean, 1 defects present (the report and the files are still written), 2 bad input or usage.
