# Toolsets

## Toolsets and config

- A toolset is a named group of tools; the full table is
  `website/docs/reference/toolsets-reference.md`.
- `platform_toolsets.cli` lists the toolsets of CLI, TUI and Desktop chats; Desktop sessions also get
  the client toolsets `project`, `desktop_ui` and `catalog`. `platform_toolsets.cron` lists those of
  agent cron runs (`cron-and-gates.md`). Dispatcher-spawned kanban workers get their lifecycle tools
  automatically.
- Off by default, on only when listed in a saved `platform_toolsets` list: `kanban`, `discord`,
  `discord_admin`, `spotify`, `video`, `video_gen`, `x_search`, `a2a`. A gateway chat creates cards
  only with `kanban` in `platform_toolsets.<platform>`; a change applies to new chats.
- `agent.disabled_toolsets` applies after `platform_toolsets` and removes a toolset everywhere.
- `hermes -p <bot> tools list|enable|disable <names...>` edits the `cli` platform (`--platform` picks
  another); `enable` and `disable` also take MCP `server:tool` names.

## Squad usage

- Every bot starts from the toolsets the installed Hermes gives a fresh default profile
  (`squadctl.py` -> `base_toolsets`, read from the runtime), minus `always_disabled`, minus `OPT_IN`
  (image_gen, tts, computer_use, connections), minus `memory` (it follows the manifest's `memory:`),
  plus kanban. Workers also lose `MANAGER_ONLY` (clarify, vision, browser, cronjob). `toolsets:` in a
  manifest adds to that base.
- A worker drops a base toolset only with `withhold:` for a permission boundary, and only `terminal`,
  `web`, `delegation`, `session_search` or `code_execution`. A manager never withholds. A bot that
  withholds `delegation` has no delegation lane.
- `agent.disabled_toolsets` = `always_disabled + (MANAGED - bot toolsets)`. `always_disabled` never
  shares a tool with the base: `search` is `web_search`, so disabling it removes web search even when
  `web` is on.
- Every bot's `delegation.model` comes from its `delegation.lane`, `research` unless the manifest names
  another.

## Notes

- `catalog` (`manage_catalog`) installs Desktop catalog picks through an approval card and exists only
  in Desktop sessions; `agent.disabled_toolsets: [catalog]` removes it.
- `web_search` belongs to `web` and `search`, not `browser`, so disabling `browser` cannot strip it.
- `browser_vault` rides with `browser` and is deferred by default.
