# SOUL.md and context files

## Contents

- [SOUL.md](#soulmd)
- [Context files](#context-files)
- [profile.yaml and ui_meta](#profileyaml-and-ui_meta)
- [Secrets](#secrets)

## SOUL.md

- `SOUL.md` is the primary identity of a profile: first in the system prompt, it
  defines who the agent is and how it speaks
  (`website/docs/guides/use-soul-with-hermes.md`).
- SOUL is for identity and voice; procedures belong in skills, and instructions
  for coding agents in `AGENTS.md`
  (`website/docs/guides/use-soul-with-hermes.md`).
- One SOUL per profile; squad tooling copies it from `squads/<key>/souls/<bot>.md`
  when it differs (`scripts/squadctl.py`).
- Squad convention: SOUL files stay within 6 lines and 800 characters
  (`scripts/skill_lint.py`, rules `soul-lines`, `soul-chars`).

## Context files

- `AGENTS.md`, `.cursorrules` and `SOUL.md` are scanned for prompt injection
  before entering the system prompt; a match blocks or warns
  (`website/docs/user-guide/security.md`, "Context file scanning").
- Which file does what at a glance: `website/docs/user-guide/which-file-does-what.md`.
- Context files and context references (file mentions, rules) are documented in
  `website/docs/user-guide/features/context-files.md` and
  `website/docs/user-guide/features/context-references.md`.

## profile.yaml and ui_meta

- `profile.yaml` in a profile directory carries profile metadata; the Desktop
  Bots pane writes `ui_meta: {hermes-bots: {...}}` there
  (`website/docs/user-guide/bot-mode.md`, "What actually makes a chat a Bot Chat").
- The `hermes-bots` block is also the Bot-Mode-managed marker: one profile with
  it marks the whole install, and there is no CLI command that writes it
  (`website/docs/user-guide/bot-mode.md`).
- Fields the Desktop reads include `title`, `hidden`, `pinned` and section
  filing via `sectionId` / `sectionName`
  (`apps/desktop/src/plugins/hermes-bots/bot-row.tsx`,
  `apps/desktop/src/plugins/hermes-bots/data.bot-meta.test.ts`).
- Squad tooling writes only the `ui_meta` key of `profile.yaml`; every other
  config change goes through `hermes -p <bot> config set`
  (`scripts/squadctl.py`, `scripts/_profile_apply.py`).

## Secrets

- `.env` and `auth.json` hold credentials; no squad script reads or prints them
  (`scripts/squadctl.py` docstring; `website/docs/user-guide/secrets/index.md`).
- Environment values reach `terminal` children only through
  `terminal.env_passthrough` (`website/docs/user-guide/security.md`).
