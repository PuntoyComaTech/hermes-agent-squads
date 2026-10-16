---
name: installing-squads
description: "Installs, updates and removes squads through squadctl. Use when adding, updating, repairing or removing a squad."
---

# Installing squads

## When to Use

- The user says "set me up", "install <squad>", "update my installation" or
  "remove <squad>".
- `scripts/hpy squadctl.py doctor` reports a `warn` or `fail`.

## Procedure

1. First run ("set me up"): `scripts/hpy squadctl.py plan --self --json`,
   assign models (`skills/assigning-models`, key `builder`), then on OK
   `scripts/hpy squadctl.py apply --self --models local/models-builder.json`.
2. Any squad: `scripts/hpy squadctl.py plan <key> [--with <optional-bot>] --json`.
   Show the bot `actions`, `pending`, `notes` and `optional_skipped`. Apply only
   after the user's explicit OK. A `root` line changes the machine-wide
   `<root>/config.yaml`: ask for it separately and add
   `--set-root-kanban-cap` only on that OK. A `board` value
   `pending owner action: ...` is a command the user runs in their terminal.
   A `credentials <NAME>` note is a key the user puts in that bot's profile.
3. If the notes list `no model assigned`, run `skills/assigning-models` first.
4. `scripts/hpy squadctl.py apply <key> [--models <file>] [--with <bot>]
   [--bots a,b] [--skip-skills] [--confirm <id>] [--set-root-kanban-cap]`.
   A `pending` item (licence or disclosure)
   installs only on a later apply with `--confirm <id>`, after the user
   answers its question.
5. Check: `scripts/hpy squadctl.py status <key>` and
   `scripts/hpy squadctl.py doctor`.
6. Update: after `hermes profile update builder`, run step 2 for each squad
   `status` lists.
7. Remove: `scripts/hpy squadctl.py uninstall <key> --dry-run`, show it; on OK
   run it without `--dry-run` (`--keep-profiles` keeps the profiles). It exports
   each profile to `local/backups/`, removes `<key>-*` cron jobs, deletes the
   profiles, archives the board and leaves project folders and
   `local/squads/<key>/` in place.
8. Coming from v1: `scripts/hpy migrate_v1.py --dry-run`, show it; on OK run
   it without `--dry-run`.
9. Document the local fleet without touching it: `scripts/hpy squadctl.py
   inventory [--profiles a,b] --out local/fleet.yaml`. It reads config, ui_meta,
   skills and cron of every profile, never `.env` or `auth.json`, and writes
   only under `local/`. The result is local data: never published
   (`skills/contributing-upstream`).

## Pitfalls

- Deleting profiles by hand: use `uninstall`, which exports first.
- `apply --self` on a machine without the builder profile: it refuses; the
  user runs the README install first.

## Verification

- `scripts/hpy squadctl.py status <key>` shows every bot `ok` with its model.
- `scripts/hpy squadctl.py plan <key> --json` reports every bot `unchanged`.
- `hermes -p <bot> cron list` shows exactly the `<key>-*` jobs the manifest
  declares.
