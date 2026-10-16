# Changelog

All notable changes to hermes-agent-squads. The builder's update watcher reads this file
(`scripts/watch_upstream.py`); keep entries short and dated.

## 2.0.3 - 2026-10-15

Fixes from the builder's real `web` install, and deploys through the vendors' own CLIs.

### Changed (deploys)

- Deploys ride on the CLIs' own logins (`gh auth login`, `cf auth login`, `wrangler login`; `vercel login` only
  where a project targets Vercel). `web-deployer` no longer passes `CLOUDFLARE_API_TOKEN`,
  `CLOUDFLARE_ACCOUNT_ID`, `GH_TOKEN` or `VERCEL_TOKEN` through its environment and no longer suggests
  `vercel_mcp`; tokens stay documented as the CI/headless path only (D-036).
- `web-deployer` declares `requires.apps: [cf, wrangler, gh]`. `squadctl doctor` reports each required app
  (PATH, the macOS app path, or `npx --no-install` for an npm-packaged CLI) and then its stored login, reading
  only the exit status of `gh auth status` / `cf auth whoami` / `wrangler whoami` — no account, masked token or
  other probe output can reach a check.
- `deploying-sites`: `cf` first (`cf cli search` before any remembered form, `cf schema`, `--dry-run`), Wrangler
  only for what `cf` lacks or for a project that ships a Wrangler config (then `cf migrate` before any
  `cf dev|build|deploy`); `deploy.md`'s third field is `creds` (logins by name, never values).

### Fixed

- squadctl `ensure_board`: inside a Kanban worker (delegated child context) it checks
  `hermes kanban boards list` first and reports "pending owner action: boards create"
  only when the board is actually missing.
- Credentials: `apply --yes` copies a provider's API key (name and value, never printed)
  from the root source into the bot's profile env file (mode 600); `doctor` checks per
  bot that the provider's key is present in the profile env file or the profile auth
  store, and `models ok` no longer passes for a bot that cannot authenticate.
- model_advisor: provider detection unions every probe (in-process, runtime,
  `hermes auth list`) with the provider key names in the root and profile env files
  (names only; values never leave the file), so a provider the first probe misses is
  still detected; key-home reporting counts the same names per scope.
- Per-card reasoning effort is documented as it really is: `kanban create`, `set-model`
  and the `kanban_create` tool carry model+provider only; the task's `reasoning_effort`
  (dispatcher passes `--reasoning`) is writable only from the kanban dashboard. CLI
  paths: `agent.reasoning_overrides`, `delegation.reasoning_effort`, cron
  `--reasoning-effort`, or a dedicated profile (V-07).
- Version: `distribution.yaml` is the single source of truth; the builder manifest is
  versionless and `status` reads the distribution version.

## 2.0.2 - 2026-10-15

Squad structure: managers, visible bots and sections, web roles and `web-frontend-pro` (S1-S3).

### Fixed (S1)

- squadctl apply: a board created from inside a Kanban worker becomes a pending owner
  action instead of failing the run; a provider that is a user plugin of the builder is
  copied into each bot's profile (and `doctor` flags a missing copy); `mcp add` answers
  the real prompt order and fails loudly when the server does not land enabled; a
  provider change clears the stale `model.base_url`/`api_mode`; the machine-wide
  `kanban.max_in_progress_per_profile` is reported by plan and written only by
  `apply --set-root-kanban-cap`; the provider key name is an owner note, never read;
  `doctor [<squad>]` filters to one squad.

### Changed (S2)

- model_advisor: per-provider auto-detection with key-home reporting, local
  `providers-exclude.txt` (detected, never recommended) and role lanes across families
  (`manager`, `frontend`, `design-pro`, `code-complex`, `code-routine`, `review`,
  `deploy`, `research`, `digest`, `aux`, `vision`) with alias compat for deprecated
  lane names.

### Changed (S3)

- Managers (C-11): exactly one manager per squad, profile name = the squad key, title
  `<Name> manager`; workers are `<key>-<role>`. The manifest field `lead` is now
  `manager` and role `lead` is `manager`; lane `lead` is `manager` in every shipped
  manifest (the aliases stay so older manifests resolve).
