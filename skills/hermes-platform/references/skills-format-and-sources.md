# Skill format and sources

## Format

- A skill is a directory with `SKILL.md` whose YAML frontmatter holds `name` and
  `description`.
- The prompt index keeps 60 characters of the description and cuts longer ones
  to 57 plus `...` (`SKILL_PROMPT_DESC_LIMIT`); put the
  trigger in the first clause.
- Squad budgets: `scripts/skill_lint.py --rules`. Authoring:
  `skills/authoring-skills/SKILL.md`.

## Where skills live

- Precedence for a duplicate name: project, local (`~/.hermes/skills/`),
  `skills.create_dir`, `skills.external_dirs`; the shadowed copy is hidden and
  logged.
- `skills.external_dirs` adds read-in-place skill directories;
  `skills.auto_load` lists skills loaded into every session.
- Agent-created skills go to `~/.hermes/skills/`, or `skills.create_dir` when
  set; existing skills are edited where found.
- Squad skills are copied, not linked, into each profile with a sha marker, so a
  repo change reaches no bot until `apply` runs.

## Bundled, official and hub skills

- Profiles seed the bundled catalog unless created with
  `--no-skills`; `hermes skills opt-out` stops future seeding and `--remove`
  also deletes unmodified bundled skills.
- Official optional skills install as `official/<category>/<name>`, for example
  `official/creative/impeccable` (`optional-skills/`).
- `hermes skills inspect <identifier>` shows name, source, trust and a SKILL.md
  preview before install.
- `hermes skills install <identifier> --yes` runs a security scan first;
  `--force` overrides a blocked verdict except `dangerous` on community or
  trusted sources.
- Catalog: `website/docs/reference/skills-catalog.md`; workflow:
  `website/docs/guides/work-with-skills.md`.
