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

1. Write the note to `local/upstream-notes/<date>-<slug>.yaml` with keys
   `file`, `problem`, `evidence`, `fix`. A note is about the repository; the
   user's preferences stay local.
   Never publish local fleets: no names, paths, skills, examples or data from
   squads or bots the repo did not ship (list them in
   `local/private-terms.txt`; `release.py` blocks any match). Generalize the fix
   or keep it local.
2. Explain the finding in plain language and ask: "Should I open a PR to the
   community repository?" Nothing is sent without an explicit yes for that PR
   (`docs/decisions.md` D-029).
3. On yes: `cd local && gh repo fork PuntoyComaTech/hermes-agent-squads --clone`,
   then `git -C local/hermes-agent-squads switch -c fix/<slug>`. Change only
   repository content (a local squad: copy `local/squads/<key>/` to
   `squads/<key>/` and add its README row), show the diff, then
   `gh pr create` with problem, evidence and fix. Examples are fictional and
   values are placeholders.

### Maintainer mode

Active when the user says they maintain the repository and
`gh api repos/PuntoyComaTech/hermes-agent-squads --jq .permissions.push`
prints `true`:

1. Work on a branch of `local/hermes-agent-squads`; keep the diff to the item
   at hand.
2. Bump `distribution.yaml` -> `version` and add a `## <version> - <date>`
   entry to `CHANGELOG.md`.
3. Commit. Once per clone, create the test venv:
   `python3 -m venv .venv && .venv/bin/pip install pytest pyyaml jsonschema`.
4. In `local/hermes-agent-squads`, run
   `scripts/hpy release.py --dry-run --python .venv/bin/python`, then the same
   without `--dry-run`. All gates green: it pushes to main. A red gate: it opens
   a PR (`release.py --help`).

## Pitfalls

- Sending user data, real names, URLs of the user's projects or credentials:
  upstream content is fictional and generic only.
- Bundling unrelated refactors into a fix PR.

## Verification

- The note has `sent: <PR or issue URL>`.
- A maintainer push came from `release.py` with every gate green.
