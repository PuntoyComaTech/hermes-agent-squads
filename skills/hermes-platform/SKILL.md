---
name: hermes-platform
description: "Indexes verified Hermes Agent primitives. Use when designing or changing a squad, bot or Hermes config."
---

# Hermes platform

## When to Use

- Before writing or editing a `squad.yaml`, a SOUL, a skill or a profile config.
- Before answering how profiles, kanban, cron, plugins, MCP or gateways behave.
- When a squad design depends on a Hermes behavior (per-card models, Projects,
  delivery targets, delegation).

## Procedure

1. Read `skills/hermes-local-notes/SKILL.md` when it exists; its facts win
   over `references/`.
2. Pick the topic from the index below and read that reference file. Act only
   on cited facts.
3. When a reference and the live Hermes disagree (`hermes <cmd> --help`), the
   live Hermes wins. Append `<topic>: <fact> (<source path>, <date>)` to
   `skills/hermes-local-notes/SKILL.md`, creating it with frontmatter
   `name: hermes-local-notes` and `description: "Lists local Hermes facts that
   override hermes-platform. Use when a reference and live Hermes disagree."`.
   Then propose the fix upstream (`skills/contributing-upstream`).
4. For anything deeper, read the cited `website/docs/...` path under the Hermes
   source root (the `sys.path` entry in `hermes --print-runtime-command`).

## Reference index

| Topic | File |
|---|---|
| Profiles, distributions, install/update | `references/profiles-and-distributions.md` |
| SOUL.md, context files, ui_meta | `references/soul-and-context-files.md` |
| Skill format and sources | `references/skills-format-and-sources.md` |
| Toolsets | `references/toolsets.md` |
| Bot Mode, Desktop, Bots pane, rail | `references/bot-mode-and-desktop.md` |
| Bot-to-bot messaging | `references/bot-to-bot.md` |
| Kanban cards, workers, per-card flags | `references/kanban.md` |
| Cron, gates, delivery | `references/cron-and-gates.md` |
| Delegation and the advisor pattern | `references/delegation.md` |
| Models, auxiliary slots, providers | `references/models-and-auxiliary.md` |
| MCP servers | `references/mcp.md` |
| Tool search and connectors | `references/tool-search-and-connectors.md` |
| Plugins and the catalog | `references/plugins.md` |
| Approvals and security | `references/approvals-and-security.md` |
| Hooks | `references/hooks.md` |
| Projects | `references/projects.md` |
| Gateways and messaging | `references/gateways-and-messaging.md` |
| Cost levers | `references/cost-levers.md` |

## Pitfalls

- A flag or config key from memory: re-read the reference or run `--help`.
- Desktop-internal facts (rail, Bots pane) cite `apps/desktop/src/...` source
  files and change without a docs update.
- UNVERIFIED notes are hypotheses, not behavior.

## Verification

- Each reference line carries a citation to `website/docs/...` or a source file.
- `scripts/hpy skill_lint.py skills/hermes-platform` exits 0.
- A claim the reference cannot cite is deleted or marked UNVERIFIED.
