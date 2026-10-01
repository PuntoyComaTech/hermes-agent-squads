# Installation: job search (Level 1)

> The builder runs this with its `squad-install` skill (`base/07-builder.md`) when the user asks it to "install the job search squad". Requires the base.
> Duration: 1-2 hours, mostly the interview and the achievements record. It can be split into two sessions (A: steps 0-1; B: steps 2-10).

```markdown
You are the builder installing the "Job search" squad (squad-install skill). Read in
full: ~/Hermes/plans/base/01-principles.md, 02-architecture.md and 07-builder.md, and
from ~/Hermes/plans/squads/jobs/: squad.yaml, 01-personalization.md,
02-architecture.md, 03-bots.md and 05-scripts.md.

Rules:
- The user may not be technical: speak simply, explain each technical step in one line and
  do it yourself.
- Verify each command with its real output. Do not make up paths, flags or results. If
  something does not exist in this Hermes version, find the equivalent in
  ~/Hermes/.cache/hermes-docs (git pull first) or with --help, say so and adapt.
- Do not modify anything outside ~/Hermes and Hermes' internal folder.
- Install only Level 1.

STEP 0 · Context. Read ~/Hermes/user/profile.md, contact.yaml,
~/Hermes/orchestrator/registry.md and ~/Hermes/builder/installed.yaml. If the base is not
installed, stop and say so. If jobs is already in installed.yaml, stop: this is an update
(base/08-updates.md), not an install.

STEP 1 · Personalization (01-personalization.md).
  a) Ask for the current CV and the evidence links (they can send them to you or to the
     orchestrator, or leave them in a folder). Save them in ~/Hermes/projects/jobs/evidence/.
  b) jobs-profile.yaml: a draft with what you know, questions about what is missing (at
     most 5 per batch), including the automation part, and proposed derived values (search
     keywords, reviewer_role, sources for their country and occupation). Show it and wait
     for an ok.
  c) achievements.yaml: extract from the CV, ask for numbers and evidence, one experience
     per batch; verified: true only with their confirmation. If they get tired, save what
     is done: they can continue with the orchestrator ("add this achievement").
  d) application-data.yaml, only if auto_apply is try.

STEP 2 · Folder and manifest. Create ~/Hermes/projects/jobs/ with the tree in
02-architecture.md §1. Write AGENTS.md (§6, variables substituted), the three YAML files,
outbox/ready/ and outbox/sent/. Add application-data.yaml to .gitignore.
Write ~/Hermes/projects/jobs/squad.yaml from plans/squads/jobs/squad.yaml: source
official, the plan's plan_version, level 1, the start_search schedule from search_times.
If auto_apply is never: remove jobs-applier from bots and its consult pair. If
weekly_summary is false: remove the weekly-summary cron. Commit.

STEP 3 · Skills. Write in skills/ the skills from 03-bots.md §3, using the template in
base/05-squad-template.md and the real profile values, and orchestration-jobs with the
text in §4 in skills/orchestration/ (the only folder the orchestrator reads). Show job-filter to the user in plain language ("I will discard openings
that...") and adjust whatever they ask.

STEP 4 · Models. List the models available on the user's Hermes connection (method in
base/07-builder.md; never invent model names). Show one table: bot, recommended model
(main_model for every jobs bot), recommended reasoning effort, the user's choice. "Same
model for all" is a valid answer. Record model and reasoning_effort per bot in
projects/jobs/squad.yaml.

STEP 5 · Profiles. For each bot in squad.yaml:
  hermes profile create <bot> --description "<description from 03-bots.md §1>"
  SOUL.md from 03-bots.md §2 with the variables substituted; the chosen model and
  agent.reasoning_effort (hermes -p <bot> config set); if the applier's model cannot see
  images, auxiliary.vision on the applier, model unchanged; only its toolsets, and its
  disabled_toolsets in agent.disabled_toolsets; terminal.cwd; skills.external_dirs;
  memory disabled; website_blocklist with linkedin.com; API key copied. On jobs-reviewer,
  check whether delegation.oneshot_max_children limits its 5 subagents when it runs as a
  Kanban worker (2 by default in non-interactive runs) and raise it if needed.
Verify with hermes -p <bot> tools list. Tell the user to create the "Job search" section
in Hermes Desktop and which bots go inside.

STEP 6 · Scripts. Write the four Level 1 scripts from 05-scripts.md in scripts/, with the
cv-ats template and their tests. Create .venv with their dependencies and check pdftotext
(install it with permission if missing). Run the tests. Test render_cv.py with the example
and deliver.py with the simulated send.

STEP 7 · Applier (if installed). Check whether the browser can upload a file in a test
form (for example, a local HTML form with <input type=file> opened from the Hermes
browser). If it cannot, say so: the applier stays in kit mode (it prepares everything and
the user submits); note it in squad.yaml (does) so the registry shows it.

STEP 8 · Automations, from squad.yaml crons.
  a) Create $HERMES_HOME/scripts/ of jobs-scout if missing, copy start_search.sh into it
     (copy, don't link: Windows) and create the --no-agent cron with the search_times (in
     the user's time zone).
  b) The same for deliver.py in the orchestrator's $HERMES_HOME/scripts/, with the
     --no-agent cron "every 15m".
  c) If weekly_summary: the orchestrator agent cron from 03-bots.md §5, with deliver to
     the channel.
  Leave them paused until step 10. `hermes -p <profile> cron list` (per profile; without `-p` it
  lists only the default one), then `hermes cron doctor`.

STEP 9 · Registry and orchestrator. Run python ~/Hermes/scripts/registry.py: it
regenerates orchestrator/registry.md and prints the orchestrator's skills.external_dirs
list. Apply that list with hermes -p orchestrator config set and verify with
hermes -p orchestrator skills list that it sees orchestration-jobs and none of the
specialists' skills (job-filter, application-writing...). Add the line under "Active squads" in
user/profile.md. Record jobs in builder/installed.yaml ({source: official, plan_version,
commit: the plans commit}) and a line in builder/changelog.md. If a change needs a gateway
restart, ask the user in one line to run hermes gateway restart, then verify.

STEP 10 · End-to-end test. Ask the user for the link to a real opening they are
interested in and to send it to the orchestrator through their app. Follow the chain with
hermes kanban list until deliver.py sends them the CV. Ask them to reply "change:
<something small>" and check that the new version arrives. If the applier is active and
the opening has a simple form, ask whether they want to try "apply" for real (it is a
real application). If everything goes well, resume the crons (hermes cron resume).

At the end, in plain language: what works, at what times it searches, the maximum number
of openings per day, what they can reply to each message and how to pause. Append any
plan defect or installation trap you found to builder/upstream-notes.md.
```

