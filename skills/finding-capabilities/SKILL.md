---
name: finding-capabilities
description: "Searches plugins, skills, MCP and connectors. Use when a squad needs a capability from a catalog."
---

# Finding capabilities

## When to Use

- A bot needs a tool, skill or integration nobody ships yet.
- The user asks what the ecosystem offers for a task (video, deploy, SEO, ...).

## Procedure

1. Search first: `python3 scripts/catalog_search.py "<query>" ... [--kind
   plugin|skill|mcp|connector] [--hub] [--json]`. It covers the plugin catalog,
   official optional skills, bundled skills, MCP and connector names
   (`scripts/catalog_search.py`).
2. For a candidate skill, run `hermes skills inspect <identifier>` and read its
   trust level, description and SKILL.md preview before proposing it.
3. For a community plugin, read its catalog entry in `plugin-catalog/`:
   presence there is the trust signal and the entry carries the disclosure
   lines (`plugin-catalog/README.md`).
4. Quote the disclosure and any licence to the user verbatim and get an
   explicit OK before installing anything with `confirm` semantics
   (`docs/decisions.md` C-02). Non-commercial licences (PolyForm NC) and
   per-seat licences (Remotion) need their own question.
5. Declare the result as a `keep` (prefix `bundled:`, `official:<cat>/<name>`,
   `hub:`, `local:`) or a plugin/MCP entry in the squad manifest, then `apply`
   (`squads/_schema/squad.schema.json`).
6. Prefer an existing bundled or official skill over a hub one, and one skill
   over a plugin when the job is procedural.

## Pitfalls

- Installing first and asking later: hub skills and community plugins install
  only after the user's OK with the disclosure shown.
- Pinning a hub identifier without checking its author and licence: keep the
  search result unpinned until reviewed (`docs/decisions.md` C-02).
- Giving a capability to the whole squad "just in case": it goes on the bot
  whose role needs it.
- Credential-heavy connectors on bots that read the web.

## Verification

- The chosen identifier resolves (`hermes skills inspect` or a catalog entry
  with its disclosure).
- The manifest entry is schema-valid and `plan <key> --json` shows the install
  action.
- The user's OK is recorded in the decision or card that introduced it.
