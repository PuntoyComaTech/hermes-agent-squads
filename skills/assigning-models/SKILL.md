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
   (`<key>` is a squad key or `builder`; `--help` documents the fields).
2. If the advisor reports the cache stale or a provider missing, ask the user
   to run `hermes -p <bot> model --refresh` in their terminal, then re-run
   step 1.
3. Show the table and ask one question: "Accept all, or change any bot?" The
   user's choices win over every suggestion (`docs/decisions.md` D-031). Write
   each change into `local/models-<key>.json` (`model`, `provider`,
   `reasoning` of that bot or lane).
4. When the user puts the reviewer on the producer's model family, say it
   breaks `scripts/data/model-roles.yaml` -> `lanes.review.rule` and ask once.
5. On OK run `scripts/hpy squadctl.py apply <key> --models local/models-<key>.json`
   (`--self` instead of `<key>` for the builder). `apply` saves the choice in
   `local/installed.yaml`.

## Pitfalls

- Editing `scripts/data/model-roles.yaml` for one user: put overrides in
  `local/model-roles.yaml`, which merges over it.
- Expecting the effort to follow `--model`: default effort is per profile;
  per-model overrides go in `agent.reasoning_overrides` (profile `config.yaml`).
- A model change for one card is not a bot assignment: use the card's
  `--model`/`--provider` (`docs/decisions.md` V-07).

## Verification

- `scripts/hpy squadctl.py plan <key> --json` notes list no `no model assigned`.
- `scripts/hpy squadctl.py doctor` reports `<bot>:models` as `assigned`.
- `local/installed.yaml` -> `bots` and `lanes` match what the user accepted.
