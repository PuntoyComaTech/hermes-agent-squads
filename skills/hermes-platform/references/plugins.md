# Plugins

## Contents

Where plugins come from; Enabling; Inspecting and pinning; What a plugin can add; What a plugin cannot
do; Desktop half and install links; The catalog; Agent Plugins v1 packages; Isolation.

## Where plugins come from

- The plugin manager scans, in order: bundled (`<repo>/plugins/<name>/`), user
  (`$HERMES_HOME/plugins/<name>/`), project (`./.hermes/plugins/<name>/`, behind
  `HERMES_ENABLE_PROJECT_PLUGINS=1`) and pip entry points; on a name collision the later source wins.
  Memory providers resolve the other way (the bundled provider wins), so a user memory provider needs
  a unique name.
- Bundled examples: `disk-cleanup` (cleans ephemeral files on session end) and `security-guidance`
  (pattern-matches dangerous code in `write_file` / `patch` / `skill_manage` and appends a warning;
  refuses the write when `SECURITY_GUIDANCE_BLOCK=1`). Full list:
  `website/docs/user-guide/features/built-in-plugins.md`.
- Plugin system: `website/docs/user-guide/features/plugins.md`; building one:
  `website/docs/developer-guide/plugins/index.md`. Hooks: `hooks.md`.

## Enabling

- Enablement is per profile: each profile's `config.yaml` holds its own `plugins.enabled` /
  `plugins.disabled`, and user plugins load from that profile's `plugins/` directory. Enabling a
  plugin for one bot enables nothing for another.
- General plugins (bundled and user) load only after `hermes plugins enable <name>` or an entry under
  `plugins.enabled`; `hermes plugins disable <name>` turns one off. Platform adapters, memory
  providers, model providers and image backends are selected by their own config keys instead.
- User-installed plugins install disabled. `hermes plugins install <name>` asks "Enable now?";
  scripts pass `--enable` or `--no-enable`.
- Squad manifests declare `plugins: {enable: [...], disable: [...]}`; `squadctl apply` enables bundled
  plugins and installs catalog ones only after the user confirms.
- A plugin runs with the bot's permissions; enable it only where needed (`security-guidance` only on
  bots that write code). Approval: `AGENTS.md` -> Rules; steps: `skills/finding-capabilities/SKILL.md`.
- `plugins.load_timeout_seconds` (default 10) and `plugins.hook_callback_timeout` (default 30) bound
  loading and each hook; a timed-out `pre_tool_call` blocks the tool.

## Inspecting and pinning

- `hermes plugins show <name>` (host isolation status, hooks), `capabilities` (declared vs granted),
  `doctor [path-or-id]` (discovery in a temporary `HERMES_HOME`), `validate <dir> --install-deps` (the
  catalog CI check), `check-updates`.
- `hermes plugins install <src> --ref <40-char SHA>` pins one commit (no tags or branches);
  `hermes plugins update` refuses to move a pinned plugin; re-pin with `install --force --ref <new>`.
- Plugin packs: `hermes plugins pack install|export|show <pack.yaml>` pin a set of plugins to exact
  SHAs with non-secret config seeds; installing fans out to pinned installs with per-plugin consent.
  This is the reproducible way to give several profiles the same plugin set.

## What a plugin can add

Each is a `ctx.*` call in `register(ctx)`:

- Tools (`register_tool`), lifecycle hooks (`register_hook`, `hooks.md`), in-session slash commands
  (`register_command`), CLI subcommands `hermes <name> ...` (`register_cli_command`), middleware,
  system-prompt sections.
- Bundled skills (`register_skill(name, SKILL.md)`): read-only, loaded only explicitly as
  `skill_view("<plugin>:<skill>")`, and absent from the `<available_skills>` index.
- Automation blueprints (`register_automation_blueprint`): listed in `/blueprint`, the dashboard and
  the Desktop cron form, per profile where the plugin is enabled. A job created from one is an
  ordinary cron job and keeps running after the plugin is disabled or removed.
