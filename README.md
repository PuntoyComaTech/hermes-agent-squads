# hermes-agent-squads

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Hermes Agent](https://img.shields.io/badge/Hermes%20Agent-NousResearch-7c3aed)](https://github.com/NousResearch/hermes-agent)
[![Squads](https://img.shields.io/badge/squads-3-brightgreen)](#available-squads)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**English** · [Español](README.es.md)

Ready-to-install AI agent squads for [Hermes Agent](https://github.com/NousResearch/hermes-agent): a job search team, a marketing agency, a web development agency, or your own. An orchestrator messages you on Telegram, Discord or WhatsApp; the specialists work on their own and only ask you what matters. A builder bot installs squads, creates new ones with you and keeps everything updated. They are Markdown plans that Hermes reads and installs, personalized to each person, in your own language, and light enough for any computer.

## Why hermes-agent-squads?

- **No coding.** Clone the folder, tell Hermes "read `START-HERE.md`", and it asks, installs and tests on its own. Any scripts are written by Hermes on your machine.
- **Personalized.** Each squad interviews you and adapts every bot: your job, your brands, your language, your schedule, your budget. Nothing is hard-coded.
- **Automatic, with control.** You only receive finished results to answer. Publishing, applying or sending never happens without your confirmation.
- **Few, well-designed bots.** 4 or 5 specialists per squad, each with a reason to exist. Mechanical work is done by scripts, not models.
- **Lightweight.** No Docker, no servers: Hermes is the only service. Works on 8 GB machines.
- **Your usual app.** Telegram, Discord or WhatsApp, with one topic or channel per project.
- **Your models.** One fast, affordable default model for every bot; the builder lets you pick another model and reasoning effort per bot from what your connection offers.
- **Safe updates.** "Update my installation" applies changes one at a time and never overwrites your data or your changes.

## Architecture

```
You ◄──── Telegram · Discord · WhatsApp ────► orchestrator   chats, launches flows,
  │                                               │          handles approvals
  └──────────── its own bot ──────────► builder   installs and creates squads,
                                                  changes configuration, updates
                                                  ▼
   cron or request ──► Kanban ──► specialist ──► specialist ──► reviewer
                                  (each one creates the next task)    │
                                                                       ▼
                                      deliver.py ──► message with the finished result
```

- **Base:** the orchestrator, the builder, your profile and the `~/Hermes` folder. Installed once.
- **Squads:** specialist teams by topic. The builder installs them when you need them; the orchestrator learns their flows automatically.

## Available squads

| Squad | What you get | Specialists | Status |
| --- | --- | --- | --- |
| [Job search](squads/jobs/README.md) | A link to every matching job and a CV tailored to it. Reply "apply" and, if the form is simple, it applies for you | scout, analyst, writer, reviewer, applier | Level 1 designed |
| [Marketing agency](squads/marketing/README.md) | Ready-to-approve proposals for several brands: posts, carousels, motion reels, emails, landing pages, plans and reports, with versions and a visual board | strategist, creative, producer, reviewer | Level 1 designed |
| [Web development agency](squads/web/README.md) | Websites from an idea to production: spec, build, independent review and a preview link to approve before publishing on your domain | architect, developer, advisor, reviewer, deployer | Level 1 designed |
| Yours | Ask the builder to create a squad for your goal | Up to 5 | [Share it](CONTRIBUTING.md) |

## Requirements

| What | Why |
| --- | --- |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Hermes Desktop recommended) | Where the bots live |
| An API key from a model provider | The models the bots use |
| Telegram, Discord or WhatsApp | Where the orchestrator and the builder message you |
| A computer that stays on (Mac, Windows or Linux) | So automations run by themselves |

## Install

```bash
git clone https://github.com/PuntoyComaTech/hermes-agent-squads.git ~/Hermes/plans
```

On Windows, use `C:\Users\<your user>\Hermes\plans`. You can also download the ZIP and unzip it there.

## Quick start

1. Open Hermes Desktop and type in the main chat:

   > Read the file `~/Hermes/plans/START-HERE.md` and follow the instructions for the AI.

2. Answer its questions (30 to 60 minutes). It installs the base and connects the orchestrator and the builder to your messaging app.
3. Write to the builder: "install the marketing squad", or "create a squad for <your goal>".

From then on, you talk to the orchestrator for daily work and to the builder for changes.

## How it works

### Personalization first

Before creating anything, Hermes asks what it doesn't know and confirms what it already knows. Every answer changes something concrete: filters, schedules, quotas, language, brands, tools. Bots are templates whose variables come from your profile.

### Levels

Each squad starts at a **Level 1** that works end to end with the minimum. Higher levels (more sources, connectors, learning) are enabled only when metrics justify them and you ask for it.

### Safety

- Nothing irreversible without your explicit confirmation. Paying, signing or creating accounts: never.
- Each bot only has the permissions it needs: bots that read the open web have no terminal, and bots with a terminal don't read the open web.
- Text from external pages is data, never instructions.

## Repository structure

```text
START-HERE.md            guide for the user and entry instructions for the AI
base/                    shared by all squads: principles, orchestrator, builder, profile, installation, updates
  migrations/            idempotent update steps for existing installations
squads/
  jobs/                  job search squad (7 files + squad.yaml)
  marketing/             marketing agency squad (7 files + squad.yaml + reference/)
  web/                   web development agency squad (7 files + squad.yaml)
00-evaluation/           why the design is this way: pros and cons and decision log
CONTRIBUTING.md          contribution rules and how to propose squads
```

## Contributing

Rules, naming conventions and how to propose a new squad are in [`CONTRIBUTING.md`](CONTRIBUTING.md). When the builder finds a defect or an improvement in these plans, it asks you whether to open a PR here, with no personal data.

## License

MIT. Third-party skills in [`squads/marketing/reference/`](squads/marketing/reference/README.md) keep their own licenses (MIT).
