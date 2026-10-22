# LinkedIn Easy Apply

Easy Apply is the one form the applier fills inside LinkedIn, on the user's signed-in session. It runs only under
`auto_apply: auto` (standing consent) and only from an opening whose `apply_url` is the job page itself:
`https://<locale.>linkedin.com/jobs/view/<id>`. The gate refuses every other address (`--method linkedin_easy_apply`).

The steps below are the working rules, not a measured script: the flow changes, so the applier reads each step and
maps it. Nothing here is clicked on a real account while the squad is being built.

## When to Use

- The gate printed `gate: open` with `--method linkedin_easy_apply`.
- `profile.md` has `auto_apply: auto`, and the opening's `apply_url` is its `/jobs/view/<id>` page.

## Procedure

1. **The session.** Bots with `shared_browser: true` drive the machine's one signed-in browser through `browser_exec`
   with `browser.cdp_url`; the plugin `shared-browser-tabs` gives this run one tab and closes it at the end of the
   turn. Never open a second tab, never close a tab, never type a credential, never sign in: the session belongs to the
   user, who signed in by hand. Read `location.href` after every click and keep it on the job page, the application
   form and the confirmation.
2. **Stop signals.** A sign-in wall, a checkpoint, a CAPTCHA, an "unusual activity" banner or a restriction notice ends
   all LinkedIn work for the day: type nothing, solve nothing, save nothing further. Block with
   `kanban_block(kind="needs_input", reason="LinkedIn asks for a sign-in check")` and tell the user to run
   `scripts/hpy shared_browser.py login https://www.linkedin.com` on this Mac. Other openings of the project wait for
   the next day's run.
3. **Open the application.** On the job page, the Easy Apply control opens a multi-step dialog. Read the step count and
   the labels; do not jump ahead with a keyboard shortcut, and do not use "Apply with resume" tricks that reformat
   the CV.
4. **Map each step, one field at a time.** Every filled field gets one source: `contact.yaml` (name, e-mail, phone,
   location, links), `application-data.yaml` (work authorization, salary expectation, start availability, relocation,
   voluntary questions, `saved_answers`), `answers.md`, the CV, or `consult:<card id>` from a support card to
   jobs-writer. Nothing is chosen because it looks plausible.
5. **Stop at the first field without a source.** Take a screenshot of that step, write `result: NEEDS_DATA`, put the
   question and the form's own options in `pending_questions`, run `check_submission.py`, then
   `kanban_block(kind="needs_input", reason="<the questions>")`. Do not continue the dialog, do not answer a screening
   question from a guess, and do not pick "prefer not to answer" unless `voluntary_questions` says so. When the
   manager returns with the answers, the next run starts the application again from the job page: Easy Apply keeps no
   draft the squad can trust.
6. **Final review step.** Easy Apply ends on a review of the filled fields. Read every line of it and compare it with
   the sources: the CV uploaded, the employer, the role, the answers. A line that does not match its source is a
   NEEDS_DATA stop, never a click through. `before.png` is the screenshot of this step. Then submit once.
7. **Confirmation.** The dialog confirms the application was sent. Save `confirmation.png`, note the job id, and record
   with `method: linkedin_easy_apply`. The tracker row and `status.json` move to `applied` through
   `record_submission.py`, and the day's `daily_easy_apply_cap` counts one more.

## What is never submitted

- A form that asks for payment, a paid test, a bank detail or an ID scan: NOT_POSSIBLE with the reason, and the user
  decides.
- A screening question the profile does not answer (years in a tool the profile never names, a licence, a salary the
  user has not set): NEEDS_DATA.
- A second application under one card, or a second one for an opening already `applied`.
- An application whose latest review is not APPROVED or whose opening's eligibility gate is not PASS: the gate closes
  it before the browser opens.

## Verification

- The gate printed `gate: open` with `--method linkedin_easy_apply` before the job page was opened.
- Every filled field in `submission.json` names a source, and `pending_questions` is empty for a SUBMITTED record.
- `confirmation.png` shows the confirmation of this opening, not a job page or a list.
- The card's result line names the company, the role, the CV file used and the apply URL.
