---
name: contributing-upstream
description: "Proposes fixes upstream with the user's OK. Use when a defect or improvement should reach the repository."
---

# Contributing upstream

## When to Use

- A card or session found a plan defect, an installation trap, a changed Hermes
  command or an improvement for the squads repository.
- The user asks to publish a local squad or fix for others.

## Procedure

### User mode (default)

1. Write the note to `local/upstream-notes/<date>-<slug>.yaml`: file, problem,
   evidence, proposed fix. Personal preferences stay local; a note is about the
   repository, not the user.
2. Explain the finding in plain language and ask: "Should I open a PR to the
   community repository?" Nothing is sent without an explicit yes **for that
   PR** (`docs/decisions.md` D-029).
3. On yes: `gh repo fork PuntoyComaTech/hermes-agent-squads --clone`,
   `git switch -c fix/<slug>`, change only repository content, show the diff,
   then `gh pr create` (or an issue) with problem, evidence and fix.
   Never include user data: examples are fictional and values are placeholders.

### Maintainer mode

Active only when `local/maintainer.yaml` exists and `gh auth status` shows an
account with push rights on the repository:

1. Work in the local clone on a branch; keep the diff to the item at hand.
2. Run `scripts/hpy release.py` (`--dry-run` checks without pushing). It gates
   on pytest, skill_lint, the manifest schema and a temp-root `plan` for every
   squad and `--self`, and requires the `distribution.yaml` version bump plus a
   `CHANGELOG.md` entry. All green: pushes to main; a red gate: opens a PR.
3. Record what landed and where in the same note that started it.

## Pitfalls

- Sending user data, real names, URLs of the user's projects or credentials:
  upstream content is fictional and generic only.
- Bundling unrelated refactors into a fix PR.

## Verification

- The PR or issue URL is stored and the note is marked `sent: <url>`.
- A maintainer push is made by `scripts/hpy release.py` with every gate green.
- The repository version and `CHANGELOG.md` agree with what shipped.
