# Squad: Jobs

Job search that runs on its own: `jobs` interviews the user, the cron starts searches, the chain filters, analyzes,
writes, reviews and delivers a CV with its link. The user replies `apply`, `change: <what>` or `no` in the lead's
Bot Chat and nothing else is asked of them.

Board `jobs` (💼). One squad serves one search: a Hermes Project (created by the builder with
`squadctl project add jobs <name> <path>`) holds `profile.md`, `achievements.yaml`, `contact.yaml`,
`application-data.yaml`, `openings/`, `companies/` and `searches/`. Formats: skill `jobs-contract`.

## Bots

| Bot | Lane | Does |
|---|---|---|
| `jobs` (lead) | lead | Profile interview, digests, apply/change/no decisions, tracking. Holds the personal data, no web |
| `jobs-scout` | research; analysis cards pinned to the review lane | Searches, applies the hard filter, saves the opening, then analyzes fit and the company |
| `jobs-writer` | copy | CV content, letter and answers from verified achievements; renders PDF, DOCX and ATS text |
| `jobs-reviewer` | review | Five independent lenses (truthfulness, ATS, recruiter, hiring manager, writing) and the verdict |
| `jobs-applier` | copy | Submits a simple form only after the user's explicit apply; otherwise writes a manual kit. Optional |

Only `jobs-writer` (CV header) and `jobs-applier` (forms) read `contact.yaml`; only `jobs-applier` reads
`application-data.yaml`. The scout never sees contact data, and `linkedin.com` is on its website blocklist.

## Flow

```mermaid
flowchart LR
  cron[cron jobs-search] --> scout["jobs-scout: search + hard filter"]
  scout -->|PASS opening| analyze["jobs-scout on the review lane: analysis"]
  analyze -->|PURSUE at or above apply_threshold| writer["jobs-writer: CV, letter, answers"]
  writer --> reviewer["jobs-reviewer: 5 lenses"]
  reviewer -->|FIX once| writer
  reviewer -->|APPROVED| digest["jobs: digest to the user"]
  digest -->|user says apply| applier["jobs-applier: submit or manual kit"]
```

Every card carries the opening id (`JOB-YYYYMMDD-company-role`), the project and paths, and an idempotency key
(`jobs:application:<project>:<ID>:<stage>`), so a rerun never duplicates a stage. Each opening ends in
`openings/<ID>/status.json`, append only.

## Files

| Path | Content |
|---|---|
| `squad.yaml` | Manifest: bots, lanes, toolsets, skills, board, cron, chains |
| `souls/` | One SOUL per bot, 6 lines max |
| `skills/` | `jobs-contract` (shared), `leading-job-search`, `finding-jobs`, `analyzing-jobs`, `writing-applications`, `rendering-cv`, `preparing-interviews`, `reviewing-applications`, `submitting-applications` |
| `scripts/start_search.py` | Cron gate: one search card per slot, paused by `profile.md` -> `search: paused` |
| `skills/rendering-cv/scripts/render_cv.py` | Deterministic CV renderer: HTML, text, PDF, DOCX and `render_report.json` |

## Cron

`jobs-search` runs `start_search.py` on the lead (`squad.yaml` -> `bots.jobs.cron.jobs-search`); it files one
search card per slot and pauses while `profile.md` says `search: paused`. Retime it in the builder's local
overlay (`local/squads/jobs/squad.yaml` -> `bots.jobs.cron.jobs-search.schedule`).

## Install notes

- The builder installs the squad and asks for the models per lane; nothing here hard-codes one.
- `jobs-applier` is optional: leave it out (`scripts/squadctl apply jobs --bots jobs,jobs-scout,jobs-writer,jobs-reviewer`)
  and "apply" answers with the link plus the ready answers instead of a submission.
- Rendering needs no dependency for HTML and text; PDF takes WeasyPrint (`pip install weasyprint`) or
  Chromium/Chrome, DOCX takes python-docx, and `pdfinfo` (poppler) lets the report enforce `--pages`. Without an
  engine the report says so and the writer reports it: nothing is installed behind the user's back.
- The community `job-search` plugin is searchable (`scripts/hpy catalog_search.py job-search`) and stays off by default.

## Rules

Skill `jobs-contract`.
