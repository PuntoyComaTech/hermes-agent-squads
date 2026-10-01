# Squad: Marketing

> One-page summary: the user reads it to decide whether to install the squad; the builder starts from it. Requires the base.
> For anyone who does marketing: a business owner, a freelancer, an agency with clients, a marketing team or a creator. Everything specific to each user and brand comes from [`01-personalization.md`](01-personalization.md).

## Purpose

A marketing squad that works on its own for **several projects at once** and delivers **ready-to-approve proposals**: social media pieces, ads, videos, emails, campaign landing pages, plans and reports, in each brand's voice and identity. Full websites belong to the web squad.

The user approves, requests changes or discards from their messaging app. Nothing is published or sent without their "yes".

## What the user sees

Each brand has its own Telegram topic or Discord channel (on WhatsApp, a single chat with the brand name in every message). This is how the week's batch arrives:

```text
☕ Café Luna · Week 41 proposals (4)
1. Carousel "3 brewing methods for your fall coffee" · Instagram · Tue 09:00
2. 15 s reel "From bean to cup" · Instagram and TikTok · Thu 18:00
3. Story with a poll · Instagram · Fri 12:00
4. Email "The fall menu is here" · Sat 08:00
📎 covers and video attached · details in the Studio
Reply: "approve all" · "approve 1 and 3" · "change 2: …" · "no to 4"
```

| The user says | What happens |
| --- | --- |
| `approve all` · `approve 1 and 3` | They are approved. On posting day, the reminder arrives with the copy ready (Level 1), or they are scheduled after the user confirms (Level 2) |
| `change 2: shorter and with a real photo` | A new, reviewed version arrives in the same chat |
| `no to 4, we don't do promos` | It is discarded, and the squad remembers this for that brand |
| `new project: Estudio Pilates Sol, @pilatessol` | Onboarding: the squad researches the brand, asks for whatever is missing, and proposes a diagnosis, voice, identity and plan |
| `make a reel for Thursday's launch` | On-demand piece |
| `campaign for Christmas` | Brief and 3 concepts (A, B, C) with a sketch; when the user replies "B", the pieces for that concept arrive |
| `marketing plan` · `how are we doing?` · `ideas` | 90-day plan, report with data, or numbered ideas based on trends ("do idea 2") |
| `pause Café Luna` · `resume` | Stops or restarts that brand's automatic work (planning and report); on-demand requests continue |
| `quiet until Monday` | The squad keeps working, but does not write until that date |

On the computer, the **Studio** shows each brand's proposals, versions, calendar and status; the Hermes Kanban shows what is in production.

## What the squad does

| Service | Who | Level |
| --- | --- | --- |
| Project onboarding: diagnosis, context, voice and visual identity (`DESIGN.md`) | Strategist; producer for the identity | 1 |
| 90-day marketing plan (or 12-month, if requested) | Strategist | 1 |
| Market, competitor and audience research | Strategist | 1 |
| Trend radar and automatic weekly calendar | Strategist | 1 |
| Campaigns and launches: brief and 3 concepts to choose from | Strategist and creative | 1 |
| Copy for social media, ads, emails, landing pages, articles and scripts | Creative | 1 |
| Static pieces and carousels in each network's sizes | Producer | 1 |
| Motion and short video with voice-over and subtitles | Producer | 1 |
| Landing pages with tracking, and HTML emails | Producer | 1 (publishing them: 2) |
| PDF guides and documents: brand manual, social media guide, plans, reports | Strategist and producer | 1 |
| Monthly results report | Strategist and a script | 1 with CSV exports; 2 with connectors |
| Scheduling posts, email drafts, deploying landing pages | Scripts, with confirmation | 2 |
| AI video for B-roll | Producer | 2 |
| Influencers, partnerships, community, press and SEO | Strategist, with advisory skills | Depending on the services chosen |
| Expert council for big decisions, and presentations for clients | Strategist and producer | Optional |
| Continuous optimization: ad fatigue, A/B tests, creative retro | Strategist | 3 |

**Never**: pay for ads, sign, create accounts, publish, send or reply to third parties without confirmation, or make up data, testimonials or figures.

## Levels

| Level | What it adds | When to move up |
| --- | --- | --- |
| **1 · Automatic squad** | Project onboarding, plan, automatic weekly planning with trends, pieces of every type, review, proposals over messaging with versions, preferences learned per brand, Studio, monthly report with exported data, publishing reminders | - |
| **2 · Connected** | Scheduling posts and creating email drafts in cloud services (always with confirmation), deploying landing pages to Cloudflare, read-only data connectors, Studio with buttons (Hermes plugin), AI video | When posting by hand takes up too much time, or the user wants data without exporting it |
| **3 · Optimization** | Metric-driven loops (ad fatigue, keyword drops, landing page regressions, creative retro), tests with stopping rules, a dedicated director if there are many brands | With 8 or more weeks of connected data |

## Bots

| Bot | Does | Why it is a separate bot |
| --- | --- | --- |
| `orchestrator` (base) | **It is the director**: chats, onboards projects, launches flows, presents proposals and handles changes | Single point of contact |
| `marketing-strategist` | Researches, plans, builds calendars and briefs, analyzes data | The only one with web access: it reads untrusted text, but has no terminal |
| `marketing-creative` | Ideas, concepts and all the copy; scripts and art direction | Never reads the web: what goes out to the public cannot be contaminated |
| `marketing-producer` | Designs, renders images and video, builds landing pages and emails, lays out documents | The only one with a terminal; it can use a stronger model for design with code |
| `marketing-reviewer` | Reviews everything with 5 independent lenses before it reaches the user | Independence: whoever made a piece never reviews it |

Specialists missing a datum consult its owner directly (`02-architecture.md` §3.1.1), without going through the orchestrator.

Models: the builder asks, per bot, which model and reasoning effort to use. Recommended: `main_model` for all, and for the producer `production_model` (the best model for design and motion with code available to the user).

Why 4 bots and why the orchestrator is the director: [`00-evaluation/05-marketing-design.md`](../../00-evaluation/05-marketing-design.md).

## What the computer needs

- **Installed by the builder:** Node 22 or later, Python 3.11 or later, FFmpeg and a headless Chromium (Playwright).
- **No Docker or servers:** the only always-on service is the Hermes gateway.
- **With 8 GB of RAM** it works with some adjustments: one render at a time.
- **Optional keys:** AI image and video, premium voice, and Level 2 services.

## Files in this plan

| File | Contents |
| --- | --- |
| [`01-personalization.md`](01-personalization.md) | Squad profile, onboarding of each brand, brand files and examples |
| [`02-architecture.md`](02-architecture.md) | Folders, piece types, flows, proposal lifecycle, data contracts, Studio and squad rules |
| [`03-bots.md`](03-bots.md) | Each bot's SOUL, own and third-party skills, orchestration skill and automations |
| [`04-installation.md`](04-installation.md) | Builder instructions to install Level 1, and maintenance |
| [`05-scripts.md`](05-scripts.md) | Scripts: planning, delivery, Studio, rendering, checks, metrics; Level 2 |
| [`06-testing-and-operations.md`](06-testing-and-operations.md) | Acceptance tests, daily operation, metrics and when to move up a level |
| [`squad.yaml`](squad.yaml) | Manifest: bots, modes, toolsets, consultation pairs, crons |
| [`reference/`](reference/README.md) | Third-party marketing skills (with scripts and licenses) the builder uses as sources for the squad's own skills |
