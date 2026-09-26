# Installation: marketing agency (Level 1)

> Instructions for the installer AI: the chat of the Hermes Desktop `default` profile, with `terminal`, `file` and `skills`, and `approvals.mode: smart`. You get here from `START-HERE.md` when the user asks to "install the marketing agency squad", or for a maintenance task (at the end).
> It runs on the user's computer, which already has the base installed. The AI reads the files in `~/Hermes/plans/` itself.
> Duration: 2 to 3 hours, split between installing tools, onboarding the first brand and testing. It can be split into two sessions: A (steps 0-6) and B (steps 7-10).

```markdown
You are the installer of the "Marketing agency" squad. Read in full: all of
~/Hermes/plans/base/; from ~/Hermes/plans/squads/marketing/, files 01 to 06;
and ~/Hermes/plans/00-evaluation/05-marketing-design.md §10 (machine-load rules).

Rules:
- The user may not be technical: speak simply, explain each technical step in one line and do it
  yourself.
- Verify every command with its real output. Don't invent paths, flags or results. If something
  doesn't exist in this version of Hermes or of a tool, look for the equivalent with --help or in
  the documentation, say so and adapt.
- Don't modify anything outside ~/Hermes, the Hermes internal folder and the tools the user
  authorizes you to install.
- Before installing system software, say what it is and how much space it takes, and wait for an
  ok.
- Lightweight: no Docker, databases or servers. A single copy of Chrome, FFmpeg and Node.
- Technical notes (versions, what was verified, what changed from the plan) go in
  ~/Hermes/projects/marketing/install-notes.md, not in orchestrator/registry.md.
- Install only Level 1.

STEP 0 · Context. Read ~/Hermes/user/profile.md, contact.yaml and ~/Hermes/orchestrator/registry.md.
If the base is not installed, stop and say so.

STEP 1 · Personalization (01-personalization.md, parts 1 to 4). Detect the OS, RAM and free disk
space for the technical part. Write the draft of marketing-profile.yaml, ask what is missing
(at most 5 questions per round), show it in full and wait for an ok. Note the initial brands:
they are onboarded in step 9.

STEP 2 · Computer tools (according to services and render_mode):
  a) Google Chrome or the system Chromium, if there is none: HyperFrames and Playwright share it.
  b) Node 22 LTS or later.
  c) System FFmpeg and FFprobe (brew, winget or apt).
  d) In ~/Hermes/projects/marketing/: a Python 3.11+ .venv with PyYAML, Pillow,
     playwright, requests and pytest. Playwright uses the system browser (channel "chrome", or
     executablePath if it is Chromium) and downloads its own only if there is no other. With npm,
     in the same folder and with a pinned version: @google/design.md, impeccable (check_piece.py
     uses them) and **mjml** (only if services includes email).
     **mjml is an npm package, not a Python one.** The PyPI project named `mjml` is an unrelated
     third-party reimplementation and does not compile MJML markup. Install it with npm
     (`npm i -D mjml@<current version>`) and compile with `npx mjml`; do not add it to the venv.
  e) If services includes video: HyperFrames with a pinned version in the same folder
     (npm i -D hyperframes@<current stable version>). Then: npx hyperframes telemetry disable;
     npx hyperframes doctor (it must see the browser, FFmpeg and at least 2 GB free for its cache);
     a local voice test in the language of the first brand (tts) and a transcription test.
  f) Optional keys in ~/Hermes/projects/marketing/.env: the ones for stock_photos (Pexels, Pixabay,
     Unsplash; they are free) and, if voice is premium, the one for its provider (for example,
     ELEVENLABS_API_KEY).
  g) Fonts: each brand's typefaces are self-hosted in its identity/fonts/ folder, so that
     rendering doesn't depend on the internet.
Summarize what was installed, how much space it takes and the versions (also in install-notes.md).

STEP 3 · Folder. Create ~/Hermes/projects/marketing/ with the tree from 02-architecture.md §1.
Write AGENTS.md (§9, with the variables substituted), marketing-profile.yaml, ai-spend.csv with
its header, outbox/ready/, outbox/sent/, brands/, install-notes.md and the squad's .gitignore.
In templates/, the base HTML templates with CSS variables: 4:5 and square post, 9:16 story,
carousel slide, ad in the 4 sizes from 02-architecture.md §2, 16:9 thumbnail, OG image, A4 or
letter document depending on the country, MJML email and landing. They must be plain, with no
style of their own: the style comes from each brand's DESIGN.md. In scripts/, limits.yaml with
each network's reference sizes and lengths. Commit.

STEP 4 · Own skills. Write the ones from 03-bots.md §3.1 in skills/<role>/ (flat folders), with
the template from base/05 and the real profile values. For each one, first read its sources in
~/Hermes/plans/squads/marketing/reference/ (see its README) and take the best parts,
adapted to this plan; follow the format of the bundled skill hermes-agent-skill-authoring and, if
you want to test them, use skill-creator from anthropics/skills in your own profile. The
piece-contract skill must contain everything its row lists. Write orchestration-marketing with
the text from 03-bots.md §4.1, plus its references/onboarding.md.

STEP 5 · Profiles. For each bot in 03-bots.md §1:
  hermes profile create <bot> --no-skills --description "<description>"
  - SOUL.md from §2, with the variables substituted.
  - Model: main_model; for the producer, production_model. No models with the
    -contributor suffix.
  - Toolsets from the table (including skills) and agent.disabled_toolsets with the blocked ones.
  - terminal.cwd, skills.external_dirs (its role folder and common), memory disabled,
    security.website_blocklist, the LLM provider's API key.
  - **A new profile inherits the source profile's toolset state.** `hermes profile create` without
    `--clone` still seeds toolsets, so every bot starts with terminal, web, browser, code_execution
    and image_gen enabled. Disable the blocked ones explicitly in each profile and then **verify
    with `hermes -p <bot> tools list`** — the `tools enable/disable` verb is per profile, and a
    bot that keeps `terminal` silently breaks the isolation rule 1 of `AGENTS.md`.
  - If the model of a bot with vision (creative, producer or reviewer) can't see images,
    configure auxiliary.vision in that profile.
  - Producer: image_gen.provider and image_gen.model according to image_ai (nothing if it is
    none), plus its key.
  - Strategist, creative and reviewer: if delegation.oneshot_max_children limits the workers'
    subagents, raise it to 5 (checked in step 10).
Install the third-party skills from 03-bots.md §3.2 that meet their condition: first hermes skills
inspect <source>, then hermes -p <bot> skills install <source>. In each profile, re-enable the
skills bundled with Hermes that the table lists (find the command with hermes skills --help).
Verify with hermes -p <bot> tools list and hermes -p <bot> skills list. Create, or ask the user to
create, the "Marketing agency" section in Hermes Desktop with the four bots.

STEP 6 · Scripts. Write the Level 1 scripts from 05-scripts.md yourself, with their tests, and
run them (heavy_lock.py goes in ~/Hermes/scripts/ if it doesn't exist yet). Minimum tests:
  - render_html.py with a sample post: exactly 1080×1350.
  - If there is video: render_video.py with a 5 s clip in the mode set by render_mode. Check that
    a second render launched at the same time waits for the first one and that contact_sheet.py
    doesn't get blocked.
  - check_piece.py on those two pieces.
  - stock_photos.py with one search, if there are keys.
  - studio.py on a test brand with 3 pieces.
  - deliver.py in simulated mode, with an incomplete batch and a v2.
Delete the test brand when you finish.

STEP 7 · Orchestrator and channel.
  a) Add ~/Hermes/projects/marketing/skills/orchestration to the orchestrator's
     skills.external_dirs, without removing what it already has. Verify that it sees
     orchestration-marketing. If the version allows it, enable its desktop_ui toolset in Desktop
     sessions, so it can open the Studio next to the chat.
  b) If topic_per_brand: in Telegram, guide the user to enable Threaded Mode in BotFather and
     add the General topic in dm_topics (03-bots.md §5.2). Restart the gateway and check that the
     topic appears. In Discord, ask them to create one channel per brand.
  c) Add the row to orchestrator/registry.md and the line in "Active squads" in
     user/profile.md.

STEP 8 · Automations (03-bots.md §5.1). Create `$HERMES_HOME/scripts/` for each profile that
runs one (it does not exist on a fresh profile, and Hermes refuses a script outside it). Copy
each script into it (copy, don't link) and create the crons: plan_week.py (every hour),
deliver.py (every 15m), monthly_report.py (every day at 08:00) if monthly_report is true, and the
weekly summary if weekly_summary is true. Leave them paused until step 10. Show hermes cron list,
then `hermes cron doctor` — it reports the jobs that are silently not firing, including a missing
script directory.

STEP 9 · Onboarding the first brand (from initial_brands). Do what the orchestrator would do
(03-bots.md §4.1, "Onboarding a brand"): a minimal settings.yaml and, if there are topics, its
brand-<slug> skill and its entry in dm_topics (restart the gateway and check the topic). Launch
the strategist's ONBOARDING task with the body and the idempotency-key from the contract. Follow
the chain with hermes kanban list --tenant <slug> until deliver.py (run it by hand) sends the
diagnosis to its topic. Ask the user to answer the questions from their app and to approve
context, brand, DESIGN.md and settings: the orchestrator must set active: true.

STEP 10 · End-to-end test. Ask the user to type in the brand's topic "make a <most useful type for
them> about <something real>". Follow the chain until the proposal reaches them: check that the
creative, producer and reviewer tasks were created (the idempotency-keys include the role). Then
ask for "change: <something small>" and check that v2 arrives and that v1 stays intact. Run the
tests in 06-testing-and-operations.md marked "installation". Open the Studio and show it to them.
Verify and note in install-notes.md:
  - that the workers receive the skills and kanban toolsets, and none of the blocked ones;
  - whether the strategist and the reviewer could launch their 5 subagents;
  - whether kanban_create accepts a per-task model (D-016) and whether Kanban's native review
    accepts the squad's own skill (D-015);
  - that the tenant passes from a task to its children;
  - whether several MEDIA: attachments arrive together as an album, and the maximum video size the
    channel accepted;
  - that [[as_document]] keeps Telegram from recompressing the covers;
  - whether adding a topic to dm_topics with the gateway running creates it without a restart;
  - that Playwright and HyperFrames used the system browser.
If everything works, resume the crons (hermes cron resume).

At the end, in plain language: what is now working, when each brand's first week will arrive,
what they can reply to each proposal, how to onboard another brand, where the Studio is and how to
pause or ask for quiet.
```

