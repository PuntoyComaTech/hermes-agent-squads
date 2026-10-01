# 0007 · Web quality gate

> Migration (`base/08-updates.md`). Run by the builder. Conditional: only if `web` is in `builder/installed.yaml`.

## What and why
Adds D-033's mandatory code-quality gate to every site repo: the six files of `squads/web/05-scripts.md` "Quality gate" in `{{W}}/templates/quality/`, the `quality-gate` skill, and the gate as a blocking step for developer, deployer and reviewer. The gate failure becomes the first item of the review's `critical` list, a contract change. Part of web `plan_version: 2` (`squads/web/squad.yaml`).

## Already applied if
`web` is not in `installed.yaml` (skip and record it), or the Verify checks pass.

## Steps
1. Back up per `08-updates.md` §3: a commit in `~/Hermes` and `hermes profile export` of `web-developer`, `web-deployer`, `web-reviewer` and `orchestrator`.
2. Install `osv-scanner` and download its offline database (`squads/web/04-installation.md` step 3c).
3. Write `quality.json`, `tsconfig.json`, `biome.json`, `eslint.config.mjs`, `.prettierrc` and `run-gate.mjs` into `{{W}}/templates/quality/` from `05-scripts.md` "Quality gate". A file that already exists and differs is shown and asked about, never overwritten.
4. Write `{{W}}/skills/common/quality-gate/SKILL.md` from `03-bots.md` §4.1 and `05-scripts.md` "Quality gate". It is inside `skills/common`, already in every profile's `skills.external_dirs`: no config change.
5. Templates, with the three-way comparison (`08-updates.md` §4), from the current plan text:
   - the `web-developer`, `web-deployer` and `web-reviewer` SOULs (`03-bots.md` §2);
   - `site-build`, `site-review`, `github-flow` and `site-contract` (`03-bots.md` §4.1, `02-architecture.md` §6);
   - `skills/orchestration/SKILL.md`: the skills-to-pin table, and gate blocks relayed verbatim, never a threshold negotiated in chat.
6. Set `plan_version: 2` in `{{ROOT}}/projects/web/squad.yaml`. Rerun `python {{ROOT}}/scripts/registry.py` and apply the printed list if it changed.
7. **Each existing site** with a `repo/`: copy the six files into the repo root, `pnpm add -D` the dev dependencies of the "Quality gate" table, set `layers` in `quality.json` to the site's real layers, and run the gate once. **Do not commit the result**: code written before the standard is expected to fail. Report the failures and let the user choose between fixing now and `pause <site>`.

## Conflicts
A template section the user changed: show both and ask (`08-updates.md` §4). A site whose repo already has its own lint or format config: show it, and ask whether the gate replaces it; never run two formatters on one file.

## Verify
- `{{W}}/templates/quality/` holds the six files and `node {{W}}/templates/quality/run-gate.mjs --help` exits 0.
- `quality-gate` appears in `hermes -p web-developer skills list`, `hermes -p web-deployer skills list` and `hermes -p web-reviewer skills list`.
- `osv-scanner --version` runs and the offline database exists in `{{ROOT}}/.cache/osv`.
- `plan_version` is `2` in `{{ROOT}}/projects/web/squad.yaml`.

## Rollback
Delete `{{W}}/templates/quality/` and `{{W}}/skills/common/quality-gate/`, restore the templates from the step 1 backup (`osv-scanner` and its cache stay; they are inert), set `plan_version` back to `1`. The sites' repos keep their copies: the gate stops being run and the files are inert.
