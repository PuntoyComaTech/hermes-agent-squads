# Profiles and distributions

## What a profile is

- A profile is an independent agent: its own `config.yaml`, `SOUL.md`, sessions, skills, memory and
  channels under `~/.hermes/profiles/<name>/`. One gateway serves many profiles:
  `gateways-and-messaging.md`.
- Commands take `-p <profile>`; without it they use the sticky profile set by `hermes profile use`,
  else the default.
- `hermes profile info <name>` shows a profile's distribution manifest (version, requirements,
  source); `hermes profile describe` writes `description` and `display_name` into `profile.yaml`.

## Creating and removing profiles

- `hermes profile create <name> --no-skills --no-alias --description ...` creates an unaliased
  profile with no bundled skills (it still seeds the directories, an empty `.env` and the default
  `SOUL.md`); `--no-skills` refuses to combine with any `--clone*` flag. Seeding details:
  `skills-format-and-sources.md` -> Bundled, official and hub skills.
- `--clone` copies `config.yaml`, `.env`, `SOUL.md`, skills, `plugins/`, `MEMORY.md`, `USER.md` and the
  memory provider's config; sessions, `state.db` and cron jobs are not copied, and messaging channels
  are stripped unless `--clone-channels`. Squad tooling never clones, because `.env` holds secret
  values.
- `hermes profile export <name> -o <file>` writes a tarball without `.env` or `auth.json`;
  `hermes profile delete <name> --yes` removes a profile. Squad tooling exports before any delete and
  never deletes project folders.

## Profile distributions

- `hermes profile install <source>` installs a profile from a git URL (`github.com/owner/repo`,
  https, ssh) or a local directory whose root holds `distribution.yaml`; flags: `--name` (`default` is
  refused), `--alias` (shell wrapper), `--force`, `-y` (skip the manifest preview).
- Install fails fast when the running Hermes does not satisfy `hermes_requires` (`>=`, `<=`, `==`,
  `!=`, `>`, `<`; bare version = `>=`). Update checks it again.
- `env_requires` (`name`, `description`, `required`, `default`) generates the installed
  `.env.EXAMPLE` when the distribution ships none; `.env` is never shipped.
- `distribution_owned` lists exactly the paths the distribution copies and later updates; without it
  the whole payload is owned. User paths (`memories`, `sessions`, `plans`, `workspace`, `home`,
  `backups`, `cache`, `local`) and credential stores are never owned, even when listed. Symlinks in a
  distribution are rejected before any write.
- `hermes profile install --force` replaces `config.yaml` with the distribution's copy and keeps user
  data and user skills. `hermes profile update <name>` re-fetches the recorded source and overwrites
  distribution-owned files and shipped skills; `config.yaml` is kept unless `--force-config`. User
  data (memories, sessions, auth, `.env`) is never touched.
- Cron jobs in `cron/jobs.json` are merged by job id, not overwritten: user jobs and each job's
  paused or enabled state survive, shipped definitions refresh in place, and a newly shipped job
  arrives paused ("Installed from a profile distribution; review it, then resume"). Resume it with
  `hermes -p <name> cron resume <id>`. Squad cron jobs come from `squadctl apply`, not from the
  distribution.
- Squad state lives under the builder profile's `local/` (`installed.yaml`, backups), which install
  and update never write.

## Updating Hermes

- A source checkout of the official repo follows the `stable` channel: `hermes update` moves only
  from one published `vX.Y.Z` release to the next. Forks and mirrors follow `main`.
- `hermes update --set-channel main` follows every commit; `--set-channel stable` returns to releases
  and pins the checkout to the latest release commit, even when that is older. `hermes update
  --channel main` is one run and saves nothing. The choice is stored under `update.installs` in the
  root `config.yaml`.
- `hermes update --check` reports whether an update exists without applying it.
- `hermes update` restarts every gateway, which stops running agents (`--no-gateway-restart` defers
  that): the user runs it, never a bot.
