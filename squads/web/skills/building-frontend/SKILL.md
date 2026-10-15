---
name: building-frontend
description: "Builds the UI, motion and 3D of a site milestone. Use when a card changes pages, components, styling, scroll animation or a three.js scene."
---

# Building the frontend

Motion and scroll are in `references/motion.md`, 3D in `references/three.md`, the design rail in `references/ui.md`.

## When to Use

- A `ui` card (or a fix round on it) needs pages, components, styling, animation or a 3D scene.
- A visual review finding comes back to you as a FIX round.
- The milestone is UI-only and the backend stage was skipped.

## Procedure

1. `kanban_show`. Read the card body, `spec.md`, the milestone note, `DESIGN.md` and the current `repo/`.
2. Branch: `git -C repo switch -c web/<ID>` (or `switch` to it when the card is a fix round). Never work on `main`.
3. First build only: `python3 "$HERMES_HOME/skills/squad-web/building-frontend/scripts/scaffold_site.py" --stack <stack> --name <site> --dir repo` writes the pinned project from `scripts/stacks.json`. An existing repo is reused as is.
4. Design system before pages: tokens (color, type scale, spacing, radius, shadow), one component per file, and layout primitives. Follow `DESIGN.md` when it exists; otherwise apply `references/ui.md` and record the choices in `decisions.md`.
5. Pages: one route per row of `spec.md -> Pages`; semantic landmarks, one `h1`, heading order, `alt` on every meaningful image, `lang` per language, forms with labels and a working submit path.
6. Motion: follow `references/motion.md`. Animate `transform` and `opacity` only, keep the first render free of animation work, honor `prefers-reduced-motion`, and stop every listener, timeline and trigger on teardown.
7. 3D: only when the spec asks for it, following `references/three.md`: lazy-loaded canvas, DPR clamped, paused when off-screen, a static fallback for reduced motion or a failed load.
8. Content: only what the user gave or approved; drafted copy is marked "draft, needs the user's ok" in the milestone note. Never invent prices, addresses, hours, reviews or legal claims.
9. Tests and checks before the commit: typecheck (`tsc --noEmit`, or the stack's `astro check`), lint/format (`biome` when present), unit tests (`vitest run`) and the critical path in `playwright`. Fix red, never relax a rule.
10. Performance: check the built page against the site's budgets — largest contentful paint under 2.5 s on a mobile profile, cumulative layout shift under 0.1, no image larger than twice its rendered size, fonts preloaded or cached.
11. Commit on `web/<ID>` with a message naming the milestone. Fill the milestone note (Done, tests, assumptions, env var names) and set status `built`, `commit` and `updated`.
12. The chain's `preview` card is already filed with your card as its parent; complete yours with `kanban_complete` and the changed files. Never push, open a PR or deploy: that is web-deployer's stage.
13. Fix round: apply exactly the `changes` of the review, keep the rest untouched, append one History line, and complete again.

## Pitfalls

- Never hard-code text that belongs in `spec.md` or `DESIGN.md`; a second source of truth drifts.
- Never ship a client bundle that imports server-only modules, secrets or an unbounded dependency.
- Never animate layout properties (`width`, `top`, `margin`), use infinite timers, or leave a `ScrollTrigger` alive after unmount.
- Never hide content behind animation-only reveals: the page must be complete with JavaScript disabled.
- Never import a font or library from a CDN the site cannot survive losing; prefer the stack's own pipeline.
- Never add a dependency for something twenty lines of code can do, and never upgrade the stack versions pinned by `scaffold_site.py` without a `decisions.md` line.

## Verification

- `tsc --noEmit` (or `astro check`) passes, lints pass, unit tests pass, and the critical path passes in a real browser.
- Every acceptance criterion of the milestone is implemented and exercised.
- Keyboard: tab order through the page, visible focus, no trap; axe reports no `critical` or `serious` issue at build time.
- Motion follows `references/motion.md` and 3D follows `references/three.md` when present.
- The milestone note says `status: built` with the commit hash, tests run and assumptions.
