---
name: writing-applications
description: "Writes the CV, letter and form answers for one opening. Use when a write card or a correction card needs the application built from verified achievements."
---

# Writing applications

One opening per card. Documents are written in the posting's language. The card body says NEW, CORRECTION or CHANGE.

## When to Use

- A write card (NEW), a correction card (CORRECTION after one review round) or a change card (CHANGE after a user request).
- Before rendering, and before the reviewer's card exists.

## Procedure

1. Read the card, `analysis.json`, `opening.md` and `profile.md`. Read `achievements.yaml` for every claim. Read
   `contact.yaml` only for the CV header.
2. Write `application/strategy.md`: the stage structure (`candidate.stage`), headline, the keywords you will cover
   (only those an achievement supports), CV language (the opening's language), evidence pieces when
   `evidence.pieces_per_application` is above 0, and every stretch you expect to flag.
3. Write `application/cv_content.json` (shape in `skills/rendering-cv/references/content-schema.md`). Each bullet is
   a strong verb, what, for whom and the result, 12 to 22 words, and it cites its achievement ids. Mark a bullet
   `"keep": true` when the letter depends on it.
4. Write `cover_letter.md` (`references/cover-letter.md`) and `answers.md` (`references/application-forms.md`) for the
   deliverables listed in `profile.md`. Every body paragraph ends with its `<!-- achievements: ACH-... -->` comment.
   Motivation and closing paragraphs use `<!-- achievements: none -->`.
5. Render the CV, then the letter, with `rendering-cv`. Read `render_report.json` (CV) and `render_report_letter.json`.
6. Put every `stretch_flags` entry in the card as: "stretch because X: keep, soften or drop". Do not finalise a
   flagged bullet before the user answers.
7. Set `status.json` to `in_review`. Create the reviewer's card: jobs-reviewer, `skills: [reviewing-applications]`,
   `parents: [<your card id>]`, `idempotency_key` `jobs:application:<project>:<ID>:review` (CORRECTION:
   `...:review-r2`; CHANGE round N: `...:review-c<N>`).

**CORRECTION and CHANGE.** Apply exactly what the reviewer or the user asked, note each change in `strategy.md`, then
redo steps 5 to 7. A requested claim with no verified achievement is never written:
`kanban_block(kind="needs_input", reason="<missing achievement>")`.

## Pitfalls

- Never claim a number, title, scope or proficiency that `achievements.yaml` does not hold. `participated` stays
  `participated`; "led" is written only when the record says led.
- Never edit `analysis.json`, `opening.md` or the history in `status.json`.
- Contact data appears only in the rendered header, never in the text of a bullet or a letter.
- Never print age, photo, marital status, date of birth or nationality. Age appears only when the profile sets
  `include_age_in_cv: true`; the other items are refused by the renderer (`private_data`).
- Never change the template to fix an overflow: tighten the wording. A template change is a question to the user;
  the renderer refuses it without the user's yes (`--template-override-by-user`).
- A company fact (product, project, priority) is written only when the dated company profile or the opening states it.
- Tailoring and style rules are in `references/cv-tailoring.md` and `references/writing-style.md`. Follow them before
  rendering; do not rely on the renderer to catch them.

## Verification

- Every bullet and paragraph cites an achievement id, and the render report has no `uncited_claim` or
  `unverified_achievement` defect.
- The render report has no defect; `pages_actual` meets the budget; `page_method` is `measured`, or the card says the
  page count is an estimate.
- Every stretch flag is in the card for the user.
- `strategy.md` explains each keyword covered and each evidence piece chosen.
- The reviewer's card exists with the right round key.
