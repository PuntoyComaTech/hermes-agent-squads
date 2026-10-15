# Toolsets

## Contents

- [What a toolset is](#what-a-toolset-is)
- [Enabling and disabling](#enabling-and-disabling)
- [Tool discovery notes](#tool-discovery-notes)

## What a toolset is

- A toolset is a named group of tools; the full table of toolsets and their
  tools is `website/docs/reference/toolsets-reference.md`.

## Enabling and disabling

- `platform_toolsets.cli` lists the toolsets enabled for interactive sessions;
  `platform_toolsets.cron` for cron agent runs
  (`website/docs/user-guide/configuration.md`; `scripts/squadctl.py`).
- `agent.disabled_toolsets` removes toolsets; squad tooling sets it to
  `always_disabled + (MANAGED - bot.toolsets)` so a bot can never gain a toolset
  the manifest does not declare (`scripts/squadctl.py`;
  `scripts/data/always-disabled.yaml`).
- The always-disabled list for squad bots, the reason per name and the registry
  check are in the header of `scripts/data/always-disabled.yaml`
  (`tests/test_contracts.py`; `docs/decisions.md` C-07).
- `hermes tools enable <names...> --profile <bot>` toggles the toolset registry
  alongside the config keys (`scripts/squadctl.py`).

## Tool discovery notes

- `catalog` (plugin catalog search) exists only in desktop-app sessions and can
  be removed with `agent.disabled_toolsets: [catalog]`
  (`website/docs/reference/toolsets-reference.md`).
- `web_search` deliberately does not belong to the `browser` toolset, so
  disabling `browser` cannot strip it
  (`website/docs/reference/toolsets-reference.md`).
