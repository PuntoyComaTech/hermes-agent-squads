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

1. Record the note: date, file, problem, evidence, proposed fix. Personal
   preferences stay local; a note is about the repository, not the user.
2. Explain the finding in plain language and ask: "Should I open a PR to the
   community repository?" Nothing is sent without an explicit yes **for that
   PR** (`docs/decisions.md` D-029).
3. On yes: fork with `gh`, branch, change only repository content, show the
   diff, then push and open the PR or issue with problem, evidence and fix.
   Never include user data: examples are fictional and values are placeholders.

### Maintainer mode

Active only when `local/maintainer.yaml` exists and `gh auth status` shows an
account with push rights on the repository:

1. Work in the local clone on a branch; keep the diff to the item at hand.
2. Run the gates, in order: `scripts/hpy skill_lint.py` on touched skill
   dirs, `pytest -q` in the test environment, and a temp-root
   `HERMES_HOME=$(mktemp -d) scripts/hpy squadctl.py plan --self --json`.
3. Bump `version` in the touched manifest and add a `CHANGELOG.md` entry.
4. **Push to main only with every check green.** A red check opens a PR instead
   of landing on main; a failing gate is never overridden or retried blindly.
5. Record what landed and where in the same note that started it.

## Pitfalls

- Sending user data, real names, URLs of the user's projects or credentials:
  upstream content is fictional and generic only.
- Pushing to main in user mode: only maintainer mode with green checks may.
- Bundling unrelated refactors into a fix PR.
- Editing files another writer owns in a parallel workstream: commit only your
  own files.

## Verification

- The PR or issue URL is stored and the note is marked `sent: <url>`.
- Maintainer pushes reference the green run of lint, pytest and the temp-root
  plan.
- The repository version and `CHANGELOG.md` agree with what shipped.
