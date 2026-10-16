---
name: managing-projects
description: "Registers Hermes Projects across manager and workers. Use when a squad starts working in a project folder."
---

# Managing projects

## When to Use

- A squad takes on a new site, brand, client or workspace: it becomes a Project.
- The user asks where a project's sessions or worktrees live.

## Procedure

1. Collect the project name and its real folder path; never impose a layout
   (`docs/decisions.md` V-04).
2. Run `scripts/hpy squadctl.py project add <key> "<name>" <path> --dry-run`,
   show it, then run it without `--dry-run`. It runs `hermes project create`
   with the squad board in the manager and every worker.
3. Cards then take `--project <slug>` (`hermes kanban create --help`).
4. Later changes (`add-folder`, `set-primary`, `rename`, `archive`): run
   `hermes -p <bot> project <action> ...` for the manager and every worker.

## Pitfalls

- Creating the project in the manager only: Project state is per profile
  (`hermes project --help`), so workers report "no projects yet".
- Writing project rows into a database by hand: use the CLI
  (`hermes_cli/projects_cmd.py` owns the state).

## Verification

- `hermes -p <bot> project list` shows the project in the manager and each worker.
- `local/installed.yaml` -> `projects.<slug>.squads` lists the squad.