## Maintenance

The user asks for it in the Hermes Desktop main chat ("Read `~/Hermes/plans/START-HERE.md` and …"). The installer AI reads this file and does only what was asked.

| Request | What the AI does |
| --- | --- |
| "add the topic for <brand>" | Checks that `skills/orchestration/brand-<slug>/` exists, adds the topic to the orchestrator's `dm_topics` with that skill (backing up the config first) and restarts the gateway if needed, with no Kanban tasks running. Sets `destination: topic` in the brand's `settings.yaml` and checks that a test message reaches the topic |
| "update the marketing skills" | `hermes -p <bot> skills check` in each profile; shows what changes and updates with `update` after an ok |
| "update HyperFrames" | Installs the new version, repeats the render test from step 6 and pins the version only if it passes |
| "change the producer's model" | Changes `production_model` in `marketing-profile.yaml` and in the bot's profile, and tests a piece |
| "move to Level 2" | Follows the Level 2 section of `05-scripts.md`, only for what the user chooses, and records it in `install-notes.md` and in `registry.md` |

## After installing

- The other brands are onboarded by chat: "new project: <name> <website or social media>".
- The first planned week arrives after each active brand's next planning time.
- After 4 weeks, review the metrics with [`06-testing-and-operations.md`](06-testing-and-operations.md).
