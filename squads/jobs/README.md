# Squad: Job search

> Squad plan. Requires the base to be installed.
> Works for any occupation, country, language level and work mode: all of that comes from the questionnaire in [`01-personalization.md`](01-personalization.md).

## Purpose

The user **only receives messages with the link to an opening that fits and a CV made for that opening**. Everything else (searching, filtering, analyzing, writing, reviewing) runs on its own. They reply "apply" and, if the form is simple, the system applies for them; if not, it leaves everything ready so they can do it in a minute.

## What the user sees

```text
🟢 84/100 · Data analyst — Acme (remote in the region)
Apply: https://boards.greenhouse.io/acme/jobs/123
CV attached 📎 cv_ats.pdf
Reply: "apply" · "change: <what>" · "no"
JOB-20260925-acme-data-analyst
```

| Reply | What happens |
| --- | --- |
| `apply` | If the form is simple (no account or CAPTCHA), it fills it in, uploads the CV and submits → "✅ Applied" with a screenshot. If a piece of data is missing, it asks with buttons. If it can't, it sends the link and the answers ready to copy |
| `change: <what>` | New CV with the change, reviewed, in the same chat |
| `no` | The opening is discarded; if they say why, the searches improve |
| Any link | It analyzes it; if it fits, the CV arrives; if not, it says why in 2 lines |
| `I applied` · `they called me` · `rejected` | Tracking updated; if there is an interview, it offers to prepare it |
| `how's it going?` · `pause` · `resume` | Summary, or stop and restart the searches |

Also, if they want it, a summary every Monday.

## Levels

| Level | What it adds | When to move up |
| --- | --- | --- |
| **1 · Automatic** | Scheduled web search by the scout, full chain, delivery by messaging, applying with confirmation, weekly summary | — |
| **2 · More sources, less spend** | Ingest scripts that use job board APIs (no tokens) before the web search | When good openings are missing or the web search gets expensive |
| **3 · Learning** | Weekly tuning of search keywords, threshold and sources based on what gets replies; applying by email if the user connects their email account | With 6+ weeks of data |

## Bots

| Bot | Does | Why it is a separate bot |
| --- | --- | --- |
| `orchestrator` (base) | Talks with the user and handles their replies | Single point of contact |
| `jobs-scout` | Searches for openings, saves their text and applies the hard filter | Web and browser permissions for reading |
| `jobs-analyst` | Analyzes the opening before looking at the user's background, researches the company with a subagent and decides | Judgment separate from the search: it does not read web pages directly |
| `jobs-writer` | Writes the CV, cover letter and answers with verified achievements; generates PDF and DOCX | Terminal only for the script; never touches the web |
| `jobs-reviewer` | Reviews with 5 independent subagents and approves or asks for corrections | **Independence**: whoever writes never reviews |
| `jobs-applier` | With confirmation, fills in and submits simple forms | The only one allowed to submit, and the only one with form data |

They all use the same model: the `main_model` the user chose (see `base/03-user-profile.md`).

Why company research is not a bot: [`00-evaluation/03-jobs-company-research.md`](../../00-evaluation/03-jobs-company-research.md). Why the applier is: [`00-evaluation/04-jobs-applier.md`](../../00-evaluation/04-jobs-applier.md).

## Files in this plan

| File | Content |
| --- | --- |
| [`01-personalization.md`](01-personalization.md) | Questionnaire, achievements record, application data and resulting profile, with an example |
| [`02-architecture.md`](02-architecture.md) | Folders, automatic chain, data contracts, squad rules |
| [`03-bots.md`](03-bots.md) | Each bot's SOUL, skills, orchestration skill and weekly summary |
| [`04-installation.md`](04-installation.md) | Instructions for Hermes to install Level 1 |
| [`05-scripts.md`](05-scripts.md) | Scripts: scheduled search, delivery, CV render, links; ingest (Level 2) |
| [`06-testing-and-operations.md`](06-testing-and-operations.md) | Acceptance tests, operations, metrics and when to move up a level |
