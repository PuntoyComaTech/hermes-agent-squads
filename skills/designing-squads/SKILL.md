---
name: designing-squads
description: "Designs a new local squad as a squad.yaml. Use when the user needs a squad no shipped squad covers."
---

# Designing squads

## When to Use

- The user asks for a squad no shipped squad covers.
- A new permission boundary, market or workflow appears that existing bots
  cannot serve.

## Procedure

1. Read `skills/hermes-platform/references/`:
   `profiles-and-distributions.md`, `toolsets.md`, `kanban.md`,
   `cron-and-gates.md`, `delegation.md`.
2. Interview in batches of at most 5 questions: goal, what reaches the user,
   what the user decides, what is irreversible, where credentials live.
3. Check shipped squads first (`squads/*/squad.yaml`). If one fits, install it
   (`skills/installing-squads`) and adapt it with an overlay
   (`skills/changing-bots`).
4. Pick the key: one short lowercase English word not used under `squads/` or
   `local/squads/`.
5. Create a bot only for one of these reasons (`docs/decisions.md` D-001): a
   permission boundary, independent judgment, a different reasoning effort, or
   context size. Everything else is a skill, subagent or script.
6. One manager `<key>` (`role: manager`, title `<Name> manager`): the only bot
   the user talks to and the one that adds Projects for the squad. Workers are
   `<key>-<role>` (`role: worker`, `memory: false`) with only the toolsets their
   role needs (V-02, V-12, C-11). All bots are visible; squadctl files the
   manager under the `Managers` Desktop section and the workers under the
   squad's own section. At most 5 required bots; a sixth sets `optional: true`
   and installs only with `squadctl apply <key> --with <name>`.
7. Lane per bot: a key of `scripts/data/model-roles.yaml` -> `lanes`.
8. Write `local/squads/<key>/squad.yaml` against
   `squads/_schema/squad.schema.json`: `schema: 2`, `key`, `name`, `version`,
   `hermes_requires`, `board`, `section`, `manager`, `bots`, `chains`. Pass
   credentials as env names in `passthrough`, never values.
9. Chains are stage lists (`stage`, `assignee`, optional `skill`, `when`,
   `lane`). A cron job has `schedule` and `script`; add `agent` (`lane`,
   `skill`, `reasoning`) only when the script is a wake gate (V-14).
10. Write `local/squads/<key>/souls/<bot>.md` per bot, the squad skills in
    `local/squads/<key>/skills/` (`skills/authoring-skills`) and cron scripts in
    `local/squads/<key>/scripts/`.
11. Validate: `scripts/hpy squadctl.py plan <key> --json`, then
    `scripts/hpy skill_lint.py local/squads/<key>`. Install with
    `skills/installing-squads`.

## Topology

One rule, used everywhere (D-001, D-005, V-07):

- `delegate_task` subagents are ephemeral: same model as the caller, no board,
  no own credentials, gone when the turn ends.
- Kanban workers are persistent profiles: own model, toolsets and credentials,
  asynchronous, each needing a board.
- Single bot with only `delegate_task` work -> Projects only, no board.
- Single bot with async, long, cron or human-in-the-loop work, or per-task
  models -> its own board (it files cards to itself).
- Manager + workers = a squad -> one board per squad, one Project per repo.

Skills follow one rule too: a hub skill is installed only after quoting its
source and licence and getting the user's explicit OK (`{id, confirm}` in
`skills.keep`); a squad's own skills ship with it and need no quote.

## Pitfalls

- A profile per specialist when only the model differs: use a per-card model
  override (`docs/decisions.md` V-07).
- A chain stage that acts without the user: irreversible steps (apply, send,
  publish, deploy) wait for the user's explicit OK.
- Writing the squad under `squads/`: that tree is distribution-owned. Local
  squads live in `local/squads/<key>/`; publishing one is
  `skills/contributing-upstream`.

## Verification

- `scripts/hpy squadctl.py plan <key> --json` exits 0 and its notes name every
  lane without a model.
- `scripts/hpy skill_lint.py local/squads/<key>` exits 0.
- Each bot has one sentence saying why it is a separate profile.
