# Hooks

## Contents

- [Gateway event hooks](#gateway-event-hooks)
- [Plugin hooks](#plugin-hooks)
- [Squad usage](#squad-usage)

## Gateway event hooks

- Gateway event hooks are a directory with `HOOK.yaml` + `handler.py` under the
  profile home; shell hooks are a `hooks:` block in the profile's `config.yaml`
  (`website/docs/user-guide/features/hooks.md`).
- Placing the files is the opt-in
  (`website/docs/user-guide/features/hooks.md`, "Trust model: placing the files
  is the opt-in").
- Events cover gateway startup, sessions, agent turns, reactions and slash
  commands; the catalog is `website/docs/user-guide/features/hooks.md`,
  "Available Events".
- A startup checklist example (BOOT.md) is in the same page's tutorial
  (`website/docs/user-guide/features/hooks.md`).

## Plugin hooks

- Plugin hooks are Python callbacks a plugin registers with
  `ctx.register_hook()`; events include `pre_tool_call`, `post_tool_call`,
  `pre_llm_call`, `post_llm_call`, `pre_verify`, `on_session_start`,
  `on_session_end`, `subagent_start`, `subagent_stop`, `gateway_platform_event`
  and the kanban task observers. The full set is `hermes_cli/plugins.py`
  (`VALID_HOOKS`) (`website/docs/user-guide/features/hooks.md`, "Plugin Hooks").
- Plugins can also register cache-safe system prompt sections and streaming
  output hooks (`website/docs/user-guide/features/hooks.md`).
- Observer hooks for external integrations:
  `website/docs/developer-guide/observer-hooks.md`.

## Squad usage

- Squads ship no hooks; behavior belongs in skills and cron gate scripts
  (`scripts/squadctl.py` only writes config keys, skills, plugins, MCP, cron).
- A plugin hook can guard writes: `security-guidance` warns on write_file/patch
  by default and refuses when `SECURITY_GUIDANCE_BLOCK=1`
  (`plugins/security-guidance/__init__.py`;
  `website/docs/user-guide/features/built-in-plugins.md`).
- Hook changes need the user's OK like any plugin change (`AGENTS.md` -> Rules).
