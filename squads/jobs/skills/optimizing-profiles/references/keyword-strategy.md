# Keyword strategy

The market file (`reports/market-YYYY-MM-DD.json`) counts what the scout read in recent postings. The writer uses it to
choose words, never to choose claims.

## Contents

- Reading the market file
- Where a term goes
- Terms the user does not hold
- Titles

## Reading the market file

Each term has `postings` (how many of the postings read use it), `share`, and when the project was checked,
`in_profile` (true when `profile.md` or `achievements.yaml` holds it) and sometimes `profile_part` (the part of a longer
term the user does hold). `postings_read` is the sample size: below 10 postings, treat the ranking as a hint.

## Where a term goes

| Term | Place |
|---|---|
| the target title and its common variants | headline (first 70 characters), a job title when true, About |
| a tool or method with `in_profile: true` | skills list (top three by share), About sentence, the experience bullet that proves it |
| a phrase the postings use for work the user did | the bullet's wording, keeping the achievement's facts |

Use a term where a person would say it. A term in more places than it is true is stuffing.

## Terms the user does not hold

`in_profile: false` is a gap. It is not written, not even as "familiar with". The audit lists the gaps in order of
`share` so planning-upskilling can use them. With `profile_part`, write only that part ("Power BI" for "Power BI
dashboards").

## Titles

`titles` counts the job titles in the sample. When the user's current title differs from the common one for the same
work, the audit proposes the headline wording, never a change to a real job title in Experience.
