---
name: submitting-applications
description: "Submits applications under consent and daily caps. Use when an apply card arrives for an approved opening, or a `Mode: KIT` card asks for a manual kit."
---

# Submitting applications

One opening per card, and a submit cannot be undone: the gate, the idempotency check and the pre-submit checklist run
before the first click. `profile.md` decides the rest: `auto` or a per-opening apply, else a kit (see Consent).

## When to Use

- An apply card for an approved opening (review APPROVED, status `ready`), or a `Mode: KIT` card: the kit only.

## Procedure

1. **Gate.** A `Mode: KIT` card submits nothing and needs no gate. Any other card runs, with
   `S="$HERMES_HOME/skills/squad-jobs/submitting-applications/scripts"`:

   ```bash
   python3 "$S/check_submission.py" <P>/openings/<ID>/application/submission.json --gate --method <method>
   ```

   `--method` names the form class: `linkedin_easy_apply` for Easy Apply, `no_login_form` otherwise; every other class
   is a kit, never a click. `gate: open` lets the submit proceed: it writes `application/gate.json`
   (the proof step 6 reads) and under `auto` reserves the day's place (4 h at most); gate and record share
   `openings/.apply.lock`. Any other line closes it:
   - `easy_apply_gap`: an Easy Apply went out under a minute ago. Wait the seconds named, run the gate again.
   - `daily_cap`: the day's cap is reached. Submit nothing and write no kit: `kanban_complete` with one line ("<n>
     applications today, the cap: this one goes tomorrow") and leave the status at `ready` so the next run applies it.
   - any other rule: `kanban_block(kind="needs_input", reason="<the rule>")`, and submit nothing.
2. **Idempotency.** Read `status.json` and `application/submission.json`: an `applied` status or a SUBMITTED file means
   complete without touching anything. Never apply twice.
3. **Pre-submit checklist.** Every item must hold; otherwise stop with NOT_POSSIBLE and name the failed item:
   - the card's opening id, the folder name and the id in `opening.md` are the same opening;
   - `apply_url` comes from `opening.md` and the form is on that host. Run
     `python3 "$HERMES_HOME/skills/squad-jobs/jobs-contract/scripts/link_check.py" "<apply_url>" --json`: an
     `unverified` verdict is kit only, never SUBMITTED, never a form opened on that host;
   - the form's language equals the opening's language, and so do the answers you will enter (`answers.md`);
   - `application/cv_ats.pdf` is this opening's CV and `render_report.json` has no hard defect;
   - the screenshots show only the form, the answers and the confirmation page (no account menu, profile or mail
     client), and `review_before_submit` is known (step 5).
