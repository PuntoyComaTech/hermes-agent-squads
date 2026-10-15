# Squad: Marketing

A lead and four workers that run a brand's marketing cycle end to end: onboarding, a 90-day plan,
a weekly calendar, briefed and reviewed pieces, and a monthly report. Everything is filed as kanban
cards on the `marketing` board; the user approves, requests changes or discards from the lead's chat.
The squad never publishes, sends, schedules or spends without an explicit OK for that action.

## Bots

One visible lead (`marketing`) and four hidden workers (`marketing-research`, `marketing-creative`, `marketing-producer`, `marketing-reviewer`); lanes, skills and keeps: `squad.yaml`. Only the lead talks to the user.

## The piece chain

`scripts/squadctl chain marketing piece --project <slug> --title "<piece title>" --run-id <piece-id> [--when research]` files a
chain of dependent cards, the lead files the same cards with the kanban tools:

`research` (only when the brief needs it) -> `copy` -> `asset` -> `review` (one fix round) -> `approve`.

- Every card carries the project, the stage skill and the key `marketing:piece:<project>:<piece-id>:<stage>`.
- The reviewer returns `approve`, `fix` (one round, back to the owning stage, then a re-review) or `escalate`.
- The lead presents an approved piece in the user's chat; a change request starts a new round with the
  user's literal wording; discards and approvals are logged in `preferences.md`.
- A `publish` card exists only at Level 2, after the user confirms the specific action.

## Crons (lead, zero-LLM gates)

`marketing-plan-week` and `marketing-report`: schedules, scripts and delivery in `squad.yaml`. Each files at most one card per brand and period (`<job>:<project>:<period>`) and stays silent otherwise.

## Brand files

One brand is one Hermes Project; the project slug is the brand slug. File layout, rules and handoffs: `skills/brand-contract`. `brand.md` stays `draft` until the user approves the onboarding; only `active` brands are planned and reported.

## Skills

| Skill | Bot |
| --- | --- |
| `leading-marketing` | lead |
| `marketing-plan` | lead |
| `product-marketing` | lead |
| `marketing-council` | lead |
| `marketing-mindset` | lead |
| `researching-markets` | research |
| `writing-copy` | creative |
| `marketing-psychology` | creative |
| `producing-assets` | producer |
| `reviewing-marketing` | reviewer |
| `brand-contract` | all |

Licences and provenance: [skills/LICENSES.md](skills/LICENSES.md).

## Install

```sh
scripts/squadctl plan marketing        # read-only diff: profiles, skills, plugins, cron, board
scripts/squadctl apply marketing --models <file from scripts/hpy model_advisor.py>
```

`apply` creates the five profiles with `--no-skills`, copies the squad skills, enables the plugins
(`disk-cleanup`; `security-guidance` on the producer), creates the board and the two cron jobs; add
each brand with `squadctl project add marketing "<Brand>" <path>`.

## Scope

- What it does not do: publish, send, schedule, deploy or spend (the user does, or Level 2 adds it);
  full websites (web squad); long or 3D video (studio squad).
- Ad accounts, pixels and connectors are added per brand later; `connectors.suggest` in `squad.yaml`
  lists the connectors the squad can offer the user.
