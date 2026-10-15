# Delegation

## Contents

- [How delegation works](#how-delegation-works)
- [Pinning the child model](#pinning-the-child-model)
- [The advisor pattern](#the-advisor-pattern)

## How delegation works

- `delegate_task` spawns subagent children from the current session; the parent
  decomposes the problem and the children execute well-specified subtasks
  (`website/docs/user-guide/features/delegation.md`).
- Children are where the tokens go: a parallel batch of subagents burns most of
  a run's total tokens (`website/docs/user-guide/features/delegation.md`).
- Delegation is a toolset; a bot without `delegation` cannot spawn children
  (`website/docs/reference/toolsets-reference.md`).

## Pinning the child model

- `delegation.model` applies to every child; when empty, children inherit the
  parent's model. Resolution order for credentials: `delegation.base_url`, then
  `delegation.provider`, then inherit the parent's provider
  (`website/docs/user-guide/features/delegation.md`).
- `delegation.reasoning_effort` sets the effort for children
  (`website/docs/user-guide/features/delegation.md`;
  `scripts/squadctl.py` writes these keys per bot).
- The pin is global: `delegate_task` has no per-task model parameter. For a
  quality-sensitive single task, use a kanban card with a per-card model
  override instead (`website/docs/user-guide/features/delegation.md`).

## The advisor pattern

- Pair a cheap worker model with a strong advisor consulted rarely: ask the
  advisor on data-model, auth, repeated failure or irreversible-migration calls
  only (`website/docs/guides/delegation-patterns.md`; `docs/decisions.md` D-005).
- Multi-lens reviews run as `delegate_task` subagents with clean contexts inside
  one reviewer bot, not as extra profiles (`docs/decisions.md` D-005).
- Squad manifests express this as `delegation: {lane: advisor}`; the builder
  writes `delegation.provider/model/reasoning_effort` from the lane
  (`squads/_schema/squad.schema.json`; `scripts/squadctl.py`).
- Subagent lifecycle details:
  `website/docs/developer-guide/subagent-lifecycle-api.md`.
