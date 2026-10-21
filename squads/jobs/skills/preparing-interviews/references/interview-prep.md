# Interview preparation

One file per opening: `openings/<ID>/interview.md`, beside `application/`. It is written from `analysis.json`,
`opening.md`, the dated company profile and `achievements.yaml`. It must match the CV and the letter the interviewer has
read.

## Contents

- Questions and their sources
- STAR mapping
- Consistency brief
- Gap preparation
- Tough questions
- Questions to ask the company
- Logistics and layout

## Questions and their sources

Write 12 to 15 likely questions, most probable first. Draw them from these sources, in this order:

1. Feedback from an earlier stage (the status history or the user's message). Whatever was doubted comes back.
2. The fit gaps in `analysis.json`. The weakest requirements are the likeliest probes.
3. The posting's must-haves, competency by competency.
4. The stage. A screen gets motivation and timeline. A technical round gets the stack and a practical task. A final round
   gets values, role scope, salary and "any reservations".

## STAR mapping

Each story is a verified achievement arranged as Situation, Task, Action, Result: two or three sentences per part.
Keep an answer to one or two minutes.

| Story | Achievement | Use for |
|---|---|---|
| Report automation | ACH-007 | "A process you improved", "a time you used data to save effort" |

Mapping steps:

- Match each question to the story whose tags fit it, not to the story with the biggest number.
- A question with no story gets a new draft built only from achievements in the record, marked "new draft".
- A story missing a detail is marked "needs detail from the user". Never fill the gap with a guess.
- An achievement recorded as `participated` stays `participated` in every answer: "I took part in", "I supported",
  "my part was".

## Consistency brief

A short list at the top of the file: the claims the CV and the letter make that the interviewer is likely to probe.
Numbers, scope words (led, owned), tools, dates and any in-progress item. For each claim, give the achievement id and
the first sentence of the answer.

The rule: no claim in the room that is not on the paper, and every claim on the paper is defensible in depth. If a
document claims something the record cannot support in depth, tell the user before the interview.

## Gap preparation

For every `hard_gap` in `analysis.json`, one three-line block:

1. Acknowledge: "I have not used dbt in production."
2. Bridge: the adjacent verified achievement, cited, for example the SQL transformations behind the reporting work.
3. Plan: what the candidate is doing to close the gap, only if the user has said so.

Never invent experience to close a gap.

## Tough questions

Prepare each answer from the record only:

- Why did you leave your last role? Factual and brief, forward-looking, no criticism of the former employer.
- You do not have X. Use the gap block above.
- Where do you see yourself in five years? The growth the role offers, not a title.
- What is your biggest weakness? A real one, with a mitigation the user actually practises.
- Why this company? Two hooks from the dated company profile, each sourced. Never a generic line.
- Long tenure with little visible output: a two-part answer. What filled the time (verified), and what it produced.

## Questions to ask the company

Three to five, drawn from the opening and the company profile, chosen for the stage:

- Screen: what the first three months look like; how success is measured; the size of the team.
- Technical: the stack's pain points; how decisions are reviewed; what a typical week holds.
- Final: how the team handles disagreement; what the last person in the role achieved in the first year; why the role is
  open now.

Drop any question the company's public material already answers. Asking it signals that the candidate did not look.

## Logistics and layout

- Header: company, role, opening id, stage, date and format. Interviewer names and titles only when they are public.
- Interview language: the opening's language, unless the user asked otherwise.
- One file, bullets, no paragraph longer than five lines.
- Sections in this order: consistency brief, likely questions with answers, gap preparation, tough questions, questions to
  ask, logistics.
