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
   --json > local/models-squads.json`, run the per-bot survey of
   `skills/assigning-models` step 4 for all their bots, then ask one OK, then run steps 2 and 4 per squad with `--models local/models-squads.json`.
2. Any squad: `scripts/hpy squadctl.py plan <key> [--with <optional-bot>] --json`.
   Show the bot `actions`, `pending`, `notes` and `optional_skipped`. Apply only
   after the user's explicit OK. A `board` value
   `pending owner action: ...` is a command the user runs in their terminal.
   Every bot gets every provider the user connected (keys and provider
   plugins); the plan lists each copy, so the user's OK covers it. A
   `credentials <NAME>` note is a provider not connected yet: the user
   connects it (`hermes model`), then apply again. Never copy a key by hand.
   Bots with the browser toolset get `browser.use_real_profile` (and the pin)
   when the user turned it on in the root or builder config; the builder
   itself never does. A bot with
   `shared_browser: true` gets the shared signed-in browser instead (one per
   machine, signed in once: `scripts/hpy shared_browser.py status|install|login
   <url>`). Never set up any other browser, debugging port or cookie copy.
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
   After the first install, tell the user once: "Sessions: pick a manager in
   the bottom selector to see its projects; + creates a new one."
6. Update ("update yourself"): run
   `scripts/hpy auto_update.py --force` and reply with its output. It is the
   same script the daily `builder-update` cron runs: it updates the builder
   when the repo has a new version, then brings every installed bot up to
   date. Lines starting `Needs you:` are `--confirm` items for step 4, or a
   skill edited here and changed upstream: the new version is installed and
   the local copy is in the named backup; move what still applies into the
   new version (generic rules go upstream, `skills/contributing-upstream`).
   Local skill edits that do not overlap the update are merged and kept.
7. Remove: `scripts/hpy squadctl.py uninstall <key> --dry-run`, show it; on OK
   run it without `--dry-run` (`--keep-profiles` keeps the profiles). It exports
   each profile to `local/backups/`, removes `<key>-*` cron jobs, deletes the
   profiles, archives the board and leaves project folders and
   `local/squads/<key>/` in place.
8. Document the local fleet without touching it: `scripts/hpy squadctl.py
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
- A squad with `shared_browser` bots: `scripts/hpy shared_browser.py status`
  shows `listening` and `plist_current: true` after the apply.
- `hermes -p <bot> cron list` shows exactly the `<key>-*` jobs the manifest
  declares.
