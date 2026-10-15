---
name: assigning-models
description: "Assigns a model per bot from connected providers. Use when a squad needs models chosen or revised."
---

# Assigning models

## When to Use

- A squad was planned and `apply` reports lanes without a model.
- The user connects a new provider, or asks to change or audit bot models.

## Procedure

1. Run `python3 scripts/model_advisor.py <squad> --json` (no argument gives the
   lane table). It reads the authenticated providers' model cache and
   `scripts/data/model-roles.yaml`, and returns per bot: lane, model, provider,
   reasoning effort, two alternatives and a one-line reason.
2. If the cache is stale (older than 7 days) or a provider is missing, ask the
   user before running `hermes model --refresh`, then re-run the advisor.
3. Show the table and ask one question: "Accept all, or change any bot?" The
   user's choices win over every suggestion (`docs/decisions.md` D-031).
4. Record the answer in `local/installed.yaml` and feed it to
   `squadctl apply <key> --models <file>` (`scripts/squadctl.py`).
5. Per-card quality needs are not a model assignment: use the card's
   `--model/--provider` override instead of changing the profile
   (`docs/decisions.md` V-07).
6. Review lane rule: when another family is available, the reviewer's model
   comes from a different family than the producer's
   (`scripts/data/model-roles.yaml`, `rule: different-family-from-producer`).

## Pitfalls

- Inventing model names: only ids from the user's authenticated providers exist
  for them; model ids belong in `scripts/data/model-roles.yaml` and
  `local/installed.yaml`, never in prose.
- Editing `model-roles.yaml` in the repo for one user: put overrides in
  `local/model-roles.yaml`, which merges over it.
- Assuming a reasoning effort travels with `--model`: effort is per profile, so
  a lane that needs another effort gets its own profile.
- Leaving auxiliary slots on the main model: they follow the `aux` lane
  (`skills/hermes-platform/references/models-and-auxiliary.md`).

## Verification

- `squadctl plan <key> --json` no longer lists missing models.
- `squadctl doctor` reports every bot's models as assigned.
- The recorded table in `local/installed.yaml` matches what the user accepted.
