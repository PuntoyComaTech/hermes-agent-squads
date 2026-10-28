# Filter rules

## Contents

- How the gates run
- Gate 1: scam or closed
- Gate 2: eligibility
- Gate 3: language
- Gate 4: geography, work mode and timezone
- Gate 5: role
- Gate 6: seniority
- Gate 7: contract and salary
- Gate 8: avoid lists and deal breakers
- Mass postings
- Language wording to CEFR
- Labels

## How the gates run

Eight gates run in this order. The first DISCARD wins and the later gates do not run. A FLAG never stops the
run. Each gate writes one verdict (PASS, FLAG or DISCARD) and, for FLAG or DISCARD, one short reason that quotes
the posting's own words. The overall `filter` is DISCARD if any gate discarded, else FLAG if any gate flagged, else
PASS. The reasons go to `filter_reasons`, one per gate that spoke.

A missing fact is `unknown`, never a guess. Never soften a requirement so an opening passes.

A pasted opening, or a card that says `force`, still runs every gate and shows every reason. Its `filter` keeps the
real value, and the analysis card is filed anyway.

## Gate 1: scam or closed

DISCARD with label `scam` or `closed` when:

- the posting asks for a payment, a fee, bank details, or an ID or passport scan before any interview;
- the posting names no identifiable employer: no legal name, no site, no way to check it;
- the only contact route is a private chat app and the posting asks for money or documents;
- the page says the position is closed, filled, or no longer accepting applications;
- the canonical URL returns 404 or 410, or redirects to a different listing;
- the deadline printed in the posting is before today. Never infer a deadline.

A page whose title does not match the expected role is a failed fetch, not a closed posting. Route it through the
escalation order in `intake-safety.md`.

Quote what the posting asks for. Never call an employer a fraud in a file or a message; the user decides.

## Gate 2: eligibility

Read the posting's eligibility, work-rights or "who can apply" wording verbatim. Compare it with the profile's
`eligibility` row for the country the role is in (`citizen`, `resident`, `permit`, `needs_sponsorship`).

| Posting wording | Verdict |
|---|---|
| Citizenship required, and the row is `resident`, `permit` or `needs_sponsorship` | DISCARD, quote |
| Permanent residence required, and the row is `permit` or `needs_sponsorship` | DISCARD, quote |
| Permanent residence required, and the row is `citizen` or `resident` | PASS |
| Security clearance, and the row is not `citizen` | DISCARD, quote |
| Security clearance, and the row is `citizen` | FLAG, label `eligibility_unverified`: the scheme must be checked |
| Names the candidate's permit class, or "international applicants welcome", "we sponsor", "visa holders considered" | PASS, note the positive |
| Company-wide welcome plus a named list of programmes, and this role is not on the list | FLAG, label `eligibility_unverified` |
| Residence wording ("must reside in", "must live in a US time zone", "US-based candidates only"), and the candidate is not based there | DISCARD, quote; FLAG with `plans_to_relocate: true` |
| Sponsorship refusal with no country named, and the candidate holds the right to work in some country | PASS, note it does not restrict the candidate |
| Visa-support refusal ("unable to support visas", "visa support is not provided"), and the row is `needs_sponsorship` | DISCARD, quote |
| Silent on citizenship and residency | PASS, label `eligibility_unverified` |
| Silent, and the posting places the role in a country the candidate needs sponsorship for | FLAG, label `eligibility_unverified` |
| Citizenship or residency wording, and the profile has no row for that country | FLAG, label `eligibility_unverified` |

Silence is not permission. Graduate programmes, government, defence, banking, telecoms and critical infrastructure
often gate eligibility on their own website. The label stays until someone checks the employer's international page.

## Gate 3: language

Only languages the posting requires as a condition of the job count. The language the ad is written in does not
count by itself (see the last row of the table).

Declared level: the CEFR level in `achievements.yaml -> languages`. A language with no row there is `undeclared`.
Thresholds: `languages_policy.flag_gap_steps` (default 1) and `languages_policy.discard_gap_steps` (default 2).
Gap = posting CEFR minus declared CEFR, in steps.

| Situation | Verdict |
|---|---|
| Required language is `undeclared` | DISCARD, quote the requirement |
| Gap is at least `discard_gap_steps` | DISCARD, quote the requirement and the declared level |
| Gap is at least `flag_gap_steps` | FLAG, quote both; the user judges |
| Required level at or below the declared level | PASS |
| Language required, no level stated in the posting | FLAG, label `language_not_stated` |
| Posting written in a language the user has `undeclared`, no requirement stated | FLAG, label `language_not_stated`, reason "interview probably in <language>" |
| Posting written in a declared language, no requirement stated | PASS |

Read meaning, not keywords: a synonym, a paraphrase or a plain implication settles a gate (Latin America holds
Colombia; "remote, hybrid or in-office" offers remote). FLAG only when two readings stay plausible after reading the
whole posting and `profile.md`; the user is the tiebreaker for those, never for what the profile already answers.

## Gate 4: geography, work mode and timezone

