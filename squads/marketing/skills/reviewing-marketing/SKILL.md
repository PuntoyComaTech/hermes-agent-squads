---
name: reviewing-marketing
description: "Reviews a marketing piece with five lenses. Use when a review stage card asks to approve, fix or escalate a piece before the user sees it."
---

# Reviewing marketing

Judge against the brief and `brand.md`, not taste. Never edit the piece. Each finding states what, where and the fix. Conventions: `brand-contract`.

## When to Use

- A `review` stage card is ready: a complete piece waits for the verdict.
- Your review card resumes after its fix cards are done.
- A draft document (plan, report, guide) needs the same five lenses.

## Procedure

1. Look at the rendered files, the document or the screenshots before reading the brief. Write down your first impression as a cold reader.
2. Read the brief, `brand.md`, `preferences.md`, `copy.md` and `sources.md`. Read `round` from `review.md` (0 when absent or when the card key ends in `review-c<N>`). On a resumed card, verify each requested change first, then review the whole piece again.
3. Run five lenses as clean-context subagents (`delegate_task`), one each, then weigh their returns:
   - **brief fit**: objective, audience, awareness level, the single call to action;
   - **voice**: voice samples, vocabulary and form of address in `brand.md`;
   - **claims**: every claim on a verified proof point, testimonial permission, mandatory disclosure, no invented numbers;
   - **persuasion**: hook, specificity, one idea, the `brand-contract -> Rules` veto list;
   - **format specs**: the brief's sizes and `brand-contract -> Formats`.
4. Decide:
   - **Critical** (blocks approval): an unsupported claim, a missing disclosure, an unlicensed or unknown-licence asset, an unmet format spec, a veto-list item, a testimonial without permission.
   - `fix` when every issue is fixable and `round < brand.md -> reviewer_rounds`.
   - `escalate` when rounds are spent, or the issue needs the user (price, a legal claim, a fact only the user has).
   - `approve` when no critical issue remains and the piece meets the brief.
5. Write `review.md`: verdict, `round`, one line per finding (what, where, fix), and two lines on why it works for an approval.
6. On `fix`, with N = round + 1, set `round: <N>` in `review.md`, then:
   - `kanban_create` one card per owning stage with no `parents`, key suffix `-r<N>` and the exact changes in the body: `copy-r<N>` (marketing-creative, `skills: [writing-copy]`) or `asset-r<N>` (marketing-producer, `skills: [producing-assets]`). A copy fix also files `asset-r<N>` with `parents: [<copy-r<N> id>]`, because the assets render the copy.
   - `kanban_link` the last fix card (`parent_id`) to this card (`child_id`).
   - `kanban_block(kind="dependency", reason="waiting for <fix card ids>")` on this card. It returns to `todo` and resumes when the fix is done; the `approve` card waits until you complete.
7. On `escalate`: `kanban_block(kind="needs_input", reason="<the exact question>; settled: <what is already decided>")`.
8. On `approve`: `kanban_complete` with `review.md` in `metadata.changed_files`.

## Pitfalls

- Approving a claim you could not find in `brand.md`.
- Asking for changes that contradict `preferences.md` or the user's literal request.
- Fix requests without exact wording ("make it better").
- Completing the card on `fix`: the `approve` card would start before the fix.

## Verification

- `review.md` has the verdict, the round and one line per finding.
- An approval has zero critical items and two lines on why it works.
- A fix has one `-r<N>` card per owning stage, the last one linked as a parent of this card, and this card blocked with `kind: "dependency"`.
- An escalation has one exact question, and nothing in the piece was changed by you.
