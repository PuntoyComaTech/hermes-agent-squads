---
name: hermes-platform
description: "Indexes verified Hermes Agent primitives. Use when designing or changing a squad, bot or Hermes config."
---

# Hermes platform

Every fact in `references/` cites a
`website/docs/...` path or a source file in the Hermes tree; facts that could
not be verified are marked UNVERIFIED and must not be relied on.

## When to Use

- Before writing or editing a `squad.yaml`, a SOUL, a skill or a profile config.
- Before answering how profiles, kanban, cron, plugins, MCP or gateways behave.
- When a squad design depends on a Hermes behavior (per-card models, Projects,
  delivery targets, delegation).

## Procedure

1. Pick the topic from the index below and read that reference file.
2. Act only on cited facts. When the reference and the live Hermes disagree,
   the live Hermes wins: run the CLI (`hermes <cmd> --help`), record the fact
   in `skills/hermes-local-notes/` and propose it upstream
   (`skills/contributing-upstream`).
3. For anything deeper, read the cited docs path in the local Hermes tree
   (`website/docs/...` inside the Hermes install).

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

- Never trust a memory of a flag or config key; re-read the reference or run
  `--help`.
- Desktop-internal facts (rail, Bots pane) cite `apps/desktop/src/...` source
  files and change without a docs update.
- UNVERIFIED notes are hypotheses, not behavior.

## Verification

- Each reference line carries a citation to `website/docs/...` or a source file.
- `scripts/hpy skill_lint.py skills/hermes-platform` exits 0.
- A claim the reference cannot cite is deleted or marked UNVERIFIED.
