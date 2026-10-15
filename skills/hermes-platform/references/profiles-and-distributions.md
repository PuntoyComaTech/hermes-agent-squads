# Profiles and distributions

## What a profile is

- A profile is an independent agent: its own `config.yaml`, `SOUL.md`, sessions,
  skills, memory and channels under `~/.hermes/profiles/<name>/`
  (`website/docs/user-guide/profiles.md`). One gateway serves many profiles:
  `gateways-and-messaging.md`.
- Commands take `-p <profile>`; without it they use the sticky profile set by
  `hermes profile use`, else the default
  (`website/docs/reference/cli-commands.md`).

## Creating and removing profiles

- `hermes profile create <name> --no-skills --no-alias --description ...`
  creates an empty, unaliased profile; `--no-skills` refuses to combine with
  any `--clone*` flag (`website/docs/reference/profile-commands.md`). Seeding
  details: `skills-format-and-sources.md` -> Bundled, official and hub skills.
- `--clone` copies `config.yaml`, `.env`, `SOUL.md`, skills, the curated
  memories and the memory provider's config; sessions, `state.db` and cron jobs
  are not copied (`website/docs/reference/profile-commands.md`). Squad tooling
  never clones, because `.env` holds secret values (`docs/decisions.md` V-10).
- `hermes profile export <name> -o <file>` writes a tarball without `.env` or
  `auth.json`; `hermes profile delete <name> --yes` removes a profile
  (`website/docs/reference/profile-commands.md`). Squad tooling exports before
  any delete and never deletes project folders (`scripts/squadctl.py`).

## Profile distributions

- `hermes profile install <source>` installs a profile from a git URL or a local
  directory whose root holds `distribution.yaml`; flags: `--name`, `--alias`
  (shell wrapper), `--force` (overwrite a same-name profile, user data kept),
  `-y` (`hermes profile install --help`;
  `website/docs/user-guide/profile-distributions.md`).
- `distribution_owned` in the manifest lists exactly the paths the distribution
  copies and later updates; without it (legacy) the whole payload is owned
  except user paths such as `memories`, `sessions` and `local`
  (`hermes_cli/profile_distribution.py`, `_owned_entries`).
- `hermes profile update <name>` re-fetches the recorded source and overwrites
  distribution-owned files plus the skills and cron jobs it ships; skills and
  cron jobs the user added stay. User data (memories, sessions, auth, `.env`) is
  never touched, and `config.yaml` is kept unless `--force-config`
  (`hermes profile update --help`).
- Squad state lives under the builder profile's `local/` (`installed.yaml`,
  backups), which install and update never write (`USER_OWNED_EXCLUDE`,
  `hermes_cli/profile_distribution.py`; `docs/decisions.md` V-01).
