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
   Then ask once which squads to install: "Only the builder (default), Web,
   Marketing, Jobs, or Everything?" (`squadctl.py status` -> `available` lists
   local squads too). No answer or "only the builder": install nothing more.
   For the chosen squads run one `scripts/hpy model_advisor.py <key> [<key>...]
   --json > local/models-squads.json`, show one table for all their bots, ask
   one OK, then run steps 2 and 4 per squad with `--models local/models-squads.json`.
2. Any squad: `scripts/hpy squadctl.py plan <key> [--with <optional-bot>] --json`.
   Show the bot `actions`, `pending`, `notes` and `optional_skipped`. Apply only
   after the user's explicit OK. A `board` value
   `pending owner action: ...` is a command the user runs in their terminal.
   A `credentials <NAME>` note is a key the user puts in that bot's profile.
3. If the notes list `no model assigned`, run `skills/assigning-models` first.
4. `scripts/hpy squadctl.py apply <key> [--models <file>] [--with <bot>]
   [--bots a,b] [--skip-skills] [--confirm <id>]`.
   A `pending` item (licence or disclosure)
   installs only on a later apply with `--confirm <id>`, after the user
   answers its question.
5. Check: `scripts/hpy squadctl.py status <key>` and
   `scripts/hpy squadctl.py doctor`. Every bot starts with web search (keyless,
   no API key), terminal and delegation; `apply` installs Hermes's managed
   browser. A `:web` check that is not `ok` is fixed before the user works.
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

- Installing a squad the user did not choose: every squad is opt-in, even on
  "set me up" and when another AI started the install.

- Deleting profiles by hand: use `uninstall`, which exports first.
- `apply --self` on a machine without the builder profile: it refuses; the
  user runs the README install first.

## Verification

- `scripts/hpy squadctl.py status <key>` shows every bot `ok` with its model.
- `scripts/hpy squadctl.py plan <key> --json` reports every bot `unchanged`.
- `hermes -p <bot> cron list` shows exactly the `<key>-*` jobs the manifest
  declares.
