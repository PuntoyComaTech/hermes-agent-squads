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

1. First run: `scripts/hpy squadctl.py apply --self`.
2. For any squad: `scripts/hpy squadctl.py plan <key> --json` first. Show
   the diff (config keys, skills, plugins, MCP, cron, projects) and the model
   questions; apply only after the user's explicit OK.
3. `apply <key> [--models <file>] [--bots a,b] [--skip-skills] [--confirm id]
   [--yes]`. Confirm items (licence or disclosure questions) stay pending
   until the user answers and you pass `--confirm <id>`.
4. Check the result: `scripts/hpy squadctl.py status <key>` and
   `scripts/hpy squadctl.py doctor`.
5. Removing: `uninstall <key> [--keep-profiles] [--yes]`. It exports each profile to
   `local/backups/`, removes `<key>-*` cron jobs, deletes profiles unless kept,
   archives the board (never deletes) and leaves project folders untouched.
6. Coming from v1: run `scripts/hpy migrate_v1.py --dry-run`, show the plan; on
   OK run without `--dry-run`. v1 sites become Projects and the orchestrator is
   archived (`docs/decisions.md` V-04).

## Pitfalls

- `--models` missing: `apply` refuses rather than guessing, and names the lanes
  without a model.
- Deleting profiles by hand: use `squadctl uninstall`.

## Verification

- `status <key>` shows every bot `ok` with its model.
- `plan <key> --json` after apply reports `unchanged` for every bot.
- `hermes -p <bot> cron list` shows exactly the `<key>-*` jobs the manifest declares.
