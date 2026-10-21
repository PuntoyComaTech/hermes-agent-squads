# Hooks

## Gateway event hooks

- A gateway hook is a directory `<profile home>/hooks/<name>/` holding `HOOK.yaml` (non-empty `events`
  list) and `handler.py`; placing the files is the opt-in. They are not gated by `plugins.enabled` or
  `plugins.disabled`.
- Events include gateway startup, session start/end/reset/compress, agent start/step/end, reactions
  and slash commands (`command:*`). Under a multi-profile gateway each profile's `hooks/` loads the
  first time an event fires in that profile.

## Shell hooks

- Shell hooks are a `hooks:` block in the profile's `config.yaml`.
- Each new `(event, command)` pair needs consent once, stored in `~/.hermes/shell-hooks-allowlist.json`.
  Non-TTY runs (gateway, cron) skip an unconsented hook with only a warning unless `--accept-hooks`,
  `HERMES_ACCEPT_HOOKS=1` or `hooks_auto_accept: true` is set. Kanban workers are spawned with
  `--accept-hooks`.
- `hermes hooks list|test|doctor|revoke` manage them.
- `hooks.outbound:` posts signed lifecycle events to HTTP endpoints, fire-and-forget.

## Plugin hooks

- Plugins register Python callbacks with `ctx.register_hook()`; events include `pre_tool_call`,
  `post_tool_call`, `pre_llm_call`, `post_llm_call`, `pre_verify`, `on_session_start`,
  `on_session_end`, `subagent_start`, `subagent_stop`, `gateway_platform_event`,
  `pre_gateway_dispatch` and `post_gateway_admission`.
- Kanban hooks, observer-only (return ignored): `kanban_task_claimed` (fires in the dispatcher),
  `kanban_task_completed`, `kanban_task_blocked` (fire in the worker), and `on_kanban_worker_spawned`,
  `on_kanban_worker_exited`, `on_kanban_worker_stale_claim`, `on_kanban_task_updated`,
  `on_kanban_dispatch_tick`.
- `pre_tool_call` can veto a tool: return `{"action": "block", "message": ...}`, or
  `{"action": "approve"}` to force the approval gate; block beats approve.
- Plugins can also register cache-safe system prompt sections (`ctx.register_system_prompt_section`)
  and streaming observers (`on_stream_start`, `on_stream_delta`, `on_stream_end`).
- Observer hooks for external integrations: `website/docs/developer-guide/observer-hooks.md`.

## Squad usage

- Squads ship no hooks; behavior belongs in skills and cron gate scripts (`scripts/squadctl.py` writes
  config keys, skills, plugins, MCP and cron only).
- A write guard comes from a plugin: `plugins.md` -> Where plugins come from (`security-guidance`).
- Hook changes need the user's OK like any plugin change (`AGENTS.md` -> Rules).
