# MCP

## Adding servers

- `hermes mcp add <name> --command <cmd> --args ...` for stdio servers (`--args` must be the last
  option) or `--url <https://...>` for HTTP/SSE; `--auth {oauth,header}`, `--preset`,
  `--env KEY=VALUE` and `--connect-timeout` refine it.
- Manage servers with `hermes mcp list`, `remove`, `test`, `configure <name>` (pick its tools) and
  `picker`.
- OAuth servers: `hermes mcp login <name>` (`reauth [--all]` renews). The approving browser must run on
  the Hermes machine, so the user completes the login once in a terminal before a headless bot uses it.
- The catalog (`hermes mcp catalog`, `hermes mcp install <name>`) holds Nous-reviewed entries; there
  is no community submission tier. An install runs what the entry's manifest specifies (for example a
  git clone): read it first.
- Squad manifests declare `mcp: {<name>: {command, args}}` or `{url}`; `squadctl apply` runs
  `hermes mcp add` per server and treats a server as applied when its name is enabled in
  `mcp_servers`; a failed probe stays pending.

## Config and use

- Servers live under `mcp_servers.<name>` with `command`, `args`, `env` or `url`, `headers`.
- `enabled: false` skips a server. `tools.include` / `tools.exclude` take exact names or
  case-sensitive globs; `include` wins when both are set. Give each bot only the tools it needs.
- `${VAR}` in `command`, `args`, `url` and `headers` resolves at connect time from the environment
  (including the profile's `.env`), keeping secret values out of `config.yaml`.
- Sampling is on by default: a server may request LLM completions through Hermes (`sampling.enabled`,
  `max_rpm` 10, `max_tokens_cap` 4096). Set `sampling.enabled: false` on servers that do not need it.
- Per-server `timeout`, `connect_timeout`, `idle_timeout_seconds` (recycles a stdio server) and
  `supports_parallel_tool_calls` (default sequential).
- MCP children get only safe system vars plus the server's own `env`; terminal passthrough does not
  apply.
- A server adds tools to the bot that has it; give one only to the bot that needs it. Deferral:
  `tool-search-and-connectors.md` -> Tool search.
- A running gateway drops removed or disabled servers within about a minute; a CLI session reloads
  with `/reload-mcp`.
