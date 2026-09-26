# Decision log

One entry per structural decision. The most recent one is at the top.

---

## D-024 · 2026-09-25 · English plans, one naming pattern, open-source repository

**Decision:** the repository is published as open source (`hermes-agent-squads`). All plans are written in English, while the bots always talk to each user in the user's preferred language. Every name follows one pattern: each squad has a short key (`jobs`, `marketing`) reused in its plan folder (`squads/<key>/`), its folder on the user's computer (`projects/<key>/`), its profiles (`<key>-<role>`), its orchestration skill (`orchestration-<key>`) and its profile file (`<key>-profile.yaml`). The full table is in `CONTRIBUTING.md`. Third-party skills used as a source for our own skills live in `squads/<key>/reference/`, with their scripts and licenses.
**Why:** English reaches more people; a single pattern makes the repository easy to navigate for any person or AI; the reference folder lets the installer AI write optimal skills for each bot from the best existing ones.

## D-023 · 2026-09-25 · In marketing, every deliverable is a piece

**Decision:** plans, reports, diagnoses, campaign concepts, guides, ideas, research and council sessions are stored as pieces (`pieces/<ID>/card.md` and `v<N>/document.md`), just like a post or a video. Idempotency keys include the role (`<ID>-<role>-<MODE>-v<N>-r<R>`), because the creative and the producer use the same mode on the same piece. Scripts are written in Python, not shell, and none of them edits the Hermes configuration: per-brand topics are added by the installer AI, and until then the brand uses the main chat.
**Why:** a single contract for versions, review, delivery and the Studio. It came out of the independent review of the plan, which found deliverables with no contract, keys that collided and a script that restarted the gateway it runs on.

## D-022 · 2026-09-25 · Agency skills: in-house ones per role and third-party ones per profile

**Decision:** the squad's own skills live in `{{ROOT}}/projects/marketing/skills/<role>/`, one flat folder per role, and each profile lists only its own folder and `common/` in `skills.external_dirs`. Third-party skills are installed in each profile from the Hermes Skills Hub, only those for that role and based on the services the user chose: `coreyhaines31/marketingskills`, the optional official Hermes skills and some from `anthropics/skills`. The squad's `AGENTS.md` includes a path table so those skills use each brand's folders without editing the skills.
**Why:** each bot's skill index stays short, third-party skills are updated with `hermes skills update` and go through the security scan, and there is no need to rely on `external_dirs` reading subfolders, because that is not documented.

## D-021 · 2026-09-25 · Vision through an auxiliary model

**Decision:** if the `main_model` cannot see images, `auxiliary.vision` is configured in the profile that needs it, instead of changing its model. This refines D-011: "another model only if a capability is missing" is solved first with the Hermes auxiliary models.
**Why:** the Hermes documentation provides for it ("On text-only main models, falls back to an auxiliary vision model"), and this way each bot keeps its model and its cost.

## D-020 · 2026-09-25 · Lightweight stack

**Decision:** no squad installs Docker, databases or self-hosted servers; the only always-on service is the Hermes gateway. Heavy jobs (video rendering, screenshots, local voice, transcription) share a lock at `{{ROOT}}/.heavy-lock`, managed by the shared script `{{ROOT}}/scripts/heavy_lock.py`, so that only one runs at a time even when different bots or squads request them. There is a single copy of each binary (system Chrome, FFmpeg, Node). On 8 GB machines: `max_in_progress: 2` and rendering with a single worker.
**Why:** the ecosystem must run on any computer, including modest machines, without overloading it. See `05-marketing-design.md` §10.

## D-019 · 2026-09-25 · In marketing, nothing goes out without approval

**Decision:** in Level 1 the user publishes by hand: they get the approved piece, the ready-to-post copy and a reminder. In Level 2, scripts create **drafts** in cloud services (Postiz Cloud or Buffer for social media, Brevo or Kit for email, Cloudflare for landing pages), and scheduling, sending or deploying requires the user's explicit confirmation for that action. Without it, nothing is ever spent on ads, no third party is answered and no creator is contacted.
**Why:** publishing is irreversible and affects the brand (D-006). Cloud services already have their apps approved by each network and put no load on the machine.

