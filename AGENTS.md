# AGENTS.md

Contributor contract for this repository. Humans start at `README.md`; Hermes behavior is documented in
`skills/hermes-platform/references/`.

## What this is

The builder's profile distribution for Hermes Agent squads: manifests (`squads/*/squad.yaml`, `builder.yaml`),
skills, tested scripts, a schema. Installed with `hermes profile install`, reconciled by `scripts/squadctl.py`.

## Installing for a user

A user asks for this with "Install github.com/PuntoyComaTech/hermes-agent-squads following its AGENTS.md". The agent
runs only `hermes profile install github.com/PuntoyComaTech/hermes-agent-squads --name builder --alias`, then tells
the user, in this order:

1. `hermes -p builder model`: pick the builder's model.
2. `builder chat` (or `hermes -p builder chat`) and say "set me up"; the builder asks which squads to install and
   which model each bot uses.
3. Desktop app: Sessions, pick a squad manager in the bottom selector, "+" creates a project.

The agent never installs squads or picks models for the user. Updates then run daily on their own (cron
`builder-update`, `scripts/auto_update.py`); "update yourself" to the builder runs the same update now.

## Rules

- **Use the tools** through `scripts/hpy <tool>.py` (the Hermes runtime interpreter): `squadctl.py` applies
  changes, `skill_lint.py` gates skills, `model_advisor.py` assigns models, `kanban_chain.py` builds chains,
  `project_sync.py` copies a manager's projects to its workers, `auto_update.py` updates the builder and squads.
  Do not reimplement them.
- **English only** in repo content; bots speak the user's language at runtime.
- **Model ids only** in `scripts/data/model-roles.yaml` and `local/installed.yaml` (enforced).
- **Real scripts, never prose scripts**: Python for YAML/JSON/HTTP work, `--help` on every script; bash only for
  the shims and one-line cron wrappers.
- **Skills pass** `scripts/hpy skill_lint.py`; rules: `skill_lint.py --rules`.
- **Verify every platform claim** against local Hermes docs or source before writing it; when Hermes contradicts
  the repo, Hermes wins: fix the repo. Bot-loaded files (`SOUL.md`, `skills/`, `squads/`) state facts without
  source paths, decision ids or history.
- **Structural decisions**: `CONTRIBUTING.md` -> Decisions.
- **No secrets**: never read or write `.env`, `auth.json` or credential values.
- **Plan, user OK, apply** for anything that touches a profile; `profile export` before any prune or uninstall.
- **Community plugins and hub skills**: `skills/finding-capabilities` steps 3-5. Squad rules (naming, visibility,
  topology, credentials): `skills/designing-squads` -> Rules, Topology.

## Map

| Path | What |
| --- | --- |
| `distribution.yaml`, `config.yaml`, `SOUL.md`, `builder.yaml` | shipped profile payload and builder bot spec |
| `skills/` | builder skills; `hermes-platform` is the verified reference |
| `scripts/`, `scripts/data/` | squadctl and helpers; lane tables |
| `squads/<key>/` | one squad: `squad.yaml`, `souls/`, `skills/`, `scripts/`, README |
| `local/` (installed builder only, never shipped) | `installed.yaml`, overlays and local squads in `squads/<key>/`, backups, state |
| `squads/_schema/squad.schema.json` | manifest schema |
| `docs/decisions.md` | condensed decision log |
| `tests/` | pytest against a temporary `HERMES_HOME` |
