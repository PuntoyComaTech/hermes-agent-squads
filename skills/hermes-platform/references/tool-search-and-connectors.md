# Tool search and connectors

## Tool search

- Tool search replaces deferred tools in the prompt with bridge tools (`tool_search`, `tool_describe`,
  `tool_call`); `tool_describe` loads each schema on demand.
- MCP and non-core plugin tools are deferred automatically. Core built-ins stay loaded; cold built-ins
  are deferred only when listed in `tools.tool_search.defer`. The shipped default defers
  `computer_use`, `session_search`, `image_generate`, `todo_list`, `process_manage`, `cronjob_manage`,
  `browser_vault` and the Desktop GUI tools. An explicit list replaces the default; `defer: []` keeps
  every tool eager.
- The bridge sees only the session's granted toolsets: a subagent, kanban worker or gateway session
  restricted to a subset cannot discover or call a deferred tool outside it. Give the bot the toolset;
  tool search never widens it.
- A `tool_call` batch takes up to 10 entries; each runs under its real tool name, so hooks and
  approvals see the underlying tool.
- Tuning: `tools.tool_search.enabled` (`on`, `auto` = on, `off`), `threshold_pct`,
  `search_default_limit`, `max_search_limit`.

## Tool names

- Renamed tools: `todo` -> `todo_list`, `cronjob` -> `cronjob_manage`, `process` -> `process_manage`.
  The old names still work as aliases; skills and SOULs use the new ones.
- Toolset names did not change: manifests keep `todo`, `cronjob` and `terminal` (which carries
  `process_manage`).

## Connectors

- Connectors are app accounts Hermes reaches through the Nous tool gateway:
  `hermes connectors list|accounts|connect|rename|disconnect`.
- Connector tools are served through the tool-search bridge; `tools.connectors.enabled` (default true)
  turns them on or off for a profile. A call is bounded at 30 seconds.
- Connectors need a Nous identity. With no Nous account, the first `manage_connections` action (or the
  Desktop Connectors page) creates a free guest identity; it does not change the model provider.
  `nous.guest: false` turns guest identities off. `hermes auth upgrade` signs the guest in to a full
  Nous account and keeps its connectors. `manage_connections` also installs and authorizes local MCP
  servers from the catalog; those never create a Nous identity.
- One app can hold several accounts, each named 1-32 characters (lowercase, digits, `-`); none is the
  default. With two or more active accounts, every tool of that connector takes `connector_alias`,
  required when every account is named. A missing or unknown alias fails and lists the valid names.
- Reconnecting keeps the old account as retired (disabled, folded away). Only the user removes an
  account (`hermes connectors disconnect <app> --alias <name>`); the agent cannot.
- A call that needs an unlinked account returns `CONNECTION_REQUIRED`; `manage_connections` returns a
  connect link per app (a card in the Desktop).

## Squad usage

- Squad manifests declare `connectors: {enabled: false, suggest: [...]}`; the suggest list is a note
  in the apply output, and the user connects apps with `hermes connectors connect <app>`.
- A bot that works with two accounts of one app (Gmail `home` and `work`) names in its SOUL which
  alias each kind of task uses.
- Connector placement: `approvals-and-security.md` -> External content.
