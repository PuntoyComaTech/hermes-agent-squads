---
name: tracking-updates
description: "Digests upstream changes and proposes each to the user. Use when Hermes or the squads repo ships an update."
---

# Tracking updates

## When to Use

- The `builder-watch` gate reports a change (new Hermes release, local version
  bump, new squads version).
- The user asks what changed upstream or what to apply.

## Procedure

### Digest mode (cron)

The `builder-watch` cron runs daily on the builder
(`builder.yaml -> bots.builder.cron`):

1. The zero-LLM gate `scripts/watch_upstream.py` compares Hermes releases, the
   local `hermes --version` and the raw `distribution.yaml` on the squads repo
   against `local/state/watch.json`. No change: it prints
   `{"wakeAgent": false}` and the tick costs zero tokens.
2. On change it prints `{"wakeAgent": true, "context": {...}}` with the tags,
   the filtered release notes (`scripts/hpy watch_upstream.py --help`) and the
   squads version delta.
3. The agent runs on the `digest` lane
   (`builder.yaml` -> `bots.builder.cron.builder-watch.agent`) with this skill,
   reads only the filtered files and writes the digest JSON below. It posts at
   most 5 lines to `bot-chat:builder` and edits nothing.

Digest JSON (`local/state/digests/<date>.json`):

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

### Apply mode (builder)

1. Propose each item to the user one by one ("vX.Y.Z adds X; your web squad can
   use it for Y; apply?"). Never apply silently.
2. Knowledge updates go to `skills/hermes-local-notes/` (not shipped), so a
   distribution update keeps them.
3. Squad changes go to the overlay `local/squads/<key>/squad.yaml`, then
   `plan`, user OK, `apply`.
4. A new squads version: suggest `hermes profile update builder`, which never
   touches `local/`, memories, sessions or `.env`
   (`skills/hermes-platform/references/profiles-and-distributions.md`).

## Pitfalls

- Summarizing from the unfiltered release body: only the filtered file may
  reach the digest model.
- Acting on a `confidence: low` item: research first or drop it.

## Verification

- The digest file exists, matches the JSON shape and every `evidence` points at
  a real file or URL.
- No repository file changed in digest mode.
- Applied items appear in the overlay or `hermes-local-notes/` with the user's
  OK recorded.
