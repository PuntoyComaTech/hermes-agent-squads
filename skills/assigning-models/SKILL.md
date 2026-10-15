---
name: assigning-models
description: "Assigns a model per bot from connected providers. Use when a squad needs models chosen or revised."
---

# Assigning models

## When to Use

- A squad was planned and `apply` reports lanes without a model.
- The user connects a new provider, or asks to change or audit bot models.

## Procedure

1. Run `scripts/hpy model_advisor.py <squad> --json`; with no squad it prints
   the lane table (`--help` documents the fields).
2. If the advisor reports the cache stale or a provider missing, ask the user
   to run `hermes -p <bot> model --refresh` in their terminal, then re-run the
   advisor.
3. Show the table and ask one question: "Accept all, or change any bot?" The
   user's choices win over every suggestion (`docs/decisions.md` D-031).
4. Write the accepted table to a file and run
   `scripts/hpy squadctl.py apply <key> --models <file>`.
5. Review lane: `scripts/data/model-roles.yaml` -> `rule: different-family-from-producer`.

## Pitfalls

- Editing `model-roles.yaml` in the repo for one user: put overrides in
  `local/model-roles.yaml`, which merges over it.
- Assuming a reasoning effort travels with `--model`: default effort is per
  profile; per-model overrides go in `agent.reasoning_overrides` (config.yaml).
- Per-card quality needs are not a model assignment: use the card's
  `--model/--provider` override (`docs/decisions.md` V-07).
- Leaving auxiliary slots on the main model: they follow the `aux` lane
  (`skills/hermes-platform/references/models-and-auxiliary.md`).

## Verification

- `squadctl plan <key> --json` no longer lists missing models.
- `squadctl doctor` reports every bot's models as assigned.
- The recorded table in `local/installed.yaml` matches what the user accepted.
