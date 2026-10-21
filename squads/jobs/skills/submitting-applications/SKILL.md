---
name: submitting-applications
description: "Submits a form only after the user's explicit apply. Use when an apply card arrives for an approved opening, or a `Mode: KIT` card asks for a manual kit."
---

# Submitting applications

One opening per card. A submit cannot be undone: the guard, the idempotency check and the pre-submit checklist all
run before the first click.

## When to Use

- An apply card for an opening whose consent.json holds the user's words for it.
- A `Mode: KIT` card: write the manual kit, nothing else.

## Procedure

1. **Gate.** A `Mode: KIT` card submits nothing and needs no gate. Any other card runs:

   ```bash
   python3 "$HERMES_HOME/skills/squad-jobs/submitting-applications/scripts/check_submission.py" \
     <P>/openings/<ID>/application/submission.json --gate
   ```

   `gate: open` lets the submit proceed. Otherwise it prints the closed rules: no consent for this opening, no approved
   review, `auto_apply: never`, or an unverified apply link. Only the apply link closing it means a kit (step 6,
   NOT_POSSIBLE). Any other rule: `kanban_block(kind="needs_input", reason="<the rule>")`, and submit nothing.
2. **Idempotency.** Read `status.json` and `application/submission.json`. If the status is `applied` or the file says
   SUBMITTED, complete without touching anything. Never apply twice.
3. **Pre-submit checklist.** Every item must hold; otherwise stop with NOT_POSSIBLE and name the failed item:
   - the card's opening id, the folder name and the id in `opening.md` are the same opening;
   - `apply_url` comes from `opening.md` and the form is on that host;
   - `apply_url` is not `unverified`: run `python3 "$HERMES_HOME/skills/squad-jobs/jobs-contract/scripts/link_check.py" "<apply_url>" --json`
     and read its `verdict`. `unverified` means kit only (step 6, NOT_POSSIBLE with `kit.md`), never SUBMITTED, and
     never a form opened on that host;
   - the form's language equals the opening's language, and so do the answers you will enter (`answers.md`);
   - `application/cv_ats.pdf` is this opening's CV and `render_report.json` has no hard defect;
   - the screenshots show only the form, the entered answers and the confirmation page. Do not capture the account
     menu, a profile page, a mail client or another tab; crop or close them first;
   - `review_before_submit` is known (step 5).
4. **Classify and map.** Open the form (not for KIT) and classify it: `no_login_form`, `requires_account`, `email`,
   `linkedin`, `captcha` or `other`. Anything but `no_login_form` goes to step 6. Map each field to one source:
   `contact.yaml`, `application-data.yaml` (the only source for work authorization, salary, availability, consents
   and saved answers), `answers.md`, the CV, or `consult:<card id>` from a support card to jobs-writer. A fact only the
   user has becomes a `pending_questions` entry (question text and the form's options), `result: NEEDS_DATA`, then
   `kanban_block(kind="needs_input", reason="<the questions>")`.
5. **Fill and submit.** Upload `cv_ats.pdf` unless the card says otherwise. Save `before.png` before submitting. When
   `review_before_submit` is true or `auto_apply` is `ask`, run the gate again with `--before-submit`: it needs the
   user's `screenshot_approval` in consent.json (see Consent file). Without it, block with the screenshot path as the
   reason. Otherwise submit once, wait for the confirmation page and save it as `confirmation.png`. A failing submit
   gets one honest attempt; then NOT_POSSIBLE with the reason. Never retry in a loop.
6. **Record.** Write `application/submission.json` (contract: jobs-contract references/opening-files.md). It names
   fields and sources only, never field values. Then run:

   ```bash
   python3 "$HERMES_HOME/skills/squad-jobs/submitting-applications/scripts/check_submission.py" \
     <P>/openings/<ID>/application/submission.json
   python3 "$HERMES_HOME/skills/squad-jobs/submitting-applications/scripts/record_submission.py" \
     <P>/openings/<ID>/application/submission.json
   ```

   The first must print `valid: <RESULT>`. Exit 1 lists the broken rules: fix the file, run again once; still exit 1 ->
   NOT_POSSIBLE with those rules as the reason. The second writes the tracker row once and appends the same status to
   `status.json` (through status.py): SUBMITTED -> `applied`, NOT_POSSIBLE -> `manual_application`, NEEDS_DATA -> nothing.
   It is safe to run twice. An email application (method `email`) may carry a `mailto:` apply_url; every other method
   needs http(s).
7. `kanban_complete` naming the artifacts, one line on the result.

## Consent file

`application/consent.json` is the only evidence of the user's apply for this opening. The manager writes it, never the
applier, from the user's literal words, and binds it to the kit the user saw:

```json
{"opening_id": "JOB-20261001-acme-data-analyst", "by": "<the user's name>", "words": "<the user's message>",
 "date": "YYYY-MM-DD", "kit_sha256": "<check_submission.py --kit-hash output>"}
```

- `opening_id` equals the opening folder name. A consent for another opening does not count.
- `by` is the user's name, never a bot profile (jobs, jobs-scout, jobs-writer, jobs-reviewer, jobs-applier).
- `kit_sha256` is the kit hash of application/ when the user said apply. A changed cv_ats.pdf, cv.docx, letter files,
  cover_letter.md or answers.md refuses the submit: the user is asked again.
- The gate is open only while the latest review-N.json is APPROVED and the latest status.json line is ready or
  applying. `date` is not before the day of the latest ready line.
- With `review_before_submit: true` or `auto_apply: ask`, add `"screenshot_approval": {"by", "words", "date",
  "screenshot"}`: the user's words after seeing `before.png`, dated not before the approval.
- Every screenshot and the approval's `screenshot` resolve inside application/.
- `auto_apply: never` refuses every submit: the opening gets a kit.
- `check_submission.py` refuses SUBMITTED whenever any of these is missing, and profile.md that cannot be read.

## Manual kit

For NOT_POSSIBLE and for KIT cards, `application/kit.md` holds every answer ready to copy, the `apply_url`, the form
class and, for an email application, the subject and body. A value that is not recorded never appears in it.

## Pitfalls

- Never create an account, log in, solve a CAPTCHA, pay, or accept terms beyond the data-processing consent the user
  authorized (`authorize_consents: true`).
- Never invent an answer. Missing data is a question, not a guess.
- Never submit a second opening under the same card.
- Never auto-submit an `unverified` apply_url, even with the user's confirmation: the kit goes to the user, who
  decides on the employer's own site.
- Screenshots and `submission.json` may hold personal data; they stay in `application/`. No contact data in a card
  body, a comment or a status note.
- The browser never opens linkedin.com (blocklisted for this bot).

## Verification

- `check_submission.py` printed `valid:` for the file you hand off.
- The gate printed `gate: open` before the first click; SUBMITTED implies `confirmation.png` exists, the tracker row is
  `applied`, and `status.json` ends with `applied`.
- Every filled field names a source; `pending_questions` is empty unless the card is blocked on them.
- NOT_POSSIBLE implies `kit.md` holds every answer and the `apply_url`, and the status is `manual_application`.