## D-018 · 2026-09-25 · Motion with HyperFrames

**Decision:** the agency's video is composed in HTML with HyperFrames (Apache 2.0, official Hermes skill), with voice-over and subtitles. AI video generation (`video_generate`) is a Level 2 add-on, if there is budget. Remotion only if the user already uses it and has a license.
**Why:** models write HTML better than React components; the license does not limit commercial use, and it runs on 8 GB with some tuning. See `05-marketing-design.md` §7.

## D-017 · 2026-09-25 · Studio: the files are the source of truth

**Decision:** each piece is a folder with `card.md` (YAML header) and versions `v1/`, `v2/`… The Level 1 view is a static HTML page generated by a script, with no server. In Level 2 the Studio is added as a Hermes plugin (a Desktop page and a dashboard tab) with buttons to approve and to request changes. Obsidian remains an optional viewer over the same files.
**Why:** zero services in Level 1, no migrations when moving up a level, and it uses the Hermes plugin SDK instead of another app. See `05-marketing-design.md` §6.

## D-016 · 2026-09-25 · `production_model` for the producer

**Decision:** `marketing-producer` uses `production_model`: the model with the best results in design and motion with code that the user has access to (in September 2026, for example, Claude Opus 5.5). If they have no better one, it is the `main_model`. The other bots use the main model.
**Why:** it is the capability exception that D-011 provides for: in design and motion with code, the model makes a visible difference. If `kanban_create` accepts a model per task, it is limited to the motion cards.

## D-015 · 2026-09-25 · Reviewer with its own card in marketing

**Decision:** as in the job search squad, `marketing-reviewer` gets its own card, reviews with 5 lenses in subagents (strategy, brand, persuasion and clarity, truthfulness and compliance, technical) and allows a single correction round. Kanban's native review (`kanban_request_review`) is tested during installation.
**Why:** a proven pattern. Native review launches a software review skill by default, and how to replace it is not documented.

## D-014 · 2026-09-25 · Several projects: a folder per brand and a tenant

**Decision:** in the agency, each project is a brand, with a `brands/<slug>/` folder. All its tasks carry `--tenant <slug>` and the workspace of its folder. If the user uses Telegram or Discord, each brand has its own topic or channel; the topic is set up by the installer AI, and until it exists, the brand uses the main chat with its name.
**Why:** the same bots serve all brands, with isolation by folder and a per-brand filter in the visual Kanban. It is the pattern Hermes documents.

## D-013 · 2026-09-25 · The orchestrator is the agency director

**Decision:** there is no director bot. The orchestrator, with the `orchestration-marketing` skill, chats, onboards projects, launches flows, presents proposals and handles changes. Breaking campaigns and weeks down into pieces is done by the strategist.
**Why:** it keeps a single point of contact (D-004) with no extra hops. See `05-marketing-design.md` §2.
**Revisit if:** with many brands or clients the orchestrator gets overloaded → `marketing-director` bot.

## D-012 · 2026-09-25 · Marketing agency with 4 specialists

**Decision:** the twelve requested roles are covered by `marketing-strategist` (thinks and researches; the only one with web access), `marketing-creative` (ideas and words; no web), `marketing-producer` (builds with code: design, motion, landing pages, emails; the only one with a terminal) and `marketing-reviewer` (independent).
**Why:** each bot is justified by permissions, model or independence. A piece goes through 3 bots, and disciplines that use the same tools are not split up. See `05-marketing-design.md` §1.

---

## D-011 · 2026-09-25 · A single model, the best in the user's catalog

**Decision:** model classes (premium, writing, standard, cheap) are removed. All bots use `main_model`: the most powerful model at that moment in the catalog of a fast, affordable provider, chosen during personalization (example, September 2026, OpenCode Go: MiMo V2.6 Pro, DeepSeek Flash 4.1, Muse Spark 1.3). Another model is used only if a capability the main one lacks is needed (vision).
**Why:** today there are near-frontier models that are fast and cheap; dropping to generic models makes results worse with no meaningful savings. It is also easier to personalize and maintain: changing the model means changing one value.

## D-010 · 2026-09-25 · Visible `~/Hermes` folder with the plans inside

