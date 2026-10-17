# Toolsets

## Toolsets and config

- A toolset is a named group of tools; the full table is
  `website/docs/reference/toolsets-reference.md`.
- `platform_toolsets.cli` lists the toolsets of CLI, TUI and Desktop chats;
  `platform_toolsets.cron` those of agent cron runs.
  Dispatcher-spawned kanban
  workers get their lifecycle tools automatically.
- `agent.disabled_toolsets` applies after `platform_toolsets` and removes a
  toolset everywhere.
- `hermes -p <bot> tools enable <names...>` enables toolsets for the `cli`
  platform (`--platform` picks another).

## Squad usage

- Every bot starts from the toolsets the default Hermes profile works with
  (`scripts/squadctl.py` -> `BASE_TOOLSETS`: file, skills, kanban, todo,
  terminal, web, delegation, session_search, code_execution); the manager also
  gets `MANAGER_TOOLSETS` (clarify, vision, browser, cronjob). `toolsets:` in a
  manifest adds to that base; a worker drops a base toolset only with
  `withhold:` for a permission boundary. A manager never withholds.
- `agent.disabled_toolsets` = `always_disabled + (MANAGED - bot toolsets)`.
  `always_disabled` never shares a tool with the base: `search` is
  `web_search`, so disabling it removes web search even when `web` is on.
- Every bot's `delegation.model` comes from its `delegation.lane`, `research`
  (the cheap lane) unless the manifest names another.

## Notes

- `catalog` (plugin catalog search) exists only in desktop-app sessions;
  `agent.disabled_toolsets: [catalog]` removes it.
- `web_search` belongs to `web` and `search`, not `browser`, so disabling
  `browser` cannot strip it.
