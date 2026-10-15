---
name: changing-bots
description: "Edits one bot's tools, skills or schedule. Use when a bot needs a change, an addition or retirement."
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
3. Run `python3 scripts/squadctl.py plan <key> --json`, show the diff, and
   apply only after the user's explicit OK.
4. `apply` reconciles config keys, `ui_meta`, skills (copied with a sha
   marker), plugins, MCP, SOUL and cron in one pass
   (`scripts/squadctl.py`).
5. When the change alters role or permissions, re-check with
   `skills/designing-squads`: a bot exists only for a permission boundary,
   independence, an effort difference or context size (`docs/decisions.md` D-001).
6. Removing a bot: drop it from the overlay and `apply`; for a whole squad use
   `squadctl uninstall <key>`, which exports backups first.

## Pitfalls

- Editing another profile's config.yaml or profile.yaml by hand: only `ui_meta`
  is written directly; everything else goes through the CLI and `squadctl`
  (`docs/decisions.md` V-10).
- Editing `skills/` in a worker profile: squad skills are copied; the source of
  truth is the repo (or overlay) and reaches the bot on the next `apply`.
- Adding a cron job without a gate: every agent cron needs its gate script or
  `agent: false`.
- Granting passthrough to a bot that reads the web: credentials go only on the
  bot that calls the API.

## Verification

- `plan <key> --json` after apply reports `unchanged`.
- `hermes -p <bot> config get` and `hermes -p <bot> cron list` show the new
  values (always with `-p`).
- `squadctl doctor` is clean for that bot.
