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
   community repository?" Nothing is sent without an explicit yes for that PR.
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
   `python3 -m venv .venv && env -u PYTHONPATH .venv/bin/pip install pytest pyyaml jsonschema`
   (a Hermes shell exports `PYTHONPATH`, which hides the venv's own packages).
4. In `local/hermes-agent-squads`, run
   `scripts/hpy release.py --dry-run --python .venv/bin/python`, then the same
   without `--dry-run`. All gates green: it pushes to main. A red gate: it opens
   a PR (`release.py --help`). The gates run the full pytest suite (about 9
   minutes): start the release with `terminal(background=true, notify=true)`
   and poll with `process_manage`; do not block on it.
5. Update the builder from the same repo with `scripts/hpy auto_update.py
   --force` (builder profile). Hermes replaces shipped skills whole, so
   auto_update three-way merges each locally edited skill file back: kept when
   the update did not change it, combined when the changes are separate, and
   on an overlap the new version is installed and the edit stays in
   `local/backups/edits-<timestamp>/`. Read every `Needs you:` line, diff each
   backup against the repo copy, and move the generic rules into the repo skill
   in the next release; squad-, fleet- or user-specific rules stay local.
   Installed copies are not the source.

## Pitfalls

- Sending user data, real names, URLs of the user's projects or credentials:
  upstream content is fictional and generic only.
- Bundling unrelated refactors into a fix PR.
- Test fixtures that write fake binaries or `#!` shebangs must quote the
  interpreter and repo paths: a checkout path with a space (a projects folder
  with a space in its name) splits the shebang and fails the test on a
  machine where it passes elsewhere.
- A Hermes shell exports `PYTHONPATH`, which hides the test venv's packages:
  run pip and pytest with `env -u PYTHONPATH`.
- Generic lessons learned on this machine go upstream; lessons that name a
  squad, fleet or user stay in local notes. Never clear a merge conflict by
  overwriting the installed skill: the other side's edit is the only copy of
  that lesson (`auto_update.py` keeps it in the backup).

## Verification

- The note has `sent: <PR or issue URL>`.
- A maintainer push came from `release.py` with every gate green.
