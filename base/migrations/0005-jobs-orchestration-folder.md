# 0005 · Jobs orchestration folder

> Migration (`base/08-updates.md`). Run by the builder. Conditional: only if `jobs` is in `builder/installed.yaml`.

## What and why
Moves `orchestration-jobs` from `projects/jobs/skills/orchestration-jobs/` to `projects/jobs/skills/orchestration/orchestration-jobs/` and points the orchestrator at `projects/jobs/skills/orchestration`. With the old layout the orchestrator read `projects/jobs/skills`, so it also loaded every jobs specialist skill (job-filter, application-writing...). The specialists keep `skills.external_dirs: [{{ROOT}}/projects/jobs/skills]`. Part of jobs `plan_version: 2` (`squads/jobs/squad.yaml`).

## Already applied if
`jobs` is not in `installed.yaml` (skip and record it), or `projects/jobs/skills/orchestration/orchestration-jobs/SKILL.md` exists, `projects/jobs/skills/orchestration-jobs/` does not, and `hermes -p orchestrator config get skills.external_dirs` lists `{{ROOT}}/projects/jobs/skills/orchestration` and not `{{ROOT}}/projects/jobs/skills`.

## Steps
1. `mkdir -p {{ROOT}}/projects/jobs/skills/orchestration`, then `mv {{ROOT}}/projects/jobs/skills/orchestration-jobs {{ROOT}}/projects/jobs/skills/orchestration/`. Move only that folder: the specialist skills stay in `projects/jobs/skills/`.
2. In `projects/jobs/squad.yaml`, set `orchestration_skills: skills/orchestration`. Leave every `bots[].skills_dirs` as `[skills]`.
3. Run `python {{ROOT}}/scripts/registry.py` and apply the list it prints with `hermes -p orchestrator config set skills.external_dirs '<list>'`.
4. Add a line to `builder/changelog.md`.

## Conflicts
If `projects/jobs/skills/orchestration/` already exists with other skills the user added, keep them and tell the user the orchestrator now reads them. If the orchestrator's `skills.external_dirs` has entries not printed by `registry.py`, show them and ask whether to keep them.

## Verify
- `hermes -p orchestrator skills list` shows `orchestration-jobs` and none of `job-filter`, `job-analysis`, `company-profile`, `application-writing`, `cv-render`, `interview-prep`, `application-review`, `form-applying`.
- `hermes -p jobs-writer skills list` still shows `application-writing`, `cv-render` and `interview-prep` (same check for each installed jobs bot and its skills in `squads/jobs/03-bots.md` §1).
- Sending "how's my search going?" to the orchestrator gets the tracking summary.

## Rollback
`git -C {{ROOT}} revert` the migration commit; `hermes profile import` the exported orchestrator profile.
