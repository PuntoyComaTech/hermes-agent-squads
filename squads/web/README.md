# Squad: Web

> One-page summary: the user reads it to decide whether to install the squad; the builder starts from it. `squad.yaml` is the manifest, `scripts/` the deterministic tools, `skills/` what the bots load.

## Purpose

Someone who does not program gets their website or web app **built, reviewed and live, from their chat**. They describe the site, approve a plain-language plan, look at a preview and say "publish".

Several sites at once, each its own project folder and its own GitHub repository. Nothing reaches production, DNS, money or data without the user's explicit answer for that action.

## What the user sees

```text
🥐 Panadería Sol · preview ready (milestone 1 of 3: home and menu)
https://m1-panaderia-sol.example.workers.dev
- Home with opening hours and the map
- Menu page, in Spanish and English
- Loads in 1.2 s on a phone; no accessibility errors
📎 screenshot attached
Reply: "publish" · "change: …" · "bug: … + screenshot"
```

| The user says | What happens |
|---|---|
| `new site: a page for my bakery with the menu` | Questions in rounds of at most 5 (never technical), then a plan: pages, stack in one line, milestones, monthly cost |
| `ok` | `spec.md` approved; the milestone chain runs: backend (if any), frontend, preview, QA, acceptance |
| `publish` | One closed question with what goes live and what it costs; after a "yes": merge commit, production deploy, live URL |
| `change: add a gallery` · `bug: the form does not send` | A new work item and a new preview |
| `connect my domain` | Registrar steps, a confirmation before any DNS change, then HTTPS |
| `rollback` | After one confirmation, the previous version is live again |
| `status` | Per site: current milestone, last preview, live URL, what waits for the user |

## Bots

| Bot | Does | Why it is a separate bot |
|---|---|---|
| `web` (lead) | Interview, `spec.md`, milestones, chains, triage, acceptance, the user's messages | Single point of contact; it never builds |
| `web-frontend` | UI, design system, motion, scroll animation, three.js | Design quality is model-bound: the `design` lane |
| `web-backend` | APIs, data, auth, tests; delegates to the `advisor` lane | Long tool loops on tests need a cheap fast coder with an escalation path |
| `web-qa` | Five lenses: acceptance, visual, WCAG 2.2, Core Web Vitals, security and SEO | Whoever builds never approves |
| `web-deployer` | GitHub flow, preview and production deploys, DNS, rollback | The only bot holding `GH_TOKEN`, `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` |

Models come from the lanes in `scripts/data/model-roles.yaml`; the builder asks the user once and records the answer.

## Stack

| Type | Examples | Stack |
|---|---|---|
| `static` | Landing, blog, docs, portfolio | Astro |
| `dynamic_seo` | Catalog, shop, content site | Next.js App Router |
| `tanstack`/`saas` | Public part plus a private app | TanStack Start |

Common: Tailwind, TypeScript, pnpm, Biome, Vitest, Playwright. Pinned versions live in `stacks.json` (`skills/building-frontend/scripts/`) and are what `scaffold_site.py` writes. Motion uses GSAP ScrollTrigger; 3D uses three.js with React Three Fiber (see `skills/building-frontend/references/`). Hosting is Cloudflare by default; a server-rendered site in production usually needs its paid plan, stated before the first deploy.

## Chain: milestone

```mermaid
flowchart LR
  api["api · web-backend<br/>(only when the spec has a backend)"] --> ui["ui · web-frontend"]
  ui --> preview["preview · web-deployer"]
  preview --> qa["qa · web-qa"]
  qa -- "FIX, at most 2 rounds" --> ui
  qa -- "APPROVED" --> accept["accept · web"]
  accept --> user(["user: publish · change · bug"])
  user -- "publish" --> production["production · web-deployer"]
```

`chain deploy-production` runs only after the user says "publish", with their literal confirmation in the card body.

## Cron

| Job | On | Schedule | What it does |
|---|---|---|---|
| `web-watch` | `web` (lead) | `0 */4 * * *` | `--no-agent`: prints to the lead's Bot Chat only when a card has been blocked over 24 h or is stale |

## What the computer needs

- The builder installs it; nothing else runs in the background (no Docker, no database, no server).
- Accounts the user creates: GitHub (free) and Cloudflare (free). The deployer guides a fine-grained GitHub token and a scoped Cloudflare token; both stay in its own environment.
- Node 22+, pnpm, git, `gh`, `cf` and Chrome are needed the first time a site builds; Playwright and Lighthouse run inside the site project.

## Files in this squad

| File | Contents |
|---|---|
| `squad.yaml` | Manifest: bots, lanes, chains, cron, keeps |
| `souls/` | One SOUL per bot |
| `skills/` | `leading-web`, `building-frontend`, `building-backend`, `reviewing-sites`, `deploying-sites`, `site-contract` |
| `scripts/` | `web_watch.py` (cron watchdog, copied into the lead profile) |
| `skills/building-frontend/scripts/` | `scaffold_site.py`, `stacks.json` (pinned framework and tool versions) |
| `skills/site-contract/scripts/` | `check_site.py` |
