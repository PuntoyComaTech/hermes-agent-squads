# Templates, engines and defect codes

## Contents

- Templates
- PDF engines
- Defect codes
- Warning codes

## Templates

Three ATS-safe HTML templates ship in `templates/`. Choose one with `--template`; the default is `classic`.

| Template | Use when | Look |
|---|---|---|
| classic | The default for most markets and stages | Serif type, a rule under each section heading |
| compact | The content is long and the page budget is tight | Sans-serif, smaller type, tighter spacing |
| modern | Digital and product roles where a light accent helps | Sans-serif, one accent colour on headings |

Every template follows the same rules: one column; no tables, columns, images, text boxes or background graphics; plain
list bullets; a name as `h1`, sections as `h2`, entries as `h3`; selectable text; no page break inside a list item and
none directly after a heading.

A template is an HTML file with four placeholders: `{{LANG}}`, `{{TITLE}}`, `{{PAGE_SIZE}}` and the content slot
`{{CONTENT}}`. The renderer fills them in one pass, so user text is never expanded a second time.

A project template (Mode: TEMPLATE, `custom-templates.md`) is named with `--project <P> --template <name>` and renders
only with a passing gate record. A project template with a shipped name (classic, compact, modern) takes
precedence over the shipped one; the gate warns about it.

Page size: `Letter` for the countries in `market.country` that use it (US, CA, MX, PH); `A4` otherwise.

## PDF engines

- WeasyPrint (a Python package, detected by an import check) is tried first under `--engine auto`.
- Chromium or Google Chrome (`--headless=new --print-to-pdf`) is the fallback. Each run uses a fresh profile directory.
- With neither, the HTML and text are still written, `engine_missing` is a defect, and the report says
  `page_method: estimate`.
- `--engine weasyprint` or `--engine chromium` forces one engine. A forced engine that is absent is a defect, never a
  silent switch.
- python-docx writes `cv.docx` (or `letter.docx`) when installed. Otherwise a `docx_skipped` warning says so and the
  PDF and text still count: DOCX is optional.

## Defect codes

| Code | Meaning | Fix |
|---|---|---|
| uncited_claim | A bullet, summary, project or letter paragraph cites no achievement | Add the ids; or `none` for a letter motivation paragraph |
| unverified_achievement | A cited id is missing from achievements.yaml or not verified | Remove the claim, or get the user's confirmation first |
| language_undeclared | A CV language is not declared in achievements.yaml | Declare it with its level, or drop it |
| language_level_raised | A CV shows a CEFR level above the declared one | Show the declared level |
| style_em_dash | An em dash in a text | Rewrite with a comma, period or colon |
| style_cliche | A cliche or a profile avoid_phrases match | Rewrite the sentence |
| stage_requirement | A returning CV has no career_gap line | Write the honest gap line |
| unknown_employer | An employer is not in achievements.yaml experiences | Use a recorded employer, or ask the user to add it |
| title_mismatch | A job title differs from the recorded title for that employer | Use the recorded title |
| date_mismatch | A date range differs from the recorded from/to | Use the recorded dates |
| unknown_education | A degree, institution or year is not in achievements.yaml education | Use the recorded entry |
| unknown_skill, unknown_skill_level | A skill or tool is in neither the achievements nor the profile; a level is not a recorded proficiency | Remove it, or record it with the user's OK |
| unsupported_number | A number differs from the cited achievement's numbers, or a headline number is in no source | Use the record's number |
| unsupported_tool | A technology named in a claim (fixed list, posting tools, CamelCase names) is in no source | Remove it, or record it with the user's OK |
| unsupported_claim | A degree of another level or field, or an ownership verb with no cited achievement recorded as led | Match the level and field in education, or cite the led achievement |
| title_mismatch | The headline matches no experience title or target role | Use a title the experience or profile holds |
| unsupported_claim | A letter names a company, school or degree that no source holds | Remove it; cite a source |
| private_data | Age, date of birth, marital status, photo or nationality in any text | Remove it; never print it |
| page_budget_exceeded | Measured pages above budget and nothing left to cut | Tighten the wording first; a template change is the user's decision |
| pages_mismatch | Measured pages differ from the `--pages` flag | Adjust content or design; never fake the count |
| engine_missing, pdf_failed | No engine, or the engine failed | Install or fix the engine; quote the message in the card |

## Warning codes (advice, not failures)

- Bullet word count outside 12 to 22.
- A keyword repeated more than three times (stuffing).
- Letter body over 300 words; a letter with no closing line.
- No heading table for the language; an unknown `candidate.stage`.
- `photo_in_cv` set (no photo is ever rendered).
- Pages estimated, not measured.
- Achievement ids or language levels not checked (no `--achievements`).
- A career_change CV without transferable skills; a senior summary without a number.
- A project template whose PDF gate was not run at registration; a manifest page limit that shrinks the budget.
- `docx_skipped`: python-docx absent or failed to import (DOCX is optional).
- `--template` differs from the profile's `cv_template`: refused (exit 2) unless the user said yes and
  `--template-override-by-user` is passed.
- A number, employer or tool that could not be checked (no experiences, skills or achievement text in the sources).
