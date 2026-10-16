# Plugins

## Where plugins come from

- The plugin manager scans, in order: bundled (`<repo>/plugins/<name>/`), user
  (`~/.hermes/plugins/<name>/`), project (`./.hermes/plugins/<name>/`, behind
  `HERMES_ENABLE_PROJECT_PLUGINS=1`) and pip entry points; on a name collision
  the later source wins.
- Bundled examples: `disk-cleanup` (cleans ephemeral files on session end) and
  `security-guidance` (pattern-matches dangerous code in `write_file` / `patch`
  / `skill_manage` and appends a warning; refuses the write when
  `SECURITY_GUIDANCE_BLOCK=1`).
- Plugin system: `website/docs/user-guide/features/plugins.md`; building one:
  `website/docs/developer-guide/plugins/index.md`. Hooks: `hooks.md`.

## Enabling

- Bundled plugins ship disabled and load only after `hermes plugins enable
  <name>` or an entry under `plugins.enabled`; `hermes plugins disable <name>`
  turns one off.
- Squad manifests declare `plugins: {enable: [...], disable: [...]}`;
  `squadctl apply` enables bundled plugins and installs catalog ones only after
  the user confirms.
- A plugin runs with the bot's permissions; enable it only where needed
  (`security-guidance` only on bots that write code). Approval: `AGENTS.md` ->
  Rules; steps: `skills/finding-capabilities/SKILL.md`.

## The catalog

- `plugin-catalog/` in the Hermes tree holds Nous-approved entries, one YAML
  each with `name`, `repo`, an exact `sha`, `description`, `tier: official |
  community` and optional `known_issues`; presence in the directory is the
  trust signal (`plugin-catalog/README.md`).
- `hermes plugins search` / `hermes plugins install <name>` use it; the desktop
  `catalog` toolset searches it and installs through an approval card
  (`plugin-catalog/README.md`).
