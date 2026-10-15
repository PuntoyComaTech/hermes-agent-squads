---
name: building-frontend
description: "Builds the UI, motion and 3D of a site milestone. Use when a card changes pages, components, styling, scroll animation or a three.js scene."
---

# Building the frontend

## When to Use

- A `ui` card, or a `fix-r<N>` card with a visual or frontend finding.
- The milestone is UI-only and the backend stage was skipped.

## Procedure

1. `kanban_show`. Read the card body, `spec.md`, the milestone note, `DESIGN.md` and `repo/`.
2. Branch: `git -C repo switch -c web/<ID>`, or `git -C repo switch web/<ID>` when it exists. Never work on `main`.
3. Empty `repo/` only: `python3 "$HERMES_HOME/skills/squad-web/building-frontend/scripts/scaffold_site.py" --stack <site.yaml stack> --name <slug> --dir repo`, then `pnpm -C repo install`.
4. Design system before pages. No `DESIGN.md`: write it with the `design-md` skill from `inputs/` and `references/ui.md`. Tokens, components and layout primitives per `references/ui.md`.
5. Pages: one route per row of `spec.md -> Pages`.
6. Motion or scroll animation: `references/motion.md`. 3D, only when the spec asks for it: `references/three.md`. Packages and pins: `scripts/stacks.json -> motion`.
7. Content: only what the user gave or approved; drafted copy is listed as "draft, needs the user's ok" in the milestone note. Never invent prices, addresses, hours, reviews or legal claims.
8. Before the commit: `pnpm -C repo check`, `pnpm -C repo test`, `pnpm -C repo lint`. Fix red; never relax a rule.
9. Commit on `web/<ID>` with a message naming the milestone. Fill the milestone note (Done, Tests run, Assumptions, Env vars and bindings) and set `status: built`, `commit` and `updated`.
10. `kanban_complete` with the changed files. The `preview` card is already your child. Never push, open a PR or deploy.
11. Fix card: apply exactly the findings in its body, append one History line, `kanban_complete`.

## Pitfalls

- Never hard-code text that belongs in `spec.md` or `DESIGN.md`.
- Never import server-only modules or secrets into a client bundle.
- Never load a font or library from a third-party CDN; use the stack's own pipeline.
- Never add a dependency for something twenty lines of code can do. Never change a pin from `scripts/stacks.json` without a `decisions.md` line.

## Verification

- `pnpm -C repo check`, `test` and `lint` pass, and the critical path works in a real browser at 390 px and 1440 px.
- Every acceptance criterion of the milestone is implemented.
- The Verification lists of the references you used pass.
- The milestone note says `status: built` with the commit hash, tests run and assumptions.
