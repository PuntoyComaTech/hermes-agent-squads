---
name: building-frontend
description: "Builds the UI, motion and 3D of a site milestone. Use when a card changes pages, components, styling, scroll animation or a three.js scene."
---

# Building the frontend

## When to Use

- A `ui` card, or a `fix-r<N>` card with a visual or frontend finding.
- The milestone is UI-only and the backend stage was skipped.

## Procedure

1. `kanban_show`. Read the card body, `spec.md`, the milestone note, `DESIGN.md` and `<repo>/` (site-contract step 2), and once per card site-contract `references/engineering-rules.md`.
2. Branch: `<repo>` is already on `web/<ID>` (site-contract step 7); never switch, stash or reset it. On another branch: block as that step says.
3. The manager laid the strict base (`pnpm -C <repo> quality` passes on `main`). No `package.json` or no `quality` script in `<repo>/`: `kanban_block(kind="needs_input", reason="the strict base is missing: run site_base.py")`; never scaffold or configure lint yourself.
4. Design system before pages. No `DESIGN.md`: write it with the `design-md` skill from `inputs/` and `references/ui.md`. Tokens, components and layout primitives per `references/ui.md`.
5. Pages: one route per row of `spec.md -> Pages`.
6. Motion or scroll animation: `references/motion.md`. 3D, only when the spec asks for it: `references/three.md`. Packages: site-contract `scripts/stacks.json -> motion`, added with `pnpm add <name>` and no version.
   Save each finished piece as you go (site-contract step 8): the design tokens, each component, each section, each page. The user watches the live tab; a card that commits once at the end leaves them blind.
7. Content: only what the user gave or approved; drafted copy is listed as "draft, needs the user's ok" in the milestone note. Never invent prices, addresses, hours, reviews or legal claims.
8. Before the final commit: `pnpm -C <repo> quality` (site-contract step 9). Fix red; never relax a rule.
9. Final commit on `web/<ID>` with a message naming the milestone. Fill the milestone note (Done, Tests run, Assumptions, Env vars and bindings) and set `status: built`, `commit` and `updated`.
10. `kanban_complete` with the changed files. The `preview` card is already your child. Never push, open a PR or deploy.
11. Fix card: apply exactly the findings in its body, append one History line, `kanban_complete`.

## Pitfalls

- Never hard-code text that belongs in `spec.md` or `DESIGN.md`.
- Never import server-only modules or secrets into a client bundle.
- Never load a font or library from a third-party CDN; use the stack's own pipeline.
- Never add a dependency for something twenty lines of code can do. Add a package only with `pnpm add <name>` (or the framework's own `add` command), never by editing `package.json` or with a version typed from memory; pnpm picks the newest release 3 days old. A `quality:deps` failure: run site-contract `scripts/security_fix.py --repo <repo>`, never pin a version yourself; review each major it reports (site-contract `references/project-base.md`, section 2).
- Never add `// biome-ignore`, `eslint-disable`, `@ts-ignore`, `@ts-expect-error` or `any`, and never edit `biome.jsonc`, `tsconfig.json`, `knip.json`, `.jscpd*.json` or `tools/quality/` (baselines included): split the function, type the value, extract the shared code.

## Verification

- `pnpm -C <repo> quality` passes, and the critical path works in a real browser at 390 px and 1440 px.
- `git -C <repo> log main..web/<ID>` shows one `wip(<ID>):` commit per finished piece, not a single end-of-card commit.
- Every acceptance criterion of the milestone is implemented.
- The Verification lists of the references you used pass.
- The milestone note says `status: built` with the commit hash, tests run and assumptions.
