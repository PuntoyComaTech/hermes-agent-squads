# Who applies: a new bot or one of the four?

2026-09-25 · Squad: job search · Outcome: D-009 in `02-decisions.md`

## The question

Applying (with the user's confirmation) needs three things no other specialist holds together: **a browser that fills in and submits forms**, **personal form data** (email, phone, work authorization, salary expectation) and **permission to submit on the user's behalf**.

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| **A · The scout** (has a browser) | No new bot | It reads arbitrary pages; adding personal data and the power to submit is the worst security combination. It mixes "search a lot" with "submit little, carefully" |
| **B · The writer** (knows the CV) | No new bot; knows what it wrote | Needs a browser; the bot that writes the CV would read external pages that can carry malicious text |
| **C · The orchestrator** (talks to the user) | No new bot; has the confirmation at hand | It has memory and no web or browser by design. Exposing it to external pages puts the whole ecosystem at risk |
| **D · New bot `jobs-applier`** (chosen) | The only bot with form data and permission to submit; its guard requires written confirmation; easy to audit (each submission leaves screenshots and `submission.json`); can be turned off alone | One more bot; depends on the Hermes browser uploading files (undocumented, tested during installation) |

**Why D:** it meets the base rule for a new bot: **different permissions** the others must not have. It acts only when the user says "apply".

## Limits accepted on purpose

- **No accounts or logins.** Portals that require them (Workday, Computrabajo, LinkedIn) get the link and a kit with answers ready to copy. Creating accounts on someone's behalf carries legal and security risks.
- **No CAPTCHAs.** Hermes solves them only with paid cloud browsers; if one shows up, it switches to kit mode.
- **Never LinkedIn**: its terms forbid automation.
- **If the browser cannot upload files**, the applier stays in kit mode.

Covered well: public forms of applicant tracking systems (Greenhouse, Lever, Ashby) and company forms without an account, common at tech companies and for remote openings.

## Level 3

- **Apply by email** when the opening says "send your CV to…", if the user connects their email to Hermes.
- **Portals that need an account**, if the user creates it and stores the login in the Hermes credential vault (`hermes vault`), which fills it in without the model seeing the password. Each portal's terms are evaluated first.
