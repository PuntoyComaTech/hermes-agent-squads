# Plugins

## Contents

- [Where plugins come from](#where-plugins-come-from)
- [Enabling](#enabling)
- [The community catalog](#the-community-catalog)
- [Review before enabling](#review-before-enabling)

## Where plugins come from

- The plugin manager scans, in order: bundled (`<repo>/plugins/<name>/`), user
  (`~/.hermes/plugins/<name>/`), project (`.hermes/plugins/`, behind
  `HERMES_ENABLE_PROJECT_PLUGINS=1`) and pip entry points
  (`website/docs/user-guide/features/built-in-plugins.md`).
- Bundled examples: `disk-cleanup` (ephemeral file cleanup on session end) and
  `security-guidance` (pattern-matches dangerous code on write/patch)
  (`website/docs/user-guide/features/built-in-plugins.md`).
- General plugin system: `website/docs/user-guide/features/plugins.md`; how to
  build one: `website/docs/developer-guide/plugins/index.md`.

## Enabling

- Bundled plugins ship disabled and load only after `hermes plugins enable
  <name>` or an entry under `plugins.enabled` in config
  (`website/docs/user-guide/features/built-in-plugins.md`).
- `hermes plugins disable <name>` turns one off
  (`website/docs/user-guide/features/built-in-plugins.md`).
- Squad manifests declare `plugins: {enable: [...], disable: [...]}`;
  `squadctl apply` enables bundled plugins and installs community ones only
  when the user confirmed (`scripts/squadctl.py`; `squads/_schema/squad.schema.json`).

## The community catalog

- `plugin-catalog/` in the Hermes tree holds community catalog entries; the
  manifest declares `name`, `tier: official | community`, description and
  disclosure lines (`plugin-catalog/README.md`).
- Presence in the catalog directory is the trust signal, not an endorsement;
  download pinning and disclosure rules are in `plugin-catalog/README.md`.
- The desktop `catalog` toolset searches the catalog and installs through an
  approval card (`website/docs/reference/toolsets-reference.md`).

## Review before enabling

- Community plugins and hub skills: run `hermes skills inspect` / read the
  catalog entry, quote its disclosure and licence to the user, and get an
  explicit OK (`plugin-catalog/README.md`; `docs/decisions.md` C-02).
- A plugin runs with the bot's permissions; enable it only on the bot that
  needs it (example: `security-guidance` only where code is written,
  `website/docs/user-guide/features/built-in-plugins.md`).
- Plugins can add hooks and tools; see `references/hooks.md`.
