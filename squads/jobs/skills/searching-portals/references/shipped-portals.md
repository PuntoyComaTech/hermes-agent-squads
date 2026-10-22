# Shipped portals

## Contents

- linkedin
- freehire
- computrabajo
- elempleo
- talent
- Endpoints (for maintainers)

## linkedin

- Source: LinkedIn's public guest listing endpoints. No login, no cookies. The CLI never logs in.
- Place: `-l` is required and is free text (`"Lima, Peru"`, `"Remote"`). The CLI also accepts `--jobage-minutes`; the
  wrapper maps only `--max-age-days` (as `--jobage`).
- Workplace: `--remote remote|hybrid|onsite`.
- Detail: a numeric id, a job-view URL on any linkedin.com host, or a `urn:li:jobPosting:` URN. `details.isActive` is
  `false` when the closed banner is on the page. Its absence is not proof the posting is open.
- Volume: 10 results per page. The CLI backs off on 429 and 5xx; the wrapper treats the final failure as
  inconclusive.
- Terms: LinkedIn's terms restrict automated access. Personal use, low volume, no bulk collection. Listings come only
  from this CLI; the signed-in browser reads posts, the user's own profile and Easy Apply (finding-jobs intake-safety).

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

## computrabajo

- Source: Computrabajo's Colombian public listing (`co.computrabajo.com`), one GET per page. python3, standard library
  only.
- Place: `-l` free text, appended to the address as `-en-<slug>` (`Bogotá, D.C.` becomes `bogota-dc`).
- Window: `--jobage N` maps to `?pubdate=N` (`1` is the last 24 hours). `--page N` maps to `&p=N`; page 2 was checked
  live and returns other rows.
- Workplace: the listing states no type, so `--remote` is not mapped.
- Detail: the offer URL under `/ofertas-de-trabajo/`. A bare `data-id` cannot reopen an offer (the id-only address
  answers 404), so `id` is the offer URL.
- Scope: a row whose link is not https on computrabajo.com (an employer, a `javascript:` href, a downgraded address) is
  dropped; the detail `id`/`url` fall back to the offer that was asked for.
- Limit: one page holds at most 100 rows; a larger `--limit` is clamped to 100, never refused.
- Rights: `co.computrabajo.com/robots.txt` disallows `/ofertas-de-trabajo/*<param>=` and account paths; the listing and
  offer pages read here are allowed.

## elempleo

- Source: elempleo's Colombian public listing (`www.elempleo.com`), one GET per search. python3, standard library only.
- Place: `-l` city, used as a path segment (`Bogotá` becomes `/bogota/`).
- Window: no `--jobage`. The board's date control and its recent sort are client-side (both were tried live and neither
  narrowed nor reordered the rows), so the wrapper applies its window to the parsed dates.
- Paging: no `--page`; a `--page` flag is refused with `BAD_ARG` instead of being ignored.
- Workplace: `--remote` comes from the card's own label (`- Hibrido`, `- Remoto`, `- Presencial`). A row that states
  none is kept.
- Detail: the offer URL under `/co/ofertas-trabajo/`; the numeric id alone answers 404, so `id` is the offer URL.
  `2026-9-4` is normalised to `2026-09-04`, and `jobLocationType: TELECOMMUTE` adds `work_mode: remote`.
- Scope and limit: as for computrabajo (https on elempleo.com only, at most 100 rows).
- `Empresa confidencial` is the board's label for a hidden employer and is kept as the company text.

## talent

- Source: talent.com's Colombian listing (`co.talent.com/jobs?k=&l=&date=N&radius=25`). python3, standard library only.
- Place: `-l` free text. `--country xx` picks the market subdomain (`co` by default, two letters).
- Window: `--jobage N` maps to `date=N`. There is no page flag: `p=2` returned no cards.
- Detail: `view?id=<numeric>`. `id` stays numeric so the offer reopens; the result `url` is the talent.com view page even
  when the page's JSON-LD carries the employer's own address, which is dropped.
- Stale offers keep their page but lose the JSON-LD `JobPosting`. Their visible heading and body are still read, with
  `details.structured_data: false`.
- The card's `<time datetime>` is the board's last-touched stamp, the closest thing this listing gives to a posted date;
  the detail page carries the true `datePosted`.
- Limit: at most 100 rows per page; a larger `--limit` is clamped.

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

computrabajo (parser in `scripts/computrabajo/cli.py`):

- `GET https://<market>.computrabajo.com/trabajo-de-<slug>[-en-<place>]?pubdate=N&p=N`: `<article class="box_offer">`
  cards keyed by `data-id`, title in `a.js-o-link`, company in `a.t_ellipsis`, place in `p.fs16 span.mr10`, age in
  `p.fc_aux`.
- The offer page carries one `schema.org JobPosting` JSON-LD block: `title`, `hiringOrganization.name`,
  `jobLocation.address`, `datePosted`, `baseSalary`, `description`.

elempleo (parser in `scripts/elempleo/cli.py`):

- `GET https://www.elempleo.com/<market>/ofertas-empleo[/<city>]/trabajo-<slug>`: `<div class="... result-item">`
  cards, title in `a.js-offer-title`, company in `.js-offer-company`, workplace label in `.js-work-modality`, age in
  `.js-offer-date`, and a `data-ga4-offerdata` JSON attribute for company, place and id. The last card is a client-side
  template (`{{title}}`) and is skipped.
- The offer page carries `JobPosting` JSON-LD; dates arrive as `2026-9-4`.

talent (parser in `scripts/talent/cli.py`):

- `GET https://<market>.talent.com/jobs?k=&l=&date=N&radius=25`: `<div data-new-id="<digits>">` cards, title in
  `.JobCard_title`, company in `.JobCard_company`, place in `.JobCard_location`, stamp in
  `<time class="JobCard_timeText" datetime>`.
- `GET https://<market>.talent.com/view?id=<digits>`: `JobPosting` JSON-LD, or a visible heading and body on a page
  whose JSON-LD is gone.
