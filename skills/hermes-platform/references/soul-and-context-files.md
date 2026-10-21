# SOUL.md and context files

## SOUL.md

- `SOUL.md` is the profile's primary identity: first in the system prompt, it defines who the agent
  is and how it speaks. Procedures belong in skills and project-specific instructions in `AGENTS.md`.
- It loads only from the profile's `HERMES_HOME`, never from the working directory or a repo. An
  empty `SOUL.md` adds nothing; `profile create` seeds a default one.
- One SOUL per profile; squad tooling copies it from `squads/<key>/souls/<bot>.md` when it differs.
  Budgets: `scripts/skill_lint.py --rules` (`soul-lines`, `soul-chars`).

## Context files

- Project context loads one file type per session, first match wins: `.hermes.md` / `HERMES.md`,
  `AGENTS.override.md`, `AGENTS.md` (a chain from the git root to the cwd), `CLAUDE.md`,
  `.cursorrules`. `SOUL.md` sits outside this chain.
- Context files and `SOUL.md` are scanned for prompt injection before entering the system prompt. A
  hit blocks a project file, and blocks `SOUL.md` when `distribution.yaml` owns it (a manifest with no
  `distribution_owned` list owns everything). A user-authored `SOUL.md` only warns. A blocked file is
  replaced by a `[BLOCKED: ...]` notice in the prompt.
- Which file does what: `website/docs/user-guide/which-file-does-what.md`. Context files:
  `website/docs/user-guide/features/context-files.md`; `@`-references for files, folders, diffs and
  URLs: `website/docs/user-guide/features/context-references.md`.

## profile.yaml and ui_meta

- `profile.yaml` carries profile metadata: `description`, `display_name` and the `ui_meta` block the
  Bots pane reads (`bot-mode-and-desktop.md` -> Bots pane and ui_meta).
- Squad tooling writes config in-process through Hermes's own writer (`set_config_value`), not
  `hermes config set`, and merges `ui_meta` with a bumped `_ui_meta_revisions` counter
  (`scripts/_profile_apply.py`).

## Secrets

- Credential files, passwords and env passthrough: `approvals-and-security.md`.
