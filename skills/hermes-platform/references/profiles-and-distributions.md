# Profiles and distributions

## Contents

- [What a profile is](#what-a-profile-is)
- [Creating profiles](#creating-profiles)
- [Profile distributions](#profile-distributions)
- [Install, update, uninstall](#install-update-uninstall)

## What a profile is

- A profile is an independent agent: its own `config.yaml`, `SOUL.md`, sessions,
  skills, memory and channels under `~/.hermes/profiles/<name>/`
  (`website/docs/user-guide/profiles.md`).
- One gateway serves many profiles; each keeps its own state
  (`website/docs/user-guide/multi-profile-gateways.md`).
- Commands take `-p <profile>`; without it they use the sticky profile set by
  `hermes profile use`, else the default
  (`website/docs/reference/cli-commands.md`).

## Creating profiles

- `hermes profile create <name>` with `--no-skills --no-alias --description ...`
  creates an empty, unaliased profile (`website/docs/reference/profile-commands.md`).
- `--no-skills` opts out of bundled-skill seeding entirely
  (`website/docs/user-guide/features/skills.md`).
- `--clone` copies `config.yaml`, `.env`, `SOUL.md`, skills, the curated
  memories and the memory provider's config from the active profile; sessions,
  `state.db` and cron jobs are not copied
  (`website/docs/reference/profile-commands.md`). Squad tooling never uses it:
  it copies `.env` (secret values) into the new profile (`scripts/squadctl.py`).
- `hermes profile export <name> -o <file>` writes a backup tarball before any
  prune or delete (`website/docs/reference/profile-commands.md`).

## Profile distributions

- `hermes profile install <source>` installs a whole profile from a git URL or a
  local directory whose root holds `distribution.yaml`
  (`website/docs/user-guide/profile-distributions.md`;
  `hermes profile install --help`).
- The manifest's `distribution_owned` list names exactly the paths the
  distribution copies and later updates; without the list (legacy) the whole
  payload is owned. `scripts/` lands in `$HERMES_HOME/scripts/` where cron
  needs it (`hermes_cli/profile_distribution.py`).
- Install flags: `--name` (override profile name), `--alias` (shell wrapper),
  `--force` (overwrite same-name profile, user data preserved), `-y`
  (`hermes profile install --help`).

## Install, update, uninstall

- `hermes profile update <name>` re-fetches the recorded source and overwrites
  distribution-owned files and the skills and cron jobs the distribution ships.
  User data (memories, sessions, auth, `.env`) is never copied by install or
  update; `config.yaml` is preserved unless `--force-config`
  (`hermes profile update --help`).
- Skills or cron jobs the user added themselves survive an update
  (`hermes profile update --help`).
- Squad tooling keeps its own state under the builder profile's `local/`
  (`installed.yaml`, backups) (`scripts/squadctl.py`).
- `hermes profile delete <name>` removes a profile; squad tooling exports a
  backup first and never deletes project folders (`scripts/squadctl.py`).
