# LinkedIn profile

Field rules the audit and the checker use. LinkedIn does not publish its ranking; the limits below are what the editor
enforces today, and the weights are what public guides report, so treat the weights as direction, not as promises.

## Contents

- How search reads a profile
- Fields and limits
- Headline
- About
- Experience
- Skills
- Other fields and settings

## How search reads a profile

Recruiters search two ways: a title field (current and past job titles) and a keywords field (the whole profile). A word
that is not on the profile cannot match. Keywords placed in the headline, a job title and the top skills count most;
repeating a term naturally across them helps, repeating it in a list does not. Completeness and recent activity are
inputs; both are the user's to act on.

## Fields and limits

| Field | Limit | Notes |
|---|---|---|
| Headline | 220 characters | about the first 70 show in search and on mobile |
| About | 2,600 characters | about the first 200 to 300 show before "see more" |
| Experience title | 100 | an actual title, not a slogan |
| Experience description | 2,000 | per role |
| Skill | 80 each, 100 in all | the top 3 are pinned |
| Custom URL | 3 to 100 | no digit runs: a default hash or a birth year |

## Headline

Role first, then specialty, then proof: `Data analyst | SQL, Python, Power BI | cut weekly reporting from 6 h to 20 min`.
Put the target role (from `target_roles`) in the first 70 characters. Do not leave the default "<title> at <company>".
The proof is an achievement with its number, cited by id.

## About

First person, short paragraphs, line breaks (most views are on mobile). Order: a hook that earns "see more" (who you
help and with what), proof (two or three achievements with numbers), the tools and methods in plain sentences (the
market's `in_profile` terms), and one line on what you want next. No "passionate", no "results-oriented".

## Experience

Each role: a scope sentence, then three to six bullets, each an action verb, the object and the result, cited by
achievement id. The job title is the real title; the target role appears in bullets only where it is true. Link
`public_evidence` pieces as attachments or Featured items.

## Skills

Twenty to thirty targeted skills, each one the user holds (`key_skills`, achievement skills and tags). Pin the first
three in this order: the target role's core skill, the strongest differentiator, the market's most asked skill that the
user holds. Order the rest by how many market postings ask for them.

## Other fields and settings

Photo, banner and Featured are advice only. Open to Work: public frame or recruiters-only; the user chooses and the
audit states both. A secondary-language profile is a separate copy in that language, drafted when
`application_languages` lists more than one.
