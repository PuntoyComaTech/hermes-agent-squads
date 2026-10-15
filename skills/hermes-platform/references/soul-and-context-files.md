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
- Budgets: `scripts/skill_lint.py --rules` (`soul-lines`, `soul-chars`).

## Context files

- `AGENTS.md`, `.cursorrules` and `SOUL.md` are scanned for prompt injection
  before entering the system prompt; a match blocks or warns
  (`website/docs/user-guide/security.md`, "Context File Injection Protection").
- Which file does what at a glance: `website/docs/user-guide/which-file-does-what.md`.
- Context files: `website/docs/user-guide/features/context-files.md`; `@`-references
  for files, folders, diffs and URLs:
  `website/docs/user-guide/features/context-references.md`.

## profile.yaml and ui_meta

- `profile.yaml` in a profile directory carries profile metadata; the Desktop
  Bots pane writes `ui_meta: {hermes-bots: {...}}` there
  (`website/docs/user-guide/bot-mode.md`, "What actually makes a chat a Bot Chat").
- Fields the Desktop reads include `title`, `hidden`, `pinned` and section
  filing via `sectionId` / `sectionName`
  (`apps/desktop/src/plugins/hermes-bots/types.ts`).
- Squad tooling writes config through Hermes's own writer (`set_config_value`)
  in-process, and merges the `ui_meta` block of `profile.yaml` with a bumped
  `_ui_meta_revisions` counter
  (`scripts/squadctl.py`; `scripts/_profile_apply.py`).

## Secrets

- Credential files, passwords and env passthrough: `approvals-and-security.md`.
