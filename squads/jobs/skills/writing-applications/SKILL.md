---
name: writing-applications
description: "Writes the CV, letter and form answers for one opening. Use when a write card or a correction card needs the application built from verified achievements."
---

# Writing applications

One opening per card, documents in the opening's language. The card body says NEW, CORRECTION or CHANGE.

## When to Use

- A write card (NEW) or a correction card (CORRECTION after one review round, CHANGE after a user request).
- Before running `render_cv.py` and before the reviewer's card exists.

## Procedure

1. Read the card, `analysis.json`, `opening.md` and `profile.md`. Read `contact.yaml` only for the CV header.
2. **strategy.md**: headline, narrative, order of experiences and skills, the keywords you will cover (only
   those an achievement supports), CV language (= the opening's language), and the evidence pieces when
   `evidence.pieces_per_application` is above 0.
3. **cv_content.json** per skill rendering-cv (the shape is documented there). Every experience bullet is a
   strong verb + what + for whom + result, 12 to 22 words, and cites its achievement ids. One idea per bullet.
4. **Other deliverables** from `profile.md` -> `deliverables`: `cover_letter.md`, `answers.md`,
   `recruiter_message.md`. Each paragraph ends with `<!-- achievements: ACH-... -->`. Answers use only recorded
   data and verified achievements.
5. **Render** per skill rendering-cv over `cv_content.json`; read `render_report.json`.
6. Set `status.json` to `in_review` and create the reviewer's card: jobs-reviewer,
   `skills: [reviewing-applications]`, `parents: [<your card id>]`, `idempotency_key`
   `jobs:application:<project>:<ID>:review` (CORRECTION: `...:review-r2`; CHANGE round N: `...:review-c<N>`).

**CORRECTION / CHANGE.** Apply exactly what the reviewer or the user asked, note in `strategy.md` what changed,
then run steps 5 and 6. A requested claim with no verified achievement is never written:
`kanban_block(kind="needs_input", reason="<missing achievement>")`.

## Pitfalls

- Never edit `analysis.json`, `opening.md` or `status.json` history.
- The CV header is the only place contact data may appear, and only in the rendered files.

## Verification

- Every bullet and paragraph cites an achievement id that exists with `verified: true`.
- `render_report.json` has no hard defect, and matches the page count when the card asks for one.
- `strategy.md` explains each keyword covered and each piece chosen.
- The reviewer's card exists with the right round key.
