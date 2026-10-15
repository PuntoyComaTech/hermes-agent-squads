---
name: authoring-skills
description: "Writes skills that pass skill_lint.py. Use when a squad or the builder needs a new or revised skill."
---

# Authoring skills

## When to Use

- A procedure repeats in cards and should stop being re-derived each time.
- A squad or the builder lacks a skill for a bounded job.

## Procedure

1. Load the bundled skill `hermes-agent-skill-authoring` and read
   `skills/hermes-platform/references/skills-format-and-sources.md`.
2. Layout: `SKILL.md` holds the procedure; detail lives one level down in
   `references/*.md`, each linked from the step that needs it; deterministic
   work lives in `scripts/` with parameters and `--help`.
3. Rules: `scripts/hpy skill_lint.py --rules` (name, description, line budgets,
   body sections When to Use, Procedure, Pitfalls, Verification, English only).
4. Ship exactly 3 scenarios in `evals/evals.json`: the happy path, a failure,
   and a refusal or escalation.
5. Cite every platform fact with its docs or source path. Run
   `hermes skills inspect <id>` before naming any skill identifier.
6. Run `scripts/hpy skill_lint.py <skill-dir>`.

## Pitfalls

- Model ids in any file of the skill: they belong only in
  `scripts/data/model-roles.yaml` and `local/installed.yaml`.
- A prose script, which the model rewrites per machine: ship a real script
  (`docs/decisions.md` V-03).

## Verification

- `scripts/hpy skill_lint.py <skill-dir>` exits 0.
- Every deterministic step calls a script that answers `--help` and does the
  job end to end.
