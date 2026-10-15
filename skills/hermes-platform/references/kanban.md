# Kanban

## Contents

- [Board and cards](#board-and-cards)
- [Per-card flags](#per-card-flags)
- [Worker lifecycle](#worker-lifecycle)
- [Exit codes](#exit-codes)
- [Workspaces and Projects](#workspaces-and-projects)

## Board and cards

- Boards and cards come from the `kanban` toolset and the `hermes kanban` CLI;
  the dispatcher in the gateway assigns `ready` cards to the assignee profile
  (`website/docs/user-guide/features/kanban.md`).
- Lifecycle: `ready` → `running` → `review` / `blocked` / `done` / `archived`;
  workers never own that truth (`website/docs/user-guide/features/kanban-worker-lanes.md`).
- The dispatcher spawns profile lanes with `hermes -p <assignee> chat -q <prompt>`
  inside the task's pinned workspace, passing `HERMES_KANBAN_TASK`,
  `HERMES_KANBAN_DB`, `HERMES_KANBAN_BOARD`, `HERMES_KANBAN_WORKSPACE` and
  `HERMES_PROFILE` (`website/docs/user-guide/features/kanban-worker-lanes.md`).

## Per-card flags

`hermes kanban create` (`website/docs/user-guide/features/kanban.md`;
`hermes kanban create --help`):

- `--model` / `--provider`: pin just this card to another model (the profile's
  reasoning effort still applies). Later changes: `hermes kanban set-model`.
- `--skill <name>` (repeatable): force-load a skill into the worker; skill names
  must exist on the assignee's profile.
- `--parent <id>` (repeatable): scheduling gate and the context handoff channel
  from a completed card to the new one.
- `--goal` / `--goal-max-turns N`: run the worker in a goal loop; the judge
  checks output against the card's title + body and an unachievable card blocks
  with the judge's reason.
- `--idempotency-key`: dedup; an existing non-archived card with the key is
  returned instead of creating a duplicate.
- Also: `--body/--body-file`, `--workspace`, `--branch`, `--project`, `--tenant`,
  `--priority`, `--triage`, `--max-runtime`, `--max-retries`, `--initial-status`.

## Worker lifecycle

- Workers call `kanban_show`, work in `cd $HERMES_KANBAN_WORKSPACE`, heartbeat
  with `kanban_heartbeat` at least hourly on long runs, and end with
  `kanban_complete`, `kanban_request_review` or `kanban_block`
  (`website/docs/user-guide/features/kanban.md`).
- Exiting 0 while the task is still `running` is a protocol violation
  (`website/docs/user-guide/features/kanban.md`).
- Board notifications reach the creator; squad leads deliver to their Bot Chat
  with `--deliver bot-chat:<lead>` (`scripts/squadctl.py`; plan `docs/decisions.md` V-05).

## Exit codes

- A failed dispatcher-spawned worker exits `1` (ordinary failure), `75`
  (`EX_TEMPFAIL`: rate limit, 5xx, timeout — requeued without a failure tick) or
  `78` (`EX_CONFIG`: rejected credential/model/TLS — terminal, parks the card
  `blocked` on first occurrence) (`website/docs/user-guide/features/kanban.md`,
  "The worker lifecycle").

## Workspaces and Projects

- `--workspace` accepts `scratch`, `worktree`, `worktree:<path>`, `dir:<path>`;
  `--project <slug>` anchors the task's worktree under the project's primary
  repo (`hermes kanban create --help`).
- Squad chains express stages as dependent cards (`scripts/kanban_chain.py`,
  `squadctl chain`).
