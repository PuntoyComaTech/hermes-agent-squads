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
  (`website/docs/reference/mcp-config-reference.md`).

## Config shape

- MCP servers live in config under `mcp_servers` with per-server command, args,
  env and tool filters (`website/docs/reference/mcp-config-reference.md`).
- Squad tooling treats a server as applied when its name already exists in
  `mcp_servers` (`scripts/squadctl.py`).

## Using MCP well

- An MCP server adds tools to the bot that has it; give one only to the bot that
  needs it (`website/docs/guides/use-mcp-with-hermes.md`).
- MCP tools can be deferred behind tool search like built-in tools
  (`website/docs/user-guide/features/tool-search.md`).
- Community MCP servers run arbitrary code as the bot's user; treat them like
  plugins and review the source or disclosure first
  (`website/docs/user-guide/features/mcp.md`).
- Deeper material: `website/docs/user-guide/features/mcp.md` and
  `website/docs/developer-guide/middleware.md`.
