# 0003 · Squad manifests and generated registry

> Migration (`base/08-updates.md`). Run by the builder (or the `default` session before `0004`).

## What and why
Writes `projects/<key>/squad.yaml` for each installed official squad, adds `scripts/registry.py`, and regenerates `orchestrator/registry.md` from the manifests. The registry and the orchestrator's `skills.external_dirs` then come from one source instead of hand edits.

## Already applied if
Every installed squad has `projects/<key>/squad.yaml` and `scripts/registry.py` exists and runs without error.

## Steps
1. For each installed official squad: copy `plans/squads/<key>/squad.yaml` to `projects/<key>/squad.yaml` and fill it from the installed system: `level` from the current registry, each bot's `model` and `reasoning_effort` from `hermes -p <bot> config get` (or the profile's `config.yaml`), crons from `hermes -p <profile> cron list` (the `-p` is required: without it the command lists only the default profile and silently under-reports). Keep extra bots or crons the user added.
2. Write `scripts/registry.py` from `07-builder.md` §6.
3. Run it. Apply the printed list with `hermes -p orchestrator config set skills.external_dirs '<list>'`.

## Conflicts
Rows or notes the user added by hand to `registry.md` outside "History": show them and ask whether to keep them (as a note in History) or drop them. A cron or bot in the system but not in the plan: keep it in `squad.yaml` and tell the user.

## Verify
`registry.md` lists every installed squad with the same bots and level as before; `hermes -p orchestrator config get skills.external_dirs` matches the script output; the orchestrator answers "what squads do I have?" correctly.

## Rollback
`git -C {{ROOT}} revert` the migration commit; `hermes profile import` of the exported orchestrator profile.
