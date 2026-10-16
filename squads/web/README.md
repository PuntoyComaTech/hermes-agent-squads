# Web squad

**Describe a site, approve a plan, check a preview, say "publish".**

[← All squads](../../README.md)

Someone who does not program gets a website or web app built, reviewed and live. Each site is its own project folder
and GitHub repository. Nothing reaches production, DNS, money or data without your explicit answer for that action.

## How it works

```mermaid
flowchart TD
    U(["You: new site: a page for my bakery"]):::you
    U --> W["web (manager)<br/>questions, plan, milestones"]:::lead
    W --> P{"You: approve the plan?"}:::ask
    P -->|"ok, site needs a backend"| BE["web-backend<br/>API and data"]:::bot
    P -->|"ok"| FE
    BE --> FE["web-frontend<br/>pages and design"]:::bot
    FE --> PV["web-deployer<br/>preview link"]:::bot
    PV --> QA["web-qa<br/>reviews the preview"]:::check
    QA -->|"needs fixes"| FE
    QA -->|"approved"| R{"You: publish, change or bug?"}:::ask
    R -->|"change / bug"| FE
    R -->|"publish + yes"| LIVE(["web-deployer: live URL"]):::done

    classDef you fill:#ede9fe,stroke:#7c3aed,color:#1e1b4b
    classDef lead fill:#fce7f3,stroke:#db2777,color:#831843
    classDef bot fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    classDef check fill:#ffedd5,stroke:#ea580c,color:#7c2d12
    classDef ask fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef done fill:#dcfce7,stroke:#16a34a,color:#14532d
```

QA rounds are capped by `automation.reviewer_rounds`. The production deploy runs only with your literal confirmation
in the card.

## What you see

```text
Panaderia Sol, preview ready (milestone 1 of 3: home and menu)
https://m1-panaderia-sol.example.workers.dev
- Home with opening hours and the map
- Menu page, in Spanish and English
- Loads in 1.2 s on a phone; no accessibility errors
Screenshot attached.
Reply: "publish", "change: ...", "bug: ... + screenshot"
```

| You say | What happens |
| --- | --- |
| `new site: a page for my bakery with the menu` | Plain-language questions in rounds of at most 5, then a plan: pages, stack in one line, milestones, monthly cost |
| `ok` | The plan is approved and the first milestone runs |
| `publish` | One Yes/No question naming what goes live and its cost; on "yes": merge, production deploy, live URL |
| `change: add a gallery`, `bug: the form does not send` | A new work item and a new preview |
| `connect my domain` | The planned DNS records, a Yes/No question, then the change and HTTPS |
| `rollback` | After one Yes/No question, the previous version is live again |
| `status` | Per site: current milestone, last preview, live URL, what waits for you |

## Bots

| Bot | Does |
| --- | --- |
| `web` (manager) | Interviews you, writes `spec.md`, plans milestones, files the work, triages changes and accepts results |
| `web-frontend` | UI, design system, motion and scroll animation |
| `web-backend` | APIs, data, auth and tests; the manager gives it a stronger model per card on hard problems |
| `web-qa` | Reviews each preview with five lenses and never fixes what it reviews |
| `web-deployer` | GitHub flow, preview and production deploys, DNS and rollback; the only bot with deploy credentials |
| `web-frontend-pro` (optional) | 3D, WebGL shaders, GSAP ScrollTrigger/Lenis and complex motion: `squadctl apply web --with web-frontend-pro` |

In the Desktop app the manager sits under `Managers` and the workers under `Web`.

## What the computer needs

- Accounts you create: GitHub and Cloudflare (free tiers). The deployer guides a fine-grained GitHub token and a
  scoped Cloudflare token; both stay in its environment.
- Node 22+, pnpm, git, `gh`, `cf` and Chrome. Playwright, axe-core and Lighthouse install inside each site repo.
- Hosting is Cloudflare by default. A server-rendered site past the free tier needs the paid Workers plan, stated in
  the plan and in the publish question. Stacks and pinned versions: `skills/building-frontend/scripts/stacks.json`.

## Schedule

| Job | When | Does |
| --- | --- | --- |
| `web-watch` | every 30 min | Tells you in the manager's chat when a card waits on you or stalls |

## Files

| Path | Contents |
| --- | --- |
| `squad.yaml` | Manifest: bots, lanes, chains, cron, keeps |
| `souls/` | One SOUL per bot |
| `skills/` | `leading-web`, `building-frontend`, `building-backend`, `reviewing-sites`, `deploying-sites`, `site-contract` |
| `skills/building-frontend/scripts/` | `scaffold_site.py`, `stacks.json` |
| `skills/site-contract/scripts/` | `check_site.py` |

## Your own extras

Ask the builder "add skill &lt;name&gt; to web-frontend". It keeps the skill in your local overlay, outside this repo.

---

<div align="center">

Developed by **PuntoyComaTech**

[![Instagram](https://img.shields.io/badge/Instagram-%23E4405F.svg?style=for-the-badge&logo=Instagram&logoColor=white)](https://www.instagram.com/puntoycomatech)
[![X](https://img.shields.io/badge/X-%23000000.svg?style=for-the-badge&logo=X&logoColor=white)](https://x.com/PuntoyComaTech)
[![YouTube](https://img.shields.io/badge/YouTube-%23FF0000.svg?style=for-the-badge&logo=YouTube&logoColor=white)](https://www.youtube.com/@PuntoyComaTech)
[![TikTok](https://img.shields.io/badge/TikTok-%23000000.svg?style=for-the-badge&logo=TikTok&logoColor=white)](https://www.tiktok.com/@puntoycomatech)
[![LinkedIn](https://img.shields.io/badge/LinkedIn-%230077B5.svg?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/gabriel-rubio99/)

</div>
