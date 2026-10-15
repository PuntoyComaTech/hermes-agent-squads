---
name: managing-projects
description: "Registers Hermes Projects across lead and workers. Use when a squad starts working in a project folder."
---

# Managing projects

## When to Use

- A squad takes on a new site, brand, client or workspace: it becomes a Project.
- The user asks where a project's sessions or worktrees live.

## Procedure

1. Collect the project name and its real folder path; never impose a fixed
   layout (`docs/decisions.md` V-04).
2. Run `scripts/hpy squadctl.py project add <squad> <name> <path>`. It runs
   `hermes project create` in the lead and in every worker of the squad.
3. Cards then carry `--project <slug>` for a deterministic worktree and branch
   (`hermes kanban create --help`).
4. Selecting a project in a bot: `hermes -p <bot> project use <slug>`.
5. Later changes (`add-folder`, `rename`, `archive`): run
   `hermes -p <bot> project <action>` in the lead and every worker.

## Pitfalls

- Creating the project in the lead only: workers then report "no projects yet"
  and their sessions cannot join the project's grouping.
- Hand-writing project rows into a database: always use the CLI
  (`hermes_cli/projects_cmd.py` owns the state).
- Expecting Projects to be shared across profiles or machines: state is
  per-profile (`hermes project --help`).

## Verification

- `hermes -p <bot> project list` shows the project in the lead and each worker.
- A test card with `--project <slug>` anchors its worktree under the project's
  primary folder.
