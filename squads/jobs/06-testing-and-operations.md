# Testing and operations: job search

> Level 1 acceptance tests, daily operations, metrics and criteria for moving up a level.
> Used by the builder (installation STEP 10 and after every SOUL or skill change) and by the orchestrator, for tracking.

## 1. Acceptance tests (Level 1)

Run after installing and after every SOUL or skill change. Adjust the `{{}}` values to the user's profile.

### Automatic chain

| # | Test | Input | Expected result |
| --- | --- | --- | --- |
| A | Ideal opening | Link to an opening that matches the whole profile | A message arrives with link + CV; nothing before that |
| B | Language above the maximum | Opening that requires more than `max_required_language` | DISCARD in the filter; no analyst task is created; if the user asked for it, the orchestrator tells them why |
| C | Language not stated | Opening in a foreign language with no level | FLAG; if `analyze_flagged`, it continues and the message includes the warning "interview probably in <language>" |
| D | Geography | "Remote, {{other country}} residents only" | DISCARD before the analysis |
| E | Below the threshold | Opening with a mediocre fit | The analyst does not create the writer's task; no message arrives (it does appear in the summary) |
| F | Skill without an achievement | A must-have that is not in `achievements.yaml` | It is in `hard_gaps`; the CV does not mention it |
| G | Altered number | Manually raise a number in `cv_content.json` and relaunch the reviewer | Truthfulness FAIL; FIX; the writer corrects it; round 2 APPROVED |
| H | Two failed rounds | Force failures in rounds 1 and 2 | Status `not_approved`; no message arrives; it appears in the weekly summary |
| I | Daily quota | More approved openings than `max_deliveries_per_day` | The highest-scoring ones arrive; the rest arrive the next day |
| J | Outside the schedule | Opening approved in the middle of the night | `deliver.py` holds it until the user's schedule |
| K | Pause | "pause the search" | `outbox/PAUSE` exists; the cron creates no tasks; "resume" reverts it |
| L | Duplicate | The same opening found twice | A single folder and a single message |
| M | Scam or closed | Opening that asks for payment, or 404 | DISCARD, with a label |
| N | Blocked task | Delete a required field from the profile | The user receives "⚠️ … needs your answer"; once they reply, it continues |

### Replies and applying

| # | Test | Input | Expected result |
| --- | --- | --- | --- |
| O | Change | "change: put the experience at X first" | "✏️ CV updated" arrives with the change applied and reviewed |
| P | Change that makes things up | "change: say I led the team" (the achievement says "participated") | The orchestrator asks for the data or the reviewer rejects it; no CV with the false claim arrives |
| Q | Apply through a simple form | "apply" to an opening with a form that needs no account (use a test, or a real application with permission) | "✅ Applied" + screenshot; status `applied` |
| R | Missing data | Form with a question that is not in the data | Asks with buttons; after the reply, submits; offers to save the answer |
| S | Requires an account | "apply" on a job board with login | "I couldn't apply: it asks to create an account. Apply here…" + `kit.md`; status `manual_application` |
| T | No confirmation | Manually create an applier task without the confirmation phrase | The applier blocks and does not submit |
| U | Double "apply" | Reply "apply" twice | A single application |
| V | Ambiguous reply | "apply" with several delivered openings and no quote | The orchestrator asks which one, with options |
| W | LinkedIn | Paste a LinkedIn link | It looks for the opening on the company's website or asks for the text; it never opens LinkedIn |

### Direct consultation (`02-architecture.md` §7)

| # | Test | Input | Expected result |
| --- | --- | --- | --- |
| X | Applier asks the writer | "apply" on a simple form with an open question not in `answers.md` ("describe a project with SQL") | A `CONSULT · <ID> · ...` card for jobs-writer is the parent of the applier's card; the applier's card blocks with kind `dependency` and resumes on its own with the answer in `## Parent task results`; the answer cites verified achievements; `submission.json` records `consult:<card id>`; no message to the user |
| Y | Writer asks the analyst | Writer task whose `analysis.json` lacks the achievements for a must-have | CONSULT card for jobs-analyst; the analyst answers from `analysis.json` without changing it or opening another consultation; the writer continues |
| Z | Disallowed pair and limits | Reviewer task that would need an answer from the writer; a task needing 3 data | No CONSULT card for jobs-writer; at most 2 consultations per task; facts only the user has (salary) block with `needs_input` and `deliver.py` reports them |

## 2. Daily operations

| Moment | What happens | What the user does |
| --- | --- | --- |
| At each search time | The chain runs on its own | Nothing |
| When an opening is ready (within their schedule) | Link + CV arrives | "apply", "change: …" or "no" |
| They see an opening somewhere else | - | Pastes the link to the orchestrator |
| A company replies | - | "they called me from X" / "rejected by X" |
| Monday | The weekly summary arrives | Nothing, or adjusts what it suggests |

Weekly check (the builder, on request, 2 minutes): `hermes cron list` (no overdue jobs), `hermes kanban list --status blocked`, `hermes gateway status`. Overdue crons mean the computer slept or the gateway stopped: the user runs `hermes gateway restart`.

## 3. Metrics

The orchestrator records them every Monday in `orchestrator/metrics.md`:

| Metric | What it is for |
| --- | --- |
| Openings found / PASS / analyzed / PURSUE | Whether the filter is too strict or too loose |
| Applications sent vs `weekly_volume` | Whether the pace is the desired one |
| Response rate = (screening + interview) / applications | **The main metric** |
| Messages delivered vs "apply" / "no" | Whether what arrives interests them (if they say "no" a lot, the threshold or the filter is too loose) |
| Automatic vs manual applications, and NOT_POSSIBLE reasons | Whether it is worth improving the applier |
| Manual corrections per application | Quality of the writer and the reviewer |
| The user's discard reasons | Adjusting the profile and the filter |
| Token cost per application (from the Hermes logs) | Spend control |

## 4. When to move up a level (or adjust instead of moving up)

Review after 3-4 weeks of use:

| Symptom | Action |
| --- | --- |
| Acceptable response rate, and good openings are missing | Move up to **Level 2** (API ingest) |
| Many openings but few replies | Do not move up. Review the analysis and the writing: does the score predict replies? Does the CV communicate well? |
| The user asks for many "change:" edits | Strengthen `application-writing` and the hiring manager subagent; complete `achievements.yaml` |
| A specific review always fails (e.g., ATS) | Improve that subagent; if it does not improve, promote it to its own bot (`base/02-architecture.md` §7) |
| Many CONSULT cards for the same question | Add that datum to the contract of the bot that owns it |
| Many "no" replies for the same reason | Move that reason into the filter in `jobs-profile.yaml` |
| 6+ weeks of data and you want to know what works | Move up to **Level 3** (weekly strategy review) |

The builder applies level changes (`04-installation.md`, Maintenance). Structural changes to the plan go to `00-evaluation/02-decisions.md` through the upstream contribution loop (`base/07-builder.md`).
