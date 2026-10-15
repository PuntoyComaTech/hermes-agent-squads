# MCP

## Contents

- [Adding servers](#adding-servers)
- [Config shape](#config-shape)
- [Using MCP well](#using-mcp-well)

## Adding servers

- `hermes mcp add <name> --command <cmd> --args ...` for stdio servers or
  `--url <https://...>` for HTTP/SSE; `--auth {oauth,header}`, `--preset`,
  `--env KEY=VALUE` and `--connect-timeout` refine it
  (`hermes mcp add --help`).
- Squad manifests declare `mcp: {<name>: {command, args}}` or `{url}`;
  `squadctl apply` runs `hermes mcp add` per server
  (`squads/_schema/squad.schema.json`; `scripts/squadctl.py`).
- Manage existing servers with `hermes mcp list` and `hermes mcp remove`
  (`website/docs/reference/cli-commands.md#hermes-mcp`).

## Config shape

- MCP servers live in config under `mcp_servers` with per-server command, args,
  env and tool filters (`website/docs/reference/mcp-config-reference.md`).
- Squad tooling treats a server as applied when its name exists in
  `mcp_servers` and is enabled; a failed probe stays pending
  (`scripts/squadctl.py`).

## Using MCP well

- An MCP server adds tools to the bot that has it; give one only to the bot that
  needs it (`website/docs/guides/use-mcp-with-hermes.md`).
- MCP tools are deferred behind tool search automatically; built-in tools only
  when named in `tools.tool_search.defer`
  (`website/docs/user-guide/features/tool-search.md`).
- The picker installs Nous-reviewed catalog entries; there is no community
  submission tier (`website/docs/user-guide/features/mcp.md`).
- Full reference: `website/docs/user-guide/features/mcp.md`.
