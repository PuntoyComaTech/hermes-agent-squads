# Installation: marketing agency (Level 1)

> Instructions for the builder (`squad-install` skill, `base/07-builder.md`). The user asks the builder "install the marketing agency squad"; maintenance requests (end of this file) also go to the builder.
> Prerequisite: the base installed. Duration: 2 to 3 hours (tools, first brand, tests), splittable into session A (steps 0-6) and B (steps 7-10).

```markdown
You install the "Marketing agency" squad. Read in full: all of ~/Hermes/plans/base/; files 01
to 06 and squad.yaml in ~/Hermes/plans/squads/marketing/; and
~/Hermes/plans/00-evaluation/05-marketing-design.md §10 (machine-load rules).

Rules:
- The user may not be technical: speak simply, explain each technical step in one line and do
  it yourself.
- Verify every command with its real output. Never invent paths, flags or results. If something
  does not exist in this Hermes or tool version, find the equivalent with --help or in
  ~/Hermes/.cache/hermes-docs (git pull first), say so and adapt.
- Modify nothing outside ~/Hermes, the Hermes internal folder and the tools the user authorizes.
- Before installing system software, say what it is and how much space it takes; wait for an ok.
- Lightweight: no Docker, databases or servers. One copy each of Chrome, FFmpeg and Node.
- You cannot restart the gateway you run in: when a step needs it, ask the user in one line to
  run `hermes gateway restart` (or use Desktop), then verify.
- Technical notes (versions, what was verified, deviations from the plan) go in
  ~/Hermes/projects/marketing/install-notes.md. Plan defects and traps go in
  ~/Hermes/builder/upstream-notes.md (base/07-builder.md).
- Install only Level 1. Read the traps in 05-scripts.md before step 5.

STEP 0 · Context. Read ~/Hermes/user/profile.md, contact.yaml, orchestrator/registry.md and
builder/installed.yaml. If the base is not installed, stop and say so.

STEP 1 · Personalization and models.
  a) 01-personalization.md, parts 1 to 4. Detect OS, RAM and free disk for the technical part.
     Draft marketing-profile.yaml, ask what is missing (at most 5 questions per round), show it
     in full and wait for an ok. Note the initial brands: they are onboarded in step 9.
  b) Models per bot (base/07-builder.md): list the models available on the user's Hermes
     connection and show one table: bot, recommended model, recommended effort, the user's
     choice. Recommendations: strategist, creative and reviewer main_model with medium effort;
     producer production_model with high effort. If a recommended model is unavailable,
     recommend the closest available one and say why. "Same model for all" is a valid answer.

STEP 2 · Computer tools (per services and render_mode):
  a) Google Chrome or the system Chromium, if there is none: HyperFrames and Playwright share it.
  b) Node 22 LTS or later.
  c) System FFmpeg and FFprobe (brew, winget or apt).
  d) In ~/Hermes/projects/marketing/: a Python 3.11+ .venv with PyYAML, Pillow, playwright,
     requests and pytest. Playwright uses the system browser (channel "chrome", or
     executablePath for Chromium) and downloads its own only if there is none. With npm, in the
     same folder and pinned: @google/design.md and impeccable (check_piece.py uses them), and
     mjml only if services includes email (npm, never pip: trap 1 in 05-scripts.md).
  e) If services includes video: HyperFrames pinned in the same folder
     (npm i -D hyperframes@<current stable version>). Then npx hyperframes telemetry disable;
     npx hyperframes doctor (it must see the browser, FFmpeg and at least 2 GB free for its
     cache); a local voice test in the first brand's language (tts) and a transcription test.
  f) Optional keys in ~/Hermes/projects/marketing/.env: stock_photos (Pexels, Pixabay, Unsplash;
     free) and, with a premium voice, its provider's (e.g. ELEVENLABS_API_KEY).
  g) Fonts: each brand's typefaces are self-hosted in its identity/fonts/, so rendering does
     not depend on the internet.
Summarize what was installed, its size and versions (also in install-notes.md).

STEP 3 · Folder. Create ~/Hermes/projects/marketing/ with the tree from 02-architecture.md §1.
Write squad.yaml (the plan's, filled in: model and reasoning_effort per bot from step 1b, crons
per the profile), AGENTS.md (§9, variables substituted), marketing-profile.yaml, ai-spend.csv
with its header, outbox/ready/, outbox/sent/, brands/, install-notes.md and the squad's
.gitignore. In templates/, plain base HTML templates with CSS variables (style comes from each
brand's DESIGN.md): 4:5 and square post, 9:16 story, carousel slide, ad in the 4 sizes from
02-architecture.md §2, 16:9 thumbnail, OG image, A4 or letter document per country, MJML email
and landing. In scripts/, limits.yaml with each network's reference sizes and lengths. Commit.

STEP 4 · Own skills. Write those in 03-bots.md §3.1 in skills/<role>/ (flat folders), with the
template from base/05 and the real profile values. For each, first read its sources in
~/Hermes/plans/squads/marketing/reference/ (see its README) and adapt the best parts; follow the
format of the bundled skill hermes-agent-skill-authoring; test with skill-creator from
anthropics/skills in your own profile if useful. piece-contract must contain everything its row
lists. Write orchestration-marketing from 03-bots.md §4.1 and its references/onboarding.md,
which is not bundled: write it from 01-personalization.md Part 5 as §4.1 describes. Without it
the orchestrator gets a diagnosis with questions and no procedure to ask them.

STEP 5 · Profiles. For each bot in 03-bots.md §1:
  hermes profile create <bot> --no-skills --description "<description>"
  - SOUL.md from §2, variables substituted.
  - Model and agent.reasoning_effort from squad.yaml with hermes -p <bot> config set.
  - Toolsets from the table (including skills) and agent.disabled_toolsets with the blocked
    ones. A new profile inherits the source profile's toolset state even without --clone, so
    every bot starts with terminal, web, browser, code_execution and image_gen enabled: disable
    the blocked ones explicitly per profile and verify with hermes -p <bot> tools list. A bot
    that keeps terminal breaks AGENTS.md rule 1.
  - terminal.cwd, skills.external_dirs (role folder and common), memory disabled,
    security.website_blocklist, the LLM provider's API key.
  - Vision bots (creative, producer, reviewer): if the model can't see images, configure
    auxiliary.vision.
  - Producer: image_gen.provider and image_gen.model per image_ai (nothing if none), plus its key.
  - Strategist, creative and reviewer: if delegation.oneshot_max_children limits workers'
    subagents, raise it to 5 (checked in step 10).
  - If the Kanban dispatcher is enabled, check that workers can launch hermes (trap 8 in
    05-scripts.md: HERMES_BIN in the gateway's environment).
Install the third-party skills from 03-bots.md §3.2 whose condition holds: hermes skills inspect
<source>, then hermes -p <bot> skills install <source>. Re-enable the bundled skills the table
lists (command in hermes skills --help). Verify with hermes -p <bot> tools list and skills list.
Tell the user to create the "Marketing agency" section in Hermes Desktop with the four bots.

STEP 6 · Scripts. Write the Level 1 scripts from 05-scripts.md, with their tests, and run them
(heavy_lock.py goes in ~/Hermes/scripts/ if it doesn't exist). Minimum tests:
  - render_html.py with a sample post: exactly 1080×1350.
  - With video: render_video.py with a 5 s clip in the render_mode; a second render launched at
    the same time waits for the first, and contact_sheet.py doesn't block.
  - check_piece.py on those two pieces.
  - stock_photos.py with one search, if there are keys.
  - studio.py on a test brand with 3 pieces.
  - deliver.py in simulated mode, with an incomplete batch and a v2.
Delete the test brand when you finish.

STEP 7 · Orchestrator, registry and channel.
  a) Run python ~/Hermes/scripts/registry.py: it regenerates orchestrator/registry.md from every
     projects/*/squad.yaml and prints the orchestrator's skills.external_dirs. Apply that list
     with hermes -p orchestrator config set, keeping what it already has. Verify that
     hermes -p orchestrator skills list shows orchestration-marketing. If the version allows it,
     enable its desktop_ui toolset in Desktop sessions (Studio next to the chat).
  b) If topic_per_brand: in Telegram, guide the user to enable Threaded Mode in BotFather and
     add the General topic in dm_topics (03-bots.md §5.2); ask for a gateway restart and check
     that the topic appears. In Discord, work through the four grants in 03-bots.md §5.2 in
     order, confirming each: a partial setup connects the gateway and never reads a message.
     After the token is written and the gateway restarted, check the gateway log for
     `discord connected`, then send one real message through the bot and read its reply (the
     only test covering all four grants).
  c) Add the line in "Active squads" in user/profile.md. Record in builder/installed.yaml:
     squads.marketing = {source: official, plan_version: <from squad.yaml>, commit: <plans
     commit>}.

STEP 8 · Automations (03-bots.md §5.1). Create $HERMES_HOME/scripts/ for each profile that runs
one (trap 4 in 05-scripts.md), copy each script into it (copy, don't link) and create the crons
listed in squad.yaml: plan_week.py (every hour), deliver.py (every 15m), monthly_report.py
(every day at 08:00) if monthly_report is true, and the weekly summary if weekly_summary is
true. Leave them paused until step 10. Show hermes cron list, then hermes cron doctor (it
reports jobs that silently don't fire, including a missing script directory).

STEP 9 · First brand (from initial_brands). Do what the orchestrator would (03-bots.md §4.1,
"Onboarding a brand"): a minimal settings.yaml and, with topics, its brand-<slug> skill and its
dm_topics entry (gateway restart by the user, check the topic). Launch the strategist's
ONBOARDING task with the body and idempotency key from the contract. Follow the chain with
hermes kanban list --tenant <slug> until deliver.py (run by hand) sends the diagnosis to its
topic. A task showing running is not proof that the worker works (trap 8): confirm with
hermes kanban runs <task-id> that the run passed its first minute and the brand folder is
gaining files. Ask the user to answer the questions from their app and approve context, brand,
DESIGN.md and settings: the orchestrator must set active: true.

STEP 10 · End-to-end test. Ask the user to type in the brand's topic "make a <most useful type
for them> about <something real>". Follow the chain until the proposal arrives: the creative,
producer and reviewer tasks exist (keys include the role). Then "change: <something small>":
v2 arrives and v1 stays intact. Run the tests marked I in 06-testing-and-operations.md. Open
the Studio and show it. Verify and note in install-notes.md:
  - workers receive the skills and kanban toolsets, and none of the blocked ones;
  - the strategist and the reviewer could launch 5 subagents;
  - whether kanban_create accepts a per-task model (D-016) and whether Kanban's native review
    accepts the squad's own skill (D-015);
  - the tenant passes from a task to its children;
  - whether several MEDIA: attachments arrive as an album, and the largest video the channel
    accepted;
  - [[as_document]] keeps Telegram from recompressing covers;
  - whether adding a topic to dm_topics with the gateway running creates it without a restart;
  - Playwright and HyperFrames used the system browser;
  - orchestration-marketing is loaded in the orchestrator profile and
    skills/orchestration/references/onboarding.md exists;
  - a question only the user can answer (a price, a goal) reaches them as a question, not as a
    blocked task with no explanation;
  - a consultation (test AB) resumes the asker's card with the answer and reaches nobody.
If everything works, resume the crons (hermes cron resume).

At the end, in plain language: what is working, when each brand's first week arrives, what they
can reply to each proposal, how to onboard another brand, where the Studio is, how to pause or
ask for quiet, and that configuration changes go to the builder.
```

