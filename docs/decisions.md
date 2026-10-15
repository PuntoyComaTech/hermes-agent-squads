# Decisions

Condensed record for v2. `D-NNN` ids come from the v1 log (`00-evaluation/02-decisions.md`, removed at cutover); `V-NN` are v2 architecture decisions (`squads-plan.md`); `C-NN` are batch 0 contract decisions. New structural decisions append here with id, date, decision, why.

## Carried over from v1 (still valid)

| Id | Decision (as it holds in v2) |
|---|---|
| D-001, D-012 | A bot exists only for a permission boundary, independence, a different model/effort, or context size. Roles that fit in another bot become skills, subagents or scripts. |
| D-002 | Level 1 of every squad works the first day; more automation is added when metrics justify it. |
| D-005 | Multi-lens reviews run as `delegate_task` subagents with a clean context inside one reviewer bot, not as extra profiles. |
| D-006, D-019 | Automatic by default. Irreversible actions (apply, send, publish, production deploy, ad spend, contacting third parties) need the user's explicit OK for that action. |
| D-008 | Company research runs as a subagent with reused profiles (30 days); now inside `jobs-scout` (V-17). |
| D-009 | `jobs-applier` stays separate and optional: simple forms only after the user's "apply", else a manual kit. |
| D-015, D-023 | One correction round per review; every card carries an idempotency key that includes the stage/role. |
| D-016 | Design and motion quality is model-bound: those bots get the `design` lane. |
| D-018 | HyperFrames is the default for motion. Remotion only with the licence question answered (C-02). |
| D-020 | Lightweight stack: no Docker, databases or self-hosted servers; the gateway is the only always-on service. |
| D-021 | Text-only main models get `auxiliary.vision` (the `vision` lane) instead of a model change. |
| D-024 | English for repo content; bots speak the user's language. Profiles are `<key>-<role>`; the lead is `<key>`. |
| D-025 (facts) | `kanban_comment` wakes nobody; a support card must never be a child of the asker's card (deadlock). |
| D-028 (goal) | Updates never overwrite personalization. Mechanism is now `distribution_owned` + `local/` (V-01). |
| D-029 | Upstream contributions only with the user's consent per PR and no user data (`contributing-upstream`). |
| D-030 | Web: Astro (static/content), Next.js App Router (dynamic SEO), TanStack Start (SaaS); Cloudflare default, Vercel if already used; `cf` over Wrangler; every site is a GitHub repo; token scope chosen by the user; only `web-deployer` holds credentials. |
| D-031 (core) | The user picks model and effort per bot from connected providers only. Now suggested by `model_advisor.py` (V-08). |
| D-033 | Every site repo ships a blocking quality gate (strict TS, Biome, Prettier for `.astro`, ESLint sonarjs/boundaries/security/functional/unicorn, jscpd, knip, offline osv-scanner, Vitest + Playwright 80%). Now real config files and scripts, not prose (V-03). |
| D-034 | Named `cf` auth profiles per client folder; commands on such a site drop `CLOUDFLARE_API_TOKEN`/`ACCOUNT_ID` from their env. |
| D-035 (core) | Visible work in progress: live localhost in the Desktop preview pane; screenshots on messaging surfaces. Delivered through Bot Chat (V-05), not an outbox. |

## Superseded v1 decisions

| Id | Replaced by |
|---|---|
| D-004, D-013, D-026, D-027 | V-02 one lead per squad; the builder is a distribution, not a base bot. |
| D-007 | V-05 kanban chains and notify; `deliver.py` and the outbox are gone. |
| D-010, D-014, D-022 | V-04 native Projects; V-06 per-profile squad skills. |
| D-011 | V-08 lanes. |
| D-017 | Kanban boards; "Studio" now names the V-13 squad. |
| D-003 | Lead interviews write `profile.md` / `brand.md` per project; no template variables. |
| D-031 (advisor bot) | `web-backend` delegation on the `advisor` lane. Hermes now has `delegation.model/provider/reasoning_effort`, which removes D-031's objection. |
| D-032 (kanban) | C-10. |

## v2 architecture

