# Delegation

## How delegation works

- `delegate_task` spawns child agents from the current session; the parent
  decomposes the problem and the children run well-specified subtasks.
- Children inherit the parent's enabled toolsets. A bot without the `delegation`
  toolset cannot spawn children.
- `hermes chat -q` one-shot runs spawn at most `delegation.oneshot_max_children`
  children in total (default 2).
- Per task: `goal`, `context`, `output_schema` (JSON Schema the child's answer
  must validate against; one correction retry), `images` (up to 8 paths or URLs
  a vision child must see).
- `action`: `spawn` (default), `list`, `steer` (queue a correction into one
  running child), `stop` (end one child; its partial result still returns).
- Background fan-outs return as one message when the whole call finishes;
  `delegation.independent_completions: true` returns each task as it finishes.

## Pinning the child model

- `delegation.model` applies to every child; when empty, children inherit the
  parent's model. Credentials resolve from `delegation.base_url`, then
  `delegation.provider`, else the parent's provider.
- `delegation.reasoning_effort` sets the children's effort; empty inherits the
  parent's.
- `delegation.fallback_providers`: an unpinned child inherits the parent's
  chain when null and has none when `[]`; a pinned child gets a chain only when
  this key declares one.
- `delegation.child_timeout_seconds` caps inactivity per child (floor 30), not
  total runtime; 0 = no cap.
- The pin is global: `delegate_task` has no per-task model parameter. A
  quality-sensitive task goes on a kanban card with `--model` instead.
- Squad manifests write `delegation: {lane: code-complex}` (default lane
  `research`); squad tooling sets
  `delegation.provider`, `delegation.model` and `delegation.reasoning_effort`
  from the lane.

## The advisor pattern

- Pair a cheap worker model with a strong advisor consulted rarely; escalate on
  data-model, auth, repeated failure or irreversible migration.
- Multi-lens reviews run as `delegate_task` children with a clean context inside
  one reviewer bot, not as extra profiles.
