# Portal contract

Every portal is a directory `scripts/<name>/` holding `portal.json` and a CLI. `portals.py` reads only the manifest
and the CLI's JSON output.

## portal.json

| Key | Type | Meaning |
|---|---|---|
| name | string | Equals the directory name. Lowercase letters, digits, dashes. |
| description | string | One line shown by `list`. |
| hosts | string list | Hosts the portal serves. A detail URL on one of them routes here. |
| url_hosts | string list | Hosts a result `url` must sit on. `[]` accepts any http(s) address (aggregators link to employers). |
| enabled | bool | Included in default searches and health checks. A named `--portal` always runs. |
| markets | string list | ISO country codes or `global`. Informational. |
| cmd | string list | Argument vector. `{dir}` is the portal directory, `{python}` the interpreter. A leading `bun` resolves through `BUN`, then PATH, then `~/.bun/bin/bun`. |
| search_flags | object | Maps search keys to CLI flags. Keys: query, location, jobage, limit, page, remote, format (format is required). Only mapped keys are sent. |
| search_defaults | string list | Extra flags sent with every search, e.g. `["--no-description"]`. |
| required_search | string list | Keys every search must carry. A default search without one is skipped with `MISSING_ARG`. |
| example_query | string | A query known to return results today. Used by health. |
| example_location | string | Required when `location` is required. Used by health. |
| retry_query | string | A common word used once when `example_query` returns nothing. Default `manager`. |

A manifest that fails validation is listed under `problems` in `list` and `health`. It is never searched and never
skipped silently.

## CLI contract

- `search` with the flags the manifest maps, plus `--format json`. Stdout: `{"meta": {...}, "results": [...]}`.
- `detail <id|url> --format json`. Stdout: one JSON object with at least the result keys.
- Errors: one JSON object on stderr, `{"error": "...", "code": "..."}`, exit 1, nothing on stdout.
- Output carries no credentials and no contact details.

## Result shape

`{id, title, company, location, date, url, portal}` plus `work_mode` when the board gives one. `date` is YYYY-MM-DD or
null. Missing text is null, never "". `id` is kept because `detail` needs it and some result URLs point at employers.

`detail` adds `description` (readable text) and `details`, the rest of the CLI's object, e.g. LinkedIn's `isActive`.

## Search rules

- Window: rows dated more than `--max-age-days` (default 14) before `--today` are dropped and counted in
  `meta.portals[].dropped_older`. Rows with no date are kept and counted in `undated`.
- Limit: `--limit` (default 20) caps each portal's rows. Order: newest first, undated last.
- Work mode: `--remote remote|hybrid|onsite` is applied by the wrapper to the `work_mode` each row states. The portal's
  own label wins; without one, the title and place are read, then the description. A row whose type is not stated
  is kept with `work_mode_unconfirmed: true` and counted in `meta.portals[].unconfirmed_work_mode` (the rows are
  kept, not dropped); a row of another type is dropped and counted in `dropped_work_mode`.
- Per portal counts: `asked` (the limit), `returned` (what the CLI sent), `count` (kept), `shortfall` (`asked - count`).
- Blocklist: `JOBS_BLOCKLIST` refuses a portal (`BLOCKED`); see the SKILL.
- Flags: `-q`, `-l`, `--remote`, `--page` go only to portals that map them. On a default search an unmapped key skips
  that portal (`UNSUPPORTED_FLAG`, listed in `meta.skipped`); on a named `--portal` it fails.
- Passthrough: arguments after `--` go to every selected CLI, search only. Name one `--portal` when using its facets.
- Exit: 0 when every selected portal answered; 1 when any failed (`meta.failed`), with the good rows still printed.

## Error codes

| Code | Meaning |
|---|---|
| BAD_ARG | A value is empty or malformed, or a number is out of range. Nothing ran. |
| BAD_PORTAL | A manifest failed validation. |
| UNKNOWN_PORTAL | No installed portal has that name. |
| UNSUPPORTED_FLAG | The portal does not map a requested key. |
| MISSING_ARG | A key the portal requires was not given. |
| BUN_MISSING | bun is not installed, or `BUN` points at nothing. |
| CLI_MISSING | The manifest's command does not exist. |
| TIMEOUT | The CLI did not answer within 120 seconds. |
| BAD_OUTPUT | The CLI printed something other than the contract JSON. |
| BAD_ID | A detail target is not an id or URL on an installed portal's host. |
| BLOCKED | The portal's host is on `JOBS_BLOCKLIST`. Nothing ran. |
| NO_PORTALS | Nothing is enabled, or nothing accepts the request. |
| other | A CLI's own code, passed through from its stderr JSON. |
