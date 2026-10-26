# Review lenses

Five independent children, five lens blocks. Each child gets only the files its lens names, a clean context and, as
`output_schema`, what `aggregate_review.py --schema <lens>` prints (the shapes below are examples). A child never
reads the kanban card, never writes files and never sees another lens. The parent saves each block as `<lens>.json` and runs `scripts/aggregate_review.py` (SKILL.md step 3).

## Contents

Shared rules; truthfulness; ats; recruiter; hiring_manager; writing; correction objects; aggregation rules.

## Shared rules

- A blocking finding carries a `correction` (shape below). If the writer would need a judgment call to apply it, the
  finding is not yet a correction: rewrite it until the location and the new text are exact.
- A concern with no fix is a warning, never a block.
- No e-mail address or phone number goes into any block. Say "the contact block" and give its location.
- Sources in order of authority: `achievements.yaml` (verified entries), `profile.md`, then the application itself.

## truthfulness

Files: `application/` (all text documents), `achievements.yaml`, `profile.md`, `application-data.yaml`
(`saved_answers`), the user's own CV text in `documents/cv/` and `opening.md` (company names only).

Checks each claim (numbers, dates, titles, companies, tools, proficiency, languages) against a `verified: true`
entry. Nothing raised, nothing rounded up. A result sentence without an achievement citation is a finding.

**Grounding.** A claim is grounded when any of the user's own files above supports it: a title the user writes
for their own program ("Web and Mobile Developer") is grounded by their CV or a saved answer.
A draft claim neither source supports is a `draft` finding and blocks. A tool named from a held member of its
family (`related_tool` in `render_report.json`, `skill_families.json`) is grounded, never a finding. When the two sources contradict each other,
or one records a fact the other does not, the finding is `profile_consistency`: a warning in the review, the draft
stays as it is, and nobody asks the user about it (the manager aligns the files from the source the user wrote).

**Company claims.** Every company-specific statement in the letter (product, news, mission, team, a number) is a
company claim, verified on a page the reviewer located itself (snippets are leads; an `opening.md` URL is never a
source). A claim with no verifiable page is `dropped`: a correction removes or grounds it, listed in `dropped_claims`.

```json
{
  "verdict": "PASS | FAIL",
  "grounding": {"sources": ["application/cover_letter.md", "achievements.yaml", "profile.md"]},
  "findings": [{
    "kind": "draft | profile_consistency",
    "check": "numbers | dates | titles | companies | tools | levels | languages | citation | grounding",
    "location": "cover_letter.md, paragraph 2",
    "text": "quoted span",
    "problem": "one line",
    "claim_terms": ["Python", "FastAPI", "AI"],
    "conflicting_sources": ["achievements.yaml", "profile.md"],
    "correction": {"type": "content", "mode": "replace", "file": "cover_letter.md", "old": "...", "new": "..."}
  }],
  "company_claims": [{
    "claim": "the statement as written",
    "location": "cover_letter.md, paragraph 1",
    "source_url": "https://company.example/about",
    "source_located_by_reviewer": true,
    "source_excerpt": "at least 40 characters copied from the fetched page, or source_file instead",
    "reason": "page states it | no page found",
    "verdict": "kept | dropped",
    "correction": {"type": "content", "mode": "instruction", "instructions": "remove the sentence"}
  }]
}
```

`conflicting_sources` is required for `profile_consistency` (no correction); `correction` for `draft` findings and
`dropped` claims, either of which makes the verdict FAIL. A `draft` finding names `claim_terms` (1 to 4 words the
claim ties together): search every file for the same claim, one finding per instance, this round. "Working remotely"
is grounded only by `work_mode: remote` on the current experience (profile.md `work_mode` is the search preference);
"Professional Working Proficiency" reads as C1, above a B2. Both are `draft` findings, whatever earlier rounds said.

## ats

Files: `application/cv_ats.txt`, `application/cv_ats.html`, `application/render_report.json`, `analysis.json`.

Checks single-column reading order, headings, selectable text, real links from the report, and keyword coverage
against the `analysis.json` keywords. A keyword that no achievement supports is a gap: `evidence: ""`, a warning, never
faked into the CV. A supported keyword is a block with a correction that adds it to the named bullet. Missing engines
are environment notes (`environment: true`) and never block.

```json
{
  "verdict": "PASS | FIX",
  "keyword_coverage": 0.8,
  "missing": [{"keyword": "data pipeline", "evidence": "ACH-007", "location": "cv_content.json, experience[0]",
               "correction": {"type": "content", "mode": "replace", "file": "cv_ats.txt", "old": "...", "new": "..."}},
              {"keyword": "Kubernetes", "evidence": ""}],
  "defects": [{"location": "cv_ats.pdf, page 2", "problem": "heading split from its first bullet", "hard": true,
               "environment": false,
               "correction": {"type": "format", "mode": "instruction", "instructions": "keep the heading with its first bullet"}}],
  "pages": {"expected": 2, "actual": 2}
}
```

A plain string in `missing` is accepted as a gap. `pages.actual` different from `pages.expected` needs a hard defect.

## recruiter: market conventions

Files: `application/` (first screen of the CV and letter), `opening.md`, `profile.md`.

