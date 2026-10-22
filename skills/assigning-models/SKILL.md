---
name: assigning-models
description: "Assigns a model per bot from connected providers. Use when a squad needs models chosen or revised."
---

# Assigning models

## When to Use

- `plan` notes list `no model assigned` for a bot or lane.
- The user connects a new provider, or asks to change or audit bot models.

## Procedure

1. Run `scripts/hpy model_advisor.py <key> --json > local/models-<key>.json`
   (`<key>` is a squad key or `builder`; `--help` documents the fields). It
   detects the authenticated providers from Hermes itself; never ask the user
   which providers they have.
2. Providers the user never wants recommended go one slug per line in
   `local/providers-exclude.txt`; the advisor lists them as `excluded` and
   never picks them. Re-run step 1 after editing it.
3. If the advisor reports the cache stale or a provider missing, ask the user
   to run `hermes -p <bot> model --refresh` in their terminal, then re-run
   step 1.
4. Survey, never skipped, also on reinstall and update: show the table (bot,
   lane, model, provider, effort, cost, why), then one `clarify` call with one
   question per bot (batches of five): choices are the pick first (marked
   recommended), then its `alternatives`; "Other" takes any connected model.
   The advisor already puts economical models first: a `cost: high` model
   appears as the pick only on a `critical` lane, or when nothing cheaper is
   connected (its reason says so). Never upgrade a non-critical bot to a premium
   model on your own; offer it as a choice. The user's choices win. Write each
   change into `local/models-<key>.json` (`model`, `provider`, `reasoning`).
5. When the user puts the reviewer on the producer's model family, say it
   breaks `scripts/data/model-roles.yaml` -> `lanes.review.rule` and ask once.
   When the advice has a `fallback` list (a pick runs on a `quota_limited`
   provider), show it with the table: it applies to every bot of the install
   and to their children. The user may edit, drop (`fallback: []`) or keep it.
6. On OK run `scripts/hpy squadctl.py apply <key> --models local/models-<key>.json`
   (`--self` instead of `<key>` for the builder). `apply` saves the choice in
   `local/installed.yaml` and gives every bot every provider the user
   connected: each API key from the root or builder env file (copied into the
   bot's env file, mode 600, never printed) and each user-installed provider
   plugin. A `credentials <NAME>` note is a provider the user has not
   connected yet: they connect it (`hermes model`), then apply again.

## Pitfalls

- Editing `scripts/data/model-roles.yaml` for one user: put overrides in
  `local/model-roles.yaml`, which merges over it.
- Expecting the effort to follow `--model`: default effort is per profile;
  per-model overrides go in `agent.reasoning_overrides` (profile `config.yaml`).
- Expecting a card to pin effort: `hermes kanban create`/`set-model` carry only
  `--model`/`--provider`; per-card `reasoning_effort` is writable only from the
  kanban dashboard (`skills/hermes-platform/references/kanban.md`).
- A model change for one card is not a bot assignment: use the card's
  `--model`/`--provider`.

## Verification

- `scripts/hpy squadctl.py plan <key> --json` notes list no `no model assigned`.
- `scripts/hpy squadctl.py doctor` reports `<bot>:models` as `assigned` and no
  `<bot>:provider-plugin` warning.
- `local/installed.yaml` -> `bots`, `lanes` and `fallback` match what the user
  accepted; each bot's `config.yaml` has the same `fallback_providers` and
  `delegation.fallback_providers`.
