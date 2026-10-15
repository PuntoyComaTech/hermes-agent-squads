# How to contribute

> Rules for changing this repository. They apply to people and to any AI that edits the files. Read
> `AGENTS.md` first; its Rules apply here.

## Rules

- **Manifests follow the schema** (`squads/_schema/squad.schema.json`); cross-field rules (one lead, chain assignees
  exist, lanes exist, worker names prefixed by the squad key) are enforced by `squadctl` and `tests/`.
- **Tests and lint must stay green**: `python3 -m pytest` and `scripts/hpy skill_lint.py skills squads`.
- **Keep the tree clean before a local install**: `hermes profile install <path>` copies everything inside the
  distribution-owned paths (`skills/`, `scripts/`, `squads/`), `__pycache__` included; run `git clean -nXd` to
  preview, then `git clean -fXd`.

## Naming conventions

| What | Pattern | Example |
| --- | --- | --- |
| Squad key | One short lowercase English word, reused in every row below | `jobs`, `marketing`, `web` |
| Squad folder | `squads/<key>/` (`squad.yaml`, `souls/`, `skills/`, `scripts/`, `README.md`) | `squads/marketing/` |
| Profiles (bots) | `<key>-<role>`; the lead is `<key>`; the base bot is `builder` | `jobs-writer`, `web-frontend` |
| Builder skills | `<gerund>` in `skills/`, frontmatter `name` equal to the directory | `installing-squads` |
| Project folders | Anywhere the user keeps them; registered as native Projects, never assumed | `~/Projects/acme-site` |
| Scripts | `snake_case.py` | `plan_week.py` |
| Cron jobs | `<key>-<job>`, kebab-case | `web-watch`, `builder-watch` |
| YAML and JSON keys | `snake_case` | `approval_mode` |
| Statuses | `lowercase_snake_case` | `in_review` |

## Testing an install locally

`hermes profile install` accepts a local directory, so a change can be exercised end to end before it is
pushed, always against a throwaway root, never the real `~/.hermes`:

```bash
T=$(mktemp -d)
HERMES_HOME=$T hermes profile install . --name builder-test -y   # local dir source, no alias
HERMES_HOME=$T hermes profile update builder-test -y             # after an edit
HERMES_HOME=$T $T/profiles/builder-test/scripts/squadctl plan --self --builder builder-test
```

`apply <key>` needs a models file (`--models fixture.yaml`, the shape in `tests/fixtures`); keep the tree clean
before the install, and delete `$T` when done.

## Proposing a new squad

1. Open an *issue* with the purpose in two lines, what reaches the user (for example, in jobs: "the link to the
   opening and a CV made for it"), and what the user decides and what is irreversible.
2. Design it with the `designing-squads` skill: one visible lead, at most 5 bots (D-001), each with a reason
   to exist (a permission boundary, independence, another reasoning effort or context size), a chain and a
   board. The builder can open the PR for you.
3. Add its row to the squads table in `README.md`, its decisions to `docs/decisions.md`, and run the lint and the
   tests.

## Improving an existing squad

- A contract change (files, statuses, handoffs, chains) updates that squad's `squad.yaml`, skills, scripts, README
  and tests together, and bumps the squad `version`.
- Something shared by every squad (a lane, a script, a lint rule) goes in `scripts/` or `AGENTS.md`, with a decision
  in `docs/decisions.md`.
- A change to the layout (profiles, folders, state files) ships a migration: `scripts/migrate_v1.py` for v1 installs,
  a new script for anything later.