## Maintenance

The user asks the builder (`config-change` skill); the builder does only what was asked. Plan updates follow `base/08-updates.md` (`update-installation`).

| Request | What the builder does |
| --- | --- |
| "add the topic for <brand>" (also as a kanban task from the orchestrator) | Checks that `skills/orchestration/brand-<slug>/` exists, backs up the orchestrator config, adds the topic to `dm_topics` with that skill, and asks the user for a gateway restart if needed, with no Kanban tasks running. Sets `destination: topic` in the brand's `settings.yaml` and checks that a test message reaches the topic |
| "update the marketing skills" | `hermes -p <bot> skills check` per profile; shows what changes and updates with `update` after an ok |
| "update HyperFrames" | Installs the new version, repeats the step 6 render test and pins it only if it passes |
| "change <bot>'s model or effort" | Updates `bots[]` in `{{M}}/squad.yaml` (and `production_model` in `marketing-profile.yaml` for the producer), applies it with `hermes -p <bot> config set` and tests a piece |
| "move to Level 2" | Follows the Level 2 section of `05-scripts.md`, only for what the user chooses; records it in `install-notes.md`, `level` in `squad.yaml`, and reruns `registry.py` |

## After installing

- Other brands are onboarded by chat: "new project: <name> <website or social media>".
- The first planned week arrives after each active brand's next planning time.
- After 4 weeks, review the metrics with [`06-testing-and-operations.md`](06-testing-and-operations.md).
