# 0004 · Builder

> Migration (`base/08-updates.md`). Run by the `default` session in Hermes Desktop: it creates the builder, which runs every later migration.

## What and why
Creates the `builder` base bot (`07-builder.md`): it installs and creates squads, makes configuration changes and applies updates, with its own channel. The orchestrator then sends configuration requests to it.

## Already applied if
`hermes profile list` shows `builder`, its channel answers, and `registry.md` has the "Base: builder" row.

## Steps
1. Folders: `{{ROOT}}/squads/`, `builder/skills/` (from `0001`). Add `.cache/` to `.gitignore`. Shallow-clone the docs into `.cache/hermes-docs` (`07-builder.md` §2).
2. Models: ask the builder's model and effort (`07-builder.md` §5).
3. Create the profile per `07-builder.md` §2 and §3; write its five skills (`07-builder.md` §4) into `builder/skills/`. Copy the provider's API key.
4. Channel: guide the user to create a second Telegram bot (@BotFather) or a second Discord application; token, allowed users and home channel in the builder's `.env`. Enable kanban for that platform. The default gateway multiplexes it: the builder must not set `gateway.standalone: true` or reuse another profile's token (`user-guide/multi-profile-gateways.md`). Ask the user to restart the gateway (`hermes gateway restart` or Desktop) and verify with `hermes gateway status`.
5. Orchestrator: apply `04-orchestrator.md` §3 step 2 (configuration and new squads go to the builder) to its `SOUL.md`, and the "Control" section of `plans/squads/<key>/03-bots.md` to each installed official squad's orchestration skill (`04-orchestrator.md` §5).
6. Run `scripts/registry.py` (the builder row appears). Record the migration in `installed.yaml`. Tell the user to move the builder into the "Base" Section in Hermes Desktop.

## Conflicts
Three-way comparison of the orchestrator's `SOUL.md` and each orchestration skill (`08-updates.md` §4). If the chosen channel app is WhatsApp only, the builder uses its Hermes Desktop chat; say so.

## Verify
`hermes -p builder send --to <channel> "Hi {{name}}, I'm your builder."` arrives; the user writes "what can you do?" and the builder answers with its five skills; asking the orchestrator "change the search time" makes it point to the builder.

## Rollback
`hermes profile delete builder` (after the user's ok), remove its bot token, `git -C {{ROOT}} revert` the migration commit, `hermes profile import` the exported orchestrator.
