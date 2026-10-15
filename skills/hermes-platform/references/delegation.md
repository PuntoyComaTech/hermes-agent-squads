# Delegation

## How delegation works

- `delegate_task` spawns child agents from the current session; the parent
  decomposes the problem and the children run well-specified subtasks
  (`website/docs/user-guide/features/delegation.md`).
- Children are where the tokens go: a parallel batch typically burns most of a
  run's total tokens (`website/docs/user-guide/features/delegation.md`).
- Children inherit the parent's enabled toolsets. A bot without the `delegation`
  toolset cannot spawn children (`website/docs/reference/toolsets-reference.md`).
- `hermes chat -q` one-shot runs spawn at most `delegation.oneshot_max_children`
  children in total (default 2) (`website/docs/user-guide/features/delegation.md`).

## Pinning the child model

- `delegation.model` applies to every child; when empty, children inherit the
  parent's model. Credentials resolve from `delegation.base_url`, then
  `delegation.provider`, else the parent's provider
  (`website/docs/user-guide/features/delegation.md`).
- `delegation.reasoning_effort` sets the children's effort; empty inherits the
  parent's (`tools/delegate_tool_config.py`).
- The pin is global: `delegate_task` has no per-task model parameter. A
  quality-sensitive task goes on a kanban card with `--model` instead
  (`website/docs/user-guide/features/delegation.md`).
- Squad manifests write `delegation: {lane: advisor}`; squad tooling sets
  `delegation.provider`, `delegation.model` and `delegation.reasoning_effort`
  from the lane (`squads/_schema/squad.schema.json`; `scripts/squadctl.py`).

## The advisor pattern

- Pair a cheap worker model with a strong advisor consulted rarely; escalate on
  data-model, auth, repeated failure or irreversible migration (squad
  convention).
- Multi-lens reviews: `docs/decisions.md` D-005.
- Subagent lifecycle: `website/docs/developer-guide/subagent-lifecycle-api.md`.
