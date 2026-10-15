---
name: installing-squads
description: "Installs and removes squads through squadctl. Use when adding, updating, repairing or removing a squad."
---

# Installing squads

## When to Use

- The user says "install <squad>", "set me up", "update my installation" or
  "remove <squad>".
- A squad is drifted, broken or needs repair (`squadctl doctor`).

## Procedure

1. First run on a new machine: the user installs the builder distribution
   (`hermes profile install github.com/PuntoyComaTech/hermes-agent-squads
   --name builder --alias`), picks the builder's model, then asks the builder
   to set things up; the builder runs `python3 scripts/squadctl.py apply --self`.
2. For any squad: `python3 scripts/squadctl.py plan <key> --json` first. Show
   the diff (config keys, skills, plugins, MCP, cron, projects) and the model
   questions; apply only after the user's explicit OK.
3. `apply <key> [--models <file>] [--bots a,b] [--skip-skills] [--confirm id]`.
   Confirm items (licence or disclosure questions) stay pending until the user
   answers and you pass `--confirm`.
4. `apply --self` reconciles the builder itself and creates the `builder-watch`
   cron (`docs/decisions.md` V-15).
5. Check the result: `python3 scripts/squadctl.py status <key>` and
   `python3 scripts/squadctl.py doctor` (Kanban plugin, gateway, apps, auth).
6. Removing: `uninstall <key> [--keep-profiles]`. It exports each profile to
   `local/backups/`, removes `<key>-*` cron jobs, deletes profiles unless kept,
   archives the board (never deletes) and leaves project folders untouched.
7. Coming from v1: run `python3 scripts/migrate_v1.py --dry-run`, review, then
   apply; v1 sites become Projects and the orchestrator is archived
   (`docs/decisions.md` V-04).

## Pitfalls

- Applying without `plan`: always show the diff first; `--dry-run` prints every
  action including `set`/`missing` passthrough names only.
- Expecting a second `apply` to change something: `apply` is idempotent and
  prints `unchanged` per bot when nothing drifted.
- `--models` missing: `apply` refuses rather than guessing, and names the lanes
  without a model (`scripts/squadctl.py`).
- Uninstalling before export: `uninstall` backs up automatically; never delete
  profiles by hand.

## Verification

- `status <key>` shows every bot `ok` with its model.
- `plan <key> --json` after apply reports `unchanged` for every bot.
- Cron list shows exactly the `<key>-*` jobs the manifest declares.
