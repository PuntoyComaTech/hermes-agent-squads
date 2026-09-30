# How to contribute

> Rules for writing or changing plans in this repository. They apply to people and to any AI that edits the files.

## Rules

- **Planning in Markdown only.** No code is written here: scripts are described as prompts (`squads/<key>/05-scripts.md`, `base/07-builder.md` §6), and the builder writes them on each user's computer.
  - Exceptions: each squad's `squad.yaml` manifest, and `squads/*/reference/` (third-party material with its licenses, a source for our own skills).
- **Language:** plans are written in English; bots always talk to the user in the user's preferred language.
- **Header:** each file starts with a `>` block that says what it is and when it is used.
- **Prompts:** everything inside ```` ```markdown ```` blocks is prompt text that is copied as is.
- **Nothing personal:** each user's data are `{{...}}` variables that come from their profile. Examples use fictional people, and never sensitive data or real cases.
- **Nothing tied to one machine:** tools chosen from the best on the market, justified, installable on Mac, Windows and Linux, and lightweight (`base/01-principles.md` §1.8).
- **Hermes:** every claim about Hermes Agent is first verified in its official documentation (`NousResearch/hermes-agent`, `website/docs` folder).
- **Decisions:** every structural decision is recorded in `00-evaluation/02-decisions.md`. If it is debatable, its pros and cons go in a file in `00-evaluation/`.
- **Migrations:** every change to a base contract (folder layout, base `AGENTS.md`, a base bot's config or SOUL, `squad.yaml` schema, registry, installed state) ships a migration in `base/migrations/` (`base/08-updates.md` §6). A change to an official squad's contracts bumps its `plan_version` and ships a conditional migration.

## Naming conventions

One pattern everywhere, so any person or AI can find things without guessing.

| What | Pattern | Example |
| --- | --- | --- |
| Squad key | One short lowercase English word, reused in every row below | `jobs`, `marketing`, `web` |
| Squad plan folder | `squads/<key>/` | `squads/marketing/` |
| Squad files | Always the same seven Markdown files, numbered, plus `squad.yaml` | `README.md`, `01-personalization.md` ... `06-testing-and-operations.md` |
| Squad manifest | `squads/<key>/squad.yaml` (schema in `base/05-squad-template.md`) | `squads/web/squad.yaml` |
| Squad reference material | `squads/<key>/reference/` | `squads/marketing/reference/skills/` |
| Folder on the user's computer | `~/Hermes/projects/<key>/` | `~/Hermes/projects/jobs/` |
| Profiles (bots) | `<key>-<role>`; the base bots are `orchestrator` and `builder` | `jobs-writer`, `marketing-strategist` |
| Orchestration skill | `orchestration-<key>` | `orchestration-marketing` |
| Squad profile file | `<key>-profile.yaml` | `jobs-profile.yaml` |
| Migrations | `base/migrations/NNNN-<kebab-name>.md`, numbered in order | `0003-squad-manifests.md` |
| Evaluation documents | `00-evaluation/NN-<key>-<topic>.md`; shared ones have no key | `04-jobs-applier.md`, `02-decisions.md` |
| Folders, Markdown files, skills | `kebab-case` | `weekly-calendar`, `install-notes.md` |
| Scripts | `snake_case.py` | `plan_week.py` |
| Cron names (`crons[].name` in `squad.yaml`) | `kebab-case` | `start-search`, `weekly-summary` |
| YAML and JSON keys | `snake_case` | `approval_mode` |
| Modes and verdicts | `UPPERCASE` | `CALENDAR`, `APPROVED` |
| Statuses | `lowercase_snake_case` | `in_review` |
| Dates inside IDs | `YYYYMMDD` | `JOB-20260925-acme-data-analyst`, `cafe-luna-20261001-carousel-01` |
| Template variables | `{{snake_case}}` | `{{main_model}}` |

## Proposing a new squad

1. Open an *issue* with:
   - the purpose in two lines;
   - what reaches the user (for example, in jobs: "the link to the job opening and a CV made for it");
   - what the user decides and what is irreversible.
2. Design it with `base/05-squad-template.md`: the same 7 files plus `squad.yaml`, an automatic end-to-end Level 1 and at most 5 specialists, each with its reason to exist. A squad created with the builder already has this shape: the builder can open the PR for you.
3. Add its row to the squads table in `README.md` and its decisions to `00-evaluation/02-decisions.md`.

## Improving an existing squad

- If a contract changes (files, statuses, handoffs, consult pairs), update that squad's `squad.yaml`, architecture, bots, scripts and tests together, and bump `plan_version`.
- Something shared by all squads goes in `base/`, with its migration.