- All bots are visible: squadctl files the Desktop sections `Managers` (managers) and
  one section per squad (workers) through `ui_meta.hermes-bots` (V-12).
- Web squad: canonical lanes (`manager`, `frontend`, `code-routine`, `review`,
  `deploy`); `web-backend` runs `code-routine` and the manager pins the `code-complex`
  model per card on hard problems; optional `web-frontend-pro` (lane `design-pro`,
  installed only with `squadctl apply web --with web-frontend-pro`) with the new
  `building-3d-motion` skill (three.js/R3F, GSAP, Blender pipeline, perf budgets and
  fallbacks).
- `deploying-sites` refuses to deploy without the project's `deploy.md` (target,
  command, env names, rollback; template provided).
- `designing-squads` holds the squad Rules (naming, visibility, cap, credentials,
  skill sources) and the Topology (delegate_task subagents vs Kanban workers; single
  bot with or without a board; one board per squad, one Project per repo).

### Fixed (release gate)

- squadctl: provider plugins installed at the root home are copied like builder ones;
  providers with no API-key env var (OAuth, external process) get no credentials note.
- squadctl `inventory`: documents the local fleet read-only (C-12).
- hermes-platform references: tool-search bridge lists `tool_describe`; `message_agent`
  also reaches a Bot Chat opened from the CLI; per-profile credential and provider
  plugin resolution added.

## 2.0.1

- release.py: `private` gate blocks local-only names listed in the maintainer's `local/private-terms.txt`.
- contributing-upstream: never publish local fleets.

## 2.0.0 - 2026-10-15

Full redesign as a profile distribution (see `docs/decisions.md`).

### Added

- The repo root is the builder's profile distribution: `hermes profile install ... --name
  builder --alias`, updated with `hermes profile update builder` (V-01).
- `squadctl` (`plan`, `apply`, `uninstall`, `status`, `doctor`, `project`, `chain`) with an
  idempotent plan, OK, apply flow (V-10).
- `model_advisor.py` (lane table per bot from the user's providers), `catalog_search.py`
  (plugins, skills, MCP, connectors), `skill_lint.py` (format gate), `kanban_chain.py`
  (chain to dependent cards), `gate_lib.py` (wakeAgent helpers), `watch_upstream.py` (daily
  zero-LLM update gate) (V-08, V-09, V-14).
- `scripts/hpy` runs every tool under the Hermes runtime interpreter (no PyYAML needed);
  `scripts/release.py` gates maintainer pushes to main.
- `scripts/board_watch.py`: a `<key>-watch` cron on every manager posts blocked and stale cards
  to the manager's Bot Chat (V-05).
- Squad manifests schema 2 (`squads/_schema/squad.schema.json`) with bots, chains, cron
  gates and per-card lanes.
- Ten builder skills under `skills/`, including `hermes-platform` (18 verified Hermes
  reference topics with citations) (V-09).
- `scripts/migrate_v1.py`: detects a v1 install (legacy profiles, `~/Hermes/projects/*`,
  `deliver.py` crons), registers the folders as native Projects, removes the deliver crons and
  archives the orchestrator into `local/backups/`; `--dry-run` and `--json`.

### Changed

- One visible manager per squad replaces the global orchestrator; workers are hidden and run
  one card at a time (V-02, V-12).
- Native Hermes Projects replace imposed `~/Hermes` folder layouts (V-04).
- Kanban notify and `bot-chat:<manager>` delivery replace `deliver.py` and the outbox (V-05).
- Profiles are created with `--no-skills`, pruned per role; squad skills are copied with a
  sha marker (V-06).
- Real, tested scripts replace prose scripts (V-03).
- The jobs analyst merges into the scout; review work pins the review lane per card (V-17).

### Removed

- `base/`, `START-HERE.md`, `README.es.md`, `00-evaluation/` (decisions condensed in
  `docs/decisions.md`), the v1 prose migrations (replaced by `scripts/migrate_v1.py`).
