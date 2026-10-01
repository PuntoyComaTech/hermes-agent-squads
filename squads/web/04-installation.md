# Installation: web development squad (Level 1)

> Instructions for the `builder` bot, skill `squad-install` (`base/07-builder.md` §4.2). You get here when the user asks the builder to "install the web squad", or for a maintenance task (at the end).
> Requires the base installed, including the builder. Duration: 1.5 to 2.5 hours, most of it waiting for the user to create accounts and the first site's chain. It can be split: A (steps 0-8) and B (steps 9-11).

```markdown
You are installing the "Web development squad". Read in full: all of ~/Hermes/plans/base/
and ~/Hermes/plans/squads/web/ (files 01 to 06 and squad.yaml). git pull in plans/ and in
~/Hermes/.cache/hermes-docs first; Hermes facts come from that docs cache, not the web.

Rules:
- The user may not be technical: explain each step in one line and do it yourself. The user only
  creates accounts, pastes tokens and says yes or no.
- Verify every command with its real output. Never invent paths, flags, cf commands or model
  names. A cf command not verified here: find it with cf cli search "<task>" and note it.
- Before installing any system software: what it is, its size, and wait for an ok.
- Lightweight: no Docker, databases or servers. One copy of Chrome and Node.
- You cannot restart the gateway you run in: ask the user in one line to run
  hermes gateway restart (or use Desktop), then check hermes gateway status.
- Technical notes (versions, what was verified, what differs from the plan) go in
  ~/Hermes/projects/web/install-notes.md. Plan defects go in ~/Hermes/builder/upstream-notes.md.
- Install only Level 1.

STEP 0 · Context. Read user/profile.md, orchestrator/registry.md, builder/installed.yaml. If the
base is missing, stop and say so. If projects/marketing/ exists, note its brands (a site may use
one as design source).

STEP 1 · Personalization (01-personalization.md Parts 1 to 4). Detect OS, RAM and free disk.
Draft web-profile.yaml, ask what is missing (at most 5 per round), show it, wait for ok. Note
initial_sites: the first one is onboarded in step 10.

STEP 2 · Models (base/07-builder.md §5). Get the models available on the user's connection: ask
the user to paste the /model list from Hermes Desktop, or read it from this session. There is no
documented non-interactive listing command; do not invent one. Show one table: bot, recommended
model, recommended effort, the user's choice. Recommended (September 2026, only if available):
web-developer Claude Sonnet 5.5 reasoning high; web-advisor Claude Opus 5.5 reasoning medium;
web-architect, web-reviewer, web-deployer {{main_model}}. If one is unavailable, propose the
closest available and say why. "Same model for all" is a valid answer.

STEP 3 · Tools. Check first, install only what is missing, with the user's ok (brew on Mac,
winget on Windows, apt on Linux, or the vendor installer):
  a) git and Node 22 LTS or later.
  b) pnpm: corepack enable, then corepack prepare pnpm@latest --activate (or npm i -g pnpm).
     Check: pnpm --version.
  c) gh (GitHub CLI). Check: gh --version. osv-scanner (brew install osv-scanner, or the release
     binary from google/osv-scanner), pinned to the version in 05-scripts.md "Quality gate".
     Check: osv-scanner --version, then download the offline database once into ~/Hermes/.cache/osv
     (OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY; .cache/ is already ignored).
  d) cf (Cloudflare CLI, open beta): npm i -g cf. Check: cf --version and cf cli search "deploy"
     returns JSON. Record the version: the beta changes often.
  e) Wrangler: not global. Used only through npx wrangler@<pinned version> for one-off secrets
     and live logs. Check: npx wrangler@<version> --version.
  f) Google Chrome or the system Chromium, shared with marketing if installed.
  g) In ~/Hermes/projects/web/: a Python 3.11+ .venv with PyYAML, playwright, requests and pytest.
     Find a 3.11+ interpreter first (`python3 --version`): macOS ships 3.9.x, and `python3 -m venv`
     then silently produces a venv too old for these scripts. Without one, create the venv from any
     3.11+ interpreter on the machine (a brew python, or another squad's venv) or install one with
     the user's ok. Record the interpreter version in install-notes.md.
     Playwright uses the system browser (channel "chrome", or executablePath for Chromium) and
     downloads its own only if none exists. With npm, pinned: lighthouse and axe-core.
Summarize versions and space in install-notes.md.

STEP 4 · Folder. Create ~/Hermes/projects/web/ with the tree of 02-architecture.md §1: AGENTS.md
(§9 with variables substituted), web-profile.yaml, outbox/ready/, outbox/sent/, sites/,
install-notes.md, the squad .gitignore (§1). Commit in ~/Hermes.

STEP 5 · Own skills (03-bots.md §4.1) in skills/<role>/, template base/05, format of the bundled
hermes-agent-skill-authoring. For each stack and provider skill, read the tool's current docs
first and record the versions. deploy-cloudflare: run cf cli search for every task it lists
(create project, build, upload preview version, preview URL, deploy, list versions and
deployments, rollback, custom domain, zone, DNS record, D1 migrations, D1 export, delete
commands for the deny list) and write the exact commands with their real output shape. Write
orchestration-web (§5.1) and skills/orchestration/references/onboarding.md from
01-personalization.md Part 5 (it is not bundled; without it the orchestrator cannot onboard).

STEP 6 · Profiles. For each bot in 03-bots.md §1:
  hermes profile create <bot> --no-skills --description "<description>"
  - SOUL.md from §2 with variables substituted.
  - hermes -p <bot> config set for model, agent.reasoning_effort (the user's choice), terminal.cwd,
    skills.external_dirs (role folder and common), memory disabled.
  - Toolsets from the table and `agent.disabled_toolsets`. A new profile inherits toolset state:
    disable the blocked ones explicitly and verify with `hermes -p <bot> tools list`. That list also
    shows toolsets Hermes enables by default and this plan never asks for (`todo`, `memory`,
    `session_search`, `connections`, `clarify`, `cronjob`, `computer_use`): turn each one off too.
    `web-advisor` in particular must end with only `file`, `skills` and `kanban` (the kanban tools are
    registered for Kanban workers automatically, so `kanban` is not in `squad.yaml` `toolsets`).
  - web-advisor: only file and skills; tools list must show terminal, web, browser and
    delegation disabled.
  - Third-party skills (§4.2): hermes skills inspect <source>, then
    hermes -p <bot> skills install <source>; re-enable the bundled ones listed.
  - The Kanban HERMES_BIN trap: squads/marketing/04-installation.md step 5.
Tell the user to create the "Web squad" section in Hermes Desktop with the five bots.

STEP 7 · Accounts and credentials. Only web-deployer holds them.
  a) GitHub. If there is no account, guide the user to create one (free) and wait.
     1. Fine-grained personal access token, guided click by click: GitHub → Settings →
        Developer settings → Personal access tokens → Fine-grained tokens → Generate. Resource
        owner: {{github_owner}}. Expiration: 1 year (note the date in install-notes.md).
        Repository permissions: Contents read and write, Pull requests read and write,
        Metadata read, Commit statuses read. Repository access: whatever the user picks.
     2. Store it: hermes -p web-deployer config set GH_TOKEN <token> (UPPER_SNAKE keys go to
        that profile's .env). Never gh auth login: it stores credentials for the whole OS user.
  b) Cloudflare. If there is no account, guide creating one (free) and wait. API token: dashboard
     → My Profile → API Tokens → Create Token → Custom token, with only: Account · Workers
     Scripts · Edit; Account · Account Settings · Read; Zone · Workers Routes · Edit and Zone ·
     DNS · Edit (all zones of the account, or added per zone when a domain is connected);
     Account · D1 · Edit, Workers KV Storage · Edit, Workers R2 Storage · Edit only when a site
     needs them. The Account ID from the dashboard overview. Store both with
     hermes -p web-deployer config set CLOUDFLARE_API_TOKEN … and CLOUDFLARE_ACCOUNT_ID ….
     If a cf call in step 11 fails for a missing permission, add only that one and note it.
  c) hermes -p web-deployer config set terminal.env_passthrough
     '[CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, GH_TOKEN]'.
  d) Verify from a web-deployer session: gh auth status shows the token user; the cf command
     cf cli search finds for "verify token" succeeds. Verify from a web-developer session that
     the same three variables are empty.
  e) GitHub access, agreed with the user (no default):
     1. Run the GitHub token check (03-bots.md §1) from a web-deployer session: who, which
        repos, whether it can create repos.
     2. Explain both options in plain words, with what the check found, and let the user choose:
        bot_creates: "I create each site's repository. Your key then needs access to all
        your repositories and permission to create them (Administration), so it could also
        change their settings."
        user_creates: "For each new site you create one empty private repository (two minutes,
        I guide you) and give the key access to it. The key never sees your other
        repositories."
     3. If the choice needs a different token (bot_creates: All repositories plus
        Administration read and write), guide the edit and repeat the check until it matches.
     4. Write repo_mode and repo_mode_checked_at in web-profile.yaml and show the change.

STEP 8 · Approvals for workers. Create one test task per bot with a terminal (developer,
reviewer, deployer) that runs a harmless command of its role: developer pnpm install in a
throwaway Astro project under the lock; reviewer check_site.py --help; deployer gh auth status
and one cf read command. If a command is denied because nobody can approve it
(approvals.single_query_mode: deny, user-guide/security.md), add to that profile's
command_allowlist only the rule key shown in the denial, and repeat. Then set approvals.deny for
each profile with the lists in 03-bots.md §1 (quoted patterns) and verify one denied command
per profile returns BLOCKED. Never set approvals.mode off.

STEP 9 · Scripts (05-scripts.md). Write them with their tests and run the tests. heavy_lock.py
goes in ~/Hermes/scripts/ only if it does not exist. deliver.py in --simulate with two sample
sites. check_site.py against the throwaway Astro build served locally by its test fixture. The six
quality-gate files ("Quality gate") in ~/Hermes/projects/web/templates/quality/; run-gate.mjs against the
throwaway Astro project with its dev dependencies, and run-gate.mjs --help exits 0.

STEP 10 · Orchestrator, channel, manifest, automations.
  a) Write ~/Hermes/projects/web/squad.yaml from plans/squads/web/squad.yaml with the model and
     reasoning_effort per bot. Run python ~/Hermes/scripts/registry.py; apply the printed
     skills.external_dirs with hermes -p orchestrator config set; check that the orchestrator
     sees orchestration-web (hermes -p orchestrator skills list) and that registry.md lists web.
  b) Topics or channels (topic_per_site): as marketing, squads/marketing/03-bots.md §5.2 and
     squads/marketing/04-installation.md step 7b.
  c) Create $HERMES_HOME/scripts/ for the orchestrator if missing, copy deliver.py, create the
     cron every 15m (--no-agent), and the weekly summary if chosen. Paused until step 11.
     hermes -p <profile> cron list (per profile; without `-p` it lists only the default one), then
     hermes cron doctor.
  d) Add the line in "Active squads" in user/profile.md. Record in builder/installed.yaml:
     squads.web = {source: official, plan_version: <from squad.yaml>, commit: <plans commit>}.

STEP 11 · End-to-end test with the first site (or a test site if the user has none; delete it at
the end, repo included only with the user's ok, done by the user in GitHub).
  a) Onboard it as the orchestrator would: settings.yaml, deployer REPO (repo created, or the
     user's empty repo verified, per repo_mode), questions, architect SPEC. The spec
     arrives in the site topic (run deliver.py by hand). The user replies "ok".
  b) Follow the chain with hermes kanban list --tenant <slug>: developer BUILD (Astro), deployer
     PREVIEW (main and branch pushed, PR open, preview URL answers 200), reviewer REVIEW.
     A card in running is not proof: check hermes kanban runs <task-id> and that files appear.
  c) The preview message reaches the user with the link and a screenshot.
  d) The user says "publish": the confirmation question arrives; only after their yes, the
     deployer merges and deploys; the live URL answers 200 and deploys/ has previous_version_id.
  e) Ask for "change: <something small>": a new preview arrives, production is untouched.
  f) Run the tests marked I in 06-testing-and-operations.md.
Verify and note: the tenant passes to children; workers get skills and kanban and none of the
blocked toolsets; the three secrets exist only in the deployer's terminal; a CONSULT card from
developer to deployer resumes the asker with the answer in Parent task results; a CONSULT card
to web-advisor gets an answer and the advisor changed no file (git status clean); the exact cf
preview and rollback commands. If everything works, hermes cron resume.

At the end, in plain language: what works, how to start another site ("new site: …"), what to
reply to a preview, that "publish" always asks first, and what costs money (domain, and Workers
Paid for app-type sites).
```

