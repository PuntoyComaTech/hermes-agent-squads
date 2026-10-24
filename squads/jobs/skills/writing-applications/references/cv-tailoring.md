# CV tailoring

The CV is one or two pages, one column, rebuilt for each opening from verified achievements. This file holds the rules
the writer applies before `render_cv.py` runs. The renderer enforces the mechanical ones; the rest is judgement.

## Contents

- Inputs and the claim boundary
- Stage structure
- Personal data and market conventions
- Headings and language
- Dates
- Bullets, keywords and stretch flags
- Tenure check
- Page budget and relevance-weighted cutting
- Cut order for hand edits

## Inputs and the claim boundary

- `achievements.yaml`: only `verified: true` records may be written. Reword a record for the posting without adding
  scope, and keep its proficiency.
- `profile.md` `candidate.stage` chooses the structure below. `market.cv_page_limit` (1 or 2) sets the budget.
  `market.conventions` decides what the market expects. `writing_style` sets tone.
- Languages in `achievements.yaml` carry a CEFR level. The CV shows the declared level only. A level is never raised.

## Stage structure

The renderer orders the sections from `candidate.stage`. The writer chooses content and emphasis.

| Stage | Section order | Emphasis |
|---|---|---|
| first_job | summary, education, projects, experience, skills, languages | Education and projects first; coursework, a capstone or a volunteer role carries the evidence |
| junior, mid, lead, unset | summary, experience, skills, projects, education, languages | Experience first; the most recent role has the most bullets |
| senior | summary, experience, skills, projects, education, languages | Scope and impact: team size, budget, users, decisions, with the numbers the record holds |
| career_change | summary, transferable skills, skills, experience, projects, education, languages | A transferable-skills block that maps past work to the posting's tasks |
| returning | summary, experience, skills, projects, education, languages | One honest line in the experience section about the gap (`career_gap`); never an unexplained blank period |

Sections with no content are skipped. A transferable-skills block the CV holds is kept even when the stage order does
not name it (it follows the order).

The renderer blocks a `returning` CV without a `career_gap` line (defect `stage_requirement`) and warns when a
`career_change` CV has no transferable skills.

## Personal data and market conventions

- Age: printed only when `candidate.include_age_in_cv: true` and `candidate.age` is set. Never inferred.
- Photo: never. The ATS templates carry no image; `photo_in_cv` only produces a warning.
- Marital status, date of birth, nationality, religion and similar data: never in a CV or letter, whatever the market.
  The renderer refuses them as `private_data`, in the headline, summary, bullets and letter.
- References: `market.conventions.references_line: true` adds a references line. Otherwise there is none.
- Contact fields come from `contact.yaml` only, and appear only in the rendered files.

## Headings and language

- Section headings follow the CV language. English and Spanish are built in. Translate every heading, including
  "Transferable skills" and the references line, not only the prose.
- A language without a heading table renders English headings and a warning. Add the table to the renderer; do not
  work around it in the content.
- Write the content in the CV language. A French CV is written in French, not English with a French heading.

## Dates

- Write every date range with one ASCII hyphen: `2022-03 - current`, `2016-2024`. An en dash in a date is the most
  common silent failure in an applicant tracking system import, because the parser splits on the hyphen and loses the
  date. The renderer converts dashes in date fields to hyphens; the writer still types hyphens.
- Every experience entry shows a start and an end (or "current"). Never invent a start date.
- In-progress education says so inside the entry, in the year field: "2025-2026 (in progress, expected Dec 2026)".
  A bare closed range reads as a finished degree.
- Check every date against the `experiences` list in `achievements.yaml`.

## Bullets, keywords and stretch flags

- Each bullet: strong verb, what, for whom, result. 12 to 22 words. One idea. Cite the achievement ids in
  `achievements`.
- Use a posting's core term in a bullet only when it is true for that work. An exact term beats a synonym for ATS
  matching; a synonym that changes the meaning is not allowed.
- Keywords come from `analysis.requirements.keywords` and `tools`. A keyword with no achievement behind it stays
  missing and is recorded as a gap. The renderer reports `keyword_coverage` and `missing_keywords`. A term repeated more
  than three times is a warning (stuffing).
- Stretch flags: a bullet that opens with an ownership verb (led, managed, built, owned, launched and similar) and cites
  an achievement recorded as `participated` or `familiar` is flagged. Reword it to the recorded proficiency before the
  review ("participated in", "contributed to") and note it in the card; ask the user only when no truthful wording keeps
  the bullet.

## Tenure check

Read each role the way a stranger reads it: the date span against the visible output. A long span with one project
reads as low output. Three honest fixes, in order:

1. Surface more real work the record holds: secondary projects, tooling, support.
2. Make the phases explicit: learning or supporting first, then ownership through delivery.
3. Name what made the cycle long: data collection, validation with experts, deployment against real output.

Never pad with invented projects and never shorten the employment dates. If the gap remains, the interview pack gets a
two-part answer (see preparing-interviews).

## Page budget and relevance-weighted cutting

- Budget: `--pages N` when given, else `market.cv_page_limit` from the profile, else 2 for a CV and 1 for a letter.
- The renderer measures the PDF. Only a measured page count over budget starts cutting. Without a PDF engine it cannot
  measure: the report says `page_method: estimate` and cuts nothing. Say so in the card.
- Cutting removes the lowest-scored experience bullet first, one at a time, until the budget holds. Score (0 to 1):
  relevance to this posting (0.5: share of the posting's keywords and tools the bullet names), uniqueness (0.3: every
  cited achievement appears once in the CV), narrative load (0.2: a cited id is also used in the letter).
- `"keep": true` protects a bullet. Each job keeps at least one bullet. Ties go to the oldest job.
- Every cut is listed in `cuts` with its score. A fact is never changed to save space; wording is the writer's job, done
  before rendering.
- Budget discipline before rendering: summary 3 lines (at most 50 words); skills 5 items; most recent role 4 to 5
  bullets; previous role 2 to 3; older roles 2; education 2 to 3 entries. The renderer refuses a summary over 50 words,
  more than 5 bullets in the latest role or 3 in any other, and a letter body over 250 words (`too_long`).
- A two-page budget is a ceiling, not a target: one dense page that a recruiter scans in ten seconds beats two pages
  of detail. Fill the second page only with lines that match the posting.
- A short last page means a line was cut too eagerly: restore the highest-relevance line that was removed. A CV that
  ends mid-page looks unfinished (`verify_layout.py` reports a thin last page).

## Cut order for hand edits

1. Duplicate claims: keep the version in the experience bullet, which is the more concrete evidence.
2. Summary sentences that restate what the skills or projects already show.
3. Experience bullets that touch no posting term.
4. Older supporting items: an old certificate, the second bullet of an old role.
5. Publications or projects beyond the two that match best.
6. Structural cuts (the oldest education entry) only after the steps above are exhausted.
