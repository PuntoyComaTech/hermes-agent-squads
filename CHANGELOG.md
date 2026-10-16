# Changelog

All notable changes to hermes-agent-squads. The builder's update watcher reads this file
(`scripts/watch_upstream.py`); keep entries short and dated.

## 2.0.7 - 2026-10-16

Every bot gets the install's fallback chain, overlays edit repo lists in place, and `plan` names config it
will never touch.

### Added

- `fallback:` in the models file (provider/model/reasoning rows) reaches every bot as `fallback_providers`,
  its children as `delegation.fallback_providers` and `agent.reasoning_overrides`, and is saved in
  `installed.yaml`. `model_advisor.py` recommends a chain when a pick runs on a quota-limited provider.
- Overlay list edits: `skills.keep_add`/`keep_remove` and `plugins.enable_add`/`enable_remove` follow the repo
  lists instead of freezing a copy. A hub keep dropped from the manifest is uninstalled; a hub skill the bot
  installed itself stays.
- `squadctl plan` notes plugins enabled on a bot that its manifest does not declare (kept, never removed) and
  profile-level `kanban.*` keys, which the gateway dispatcher never reads.
- `catalog_search.py --shelf` and `--hermes-version`; plugin hits list `shelf`, `requires_hermes` and
  `known_issues`.
- `skill_lint.py` rule `no-issue-notes`: no upstream issue numbers or harmless-warning notes in bot context.
- References: `memory.md`; credential pools and `prompt_caching.cache_ttl`; Agent Plugins v1 packages and
  `plugins.isolation`; project-skill trust (`managing-projects` trusts a repo that ships skills); every
  auxiliary slot and its lane; connector guest identity and several accounts per app; the renamed tools
  `todo_list`, `cronjob_manage`, `process_manage` and the shipped `tools.tool_search.defer`; Hermes release
  channels (`--set-channel`).

### Fixed

- `apply` fails when Hermes rejects a toolset (it exits 0 and prints "Unknown toolset"); invalid YAML names
  the file and line; a `bots:` model pin that beats its lane is a plan note.
- `cf` and `wrangler` run from PATH, a local npx copy or npx on first use; `doctor` never downloads.
- `model_advisor.py` counts providers available only through a credential pool, `custom:<name>` included.

### Tests

- QA pass merged: real-hermes tests run whenever `hermes` is on PATH; the fake's toolsets match real Hermes;
  the web fixture is the shipped manifest and test models cover every lane; a contract test fails when
  Hermes adds an auxiliary slot squadctl does not route.

## 2.0.6 - 2026-10-15

Bots keep what they learn: apply never deletes their skills, and every bot has memory by default.

### Changed

- `squadctl apply` records what it installed in `skills/.squad-installed.json` and removes only those paths
  (or `.squad-sha` copies, or symlinks into the squad source). Any other skill shows per bot as `learned`
  in `plan` and `apply` and stays.
- Built-in memory is on unless a bot sets `memory: false` (squadctl adds the `memory` toolset). Every SOUL
  has one line on what its memory holds: job pitfalls and fixes, never secrets.
- `designing-squads`: the QA lane is `kanban_request_review(reviewer=...)`; open-ended cards use `goal_mode`.

### Added

- `references/kanban.md`: Review lane, Dispatcher config (root-only keys with defaults), Goal-mode cards.
- `references/cron-and-gates.md`: `--pin`/`--unpin`, `--paused`, `--interpreter`, `--continuity`,
  `cron.catch_up_missed`, `[CRON_FAILURE]`, `cron.failure_repeat_alert_hours`, `hermes cron incidents`.
- `squadctl doctor` warns on a squad agent cron job with no model pin; `apply` restores it.

## 2.0.5 - 2026-10-15

The update watcher stops dropping section-scoped Hermes changes, and squads set no kanban cap.

### Fixed

- `watch_upstream.py` matches keywords against the bullet and its heading; every bullet under Upgrade notes,
  Kanban, Cron, Delegation, Plugin system, Skills and Profiles is priority, and priority bullets over the cap go to
  `<tag>.overflow.md` (`context.overflow`) instead of being dropped. Goal, delegation, memory providers, credential
  pools, connectors and provider plugins are priority keywords. Tested on the recorded v0.22.0 body.
- `watch_upstream.py --squads-ref` (default `HEAD`, the branch `hermes profile update` clones) replaces the
  hardcoded `main`.

### Removed

- The kanban cap: `apply --set-root-kanban-cap` and the `root` key of the apply output are gone. `squadctl doctor`
  warns on any home (root or profile) that sets `kanban.max_in_progress_per_profile`.
- Source citations, decision ids and decision-log pointers from bot-loaded files (`skills/`, `squads/`, script
  comments); `references/cost-levers.md`. A contract test keeps them out.

### Changed

- `references/delegation.md` documents `output_schema`, `images`, `steer`/`stop`, `independent_completions`,
  `fallback_providers` and `child_timeout_seconds`. `hermes-platform` finds the Hermes source through
  `hermes --version` and warns that `config get` flags valid keys outside the schema.

## 2.0.4 - 2026-10-15

The distribution ships the builder plus `web`, `marketing` and `jobs`: the web squad is web-only and
the root kanban cap is opt-in.

### Removed

- The `studio` squad (manifest, four skills, three souls). No board, profile, fixture or reference to
  it remains; `web-frontend-pro` asks the card's requester for offline renders instead of ordering them.

### Changed

- `web-frontend` and `web-frontend-pro` keep `impeccable`, `scrollcraft`, `claude-design`, `design-md`
  and `popular-web-designs`. `hyperframes`, `dream-loop` and `auteur` are out: video rendering and
  taste, not site work.
- `building-3d-motion` gains `references/animation-libraries.md` — GSAP/ScrollTrigger, Lenis, Motion,
  three.js/R3F + drei, Theatre.js and Lottie/Rive, each with its bundle cost and reduced-motion switch.
- `squadctl plan` and `squadctl doctor` never propose `kanban.max_in_progress_per_profile`; `apply
  --set-root-kanban-cap` is the only writer and runs on the user's ask (V-12).
- Squad `version` 3.1.1 in `web`, `marketing` and `jobs`.

### Fixed

- Stale references: `start_search.py --lead` is `--manager`, the marketing templates are named by the
  skill that owns them, `site-contract` names `check_site.py`, and the review-round wording in the
  jobs and web lenses and evals matches the rules that cap rounds.

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
