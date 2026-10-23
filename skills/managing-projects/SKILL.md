---
name: managing-projects
description: "Creates squad Projects and copies them to the workers. Use when a squad starts working in a new project folder."
---

# Managing projects

## When to Use

- A squad takes on a new site, brand, client or search: it becomes a Project.
- The user asks where a project's sessions or worktrees live.

## Procedure

1. Folder: the user picks it, new or an existing repo. Never choose one for
   them, never the home root or a profile directory.
2. The user creates it: Desktop Sessions, the manager in the bottom selector,
   "+", then chats inside it (the chat's working directory is the project's
   primary folder). When the user names a folder in chat instead, a manager
   chat `tool_call`s `desktop_project` with
   `{"action": "create", "name": "<name>", "path": "<their folder>"}`.
   Otherwise: `hermes -p <manager> project create "<name>" <folder>`.
   Gateway channels (Discord, etc.) do not inherit the Desktop project: the
   channel prompt must name the folder.
3. Copy it to the workers: `scripts/hpy project_sync.py --manager <manager>`
   (a manager runs `python3 $HERMES_HOME/scripts/project_sync.py`; add
   `--dry-run` to preview). It creates the project in every worker that lacks
   it and binds the squad board. A project made with "+" syncs the same way.
4. Tell the user once: "Sessions: pick <manager> in the bottom selector to
   see its projects; + creates another in a folder you choose."
5. When the folder ships `.hermes/skills/` or `.agents/skills/`, show the
   user those skill names and, after an explicit OK, run `hermes -p <bot>
   skills trust <path>` for the manager and every worker. Untrusted project
   skills never load.
6. Cards then take `--project <slug>`.
7. Later changes (`add-folder`, `set-primary`, `rename`, `archive`): run
   `hermes -p <bot> project <action> ...` for the manager and every worker.

## Pitfalls

- Creating the project in the manager only: Project state is per profile,
  so workers report "no projects yet" until `project_sync.py` runs.
- Writing project rows into a database by hand: use `hermes project`.
- Choosing a folder for the user: a bot-chosen folder lands outside the
  project the user expects and leaves stray folders.
- Expecting `project_sync.py` to create folders or set `repo_scan_roots`:
  `--setup` (run by `squadctl apply`) only resets the
  `repo_scan_roots: [~/Projects/<squad>]` that squad versions before 2.5.0 set.
- Assuming a `repo/` subfolder: a folder that already is the git repo keeps its
  layout; read the repo path from the squad's config (web: `site.yaml ->
  repo.path`).
- Sweeping a shared parent folder with a sync, cleanup or scan: target the
  exact project paths. A parent that also holds the user's own repos treats
  them as squad data.

## Verification

- `hermes -p <bot> project list` shows the project in the manager and each worker.
- A trusted repo: `hermes -p <bot> config get skills.trusted_project_dirs`
  lists its path in the manager and each worker.
