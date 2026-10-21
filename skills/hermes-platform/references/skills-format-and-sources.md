# Skill format and sources

## Format

- A skill is a directory with `SKILL.md` whose YAML frontmatter holds `name` and `description`.
- The prompt index shows at most 60 characters of the description: a longer one is cut to 57 plus
  `...` (`SKILL_PROMPT_DESC_LIMIT`). Put the trigger in the first clause.
- `skill_manage` refuses to create a new skill whose description exceeds 60 characters; existing
  skills only warn (Hermes linter: `tools/skill_linter.py`).
- Squad budgets: `scripts/skill_lint.py --rules`. Authoring: `skills/authoring-skills/SKILL.md`.

## Where skills live

- Precedence for a duplicate name across tiers: project, local (`~/.hermes/skills/`),
  `skills.create_dir`, `skills.external_dirs`; the shadowed copy is hidden and logged. Two different
  skills with the same name inside one tier are refused as ambiguous.
- Project skills (`<repo>/.hermes/skills/`, `<repo>/.agents/skills/`; the repo is the nearest
  ancestor with `.git`) load only after `hermes -p <bot> skills trust <repo>`. Trust is per profile
  (`skills.trusted_project_dirs`); `skills untrust <repo>` revokes it, and
  `skills.project_discovery: false` stops the scan.
- `skills.external_dirs` adds read-in-place skill directories; `skills.auto_load` lists skills loaded
  into every session, resolved when the prompt is first built (a missing name warns and is skipped).
- Agent-created skills go to `~/.hermes/skills/`, or `skills.create_dir` when set; existing skills are
  edited where found.
- Squad skills are copied, not linked, into each profile with a sha marker, so a repo change reaches
  no bot until `apply` runs.

## Bundled, official and hub skills

- Profiles seed the bundled catalog unless created with `--no-skills`; `hermes skills opt-out` stops
  future seeding (`opt-in` undoes it) and `--remove` also deletes unmodified bundled skills.
- Official optional skills install as `official/<category>/<name>`, for example
  `official/creative/impeccable` (`optional-skills/`).
- `hermes skills inspect <identifier>` shows name, source, trust and a SKILL.md preview before
  install.
- `hermes skills install <identifier>` always runs a security scan; `--yes` only skips the
  confirmation. `--force` overrides a blocked verdict except `dangerous` on community or trusted
  sources.
- Catalog: `website/docs/reference/skills-catalog.md`; workflow:
  `website/docs/guides/work-with-skills.md`.
