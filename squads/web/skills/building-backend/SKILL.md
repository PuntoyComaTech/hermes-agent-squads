---
name: building-backend
description: "Builds APIs, data, auth and tests in the site repo. Use when a milestone adds routes, persistence, auth, integrations or a migration."
---

# Building the backend

## When to Use

- An `api` card: server routes, data storage, authentication, a third-party integration or a migration.
- A `fix-r<N>` card with a backend finding.

## Procedure

1. `kanban_show`. Read the card body, `spec.md`, the milestone note, `decisions.md` and `<repo>/` (site-contract step 2), and once per card site-contract `references/engineering-rules.md`.
2. Branch: `<repo>` is already on `web/<ID>` (site-contract step 7); never switch, stash or reset it. On another branch: block as that step says.
3. Contract first: the route or function signature, request and response shapes, and error cases as failing tests (`pnpm -C <repo> test`), then the implementation. Logic goes in `src/server/` or `src/domain/` (covered at 100 %, never importing UI); routes stay thin. Save each finished piece (site-contract step 8): each contract with its tests, each route, each migration.
4. Data, auth, integrations and secrets: `references/data-and-auth.md`.
5. Advisor: on a trigger in `references/advisor.md`, consult before deciding.
6. Validate every external input at the boundary, one module per concern.
7. Before the final commit: `pnpm -C <repo> quality` (site-contract step 9), and the milestone's integration path against a local database or the platform's local runtime, never production.
8. Commit on `web/<ID>`. Fill the milestone note (Done, Tests run, Assumptions, Env vars and bindings, Migrations with `destructive: yes|no`) and set `status: built`.
9. `kanban_complete` with the changed files. Never push or deploy.
10. Fix card: apply exactly the findings in its body, append one History line, `kanban_complete`.

## Pitfalls

- Add a package only with `pnpm add <name>`, never by editing `package.json` or with a version from memory. A `quality:deps` failure: run site-contract `scripts/security_fix.py --repo <repo>`; review each major it reports (site-contract `references/project-base.md`, section 2).
- Never log request bodies, tokens, cookies or personal data; log ids and outcomes.
- Compare secrets with the platform's constant-time helper, never `==`.
- Never add a service, queue or database the spec did not choose.
- Never add `any`, `@ts-ignore`, an inline lint disable, or edit the quality configs (`biome.jsonc`, `tsconfig.json`, `knip.json`, `.jscpd*.json`, `tools/quality/` with its baselines).
- Never disable a failing test: fix it, or `kanban_block(kind="needs_input", reason="<test>: <why it cannot pass>")`.
- Never change an existing response shape: add a field or a route.

## Verification

- Every backend acceptance criterion has an automated test, and `pnpm -C <repo> quality` passes.
- One `wip(<ID>):` commit per finished piece on `web/<ID>`.
- Migrations apply on a fresh database and on a copy of the current one.
- The milestone note names every env var and binding the site now needs.
