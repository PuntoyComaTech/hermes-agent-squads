---
name: preparing-interviews
description: "Builds interview preparation for one opening. Use when an interview card arrives or the user asks to prepare for an interview with a company."
---

# Preparing interviews

One opening, one file: `openings/<ID>/interview.md`, beside `application/`. The pack must match the CV and the letter
the interviewer has read.

## When to Use

- A `preparing-interviews` card from the manager ("prepare me for the interview with X").
- Before the user's interview, when `analysis.json` and the company profile exist.
- A mock interview, when the user asks to practise (after the pack exists).

## Procedure

1. Read `analysis.json` (requirements, fit, `hard_gaps`, the hiring-manager lens), `opening.md`,
   `companies/<company>.md`, `achievements.yaml`, and the two documents the interviewer read:
   `application/cv_content.json` and `application/cover_letter.md`.
2. Write `interview.md` in the opening's language, sections in the order of `references/interview-prep.md`:
   - **Consistency brief**: the claims the CV and letter make that the interviewer will probe, each with its id.
   - **12 to 15 likely questions**, most probable first, each with a 3 to 5 sentence answer built only from verified
     achievements and cited (`ACH-007`). Story questions use the STAR shape.
   - **Gap preparation**: for every `hard_gap`, the three-line block (acknowledge, bridge, plan).
   - **Tough questions** from `references/interview-prep.md`, answered from the record only.
   - **Three to five questions to ask the company**, drawn from the opening and the company profile, chosen for the stage.
   - **Logistics**: format, language, interviewer names and titles only when public.
3. Mock interview, only when asked: follow `references/mock-interview.md` in the conversation. Write nothing to the
   project folder unless the user asks for notes.
4. `kanban_complete` naming the file. The manager delivers it to the user.

## Pitfalls

- Never invent a company detail that the dated profile or the opening does not state.
- Never show a claim stronger than the record: `participated` stays "took part in". If the user asks for an answer that
  claims more, offer the honest framing instead.
- Contact details never appear in the pack beyond the name the user uses.
- Keep it readable in one sitting: bullets, no paragraph longer than five lines.

## Verification

- Every suggested answer cites at least one verified achievement.
- Every `hard_gap` has its gap block, and the answer never claims the missing skill.
- The consistency brief covers every number, scope word and in-progress item in the CV and the letter.
- The file is in the opening's language and sits beside `application/`.
