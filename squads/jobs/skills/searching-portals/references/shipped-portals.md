# Shipped portals

## linkedin

- Source: LinkedIn's public guest listing endpoints. No login, no cookies. The CLI never logs in.
- Place: `-l` is required and is free text (`"Lima, Peru"`, `"Remote"`). The CLI also accepts `--jobage-minutes`; the
  wrapper maps only `--max-age-days` (as `--jobage`).
- Workplace: `--remote remote|hybrid|onsite`.
- Detail: a numeric id, a job-view URL on any linkedin.com host, or a `urn:li:jobPosting:` URN. `details.isActive` is
  `false` when the closed banner is on the page. Its absence is not proof the posting is open.
- Volume: 10 results per page. The CLI backs off on 429 and 5xx; the wrapper treats the final failure as
  inconclusive.
- Terms: LinkedIn's terms restrict automated access. Personal use, low volume, no bulk collection. The squad browser
  blocklist keeps linkedin.com, so no agent browses it.

## freehire

- Source: freehire.me public JSON API. No key. Best-effort service with no SLA. `FREEHIRE_API_URL` points the CLI at a
  self-hosted instance.
- Place: facets only, not free text. `--region` (global, eu, uk, north_america, latam, apac, mena, africa, cis, none),
  `--country` (ISO-3166 alpha-2), `--city`. Pass them after `--` with `--portal freehire`.
- A region outside the vocabulary (`us` is a country) prints a warning on stderr and still exits 0. Check the warning.
- Missing geography means unresolved, not "not applicable". `--region none` finds jobs with no resolved region.
- Search: the wrapper adds `--no-description` by default, so search rows carry no description. Use `detail` for one
  body, within a budget of 5 per search card.
- Scope: technology roles. Coverage of other roles is partial.
- Result `url`: the employer's own apply page, so `url_hosts` is `[]`. `id` is the freehire slug.
- Detail: a slug or `https://freehire.me/jobs/<slug>`. Closed postings are still served, but the CLI does not expose the
  closed timestamp, so a freehire row cannot be checked for closed status yet.

## Endpoints (for maintainers)

linkedin (parsers in `scripts/linkedin/src/helpers.ts`):

- `GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`: `keywords`, `location`, `f_TPR`
  (seconds window, e.g. `r1209600` for 14 days), `f_WT` (1 onsite, 2 remote, 3 hybrid), `start` (10 per page). Returns
  `<li>` cards keyed by `data-entity-urn="urn:li:jobPosting:<id>"`.
- `GET https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/<id>`: title `top-card-layout__title`, company
  `topcard__org-name-link`, place `topcard__flavor--bullet`, description `show-more-less-html__markup`, criteria
  `description__job-criteria-subheader` and `description__job-criteria-text`. Closed banner `closed-job__flavor`.

freehire (client in `scripts/freehire/src/helpers.ts`, commands in `scripts/freehire/src/commands/`):

- `GET {FREEHIRE_API_URL or https://freehire.me}/api/v1/agent/jobs/search`: full descriptions; `/api/v1/jobs/search` is
  the lean variant used by `--no-description`.
- `GET /api/v1/jobs/{slug}`: one posting, HTML description stripped client-side.
- Envelope `{data, meta, error}`. Query parameters used: `q`, `limit`, `offset`, `posted_within_days`, `regions`,
  `countries`, `cities`, `seniority`, `category`, `skills`, `company_slug`, `work_mode`, `description_format`.
- `GET /api/v1/jobs/facets` is the controlled vocabulary with counts. The CLI does not call it; check it before
  guessing a facet value.
