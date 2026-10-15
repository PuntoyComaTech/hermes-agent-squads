# Squad: Marketing

A lead and four workers that run a brand's marketing cycle end to end: onboarding, a 90-day plan,
a weekly calendar, briefed and reviewed pieces, and a monthly report. Everything is filed as kanban
cards on the `marketing` board; the user approves, requests changes or discards from the lead's chat.
The squad never publishes, sends, schedules or spends without an explicit OK for that action.

## Bots

| Bot | Role | Lane | What it does |
| --- | --- | --- | --- |
| `marketing` | lead | lead | Brand onboarding (`brand.md` per project), 90-day plan, calendar, briefs, chain filing, approvals, reports |
| `marketing-research` | worker | research | Dated, sourced market, competitor and ad-library evidence |
| `marketing-creative` | worker | copy | Concepts, all copy, scripts and art direction; no web |
| `marketing-producer` | worker | design | Statics, carousels, landings, emails, documents, short HyperFrames clips |
| `marketing-reviewer` | worker | review | Five lenses: brief fit, voice, claims, persuasion, format specs |

Workers are hidden in the Bots pane; only the lead talks to the user. Skills per bot live in
`squad.yaml`; the shared contracts are in `skills/brand-contract`.

## The piece chain

`squadctl chain marketing piece --project <slug> --title "<piece title>" [--when research]` files a
chain of dependent cards — or the lead files the same cards with the kanban tools:

`research` (only when the brief needs it) → `copy` → `asset` → `review` (one fix round) → `approve`.

- Every card carries the project, the stage skill and the key `<squad>:piece:<project>:<piece-id>:<stage>`.
- The reviewer returns `approve`, `fix` (one round, back to the stage that owns the issue) or `escalate`.
- The lead presents an approved piece in the user's chat; a change request starts a new round with the
  user's literal wording; discards and approvals are logged in `preferences.md`.
- A `publish` card exists only at Level 2, after the user confirms the specific action.

## Crons (lead, zero-LLM gates)

| Job | When | Script | Files a card only when |
| --- | --- | --- | --- |
| `marketing-plan-week` | Mondays 08:00 | `scripts/plan_week.py` | an active brand lacks next week's calendar |
| `marketing-report` | 1st of the month 08:00 | `scripts/report_gate.py` | a brand's analytics exports changed |

Both print one line when they file a card (delivered to the lead's Bot Chat) and stay silent
otherwise. Cards are keyed `<job>:<project>:<period>`, so re-runs never duplicate them.

## Brand files

One brand is one Hermes Project; the project slug is the brand slug. Inside the project folder:

```text
brand.md  DESIGN.md  preferences.md  PAUSE
plan/90-day.md
research/<date>-<topic>.md
calendar/<YYYY>-W<WW>.md
pieces/<piece-id>/          brief.md copy.md assets/ sources.md review.md
data/inbox/                 analytics exports, never edited
reports/<YYYY-MM>.md
```

`skills/brand-contract` holds the rules (claims need verified proof points, assets need a licence
line, `PAUSE` stops the automatic gates). `brand.md` stays `draft` until the user approves the
onboarding; only `active` brands are planned and reported.

## Skills

| Skill | Bot | Source |
| --- | --- | --- |
| `leading-marketing` | lead | this repo (squad orchestration and onboarding) |
| `marketing-plan` | lead | adapted from coreyhaines31/marketingskills (MIT), trimmed to the plan budget |
| `product-marketing` | lead | adapted from coreyhaines31/marketingskills (MIT) |
| `marketing-council` | lead | adapted from coreyhaines31/marketingskills (MIT); advisor dossiers in `references/` |
| `marketing-mindset` | lead | adapted from axelfreeman/marketing-mindset (MIT), trimmed; W11 junk removed |
| `researching-markets` | research | this repo |
| `writing-copy` | creative | this repo |
| `marketing-psychology` | creative | adapted from coreyhaines31/marketingskills (MIT), trimmed |
| `producing-assets` | producer | this repo |
| `reviewing-marketing` | reviewer | this repo |
| `brand-contract` | all | this repo (file layout, claims, handoffs) |

Licences and provenance: [skills/LICENSES.md](skills/LICENSES.md).

Keeps installed beside the squad skills: `official:creative/social-media-content-calendar`,
`official:productivity/decision-questionnaire` (lead); `bundled:competitor-news-monitor`,
`bundled:blocked-page-recovery`, `official:social-media/reddit-reading`, `official:research/scrapling`
(research); `bundled:humanizer` (creative); `bundled:claude-design`, `bundled:design-md`,
`official:creative/impeccable`, `official:creative/hyperframes` (producer).

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
  lists what the lead and the research worker can offer the user.
