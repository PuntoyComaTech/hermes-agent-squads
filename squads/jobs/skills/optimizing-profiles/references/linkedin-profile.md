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
- Education
- Languages
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
Put the strongest positioning title in the first 70 characters. Do not leave the default "<title> at <company>".
The proof is an achievement with its number, cited by id.

## Positioning titles

Companies name the same work many ways, and new names spread fast. The headline and About may use any title of a
role family the user is recognised in (`jobs_common.recognised_roles`: a title in `target_roles`,
`acceptable_roles` or `positioning_titles`, or enough of the family's signals in their own achievements), not only
the titles of their past jobs. The real job title of each experience entry never changes.

- Order by market pull: an `emerging` family the user is recognised in and wants goes first (`Forward Deployed
  Engineer · Technical Lead · AI Engineer`), then the seniority title, then the classic one.
- A positioning keyword appears in at least three places or it carries little weight: the headline, the first line
  of the About, the skills list (its skill form: "Forward Deployed Engineering"), and, where the work matches, a role's
  bullet or skills. Never a list of the same word.
- The title it grew out of keeps a place: "full stack" stays in the About's first line ("forward deployed engineer
  with a full-stack background"), in the skills ("Full-Stack Development") and in the roles that were full stack.
- Each positioning block cites the achievements that show the family's work (for FDE: an end-to-end delivery for a
  client, AI integrated into the client's product, MCP servers, agents or skills in production).

## About

First person, short paragraphs, line breaks (most views are on mobile). At most 1,500 characters: the first ~265 show
before "see more", and they must say who the user is and what they do. Order: who you are and for whom (the role and
the domain), two or three proofs in one line each, the core stack in one line. No career history (the Experience
section holds it), no closing pitch, no "passionate", no "results-oriented". Search reads keywords from the headline,
titles and skills more than from a long About, so length buys nothing.

## Experience

Each role: a scope sentence, then two to four one-line bullets, each an action verb, the object and the result, cited
by achievement id, at most 600 characters in all. Name sectors and scope, never a client, brand or internal project of
the current employer (`confidential_terms`, `keep_off_public_profile`), and no team size the user kept off the profile;
a client list ends in "among others". The job title is the real title; the target role appears in bullets only where it is true. Link
`public_evidence` pieces as attachments or Featured items.

## Skills

Twenty to thirty targeted skills, each one the user holds (`key_skills`, achievement skills and tags). Pin the first
three in this order: the target role's core skill, the strongest differentiator, the market's most asked skill that the
user holds. Order the rest by how many market postings ask for them.

Each role also shows up to five skills of its own (`role_skills`): the ones that role proves, so a recruiter filtering
by skill finds the role that used it. Top skills are the 3 to 5 LinkedIn pins on the About card, in order of
importance; every pin is also in `skills`, so the pins never name a skill the list drops.

## Education

Every school on the profile gets a description of at most 400 characters: what was studied in the market's words (a
bootcamp is "full-stack web development", a course list names the subjects that still matter), cited by its EDU id.
A degree name or date that differs from `achievements.yaml` goes to the audit as a `structure` row; the school's own
name is the entry and is never renamed.

## Languages

A profile has one primary language and optional secondary ones (the "Profile language" card). Each language holds its
own copy of every field, and a recruiter sees the one matching their interface. Draft one complete copy per language,
the same facts in both, written natively rather than word for word.

## Other fields and settings

Photo, banner and Featured are advice only. Open to Work: public frame or recruiters-only; the user chooses and the
audit states both.
