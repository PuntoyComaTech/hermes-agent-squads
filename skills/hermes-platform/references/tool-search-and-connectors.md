# Tool search and connectors

## Tool search

- Tool search replaces deferred tools in the prompt with bridge tools
  (`tool_search`, `tool_describe`, `tool_call`); `tool_describe` loads each
  schema on demand
  (`website/docs/user-guide/features/tool-search.md`).
- MCP and non-core plugin tools are deferred automatically. Core built-ins stay
  loaded; cold built-ins are deferred only when listed in
  `tools.tool_search.defer`, whose shipped default covers a few (for example
  `computer_use`, `session_search`). An explicit list replaces the default;
  `defer: []` keeps every tool eager
  (`website/docs/user-guide/features/tool-search.md`).

## Connectors

- Connectors are app accounts Hermes reaches through the Nous tool gateway:
  `hermes connectors list|accounts|connect|rename|disconnect`
  (`website/docs/reference/cli-commands.md#hermes-connectors`).
- Connector tools are served through the tool-search bridge;
  `tools.connectors.enabled` (default true) turns them on or off for a profile
  (`website/docs/user-guide/features/tool-search.md`, "Connectors (remote
  tools)"). Architecture: `website/docs/user-guide/features/tool-gateway.md`.

## Squad usage

- Squad manifests declare `connectors: {enabled: false, suggest: [...]}`; the
  suggest list is a note in the apply output, and the user connects apps with
  `hermes connectors connect <app>` (`scripts/squadctl.py`;
  `squads/_schema/squad.schema.json`).
- Connector placement: `approvals-and-security.md` -> External content.
