# Hooks

## Contents

- [Gateway event hooks](#gateway-event-hooks)
- [Plugin hooks](#plugin-hooks)
- [Squad usage](#squad-usage)

## Gateway event hooks

- Gateway event hooks are shell/Python snippets placed in a hooks directory;
  placing the files is the opt-in (`website/docs/user-guide/features/hooks.md`,
  "Trust model: placing the files is the opt-in").
- Events cover boot and gateway dispatch; the catalog of available events is in
  `website/docs/user-guide/features/hooks.md`, "Available Events".
- A startup checklist example (BOOT.md) is in the same page's tutorial
  (`website/docs/user-guide/features/hooks.md`).

## Plugin hooks

- Plugin hooks are Python callbacks a plugin registers: `pre_tool_call`,
  `post_tool_call`, `pre_llm_call`, `post_llm_call`, `pre_verify`,
  `on_session_start`, `on_session_end`, `on_session_finalize`,
  `on_session_reset`, `agent_loop_stopped`, `subagent_start`, `subagent_stop`,
  `pre_gateway_dispatch`, `post_gateway_admission`, `gateway_platform_event`,
  `pre_approval_request`, `post_approval_response`, `on_human_input_request`
  (`website/docs/user-guide/features/hooks.md`, "Plugin Hooks").
- Plugins can also return cache-safe system prompt sections and streaming
  output hooks (`website/docs/user-guide/features/hooks.md`).
- Observer hooks for external integrations:
  `website/docs/developer-guide/observer-hooks.md`.

## Squad usage

- Squads ship no hooks; behavior belongs in skills and cron gate scripts
  (`scripts/squadctl.py` only writes config keys, skills, plugins, MCP, cron).
- A plugin hook may refuse tool calls (for example `security-guidance` on
  write_file/patch), which is the lightest way to add a guard rail
  (`website/docs/user-guide/features/built-in-plugins.md`).
- Hook changes need the user's OK like any plugin change
  (`docs/decisions.md` C-02).