## Maintenance

The user asks the builder. It does only what was asked, with `config-change` (`base/07-builder.md` §4.3).

| Request | What the builder does |
| --- | --- |
| "add the topic for <site>" | As marketing's "add the topic for <brand>" (`squads/marketing/04-installation.md`, Maintenance), with `site-<slug>` |
| "renew my GitHub token" · "renew my Cloudflare token" | Guides a new token with the same permissions, stores it in web-deployer's `.env`, verifies (GitHub: the token check matches `repo_mode`), asks the user to revoke the old one |
| "let the bot create my repos" · "I'll create the repos myself" | Explains the other `repo_mode` in plain words, guides the token change, runs the GitHub token check from web-deployer, updates `repo_mode` and `repo_mode_checked_at` in `web-profile.yaml` |
| "the domain needs DNS permission" | Adds only Zone · DNS · Edit for that zone to the Cloudflare token (user clicks), verifies with a read |
| "update cf" | `npm i -g cf@latest`, re-runs `cf cli search` for every command in `deploy-cloudflare`, updates the skill only where output changed, records it |
| "update the web skills" | `hermes -p <bot> skills check` in each profile; shows changes; updates after ok |
| "change the developer's model" · "change the advisor's model" | `hermes -p web-developer config set` or `hermes -p web-advisor config set` for `model` and `agent.reasoning_effort`; updates `squad.yaml`; one test BUILD, or one test CONSULT for the advisor |
| "use Vercel for <site>" | Writes `deploy-vercel` if missing, guides a Vercel token into web-deployer's `.env` and passthrough, sets `provider: vercel` in that site; checks `commercial` |
| "<client> brings their own Cloudflare account" · "put a wall between my clients" | Guides `cf auth create <slug>` (the user logs in through the browser), then `cf auth activate <slug> {{W}}/sites/<slug>`, and verifies with `cf auth whoami` and `cf auth list` **from inside that folder**. Sets `cloudflare.profile: <slug>` in that site's `settings.yaml` and checks that `env -u CLOUDFLARE_API_TOKEN -u CLOUDFLARE_ACCOUNT_ID cf --profile <slug> auth whoami` reports the client's account. Records in `install-notes.md` which account plain `cf auth whoami` reports from inside the folder with the token set (the precedence is undocumented; the deployer does not depend on it). Notes it in that site's `decisions.md`. When the site is handed over: `cf auth deactivate {{W}}/sites/<slug>` and `cf auth delete <slug>`, then ask the user to revoke the access in their Cloudflare dashboard |
| "move to Level 2" | `06-testing-and-operations.md` §5, only what the user chooses; records it in `install-notes.md` and `squad.yaml` `level` |
