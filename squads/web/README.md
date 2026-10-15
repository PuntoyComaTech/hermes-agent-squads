# Squad: Web

## Purpose

Someone who does not program gets a website or web app built, reviewed and live. The user describes a site, approves a plan, checks a preview and says "publish".

Each site is its own project folder and GitHub repository. Nothing reaches production, DNS, money or data without the user's explicit answer for that action.

## What the user sees

```text
Panaderia Sol, preview ready (milestone 1 of 3: home and menu)
https://m1-panaderia-sol.example.workers.dev
- Home with opening hours and the map
- Menu page, in Spanish and English
- Loads in 1.2 s on a phone; no accessibility errors
Screenshot attached.
Reply: "publish", "change: ...", "bug: ... + screenshot"
```

| The user says | What happens |
|---|---|
| `new site: a page for my bakery with the menu` | Plain-language questions in rounds of at most 5, then a plan: pages, stack in one line, milestones, monthly cost |
| `ok` | The plan is approved and the first milestone runs: backend if any, frontend, preview, QA, acceptance |
| `publish` | One Yes/No question naming what goes live and its cost; on "yes": merge, production deploy, live URL |
| `change: add a gallery`, `bug: the form does not send` | A new work item and a new preview |
| `connect my domain` | The planned DNS records, a Yes/No question, then the change and HTTPS |
| `rollback` | After one Yes/No question, the previous version is live again |
| `status` | Per site: current milestone, last preview, live URL, what waits for the user |

## Bots

One visible lead (`web`) and four hidden workers: `squad.yaml -> bots`. Models come from the lanes in `scripts/data/model-roles.yaml`.

## Stack

Stacks, site types and pinned versions: `skills/building-frontend/scripts/stacks.json`. Hosting is Cloudflare by default; a server-rendered site past the free tier needs the paid Workers plan, stated in the plan and in the publish question.

## Chain: milestone

```mermaid
flowchart LR
  api["api: web-backend<br/>(site.yaml backend: true)"] --> ui["ui: web-frontend"]
  ui --> preview["preview: web-deployer"]
  preview --> qa["qa: web-qa"]
  qa -- "FIX (automation.reviewer_rounds)" --> ui
  qa -- "APPROVED" --> accept["accept: web"]
  accept --> user(["user: publish, change, bug"])
  user -- "publish" --> production["production: web-deployer"]
```

`production` runs only with the user's literal confirmation in the card.

## Cron

`web-watch` runs the builder's `scripts/board_watch.py` on the lead (`squad.yaml -> bots.web.cron`): it posts to the lead's Bot Chat when a card waits on the user or stalls.

## What the computer needs

- Accounts the user creates: GitHub and Cloudflare (free tiers). The deployer guides a fine-grained GitHub token and a scoped Cloudflare token; both stay in its environment.
- Node 22+, pnpm, git, `gh`, `cf` and Chrome. Playwright, axe-core and Lighthouse install inside each site repo.

## Files

| File | Contents |
|---|---|
| `squad.yaml` | Manifest: bots, lanes, chains, cron, keeps |
| `souls/` | One SOUL per bot |
| `skills/` | `leading-web`, `building-frontend`, `building-backend`, `reviewing-sites`, `deploying-sites`, `site-contract` |
| `skills/building-frontend/scripts/` | `scaffold_site.py`, `stacks.json` |
| `skills/site-contract/scripts/` | `check_site.py` |
