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
6. Check every hand-off between stages: for each value one skill reads from
   another stage's output (a store file, a key, a status), the producing skill
   must have an explicit step that writes it. A consumer with no producer step
   fails silently at runtime. Prove each hand-off with one run: execute the
   producer, then the consumer, on a fixture, and assert the consumer sees the
   value; reading both SKILL.md files does not catch a missing writer.
7. Create every skill that `squad.yaml` names before `squadctl plan`: plan warns
   on a named skill with no SKILL.md, and the bot runs without it.
8. Run `scripts/hpy skill_lint.py <skill-dir>`, then the repository's test
   suite: lint checks the shape of a skill, the contract tests check what a
   bot-facing doc may say (cited sentences, internal ids, line budgets).

## Pitfalls

- Model ids in any file of the skill: they belong only in
  `scripts/data/model-roles.yaml` and `local/installed.yaml`.
- A prose script, which the model rewrites per machine: ship a real script.
- A line that changes nothing the bot does: harmless warnings, upstream issue
  numbers, bug-tracker remarks. Not written in skills, SOULs, notes or
  memory (lint rule `no-issue-notes`).
- A doc that reaches bot context (anything a squad copies into a profile,
  `skills.keep` included) carries the rule in words, never a citation to a
  decision log or an internal id: the contract test rejects citations in
  bot-loaded files, and an id means nothing to a bot that never sees the log.
- A new required input on a checker or script (a file, a key, a flag): add it
  to the shared helper that builds the test fixture, not to each test. Per-test
  copies diverge and the tests you did not edit fail on the next run.
- Replacing a paragraph in a reference doc: note the sentences before and after
  it first, then grep the file for their distinctive tokens. A replace anchored
  on the paragraph's last line swallows the sentence that followed it, and the
  assertion on that sentence fails while the doc reads clean.
- A test that only asserts a helper's return value: assert the outcome the user
  sees (a rejected link, a written file, a blocked submission). The helper can
  pass while the feature is broken.
- Wrapping a test run in the coreutils `timeout` binary: macOS does not ship
  it, the command never starts, and silence reads as a pass. Run pytest
  directly.
- Writing a skill file you have not read whole: read it in one call first. A
  paged read is refused by the write guard, and a partial read overwrites the
  lines you did not see.
- Scoping a skill wider than the probes: cover the surface that was executed
  and label the rest unverified. Confident syntax nobody ran is what the user
  calls invented.
- Telling the user a fact is documented before that sentence exists: write it,
  then name the file. A claim that a file holds text it does not reads as
  invented work.

## Verification

- `scripts/hpy skill_lint.py <skill-dir>` exits 0, and the repository's
  contract tests pass on every file the skill ships.
- Every deterministic step calls a script that answers `--help` and does the
  job end to end.
