---
name: tracking-updates
description: "Digests Hermes releases and docs, proposes each change. Use when builder-watch wakes or the user asks what changed upstream."
---

# Tracking updates

## When to Use

- The `builder-watch` cron wakes the builder with a `## Script Output` block.
- The user asks what changed in Hermes, what to apply, or for an audit of the references.
- A builder chat opens while `local/state/digests/*.json` holds items with `status: open`.
- The squads themselves are not this skill: `builder-update` applies them with no agent
  (`skills/installing-squads` step 6).

## Procedure

### Digest mode (cron)

`builder-watch` (`builder.yaml` -> `bots.builder.cron.builder-watch`) runs the
gate `scripts/watch_upstream.py` (`--help` lists the three signals: releases,
local version, local docs). With `--docs-ref origin/main` (maintainer mode:
the overlay `local/squads/builder/squad.yaml` sets
`bots.builder.cron.builder-watch.args`) the docs signal reads Hermes `main`, so
a change is digested before its release. A quiet tick prints `{"wakeAgent": false}` and no
agent runs. On a change Hermes prepends the gate's stdout to this turn as
`## Script Output`; `context.changed` names the signals that fired.

1. Read only what the context lists:
   - `release`: the files in `context.filtered` and `context.overflow`
     (priority bullets over the cap);
   - `hermes`: `context.hermes` (local version change);
   - `docs`: the diff in `context.docs.diff` (and `context.docs.overflow`).
     `context.docs.references` names the `skills/hermes-platform/references/`
     files the changed docs feed (`*` = all); `new_pages` are docs no reference
     maps yet.
2. For each docs change, compare the diff with the named reference and keep
   only changes that make a reference line wrong or leave out a behavior a
   squad depends on. Formatting and wording changes are no item.
3. Write `local/state/digests/<date>.json`:

```json
{
  "date": "YYYY-MM-DD",
  "tags": ["vX.Y.Z"],
  "items": [
    {
      "area": "profiles | skills | kanban | cron | plugins | mcp | connectors | desktop | projects | gateways | other",
      "change": "one line, dated facts only",
      "evidence": "path or URL the change was read from",
      "reference": "references/<file>.md the change makes stale, or none",
      "affects": "which installed squad or bot this touches, or none",
      "action": "update-reference | new-capability | deprecation | config-change | none",
      "confidence": "high | medium | low",
      "status": "open | applied | declined"
    }
  ]
}
```

4. Reply with at most 5 lines in the user's language (cron delivers them to
   `bot-chat:builder`): one line per `open` item with action other than `none`,
   naming the installed squad it touches ("your web squad: ..."), and whether
   it needs `hermes update`. Edit nothing else. When the gate output is unreadable or a listed file is
   missing, reply with `[CRON_FAILURE]` as the first line and the cause on the
   next line: the run is recorded as failed and alerts once.

### Apply mode (builder)

1. Read every digest item with `status: open` and propose them one by one
   with `clarify` ("Hermes vX.Y.Z changes X; your web squad uses it for Y;
   apply?"). Apply only after an explicit yes; set `status` to `applied` or
   `declined` so it is never proposed twice. In maintainer mode a generic fix
   (reference, script, plugin) is a bug fix: apply it to the squads repo
   (`skills/contributing-upstream` maintainer mode) and report after.
2. A Hermes fact (`update-reference`): verify it in the live Hermes first
   (`--help`, the source). The references are distribution-owned, so a local
   edit is overwritten by the next update: record it in
   `skills/hermes-local-notes/SKILL.md` (`skills/hermes-platform` step 3) and
   send the reference fix upstream (`skills/contributing-upstream`). When a
   release rewrites a reference, bump `verified_against` in
   `scripts/data/doc-sources.json` with it.
3. A squad change: write the overlay (`skills/changing-bots`), then `plan`,
   user OK, `apply`.
4. A new Hermes release: tell the user to run `hermes update` (it moves
   release to release; `hermes update --set-channel main` follows every
   commit). Never run it from a bot: it restarts every gateway. After it, the
   next `builder-update` brings every bot's SOUL and toolsets to the new
   Hermes, and the next `builder-watch` diffs the new docs.

### Audit mode (each minor release, or on request)

The docs signal sees only the mapped docs. Once per minor release:

1. Fan out read-only `delegate_task` children, 2-4 references each, with the
   paths from `scripts/data/doc-sources.json`. Each returns items
   `{kind: wrong|stale|missing, claim, fact, evidence, priority}`.
2. Verify every `wrong` and `high` item in the source yourself: children are
   self-reports.
3. Write `local/state/audits/<date>.json`, then run Apply mode on the items.
   A docs page an item cites that the map lacks goes into the map.

## Pitfalls

- Acting on a `confidence: low` item: research it first or drop it.
- Skipping the digest file: a change stays pending until
  `local/state/digests/<date>.json` is newer than the wake, so the next tick
  wakes again with the same diff.
- Editing `skills/hermes-platform/references/` in the installed profile:
  `builder-update` replaces it (a backup is kept); fixes go upstream.
- A `main`-only change (maintainer mode) is not in the user's Hermes yet:
  ship code that works on both sides (try the new key, fall back to the old)
  and say "after <last release>" in the reference.
- Docs describe intent; the source wins when they disagree (example: a
  documented flag the CLI lacks). Record such a gap as `wrong`.

## Verification

- The digest file matches the JSON shape and every `evidence` points at a real
  file or URL.
- No repository file changed in digest mode.
- Applied items appear in the overlay, `skills/hermes-local-notes/` or an
  upstream PR after the user's yes.
