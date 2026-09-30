# Squad: Web development agency

> One-page summary of the squad. The user reads it to decide whether to install it; the builder uses it as a starting point for `squad-install`. Requires the base.
> Everything specific to the user and to each site comes from [`01-personalization.md`](01-personalization.md).

## Purpose

A person who does not program gets their website or web app **built, reviewed and in production from their chat**. They describe the idea, approve a plain-language plan, look at a preview link and say "publish".

Several sites at once, each in its own GitHub repository and on the user's own Cloudflare (or Vercel) account. Nothing goes to production, touches DNS, deletes data or costs money without the user's explicit "yes" for that action.

## What the user sees

Each site has its own Telegram topic or Discord channel. A milestone arrives like this:

```text
🥐 Panadería Sol · Preview ready (milestone 1 of 3: home and menu)
https://m1-panaderia-sol.example.workers.dev
- Home with opening hours and the map
- Menu page, in Spanish and English
- Loads in 1.2 s on a phone; accessibility 100/100
📎 phone screenshot attached
Reply: "publish" · "change: …" · "bug: … + screenshot"
```

| The user says | What happens |
| --- | --- |
| `new site: a page for my bakery with the menu` | Onboarding questions (at most 5 per round), then a plan: pages, stack in one line, milestones, monthly cost |
| `ok` (to the plan) | Milestones are built, reviewed and deployed to a preview, one after another |
| `publish` | One confirmation question with what goes live and what it costs, then production and the live link |
| `change: add a gallery` · `bug: the form does not send + screenshot` | A new preview with the change or the fix |
| `connect my domain` | Plain instructions for what the user does at their registrar, a confirmation before any DNS change, then HTTPS on the domain |
| `rollback` | After one confirmation, the previous production version is back in about a minute |
| `status` · `pause <site>` · `resume` | Where each site is, or stop and restart automatic work on it |

## Levels

| Level | What it adds | When to move up |
| --- | --- | --- |
| **1 · Site in production** | Onboarding, spec, milestones built on branches, 5-lens review, preview per milestone, production with confirmation, domain, rollback. Data (D1, R2, KV) only if the spec needs it | - |
| **2 · Connected** | CMS, analytics, auth and payments integrations (Better Auth, Supabase, Stripe; the user creates every account), dependency update cron, performance monitoring | A site is live and the user edits content often, sells online, or needs to know traffic |

## Bots

| Bot | Does | Why it is a separate bot |
| --- | --- | --- |
| `orchestrator` (base) | Onboards sites, launches flows, asks for confirmations, delivers | Single point of contact |
| `web-architect` | Interview synthesis, spec, stack choice explained simply, milestones and acceptance criteria, change triage | The only one with `web` and an open-web `browser` (the reviewer's browser is limited to preview URLs): it reads untrusted pages and has no terminal |
| `web-developer` | Builds each milestone, tests locally, commits on a branch | Terminal without web and without credentials: code never mixes with untrusted pages or production keys. Its own model (stronger at code) |
| `web-advisor` | Read-only second opinion when the developer or the architect consults it: data model, auth, a repeated error, an irreversible migration, a repeated review finding | Its own stronger model and reasoning effort and a clean context, used only when consulted; no terminal, web or credentials |
| `web-reviewer` | Reviews each preview with 5 independent lenses | Independence: whoever built it never approves it |
| `web-deployer` | GitHub repo, branches, PRs, preview and production deploys, DNS, domains, secrets, rollback | The only one holding the Cloudflare token and GitHub access (different permissions). How much the GitHub token can do is agreed with the user at install |

## Stack

The architect chooses; the user only hears one line on why.

| Site type (`type`) | Examples | Stack |
| --- | --- | --- |
| `static` | Landing, blog, docs, portfolio | Astro (Starlight for docs) |
| `dynamic_seo` | E-commerce, catalog, CMS content | Next.js App Router, on Cloudflare via the OpenNext adapter |
| `saas` | Public part plus a very fast private app | TanStack Start (Router, Query, Form) |

Common: Tailwind v4, shadcn/ui, pnpm, Vitest, Playwright. Only if needed: Cloudflare D1, R2, KV with Better Auth, or Supabase; payments with Stripe (Level 2).

Hosting: **Cloudflare by default** (commercial use allowed on the free plan). Astro static fits the free plan. SSR apps (Next.js, TanStack Start) in production normally need Workers Paid, USD 5/month; the user hears this before the first production deploy. Vercel only if the user already uses it (Hobby is non-commercial only).

## Flows

| Flow | Chain | What reaches the user |
| --- | --- | --- |
| New site | orchestrator (onboarding) → deployer REPO and architect SPEC | Plan in plain language, with cost; waits for "ok" |
| Milestone | developer BUILD → deployer PREVIEW → reviewer REVIEW (FIX loop, 2 rounds max) | Preview link and summary |
| Publish | orchestrator confirmation → deployer PRODUCTION | Live link |
| Change | architect TRIAGE → milestone chain | New preview |
| Bug | developer BUILD (kind bug) → milestone chain | New preview with the fix |
| Domain | deployer DOMAIN (CHECK, then APPLY after confirmation) | Instructions, then the domain working with HTTPS |
| Rollback | orchestrator confirmation → deployer ROLLBACK | Previous version live |

**Never**: pay, create accounts, buy domains, delete data, deploy to production or change DNS without explicit confirmation for that action.

## What the computer needs

- Installed by the builder, with permission: Node 22+, pnpm, git, `gh`, `cf` (Cloudflare CLI), Wrangler (only through `npx`), Python 3.11+ venv with Playwright using the system Chrome, Lighthouse and axe-core.
- No Docker or servers: the only always-on service is the Hermes gateway. Builds and browser checks share the heavy-work lock.
- Accounts the user creates: GitHub and Cloudflare (both free). The builder guides creating a minimal-scope Cloudflare API token and a fine-grained GitHub token, both stored only in `web-deployer`'s `.env`. The user chooses whether the bot creates each site's repository (the token sees all repositories) or the user creates each empty one (the token sees only those).

## Files in this plan

| File | Contents |
| --- | --- |
| [`01-personalization.md`](01-personalization.md) | Agency questionnaire, per-site onboarding, `web-profile.yaml`, `settings.yaml` |
| [`02-architecture.md`](02-architecture.md) | Folders, IDs, flows, decisions, consultations, data contracts, Kanban, `AGENTS.md` |
| [`03-bots.md`](03-bots.md) | Configuration, SOULs, skills, orchestration skill |
| [`04-installation.md`](04-installation.md) | Installation by the builder and maintenance |
| [`05-scripts.md`](05-scripts.md) | `deliver.py`, `check_site.py` |
| [`06-testing-and-operations.md`](06-testing-and-operations.md) | Acceptance tests, operations, problems, metrics, Level 2 |
| [`squad.yaml`](squad.yaml) | Squad manifest |
