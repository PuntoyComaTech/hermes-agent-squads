---
name: building-backend
description: "Builds APIs, data, auth and tests in the site repo. Use when a milestone adds routes, persistence, auth, integrations or a migration."
---

# Building the backend

## When to Use

- An `api` card: server routes, data storage, authentication, a third-party integration or a migration.
- A `fix-r<N>` card with a backend finding.

## Procedure

1. `kanban_show`. Read the card body, `spec.md`, the milestone note, `decisions.md` and `repo/`.
2. Branch: `git -C repo switch -c web/<ID>`, or `git -C repo switch web/<ID>` when it exists. Never work on `main`.
3. Contract first: the route or function signature, request and response shapes, and error cases as failing tests (`pnpm -C repo test`), then the implementation.
4. Data, auth, integrations and secrets: `references/data-and-auth.md`.
5. Advisor: on a trigger in `references/advisor.md`, consult before deciding.
6. Validate every external input at the boundary, one module per concern.
7. Before the commit: `pnpm -C repo check`, `pnpm -C repo test`, `pnpm -C repo lint`, and the milestone's integration path against a local database or the platform's local runtime, never production.
8. Commit on `web/<ID>`. Fill the milestone note (Done, Tests run, Assumptions, Env vars and bindings, Migrations with `destructive: yes|no`) and set `status: built`.
9. `kanban_complete` with the changed files. Never push or deploy.
10. Fix card: apply exactly the findings in its body, append one History line, `kanban_complete`.

## Pitfalls

- Never log request bodies, tokens, cookies or personal data; log ids and outcomes.
- Compare secrets with the platform's constant-time helper, never `==`.
- Never add a service, queue or database the spec did not choose.
- Never disable a failing test: fix it, or `kanban_block(kind="needs_input", reason="<test>: <why it cannot pass>")`.
- Never change an existing response shape: add a field or a route.

## Verification

- Every backend acceptance criterion has an automated test.
- Migrations apply on a fresh database and on a copy of the current one.
- The milestone note names every env var and binding the site now needs.
