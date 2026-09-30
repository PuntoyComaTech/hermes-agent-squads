# Web squad: bots, stack, provider, CLI, advisor and GitHub access

2026-09-30 · Squad: web · Outcomes: D-030 and D-031 in `02-decisions.md`

## 1. How many bots?

| Option | Pros | Cons |
| --- | --- | --- |
| **3 · architect, developer (also deploys), reviewer** | One handoff fewer | Cloud and GitHub credentials sit next to arbitrary build and dependency scripts |
| **4 · architect, developer, reviewer, deployer** | Each bot has a base reason: the only bot on the web never runs code; the bot that runs code holds no credentials; review is independent | No stronger second opinion without paying the top model on every developer turn |
| **5 · the four plus `web-advisor`** (chosen) | The same reasons, plus a read-only advisor on its own stronger model, used only when consulted (§5) | One more profile to configure; each consultation is a Kanban round trip |
| **5 · the four plus a designer** | Focused design SOUL | Same tools as the developer (code, browser preview, vision); one more handoff per milestone. Design comes from a marketing brand's `DESIGN.md` or the site's own |

## 2. Stack per site type

| Type | Stack | Pros | Cons |
| --- | --- | --- | --- |
| Static or content (landing, blog, docs, portfolio) | Astro (Starlight for docs) | Ships almost no JavaScript; fits the Cloudflare free plan | Weak for app-like interactivity |
| Dynamic, public, SEO (e-commerce, catalog, CMS) | Next.js App Router, on Cloudflare through OpenNext | Largest ecosystem; server rendering for SEO | Adapter layer on Cloudflare; SSR usually needs Workers Paid |
| SaaS with a public part and a fast private app | TanStack Start (Router, Query, Form) | Type-safe routing and data loading; fast client app | Younger ecosystem; SSR usually needs Workers Paid |

Common to all: Tailwind v4, shadcn/ui, pnpm, Vitest, Playwright. Data and auth only if needed: Cloudflare D1/R2/KV with Better Auth, or Supabase; payments with Stripe. One matrix keeps the bots generic: the task pins one stack skill.

## 3. Cloudflare or Vercel?

| | Cloudflare (default) | Vercel (only if the user already uses it) |
| --- | --- | --- |
| Free plan | Commercial use allowed. Workers Free: 100,000 requests/day, 10 ms CPU per request, static asset requests free and unlimited | Hobby: non-commercial use only |
| Paid | Workers Paid: USD 5/month, 10M requests, CPU up to 5 min | Required for any commercial site |
| Fit | Astro static runs free; Next.js and TanStack Start SSR in production normally need Workers Paid (the bot says so before the first production deploy) | Native Next.js support |
| Extras | DNS, domains, D1, R2, KV, WAF from one account and one CLI | |

## 4. `cf` or Wrangler?

| | `cf` (chosen) | Wrangler |
| --- | --- | --- |
| Coverage | The whole Cloudflare API: projects, dev, build, deploy, DNS, domains, zones, D1, R2, KV, WAF | Workers-centric |
| For agents | JSON output; `cf cli search "<task>"` finds the command | |
| Maturity | Open beta since 2026-09-28 | Stable |
| Gaps | No individual secrets, no live log tailing: Wrangler covers those two | |

Rules: `cf cli search` before any Wrangler use; `cf migrate --dry-run` then `cf migrate` before `cf dev/build/deploy` in a Wrangler-configured project.

## 5. Advisor for the developer and the architect

| Option | Pros | Cons |
| --- | --- | --- |
| **A · `web-advisor` bot, consulted with a CONSULT card** (chosen) | Its own model and reasoning effort as a normal profile (`agent.reasoning_effort`); a clean context; read-only toolsets (`file`, `skills`); the standard consultation protocol with no new mechanism; costs only when consulted | A Kanban round trip per question (the dispatcher checks every 60 s); it counts toward the 2 consultations per task; no terminal, so the asker pastes the error output |
| **B · `delegate_task` subagent routed with `delegation.model`** | No extra profile | The subagent inherits the developer's toolsets, terminal included; subagents have no documented reasoning-effort key (only raw provider settings in `delegation.request_overrides`) |
| **C · Mixture of Agents preset** (developer as aggregator, advisor as reference) | Second opinion on every turn | References do not see tool results; cost on every turn |
| **D · Developer on the strongest model** | No extra mechanism | Pays the top price for routine edits |

Triggers and limits: D-031.

## 6. GitHub token scope for `web-deployer`

No default: at install the deployer checks with `gh` what the token can do (who, which repos, whether it can create repos) and the builder explains both options in plain words; the deployer repeats the check at each site's onboarding (REPO).

| Option | Pros | Cons |
| --- | --- | --- |
| **`bot_creates` · All repositories plus Administration write** | Zero manual steps per site | The token can read, write and reconfigure every repository of the owner |
| **`user_creates` · The user creates each empty repo and adds it to the token** | The token sees only the site repos | Two minutes of guided clicks per new site; onboarding waits for them |

The choice is `repo_mode` in `web-profile.yaml`; the user can switch later through the builder. D-030.
