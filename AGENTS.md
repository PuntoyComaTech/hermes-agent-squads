# AGENTS.md

Contributor contract for this repository. Humans start at `README.md`; Hermes behavior is documented in
`skills/hermes-platform/references/` (every fact cites its source).

## What this is

The builder's profile distribution for Hermes Agent squads: manifests (`squads/*/squad.yaml`, `builder.yaml`),
skills, tested scripts, a schema. Installed with `hermes profile install`, reconciled by `scripts/squadctl.py`.

## Rules

- **Use the tools** through `scripts/hpy <tool>.py` (the Hermes runtime interpreter): `squadctl.py` applies
  changes, `skill_lint.py` gates skills, `model_advisor.py` assigns models, `kanban_chain.py` builds chains.
  Do not reimplement them.
- **English only** in repo content; bots speak the user's language at runtime.
- **Model ids only** in `scripts/data/model-roles.yaml` and `local/installed.yaml` (enforced).
- **Real scripts, never prose scripts**: Python for YAML/JSON/HTTP work with `--help` on every script; bash only
  for the `squadctl` shim and one-line wrappers.
- **Skills follow the budget** (`skill_lint.py`): third-person description with "Use when", sections When to Use /
  Procedure / Pitfalls / Verification, 3 evals, one-level references (`docs/decisions.md` V-09).
- **Verify every platform claim** against local Hermes docs or source and cite the path; when Hermes contradicts
  the repo, Hermes wins: fix the repo.
- **Structural decisions** append to `docs/decisions.md` with id, date, decision, why.
- **No secrets**: never read or write `.env`, `auth.json` or credential values.
- **Plan → user OK → apply** for anything that touches a profile; `profile export` before any prune or uninstall.
- **Community plugins and hub skills** install only after quoting their disclosure and licence and getting an
  explicit OK.

## Map

| Path | What |
| --- | --- |
| `distribution.yaml`, `config.yaml`, `SOUL.md`, `builder.yaml` | shipped profile payload and builder bot spec |
| `skills/` | builder skills; `hermes-platform` is the verified reference |
| `scripts/`, `scripts/data/` | squadctl and helpers; lane tables |
| `squads/<key>/` | one squad: `squad.yaml`, `souls/`, `skills/`, `scripts/`, README |
| `squads/_schema/squad.schema.json` | manifest schema |
| `docs/decisions.md` | condensed decision log |
| `tests/` | pytest against a temporary `HERMES_HOME` |
