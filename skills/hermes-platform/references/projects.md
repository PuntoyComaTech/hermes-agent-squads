# Projects

## What a Project is

- Projects are named workspaces that can span several folders or repos; they
  group Desktop sessions and, when bound to a kanban board, give tasks a
  deterministic worktree and branch.
- Project state is per profile: a project created in one profile is invisible
  to the others.

## Commands

- `hermes project create <name> [folders...]` with `--slug`, `--primary <path>`,
  `--description`, `--icon`, `--color`, `--board <slug>` (bind a kanban board)
  and `--use`.
- `hermes project list|show|add-folder|remove-folder|rename|set-primary|use|
  archive|restore|bind-board` manage them afterwards; `use <slug>` sets the
  profile's active project, as the Desktop selector does.
- `hermes kanban create --project <slug>` links a card to a project and anchors
  its worktree under the project's primary repo with a deterministic branch.

## Squad usage

- `squadctl project add` runs `project create` in every bot of the squad.
