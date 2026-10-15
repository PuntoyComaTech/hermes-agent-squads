---
name: building-backend
description: "Builds APIs, data, auth and tests in the site repo. Use when a milestone adds routes, persistence, auth, integrations or a migration."
---

# Building the backend

Data and auth rules are in `references/data-and-auth.md`; the advisor consultation is in `references/advisor.md`.

## When to Use

- A card needs server routes, data storage, authentication, a third-party integration or a migration.
- A frontend card needs a contract (endpoint, payload, error shape) before it can consume it.
- A review FIX round names a backend finding.

## Procedure

1. `kanban_show`. Read the card body, `spec.md`, the milestone note, `decisions.md` and the current `repo/`.
2. Branch: `git -C repo switch -c web/<ID>` (or `switch` to it on a fix round). Never work on `main`.
3. Contract first: write the route or function signature, the request and response shape, and the error cases as tests (`vitest run` or the stack's runner). Red tests before implementation.
4. Data: define the schema and one migration per change, forward-only. Read `references/data-and-auth.md` before choosing a model; consult the advisor first (step 8) if the model is not obvious.
5. Implementation: one module per concern, dependency direction pointing at the domain, no framework object leaking into business logic. Validate every external input at the boundary.
6. Auth, when the milestone includes it: sessions or tokens per `references/data-and-auth.md`, passwords hashed with the platform's primitive, nothing custom.
7. Secrets and bindings: names documented in the milestone note, values supplied by the deployer's environment. Never in the repo, never in `.env` committed, never in a test fixture that ships.
8. Advisor triggers (`references/advisor.md`): before choosing a data model or auth approach, after two failed attempts at the same error, before an irreversible migration, and when the reviewer repeats a finding. One question per consultation; record question, advice and the decision you took.
9. Run the full local check before committing: typecheck, lints, unit tests, and the integration path the milestone needs (a local database or the platform's dev runtime, never production).
10. Migrations that drop or rewrite data are destructive: flag `destructive: yes` in the milestone note with what changes and how it can be rolled back. The deploy stage will not run it without the user's confirmation.
11. Commit on `web/<ID>`, fill the milestone note (Done, tests, assumptions, env var and binding names, migrations), set `status: built`.
12. Complete your card with `kanban_complete` and the changed files. The `ui` or `preview` card waits on it; never push or deploy.
13. Fix round: apply exactly the review's `changes`, append one History line, complete again.

## Pitfalls

- Never log request bodies, tokens, cookies or personal data; log identifiers and outcomes.
- Never trust client input, including a value that "cannot" be wrong, and never compare secrets with `==` on strings when the platform offers a constant-time helper.
- Never run a destructive migration against a live database from a build card; that is a deploy-stage action with a backup and a confirmation.
- Never introduce a service, queue or database the spec did not choose; prefer what the platform already provides.
- Never leave a failing test disabled: fix it or block and say why.
- Never change an existing API's response shape for a new consumer; add a field or a route.

## Verification

- Every acceptance criterion that touches the backend is exercised by an automated test, not a manual curl.
- Tests cover the failure path: invalid input, unauthorized access, missing record.
- Migrations apply cleanly on a fresh database and on a copy of the current one.
- No secret, token or personal record appears in the repo, in fixtures, or in logs.
- The milestone note names every env var and binding the site now needs.
