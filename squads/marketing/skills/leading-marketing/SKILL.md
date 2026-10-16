---
name: leading-marketing
description: "Runs brand onboarding, planning, briefs and reports. Use when a marketing manager card asks for a brand onboarding, a 90-day plan, a weekly calendar, piece briefs, an approval or a results report."
---

# Leading marketing

Manager procedure; conventions in `brand-contract`. Workers produce; you brief, file cards and take the user's decisions.

## When to Use

- A card from `marketing-plan-week`, `marketing-report`, an onboarding or a user request lands in your profile.
- The `approve` stage of a `piece` chain becomes ready.
- The user replies to a piece or a calendar: `approve 2`, `change 2: ...`, `no to 4`, `published <link>`.
- The user asks for a plan, a calendar, a report, ideas or status.

## Procedure

1. Read the card (`kanban_show`), then `brand.md`, `preferences.md` and the file the card names. The card workspace is the brand folder.
2. **Onboarding**: follow `references/onboarding.md`. When the brand has no project, ask the user to run `scripts/squadctl project add marketing "<Brand>" <path>` and wait.
3. **90-day plan**: run `marketing-plan`; present the three bets and the roadmap in five lines; the plan is approved only when the user says so.
4. **Weekly calendar**: read the plan, the previous calendar and the key dates; write `calendar/<YYYY>-W<WW>.md` from `brand-contract` `templates/calendar.md`. For each planned piece, write `pieces/<piece-id>/brief.md` from `brand-contract` `templates/brief.md`, then file one card per stage of the `piece` chain (research, copy, asset, review, approve), each with `parents: [<previous stage id>]`, per `brand-contract` steps 4-5. File `research` only when the brief says `Research needed: yes`.
5. **Approvals**: on the `approve` card, `kanban_block(kind="needs_input", reason="<two-line summary> <cover asset path>")`. When the user replies, `kanban_comment` the literal reply, `kanban_unblock`, and on the re-run:
   - `approve`: complete with the absolute paths of `copy.md` and every file in `assets/` in `artifacts`; that is the ready-to-post package.
   - `change`: file a `-c<N>` card for the owning stage with the literal request (a copy change also files `asset-c<N>` as its child), then `review-c<N>` and `approve-c<N>`, each a child of the previous; complete this card.
   - `no`: complete this card with `summary` "discarded: <reason>".
   Add one `preferences.md` log line per reply, including `published <link>`.
6. **Publishing**: with `brand.md -> publishing: manual` the user posts the package. When `publishing` names a connector and the user sends `publish <n>` for that piece, file `publish` (assignee marketing, key suffix `publish`) with the user's literal confirmation in the body.
7. **Reports**: read the exports in `data/inbox/`; write `reports/<YYYY-MM>.md`: what worked, what did not and why, matched per piece through `utm_content`, closing with three numbered decisions. Judge with `marketing-mindset`. With no new data, say so and name the missing export. Then `kanban_block(kind="needs_input", reason="<report path> + the three decisions")` so the user sees it (step 8).
8. **Blocked cards**: a board run cannot message the user; a `needs_input` block reaches your Bot Chat (the `marketing-watch` cron posts it when no chat filed the chain). Show the user its reason, `kanban_comment` the literal answer, then `kanban_unblock`.
9. **Pause**: `pause <brand>` creates `PAUSE` in the brand folder; `resume <brand>` deletes it. It stops the weekly and monthly gates, not a running chain.

## Pitfalls

- Filing a chain without a brief, or a `research` card without `Research needed: yes`.
- Editing copy, assets or `brand.md` wording yourself instead of filing a card to the worker that owns it.
- Presenting a piece before the `review` card completes with `approve`.
- A message about a brand that does not name the brand.
- More pieces than `brand.md -> weekly_quota`, or channels outside `brand.md -> channels`.

## Verification

- Every card you file follows `brand-contract` steps 4-5; each stage card is a `parents` child of the previous one.
- `brand.md` is `active` only after the user approved it.
- Every user reply has one `preferences.md` log line and one completed or new card.
- The report names its data window and the sample size behind every rate.
