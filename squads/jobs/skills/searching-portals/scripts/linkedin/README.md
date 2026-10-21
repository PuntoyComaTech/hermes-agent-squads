# linkedin-cli

CLI for searching LinkedIn's public job listings (guest endpoints) for any country or region, plus remote.
Used by `scripts/portals.py` through `portal.json`; it also runs on its own.

- Data source: `seeMoreJobPostings/search` and `jobPosting/<id>` on www.linkedin.com (no login, no cookies).
- Dependencies: none. `bun` runs it directly; `bun install` is not needed.
- Personal use only. LinkedIn's Terms of Service restrict automated access. Keep volume low.

```bash
bun run src/cli.ts search -q "data analyst" -l "Lima, Peru" --jobage 14 --format table
bun run src/cli.ts detail 4000000003 --format plain
```

Commands: `search` (`--location` required; `--query`, `--jobage` or `--jobage-minutes`, `--remote`,
`--page`, `--limit`, `--format json|table|plain`) and `detail <id|url>` (`--format json|plain`).
Errors go to stderr as `{"error","code"}` with exit 1. Tests: `bun test --timeout 30000`, offline.
