---
name: changing-bots
description: "Edits one bot's tools, skills or schedule. Use when a bot is added, changed, split or retired."
---

# Changing bots

## When to Use

- The user wants a bot to gain or lose toolsets, skills, plugins, MCP servers,
  connectors, schedules or its lane.
- A bot is redundant, or a new bot must split out of an existing one.

## Procedure

1. Restate the change in one line and find what it touches: the manifest
   (`squad.yaml` / `builder.yaml`), profile config, skills, cron.
2. Ship the change through the overlay: write
   `local/squads/<key>/squad.yaml` with just the changed fields; merge order is
   repo manifest < local overlay < `local/installed.yaml`
   (`scripts/squadctl.py`).
3. Run `scripts/hpy squadctl.py plan <key> --json`, show the diff, and
   apply only after the user's explicit OK.
4. When the change alters role or permissions, re-check D-001 with
   `skills/designing-squads`.
5. Removing a bot: drop it from the overlay and `apply`; for a whole squad use
   `squadctl uninstall <key>`, which exports backups first.

## Pitfalls

- Editing a profile's config by hand: change the overlay and `apply`.
- Editing `skills/` in a worker profile: squad skills are copied; the source of
  truth is the repo (or overlay) and reaches the bot on the next `apply`.
- Adding a cron job without a gate: every agent cron needs its gate script or
  `agent: false`.
- Granting passthrough to a bot that reads the web: credentials go only on the
  bot that calls the API.

## Verification

- `plan <key> --json` after apply reports `unchanged`.
- `hermes -p <bot> config get` and `hermes -p <bot> cron list` show the new
  values.
- `squadctl doctor` is clean for that bot.
