# freehire-cli

CLI for the freehire.me job aggregator's public JSON API: technology roles across many markets.
Used by `scripts/portals.py` through `portal.json`; it also runs on its own.

- Data source: `/api/v1/agent/jobs/search` (full descriptions; the agent endpoint reads every body, so it is opt-in),
  `/api/v1/jobs/search` (`--no-description`, the wrapper's default, which carries no description),
  `/api/v1/jobs/{slug}`. Reads are public; no key is used.
- Dependencies: none. `bun` runs it directly.
- Base URL: `FREEHIRE_API_URL` (default `https://freehire.me`) points it at a self-hosted instance.
- freehire.me is a best-effort service without an SLA. An unreachable API exits 1 with a clear error.

```bash
bun run src/cli.ts search -q "backend engineer" --seniority senior --limit 10 --format table
bun run src/cli.ts search -q "golang OR rust" --remote remote --country PE,US --format table
bun run src/cli.ts detail golang-acme-2bxu6dxm --format plain
```

Place filters are facets: `--region`, `--country`, `--city` (comma = OR). Locations are not free text.
Tests: `bun test --timeout 30000`, offline (loopback servers and stubbed fetch).
