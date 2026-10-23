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
   A bot with `shared_browser: true` (every shipped bot that browses) gets the
   machine's one signed-in browser: one per machine, signed in once by the
   owner (`scripts/hpy shared_browser.py status|install|login <url>`). No bot
   gets `browser.use_real_profile`, even when the owner has it on for their own
   chats: a profile copy wins over `cdp_url` and fails while their browser is
   open. `apply` turns off a copy an older version mirrored and clears
   `browser.real_profile_pin`. Never set up any other browser, debugging port or
   cookie copy.
3. If the notes list `no model assigned`, run `skills/assigning-models` first.
   The `projects` line is what `apply` runs after the bots
   (`project_sync.py --setup`): mention in the OK message any bot whose
   `desktop.repo_scan_roots` it resets.
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
   A locally learned rule the new design contradicts is reworded to that
   design, not dropped: restoring the old rule, or deleting the file, throws
   away the only copy of a lesson learned in production. After the update, grep
   the installed copies for a sentence the release retired; a rule merged back
   from an older edit still teaches the previous design to the bot and to the
   next session. `builder-update` is a script cron with no agent, so it spends
   no tokens, but its fires come from that profile's gateway: on a new machine
   confirm the job exists and ran recently (`hermes -p builder cron list`)
   before telling the user updates are automatic, and run
   `auto_update.py --force` once after the first install.
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
- A `doctor` line `app <name> not found` is not proof the bot is broken: an
  official installer often drops a CLI in a home folder (`~/.bun/bin/bun`) and
  edits only the shell rc, so a non-login shell lacks it on `PATH`. Check how
  the consuming script resolves the binary before acting: when that finds the
  tool and `doctor` does not, the defect is the checker. Teach the shared
  resolver the installer's home location (`APP_HOME_BINS` in `squadctl.py`) with
  a test that goes red without it; never tell the user to reinstall or hand-edit
  `PATH`, and never mark the bot as needing repair.
- An install or apply trap that leaves the bot on a stale copy (a symlink in
  the source folder, a path given to `hpy`, an `env:` auth row, a mirrored
  setting): `references/apply-traps.md`.
- Applying a squad whose profiles another agent is editing on the same machine:
  a profile holds one copy, so the apply overwrites their work in progress.
  Apply only the squads you changed, name the ones you left alone and why, and
  say which version they must rebase onto.

## Verification

- `scripts/hpy squadctl.py status <key>` shows every bot `ok` with its model.
- `scripts/hpy squadctl.py plan <key> --json` reports every bot `unchanged`.
- A squad with `shared_browser` bots: `scripts/hpy shared_browser.py status`
  shows `listening` and `plist_current: true` after the apply.
- `hermes -p <bot> cron list` shows exactly the `<key>-*` jobs the manifest
  declares, `<key>-browser-sweep` on each squad's manager included. That sweep
  is one machine-wide job despite the cron on every manager: it takes a lock and
  a 150-minute stamp next to the shared browser's state, and the losing fires
  exit 0 with a skip. Run it by hand after an update instead of assuming it ran.
- An apply that changes a rule, a script or a template is verified per bot by
  content, not by the `changed` count: grep the new sentence in each bot's
  `SOUL.md`, list the new script under its skill folder, then send the smoke
  chat. A profile copied from a stale checkout reports `changed` and still runs
  the old rule.
- After `apply --src <checkout>`, each bot's copied `project_sync.py` matches
  the checkout's file (`cmp`): a stale copy re-creates folders a fix removed
  while the apply still reports `ok`.
- After an apply that copies a key: count the key line in each bot's env file
  (never print it) and send each bot a one-line chat, in parallel. A bot is
  broken only on a real empty answer plus a fallback line, not on a parsing
  miss.
