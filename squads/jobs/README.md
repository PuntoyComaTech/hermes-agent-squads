# Squad: Jobs

`jobs` interviews the user, the cron starts searches, the chain filters, analyzes, writes, reviews and delivers a
CV with its link. The user replies `apply`, `change: <what>` or `no` in the lead's Bot Chat.

Board `jobs`. One search is one Hermes Project (`scripts/squadctl project add jobs <name> <path>`); its folder
holds the files of skill `jobs-contract`.

## Bots

| Bot | Lane | Does |
|---|---|---|
| `jobs` (lead) | lead | Profile interview, digests, apply/change/no decisions, tracking. Holds the personal data, no web |
| `jobs-scout` | research; analysis cards pinned to the review lane | Searches, applies the hard filter, saves the opening, then analyzes fit and the company |
| `jobs-writer` | copy | CV content, letter and answers from verified achievements; renders PDF, DOCX and ATS text |
| `jobs-reviewer` | review | Five independent lenses (truthfulness, ATS, recruiter, hiring manager, writing) and the verdict |
| `jobs-applier` | copy | Submits a simple form only after the user's explicit apply; otherwise writes a manual kit. Optional |

Only `jobs-writer` and `jobs-applier` read `contact.yaml`. `linkedin.com` is on the scout and applier website
blocklists.

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

Card fields and idempotency keys: skill `jobs-contract` step 4.

## Files

| Path | Content |
|---|---|
| `squad.yaml` | Manifest: bots, lanes, toolsets, skills, board, cron, chains |
| `souls/` | One SOUL per bot, 6 lines max |
| `skills/` | `jobs-contract` (shared), `leading-job-search`, `finding-jobs`, `analyzing-jobs`, `writing-applications`, `rendering-cv`, `preparing-interviews`, `reviewing-applications`, `submitting-applications` |
| `scripts/start_search.py` | Cron gate: one search card per slot, paused by `profile.md` -> `search: paused` |
| `skills/rendering-cv/scripts/render_cv.py` | Deterministic CV renderer: HTML, text, PDF, DOCX and `render_report.json` |

## Cron

Retime `jobs-search` in the builder's local overlay (`local/squads/jobs/squad.yaml` ->
`bots.jobs.cron.jobs-search.schedule`). It files nothing until the project and `profile.md` exist.

## Install notes

- `jobs-applier` is optional: leave it out (`scripts/squadctl apply jobs --bots jobs,jobs-scout,jobs-writer,jobs-reviewer`)
  and "apply" answers with the link plus the ready answers instead of a submission.
- PDF needs WeasyPrint (`pip install weasyprint`) or Chromium/Chrome, DOCX needs python-docx, and `--pages`
  needs `pdfinfo` (poppler). Without them the writer reports the gap; nothing is installed for the user.
- The community `job-search` plugin is searchable (`scripts/hpy catalog_search.py job-search`) and stays off by default.

## Rules

Skill `jobs-contract`.
