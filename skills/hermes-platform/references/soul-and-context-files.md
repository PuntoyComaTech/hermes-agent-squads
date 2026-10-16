# SOUL.md and context files

## SOUL.md

- `SOUL.md` is the profile's primary identity: first in the system prompt, it
  defines who the agent is and how it speaks. Procedures belong in skills and
  project-specific instructions in `AGENTS.md`.
- One SOUL per profile; squad tooling copies it from
  `squads/<key>/souls/<bot>.md` when it differs.
  Budgets: `scripts/skill_lint.py --rules` (`soul-lines`, `soul-chars`).

## Context files

- `AGENTS.md`, `.cursorrules` and `SOUL.md` are scanned for prompt injection
  before entering the system prompt. A hit blocks a project file and a
  distribution-owned `SOUL.md`; the profile's own `SOUL.md` only warns.
- Which file does what: `website/docs/user-guide/which-file-does-what.md`.
  Context files: `website/docs/user-guide/features/context-files.md`;
  `@`-references for files, folders, diffs and URLs:
  `website/docs/user-guide/features/context-references.md`.

## profile.yaml and ui_meta

- `profile.yaml` carries profile metadata, including the `ui_meta` block the
  Bots pane reads: `bot-mode-and-desktop.md` -> Bots pane and ui_meta.
- Squad tooling writes config in-process through Hermes's own writer
  (`set_config_value`), not `hermes config set`, and merges `ui_meta` with a
  bumped `_ui_meta_revisions` counter (`scripts/_profile_apply.py`).

## Secrets

- Credential files, passwords and env passthrough: `approvals-and-security.md`.
