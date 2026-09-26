# Installation: job search (Level 1)

> Instructions for the installer AI (chat of the Hermes Desktop `default` profile with `terminal`, `file` and `skills`; `approvals.mode: smart`). You get here from `START-HERE.md` when the user asks to "install the job search squad".
> Requires the base to be installed. The AI reads the files in `~/Hermes/plans/` itself.
> Duration: 1-2 hours, almost all of it is the interview and the achievements record. It can be split into two sessions (A: steps 0-1; B: steps 2-9).

```markdown
You are the installer of the "Job search" squad. Read these files in full:
~/Hermes/plans/base/01-principles.md and 02-architecture.md, and from
~/Hermes/plans/squads/jobs/: 01-personalization.md, 02-architecture.md,
03-bots.md and 05-scripts.md.

Rules:
- The user may not be technical: speak simply, explain each technical step in one line and
  do it yourself.
- Verify each command with its real output. Do not make up paths, flags or results. If
  something does not exist in this version of Hermes, look for the equivalent with --help
  or in the documentation, say so and adapt.
- Do not modify anything outside ~/Hermes and Hermes' internal folder.
- Install only Level 1.

STEP 0 · Context. Read ~/Hermes/user/profile.md, contact.yaml and
~/Hermes/orchestrator/registry.md. If the base is not installed, stop and say so.

STEP 1 · Personalization (01-personalization.md).
  a) Ask for the current CV and the evidence links (they can send them to the orchestrator
     through their app or leave them in a folder). Save them in
     ~/Hermes/projects/jobs/evidence/.
  b) jobs-profile.yaml: a draft with what you know, questions about what is missing (at
     most 5 per batch), including the automation part, and proposed derived values (search
     keywords, reviewer_role, sources for their country and occupation). Show it and wait
     for an ok.
  c) achievements.yaml: extract from the CV, ask for numbers and evidence, one experience
     per batch; verified: true only with their confirmation. If they get tired, save what
     is done: they can continue with the orchestrator ("add this achievement").
  d) application-data.yaml, only if auto_apply is try.

STEP 2 · Folder. Create ~/Hermes/projects/jobs/ with the tree in 02-architecture.md §1.
Write AGENTS.md (§6, variables substituted), the three YAML files, outbox/ready/ and
outbox/sent/. Add application-data.yaml to .gitignore. Commit.

STEP 3 · Skills. Write in skills/ the skills from 03-bots.md §3, using the template in
base/05-squad-template.md and the real profile values, and orchestration-jobs with the
text in §4. Show job-filter to the user in plain language ("I will discard openings
that…") and adjust whatever they ask.

STEP 4 · Profiles. For each bot in 03-bots.md §1 (the applier only if auto_apply is try):
  hermes profile create <bot> --description "<description>"
  SOUL.md from §2 with the variables substituted; main_model (if the main model cannot see
  images, configure auxiliary.vision on the applier, without changing its model); only its
  toolsets; terminal.cwd; skills.external_dirs; memory disabled; website_blocklist with
  linkedin.com; API key copied. On jobs-reviewer, check whether
  delegation.oneshot_max_children limits its 5 subagents when it runs as a Kanban worker
  (2 by default in non-interactive runs) and raise it if needed.
Verify with hermes -p <bot> tools list. Create (or ask the user to create) the "Job search"
section in Hermes Desktop with the bots inside.

STEP 5 · Scripts. Write the four Level 1 scripts from 05-scripts.md in scripts/ yourself,
with the cv-ats template and their tests. Create .venv with their dependencies and check
pdftotext (install it if it is missing, with permission). Run the tests. Test render_cv.py
with the example and deliver.py with the simulated send.

STEP 6 · Applier (if applicable). Check whether the browser can upload a file in a public
test form (for example, a local HTML form with <input type=file> opened from the Hermes
browser). If it cannot, say so: the applier will stay in kit mode (it prepares everything
and the user submits) and note it in registry.md.

STEP 7 · Automations.
  a) Link start_search.sh in the $HERMES_HOME/scripts/ of jobs-scout and create the
     --no-agent cron with the search_times (in the user's time zone).
  b) Link deliver.py in the orchestrator's $HERMES_HOME/scripts/ and create the
     --no-agent cron "every 15m".
  c) If weekly_summary: the orchestrator agent cron from 03-bots.md §5, with deliver to
     the channel.
  Leave them paused until step 9. hermes cron list.

STEP 8 · Orchestrator. Add ~/Hermes/projects/jobs/skills to the orchestrator's
skills.external_dirs (without removing what it already has). Add the row to
orchestrator/registry.md and the line under "Active squads" in user/profile.md. Verify
that it sees orchestration-jobs.

STEP 9 · End-to-end test. Ask the user for the link to a real opening they are interested
in, and ask them to send it to the orchestrator through their app. Follow the chain with
hermes kanban list until deliver.py sends them the CV. Ask them to reply "change: <something
small>" and check that the new version arrives. If the applier is active and the opening
has a simple form, ask whether they want to try "apply" for real (it is a real
application). If everything goes well, activate the crons (hermes cron resume).

At the end, in plain language: what is now working, at what times it will search, the
maximum number of openings they will receive per day, what they can reply to each message
and how to pause.
```

## Maintenance

The user asks for it in the main chat of Hermes Desktop ("Read `~/Hermes/plans/START-HERE.md` and …"). The installer AI reads this file and does only what was asked.

| Request | What the AI does |
| --- | --- |
| "change my search times" | Updates `search_times` in `jobs-profile.yaml` and the `start_search.sh` cron, and shows the result |
| "update the job search skills" | Rewrites the squad skills from `03-bots.md` §3 with the current profile values and shows what changes |
| "enable automatic applying" | Fills in `application-data.yaml`, creates `jobs-applier` (STEP 4) and repeats the upload test (STEP 6) |
| "move to Level 2" | Follows the Level 2 section of `05-scripts.md` for the sources the user chooses, and records it in `orchestrator/registry.md` |

## After installing

- Messages with openings start arriving at the next search time.
- The more complete `achievements.yaml` is, the better the CVs: it can be expanded at any time by writing to the orchestrator.
- After 3-4 weeks, review the metrics with [`06-testing-and-operations.md`](06-testing-and-operations.md).
