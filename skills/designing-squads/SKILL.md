---
name: designing-squads
description: "Turns a user need into a local squad.yaml. Use when creating, scaling or reshaping a squad."
---

# Designing squads

## When to Use

- The user asks for a squad no shipped squad covers, or wants to reshape one.
- A new permission boundary, market or workflow appears that existing bots
  cannot serve.

## Procedure

1. Read `skills/hermes-platform/references/`:
   `profiles-and-distributions.md`, `toolsets.md`, `kanban.md`,
   `cron-and-gates.md`, `delegation.md`.
2. Interview in batches of at most 5 questions: goal, what reaches the user,
   what the user decides, what is irreversible, where credentials live.
3. Check shipped squads first (`squads/*/squad.yaml`); if one fits with
   personalization, install it instead of designing a new one.
4. Create bots only for one of these reasons (`docs/decisions.md` D-001): a
   permission boundary, independent judgment, a different reasoning effort, or
   context size. Everything else is a skill, subagent or script.
5. One visible lead per squad, named after the squad key; workers are hidden,
   run one card at a time and hold only the toolsets their role needs
   (`docs/decisions.md` V-02, V-12). At most 5 bots.
6. Assign each bot a lane: a key of `scripts/data/model-roles.yaml` -> `lanes`.
7. Declare toolsets, squad skills, keeps, plugins, MCP, connectors,
   passthrough (names only), delegation, memory and cron per bot in
   `squads/<key>/squad.yaml` (schema: `squads/_schema/squad.schema.json`).
8. Define chains as stage lists (`stage`, `assignee`, `skill`, optional `when`
   and `lane`) and cron jobs with a gate script or `agent: false`
   (`docs/decisions.md` V-14).
9. Write `souls/<bot>.md` (rules `soul-lines`, `soul-chars`), the squad skills
   and a README of at most 120 lines.
10. Validate: `scripts/hpy squadctl.py plan <key> --json`, then
    `scripts/hpy skill_lint.py squads/<key>`.

## Pitfalls

- A profile per specialist when only the model differs: use a per-card model
  override instead (`docs/decisions.md` V-07).
- Chains that need the user's decision without asking them: irreversible steps
  (apply, send, publish, deploy) always wait for the user's explicit OK.
- Schedules without a gate: every agent cron gets a `wakeAgent` gate
  (`skills/hermes-platform/references/cron-and-gates.md`).

## Verification

- `plan <key> --json` reports a valid spec and names every unresolved model.
- `scripts/hpy skill_lint.py squads/<key>` exits 0.
- The design fits in one sentence per bot: why that bot exists as a separate
  profile.