**Decision:** the whole ecosystem lives in `~/Hermes/` (home folder, any operating system), with `plans/` (this repository), `user/`, `orchestrator/` and `projects/<squad>/`. The user installs it by telling Hermes "read `~/Hermes/plans/START-HERE.md`".
**Why:** so anyone can use it without pasting prompts or knowing about paths. The disk root is not used because it requires administrator permissions and is left out of backups.

## D-009 · 2026-09-25 · Fifth specialist: `jobs-applier`

**Decision:** a separate bot applies, only with explicit confirmation, and only on forms with no account and no CAPTCHA; if it cannot, it delivers a kit for applying by hand.
**Why:** see `04-jobs-applier.md`. Different permissions (a browser that submits + form data).

## D-008 · 2026-09-25 · Company research as a subagent of the analyst

**Decision:** option C of `03-jobs-company-research.md`: a subagent with a clean context and company profiles reusable for 30 days.
**Revisit if:** the analyst's spending is high or a page manipulates a decision → `jobs-researcher` bot.

## D-007 · 2026-09-25 · Handoff chain between specialists

**Decision:** each specialist creates the next one's task when it finishes, only if its result justifies it. The last one leaves the result in `outbox/ready/`, and a script (`deliver.py`, a cron job with no LLM) sends it to the user with `hermes send`.
**Why:** it works the same when a cron job triggers it with nobody in the chat; it avoids a coordinator spending between stages, and there are no useless branches. It goes against the general Hermes recommendation that only the orchestrator hands out work; it is accepted because the chain is linear and fixed.
**Rejected alternatives:** orchestrator woken up at each stage (depends on an open chat session and spends one orchestrator run per stage); whole chain created up front with guards (empty runs).

## D-006 · 2026-09-25 · Automatic by default; confirmation only for what is irreversible

**Decision:** the user only receives, through their messaging app, the link to each approved opening and the CV made for it. Applying, sending or writing to third parties requires their explicit confirmation for that action; with it, an authorized bot carries it out. It replaces the earlier rule "the human carries out anything irreversible" and, in the job search squad, replaces the "assisted" Level 1 (the user picked from a list).
**Why:** maximum automation and minimum friction for the user.

## D-005 · 2026-09-25 · Review with subagents, not bots

**Decision:** the job search reviewer is a single bot that launches 5 subagents (`delegate_task`) with a clean context.
**Why:** it keeps independence (no subagent wrote the CV) without 6 profiles. `delegate_task` cannot call other profiles, but it does not need to.
**Revisit if:** a specific review is consistently weak → promote it to a bot.

## D-004 · 2026-09-25 · The orchestrator learns flows through skills

**Decision:** the orchestrator's SOUL is generic; each squad installs an `orchestration-<squad>` skill in a folder the orchestrator reads through `skills.external_dirs`, and a row in `orchestrator/registry.md`.
**Why:** adding a squad does not require rewriting the orchestrator; each plan is self-contained.

## D-003 · 2026-09-25 · Personalization through a questionnaire + YAML profile

**Decision:** the bots' prompts are templates with `{{variables}}`. A base questionnaire (once per user) and one per squad produce the profiles. The AI confirms what it already knows (memory, CV) and only asks for what is missing.
**Why:** the original plan hard-coded occupation, language, region and hardware; this way it works for anyone.

## D-002 · 2026-09-25 · Maturity levels per squad

**Decision:** each squad defines a Level 1 that works in one day (updated by D-006: Level 1 is now automatic). Automation (cron, ingest) and learning are Levels 2 and 3, which are turned on based on metrics.
**Why:** we do not know whether the complex approach yields better results; it has to be measured before it is built.

## D-001 · 2026-09-25 · From 19 bots to orchestrator + 4 specialists

**Decision:** the job search squad uses `jobs-scout`, `jobs-analyst`, `jobs-writer` and `jobs-reviewer`, coordinated by the base `orchestrator`.
**Why:** see `01-jobs-plan-review.md`. Rule applied: a bot only if it needs independence, different permissions, a different model, or does not fit in context.
**Rejected alternatives:** 19 bots (cost, fragility, maintenance); a single bot (loses independent review and mixes web permissions with writing).
