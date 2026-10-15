# Changelog

All notable changes to hermes-agent-squads. The builder's update watcher reads this file
(`scripts/watch_upstream.py`); keep entries short and dated.

## 2.0.0 — 2026-10-15

Full redesign as a profile distribution (see `docs/decisions.md`).

### Added

- The repo root is the builder's profile distribution: `hermes profile install ... --name
  builder --alias`, updated with `hermes profile update builder` (V-01).
- `squadctl` (`plan`, `apply`, `uninstall`, `status`, `doctor`, `project`, `chain`) with an
  idempotent plan → OK → apply flow (V-10).
- `model_advisor.py` (lane table per bot from the user's providers), `catalog_search.py`
  (plugins, skills, MCP, connectors), `skill_lint.py` (format gate), `kanban_chain.py`
  (chain → dependent cards), `gate_lib.py` (wakeAgent helpers), `watch_upstream.py` (daily
  zero-LLM update gate) (V-08, V-09, V-14).
- Squad manifests schema 2 (`squads/_schema/squad.schema.json`) with bots, chains, cron
  gates and per-card lanes.
- Ten builder skills under `skills/`, including `hermes-platform` (18 verified Hermes
  reference topics with citations) (V-09).
- New `studio` squad for rendered and standalone assets: motion, video, 3D (V-13).

### Changed

- One visible lead per squad replaces the global orchestrator; workers are hidden and run
  one card at a time (V-02, V-12).
- Native Hermes Projects replace imposed `~/Hermes` folder layouts (V-04).
- Kanban notify and `bot-chat:<lead>` delivery replace `deliver.py` and the outbox (V-05).
- Profiles are created with `--no-skills`, pruned per role; squad skills are copied with a
  sha marker (V-06).
- Real, tested scripts replace prose scripts (V-03).
- The jobs analyst merges into the scout; review work pins the review lane per card (V-17).

### Removed

- `base/`, `START-HERE.md`, `README.es.md`, `00-evaluation/` (decisions condensed in
  `docs/decisions.md`), the v1 prose migrations (replaced by `scripts/migrate_v1.py`).
