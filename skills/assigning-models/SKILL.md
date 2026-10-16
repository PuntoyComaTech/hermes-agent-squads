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
4. Show the table and ask one question: "Accept all, or change any bot?" The
   user's choices win over every suggestion. Write
   each change into `local/models-<key>.json` (`model`, `provider`,
   `reasoning` of that bot or lane).
5. When the user puts the reviewer on the producer's model family, say it
   breaks `scripts/data/model-roles.yaml` -> `lanes.review.rule` and ask once.
6. On OK run `scripts/hpy squadctl.py apply <key> --models local/models-<key>.json`
   (`--self` instead of `<key>` for the builder). `apply` saves the choice in
   `local/installed.yaml` and copies a user-installed provider plugin into
   each bot that uses it. A `credentials <NAME>` note is a key the user adds
   to that bot's profile; squadctl never reads or copies key values.

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
- `local/installed.yaml` -> `bots` and `lanes` match what the user accepted.
