# MCP

## Adding servers

- `hermes mcp add <name> --command <cmd> --args ...` for stdio servers (`--args`
  must be the last option) or `--url <https://...>` for HTTP/SSE; `--auth
  {oauth,header}`, `--preset`, `--env KEY=VALUE` and `--connect-timeout` refine
  it (`hermes mcp add --help`).
- Manage servers with `hermes mcp list`, `hermes mcp remove` and `hermes mcp
  test` (`website/docs/reference/cli-commands.md#hermes-mcp`).
- Squad manifests declare `mcp: {<name>: {command, args}}` or `{url}`;
  `squadctl apply` runs `hermes mcp add` per server and treats a server as
  applied when its name is enabled in `mcp_servers`; a failed probe stays
  pending (`squads/_schema/squad.schema.json`; `scripts/squadctl.py`).

## Config and use

- Servers live under `mcp_servers` with per-server command, args, env and tool
  filters (`website/docs/reference/mcp-config-reference.md`).
- MCP children get only safe system vars plus the server's own `env`; terminal
  passthrough does not apply (`website/docs/user-guide/security.md`, "MCP
  Credential Handling").
- A server adds tools to the bot that has it; give one only to the bot that
  needs it (`website/docs/guides/use-mcp-with-hermes.md`). Deferral:
  `tool-search-and-connectors.md` -> Tool search.
- The catalog (`hermes mcp catalog`, `hermes mcp install <name>`) holds
  Nous-reviewed entries; there is no community submission tier
  (`website/docs/user-guide/features/mcp.md`).
