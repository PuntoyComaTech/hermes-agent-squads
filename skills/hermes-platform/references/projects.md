# Projects

## Contents

- [What a Project is](#what-a-project-is)
- [Commands](#commands)
- [Projects and kanban](#projects-and-kanban)
- [Squad usage](#squad-usage)

## What a Project is

- Projects are human-named workspaces that can span multiple folders or repos;
  they anchor Desktop session grouping and, when bound to a kanban board, give
  tasks a deterministic worktree + branch convention
  (`hermes project --help`).
- Project state is per-profile: a project created in one profile is invisible to
  the others (`hermes project --help`).

## Commands

- `hermes project create <name> [folders...]` with `--slug`, `--primary <path>`,
  `--description`, `--icon`, `--color`, `--board <slug>` (bind a kanban board)
  and `--use` (`hermes project create --help`).
- `hermes project list|show|add-folder|remove-folder|rename|set-primary|use|
  archive|restore|bind-board` manage them afterwards (`hermes project --help`).
- `hermes project use <slug>` sets the active project for a profile; the
  Desktop selector does the same (`README.md`).

## Projects and kanban

- `hermes kanban create --project <slug>` links the card to a project and
  anchors its worktree under the project's primary repo with a deterministic
  branch (`hermes kanban create --help`).
- Project state lives in per-profile storage (`hermes_cli/projects_db.py`,
  `tools/project_tools.py`).

## Squad usage

- Because Projects are per-profile, `squadctl project add` runs
  `project create` in the lead and every worker that touches the project
  (`scripts/squadctl.py`; `docs/decisions.md` V-04).
- Squads use Projects instead of imposed folder layouts
  (`docs/decisions.md` V-04).