## Maintenance

The user asks the builder (its chat or channel); the orchestrator forwards configuration requests to it. The builder does only what was asked, verifies, and records it in `builder/changelog.md`.

| Request | What the builder does |
| --- | --- |
| "change my search times" | Updates `search_times` in `jobs-profile.yaml`, the `start-search` cron and its schedule in `projects/jobs/squad.yaml`; shows the result |
| "update the job search skills" | Rewrites the squad skills from `03-bots.md` §3 with the current profile values and shows what changes |
| "change the model of <bot>" | Lists available models, applies model and `agent.reasoning_effort` with `hermes -p <bot> config set`, updates `squad.yaml` |
| "enable automatic applying" | Fills in `application-data.yaml`, adds `jobs-applier` and its consult pair to `squad.yaml`, runs STEP 5 for it, repeats the upload test (STEP 7) and `registry.py` |
| "move to Level 2" | Follows the Level 2 section of `05-scripts.md` for the sources the user chooses, adds the ingest crons and `level: 2` to `squad.yaml`, runs `registry.py` |
| "update my installation" | `base/08-updates.md` |

## After installing

- Openings start arriving at the next search time.
- The more complete `achievements.yaml` is, the better the CVs: the user expands it by writing to the orchestrator.
- After 3-4 weeks, review the metrics with [`06-testing-and-operations.md`](06-testing-and-operations.md).
