# 0001 · Installed state

> Migration (`base/08-updates.md`). Run by the `default` session when there is no builder yet, otherwise by the builder.

## What and why
Creates `{{ROOT}}/builder/` and `builder/installed.yaml` by inspecting what exists. Installations made before the builder have no record of what is installed, so later migrations cannot know what to skip.

## Already applied if
`{{ROOT}}/builder/installed.yaml` exists and lists `0001-installed-state` in `migrations_applied`.

## Steps
1. If `plans/` is not a git clone (a copied folder), move it to `plans.old/`, `git clone https://github.com/PuntoyComaTech/hermes-agent-squads.git {{ROOT}}/plans`, and delete `plans.old/` after the user's ok.
2. Installed commit: the commit noted before the pull (`08-updates.md` §5). If unknown, find the newest commit of `plans/` whose templates match the installed `SOUL.md` files (`git -C plans log`), or write `unknown`.
3. Create `builder/` with `changelog.md`, `upstream-notes.md` and `skills/`.
4. Detect installed squads: each `projects/<key>/` with a matching `hermes profile list` prefix. For each: `source: official` if `plans/squads/<key>/` exists, `plan_version: 1`, `commit` = the installed commit.
5. Write `installed.yaml` (schema in `08-updates.md` §1) with `migrations_applied: [0001-installed-state]`.

## Conflicts
If a folder in `projects/` has no matching profiles, or profiles have no folder, list them and ask whether they are installed. With `commit: unknown`, every template section counts as changed by the user in later migrations (ask, never apply silently).

## Verify
`installed.yaml` parses as YAML and lists every installed squad; `git -C plans status` works.

## Rollback
Delete `builder/`; restore `plans.old/` if step 1 ran.
