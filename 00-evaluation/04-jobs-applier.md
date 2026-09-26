# Who applies: a new bot or one of the four?

> Pros-and-cons review of a decision in the job search squad. Check it when changing the squad's structure; the outcome is recorded in `02-decisions.md` (D-009).

2026-09-25 · Squad: job search

## The question

Applying on its own (with the user's confirmation) requires three things that no specialist has all at once today: **a browser to fill in and submit forms**, **personal data for forms** (email, phone, work authorization, salary expectation) and **permission to submit on the user's behalf**. Do we give this to one of the four or create a fifth?

## Options

| Option | Pros | Cons |
| --- | --- | --- |
| **A · The scout does it** (it already has a browser) | No new bot | The scout reads arbitrary pages; also giving it the personal data and the power to submit is the worst security combination. It mixes "search a lot" with "submit little, and carefully" |
| **B · The writer does it** (it already knows the CV) | No new bot; it knows what it wrote | It would need a browser; the bot that writes the CV would start reading external pages, which can carry malicious text |
| **C · The orchestrator does it** (it already talks to the user) | No new bot; it has the confirmation at hand | The orchestrator is designed with no web or browser: it is the one that has memory and talks to the user. Exposing it to external pages puts the whole ecosystem at risk |
| **D · New bot `jobs-applier`** | The only bot with the form data and permission to submit; its guard requires written confirmation; it is easy to audit (each submission leaves screenshots and `submission.json`); it can be turned off without touching anything else | One more bot to configure; its quality depends on the Hermes browser being able to upload files (not documented: tested during installation) |

## Recommendation

**Option D.** It meets the base rule for creating a bot: **different permissions** that the others must not have. The four specialists stay as they were and the new one only acts when the user says "apply".

## Limits accepted on purpose

- **It does not create accounts or log in.** Many portals require this (Workday, Computrabajo, LinkedIn): in those cases it sends the link and a kit with the answers ready to copy. Creating accounts on someone's behalf brings legal and security risks that are not worth it.
- **It does not solve CAPTCHAs.** Hermes only solves them with paid cloud browsers; if one shows up, it switches to kit mode.
- **Never LinkedIn**: its terms forbid automating it.
- **If the browser cannot upload files**, the applier stays in kit mode until Hermes allows it.

What it does cover well: public forms from applicant tracking systems such as Greenhouse, Lever or Ashby, and companies' own forms that need no account. They are very common at tech companies and for remote openings.

## Later (Level 3)

- **Apply by email** when the opening says "send your CV to…", if the user connects their email to Hermes.
- **Portals that need an account**, if the user creates the account themselves and stores the login in the Hermes credential vault (`hermes vault`), which fills it in without the model seeing the password. This requires evaluating each portal's terms.
