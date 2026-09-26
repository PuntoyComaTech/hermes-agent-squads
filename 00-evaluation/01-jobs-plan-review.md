# Review of the "Hermes Career Fleet" plan

2026-09-25 · Plan reviewed: an earlier plan with 19 bots, 7 scripts and a Kanban graph per job opening, built for a single person (not included in this repository)

> **Update (same day):** after reviewing it, the design became **automatic by default** (D-006), with a fifth specialist for applying (D-009). Point 3 ("the user chooses first") and the "never submit" limit in this review were replaced; see `02-decisions.md`.

## Verdict

**The principles are good and the architecture is too big for the problem.** A person looking for a job needs between 5 and 20 good applications per week. Nineteen bots coordinated through Kanban is the architecture of a recruiting operation, not of an individual job search.

Recommendation: keep the principles and the data contracts, and cut down to **1 orchestrator + 4 specialists** in the job search squad. The other 15 roles become skills, subagents or scripts. Growth happens by levels, only if the numbers justify it.

## What to keep (what actually produces good results)

| Plan idea | Why it's worth it | Where it lives in the new design |
| --- | --- | --- |
| Record of verified achievements (claims) with evidence | It is what prevents making things up. It is the core asset of the whole squad | `jobs/achievements.yaml`, read by the analyst, the writer and the reviewer |
| Analyze the job opening before looking at the CV | Keeps the CV from being "read into" the opening | Mandatory step 1 for the analyst, with no access to achievements in that step |
| Whoever writes does not review their own work | It is the biggest jump in quality | Writer bot ≠ reviewer bot |
| Cheap filter before expensive models | Keeps spending in check | Filter rules in the scout with a cheap model |
| REJECT / WATCH / PURSUE | Explicit, auditable decision | The analyst's output |
| Cap on correction rounds, then a human | Prevents infinite loops | At most 1 automatic correction, then the user decides |
| Never submit the application automatically | Reputational and legal risk | Base rule |
| Scripts for deterministic work | Zero tokens, no LLM errors | CV rendering, API ingest, link checking |
| LinkedIn not automated | Its terms forbid it | Only URLs the user pastes |

## What to simplify and why

### 1. 19 bots → 5

Applying the rule "a bot only if it needs independence, different permissions, a different model, or does not fit in context" (see [`base/01-principles.md`](../base/01-principles.md)):

| Bots in the original plan | Become | Reason |
| --- | --- | --- |
| `career-director` | **orchestrator** (base, shared by all squads) | You enter a single chat; it knows all the flows |
| `job-scout`, `job-triage` | **jobs-scout** | Same permissions (web); the filter is a skill with fixed rules |
| `company-researcher`, `jd-analyst`, `evidence-librarian`, `fit-analyst` | **jobs-analyst** | They read the same things and produce a single decision. The "opening before CV" independence is achieved through the order of the steps (or a blind subagent), not with 4 bots |
| `positioning-strategist`, `portfolio-curator`, `resume-writer`, `application-writer`, `resume-architect` | **jobs-writer** | They all write the same story; splitting them forces the context to be passed through files 5 times |
| `truth-auditor`, `ats-auditor`, `editorial-qa`, `recruiter-reviewer`, `hiring-manager-reviewer`, `quality-chair` | **jobs-reviewer** with 4 to 5 subagents in parallel | Independence is kept: each subagent starts with a clean context and none of them wrote the CV |
| `career-strategist` | Weekly orchestrator skill (Level 3) | It only makes sense with weeks of data |
| `document-engineer`, `career-reporter`, `job-integrity` | Scripts (the plan already said so) | Deterministic |

### 2. The Kanban graph with a "director at every boundary" → a linear chain with guards

The plan needed the director between every stage because Kanban has no conditional branches. That is ~6 extra runs of a premium model per opening just to coordinate. In the new design the orchestrator creates the whole chain at once (analyst → writer → reviewer) and each specialist starts with a **guard**: if the previous stage said REJECT, it closes the task in one line without spending anything.

### 3. Automatic discovery from day 1 → the user chooses first

The plan processed every new opening all the way to the end. In Level 1 the scout delivers a **short filtered list** and the user chooses which ones to pursue. It is cheaper, gives control and produces the most valuable data point: which openings the user really cares about.

### 4. A plan built for one person → a template for anyone

The plan hard-coded the occupation, language level, region, hardware and sources of one specific person. In the new design all of that comes from a questionnaire and is stored in `jobs/jobs-profile.yaml`.

## Risks of the original plan that are avoided

| Risk | With 19 bots | With 5 |
| --- | --- | --- |
| Cost per opening | ~20 agent runs, 8 of them premium | 3 to 4 runs + cheap reviewer subagents |
| Points of failure | Orphaned cards, 19 SOULs to maintain, context lost across 15 handoffs | 3 handoffs, 5 SOULs |
| Time to first result | Phases 0-5, weeks | Level 1 in one day |
| Debugging | Which of the 19 bots failed? | The chain is linear and each step leaves a file |
| Adapting to another person | Rewrite templates, sources and reviewers | Fill in the questionnaire |

## What is lost by simplifying (and how to get it back if needed)

- **Per-opening parallelism** (research, JD and evidence at the same time). It comes back with subagents inside the analyst if time matters.
- **Fine-grained reviewer specialization.** If a specific review (for example ATS) is consistently weak, that subagent is promoted to its own bot. The criterion is in [`base/02-architecture.md`](../base/02-architecture.md).
- **24/7 automation.** It is Level 2-3 of the squad; it is turned on once Level 1 already produces applications that reach an interview.

## How we will know whether it works

Metrics the orchestrator records from Level 1 on, which decide whether to move up a level:

- openings reviewed per week and how many the user chooses to pursue;
- applications submitted;
- response rate (screening or interview / applications);
- corrections the user had to make by hand on each CV;
- token cost per application.

If after 3-4 weeks the response rate is acceptable and the bottleneck is finding openings, Level 2 (automatic ingest) is turned on. If the bottleneck is CV quality, the reviewer is strengthened. Not before.
