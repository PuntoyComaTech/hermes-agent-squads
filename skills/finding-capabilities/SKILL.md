---
name: finding-capabilities
description: "Searches plugins, skills, MCP and connectors. Use when a squad needs a capability from a catalog."
---

# Finding capabilities

## When to Use

- A bot needs a tool, skill or integration nobody ships yet.
- The user asks what the ecosystem offers for a task (video, deploy, SEO).

## Procedure

1. Search: `scripts/hpy catalog_search.py "<query>" ["<query>" ...]
   [--kind plugin,skill,mcp] [--hub] [--json]`. Connector names match under
   `mcp`.
2. Prefer a bundled or official skill over a hub one, and a skill over a
   plugin when the job is procedural.
3. Skill candidate: run `hermes skills inspect <identifier>` and read its trust
   level, author, licence and SKILL.md preview.
4. Community plugin: read `plugin-catalog/<name>.yaml` in the Hermes tree.
   Presence there is the trust signal; risky behavior is disclosed in its
   `description` (`plugin-catalog/README.md` rule 13).
5. Quote that disclosure and the licence to the user verbatim and get an explicit
   OK. Non-commercial (PolyForm NC) and per-seat (Remotion) licences get their
   own question.
6. Declare the result in the squad manifest or overlay
   (`squads/_schema/squad.schema.json`): a `skills.keep` entry (`bundled:`,
   `official:<cat>/<name>`, `hub:`, `local:`), a `plugins.enable` entry or an
   `mcp` server. Add a `confirm` text to any item that needs the user's OK.
7. Run `scripts/hpy squadctl.py plan <key> --json`; each `confirm` item shows
   under `pending`. After the OK: `apply <key> --confirm <id>`.

## Pitfalls

- Installing first and asking later: hub skills and community plugins install
  only after the user's OK with the disclosure shown.
- Giving a capability to the whole squad: it goes on the bot whose role needs
  it.
- Connectors on a bot with `web` or `browser`: put them only on bots without
  either.

## Verification

- The identifier resolves (`hermes skills inspect` or a catalog entry).
- `scripts/hpy squadctl.py plan <key> --json` shows the install action or the
  `pending` item.
- Each `--confirm <id>` matches an item the user approved.
