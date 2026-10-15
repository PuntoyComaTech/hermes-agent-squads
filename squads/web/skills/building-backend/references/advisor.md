# Advisor consultation

The advisor is a stronger model reached with `delegate_task` from your own card. It reads files, answers, and writes nothing.

## When to consult

1. Before choosing a data model.
2. Before choosing an auth approach.
3. After two failed attempts at the same error.
4. Before an irreversible migration (one that drops or rewrites data).
5. When the reviewer repeats a finding you already fixed once.

Outside those triggers, decide with what you have: assume if the impact is low and record the assumption in the milestone note. At most 2 consultations per card, this one included.

## What the delegation carries

- The question in one sentence, with the decision it blocks.
- The error output or log excerpt, verbatim, trimmed to the relevant frames.
- The file paths it may read: the migration or schema, the auth module, `spec.md`, the milestone note.
- What you already tried and what you rule out, in one line each.

Never paste a secret, a token, a customer record or an entire log. Give the path and the excerpt.

## Reading the answer

- The answer frame is: recommendation, why, main risk, how to verify.
- You decide. The advisor advises: if you disagree, say why in the milestone note and move on.
- A vague answer ("it depends") is not a dead end: ask once more for the safest concrete option, then decide.

## Recording it

In the milestone note's Advisor section:

```markdown
## Advisor
Q: session cookies or rotating tokens for the client portal?
A: cookies (httpOnly, sameSite lax); tokens only if a mobile app appears.
Decision: cookies. Recorded 2026-10-12.
```

## Verification

- The consultation happened only on a real trigger, and the card body shows question, error and paths.
- The advice and your decision are in the milestone note; the repo itself changed only by your hand.
- No secret, token or personal record left the machine in the question.
