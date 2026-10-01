# AGENTS.md

> Instructions for any AI agent that opens this repository: a Hermes session using it as plans, or a coding agent editing it. Humans start at [`README.md`](README.md).

## What this is

Markdown plans that Hermes Agent reads to install a bot ecosystem: a base (user profile, `orchestrator`, `builder`) and squads of specialist bots (`squads/jobs`, `squads/marketing`, `squads/web`). There is no application code to build or run here.

## If you are a Hermes session using these plans

1. Go to [`START-HERE.md`](START-HERE.md), section "For the installer AI", and follow it.
2. **You install the base only:** the user's profile, the `orchestrator` and the `builder` ([`base/06-base-installation.md`](base/06-base-installation.md)).
3. **You never install, create, design or adapt a squad**, its bots, profiles, skills or crons, even if the user asks, even during personalization. Only the builder does that ([`base/01-principles.md`](base/01-principles.md) §1.10). When the base is ready, tell the user in one line to write to the builder.
4. Verify every command against its real output. If the Hermes documentation contradicts a plan, the documentation wins: say so and adapt.

## If you are editing this repository

Full rules in [`CONTRIBUTING.md`](CONTRIBUTING.md). The ones most often broken:

- **Markdown only.** Scripts and configs are specified as prompts in `squads/<key>/05-scripts.md` and written on the user's machine by the builder. Exceptions: `squad.yaml` and `squads/*/reference/`.
- **English** for every plan. Bots speak the user's language at runtime.
- **Naming** follows the table in `CONTRIBUTING.md`. The system's unit is a **squad**, never an "agency".
- **Every structural decision** gets an entry at the top of [`00-evaluation/02-decisions.md`](00-evaluation/02-decisions.md): `D-NNN`, date, Decision, Why, Rejected alternatives, and Revisit if when it applies.
- **Contract changes ship a migration.** A base contract change adds `base/migrations/NNNN-<name>.md` in the format of the existing ones (What and why, Already applied if, Steps, Conflicts, Verify, Rollback). A squad contract change also bumps that squad's `plan_version` in `squad.yaml`.
- **Change a squad's files together.** A new step in a bot means updating its SOUL (`03-bots.md`), the skills pinned per task (`02-architecture.md` and the orchestration table in `03-bots.md`), the install steps (`04-installation.md`) and the tests (`06-testing-and-operations.md`).
- **Verify tools and versions** against official docs or the package registry, and record the date. Never invent flags.
- **Nothing personal.** User data are `{{variables}}`; examples are fictional.
- **Do not edit** `squads/*/reference/`: third-party material under its own license.

## Map

| Path | What |
| --- | --- |
| `START-HERE.md` | Entry point for the user and the installer AI |
| `base/` | Shared by every squad: principles, architecture, profile, orchestrator, builder, updates |
| `base/migrations/` | Numbered, idempotent update steps |
| `squads/<key>/` | One squad: 7 Markdown files + `squad.yaml` |
| `00-evaluation/` | Design rationale and the decision log |
| `llms.txt` | Short index of this repository for LLMs |
