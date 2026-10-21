# Kanban

## Contents

Board and cards; Per-card flags; Linking and support cards; Goal-mode cards; Worker lifecycle;
Review lane; Dispatcher config.

## Board and cards

- Boards and cards come from the `kanban` toolset and the `hermes kanban` CLI; the dispatcher in the
  gateway assigns `ready` cards to the assignee profile.
- Statuses: `triage`, `todo`, `scheduled`, `ready`, `running`, `review`, `blocked`, `done`,
  `archived`. The kanban kernel owns transitions; workers change status only through `kanban_*` tools.
- The dispatcher spawns `hermes -p <assignee> --cli --accept-hooks [--skills ...] [-m/--provider]
  [--reasoning] --toolsets ... chat -q "work kanban task <id>"` inside the task's workspace with
  `HERMES_KANBAN_TASK`, `HERMES_KANBAN_DB`, `HERMES_KANBAN_BOARD`, `HERMES_KANBAN_WORKSPACE` and
  `HERMES_PROFILE` set. The worker reads the body with `kanban_show`.
- Board resolution: `--board <slug>`, then `HERMES_KANBAN_BOARD`, then `~/.hermes/kanban/current`,
  then `default`; every `kanban_*` tool takes an optional `board`.

## Per-card flags

`hermes kanban create`:

- `--model` / `--provider`: pin this card to another model; `hermes kanban set-model <id> <model>
  --provider <p>` changes it later. There is no reasoning-effort flag on `hermes kanban create`,
  `set-model` or the `kanban_create` tool. Per-card depth exists in the data model
  (`tasks.reasoning_effort`, which makes the dispatcher pass `--reasoning <level>` to the worker) but
  the only writer is the kanban dashboard's task create/PATCH `reasoning_effort`. From the CLI the
  paths for another depth are the bot's `agent.reasoning_effort` (per model:
  `agent.reasoning_overrides`), `delegation.reasoning_effort` for `delegate_task` children,
  `hermes cron create --reasoning-effort` for cron jobs, or a dedicated profile.
- `--skill <name>` (repeatable): force-load a skill into the worker; the name must exist on the
  assignee's profile.
- `--parent <id>` (repeatable): scheduling gate and the handoff channel from a completed card to the
  new one.
- `--goal` / `--goal-max-turns N`: run the worker in a goal loop (Goal-mode cards).
- `--idempotency-key`: an existing non-archived card with the key is returned instead of a duplicate.
- `--workspace`: `scratch` (default), `worktree`, `worktree:<path>`, `dir:<path>`. `scratch` is
  deleted when the card completes: only files declared as `artifacts` in `kanban_complete` or
  `kanban_request_review` survive. `dir:` needs an absolute path. `worktree` is kept.
  `--project <id-or-slug>` anchors the worktree under the project's primary repo (`projects.md`).
- `--completion-contract`: `local-only` (default) or `OWNER/REPO` / an exact PR URL. A PR contract
  completes only when the PR head's required checks pass, with `metadata.published_pr` set.
- Also: `--assignee`, `--body` / `--body-file`, `--branch`, `--tenant`, `--priority`, `--triage`,
  `--max-runtime`, `--max-retries`, `--initial-status`, `--created-by`, `--json`.
- The `kanban_create` tool names them `parents`, `skills`, `workspace_kind` (`scratch`, `dir`,
  `worktree`) + `workspace_path`, `idempotency_key`, `goal_mode`, `model`, `provider`.

## Linking and support cards

- `kanban_link(parent_id, child_id)` gates the child behind the parent; linking a running child is
  refused unless it is the worker's own card.
- A worker blocked on its card that files a support card links the support card as the parent of its
  own card (`kanban_link(parent_id=<support>, child_id=<own card>)`), then
  `kanban_block(kind="dependency")`. Never link the other way: a support card gated behind the card
  it should unblock never runs, and neither does the blocked card.

## Goal-mode cards

- `/goal <text>` loops one chat session until a judge says done; it never creates, claims or moves a
  card.
