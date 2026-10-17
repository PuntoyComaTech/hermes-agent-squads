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

- The manager creates the project (`desktop_project` create, "+" in the
  sidebar, or `hermes -p <manager> project create`); `project_sync.py` copies
  it to every worker and binds the squad board.
- Desktop Project grouping is a device-wide sidebar setting with no config
  key. It turns on when the user creates a project with "+", opens a folder,
  or goes to a project with ⌘K, or when the selected chat's agent calls
  `desktop_project` create or switch with a path.
