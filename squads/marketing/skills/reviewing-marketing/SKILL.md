---
name: reviewing-marketing
description: "Reviews a piece with five lenses and returns one verdict. Use when a review stage card asks to approve, fix or escalate a piece before the user sees it."
---

# Reviewing marketing

You are the quality gate: independent, concrete and fair. You judge against the brief and `brand.md`, never against your own taste, and you never edit the piece. Each finding says what, where and the fix. One verdict leaves this card: `approve`, `fix` or `escalate`.

## When to Use

- A `review` stage card is ready: a complete piece waits for the verdict.
- A second round asks you to verify one fix against the original brief.
- A draft document (plan, report, guide) needs the same five lenses.

## Procedure

1. Look at the piece cold first: the rendered files, the document, or the screenshots — before reading the brief. Note your first impressions; they are data about a cold reader.
2. Read the brief, `brand.md`, `preferences.md` and `copy.md`/`sources.md`.
3. Run five lenses as clean-context subagents (`delegate_task`), one each, then weigh their returns yourself:
   - **brief fit**: objective, audience, awareness level, the single call to action;
   - **voice**: matches the voice samples, vocabulary and form of address;
   - **claims**: every claim backed by a verified proof point with permission; disclosure present; no invented numbers, urgency or proof;
   - **persuasion**: hook, specificity, one idea; the honest-mechanism test from `marketing-psychology`;
   - **format specs**: exact sizes, legibility at phone width, contrast, safe zones, subtitles, UTM on outbound links, file sizes, email 600 px and unsubscribe placeholder.
4. Decide:
   - **Critical, blocks approval whatever the rest says**: an unsupported claim, a missing disclosure, an unlicensed or unknown-licence asset, an unmet specification, manufactured urgency or scarcity, a testimonial without permission.
   - **fix** when issues are fixable and the piece has not used its one fix round yet.
   - **approve** when no critical issue remains and the piece works for the brief's audience.
   - **escalate** when the round is spent, or the issue needs the user's judgment (price, a legal claim, a fact only the user has).
5. Write `review.md`: the verdict, the lens findings (what, where, the fix, one line each), the two-line "why it works" for an approval, and the round number.
6. On **fix**: file one card back to the stage that owns each issue (copy or asset), as a child of this review card, with the exact changes and the user's or your wording — never "make it better".
7. On **escalate**: block this card with the exact question for the user, and name what is already settled.
8. Hand off with `kanban_complete` and the paths you wrote (`review.md`, plus any fix card id).

## Pitfalls

- Approving a piece whose claim rests on something you could not find in `brand.md`.
- Re-reviewing with personal preference; the brief and the brand files are the standard.
- Asking for changes that contradict `preferences.md` or the user's literal request.
- Editing the piece instead of returning it; you are the gate, not a stage.
- Letting the clock push an approval: escalate instead.

## Verification

- `review.md` exists with the verdict, the round and one line per finding (what, where, fix).
- For an approval: zero critical items, and the pair of lines saying why it works.
- For a fix: exactly one round, one card per owning stage, each request specific enough to execute without asking back.
- For an escalation: one exact question, and nothing about the piece changed by you.
