---
name: writing-applications
description: "Writes the CV, letter and form answers for one opening. Use when a write card or a correction card needs the application built from verified achievements."
---

# Writing applications

You turn verified achievements into a CV, letter and answers for one opening, in the opening's language. The card
body says NEW, CORRECTION or CHANGE. Nothing enters a document unless `achievements.yaml` has it with
`verified: true`, cited by id.

## When to Use

- A write card (NEW) or a correction card (CORRECTION after one review round, CHANGE after a user request).
- Before running `render_cv.py` and before the reviewer's card exists.

## Procedure

1. Read the card, `analysis.json`, `opening.md` and `profile.md`. Read `contact.yaml` only for the CV header;
   its data never appears in a card, comment or any file outside `application/`.
2. **strategy.md**: headline, narrative, order of experiences and skills, the keywords you will cover (only
   those an achievement supports), CV language (= the opening's language), and the evidence pieces when
   `evidence.pieces_per_application` is above 0.
3. **cv_content.json** per skill rendering-cv (the shape is documented there). Every experience bullet is a
   strong verb + what + for whom + result, 12 to 22 words, and cites its achievement ids. Style: no empty
   adjectives, no filler, one idea per bullet, most relevant experience first.
4. **Other deliverables** from `profile.md` -> `deliverables`: `cover_letter.md`, `answers.md`,
   `recruiter_message.md`. Each paragraph ends with `<!-- achievements: ACH-... -->`. Answers use only recorded
   data and verified achievements.
5. **Render** with skill rendering-cv: `python3 "$HERMES_HOME/skills/squad-jobs/rendering-cv/scripts/render_cv.py"`
   over `cv_content.json`; read `render_report.json`. At most 3 attempts; when space runs short, change the
   design, never a fact or a number.
6. Set `status.json` to `in_review` and create the reviewer's card: jobs-reviewer, skill
   reviewing-applications, `parents` = [your card], `idempotency_key` `jobs:application:<project>:<ID>:review`
   (round 2: `...:review-r2`).

**CORRECTION / CHANGE.** Apply exactly what the reviewer or the user asked, note in `strategy.md` what changed,
re-render, and file the round-2 review card. A requested claim with no verified achievement is never written:
`kanban_block(kind="needs_input")` and name the missing achievement.

## Pitfalls

- Never change a number, date, job title, company or tool; never round up; never raise a proficiency level.
- Never use an achievement with `verified: false`, and never write a claim the user did not confirm.
- Never browse: you have no web toolset, and the analysis is the scout's file.
- Never edit `analysis.json`, `opening.md` or `status.json` history.
- The CV header is the only place contact data may appear, and only in the rendered files.

## Verification

- Every bullet and paragraph cites an achievement id that exists with `verified: true`.
- `render_report.json` has no hard defect, and matches the page count when the card asks for one.
- `strategy.md` explains each keyword covered and each piece chosen.
- The reviewer's card exists with the right round key.
