# Decisions

`D-` ids come from v1, `V-` are v2 architecture, `C-` are contracts. Append new decisions with id, date, decision, why.

## Carried over from v1

| Id | Decision (as it holds in v2) |
|---|---|
| D-001, D-012 | A bot exists only for a permission boundary, independence, a different reasoning effort, or context size; model-only differences use per-card `--model` (V-07). Roles that fit in another bot become skills, subagents or scripts. |
| D-002 | Level 1 of every squad works the first day. |
| D-003 | Manager interviews write `profile.md` / `brand.md` per project; no template variables. |
| D-005 | Multi-lens reviews run as `delegate_task` subagents with a clean context inside one reviewer bot, not as extra profiles. |
| D-006, D-019 | Automatic by default. Irreversible actions (apply, send, publish, production deploy, ad spend, contacting third parties) need the user's explicit OK for that action. |
| D-008 | Company research runs as a subagent with reused profiles (30 days), inside `jobs-scout` (V-17). |
| D-009 | `jobs-applier` stays separate and optional: simple forms only after the user's "apply", else a manual kit. |
| D-015, D-023 | Fix rounds are capped per review (web: `site.yaml` -> `automation.reviewer_rounds`; other squads: one). Every card carries an idempotency key that includes the stage or role. |
| D-016 | Design and motion quality is model-bound: those bots get the `frontend` or `design-pro` lane. |
| D-018 | HyperFrames is the default for motion. Remotion only with the licence question answered (`confirm`). |
| D-020 | Lightweight stack: no Docker, databases or self-hosted servers; the gateway is the only always-on service. |
| D-021 | Text-only main models get `auxiliary.vision` (the `vision` lane) instead of a model change. |
| D-024 | English for repo content; bots speak the user's language. Profiles are `<key>-<role>`; the manager is `<key>`. |
| D-025 | `kanban_comment` wakes nobody; a support card must never be a child of the asker's card (deadlock). |
| D-028 | Updates never overwrite personalization: `distribution_owned` plus `local/` (V-01). |
| D-029 | Upstream contributions only with the user's consent per PR and no user data (`contributing-upstream`). |
| D-030 | Web: Astro (static/content), Next.js App Router (dynamic SEO), TanStack Start (SaaS); Cloudflare default, Vercel if already used; `cf` over Wrangler; every site is a GitHub repo; token scope chosen by the user; only `web-deployer` holds credentials. |
| D-031 | The user picks model and effort per bot from connected providers only; `model_advisor.py` suggests (V-08). `web-backend` delegation runs on the `code-complex` lane (`delegation.model/provider/reasoning_effort`), and hard-problem cards pin that lane's model per card (`model`/`provider` on the kanban card). |
| D-033 | Every site repo ships a blocking quality gate (strict TS, Biome, Prettier for `.astro`, ESLint sonarjs/boundaries/security/functional/unicorn, jscpd, knip, offline osv-scanner, Vitest + Playwright 80%) as real config files and scripts (V-03). |
| D-034 | Named `cf` auth profiles per client folder; commands on such a site drop `CLOUDFLARE_API_TOKEN`/`ACCOUNT_ID` from their env. |
| D-035 | Visible work in progress: live localhost in the Desktop preview pane; screenshots on messaging surfaces, delivered through Bot Chat (V-05). |
| D-036 | Deploys ride on the vendors' own CLIs and their interactive logins (`gh auth login`, `cf auth login`, `wrangler login`; `vercel login` only for a project that targets Vercel). `web-deployer` declares `requires.apps: [cf, wrangler, gh]` and `squadctl doctor` reports each app installed and logged in, reading only the exit status; API tokens are the CI/headless path and are never passed into a profile's environment. |
| D-037 | (2026-10-20) Jobs 4.0: one Hermes Project per person; `profile.md` carries the personalisation (career stage, optional age never inferred, CEFR languages with flag/discard gap steps, market conventions, eligibility per country, scoring weights and bands, deal-breakers, writing style). Gates (scam, eligibility, language, location, role, seniority, contract, avoid) run before scoring; decisions, weights and bands are code (`score_analysis.py`), dimension scores are the model's judgment. |
| D-038 | (2026-10-20) Jobs portals are data-driven (`searching-portals/scripts/<portal>/portal.json` + a zero-dependency bun CLI, normalised by `portals.py`); only country-agnostic boards ship (LinkedIn public listings, freehire). Market boards are added per user with `adding-portals`. Browser access to `linkedin.com` stays blocked. |
| D-039 | (2026-10-20) Jobs documents stay HTML -> PDF/DOCX (WeasyPrint or Chromium, optional python-docx), never a TeX toolchain: ATS-safe single column, page budget from the market, relevance-weighted cutting, text-layer and layout checks (`verify_pdf.py`, `verify_layout.py`). |
| D-040 | (2026-10-20) Job mail runs through the Hermes Gmail connector on `jobs-writer` only (no web, no browser), read-only; it writes a proposal and the manager applies it after the user's yes. The pipeline view is an offline `reports/dashboard.html`, no third-party workspace. `jobs-followups` is a no-agent gate. |
| D-041 | (2026-10-22) Projects, libraries and tools come from their official installer, never from files or versions written by hand: one command (`site_base.py --site`) runs the stack's create CLI, re-adds the template's packages on their major with `pnpm add`, adds the squad's tools with no version, pins pnpm to its newest release 3 days old, and installs scanners with Homebrew. The release-age rule is 3 days (known npm attacks were pulled within hours to two days); a security fix never waits (`security_fix.py`: exact releases of the fix's own family, logged, removed once old); `quality:fresh` fails a version typed from memory. |
| D-042 | (2026-10-22) Supersedes the browser part of D-038 and D-040 (job mail moves in D-044). LinkedIn job listings come only from the public portal CLI; the signed-in browser reads hiring posts (scout), the user's own profile (writer) and Easy Apply forms (applier). Google Jobs is dropped: it renders only in a visible window. Computrabajo, elempleo and Talent.com are HTTP portals reading schema.org JSON-LD. Indeed stays out: its MCP server admits only the claude.ai client, so neither Hermes nor Claude Code can use it, and impersonating a client is refused. |
| D-043 | (2026-10-22) `auto_apply: auto` is a standing consent recorded once (`auto_apply_since`): an approved application with eligibility PASS and fit at or above `apply_threshold` is submitted without a per-opening apply, within `daily_apply_cap` and `daily_easy_apply_cap`. The user reads which CV went where; anything the squad cannot finish becomes a question or a kit. `try` and `ask` keep the per-opening consent. |
| D-044 | (2026-10-22) Job mail moves to a new optional bot `jobs-inbox` (Gmail connector, no web, no browser): the writer now drives a browser, and a connector never sits on a bot with `web` or `browser`. It also returns verification codes other bots ask for, one site and time window per card. |
| D-045 | (2026-10-23) A squad reaches the owner on a chat platform only through its manager: workers hand work to the manager on the board and never hold a platform token. `squadctl connect <bot> <platform>` binds one channel per bot (home channel, mention-free, channel prompt; Discord channels found or created by name with the bot's own token). Cron jobs marked `notify: true` (digests, board watch, reports) deliver to every connected channel whose token is present and fall back to Bot Chat otherwise; housekeeping jobs always stay on Bot Chat. `apply` and `upgrade` compute the same target, so they never move a digest away from the channel the owner reads. |
| D-046 | (2026-10-24) Jobs privacy and pace. `profile.md` `confidential_terms` is enforced in code at four points (renderer, profile copy checker, review aggregator, submit gate), because a rule in prose leaked client names into five applications and a LinkedIn draft. Outward texts have hard length caps (CV summary 50 words, 5/3 bullets, letter 250 words, LinkedIn About 1,500 and experience 600 characters): a person reads them in seconds, and the keywords fit in those lines. The manager asks only for missing facts, `apply`, public writes, RESET, payments and credentials; a user's correction is its own approval. |

## v2 architecture

- **V-01** The repo root is the builder's profile distribution (`hermes profile install`). `distribution.yaml` -> `distribution_owned` lists what install and update write; user state lives in `local/`.
- **V-02** One visible manager per squad; no global coordinator or registry.
- **V-03** Real, tested scripts, never prose scripts. Python wherever YAML/JSON/HTTP is involved; bash only for the shims and one-line cron wrappers.
- **V-04** Native Hermes Projects (per profile, `projects.db`) hold project folders; the builder never imposes a layout.
- **V-05** Results reach the user through kanban notify and `bot-chat:<manager>` cron delivery. A board run cannot message the user: a manager card that needs the user ends in `kanban_block(kind="needs_input", reason=<message>)`. A messaging chat (Discord, Telegram, ...) subscribed to the card gets the event; every other block, including chains filed from a Desktop or CLI session (their `tui` subscription is not read away from the desk), is posted by the `<key>-watch` cron (`scripts/board_watch.py`, no agent) to the manager's connected channel or Bot Chat, one file-carrying message per run.
- **V-06** Profiles are created with `--no-skills`, opt-out, then pruned to `hermes-agent`, squad skills and declared keeps. Squad skills are copied (sha marker), not linked.
- **V-07** A new profile only per permission boundary or reasoning effort; model-only differences use per-card `--model`.
- **V-08** Model ids live only in `scripts/data/model-roles.yaml` and `local/installed.yaml`. Lanes hold regex candidates per family.
- **V-09** `skill_lint.py` enforces the skill and SOUL budgets (`skill_lint.py --rules`).
- **V-10** `squadctl` is idempotent (plan, OK, apply), never uses `--clone`, never reads or prints secret values, exports profiles before uninstall or prune.
- **V-11** `always_disabled` toolsets live in `scripts/data/always-disabled.yaml` (C-07).
- **V-12** All bots are visible. Every bot has built-in memory unless its manifest sets `memory: false`; each SOUL names what its memory holds (job pitfalls and fixes, never secrets). `apply` removes only skills it installed (`skills/.squad-installed.json` or the `.squad-sha` marker); skills a bot wrote with `skill_manage` are reported as `learned` and kept. Desktop sections are stamped per bot on `ui_meta.hermes-bots` (`sectionId`/`sectionName`): every squad's manager under `Managers`, one section per squad for its workers; a bot belongs to exactly one section and the Desktop rebuilds the section records from the members (C-11).
- **V-14** Updates: zero-LLM `watch_upstream.py` gate, then a digest-lane agent; apply only through the builder with the user's OK.
  (2026-10-20) The gate also diffs the local Hermes docs mapped in `scripts/data/doc-sources.json`, because releases notes alone let the references drift; a full reference audit (read-only subagents) runs once per minor release.
- **V-15** Cron jobs are created with `hermes cron create`; no `jobs.json` is shipped.
- **V-16** Only managers create cards on another squad's board.
- **V-17** The scout does job analysis; analysis cards pin the review lane with per-card `--model`.
- **V-18** (2026-10-20) Local skill edits survive updates. Hermes's background skill review patches the skills a session used, shipped ones included, while `hermes profile update` and `squadctl apply` replaced shipped skills whole (a backup was the only trace). Both now merge three ways (`scripts/merge3.py`) against the copy shipped by the last update (`local/state/shipped/`, `local/state/skill-base/<bot>/`): an untouched file keeps the edit, separate changes combine, an overlap installs the new version and reports `Needs you` with the backup. Generic lessons still belong upstream; the merge only stops the silent loss.

## Contracts (2026-10-15)

- **C-01** `squad.schema.json` is strict (`additionalProperties: false` everywhere). Cross-field rules (the manager is the bot named after the squad key with role `manager` and title `<Name> manager`, exactly one manager, chain assignees exist, lanes exist, worker names prefixed by the key, at most 5 required bots, toolsets disjoint from `always_disabled`) live in `squadctl`, `skill_lint` (`manager-naming`) and `tests/test_contracts.py`.
- **C-02** Schema fields beyond the base manifest:
  - stage `lane` (analysis cards on the review lane);
  - bot `website_blocklist` (maps to `security.website_blocklist`);
  - `{id|name, confirm}` objects in `skills.keep` and `plugins.enable` for items that need the user's OK (Remotion licence, PolyForm NC, blender);
  - bot `requires.apps` (the CLIs a bot drives: `squadctl doctor` reports each one installed and, for the known ones, logged in — D-036);
  - cron `agent.reasoning` (digest at high);
  - optional top-level and `board` `description`.
  Stage names may start with a digit (`3d`). `board` is optional so `builder.yaml` validates.
- **C-03** Keep prefixes are `bundled:`, `official:<category>/<name>`, `hub:`, `local:`. No `link:` prefix: symlinks are not portable.
- **C-04** In `model-roles.yaml`, `family` is the model vendor family and `provider_pref` defaults to that family's providers. Anthropic candidates also list `copilot`, `github-copilot` and `openrouter`, which serve Claude models.
- **C-05** Every family has a candidate in every lane. "Cheapest model of the user's provider" is encoded as generic `-mini`/`-flash` regexes plus `fallback: cheapest`, because the cache has no prices.
- **C-06** Candidates with no match in any current fixture catalog stay as unverified regexes.
- **C-07** `always-disabled.yaml` drops `setup` and `start_chat` (retired toolset names) and `stt` (config-only, zero tool schemas). The other names are verified in `toolsets.py`; `a2a` is plugin-registered.
- **C-08** Lint `name-gerund` exempts `*-contract`, `hermes-platform` and the vetted marketing skills `marketing-plan`, `product-marketing`, `marketing-council`, `marketing-psychology`.
- **C-09** Lint semantics fixed by the fixtures:
  - a script that fails `py_compile` or `bash -n` is not also checked for `--help` or shellcheck;
  - the Spanish stopword list excludes English homographs;
  - "TOC" means a `Contents` heading in the first 20 lines;
  - `hermes-platform` uses the 80-line `index-lines` budget instead of `skill-lines`.
  Rule ids: `skill_lint.py --rules`.
- **C-10** `kanban` is listed in bot toolsets: `disabled_toolsets = always_disabled + (MANAGED - bot toolsets)` would otherwise disable it.
- **C-11** Manager naming and visibility: a squad has exactly one manager, profile name = the squad key, title `<Name> manager`; workers are `<key>-<role>`; the manifest field is `manager` and the role is `manager` (lane aliases resolve old lane names). All bots are visible and filed in Desktop sections `Managers` (managers) and `<Squad>` (workers) via `ui_meta.hermes-bots`. A bot with `optional: true` installs only with `squadctl plan/apply <key> --with <name>`; the 5-bot cap counts required bots and is cross-field because JSON Schema cannot count optional members.
- **C-12** (2026-10-15) Provider credentials: a user-installed provider plugin (builder profile first, then the root home) is copied into each bot that uses it, because Hermes loads user provider plugins per `HERMES_HOME`. A provider whose registry entry declares no API-key env var (OAuth, external process) gets no credentials note; `<PROVIDER>_API_KEY` is guessed only for providers the registry does not know. `squadctl inventory` documents existing profiles read-only (never `.env`/`auth.json`) and writes only under `local/`.
- **C-13** (2026-10-22) `shared_browser: true` on a bot: one signed-in headless Chromium per machine (`scripts/shared_browser.py`, a launchd service on 127.0.0.1:9333, Hermes's managed Chrome for Testing on `~/.hermes/browser-sessions/hermes`) reached through `browser.cdp_url`, with `browser.use_real_profile` off. A copy of the owner's browser profile fails whenever that browser is open (write lock on its login databases) and carries the owner's whole personal session; separate per-bot profiles cannot share one sign-in (Chromium locks a profile directory to one process) and copied cookies make Google end the session. The owner signs in in a plain visible window on the same directory (`shared_browser.py login`): Google refuses sign-in in a window with a debugging port. Hermes keeps a harness daemon and its tab per `browser_exec` session on a CDP override and never closes them, so the `shared-browser-tabs` plugin names one session per task, makes `new_tab` navigate in place, and at turn end stops that session's daemon and closes the tabs it held; a no-agent sweep on the squad manager every 3 hours closes what crashed runs left. The service blocks no host (2026-10-28, owner's call: bots use any site, Gemini included; the earlier `--host-resolver-rules` containment of Google apps is gone).
- **C-14** (2026-10-23) Every shipped bot with the `browser` toolset sets `shared_browser: true` (jobs, web, marketing), and squadctl no longer mirrors the owner's `browser.use_real_profile` onto any bot; an older mirror is turned off and its pin cleared on apply. The owner's own chats keep the setting. GitHub, Cloudflare and Vercel stay on their CLIs (`gh`, `cf`, `wrangler`, `vercel`), never in a browser. The sweep cron ships on every manager but runs once per machine: a lock and a 150-minute stamp make the other fires exit untouched.
- **C-15** (2026-10-25) The squad-hub Desktop plugin. A Desktop plugin can add panes, status-bar items, palette commands
  and settings, and can run RPCs, but it cannot filter the core profile rail or the Bots tab, so it hides both with CSS keyed
  on the app's own `data-slot` / `data-tree-tab` hooks, behind two settings, and removes the rules when it is disabled.
  Switching the window's profile is slow because the whole UI re-initialises for the new profile (the backend is already one
  multiplexed process), so the plugin never switches it: a chat opens as a tab under its own profile (`session.create` with
  the folder, then `openSession` with `intent: tab`). Chats come from one `/api/profiles/sessions?sources=desktop,tui,cli`
  call and `projects.list` per bot, never `projects.tree` (1.5 s for a bot with many kanban runs); `git worktree list` runs
  apart, per repo with a deadline, so a blocked folder cannot stall the list. Workers have no human chats, so "bots with
  human chats plus default, builder and managers" is the generic rule. The plugin is one file because a disk plugin loads
  uncompiled; it ships a UI string bundle in English and Spanish (a locale bundle, not repo prose). Bot faces are Lucide icons
  embedded in the file (ISC, licence beside it) rather than petdex pets or generated characters: gallery pets are user
  uploads with unclear rights and read alike at 20 px, while an icon says what the bot does. A squad with bots but no
  manager is grouped by its Desktop section, so a local squad can exist before its manager does without a manifest.
  Working/unread come from Desktop's live busy flags plus its own finished-while-away marker, because the backend
  unread flag alone misses a chat that ends while another is in view; a project with many folders lists those chats under its
  own row (open or closed) and keeps its folders folded, rather than expanding every folder.
  Floating sides and the `.env` handling moved to `squad-hub-plus` (C-16).
- **C-16** (2026-10-29) The catalog copy is SDK-only; `squad-hub-plus` holds the rest. The Hermes plugin catalog lists
  Desktop plugins that stay inside the plugin SDK (review of NousResearch/hermes-agent#144864), so `squad-hub` reaches
  the app only through host doors: `host.listPersistedSessions` per bot, `host.requestProfile` for `session.archive` /
  `session.title` / `projects.project_sessions`, the SDK unread functions instead of the app's private unread key, and
  `ctx.rest` against its own GET-only backend (`dashboard/plugin_api.py` on `hermes_cli.kanban_db`) for boards and
  cards, because there is no SDK door to another plugin's REST. Floating sides, git worktrees, the native folder picker,
  the worktree status Clean up reads and the Kanban page's board preselection live in the repo-only `squad-hub-plus`, which `squadctl apply` installs
  and enables beside `squad-hub` on the same managers (same opt-out), never through the catalog. The two talk through
  `squad-hub:<action>` DOM events: plus takes an action with `preventDefault()` and squad-hub then skips its SDK
  fallback (a typed folder path, the exact `git worktree …` command on the clipboard, the folder revealed in the file
  manager). Hiding the Bots tab and the profile selector, the `.env` double-click and the worktree PR chips were
  retired, not moved: they changed Hermes' own window without adding to the squads view. The crons pane is drawn with
  the SDK pieces Bot Mode's Cronjobs pane uses (`RowButton`, `Switch`, `relativeTime`, `nextRunOverdueMs`, the app's
  `cron` strings) so it follows Hermes' look; Bot Mode's `RoutinesPane` itself is not exported and is scoped to one
  bot. A feature moves back into the catalog copy as its upstream issue lands: auto-hide zones
  NousResearch/hermes-agent#146514, a worktree verb #146515.
