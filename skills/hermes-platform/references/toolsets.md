# Toolsets

## Toolsets and config

- A toolset is a named group of tools; the full table is
  `website/docs/reference/toolsets-reference.md`.
- `platform_toolsets.cli` lists the toolsets of CLI, TUI and Desktop chats;
  `platform_toolsets.cron` those of agent cron runs
  (`website/docs/user-guide/features/kanban.md`;
  `website/docs/user-guide/features/cron.md`). Dispatcher-spawned kanban
  workers get their lifecycle tools automatically.
- `agent.disabled_toolsets` applies after `platform_toolsets` and removes a
  toolset everywhere (`website/docs/user-guide/configuration.md`, "Global
  Toolset Disable").
- `hermes -p <bot> tools enable <names...>` enables toolsets for the `cli`
  platform (`--platform` picks another) (`hermes tools enable --help`).

## Squad usage

- Squad tooling sets `agent.disabled_toolsets` to `always_disabled + (MANAGED -
  bot.toolsets)`, so a bot never gains a toolset its manifest does not declare
  (`scripts/squadctl.py`). The list and the reasons are in the header of
  `scripts/data/always-disabled.yaml` (`docs/decisions.md` C-07).

## Notes

- `catalog` (plugin catalog search) exists only in desktop-app sessions;
  `agent.disabled_toolsets: [catalog]` removes it
  (`website/docs/reference/toolsets-reference.md`).
- `web_search` belongs to `web` and `search`, not `browser`, so disabling
  `browser` cannot strip it (`website/docs/reference/toolsets-reference.md`).
