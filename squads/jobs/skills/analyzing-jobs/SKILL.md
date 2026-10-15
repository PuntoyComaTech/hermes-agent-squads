---
name: analyzing-jobs
description: "Decides PURSUE, WATCH or REJECT for one saved opening. Use when an analysis card arrives for a filtered opening and the company profile is needed."
---

# Analyzing jobs

One opening per card.

## When to Use

- An analysis card for a PASS or FLAG opening.
- Before creating the writer's card, or when the user asks "why".

## Procedure

1. Read the card, `opening.md` and `profile.md`. Work in the opening's folder.
2. **Requirements first, without reading `achievements.yaml`.** From `opening.md` alone, write
   `must_have`, `nice_to_have`, `responsibilities`, `tools`, `keywords`, `disqualifiers`, `priorities` into
   `analysis.json`.
3. **Company.** Reuse `companies/<company>.md` while it is under 30 days old. Otherwise profile the company
   yourself from its site, its jobs page, public news and profiles: summary, product, sector, brand tone, team
   signals, news, sources. At most `profile.md` -> `max_company_searches` page reads; a blocked page is handled
   with the blocked-page-recovery skill. Save the dated profile to `companies/<company>.md`.
4. **Evidence.** Now read `achievements.yaml`. For every requirement list the verified achievements that support
   it with a confidence from 0 to 1 (`verified: false` items are not evidence). A must-have with none is a
   `hard_gap`; a nice-to-have with none is a normal gap.
5. **Decide.** `fit.score` 0-100, `fit.decision` PURSUE, WATCH or REJECT, plus strengths, gaps, hard_gaps,
   transferable skills and `overselling_risk`. REJECT when a disqualifier or a hard gap in a core must-have
   exists; WATCH when no REJECT reason applies and `fit.score` < `apply_threshold`. `fit.reason` is one line
   naming the deciding requirement.
6. **Hand off** when the decision is PURSUE and the score is at least `apply_threshold`, or when the card body
   says "force": `kanban_create` for jobs-writer with `skills: [writing-applications]`,
   `idempotency_key` `jobs:application:<project>:<ID>:write`, document language = the opening's language, and
   the other fields of jobs-contract step 4. Otherwise create nothing.
7. Set `status.json` to `analyzed` and `kanban_complete` with one line: decision and score.

## Pitfalls

- Never downgrade a must-have to a nice-to-have.
- Never write CV text or suggest sentences: that is the writer's card.
- A fact you cannot settle from the files (is this a must-have?) becomes an assumption in the fit reason.

## Verification

- `analysis.json` follows the contract in skill jobs-contract, `references/opening-files.md`.
- Every must-have has either evidence with a confidence or a `hard_gap` entry.
- `fit.reason` names the deciding requirement.
- The writer's card exists only for PURSUE at or above the threshold, or with "force".
