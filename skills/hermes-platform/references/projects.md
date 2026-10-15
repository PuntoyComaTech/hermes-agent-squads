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
  Desktop selector does the same (`hermes_cli/projects_cmd.py`).

## Projects and kanban

- `hermes kanban create --project <slug>` links the card to a project and
  anchors its worktree under the project's primary repo with a deterministic
  branch (`hermes kanban create --help`).

## Squad usage

- Because Projects are per-profile, `squadctl project add` runs
  `project create` in every bot of the squad
  (`scripts/squadctl.py`; `docs/decisions.md` V-04).
