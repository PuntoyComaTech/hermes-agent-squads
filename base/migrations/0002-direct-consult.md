# 0002 · Direct consultation

> Migration (`base/08-updates.md`). Run by the builder (or the `default` session before `0004`).

## What and why
Adds the direct consultation rule (`01-principles.md` §2.3, design in `02-architecture.md` §5.1): a specialist missing a datum opens a support card for the bot that owns it and blocks on it, instead of relaying through the orchestrator. Replaces marketing's fast path (comment plus a separate reply task), whose answer never resumed the asking card.

## Already applied if
`{{ROOT}}/AGENTS.md` contains `CONSULT ·` and every installed squad's `AGENTS.md` lists its consult pairs.

## Steps
1. `{{ROOT}}/AGENTS.md`: apply `plans/base/01-principles.md` §2 rule by rule with the three-way comparison. Rule 3 ("Ask before assuming" in installations before this migration) becomes the consultation rule; rule 8 drops its single-model sentence (models are per bot, `07-builder.md` §5).
2. For each installed official squad (`installed.yaml`): apply the consultation rule with its pairs from the squad `AGENTS.md` in `plans/squads/<key>/02-architecture.md` to `projects/<key>/AGENTS.md`, and the CONSULT mode and consultation lines of the SOULs and skills in `plans/squads/<key>/03-bots.md` to the installed `SOUL.md` files and skills.
3. Marketing only: remove the fast path (comment + reply task) from `projects/marketing/AGENTS.md` and its skills; the base rule covers it.
4. Own squads (`source: own`): tell the user the rule is in the base `AGENTS.md` and offer to add consult pairs with `config-change`.

## Conflicts
Three-way comparison per section (`08-updates.md` §4). A rule the user wrote about asking the orchestrator: show it next to the new rule and ask.

## Verify
`rg "CONSULT ·" {{ROOT}}/AGENTS.md` matches; each installed squad's `AGENTS.md` lists pairs; `rg -i "fast path" {{ROOT}}/projects/marketing` finds nothing. Optional: create a test support card and check the asking card goes to `todo` with a `dependency_wait` event (`hermes kanban show <id>`), then archive both.

## Rollback
`git -C {{ROOT}} revert` the migration commit; `hermes profile import` of the exported profiles if a SOUL changed.
