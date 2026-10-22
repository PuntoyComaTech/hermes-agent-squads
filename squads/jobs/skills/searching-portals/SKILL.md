---
name: searching-portals
description: "Searches job portals and normalises the results. Use when a search card needs portal postings, one posting's detail, or a portal's health checked."
---

# Searching portals

`scripts/portals.py` runs every enabled portal CLI and returns one result shape for all of them. Each portal is a
directory under `scripts/` with a `portal.json` manifest and its own CLI, so a new board is a new directory, never an
edit to the script. Shipped: `linkedin` (public LinkedIn listings, needs a place) and `freehire` (freehire.me, technology
roles, place filters as facets).

## When to Use

- A search card needs postings from the last 14 days.
- One posting's full detail is needed, by portal id or by a URL on a portal's own host.
- A portal returns nothing, junk fields or errors, and someone needs a verdict on it.

## Procedure

1. Set the script path once: `P="$HERMES_HOME/skills/squad-jobs/searching-portals/scripts/portals.py"`.
2. List what is installed: `python3 "$P" list`. Report every entry in `problems`; a broken manifest is never searched.
3. Search every enabled portal:
   `python3 "$P" search -q "data analyst" -l "Lima, Peru" --max-age-hours 24 --limit 20` (the hours of the card's
   `Window:` line; a portal that takes minutes gets that exact window, others the whole days that cover it)
   - `-q` keywords, `-l` place text, `--remote remote|hybrid|onsite`, `--page N`, `--today YYYY-MM-DD` to pin the window.
   - One plain term per call: a role title or one skill (`data analyst`, then `BI analyst`). Never `OR`, quotes,
     `site:` or a combined string: boards read them as words and silently return another set. Run one call per term
     and per language of `search_keywords`, and dedupe across calls.
   - `linkedin` is skipped with `MISSING_ARG` when no `-l` is given; `freehire` is skipped with `UNSUPPORTED_FLAG` when
     `-l` is given. Both appear in `meta.skipped`. Use `--portal NAME` to make a skip a failure.
   - Portal facets go after `--` with `--portal NAME`, e.g. `-- --country PE --region eu`. Without `--portal` they reach
     every selected portal.
   - `--remote remote` is applied by this script to the workplace type each row states (the portal's label, else the
     title, place or description). A row of another type is dropped (`dropped_work_mode`); a row with no stated
     type is kept with `work_mode_unconfirmed: true` (`unconfirmed_work_mode` counts them) and the location
     gate decides from the posting body.
4. Read the exit code. 0: every selected portal answered. 1: at least one failed; `meta.failed` names it with its code,
   and the rows from the others are still printed. Report the failure; never present a partial list as the full one.
5. Check `meta.portals` per portal: `asked` is the limit, `returned` is what the portal sent, `count` is what was kept,
   and `shortfall` is `asked - count`. `dropped_older` counts rows outside the window; `dropped_work_mode` counts rows of
   another workplace type; `undated` counts rows kept with a null date. A null date is never guessed. Report any
   shortfall to the user as "asked N, got M" with the reason from these counts.
5b. Pre-filter before any detail: `python3 "$P" prefilter --profile <P>/profile.md --input <search.json> [--input ...]
   --project <P>`. It keeps rows whose title shares a word with `search_keywords`, `target_roles` or
   `acceptable_roles`, drops `avoid_companies`, the wrong `work_mode` and rows older than `search_days`, keeps the
   rows posted before `--since` (the card's window), keeps the newest `max_candidates_per_run` (default 60) and names at most `max_detail_calls` (default 15) `detail_targets`.
   `analysis_cap` gives this project's analysis cards filed today. It makes no network call.
6. Detail for a shortlisted posting:
   `python3 "$P" detail 4000000003 --portal linkedin` or `python3 "$P" detail https://freehire.me/jobs/<slug>`.
   A URL routes to the portal that owns its host. A URL on any other host is refused with `BAD_ID` before any fetch.
   LinkedIn detail carries `details.isActive`; `false` means the closed banner was shown.
7. Health when results look wrong (company empty everywhere, HTML in titles, zero results for a query that worked
   before): `python3 "$P" health --portal NAME [--detail]`. Verdict rules: `references/health-verdicts.md`.
8. Field meanings, error codes and each shipped portal's quirks: `references/portal-contract.md` and
   `references/shipped-portals.md`.

## Pitfalls

- A 429, a block page or an outage is `inconclusive`, never `broken`. Back off once, report it, do not loop.
- `detail` is one request per posting. Freehire search rows carry no description (the wrapper sends `--no-description`):
  score a candidate on title, company, location and `work_mode`, and run `detail` only on shortlisted rows, at most 5
  per search card.
- A company that is an identifier (a 16-plus hex string or a UUID) is returned as null, never as a name.
- A flag value that is empty or starts with `-` is refused with `BAD_ARG`, never read as "no filter".
- A null `date` stays null. Do not infer a posting date from relative text such as "3 days ago" or from result order.
- The portals need no credentials, and the script never reads `.env` files or prints contact details. Do not add a key flag.
- The squad browser never opens linkedin.com. The LinkedIn CLI reads LinkedIn's public guest listings only, never a
  logged-in page. Keep volume to a handful of searches per run.
- `JOBS_BLOCKLIST` (comma-separated hosts in the environment) refuses a portal: a default search lists it in
  `meta.skipped` with `BLOCKED`, a named `--portal` fails with `BLOCKED`, and `detail` refuses with `BLOCKED`. The
  built-in linkedin.com entry of the browser and fetch tools does not apply here: the portal CLI is the sanctioned
  reader of public LinkedIn listings. Policy in `finding-jobs/references/intake-safety.md`.
- Both CLIs run on bun. On `BUN_MISSING`, report that portal as not searched. The `BUN` variable sets an explicit path.
- Mass-posting consolidation and closed-at-source decisions belong to finding-jobs. This skill reports what the portals
  returned.

## Verification

- `python3 "$P" --help` exits 0. `list` shows each portal with its `enabled` value and an empty `problems` list.
- Every row in `results` carries `id, title, company, location, date, url, portal`; missing values are null, not "".
- Each `date` is YYYY-MM-DD and within `meta.max_age_days` of `meta.today`, or null.
- `meta.failed` and `meta.skipped` account for every portal the run was meant to search. The card summary says which
  were not searched and why.
- A detail's `url` sits on the portal's host, and its `description` is readable text without tags or entities.
