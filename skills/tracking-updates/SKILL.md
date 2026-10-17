---
name: tracking-updates
description: "Digests Hermes releases and proposes each change. Use when Hermes ships a release or the user asks what changed upstream."
---

# Tracking updates

## When to Use

- The `builder-watch` cron wakes the builder with a `## Script Output` block.
- The user asks what changed upstream or what to apply.

## Procedure

### Digest mode (cron)

`builder-watch` (`builder.yaml` -> `bots.builder.cron.builder-watch`) runs the
gate `scripts/watch_upstream.py` (`--help` lists the signals). A quiet tick
prints `{"wakeAgent": false}` and no agent runs. On a change Hermes prepends
the gate's stdout to this turn as `## Script Output`.

Squads updates are not digested here: the `builder-update` cron applies them
with no agent (`skills/installing-squads` step 6).

1. Read only the files listed in `context.filtered` and `context.overflow`
   (priority bullets over the cap).
2. Write `local/state/digests/<date>.json`:

```json
{
  "date": "YYYY-MM-DD",
  "tags": ["vX.Y.Z"],
  "items": [
    {
      "area": "profiles | skills | kanban | cron | plugins | mcp | connectors | desktop | projects | gateways | other",
      "change": "one line, dated facts only",
      "evidence": "path or URL the change was read from",
      "affects": "which installed squad or bot this touches, or none",
      "action": "update-reference | new-capability | deprecation | config-change | none",
      "confidence": "high | medium | low"
    }
  ]
}
```

3. Reply with at most 5 lines (cron delivers them to `bot-chat:builder`).
   Edit nothing else. When the gate output is unreadable or a listed file is
   missing, reply with `[CRON_FAILURE]` as the first line and the cause on the
   next line: the run is recorded as failed and alerts once.

### Apply mode (builder)

1. Propose each item to the user one by one ("Hermes vX.Y.Z adds X; your web
   squad can use it for Y; apply?"). Apply only after an explicit yes.
2. A Hermes fact: record it as `skills/hermes-platform` step 2 says.
3. A squad change: write the overlay (`skills/changing-bots`), then `plan`,
   user OK, `apply`.
4. A new Hermes release: tell the user to run `hermes update` (it moves
   release to release; `hermes update --set-channel main` follows every
   commit). Never run it from a bot: it restarts every gateway.

## Pitfalls

- Acting on a `confidence: low` item: research it first or drop it.
- Skipping the digest file: a change stays pending until
  `local/state/digests/<date>.json` is newer than the wake, so the next tick
  wakes again.

## Verification

- The digest file matches the JSON shape and every `evidence` points at a real
  file or URL.
- No repository file changed in digest mode.
- Applied items appear in the overlay or `skills/hermes-local-notes/` after
  the user's yes.
