# Decision log

One entry per structural decision, newest first. IDs and dates are stable: other files cite them.

---

## D-031 · 2026-09-30 · Model and reasoning effort per bot, chosen by the user

**Decision:** the builder asks, per bot, which model and reasoning effort to use, listing only the models available on the user's Hermes connection (the catalog Hermes Desktop and `/model` show). One table per squad: bot, recommended model, recommended effort, the user's choice. "Same model for all" is a valid one-line answer. The choice is stored as `model` and `reasoning_effort` in `bots[]` of the squad's `squad.yaml` and applied with `hermes -p <bot> config set` (`agent.reasoning_effort`). `user/profile.md` keeps `main_model` as the default suggestion. Recommendations, dated September 2026 and shown only if available: `web-developer` on Claude Sonnet 5.5 with reasoning high, `web-advisor` on Claude Opus 5.5 with reasoning medium, every other bot on `main_model`. If a recommended model is missing, the builder recommends the closest available one and says why.
The advisor is a bot, `web-advisor`, with its model and reasoning effort set like any profile. It is read-only (`file`, `skills`; no terminal, web or browser) and answers through the standard direct consultation (CONSULT card plus dependency block, `base/01-principles.md` §2): web-developer consults it before choosing a data model or auth approach, after two failed attempts at the same error, before an irreversible data migration, and when the reviewer repeats a finding; web-architect consults it on architecture choices. These consultations count toward the base limit of 2 per task. The advisor advises; the asker decides and records the advice.
**Why:** the default stays one model (D-011), but some roles gain from a stronger model and the user pays for it, so the user decides. Catalogs differ per connection, so names come from the connection, never from the plan. An advisor bot costs only when consulted, runs on its own model and effort with a clean context, and reuses the consultation protocol with no new mechanism.
**Rejected alternatives:** fixed models per role in the plans (they break on connections that lack them); the advisor as a `delegate_task` subagent routed with `delegation.model` (it inherits the developer's toolsets, and subagents have no documented reasoning-effort key); a Mixture of Agents preset with the developer as aggregator (references do not see tool results, and it costs on every turn). Pros and cons: `06-web-design.md` §5.

## D-030 · 2026-09-30 · Web squad: 5 bots, Cloudflare by default, `cf` over Wrangler, GitHub always

**Decision:** squad `web`, multi-project (`projects/web/sites/<slug>/`, one tenant per site). Bots: `web-architect` (the only one with web research; spec, stack, milestones, change triage), `web-developer` (terminal; builds, tests, commits on a local branch; no web, no credentials), `web-advisor` (read-only second opinion on its own model, consulted by the developer and the architect, D-031), `web-reviewer` (independent, 5 lenses in subagents, checks the preview with a browser limited to preview URLs) and `web-deployer` (the only one with Cloudflare and GitHub credentials; preview and production deploys, DNS, domains, secrets, rollback). Stack by site type: Astro for static and content, Next.js App Router for dynamic public SEO sites, TanStack Start for SaaS. Cloudflare is the default provider; Vercel only if the user already uses it. `cf` runs everything Cloudflare; Wrangler only for what `cf` lacks (individual secrets, live log tailing). Every site is a repo in the user's GitHub account; production only with the user's explicit confirmation for that release. The GitHub token's scope has no default: at install and at each site's onboarding the deployer checks with `gh` what the token can do, and the user chooses between a token with all repositories and Administration write (the bot creates repos) and creating each empty repo themselves (the token sees only those). Pros and cons: `06-web-design.md`.
**Why:** each bot is justified by permissions, independence or its own model (`base/01-principles.md` §1.3): the bot that reads the web never runs code, the bot that runs dependency code holds no credentials, the advisor gets a stronger model only when consulted. Repository access trades convenience against exposure of the user's other repositories, so the user decides. Cloudflare's free plan allows commercial use. `cf` covers the whole Cloudflare API with JSON output, so one CLI serves every task. GitHub gives previews per branch, rollback by revert and code the user owns.
**Rejected alternatives:** 3 bots with the developer deploying (credentials next to arbitrary build scripts); a separate designer bot (same tools as the developer, one more handoff per milestone); Vercel by default (Hobby is non-commercial only); Wrangler for everything (narrower than `cf`); a fixed GitHub token scope (all repositories exposes every repo, selected repositories adds a manual step per site: the user weighs it).

## D-029 · 2026-09-30 · User squads in `~/Hermes/squads` and the upstream contribution loop

**Decision:** squads the user designs with the builder live in `{{ROOT}}/squads/<key>/`, in the same format as `plans/squads/<key>/`, with `source: own` in their manifest. `plans/` stays read-only. The builder appends every plan defect, installation trap, changed Hermes command, ambiguous contract or improvement to `{{ROOT}}/builder/upstream-notes.md`, separating upstream defects from personal preferences. It tells the user in plain language and asks "Should I open a PR to the community repository?". Only with an explicit yes for that PR it forks `PuntoyComaTech/hermes-agent-squads` with `gh`, changes only Markdown under `plans/` (plus a decision entry for structural changes), shows the diff and opens the PR. Never any user data: only `{{variables}}` and fictional examples.
**Why:** official squads are examples; users need their own. A read-only `plans/` keeps `git pull` clean. Every installation finds defects, and the loop returns them to everyone.
**Rejected alternatives:** editing `plans/` in place (breaks updates and mixes user data with templates); PRs without asking (consent and data leakage).

## D-028 · 2026-09-30 · Updates as idempotent migrations that preserve personalization

**Decision:** an installation is updated by `base/08-updates.md` running `base/migrations/NNNN-<name>.md` one at a time, each idempotent, with a summary and the user's ok. State lives in `{{ROOT}}/builder/installed.yaml`. Before each migration: a commit in `~/Hermes` and `hermes profile export` of every profile it touches. Personalization is never overwritten: `user/`, squad working data, memories, `.env` files, crons the user added, skills Hermes created, the user's own squads. Files generated from a template are merged section by section with a three-way comparison (installed template, current file, new template); sections changed by the user or by Hermes are shown in plain language and asked about.
**Why:** users and Hermes change the installed files; reinstalling or overwriting loses that. Idempotent steps can be re-run and stopped at any point.
**Rejected alternatives:** reinstalling from scratch; replacing whole files; a two-way diff (it cannot tell a user change from a template change).

## D-027 · 2026-09-30 · `builder` base bot: squads and configuration

**Decision:** a second base bot, `builder`, creates squads and makes every configuration change (skills `squad-design`, `squad-install`, `config-change`, `update-installation`, `upstream-contribution`). Toolsets: terminal, file, skills, delegation, memory, clarify, kanban. No web, browser or code execution: it verifies Hermes facts against `{{ROOT}}/.cache/hermes-docs`, pulled before use. It has memory and its own channel identity (a second Telegram bot or Discord application), multiplexed in the default gateway. It cannot restart the gateway it runs in, so it asks the user to run `hermes gateway restart` and then verifies. Scripts never edit Hermes config; the builder applies config with `hermes -p <profile> config set` and `tools enable/disable`. When the user asks the orchestrator for a change, the orchestrator creates a kanban task for `builder` (short changes) or points the user to the builder (long conversations).
**Why:** the orchestrator stays the voice of the squads without terminal or config permissions. The official docs are a pinned, trusted source; web pages are neither. A persistent bot remembers what was installed and is reachable from the messaging app for later changes.
**Rejected alternatives:** the orchestrator making config changes (mixes permissions and bloats its context); installation only from a one-off Desktop session (no memory of the installation, no channel for later changes).

## D-026 · 2026-09-30 · Squad manifest `squad.yaml` and generated registry

**Decision:** every squad plan has `squads/<key>/squad.yaml` (key, source, plan version, level, projects dir, bots with toolsets and skill dirs, consult pairs, crons, example requests). The builder writes the filled-in copy to `{{ROOT}}/projects/<key>/squad.yaml`. `{{ROOT}}/scripts/registry.py` reads every manifest, regenerates `orchestrator/registry.md` and prints the orchestrator's `skills.external_dirs`; the builder applies it with `hermes config set`.
**Why:** one machine-readable source per squad that the builder, updates and the registry share. Generated files do not drift.
**Rejected alternatives:** a hand-edited `registry.md` (drifts from what is installed); the script editing config itself (scripts never edit Hermes config, D-023).

## D-025 · 2026-09-30 · Direct consultation between specialists

**Decision:** a specialist missing a datum first resolves it with what it has; if the datum is low impact it assumes, records the assumption and continues. Otherwise, only for pairs listed in `consult` of `squad.yaml`, it creates a support card (`CONSULT · <ID> · <question>`) assigned to the bot that owns the datum, links its own card as the child, and blocks with kind `dependency`. Its card resumes when the support card completes, with the answer in `## Parent task results`. The answering bot answers only from its outputs and project files and never consults in turn (depth 1). At most 2 consultations per task, one datum each. Contract: `base/02-architecture.md` §5.
**Why:** the question goes straight to the owner of the datum and the wake-up is native to Kanban, with no orchestrator run and no open chat needed.
**Rejected alternatives:** relaying through the orchestrator (extra runs, needs the user or an orchestrator session); `message_agent` (exists only in canonical Bot Chat sessions, not in Kanban workers); A2A (for crossing machine or framework boundaries; on one machine Hermes points to Kanban or delegation); a `kanban_comment` alone (does not wake anyone); the support card as a child of the asker's card (deadlock).

## D-024 · 2026-09-25 · English plans, one naming pattern, open-source repository

**Decision:** the repository is open source (`hermes-agent-squads`). Plans are in English; bots talk to each user in the user's language. Each squad has a short key (`jobs`, `marketing`) reused in its plan folder (`squads/<key>/`), its working folder (`projects/<key>/`), its profiles (`<key>-<role>`), its orchestration skill (`orchestration-<key>`) and its profile file (`<key>-profile.yaml`). Full table: `CONTRIBUTING.md`. Third-party skills used as a source for our own live in `squads/<key>/reference/`, with their scripts and licenses.
**Why:** English reaches more people; one pattern makes the repository easy to navigate for people and AIs; the reference folder lets the installer write the best skill for each bot from existing ones.

## D-023 · 2026-09-25 · In marketing, every deliverable is a piece

**Decision:** plans, reports, diagnoses, campaign concepts, guides, ideas, research and council sessions are pieces (`pieces/<ID>/card.md` and `v<N>/document.md`), like a post or a video. Idempotency keys include the role (`<ID>-<role>-<MODE>-v<N>-r<R>`), because the creative and the producer use the same mode on the same piece. Scripts are Python, not shell, and none edits the Hermes configuration: per-brand topics are added by the installer, and until then the brand uses the main chat.
**Why:** one contract for versions, review, delivery and the Studio. It fixes deliverables with no contract, colliding keys and a script that restarted the gateway it runs on.

## D-022 · 2026-09-25 · Agency skills: in-house per role, third-party per profile

**Decision:** the squad's own skills live in `{{ROOT}}/projects/marketing/skills/<role>/`, one flat folder per role; each profile lists only its folder and `common/` in `skills.external_dirs`. Third-party skills are installed per profile from the Hermes Skills Hub, only those for that role and the services the user chose: `coreyhaines31/marketingskills`, optional official Hermes skills and some from `anthropics/skills`. The squad's `AGENTS.md` has a path table so those skills use each brand's folders unedited.
**Why:** each bot's skill index stays short, third-party skills update with `hermes skills update` and pass the security scan, and nothing depends on `external_dirs` reading subfolders (undocumented).

## D-021 · 2026-09-25 · Vision through an auxiliary model

**Decision:** if a bot's model cannot see images, `auxiliary.vision` is configured in that profile instead of changing its model.
**Why:** Hermes documents it ("On text-only main models, falls back to an auxiliary vision model"), and each bot keeps its model and cost.

## D-020 · 2026-09-25 · Lightweight stack

**Decision:** no squad installs Docker, databases or self-hosted servers; the only always-on service is the Hermes gateway. Heavy jobs (video rendering, screenshots, builds, local voice, transcription) share the lock `{{ROOT}}/.heavy-lock`, managed by `{{ROOT}}/scripts/heavy_lock.py`, so only one runs at a time across bots and squads. One copy of each binary (system Chrome, FFmpeg, Node). On 8 GB machines: `max_in_progress: 2` and rendering with one worker.
**Why:** it must run on modest machines without overloading them. See `05-marketing-design.md` §10.

## D-019 · 2026-09-25 · In marketing, nothing goes out without approval

**Decision:** in Level 1 the user publishes by hand with the approved piece, the ready-to-post copy and a reminder. In Level 2, scripts create **drafts** in cloud services (Postiz Cloud or Buffer, Brevo or Kit, Cloudflare for landing pages); scheduling, sending or deploying requires the user's explicit confirmation for that action. Without it, nothing is spent on ads, no third party is answered and no creator is contacted.
**Why:** publishing is irreversible and affects the brand (D-006). Cloud services have their apps approved by each network and put no load on the machine.

## D-018 · 2026-09-25 · Motion with HyperFrames

**Decision:** video is composed in HTML with HyperFrames (Apache 2.0, official Hermes skill), with voice-over and subtitles. AI video (`video_generate`) is a Level 2 add-on if there is budget. Remotion only if the user already uses it and has a license.
**Why:** models write HTML better than React components; the license allows commercial use; it runs on 8 GB with tuning. See `05-marketing-design.md` §7.

## D-017 · 2026-09-25 · Studio: the files are the source of truth

**Decision:** each piece is a folder with `card.md` (YAML header) and versions `v1/`, `v2/`. Level 1 view: a static HTML page generated by a script, no server. Level 2: the Studio as a Hermes plugin (a Desktop page and a dashboard tab) with approve and request-changes buttons. Obsidian is an optional viewer over the same files.
**Why:** zero services in Level 1, nothing to migrate between levels, and it uses the Hermes plugin SDK instead of another app. See `05-marketing-design.md` §6.

## D-016 · 2026-09-25 · `production_model` for the producer

**Decision:** `marketing-producer` uses `production_model`: the model with the best results in design and motion with code the user has access to (September 2026 example: Claude Opus 5.5), or `main_model` if there is none better.
**Why:** in design and motion with code, the model makes a visible difference. If `kanban_create` accepts a model per task, it is limited to motion cards.

## D-015 · 2026-09-25 · Reviewer with its own card in marketing

**Decision:** as in the job search squad, `marketing-reviewer` gets its own card, reviews with 5 lenses in subagents (strategy, brand, persuasion and clarity, truthfulness and compliance, technical) and allows one correction round. Kanban's native review (`kanban_request_review`) is tested during installation.
**Why:** a proven pattern. Native review launches a software review skill by default, and replacing it is undocumented.

## D-014 · 2026-09-25 · Several projects: a folder per brand and a tenant

**Decision:** each agency project is a brand with a `brands/<slug>/` folder. Its tasks carry `--tenant <slug>` and the workspace of its folder. On Telegram or Discord each brand has its own topic or channel, set up by the installer; until it exists, the brand uses the main chat with its name.
**Why:** the same bots serve all brands, isolated by folder and filterable per brand in the visual Kanban. It is the pattern Hermes documents.

## D-013 · 2026-09-25 · The orchestrator is the agency director

**Decision:** there is no director bot. The orchestrator, with the `orchestration-marketing` skill, chats, onboards projects, launches flows, presents proposals and handles changes. The strategist breaks campaigns and weeks down into pieces.
**Why:** a single point of contact (D-004) with no extra hops. See `05-marketing-design.md` §2.
**Revisit if:** with many brands or clients the orchestrator gets overloaded → `marketing-director` bot.

## D-012 · 2026-09-25 · Marketing agency with 4 specialists

**Decision:** the twelve requested roles are covered by `marketing-strategist` (thinks and researches; the only one with web access), `marketing-creative` (ideas and words; no web), `marketing-producer` (builds with code: design, motion, landing pages, emails; the only one with a terminal) and `marketing-reviewer` (independent).
**Why:** each bot is justified by permissions, model or independence. A piece goes through 3 bots, and disciplines that share tools are not split. See `05-marketing-design.md` §1.

## D-011 · 2026-09-25 · One default model, the best in the user's catalog

**Decision:** by default every bot uses `main_model`: the most powerful model in the catalog of a fast, affordable provider, chosen during personalization (September 2026 example, OpenCode Go: MiMo V2.6 Pro, DeepSeek Flash 4.1, Muse Spark 1.3). Another model only when a capability is missing or makes a visible difference (D-016).
**Why:** near-frontier models are fast and cheap; generic cheaper models make results worse with no meaningful savings. Changing the model means changing one value.
Refined by D-021 (vision) and D-031 (per-bot choice by the user).

## D-010 · 2026-09-25 · Visible `~/Hermes` folder with the plans inside

**Decision:** the ecosystem lives in `~/Hermes/` (home folder, any OS), with `plans/` (this repository), `user/`, `orchestrator/` and `projects/<squad>/`. The user installs it by telling Hermes "read `~/Hermes/plans/START-HERE.md`".
**Why:** anyone can use it without pasting prompts or knowing paths. The disk root needs administrator permissions and is left out of backups.

## D-009 · 2026-09-25 · Fifth specialist: `jobs-applier`

**Decision:** a separate bot applies, only with explicit confirmation, and only on forms with no account and no CAPTCHA; otherwise it delivers a kit for applying by hand.
**Why:** different permissions (a browser that submits, plus form data). See `04-jobs-applier.md`.

## D-008 · 2026-09-25 · Company research as a subagent of the analyst

**Decision:** option C of `03-jobs-company-research.md`: a subagent with a clean context and company profiles reused for 30 days.
**Revisit if:** the analyst's spending is high or a page manipulates a decision → `jobs-researcher` bot.

## D-007 · 2026-09-25 · Handoff chain between specialists

**Decision:** each specialist creates the next one's task when it finishes, only if its result justifies it. The last one leaves the result in `outbox/ready/`, and a script (`deliver.py`, a cron job with no LLM) sends it to the user with `hermes send`.
**Why:** it works the same when a cron triggers it with nobody in the chat, no coordinator spends between stages, and there are no useless branches. It goes against the general Hermes recommendation that only the orchestrator hands out work; accepted because the chain is linear and fixed.
**Rejected alternatives:** orchestrator woken at each stage (needs an open chat session and one orchestrator run per stage); whole chain created up front with guards (empty runs).

## D-006 · 2026-09-25 · Automatic by default; confirmation only for what is irreversible

**Decision:** the user receives, through their messaging app, the link to each approved opening and the CV made for it. Applying, sending or writing to third parties requires their explicit confirmation for that action; with it, an authorized bot carries it out.
**Why:** maximum automation, minimum friction, no irreversible action without the user.

## D-005 · 2026-09-25 · Review with subagents, not bots

**Decision:** the job search reviewer is one bot that launches 5 subagents (`delegate_task`) with a clean context.
**Why:** it keeps independence (no subagent wrote the CV) without 6 profiles. `delegate_task` cannot call other profiles, and it does not need to.
**Revisit if:** a specific review is consistently weak → promote it to a bot.

## D-004 · 2026-09-25 · The orchestrator learns flows through skills

**Decision:** the orchestrator's SOUL is generic; each squad installs an `orchestration-<squad>` skill in a folder the orchestrator reads through `skills.external_dirs`, plus a row in `orchestrator/registry.md`.
**Why:** adding a squad does not require rewriting the orchestrator; each plan is self-contained.

## D-003 · 2026-09-25 · Personalization through a questionnaire + YAML profile

**Decision:** bot prompts are templates with `{{variables}}`. A base questionnaire (once per user) and one per squad produce the profiles. The AI confirms what it already knows (memory, CV) and asks only for what is missing.
**Why:** occupation, language, region and hardware differ per user; templates make the plans work for anyone.

## D-002 · 2026-09-25 · Maturity levels per squad

**Decision:** each squad defines a Level 1 that works automatically in one day (D-006). More automation (cron, ingest) and learning are Levels 2 and 3, turned on based on metrics.
**Why:** a more complex approach is not known to yield better results; it is measured before it is built.

## D-001 · 2026-09-25 · Job search: orchestrator + 4 specialists

**Decision:** the job search squad uses `jobs-scout`, `jobs-analyst`, `jobs-writer` and `jobs-reviewer`, coordinated by the base `orchestrator` (plus `jobs-applier`, D-009). Roles that do not need their own bot become skills (triage filter, positioning), subagents (reviewer lenses, company research) or scripts (CV rendering, ingest, link checking, reports).
**Why:** rule applied: a bot only if it needs independence, different permissions, a different model, or does not fit in context (`base/01-principles.md` §1.3). A person needs 5 to 20 good applications per week, not a recruiting operation. What produces quality is kept: a register of verified achievements with evidence, analyzing the opening before reading the CV, the writer never reviewing its own work, REJECT / WATCH / PURSUE decisions, a capped number of correction rounds, scripts for deterministic work, no LinkedIn automation. Result: 3 to 4 runs per opening, a linear chain where each step leaves a file, Level 1 in one day.
**Rejected alternatives:** 19 bots with a coordinator between every stage (about 20 runs per opening, 19 SOULs to maintain, context lost across 15 handoffs); a single bot (loses independent review and mixes web permissions with writing).
