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

## v2 architecture

- **V-01** The repo root is the builder's profile distribution (`hermes profile install`). `distribution.yaml` -> `distribution_owned` lists what install and update write; user state lives in `local/`.
- **V-02** One visible manager per squad; no global coordinator or registry.
- **V-03** Real, tested scripts, never prose scripts. Python wherever YAML/JSON/HTTP is involved; bash only for the shims and one-line cron wrappers.
- **V-04** Native Hermes Projects (per profile, `projects.db`) hold project folders; the builder never imposes a layout.
- **V-05** Results reach the user through kanban notify and `bot-chat:<manager>` cron delivery. A board run cannot message the user: a manager card that needs the user ends in `kanban_block(kind="needs_input", reason=<message>)`. The chat that filed the chain gets the event; for cron-filed chains, the `<key>-watch` cron (`scripts/board_watch.py`, no agent) posts it to the manager's Bot Chat.
- **V-06** Profiles are created with `--no-skills`, opt-out, then pruned to `hermes-agent`, squad skills and declared keeps. Squad skills are copied (sha marker), not linked.
- **V-07** A new profile only per permission boundary or reasoning effort; model-only differences use per-card `--model`.
- **V-08** Model ids live only in `scripts/data/model-roles.yaml` and `local/installed.yaml`. Lanes hold regex candidates per family.
- **V-09** `skill_lint.py` enforces the skill and SOUL budgets (`skill_lint.py --rules`).
- **V-10** `squadctl` is idempotent (plan, OK, apply), never uses `--clone`, never reads or prints secret values, exports profiles before uninstall or prune.
- **V-11** `always_disabled` toolsets live in `scripts/data/always-disabled.yaml` (C-07).
- **V-12** All bots are visible; workers have no memory and run one card at a time (`kanban.max_in_progress_per_profile: 1` in the gateway root config). Desktop sections are stamped per bot on `ui_meta.hermes-bots` (`sectionId`/`sectionName`): every squad's manager under `Managers`, one section per squad for its workers; a bot belongs to exactly one section and the Desktop rebuilds the section records from the members (C-11).
- **V-13** The `studio` squad owns rendered and standalone assets; web-frontend owns interactive code inside a site.
- **V-14** Updates: zero-LLM `watch_upstream.py` gate, then a digest-lane agent; apply only through the builder with the user's OK.
- **V-15** Cron jobs are created with `hermes cron create`; no `jobs.json` is shipped.
- **V-16** Only managers create cards on another squad's board.
- **V-17** The scout does job analysis; analysis cards pin the review lane with per-card `--model`.

## Contracts (2026-10-15)

- **C-01** `squad.schema.json` is strict (`additionalProperties: false` everywhere). Cross-field rules (the manager is the bot named after the squad key with role `manager` and title `<Name> manager`, exactly one manager, chain assignees exist, lanes exist, worker names prefixed by the key, at most 5 required bots, toolsets disjoint from `always_disabled`) live in `squadctl`, `skill_lint` (`manager-naming`) and `tests/test_contracts.py`.
- **C-02** Schema fields beyond the base manifest:
  - stage `lane` (analysis cards on the review lane);
  - bot `website_blocklist` (maps to `security.website_blocklist`);
  - `{id|name, confirm}` objects in `skills.keep` and `plugins.enable` for items that need the user's OK (Remotion licence, PolyForm NC, blender);
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
