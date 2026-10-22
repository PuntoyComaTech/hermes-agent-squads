# Profile keys

The keys the personalisation interview fills. Existing keys (search, keywords, cities and so on) keep their meaning in
`jobs-contract/references/profile-files.md`. Defaults apply when a key is absent.

## Contents

- candidate
- market and eligibility
- languages
- scoring, deal breakers and preferences
- writing style and search settings
- Language gate rules

## candidate

| Key | Values | Default | Note |
|---|---|---|---|
| stage | first_job, junior, mid, senior, lead, career_change, returning | none (required) | drives the playbook |
| situation | employed, unemployed, student, freelance | employed | |
| age | integer or null | null | optional; never inferred; printed only when include_age_in_cv |
| include_age_in_cv | true or false | false | |
| photo_in_cv | true or false | false | follows the market row |

## market and eligibility

```yaml
market:
  country: PE                      # ISO-3166 alpha-2 of the target market
  cv_page_limit: 2                 # 1 or 2
  conventions: {photo: false, age: false, marital_status: false, references_line: false}
eligibility:                       # one row per country applied in
  - {country: "PE", status: citizen}     # citizen | resident | permit | needs_sponsorship
  - {country: "US", status: needs_sponsorship, notes: ""}
```

Quote every country code: unquoted `NO` (Norway) reads as false.

A gate reads `eligibility` against the posting's wording. Silence in the posting keeps the opening, with the
`eligibility_unverified` label. A status the user did not give is never assumed.

## languages

Levels live in `achievements.yaml` under `languages`, one entry per language, on the CEFR scale (A1 to C2):

```yaml
languages:
  - {language: english, level: B2, verified: true}
languages_policy: {flag_gap_steps: 1, discard_gap_steps: 2}
```

Honesty note to give the user once: a declared level is a self-assessment until a test or real work confirms it. Pick
the level you can show. A posting asking for a level above yours is flagged for your own judgment, not hidden.

## scoring, deal breakers and preferences

| Key | Default | Note |
|---|---|---|
| scoring.weights | technical 30, experience 25, behavioral 15, career 30 | must sum to 100; location is pass or fail, never weighted |
| scoring.bands | strong 75, good 60, moderate 45, weak 30 | below weak is poor |
| deal_breakers | [] | duties or conditions the user refuses, matched against the opening; a work mode goes in work_mode |
| career_goals | [] | |
| energizers | [] | tasks that give energy |
| drains | [] | tasks that drain energy |
| behavioral | {thrives_in: [], avoid: [], work_style: ""} | |
| salary_data | null | path to a user-supplied benchmark file |

## writing style and search settings

| Key | Default | Note |
|---|---|---|
| writing_style | {tone: warm_direct, formality: medium, avoid_phrases: []} | used by writing-applications and tracking-outcomes drafts |
| follow_up_days | 10 | quiet days before a follow-up draft is offered |
| stale_days | 60 | quiet days before a submitted row is listed as stale |
| apply_threshold | 70 | minimum fit score for a writer card |
| max_analyses_per_day | 5 | deep analyses a day, freshest first; the rest wait for the next check or "analyze <id>" |
| user_language | required | ISO 639-1 (es, en, pt). Every message to the user is in it; documents follow the posting's language |
| timezone | required | IANA zone (America/Lima). The check times and "today" use it |
| search_times | ["12:00"] | 1 to 4 local check times on weekdays; each check reads only postings since the previous one |
| auto_apply | required | never (no submit; kit only), ask (submit after the user approves the screenshot), try (submit after the user's apply for that opening) |
| apply_consent | per_opening | fixed: each submit needs the user's apply for that opening; there is no standing permission |
| review_before_submit | false | true makes every submit wait for the screenshot approval; required by ask |

Onboarding asks, in this order and in one batch: user_language, timezone, then the three consent values in one plain
sentence each (never, ask, try), then deal breakers. The answer to auto_apply is written as given, never inferred.

## Language gate rules

Applied by the scout before scoring, first DISCARD wins:

- A language the posting requires that is not declared at all: DISCARD.
- A declared level below the required one by `discard_gap_steps` or more: DISCARD.
- Below by `flag_gap_steps` only: FLAG.
- The posting names no level: FLAG.
- A required level at or below the declared one: PASS.
