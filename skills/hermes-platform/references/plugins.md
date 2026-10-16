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
- User-installed plugins install disabled. `hermes plugins install <name>`
  asks "Enable now?"; scripts pass `--enable` or `--no-enable`.

## The catalog

- `plugin-catalog/` in the Hermes tree holds Nous-approved entries, one YAML
  each with `name`, `repo`, an exact `sha`, `description` and `tier: official |
  community`; presence in the directory is the trust signal. A catalog entry
  is not a code audit.
- Fields that change a pick:
  - `category` is the browse shelf: `desktop` (default), `memory`,
    `platform`, `web`, `tools`, `voice`, `automation`, `models`, `general`.
  - `requires_hermes` is the minimum Hermes version.
  - `known_issues` are shown at the install prompt and never block it.
- `hermes plugins search` / `hermes plugins install <name>` use it; the desktop
  `catalog` toolset searches it and installs through an approval card.
- `scripts/hpy catalog_search.py "<query>" --kind plugin --shelf <shelf>
  --hermes-version <X.Y.Z>` keeps one shelf and drops entries this Hermes
  cannot run; each hit lists `requires_hermes` and `known_issues`.
- Memory providers are plugins on the `memory` shelf: `memory.md`. Model
  providers are plugins on the `models` shelf: install with `hermes plugins
  install <name>`, log in with `hermes auth`, then `models-and-auxiliary.md`
  -> Providers.

## Agent Plugins v1 packages

- A portable package (`plugin.json`, `skills/*/SKILL.md`, root `mcp.json`)
  installs through `hermes plugins install` and stays disabled until
  `hermes plugins enable <name>`.
- Enabled, it adds read-only skills named `agent-plugin-<slug>-<hash>` (find
  them with `skills_list`) and the MCP servers in its `mcp.json`. A server in
  `config.yaml` with the same name wins over the package's.
- The format defines no trust, permissions or sandbox: enabling grants full
  trust, like any plugin.
- The catalog name and the manifest name can differ (`touchdesigner` installs
  as `td`); `enable`, `disable`, `show`, `update` and `remove` accept either.

## Isolation

- `plugins.isolation: host` (default `in_process`) runs a profile's
  user-installed plugins in one separate process per profile, holding only that
  profile's environment and secrets; a crash restarts the host, not Hermes.
  Bundled plugins stay in-process.
- Under `host`, plugins that need in-process code fail to load with a reason:
  platform adapters, approval transports, model providers that build their own
  SDK client, streaming dashboard endpoints, monkeypatching plugins. A plugin's
  `hermes <command>` subcommands are skipped; the rest of it loads.
- `hermes plugins show <name>` reports whether a plugin runs in the host and
  why not; check it and `known_issues` before choosing `host`.