- Durable state: `plugin_data_dir()` and `plugin_db()` survive `hermes plugins update` and `remove`,
  scoped to the active profile.

## What a plugin cannot do

- Create or clone a profile: profiles come from `hermes profile install`
  (`profiles-and-distributions.md`). A squad ships as a profile distribution, not a plugin.
- Change another profile's plugin state.
- Update itself inside the catalog: catalog rule 3 forbids self-updaters; updates are SHA-bump PRs
  plus `hermes plugins update`.
- Replace or monkeypatch core (catalog rule 9); such plugins fail `hermes plugins validate`.

## Desktop half and install links

- A unified package holds `plugin.yaml`, `skills/`, `dashboard/` (`manifest.json` + `plugin_api.py`)
  and `desktop/plugin.js`. Hermes copies the desktop half into `$HERMES_HOME/desktop-plugins/<id>/`
  (app-level, once for all profiles); edits show only after Rescan, or live from a checkout linked
  with `ln -s <checkout> ~/.hermes/plugins/<id>`.
- Both halves are opt-in: the desktop half in Capabilities -> Plugins, the Python half in
  `plugins.enabled`.
- One-click links: `hermes://plugin/install?repo=owner/repo&enable=1` opens a confirmation dialog and
  never auto-installs; `catalog=<name>` installs the reviewed pin; `force=1` replaces an install.

## The catalog

- `plugin-catalog/` in the Hermes tree holds Nous-approved entries, one YAML each with `name`, `repo`,
  an exact `sha`, `description` and `tier: official | community`; presence in the directory is the
  trust signal. A catalog entry is not a code audit.
- Fields that change a pick:
  - `category` is the browse shelf: `desktop` (default), `memory`, `platform`, `web`, `tools`,
    `voice`, `automation`, `models`, `general`.
  - `requires_hermes` is the minimum Hermes version.
  - `known_issues` are shown at the install prompt and never block it.
- `hermes plugins search [term] [--json]` and `hermes plugins install <name>` use it. The desktop
  `catalog` toolset (`manage_catalog`) installs catalog picks through an approval card; it does not
  search.
- Squad tooling: `scripts/hpy catalog_search.py "<query>" --kind plugin --shelf <shelf>
  --hermes-version <X.Y.Z>` keeps one shelf and drops entries this Hermes cannot run; each hit lists
  `requires_hermes` and `known_issues`.
- Memory providers are plugins on the `memory` shelf: `memory.md`. Model providers are plugins on the
  `models` shelf: install with `hermes plugins install <name>`, log in with `hermes auth`, then
  `models-and-auxiliary.md` -> Providers and the models cache.

## Agent Plugins v1 packages

- A portable package (`plugin.json`, `skills/*/SKILL.md`, root `mcp.json`) installs through
  `hermes plugins install` and stays disabled until `hermes plugins enable <name>`.
- Enabled, it adds read-only skills named `agent-plugin-<slug>-<hash>` (find them with `skills_list`)
  and the MCP servers in its `mcp.json`. A server in `config.yaml` with the same name wins over the
  package's.
- The format defines no trust, permissions or sandbox: enabling grants full trust, like any plugin.
- The catalog name and the manifest name can differ (`touchdesigner` installs as `td`); `enable`,
  `disable`, `show`, `update` and `remove` accept either.

## Isolation

- `plugins.isolation: host` (default `in_process`) runs a profile's user-installed plugins in one
  separate process per profile, holding only that profile's environment and secrets; a crash restarts
  the host, not Hermes. Bundled plugins stay in-process.
- Under `host`, plugins that need in-process code fail to load with a reason: platform adapters,
  approval transports, model providers that build their own SDK client, streaming dashboard endpoints,
  monkeypatching plugins. A plugin's `hermes <command>` subcommands are skipped; the rest loads.
- Check `hermes plugins show <name>` and `known_issues` before choosing `host`.
- `hermes -p <profile> plugins list` wraps the Name column of its table: a grep for a long plugin name misses an
  enabled one. Read the Status column, or the profile config's `plugins.enabled` list, before reporting it off.
