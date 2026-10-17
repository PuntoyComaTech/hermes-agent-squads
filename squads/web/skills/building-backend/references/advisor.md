# Advisor consultation

Consult with `delegate_task`; your profile routes it to the advisor lane. The advisor reads files and answers; it writes nothing.

## When to consult

1. Before choosing a data model.
2. Before choosing an auth approach.
3. After two failed attempts at the same error.
4. Before an irreversible migration (one that drops or rewrites data).
5. When the reviewer repeats a finding you already fixed once.

Outside those triggers, decide and record the assumption in the milestone note. At most 2 consultations per card.

## What the delegation goal carries

- The question in one sentence, with the decision it blocks.
- The error output or log excerpt, verbatim, trimmed to the relevant frames.
- The file paths it may read: the migration or schema, the auth module, `spec.md`, the milestone note.
- What you already tried and what you rule out, in one line each.

Never a secret, a token, a customer record or a whole log.

## Reading the answer

- Ask for: recommendation, why, main risk, how to verify.
- You decide. If you disagree, write why in the milestone note.
- A vague answer: ask once more for the safest concrete option (the second consultation), then decide.

## Recording it

In the milestone note's Advisor section:

```markdown
## Advisor
Q: session cookies or rotating tokens for the client portal?
A: cookies (HttpOnly, SameSite=Lax); tokens only if a mobile app appears.
Decision: cookies. Recorded <YYYY-MM-DD>.
```

## Verification

- Each consultation matches a trigger above.
- Question, advice and decision are in the milestone note.
- No secret, token or personal record was in the question.
