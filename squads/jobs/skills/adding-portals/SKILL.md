---
name: adding-portals
description: "Guides adding a job board as a portal skill. Use when a board is missing from the portal search and the user wants it searched."
---

# Adding portals

A portal is a directory `searching-portals/scripts/<name>/` with a `portal.json` manifest and a CLI that follows the
portal contract (`searching-portals/references/portal-contract.md`). `templates/portal-cli/` is a working starting point
with its own offline tests. The job: investigate the board, scaffold, prove it live, then decide `enabled`.

## When to Use

- The user names a job board that the search does not cover yet, usually a market board.
- A portal's CLI is broken for good and a new directory should replace it.

## Procedure

1. Interview the user for: a name (lowercase, dashes, equal to the directory), the home URL, the market as ISO codes,
   the posting language, and one realistic test query with a place.
2. Investigate with `references/investigation-checklist.md`, in order. Record each answer. At a stop condition, stop and
   tell the user: a disallowed robots.txt path, terms that forbid automated access, or a login wall. The user decides;
   a board that stops here is not scaffolded.
3. Scaffold: copy `templates/portal-cli/` to `searching-portals/scripts/<name>/`, then:
   - rename the package and the service's environment variable, and set the base URL in one place;
   - write `portal.json`: `name` equal to the directory; `hosts` (the board); `url_hosts` (the host results link to, or
     `[]` for aggregators that link to employers); `markets`; `search_flags` listing only flags the CLI really takes;
     `required_search`; `example_query` (a query that returns results today); `retry_query`; `enabled: false`;
   - replace the fetch and field mapping in `src/cli.ts` with the board's own. Keep the contract: `search` and `detail`,
     the JSON envelope, errors as `{"error","code"}` on stderr with exit 1, backoff on 429 and 5xx.
4. Test offline: `bun test --timeout 30000` inside the new directory. Fixtures are captured from the board, with the
   capture date in the fixture README. Never invent them.
5. Prove it live with a handful of requests: `bun run src/cli.ts search -q "<test query>" --limit 5 --format table`,
   then one `detail`. Read the rows yourself: titles and companies filled, URLs on the expected host, dates parsed.
6. Health: `python3 "$P" list` must show the portal with `problems` empty, then
   `python3 "$P" health --portal <name> --detail` gives the verdict. `P` is
   `$HERMES_HOME/skills/squad-jobs/searching-portals/scripts/portals.py`. Set `enabled: true` only on `healthy`.
   Otherwise leave it disabled and say why.
7. Report to the user: files created, live counts, the verdict, and the enabled state. Nothing else needs registering;
   `portals.py` discovers the directory.

## Pitfalls

- The board's host goes in `portal.json` and the CLI only. Never in a shared file or a skill description.
- A board with no JSON endpoint and unstable markup is a poor fit. A parser that half-works is worse than none.
- Credentials come only from an environment variable named for the service, never a flag. If it is unset, exit 1 with
  `MISSING_CREDENTIALS` naming the variable. Never print or store a token.
- Keep volume low: a few requests while testing, respect robots.txt, back off on 429.
- A board that fails the live test or the health check stays `enabled: false`. Do not enable it to be helpful.
- Do not add a parsing library to a zero-dependency CLI unless the markup defeats chunked parsing; say so in its README.

## Verification

- `portal.json` validates: `list` shows the portal and does not list it under `problems`.
- `bun test --timeout 30000` passes in the new directory.
- The live search returned at least one row with a title and a URL, and `detail` returned readable text.
- `health` returned a verdict, and `enabled` matches it: `true` only for `healthy`.
- The report to the user lists the files, the live counts, the verdict and the enabled state.
