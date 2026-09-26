# How to contribute

> Rules for writing or changing plans in this repository. They apply to people and to any AI that edits the files.

## Rules

- **Planning in Markdown only.** No code is written here: scripts are described as prompts in `squads/<x>/05-scripts.md`, and the installer AI writes them on each user's computer.
  - Only exception: `squads/*/reference/`, which keeps third-party material (skills with their scripts and licenses) as a source for writing our own skills.
- **Language:** plans are written in English; bots always talk to the user in the user's preferred language.
- **Header:** each file starts with a `>` block that says what it is and when it is used.
- **Prompts:** everything inside ```` ```markdown ```` blocks is prompt text that is copied as is.
- **Nothing personal:** each user's data are `{{...}}` variables that come from their profile. Examples use fictional people, and never sensitive data or real cases.
- **Nothing tied to one machine:** tools chosen from the best on the market, justified, installable on Mac, Windows and Linux, and lightweight (`base/01-principles.md` §1.8).
- **Hermes:** every claim about Hermes Agent is first verified in its official documentation (`NousResearch/hermes-agent`, `website/docs` folder).
- **Decisions:** every structural decision is recorded in `00-evaluation/02-decisions.md`. If it is debatable, its pros and cons go in a file in `00-evaluation/`.

## Naming conventions

One pattern everywhere, so any person or AI can find things without guessing.

| What | Pattern | Example |
| --- | --- | --- |
| Squad key | One short lowercase English word, reused in every row below | `jobs`, `marketing` |
| Squad plan folder | `squads/<key>/` | `squads/marketing/` |
| Squad files | Always the same seven, numbered | `README.md`, `01-personalization.md` … `06-testing-and-operations.md` |
| Squad reference material | `squads/<key>/reference/` | `squads/marketing/reference/skills/` |
| Folder on the user's computer | `~/Hermes/projects/<key>/` | `~/Hermes/projects/jobs/` |
| Profiles (bots) | `<key>-<role>` | `jobs-writer`, `marketing-strategist` |
| Orchestration skill | `orchestration-<key>` | `orchestration-marketing` |
| Squad profile file | `<key>-profile.yaml` | `jobs-profile.yaml` |
| Evaluation documents | `00-evaluation/NN-<key>-<topic>.md`; shared ones have no key | `04-jobs-applier.md`, `02-decisions.md` |
| Folders, Markdown files, skills | `kebab-case` | `weekly-calendar`, `install-notes.md` |
| Scripts | `snake_case.py` | `plan_week.py` |
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
2. Design it with `base/05-squad-template.md`: the same 7 files, an automatic end-to-end Level 1 and at most 5 specialists, each with its reason to exist.
3. Add its row to the squads table in `README.md` and its decisions to `00-evaluation/02-decisions.md`.

## Improving an existing squad

- If a contract changes (files, statuses, handoffs), update that squad's architecture, bots, scripts and tests at the same time.
- If something shared by all squads changes, it goes in `base/`.
