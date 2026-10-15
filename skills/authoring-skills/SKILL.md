---
name: authoring-skills
description: "Writes skills to the format budgets. Use when a squad or the builder needs a new or revised skill."
---

# Authoring skills

## When to Use

- A procedure repeats in cards and should stop being re-derived each time.
- A squad or the builder lacks a skill for a bounded job.

## Procedure

1. Read `skills/hermes-platform/references/skills-format-and-sources.md` and the
   upstream authoring guide (`website/docs/developer-guide/creating-skills.md`
   in the local Hermes tree).
2. Structure: progressive disclosure. `SKILL.md` holds the procedure; detail
   lives one level down in `references/*.md`; deterministic work lives in
   `scripts/` with `--help`.
3. Frontmatter: `name` equals the directory (kebab-case gerund, ≤ 40 chars) and
   `description` is third person — capability clause ≤ 57 chars, then
   "Use when ...", ≤ 250 chars total (`scripts/skill_lint.py`).
4. Body sections in order: When to Use, Procedure, Pitfalls, Verification. No
   filler.
5. Budgets: lead/builder SKILL.md ≤ 150 lines, worker ≤ 120, the
   `hermes-platform` index ≤ 80; references ≤ 200 lines, one level deep, with a
   Contents heading when over 100 lines (`scripts/skill_lint.py`).
6. Ship exactly 3 eval scenarios in `evals/evals.json`
   (`tests/fixtures/skills/good/building-widgets/evals/evals.json` shows the
   shape).
7. Cite every platform fact with its docs path; run
   `hermes skills inspect <id>` before referencing any skill identifier.
8. Gate: `python3 scripts/skill_lint.py <skill-dir>` must exit 0.

## Pitfalls

- Model ids in any file of the skill: they belong only in
  `scripts/data/model-roles.yaml` and `local/installed.yaml`.
- Prose scripts: a script the model rewrites per machine is not deterministic
  (`docs/decisions.md` V-03).
- Nested reference folders or a second skill inside a skill directory: both
  fail lint rules `ref-depth` and `children-allowed`.
- Spanish or mixed-language text: files are English only; the linter fails a
  stopword ratio above 3%.

## Verification

- `skill_lint.py <skill-dir>` exits 0.
- Every deterministic step has a script that runs with `--help` and does the
  job end to end.
- The 3 evals cover the happy path, a failure and a refusal or escalation case.