4. **Classify and map.** Open the form (not for KIT) and classify it: `no_login_form`, `linkedin_easy_apply`,
   `requires_account`, `email`, `linkedin`, `captcha` or `other`. Anything but the first two goes to step 6. Map each
   field to one source: `contact.yaml`, `application-data.yaml` (the only source for work authorization, salary,
   availability, consents and saved answers), `answers.md`, the CV, or `consult:<card id>` from a support card to
   jobs-writer: every free-text question the record answers (strength, ownership, priorities, first 90 days) goes on one
   such card, never to the user. A fact only the user has becomes a `pending_questions` entry (question text and the
   form's options), `result: NEEDS_DATA`, then `kanban_block(kind="needs_input", reason="<the questions>")`.
   **Easy Apply** runs on the shared signed-in browser: `references/easy-apply.md`. Its steps are mapped one field at a
   time and it stops at the first field without a source. A form that asks for payment, a paid test, or data that is
   not in `contact.yaml` or `application-data.yaml` is never submitted: NEEDS_DATA or NOT_POSSIBLE, never a guess.
5. **Fill and submit.** Upload the file `jobs-contract/scripts/upload_copy.py <P>/openings/<ID>/application` prints,
   never one you named, unless the card says otherwise. Save `before.png` before submitting. When
   `review_before_submit` is true or `auto_apply` is `ask`, run the gate again with `--before-submit`: it needs the
   user's `screenshot_approval` (see Consent), else block with the screenshot path as the reason. Easy Apply stops on
   its own final review step and compares it with the sources before Submit. Otherwise submit once and save the
   confirmation page as `confirmation.png`. One honest attempt; then NOT_POSSIBLE. Never retry in a loop.
6. **Record.** Write `application/submission.json` (contract: jobs-contract references/opening-files.md): fields and
   sources only, never values. A **SUBMITTED** card runs the record alone, and never `check_submission.py` first: the
   record re-checks the file itself with `--post-submit`, so a submit that happened is never turned into NOT_POSSIBLE
   after the click.

   ```bash
   python3 "$S/record_submission.py" <P>/openings/<ID>/application/submission.json
   ```

   It writes the tracker row once and appends `applied`. With a `gate.json` stamp of this opening under 4 hours old it
   records the rules that moved after the click (the cap, a replaced review, the consent date) with the status note
   `recorded over the gate: <rule>`; every other rule refuses the record (exit 1): a question for the manager, never a
   fake NOT_POSSIBLE. **NOT_POSSIBLE / NEEDS_DATA** run `"$S/check_submission.py"` on the same file first: it must
   print `valid: <RESULT>`, and exit 1 lists the broken rules — fix the file, run it again once, then NOT_POSSIBLE
   with those rules as the reason. NOT_POSSIBLE records `manual_application`, NEEDS_DATA nothing, and either result
   that leaves the row unwritten after an open gate gives the place back:
   `python3 "$S/apply_state.py" --release <P> --opening <ID>`. Safe twice; an email may carry a `mailto:` apply_url.
7. `kanban_complete` naming the artifacts, one line on the result. SUBMITTED states the company, the role, the CV file
   used (`application/cv_ats.pdf`) and the apply URL, which the manager quotes in the digest. NEEDS_DATA and
   NOT_POSSIBLE state what the user must do; the manager relays it.

## Consent

- `auto` + `apply_consent: standing` (the two must match): the yes is recorded once, dated (`auto_apply_since`), with
  `daily_apply_cap` (default 10) and `daily_easy_apply_cap` (default 5): no consent.json, no per-opening apply, no
  screenshot approval. The gate needs an APPROVED latest review, a dated `ready` line and this opening's `analysis.json`:
  `id` equal to the folder, `fit.decision: PURSUE` (never WATCH or REJECT: a failed gate, a deal-breaker or a core
  gap), no gate at FAIL, `fit.score` at or above a finite `apply_threshold` (0..100), an employer ATS link (or a
  LinkedIn `/jobs/view` page for Easy Apply) and cap room. A cap means tomorrow, never a kit.
- `try` + `per_opening`: `application/consent.json` is the evidence of the user's apply for this opening. The manager
  writes it, never the applier, from the user's own answer, typed or a clicked `clarify` choice (`{opening_id, by, words, date, kit_sha256}`), bound to
  the kit the user saw: `opening_id` equals the folder, `by` is the user's name and never a bot profile, and a changed
  `cv_ats.pdf`, letter or `answers.md` refuses the submit. The consent date is not before the approval.
- `ask` + `per_opening`: the same file, plus `"screenshot_approval": {"by", "words", "date", "screenshot"}` after the
  user saw `before.png`.
- `never`: every submit is refused; the opening gets a kit.
- A profile the checker cannot read refuses SUBMITTED: the settings must be known, never assumed.

## Manual kit

For NOT_POSSIBLE and KIT cards, `application/kit.md` holds every answer ready to copy, the `apply_url`, the form class
and, for an email, the subject and body. A value that is not recorded never appears in it.

## Pitfalls

- Never create an account, log in, solve a CAPTCHA, pay, or accept terms beyond the data-processing consent the user
  authorized (`authorize_consents: true`).
- Never invent an answer: missing data is a question. A "used <tool>?" whose family the candidate holds is yes.
- Never submit a second opening under the same card, and never apply twice under standing consent.
- Never turn a click that happened into NOT_POSSIBLE: the record decides that, not the bot's second thoughts.
- Never auto-submit an `unverified` apply_url, even with the user's confirmation: the kit goes to the user.
- Never drive the shared browser past a sign-in wall, a checkpoint, a CAPTCHA or a restriction notice, and never type
  a credential: that stops LinkedIn work for the day (references/easy-apply.md).
- Screenshots and `submission.json` stay in `application/`; no contact data in a card, a comment or a status note.

## Verification

- The gate printed `gate: open` before the first click; SUBMITTED implies `confirmation.png`, the tracker row `applied`
  and `status.json` ending `applied`; every filled field names a source.
- NOT_POSSIBLE implies `kit.md` holds every answer and the `apply_url`, with status `manual_application`; a card closed
  on `daily_cap` names the count and the cap and leaves its opening `ready`, with no kit.
- No reservation is left behind: `apply_state.py --status <P>` lists none for the opening.
