# Hooks

## Gateway event hooks

- A gateway hook is a directory `<profile home>/hooks/<name>/` holding
  `HOOK.yaml` (non-empty `events` list) and `handler.py`; placing the files is
  the opt-in (`website/docs/user-guide/features/hooks.md`, "Trust model: placing
  the files is the opt-in").
- Events include gateway startup, session start/end/reset/compress, agent
  start/step/end, reactions and slash commands (`command:*`)
  (`website/docs/user-guide/features/hooks.md`, "Available Events").
- Shell hooks are a separate `hooks:` block in the profile's `config.yaml`
  (`website/docs/user-guide/features/hooks.md`, "Shell Hooks").

## Plugin hooks

- Plugins register Python callbacks with `ctx.register_hook()`; events include
  `pre_tool_call`, `post_tool_call`, `pre_llm_call`, `post_llm_call`,
  `pre_verify`, `on_session_start`, `on_session_end`, `subagent_start`,
  `subagent_stop`, `gateway_platform_event` and the kanban observers. The full
  set is `VALID_HOOKS` in `hermes_cli/plugins.py`
  (`website/docs/user-guide/features/hooks.md`, "Plugin Hooks").
- Plugins can also register cache-safe system prompt sections
  (`ctx.register_system_prompt_section`) and streaming observers
  (`on_stream_start`, `on_stream_delta`, `on_stream_end`).
- Observer hooks for external integrations:
  `website/docs/developer-guide/observer-hooks.md`.

## Squad usage

- Squads ship no hooks; behavior belongs in skills and cron gate scripts
  (`scripts/squadctl.py` writes config keys, skills, plugins, MCP and cron only).
- A write guard comes from a plugin: `plugins.md` -> Where plugins come from
  (`security-guidance`).
- Hook changes need the user's OK like any plugin change (`AGENTS.md` -> Rules).
