# Cost levers

## Contents

- [Prompt cost](#prompt-cost)
- [Model cost](#model-cost)
- [Zero-token paths](#zero-token-paths)

## Prompt cost

- Every enabled skill adds an index line to every prompt; the description is cut
  at 60 characters (`agent/skill_utils.py`, `SKILL_PROMPT_DESC_LIMIT`). Fewer,
  tighter skills mean cheaper turns (`website/docs/user-guide/features/skills.md`).
- Profiles created with `--no-skills` and pruned to role-relevant skills skip the
  ~90 bundled skills other profiles carry
  (`website/docs/user-guide/features/skills.md`; `scripts/squadctl.py`).
- Tool search defers rarely used tools out of the always-on prompt
  (`website/docs/user-guide/features/tool-search.md`).
- Context compression keeps long sessions affordable; it runs on the
  `auxiliary.compression` model, so pin that slot to a cheap model
  (`website/docs/user-guide/configuration.md`).

## Model cost

- Auxiliary slots (titles, summaries, curator, judges) default to the main
  model; pointing them at the `aux` lane is the cheapest structural win
  (`website/docs/user-guide/configuration.md`; `scripts/data/model-roles.yaml`).
- Delegation children burn most of a run's tokens; pin `delegation.model` to a
  cheap model and keep judgment in the parent
  (`website/docs/user-guide/features/delegation.md`).
- Per-card `--model` overrides put quality spend on the few cards that need it
  instead of a whole profile (`website/docs/user-guide/features/kanban.md`).
- Reasoning effort is per profile; a lane that needs another effort gets its own
  profile (`docs/decisions.md` V-07).

## Zero-token paths

- Cron gate scripts print `{"wakeAgent": false}` and cost no LLM tokens
  (`website/docs/user-guide/features/cron.md`).
- `--no-agent` cron jobs never wake a model at all
  (`hermes cron create --help`).
- `--monitor-script` hashes a cheap source and suppresses unchanged runs
  (`hermes cron create --help`).
- `kanban_comment` wakes nobody (`docs/decisions.md` D-025).