- **V-01** The repo root is the builder's profile distribution (`hermes profile install`). `distribution_owned` ships SOUL.md, config.yaml, skills, scripts, squads; user state lives in `local/`.
- **V-02** One visible lead per squad replaces the global orchestrator and registry.
- **V-03** Real, tested scripts replace prose scripts. Python wherever YAML/JSON/HTTP is involved; bash only for the `squadctl` shim and one-line cron wrappers.
- **V-04** Native Hermes Projects (per profile, `projects.db`) replace `~/Hermes/projects/...`.
- **V-05** Kanban notify and `bot-chat:<lead>` delivery replace `deliver.py` and the outbox.
- **V-06** Profiles are created with `--no-skills`, opt-out, then pruned to `hermes-agent`, squad skills and declared keeps. Squad skills are copied (sha marker), not linked.
- **V-07** A new profile only per permission boundary or reasoning effort; model-only differences use per-card `--model`.
- **V-08** Model ids live only in `scripts/data/model-roles.yaml` and `local/installed.yaml`. Lanes hold regex candidates per family.
- **V-09** Skill and SOUL budgets of plan §2.4 are enforced by `skill_lint.py`.
- **V-10** `squadctl` is idempotent (plan, OK, apply), never uses `--clone`, never reads or prints secret values, exports profiles before uninstall or prune.
- **V-11** `always_disabled` toolsets come from the Omnicommerce reference (C-07).
- **V-12** Workers are hidden, have no memory and run one card at a time; leads are visible with board notifications.
- **V-13** New `studio` squad owns rendered and standalone assets; web-frontend owns interactive code inside a site.
- **V-14** Updates: zero-LLM `watch_upstream.py` gate, then a digest-lane agent; apply only through the builder with the user's OK.
- **V-15** Cron jobs are created with `hermes cron create`; no `jobs.json` is shipped.
- **V-16** Only leads create cards on another squad's board.
- **V-17** The jobs analyst merges into the scout; analysis cards pin the review lane with per-card `--model`.

## Batch 0 contracts (2026-10-15)

- **C-01** `squad.schema.json` is strict (`additionalProperties: false` everywhere). Cross-field rules (lead exists with role lead, chain assignees exist, lanes exist, worker names prefixed by the key, toolsets disjoint from `always_disabled`) live in `squadctl` and `tests/test_contracts.py`.
- **C-02** Fields added to plan §3.1, each required by another plan section:
  - stage `lane` (§4.3 analysis cards on the review lane);
  - bot `website_blocklist` (§4.3, maps to `security.website_blocklist`);
  - `{id|name, confirm}` objects in `skills.keep` and `plugins.enable` for items that need the user's OK (§4.4 Remotion licence, PolyForm NC, blender);
  - cron `agent.reasoning` (§5.4 digest at high);
  - optional top-level and `board` `description`.
  Stage names may start with a digit (`3d`). `board` is optional so `builder.yaml` validates.
- **C-03** Keep prefixes are `bundled:`, `official:<category>/<name>`, `hub:`, `local:`. Omnicommerce's `link:` is dropped: personal symlinks are not portable.
- **C-04** In `model-roles.yaml`, `family` is the model vendor family and `provider_pref` defaults to that family's providers. Following the plan, `copilot` is in the openai family, so a copilot-only user gets GPT-5.4 for design even though copilot also serves Claude Opus 5.5. **Open:** add `copilot` to the Claude candidates' `provider_pref`?
- **C-05** Google candidates were added to lead, code, advisor and copy, so every family has a candidate in every lane. "Cheapest model of the user's provider" is encoded as generic `-mini`/`-flash` regexes plus `fallback: cheapest`, because the cache has no prices.
- **C-06** Gemini 3.1 Pro appears in no current fixture catalog; its regex is kept per the plan and is unverified. GPT-5.4 is kept per the plan although copilot lists newer GPT ids.
- **C-07** `always-disabled.yaml` drops `setup` and `start_chat` (retired toolset names) and `stt` (config-only, zero tool schemas). The other 16 names were verified in `toolsets.py`; `a2a` is plugin-registered.
- **C-08** Lint `name-gerund` exempts `*-contract`, `hermes-platform` and the vetted marketing skills the plan names (`marketing-plan`, `product-marketing`, `marketing-council`, `marketing-psychology`).
- **C-09** Lint semantics fixed by the fixtures:
  - a script that fails `py_compile` or `bash -n` is not also checked for `--help` or shellcheck;
  - the Spanish stopword list excludes English homographs;
  - "TOC" means a `Contents` heading in the first 20 lines;
  - `hermes-platform` uses the 80-line `index-lines` budget instead of `skill-lines`.
  Rule ids are in `tests/fixtures/skills/bad/rules.yaml`.
- **C-10** `kanban` is listed in bot toolsets (presets L and W), reversing D-032: `disabled_toolsets = always_disabled ∪ (managed − toolsets)` would otherwise disable it.
