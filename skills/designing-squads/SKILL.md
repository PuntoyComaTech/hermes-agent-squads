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
6. Lane per bot: a key of `scripts/data/model-roles.yaml` -> `lanes`. A bot that
   verifies truthfulness or judges quality takes the reasoning lane, never the
   cheap one, and so do its delegated children (`delegation: {lane: ...}`): a
   cheap model passes claims it cannot check.
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

`squadctl` and `skill_lint.py` enforce what they can check (toolsets, schema, skill shape); the rest is yours.

- A bot exists only for a permission boundary, independent judgment, a
  different reasoning effort, or context size. Everything else is a skill,
  subagent or script.
- One manager per squad: profile name `<key>`, `role: manager`, title
  `<Name> manager`. It is the only bot the user talks to and the one that adds
  Projects.
- Workers: `<key>-<role>`, `role: worker`. Every bot gets the Hermes base
  toolsets (`references/toolsets.md` in hermes-platform -> Squad usage);
  `toolsets:` adds, `withhold:` removes a base toolset from a worker only for a
  permission boundary. Never take tools from a manager. Memory is on by default (squadctl adds the `memory` toolset); the
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
- An account a bot must not combine with browsing (mail, a personal feed)
  gets its own worker bot. `withhold` strips a toolset from a worker only, and
  squadctl keeps `clarify`, `vision`, `browser` and `cronjob` on every manager,
  so moving the account up to the manager does not isolate it.
- A bot with the `browser` toolset sets `shared_browser: true` (squadctl
  requires the toolset); no bot browses on a copy of the owner's profile. Give it no connector and no credentials yourself. The
  service already makes the Google mail, files and account hosts unresolvable;
  a `website_blocklist` only catches URLs written literally in a call. The
  owner signs in once per site (`scripts/hpy shared_browser.py login <url>`);
  bots never take turns on a browser: each run gets its own tab.
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
- QA lane: the implementer ends with
  `kanban_request_review(reviewer=<key>-qa)` on its own card; the reviewer
  approves with `kanban_complete` or returns it with `kanban_request_changes`.
  Use a separate chain stage only when QA needs its own card (a deployed
  preview, a different workspace). The reviewer keeps
  `bundled:sdlc-review` (the dispatcher force-loads it on review cards).
  Dispatcher keys: `hermes-platform/references/kanban.md` -> Dispatcher config.
- Open-ended cards (no fixed end state): `goal_mode` with
  `goal_max_turns`; the goal judge gates `kanban_complete` and
  `kanban_request_review`.

## Pitfalls

- A profile per specialist when only the model differs: use a per-card model
  override.
- A cron job that touches a resource the whole machine shares (the one browser,
  a service, a log): give its script a lock and a `did it run` stamp in the
  shared state dir, and make the losing fire exit 0 with a skip line. Managers
  firing at the same minute otherwise multiply the work and log errors the
  watcher escalates to the user.
- A chain stage that acts without the user: irreversible steps (apply, send,
  publish, deploy) wait for the user's explicit OK, per action or once as a
  recorded standing consent with caps that a script enforces.
- A topology or key offered from memory (which toolset a bot can give up,
  which config key takes a list): read `scripts/squadctl.py` constants,
  `squads/_schema/squad.schema.json` or `references/toolsets.md` first. A rule
  the user accepts and the script then refuses costs a whole design round.
- Publishing a shipped squad's contract change (bots, skills, cron, chains)
  without a `distribution.yaml` bump and a CHANGELOG entry: the release gate
  fails. Before any publish a reviewer who did not write the change (another
  model or QA run) reads the result, and the user sees the status first.
- Writing the squad under `squads/`: that tree is distribution-owned. Local
  squads live in `local/squads/<key>/`; publishing one is
  `skills/contributing-upstream`.

## Verification

- `scripts/hpy squadctl.py plan <key> --json` exits 0 and its notes name every
  lane without a model.
- `scripts/hpy skill_lint.py local/squads/<key>` exits 0.
- Each bot has one sentence saying why it is a separate profile.
