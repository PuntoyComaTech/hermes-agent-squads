# 0006 · Jobs lowercase statuses

> Migration (`base/08-updates.md`). Run by the builder. Conditional: only if `jobs` is in `builder/installed.yaml`.

## What and why
Jobs statuses follow the naming rule in `CONTRIBUTING.md`: `lowercase_snake_case` (`in_preparation`, `manual_application`). Verdicts and results stay `UPPERCASE`: `filter`, `fit.decision`, review `verdict`, `submission.json` `result`, and modes. Converts the stored values and the installed templates that write them. Part of jobs `plan_version: 2` (`squads/jobs/squad.yaml`).

Mapping: `FOUND`, `DISCARDED`, `ANALYZED`, `IN_PREPARATION`, `IN_REVIEW`, `NOT_APPROVED`, `READY`, `DELIVERED`, `APPLYING`, `APPLIED`, `MANUAL_APPLICATION`, `SKIPPED`, `SCREENING`, `INTERVIEW`, `OFFER`, `REJECTED`, `CLOSED` → the same word in lowercase.

## Already applied if
`jobs` is not in `installed.yaml` (skip and record it), or the Verify checks pass and the installed jobs SOULs, `orchestration-jobs` and `scripts/deliver.py` write lowercase statuses.

## Steps
1. Pause the jobs crons (`hermes cron pause` for `start-search` and `deliver`) and wait until `hermes kanban list` shows no running jobs task.
2. Back up: `tar -czf {{ROOT}}/builder/backup-0006-<YYYYMMDD>.tar.gz -C {{ROOT}}/projects/jobs openings tracking.csv outbox` (the migration commit alone does not cover files in `.gitignore`).
3. Write a one-off script (not kept in `projects/jobs/scripts/`) that, with the mapping above:
   - in each `openings/*/status.json`, converts `status` and every `history[].status`;
   - in `tracking.csv`, converts only the `status` column;
   - in `outbox/ready/*.json` and `outbox/sent/*.json`, converts any `status` field.
   It changes only exact mapped values, never `filter`, `decision`, `verdict` or `result`, leaves lowercase values untouched (so a second run changes nothing), and prints the count of files changed. Run it with `--dry-run` first, show the counts, then run it.
4. Templates, with the three-way comparison (`08-updates.md` §4): each installed jobs `SOUL.md` from `plans/squads/jobs/03-bots.md` §2, `skills/orchestration/orchestration-jobs/SKILL.md` from §4 (or `skills/orchestration-jobs/` if `0005` was skipped), and `projects/jobs/AGENTS.md` if the user added a status there.
5. `scripts/deliver.py`: apply the status lines of `plans/squads/jobs/05-scripts.md` (writes `delivered`; the tracking status column copies `status.json`). Run its tests.
6. Resume the crons.

## Conflicts
A status outside the mapping (one the user or Hermes added): show it and ask for its lowercase name; never drop it. A template section the user changed: show both and ask (`08-updates.md` §4).

## Verify
- `rg -n '"status": *"[A-Z_]+"' {{ROOT}}/projects/jobs/openings {{ROOT}}/projects/jobs/outbox` finds nothing.
- The `status` column of `tracking.csv` has no uppercase value, and its `filter` and `decision` columns are unchanged.
- `rg -nw 'FOUND|DISCARDED|ANALYZED|IN_PREPARATION|IN_REVIEW|NOT_APPROVED|READY|DELIVERED|APPLYING|APPLIED|MANUAL_APPLICATION|SKIPPED|SCREENING|OFFER|REJECTED|CLOSED'` over the installed jobs `SOUL.md` files, `orchestration-jobs` and `scripts/deliver.py` finds nothing (`INTERVIEW` stays: it is also a writer mode).
- The next `deliver.py` run completes without errors and "how's my search going?" gets the same counts as before.

## Rollback
Restore the backup (`tar -xzf builder/backup-0006-<YYYYMMDD>.tar.gz -C {{ROOT}}/projects/jobs`), `git -C {{ROOT}} revert` the migration commit, `hermes profile import` the exported jobs profiles, resume the crons.