- A card created with `--goal` (`goal_mode`) runs the same loop inside its worker session;
  `kanban_complete` and `kanban_request_review` pass the judge first, `kanban_schedule` is refused,
  and `kanban_block` accepts only `dependency` or `needs_input`.
- Completion contracts (`outcome`, `verification`, `constraints`, `boundaries`, `stop_when`),
  `/subgoal` and quality gates: `website/docs/user-guide/features/goals.md` in the Hermes source.

## Worker lifecycle

- `kanban_block` requires `reason`; `kind` is `dependency`, `needs_input`, `capability` or
  `transient`. `dependency` with no open parent is recorded as `needs_input`. The same kind blocked
  twice in a row escalates the card to `triage`.
- Exiting 0 while the task is still `running` is a protocol violation. A failed worker exits `1`
  (ordinary failure), `75` (`EX_TEMPFAIL`: rate limit, quota, 5xx, timeout; requeued without a
  failure tick) or `78` (`EX_CONFIG`: rejected credential, model or TLS; the card parks `blocked` on
  the first occurrence).
- `delegate_task` children of a worker are fenced from the board: `kanban_complete`,
  `kanban_request_review` and board writes refuse inside them. The worker itself closes the card.
- A terminal event resumes the gateway or TUI session that created the card
  (`kanban.auto_subscribe_on_create`, default true).
- Squad chains express stages as dependent cards (`scripts/kanban_chain.py`, `squadctl chain`).
- `kanban_schedule(reason)` / `hermes kanban schedule <id> [reason]` parks a card in `scheduled`; it
  resumes only when unblocked (`hermes kanban unblock <id>`). There is no time-based start: the
  `--scheduled-at` / `--at` forms in the docs are not in the CLI.

## Review lane

- `kanban_request_review(summary, metadata, reviewer=<profile>)`: `running` or `ready` -> `review`,
  reassigned to `reviewer` (must be an installed profile). Not a block: review cycles never trip the
  unblock-loop counter.
- With `kanban.review_dispatch: true` the dispatcher claims `review` cards and spawns the reviewer
  with the card's skills plus `sdlc-review`.
- The reviewer ends with `kanban_complete` (approved -> `done`) or `kanban_request_changes(reason)`
  (back to the implementer: `ready` when every parent is done, else `todo`).
- A worker with a pre-created QA child card completes instead; requesting review as well would
  duplicate the lane.
- A squad reviewer is pruned to its declared skills: keep `bundled:sdlc-review`, or give the card a
  `--skill` the reviewer has. A worker whose every forced skill is missing fails at start.

## Dispatcher config

Root config only (`hermes config set kanban.<key>`): the gateway dispatcher reads the default
profile, never a bot profile. Read the live values with `hermes config get kanban`.

| Key | Default | Effect |
|---|---|---|
| `dispatch_in_gateway` | `true` | The gateway runs the dispatcher |
| `dispatch_interval_seconds` | `60` | Seconds between ticks |
| `review_dispatch` | `true` | Auto-claim `review` cards (see Review lane) |
| `failure_limit` | `2` | Consecutive spawn_failed, timed_out or crashed runs before auto-block |
| `dispatch_stale_timeout_seconds` | `14400` | Reclaim a card running longer than this whose last heartbeat is missing or over 1 h old; `0` = off |
| `max_in_progress` | unset | Host cap across boards; unset = MemTotal / 512 MiB clamped to 2-8, no cap on macOS |
| `max_in_progress_per_profile` | unset | Per-profile cap; squads set none |
| `dispatch_profiles` | unset | Profiles this home may claim on a shared `kanban.db` |
| `auto_decompose`, `auto_decompose_per_tick` | `true`, `3` | Run the decomposer on `triage` cards |
| `orchestrator_profile`, `default_assignee` | `""` | Profile for decomposed root cards and for unmatched assignees; `""` = default |
| `reconcile_orphans` | `true` | Requeue `running` cards with broken claim bookkeeping |
| `auto_subscribe_on_create` | `true` | The creating session gets terminal events |

A worker that runs past an hour keeps its claim through the automatic heartbeat; a long manual loop
calls `kanban_heartbeat`.
