# Profiles and distributions

## What a profile is

- A profile is an independent agent: its own `config.yaml`, `SOUL.md`, sessions,
  skills, memory and channels under `~/.hermes/profiles/<name>/`.
  One gateway serves many profiles:
  `gateways-and-messaging.md`.
- Commands take `-p <profile>`; without it they use the sticky profile set by
  `hermes profile use`, else the default.

## Creating and removing profiles

- `hermes profile create <name> --no-skills --no-alias --description ...`
  creates an empty, unaliased profile; `--no-skills` refuses to combine with
  any `--clone*` flag. Seeding
  details: `skills-format-and-sources.md` -> Bundled, official and hub skills.
- `--clone` copies `config.yaml`, `.env`, `SOUL.md`, skills, the curated
  memories and the memory provider's config; sessions, `state.db` and cron jobs
  are not copied. Squad tooling
  never clones, because `.env` holds secret values.
- `hermes profile export <name> -o <file>` writes a tarball without `.env` or
  `auth.json`; `hermes profile delete <name> --yes` removes a profile.
  Squad tooling exports before
  any delete and never deletes project folders.

## Profile distributions

- `hermes profile install <source>` installs a profile from a git URL or a local
  directory whose root holds `distribution.yaml`; flags: `--name`, `--alias`
  (shell wrapper), `--force` (overwrite a same-name profile, user data kept),
  `-y`.
- `distribution_owned` in the manifest lists exactly the paths the distribution
  copies and later updates; without it the whole payload is owned except user
  paths such as `memories`, `sessions` and `local`.
- `hermes profile update <name>` re-fetches the recorded source and overwrites
  distribution-owned files plus the skills and cron jobs it ships; skills and
  cron jobs the user added stay. User data (memories, sessions, auth, `.env`) is
  never touched, and `config.yaml` is kept unless `--force-config`.
- Squad state lives under the builder profile's `local/` (`installed.yaml`,
  backups), which install and update never write (`USER_OWNED_EXCLUDE`).

## Updating Hermes

- A source checkout of the official repo follows the `stable` channel:
  `hermes update` moves only from one published `vX.Y.Z` release to the next.
  Forks and mirrors follow `main`.
- `hermes update --set-channel main` follows every commit; `--set-channel
  stable` returns to releases and pins the checkout to the latest release
  commit, even when that is older. `hermes update --channel main` is one run
  and saves nothing. The choice is stored under `update.installs` in the root
  `config.yaml`.
- `hermes update --check` reports whether an update exists without applying it.
- `hermes update` restarts every gateway, which stops running agents
  (`--no-gateway-restart` defers that): the user runs it, never a bot.
