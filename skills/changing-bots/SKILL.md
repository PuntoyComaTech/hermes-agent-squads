---
name: changing-bots
description: "Edits, adds, splits and retires the bots of a squad. Use when a bot is added, changed, split or retired."
---

# Changing bots

## When to Use

- The user wants a bot to gain or lose toolsets, skills, plugins, MCP servers,
  connectors, cron jobs or its lane.
- A squad needs another bot, one bot split in two, or a bot retired.

## Procedure

1. Write the change to the overlay `local/squads/<key>/squad.yaml` (key
   `builder` for the builder). Merge rule (`deep_merge` in
   `scripts/squadctl.py`): maps merge per key, lists and scalars replace,
   `null` deletes the key. Write every changed list or chain in full.
2. Put new or changed assets next to the overlay; they win over the repo
   copies: `local/squads/<key>/souls/<bot>.md`,
   `local/squads/<key>/skills/<skill>/` (`skills/authoring-skills`),
   `local/squads/<key>/scripts/<script>`.
3. Add a bot: check `skills/designing-squads` -> Rules, then add
   `bots.<key>-<role>` with `role: worker`, `title`, `description`, `lane`,
   `toolsets` (`squads/_schema/squad.schema.json` -> `bot`), its SOUL with
   one line on what its memory stores, and the chain stages it takes. Past
   5 required bots the new bot sets `optional: true`.
   Change a model: `skills/assigning-models`. Add a Project:
   `skills/managing-projects`.
4. Split a bot: add the new bot as in step 3, then rewrite the old bot's
   `toolsets` and `skills.squad` and every chain whose stages move.
5. Retire a bot: set `bots.<bot>: null`; rewrite every chain and copy into the
   overlay every squad skill that names it, with the bot replaced.
   Move its open cards first: `hermes kanban --board <slug> list --assignee <bot> --json`,
   then `hermes kanban --board <slug> reassign <id> <new-bot> --reclaim` per card.
6. Run `scripts/hpy squadctl.py plan <key> --json` (`--self` for the builder),
   show the diff and apply only after the user's explicit OK:
   `scripts/hpy squadctl.py apply <key>`. A new lane without a model needs
   `skills/assigning-models` first.
7. After a retire, `apply` leaves the old profile in place. On the user's OK run
   `hermes profile export <bot> -o local/backups/<bot>.tar.gz`, then
   `hermes profile delete <bot> --yes`.

## Pitfalls

- Editing a profile's `config.yaml`, `SOUL.md` or `skills/` by hand: the next
  `apply` overwrites it. Change the overlay.
- A cron `agent` job whose `script` prints on quiet ticks: only empty stdout or
  a last line `{"wakeAgent": false}` skips the agent
  (`skills/hermes-platform/references/cron-and-gates.md`).
- `passthrough` on a bot with `web` or `browser`: `skills/designing-squads` ->
  Rules.

## Verification

- `scripts/hpy squadctl.py plan <key> --json` reports every bot `unchanged`.
- `hermes -p <bot> config get <config-key>` and `hermes -p <bot> cron list`
  show the new values.
- After a retire, `hermes profile list` no longer shows the bot and
  `scripts/hpy squadctl.py doctor` reports no `fail`.
