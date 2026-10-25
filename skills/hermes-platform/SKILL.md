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
- Before planning a Desktop plugin, a new pane or any UI that reads across
  profiles: `references/desktop-plugins.md`.

## Procedure

1. Read `skills/hermes-local-notes/SKILL.md` when it exists; its facts win
   over `references/`.
2. Pick the topic from the index below and read that reference file. The
   references were verified against the Hermes version in
   `scripts/data/doc-sources.json` (`verified_against`); on a newer Hermes,
   check a fact you act on against `--help` or the source.
3. When a reference and the live Hermes (`hermes <cmd> --help`, the source)
   disagree, the live Hermes wins. Append `<topic>: <fact> (<date>)` to
   `skills/hermes-local-notes/SKILL.md`, creating it with frontmatter
   `name: hermes-local-notes` and `description: "Lists local Hermes facts that
   override hermes-platform. Use when a reference and live Hermes disagree."`.
   Then propose the fix upstream (`skills/contributing-upstream`).
4. For anything deeper, read `website/docs/` under the Hermes source root:
   the `Install directory:` line of `hermes --version`.

## Reference index

| Topic | File |
|---|---|
| Profiles, distributions, install/update | `references/profiles-and-distributions.md` |
| SOUL.md, context files, ui_meta | `references/soul-and-context-files.md` |
| Skill format and sources | `references/skills-format-and-sources.md` |
| Toolsets | `references/toolsets.md` |
| Browser backends, real profile, signing in for bots | `references/browser.md` |
| Bot Mode, Desktop, Bots pane, rail | `references/bot-mode-and-desktop.md` |
| Bot-to-bot messaging | `references/bot-to-bot.md` |
| Kanban cards, workers, per-card flags | `references/kanban.md` |
| Cron, gates, delivery | `references/cron-and-gates.md` |
| Delegation and the advisor pattern | `references/delegation.md` |
| Models, auxiliary slots, providers, credential pools, prompt cache | `references/models-and-auxiliary.md` |
| Built-in memory and memory providers | `references/memory.md` |
| MCP servers | `references/mcp.md` |
| Tool search and connectors | `references/tool-search-and-connectors.md` |
| Plugins and the catalog | `references/plugins.md` |
| Desktop plugins: surfaces, host doors, limits | `references/desktop-plugins.md` |
| Approvals and security | `references/approvals-and-security.md` |
| Hooks | `references/hooks.md` |
| Projects | `references/projects.md` |
| Gateways and messaging | `references/gateways-and-messaging.md` |

## Pitfalls

- A flag or config key from memory: re-read the reference or run `--help`.
- `hermes config get <key>` warns "not a recognized config key" for valid
  keys outside the schema (`agent.reasoning_effort`): read those with
  `hermes config show` or the profile's `config.yaml`.
- UNVERIFIED notes are hypotheses, not behavior.
- A Desktop plugin surface from memory: check `apps/desktop/src/sdk/index.ts`;
  the SDK doc page omits side effects core runs.

## Verification

- The answer matches `hermes <cmd> --help` on this machine.
- `scripts/hpy skill_lint.py skills/hermes-platform` exits 0.
