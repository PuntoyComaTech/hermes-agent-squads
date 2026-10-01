# 0008 · Web quality-gate fixes and visible previews

> Migration (`base/08-updates.md`). Run by the builder. Conditional: only if `web` is in `builder/installed.yaml`.

## What and why

Part of web `plan_version: 3` (`squads/web/squad.yaml`). Two fixes from the first real site:

1. **Quality-gate configs that run.** The configs built from D-033's prose failed in every tool.
   `05-scripts.md` "Quality gate" now gives the verified file contents and a traps table. The
   Prettier file becomes `.prettierrc.json`; `run-gate.mjs` checks it sits at a repo root and runs
   `knip` with no flags.
2. **Visible work in progress (D-035).** The developer leaves build screenshots in
   `reviews/<ID>-r<R>/` from the first renderable version and writes a `progress` outbox file that
   `deliver.py` sends. No screenshots, no handoff to PREVIEW.

## Already applied if

`web` is not in `installed.yaml` (skip and record it), or the Verify checks pass.

## Steps

1. Back up per `08-updates.md` §3: a commit in `~/Hermes` and `hermes profile export` of
   `web-developer`, `web-deployer`, `web-reviewer` and `orchestrator`.
2. Rewrite `{{W}}/templates/quality/biome.json`, `eslint.config.mjs`, `run-gate.mjs` and
   `.prettierrc.json` from `05-scripts.md` "Quality gate". Show a stale `.prettierrc` before
   removing it. `quality.json` and `tsconfig.json` do not change.
3. In every existing site `repo/`: replace the four config files with the corrected ones. Add the
   `rollup` pin to `pnpm-workspace.yaml` only if `tsc --noEmit` reports the vite/rollup `Plugin`
   conflict. Run the gate once and report the result. Do **not** commit.
4. Rewrite `{{W}}/scripts/deliver.py` from `05-scripts.md` (new `progress` kind) and rerun its
   tests in `--simulate`.
5. With the three-way comparison (`08-updates.md` §4), from the current plan text: the
   `web-developer` SOUL and `skills/developer/site-build` (`03-bots.md` §2, §4.1), and
   `skills/orchestration/SKILL.md` (`03-bots.md` §5.1 "Visible work in progress").
6. Set `plan_version: 3` in `{{ROOT}}/projects/web/squad.yaml`. Rerun
   `python {{ROOT}}/scripts/registry.py` and apply the printed list if it changed.

## Conflicts

A file, template or skill section the user changed: show both and ask (`08-updates.md` §4). A
site repo with its own lint or format config: show it and ask which wins; never run two
formatters on one file.

## Verify

- `node {{W}}/templates/quality/run-gate.mjs --help` exits 0. Run from the template folder without
  `--help`, it exits 1 ("not a repo root").
- On a site repo, `pnpm exec biome check --error-on-warnings .` starts with no `Found an unknown
  key`, and `pnpm exec tsc --noEmit` exits 0.
- `deliver.py --simulate` prints a `progress` message for a sample `progress` file.
- The developer SOUL contains `progress.json`; the orchestrator skill contains "Visible work in
  progress".
- `plan_version` is `3` in `{{ROOT}}/projects/web/squad.yaml`.

## Rollback

Restore the template files, `deliver.py` and the skills from the step 1 backup, remove the rollup
pin where this migration added it, and set `plan_version` back to `2`. Site repos keep their
copies; screenshots already taken stay.
