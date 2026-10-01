# 0008 · Web quality-gate fixes and visible previews

> Migration (`base/08-updates.md`). Run by the builder. Conditional: only if `web` is in `builder/installed.yaml`.

## What and why

Two fixes from the first real site built with this squad (D-035, and corrections to D-033's spec):

1. **The quality-gate template, as actually verified.** The config prompts in `05-scripts.md`
   "Quality gate" were written as prose, and the files built from them did not run: Biome refused
   to start (`{"all": true}` and `$comment` are not keys it accepts), it swept `.astro` files it
   cannot parse, ESLint had no `projectService` (no typed rule could run) and used two option
   shapes its plugins reject, and the gate runner passed `knip` a flag that does not exist.
   `05-scripts.md` now carries the verified file contents and a traps table with the exact errors.
   The template in `{{W}}/templates/quality/` is rewritten from them (`.prettierrc` becomes
   `.prettierrc.json`), and `pnpm-workspace.yaml` gains the `rollup: 4.55.1` pin that
   `exactOptionalPropertyTypes` + `skipLibCheck: false` need (vite 6.4.3 and rollup 4.63.5 declare
   the same `Plugin` interface incompatibly).
2. **Visible work in progress** (D-035): every BUILD milestone leaves build screenshots in
   `reviews/<ID>-r<R>/` from the first renderable version (`build-<page>-mobile.png`,
   `build-<page>-desktop.png`, `build-<page>-viewport-mobile.png`) and they are part of the
   deliverable (no screenshots, no handoff to PREVIEW); the orchestrator opens the first version in
   the desktop preview pane (`desktop_preview`) or sends the artifacts when its session has no
   such tool, and cuts and reassigns a worker after two attempts with no visible artifact.

Part of web `plan_version: 3` (`squads/web/squad.yaml`): the BUILD output and its handoff changed.

## Already applied if

`web` is not in `installed.yaml` (skip and record it), or the Verify checks pass.

## Steps

1. Back up per `08-updates.md` §3: a commit in `~/Hermes` and `hermes profile export` of
   `web-developer`, `web-deployer`, `web-reviewer` and `orchestrator`.
2. Rewrite `{{W}}/templates/quality/biome.json`, `eslint.config.mjs`, `run-gate.mjs` and the
   Prettier config from `05-scripts.md` "Quality gate" (the Prettier file becomes
   `.prettierrc.json`; remove a stale `.prettierrc` after showing it, never silently).
   `quality.json` and `tsconfig.json` do not change. A file the user changed is shown and asked
   about, never overwritten.
3. In every site `repo/` that already exists: add the `rollup: 4.55.1` pin to
   `pnpm-workspace.yaml` `overrides` if `tsc --noEmit` reports the vite/rollup `Plugin` conflict,
   and replace the repo's copies of the four config files with the corrected ones. Do **not**
   commit the result: run the gate once and report what it says.
4. Templates, with the three-way comparison (`08-updates.md` §4), from the current plan text:
   the `web-developer` SOUL and `skills/developer/site-build` (`03-bots.md` §2 and §4.1: the
   screenshot step and "no screenshots, no handoff"), and `skills/orchestration/SKILL.md`
   (`03-bots.md` §5.1 "Visible work in progress").
5. Set `plan_version: 3` in `{{ROOT}}/projects/web/squad.yaml`. Rerun
   `python {{ROOT}}/scripts/registry.py` and apply the printed list if it changed.

## Conflicts

A template or skill section the user changed: show both and ask (`08-updates.md` §4). A site whose
repo has its own lint or format config: show it and ask which one wins; never run two formatters
on one file.

## Verify

- `node {{W}}/templates/quality/run-gate.mjs --help` exits 0, and
  `pnpm exec biome check --error-on-warnings .` on a site repo starts (no `Found an unknown key`).
- `pnpm exec tsc --noEmit` on a site repo exits 0 with the rollup pin in place.
- The orchestrator skill contains "Visible work in progress", and the developer SOUL contains the
  screenshot step.
- `plan_version` is `3` in `{{ROOT}}/projects/web/squad.yaml`.

## Rollback

Restore the four template files and the two skills from the step 1 backup, remove the rollup pin
where this migration added it, and set `plan_version` back to `2`. The sites' repos keep their
copies; the screenshots already taken stay where they are.
