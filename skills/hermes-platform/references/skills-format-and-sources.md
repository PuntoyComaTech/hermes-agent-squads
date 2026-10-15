# Skill format and sources

## Contents

- [Format](#format)
- [Where skills live](#where-skills-live)
- [Bundled, official and hub skills](#bundled-official-and-hub-skills)
- [Authoring](#authoring)

## Format

- A skill is a directory with `SKILL.md` and YAML frontmatter holding `name` and
  `description` (`website/docs/developer-guide/creating-skills.md`).
- The description is truncated to 60 characters in the prompt index
  (`SKILL_PROMPT_DESC_LIMIT`, `agent/skill_utils.py`), so the first clause must
  stand alone; keep the trigger early.
- Squad format budgets (line counts, description shape, one-level references,
  evals) are enforced by `scripts/skill_lint.py` (`docs/decisions.md` V-09).

## Where skills live

- Precedence for a duplicate skill name: project, local (`~/.hermes/skills/`),
  `skills.create_dir`, `skills.external_dirs`; the shadowed copy is hidden and
  logged (`website/docs/user-guide/features/skills.md`).
- `skills.external_dirs` in config adds read-in-place skill directories;
  `skills.auto_load` lists skills loaded into every session
  (`website/docs/user-guide/features/skills.md`; `website/docs/user-guide/configuration.md`).
- Agent-created skills are written to `~/.hermes/skills/` (or
  `skills.create_dir` when set) and modified where found
  (`website/docs/user-guide/features/skills.md`).
- Squad skills are copied, not linked, into each profile with a sha marker, so a
  repo change reaches no bot until `apply` runs (`scripts/squadctl.py`).

## Bundled, official and hub skills

- Profiles seed with the bundled catalog (58 skills in v0.22.0) unless created
  with `--no-skills`; `hermes skills opt-out` stops future seeding and `--remove`
  also deletes unmodified bundled skills
  (`website/docs/user-guide/features/skills.md`).
- Official optional skills install as `official/<category>/<name>` (verified
  identifier `official/creative/impeccable`, `hermes skills inspect`), catalog:
  `website/docs/reference/optional-skills-catalog.md`.
- Hub skills install with `hermes skills install <identifier> --yes`; a scan
  verdict gates the install, and `--force` overrides it except a `dangerous`
  verdict on community or trusted sources (`hermes skills install --help`).
- `hermes skills inspect <identifier>` shows name, source, trust and the SKILL.md
  preview before anything is installed (`hermes skills inspect` output).
- Catalogs: `website/docs/reference/skills-catalog.md`; workflow:
  `website/docs/guides/work-with-skills.md`.

## Authoring

- `skills/authoring-skills/SKILL.md`.
