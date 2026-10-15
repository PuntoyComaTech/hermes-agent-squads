---
name: preparing-interviews
description: "Builds interview preparation notes for one opening. Use when an interview card arrives or the user asks to prepare for an interview with a company."
---

# Preparing interviews

One opening, one file: `interview.md` beside `application/`. Every suggested answer comes from `achievements.yaml`
with `verified: true`; you never invent a story, a number or a level.

## When to Use

- A `preparing-interviews` card from the lead ("prepare me for the interview with X").
- Before the user's interview, when `analysis.json` and the company profile exist.

## Procedure

1. Read `analysis.json` (requirements, priorities, hard gaps, hiring-manager lens), `opening.md`,
   `companies/<company>.md` and `achievements.yaml`.
2. Write `interview.md`:
   - **12 to 15 likely questions** in the opening's language, most probable first: the hiring manager's
     questions from `analysis.json`, the must-haves, the hard gaps, and one about the company's product.
   - Under each: a suggested answer of 3 to 5 sentences built only from verified achievements, cited
     (`ACH-007`), and the STAR shape (situation, task, action, result) when it is a story question.
   - **Gaps to prepare**: for every `hard_gap`, one honest sentence the user can say (adjacent work, plan to
     learn) and the achievement that proves the adjacent skill.
   - **Questions to ask the company**: 3 to 5, drawn from the company profile and the opening, not generic.
   - **Logistics**: interview language, format and anything the opening states about the process.
3. Keep it readable in one sitting: bullets, no paragraphs longer than 5 lines.
4. `kanban_complete` naming the file; the lead delivers it to the user.

## Pitfalls

- Never promise a skill the achievements do not support, and never coach an exaggerated claim.
- Never invent details about the company that are not in its dated profile or the opening.
- Contact details never appear here beyond the name the user uses in conversation.

## Verification

- Every suggested answer cites at least one verified achievement.
- Every `hard_gap` has a preparation line.
- The file is in the opening's language and sits beside `application/`.