Compare the posting's work mode with `work_mode` and `cities` in the profile.

- A role that offers remote work as an option (remote-first with offices, "remote or hybrid", an optional office) is
  remote: judge it by its remote scope below, never as onsite or hybrid.
- Onsite or hybrid in a city outside `cities`, with no relocation stated as acceptable: DISCARD, quote the place.
- Remote restricted to countries that exclude `market.country`: DISCARD, quote the restriction. Record every
  country the posting hires in as `hiring_countries` (ISO codes, primary first), body included: the analysis gates
  read that list, and a region alone (`remote_region:eu`) hides a list that names the user's country or misses it.
- Remote restricted to a country the candidate needs sponsorship for: DISCARD, quote. The candidate's CV market does
  not change this.
- Remote in a named region the scout cannot map to the candidate's country: FLAG. Never guess a region's membership.
- Hybrid or onsite in one of `cities`, or remote without restriction: PASS.
- A time-zone requirement with both offsets known and a difference above `timezone_max_diff_h`: DISCARD. A time zone
  that cannot be checked: FLAG, label `timezone_unknown`.

## Gate 5: role

Match the function of the work, not the literal title or its rank. Compare with `target_roles` and
`acceptable_roles`: "Senior", "Lead", "Staff" or "Principal" in a title does not change the function.

- The main function sits outside both lists: DISCARD, quote the title and the first responsibility line.
- The function is adjacent (most tools shared, a different domain): FLAG, name the adjacency.
- Inside `target_roles`: PASS.

## Gate 6: seniority

Compare the years the posting states (never inferred from a title) with the candidate's years, computed from the
dated experiences in `achievements.yaml` (overlaps counted once; `score_analysis.py years --project P` prints them).

- Generic years ("N years of software, engineering or development experience"): compare with the total years.
- Years in a role ("N years as tech lead", "N years of management"): compare with the total years by default
  (`seniority_basis: total`: most markets ask for years of the profession, not of a rank). With
  `seniority_basis: role`, compare with the time in titles that hold that role word.
- Years in a skill or domain ("3 years of Kubernetes", "5+ years of experience with React"): not a seniority question.
  A soft note, no discard.
- Required years at or below the candidate's years: PASS.
- Short by at most `seniority_margin` (default 1, because employers usually stretch about a year): PASS with a soft
  note, quote the requirement. Never a discard.
- Short by more than `seniority_margin`: DISCARD, quote the requirement and both figures.
- Not stated: PASS. A title such as "Lead" alone is not a years requirement.

`profile.md` `years_experience` is a fallback used only when no experience has dates. It is an optional override,
not the source of truth: `years_experience.in_role` is never compared with a posting.

## Gate 7: contract and salary

Only when the posting states them. An unstated value never discards.

- Contract type stated and not in `contract`: DISCARD, quote.
- Salary stated in the same currency, period and type as `min_salary`, and below it: DISCARD, quote the figure.
- Salary stated in another currency, period or type: no comparison and no discard. Reason: "not comparable with
  min_salary".
- Not stated: label `salary_missing` or `contract_missing`. The verdict is unchanged.

## Gate 8: avoid lists and deal breakers

- Company in `avoid_companies` (case-insensitive name match) or a sector in `avoid_sectors` that the posting states:
  DISCARD.
- A phrase in `deal_breakers` found in the posting, with reviewed paraphrases ("guardias todos los fines de semana"
  matches "guardias rotativas los fines de semana"): DISCARD, quote the phrase. A negated wish ("no on-call") matches
  only a positive mention of what it negates.
- An avoided sector matches each of its words or a reviewed synonym ("crypto betting / gambling" matches "online
  gambling"): DISCARD, quote the term.

## Mass postings

The same text, or the same requisition id, posted in several cities by one company is one opening, not several.

- Keep one folder: the copy whose city is in `cities`, else the first copy found. Its gates run on that copy.
- The search file row lists the spread once: "posted identically in 6 cities (Lima, Arequipa, ...)".
- Label `mass_posting`. It is a caution, never a gate: it does not change the verdict or the fit. Companies do hire
  the same role in several cities.

## Language wording to CEFR

| Wording in the posting | Assumed CEFR |
|---|---|
| native, bilingual, native speaker | C2 |
| fluent, advanced, proficient | C1 |
| upper-intermediate, business, professional working proficiency, "daily meetings with clients" | B2 |
| intermediate, conversational, "reading documentation" | B1 |
| basic, elementary, "nice to have" | A2 |
| a CEFR code written out (A1 to C2) | that code |

Write the normalized value into `opening.md` as `required_language`, for example `{english: B2}`, or `unknown`.

## Labels

Short snake_case tags that travel to the analysis: `unverified_link` (from `link_check.py`, see intake-safety.md),
`language_not_stated`, `eligibility_unverified`, `mass_posting`,
`possible_repost`, `salary_missing`, `contract_missing`, `timezone_unknown`, `scam`, `closed`. Add a label only when
the posting visibly shows what the label names.
