---
name: designing-squads
description: "Designs a new local squad or single bot as a squad.yaml. Use when no shipped squad covers the user's need."
---

# Designing squads

## When to Use

- The user asks for a squad or a single bot no shipped squad covers.
- A new permission boundary, market or workflow appears that existing bots
  cannot serve.

## Procedure

1. Read `skills/hermes-platform/references/`:
   `profiles-and-distributions.md`, `toolsets.md`, `kanban.md`,
   `cron-and-gates.md`, `delegation.md`.
2. Interview in batches of at most 5 questions: goal, what reaches the user,
   what the user decides, what is irreversible, which external APIs are called.
   Never ask which model providers exist: `skills/assigning-models` detects
   them.
3. Check shipped squads first (`squads/*/squad.yaml`). If one fits, install it
   (`skills/installing-squads`) and adapt it with an overlay
   (`skills/changing-bots`).
4. Pick the key: one short lowercase English word not used under `squads/` or
   `local/squads/`.
5. Decide the bots and the board with Rules and Topology below. A single bot
   is a squad whose only bot is the manager `<key>`.
6. Lane per bot: a key of `scripts/data/model-roles.yaml` -> `lanes`.
7. Write `local/squads/<key>/squad.yaml` against
   `squads/_schema/squad.schema.json`: `schema: 2`, `key`, `name`, `version`,
   `hermes_requires`, `board` (only when Topology says so), `section`,
   `manager`, `bots`, `chains`.
8. Chains are stage lists (`stage`, `assignee`, optional `skill`, `when`,
   `lane`). A cron job has `schedule` and `script`; add `agent` (`lane`,
   `skill`, `reasoning`) only when the script is a wake gate.
9. Write `local/squads/<key>/souls/<bot>.md` per bot, the squad skills in
   `local/squads/<key>/skills/` (`skills/authoring-skills`) and cron scripts in
   `local/squads/<key>/scripts/`. Capabilities from catalogs:
   `skills/finding-capabilities`.
10. Validate: `scripts/hpy squadctl.py plan <key> --json`, then
    `scripts/hpy skill_lint.py local/squads/<key>`. Install with
    `skills/installing-squads`.

## Rules

Enforced by `squadctl` and `skill_lint.py`.

- A bot exists only for a permission boundary, independent judgment, a
  different reasoning effort, or context size. Everything else is a skill,
  subagent or script.
- One manager per squad: profile name `<key>`, `role: manager`, title
  `<Name> manager`. It is the only bot the user talks to and the one that adds
  Projects.
- Workers: `<key>-<role>`, `role: worker`, only the toolsets their role
  needs. Memory is on by default (squadctl adds the `memory` toolset); the
  SOUL has one line on what it stores: job pitfalls and fixes, never secrets.
  `memory: false` only for a bot that must keep nothing between cards.
- Skills a bot writes with `skill_manage` are `learned`: `squadctl plan`
  lists them per bot and `apply` never removes them.
- All bots are visible. squadctl files the manager under the Desktop section
  `Managers` and the workers under the squad's `section`.
- At most 5 required bots; another bot sets `optional: true` and installs only
  with `squadctl apply <key> --with <name>`.
- Credentials: env names in `passthrough` (never values), only on the bot that
  calls that API, never on a bot with `web` or `browser`.
- CLIs a bot drives: `requires.apps`. `squadctl doctor` reports each one
  installed and logged in (`gh auth login`, `cf auth login`, `wrangler login`,
  once, by the user) and never prints a probe's output.
- Squad skills ship in `local/squads/<key>/skills/` and need no quote; hub
  skills and community plugins follow `skills/finding-capabilities` steps 3-5.

## Topology

- `delegate_task` subagents are ephemeral: the caller's model unless
  `delegation.model` pins one, no board, no own credentials, gone when the
  turn ends.
- Kanban workers are persistent profiles: own model, toolsets and credentials,
  asynchronous, each on a board.
- Single bot with only `delegate_task` work: no `board`; Projects only.
- Single bot with async, long, cron or human-in-the-loop work, or per-card
  models: its own `board` (it files cards to itself).
- Manager + workers: one `board` per squad; one Project per repo or folder
  (`skills/managing-projects`).

## Pitfalls

- A profile per specialist when only the model differs: use a per-card model
  override.
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