Reads like a recruiter with thirty seconds: who this person is, the role they want, whether location and work mode are
visible, whether evidence is linked. Blockers only when they would sink the application: wrong role, no contact block,
an unreadable first screen.

**Market.** From `profile.md` front matter: `market.conventions` (photo, age, marital_status, references_line),
`market.cv_page_limit`, `candidate.include_age_in_cv`, `candidate.photo_in_cv`. A convention set to false means the
document prints nothing of that kind. Every violation blocks with a correction. The page count comes from
`render_report.json`; going over `cv_page_limit` needs a `page_limit` violation.

```json
{
  "verdict": "PASS | FIX",
  "seconds_to_understand": 20,
  "would_open_evidence": true,
  "blockers": [{"location": "cv_ats.html, header", "problem": "no role line on the first screen",
                "correction": {"type": "format", "mode": "instruction", "instructions": "add the target role under the name"}}],
  "market": {
    "checked": ["photo", "age", "marital_status", "references_line", "page_limit"],
    "pages": 2,
    "page_limit": 2,
    "violations": [{"convention": "photo", "location": "cv_ats.html, header", "problem": "a photo is printed",
                    "correction": {"type": "format", "mode": "instruction", "instructions": "remove the photo"}}]
  }
}
```

`convention` is one of the four conventions or `page_limit`.

## hiring_manager: interview-backtrack test

Files: `application/`, `opening.md`, `analysis.json`, `profile.md` (for `reviewer_role`).

Plays `reviewer_role`: can this person do the job? Are the must-haves addressed, the hard gaps handled honestly? Which
interview questions follow from the documents?

**Backtrack test.** For each claim that states a result or a scope (led, owned, built, shipped, cut, managed, any
number), write the question an interviewer would ask to get the detail behind it. Answer it from `achievements.yaml`
and `profile.md` only. `answerable_from_sources: false` means the sources cannot back the detail: a fabricated
stretch. It blocks, with a correction that rewrites the claim to the scope and proficiency the sources state. A detail
the documents do not state (which vector store) is an `interview_questions` entry, never a block or a user question.

```json
{
  "verdict": "PASS | FIX",
  "can_do_the_job": true,
  "concerns": ["no production Kubernetes; the letter does not claim it"],
  "interview_questions": ["How did you handle a failed holiday run of the report?"],
  "stretches": [{"location": "cover_letter.md, paragraph 2", "claim": "led the migration",
                 "backtrack_question": "What did you own in the migration?", "answerable_from_sources": false,
                 "claim_terms": ["led", "migration"],
                 "correction": {"type": "content", "mode": "replace", "file": "cover_letter.md",
                                "old": "led the migration", "new": "took part in the migration"}}]
}
```

`answerable_from_sources: true` does not block; `false` also names `claim_terms`. Concerns and interview questions are
plain strings.

## writing: language check

Files: `application/`, `opening.md`.

Grammar, spelling, jargon, bullet shape (strong verb, what, for whom, result; 12 to 22 words), length for the format,
tone of the letter and answers. Each finding names the exact location and the fix; no paragraph rewrites.

**Language.** `document_language` is the language of the CV and letter. `opening_language` comes from the opening's
front matter. `declared_level` is the CEFR level in `achievements.yaml` for the opening's language, null when the
language is undeclared. `implied_level` is the level the letter itself claims, null when it claims none. A document
language that differs from the opening's blocks. A declared level that differs from the implied one blocks.

```json
{
  "verdict": "PASS | FIX",
  "findings": [{"location": "cover_letter.md, paragraph 3", "text": "quoted span", "fix": "split the sentence",
                "correction": {"type": "format", "mode": "replace", "file": "cover_letter.md", "old": "...", "new": "..."}}],
  "language": {"document_language": "en", "opening_language": "en", "declared_level": "B2", "implied_level": null,
               "location": "cover_letter.md", "correction": null}
}
```

`language.correction` is required only when a mismatch exists.

## Correction objects

Each block correction is `{type, mode: "replace", file, old (exact, occurs once), new}` (`new` empty deletes) or
`{type, mode: "instruction", instructions}`. `type`: content (facts, claims, results), format (layout, length,
pages, photo), strategy (positioning, which achievement leads).

## Aggregation rules

Enforced by `scripts/aggregate_review.py` (the parent runs it, never a lens).
1. A lens verdict matches its blocks: PASS with a block, or FIX (FAIL for truthfulness) without one, is an error.
2. A block is: a draft finding, a dropped company claim, a supported missing keyword, a hard defect, a recruiter
   blocker, a market violation, an unanswerable stretch, a writing finding, or a language mismatch.
3. No block in any lens: APPROVED, status `ready`. Any block: round 1 gives FIX (status `in_review`); round 2 or later gives NOT_APPROVED (status `not_approved`).
   Truthfulness FAIL is never APPROVED. With `--apply` (always, in this squad) only hard blocks count: writing
   findings, recruiter blockers and supported keywords are fixed by the reviewer in place (`applied`, `polish`).
4. Internal text (outside answers.md [FIELD] blocks, strategy.md, kit.md) never blocks; a required form question
   without its [FIELD] always does; APPROVED needs an employer link (`aggregate_review.py --help`).
5. `summary_for_user`: 1 to 5 lines in the user's language, no internal field names; contact data anywhere in the
   review is an error and nothing is written.
