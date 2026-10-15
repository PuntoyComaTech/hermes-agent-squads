# Kanban

## Board and cards

- Boards and cards come from the `kanban` toolset and the `hermes kanban` CLI;
  the dispatcher in the gateway assigns `ready` cards to the assignee profile
  (`website/docs/user-guide/features/kanban.md`).
- Statuses: `triage`, `todo`, `scheduled`, `ready`, `running`, `review`,
  `blocked`, `done`, `archived` (`hermes kanban list --help`). The kanban kernel
  owns transitions; workers change status only through `kanban_*` tools
  (`website/docs/user-guide/features/kanban-worker-lanes.md`).
- The dispatcher spawns `hermes -p <assignee> chat -q <prompt>` inside the
  task's workspace with `HERMES_KANBAN_TASK`, `HERMES_KANBAN_DB`,
  `HERMES_KANBAN_BOARD`, `HERMES_KANBAN_WORKSPACE` and `HERMES_PROFILE` set
  (`website/docs/user-guide/features/kanban-worker-lanes.md`).
- `hermes kanban --board <slug> <command>` selects the board; every `kanban_*`
  tool takes an optional `board` (`hermes kanban --help`;
  `tools/kanban_tools_schemas.py`).

## Per-card flags

`hermes kanban create` (`hermes kanban create --help`):

- `--model` / `--provider`: pin this card to another model; there is no
  reasoning-effort flag. Later changes: `hermes kanban set-model <id> <model>`
  (`website/docs/user-guide/features/kanban.md`, "Per-task model override").
- `--skill <name>` (repeatable): force-load a skill into the worker; the name
  must exist on the assignee's profile.
- `--parent <id>` (repeatable): scheduling gate and the handoff channel from a
  completed card to the new one.
- `--goal` / `--goal-max-turns N`: run the worker in a goal loop; a judge checks
  output against the title and body, and an unachievable or out-of-budget card
  blocks (`website/docs/user-guide/features/kanban.md`).
- `--idempotency-key`: an existing non-archived card with the key is returned
  instead of a duplicate.
- `--workspace`: `scratch` (default), `worktree`, `worktree:<path>`,
  `dir:<path>`. `--project <slug>` anchors the worktree under the project's
  primary repo (`projects.md`).
- Also: `--assignee`, `--body` / `--body-file`, `--branch`, `--tenant`,
  `--priority`, `--triage`, `--max-runtime`, `--max-retries`,
  `--initial-status`, `--created-by`, `--completion-contract`, `--json`.
- The `kanban_create` tool names them `parents`, `skills`, `workspace_kind`
  (`scratch`, `dir`, `worktree`) + `workspace_path`, `idempotency_key`,
  `goal_mode`, `model`, `provider` (`tools/kanban_tools_schemas.py`).

## Worker lifecycle

- Workers call `kanban_show`, work in `$HERMES_KANBAN_WORKSPACE`, call
  `kanban_heartbeat` at least hourly on long runs, and end with
  `kanban_complete`, `kanban_request_review` or `kanban_block`
  (`website/docs/user-guide/features/kanban.md`, "The worker lifecycle").
- `kanban_block` requires `reason`; `kind` is `dependency`, `needs_input`,
  `capability` or `transient` (`tools/kanban_tools_schemas.py`).
- Exiting 0 while the task is still `running` is a protocol violation. A failed
  worker exits `1` (ordinary failure), `75` (`EX_TEMPFAIL`: rate limit, quota,
  5xx, timeout; requeued without a failure tick) or `78` (`EX_CONFIG`: rejected
  credential, model or TLS; the card parks `blocked` on the first occurrence)
  (`website/docs/user-guide/features/kanban.md`, "The worker lifecycle").
- A terminal event resumes the gateway or TUI session that created the card
  (`kanban.auto_subscribe_on_create`, default true;
  `website/docs/user-guide/features/kanban.md`).
- Squad chains express stages as dependent cards (`scripts/kanban_chain.py`,
  `squadctl chain`).
