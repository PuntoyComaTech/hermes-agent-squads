# Updating an installation

> Base prompt. How an installed `~/Hermes` receives changes to the plans without losing personalization.
> Run by the builder's `update-installation` skill. If the builder does not exist yet, the Hermes Desktop `default` session runs this file: migration `0004-builder` creates the builder, which does the rest.

## 1. Installed state: `{{ROOT}}/builder/installed.yaml`

```yaml
plans_commit: 42b5718          # commit of plans/ installed last
date: 2026-09-30
migrations_applied: [0001-installed-state, 0002-direct-consult]
squads:
  jobs:      {source: official, plan_version: 1, commit: 42b5718}
  marketing: {source: official, plan_version: 1, commit: 42b5718}
```

A clean base install (`06-base-installation.md`) writes it with every migration marked applied. Installations without it start with `0001-installed-state`.

## 2. Migrations

`plans/base/migrations/NNNN-<kebab-name>.md`, applied in number order. Each is a prompt with these sections: **What and why**, **Already applied if** (idempotent check), **Steps**, **Conflicts**, **Verify**, **Rollback**.

Migrations cover the base and, conditionally, the contracts of installed official squads (a step for a squad that is not installed is skipped). Official squads jobs, marketing and web are examples; users build their own with the builder, and migrations never touch `{{ROOT}}/squads/`.

## 3. What is never overwritten

- `user/`.
- Squad working data in `projects/*/`: profiles, brands, sites, openings, outputs.
- Memories, `.env` files, crons the user added.
- Skills Hermes created on its own (any skill not produced by a plan).
- The user's own squads in `{{ROOT}}/squads/`.

## 4. Files generated from a plan template

`SOUL.md`, `AGENTS.md` and plan skills get a three-way comparison per section:

| Base (original template) | Ours (user's current file) | Theirs (new template) |
| --- | --- | --- |
| `git -C plans show <installed commit>:<path>` | the installed file | `plans/<path>` after `git pull` |

- Section untouched by the user or Hermes (ours = base): apply the new template.
- Section changed by the user or by Hermes: show both in plain language and ask which to keep, or propose a merge.
- Never replace a whole file.

## 5. Procedure

1. Note the current commit (`git -C plans rev-parse HEAD`), then `git pull` in `plans/`. List migrations not in `migrations_applied`.
2. For each, in order:
   1. Run its "Already applied if" check. If applied, record it and move on.
   2. Summarize in plain language what it changes; wait for the user's ok. The user can stop anytime.
   3. Commit in `{{ROOT}}` and `hermes profile export` every profile it touches.
   4. Apply its steps, resolving conflicts with §4.
   5. Run its verification. On failure, run its rollback and stop.
   6. Append it to `migrations_applied`; update `plans_commit`, `date` and the affected squads' `commit` and `plan_version`. Commit.
3. Final summary: what changed, what the user decided, anything pending.

## 6. Writing a migration (contributors)

Every change to a base contract (folder layout, `AGENTS.md`, a base bot's config or SOUL, `squad.yaml` schema, registry, installed state) ships a migration. A change to an official squad's contracts bumps its `plan_version` and ships a conditional migration. Keep each one small and idempotent.
