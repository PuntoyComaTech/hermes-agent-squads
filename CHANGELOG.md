# Changelog

All notable changes to hermes-agent-squads. The builder's update watcher reads this file
(`scripts/watch_upstream.py`); keep entries short and dated.

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
  fallbacks, reusing the studio squad's skills).
- `deploying-sites` refuses to deploy without the project's `deploy.md` (target,
  command, env names, rollback; template provided).
- `designing-squads` documents the topology rule (delegate_task subagents vs Kanban
  workers; one board per squad, one Project per repo) and hub-skill quoting.

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
- New `studio` squad for rendered and standalone assets: motion, video, 3D (V-13).
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
