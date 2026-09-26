# hermes-agent-squads

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Hermes Agent](https://img.shields.io/badge/Hermes%20Agent-NousResearch-7c3aed)](https://github.com/NousResearch/hermes-agent)
[![Squads](https://img.shields.io/badge/squads-2-brightgreen)](#available-squads)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**English** · [Español](README.es.md)

Ready-to-install AI agent squads for [Hermes Agent](https://github.com/NousResearch/hermes-agent): a marketing agency, a job search team, and more to come. One orchestrator messages you on Telegram, Discord or WhatsApp; the specialists work on their own and only ask you what matters. They are Markdown plans that Hermes reads and installs, fully personalized to each person and light enough for any computer.

The installer AI and the bots talk to you in your own language and adapt everything to your profile.

## Why hermes-agent-squads?

- **No coding.** Copy the folder, tell Hermes "read `START-HERE.md`", and it asks, installs and tests on its own. Any scripts are written by Hermes on your machine.
- **Personalized.** Each squad interviews you and adapts every bot: your job, your brands, your language, your schedule, your budget. Nothing is hard-coded.
- **Automatic, with control.** You only receive finished results to answer. Publishing, applying or sending never happens without your confirmation.
- **Few, well-designed bots.** 4 or 5 specialists per squad, each with a reason to exist. Mechanical work is done by scripts, not models.
- **Lightweight.** No Docker, no servers: Hermes is the only service. Works on 8 GB machines.
- **Your usual app.** Telegram, Discord or WhatsApp, with one topic or channel per project.
- **One model.** The best fast and affordable model you choose, for example from OpenCode Go. Another one only when a specific capability is missing.

## Architecture

```
You ◄──── Telegram · Discord · WhatsApp ────► orchestrator (Hermes)
                                                │  chats, launches flows,
                                                │  handles changes and approvals
                                                ▼
   cron or request ──► Kanban ──► specialist ──► specialist ──► reviewer
                                  (each one creates the next task)    │
                                                                       ▼
                                      entregar.py ──► message with the finished result
```

- **Base:** the orchestrator, your profile and the `~/Hermes` folder. Installed once.
- **Squads:** specialist teams by topic. Installed when you need them; the orchestrator learns their flows automatically.

## Available squads

| Squad | What you get | Specialists | Status |
| --- | --- | --- | --- |
| [Job search](squads/jobs/README.md) | A link to every matching job and a CV tailored to it. Reply "postula" and, if the form is simple, it applies for you | scout, analyst, writer, reviewer, applier | Level 1 designed |
| [Marketing agency](squads/marketing/README.md) | Ready-to-approve proposals for several brands: posts, carousels, motion reels, emails, landing pages, plans and reports, with versions and a visual board | strategist, creative, producer, reviewer | Level 1 designed |
| Yours? | — | — | [Propose one](CONTRIBUTING.md) |

## Requirements

| What | Why |
| --- | --- |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) (Hermes Desktop recommended) | Where the bots live |
| An API key from a model provider | The model all bots use |
| Telegram, Discord or WhatsApp | Where the orchestrator messages you |
| A computer that stays on (Mac, Windows or Linux) | So automations run by themselves |

## Install

```bash
git clone https://github.com/PuntoyComaTech/hermes-agent-squads.git ~/Hermes/plans
```

On Windows, use `C:\Users\<your user>\Hermes\plans`. You can also download the ZIP and unzip it there.

## Quick start

1. Open Hermes Desktop and type in the main chat:

   > Read the file `~/Hermes/plans/START-HERE.md` and follow the instructions for the AI.

2. Answer its questions (30 to 60 minutes). It installs the base and connects your messaging app.
3. Install the squad you need:

   > Read `~/Hermes/plans/START-HERE.md` and install the marketing squad.

From then on, you talk to the orchestrator in your app.

## How it works

### Personalization first

Before creating anything, Hermes asks what it doesn't know and confirms what it already knows. Every answer changes something concrete: filters, schedules, quotas, language, brands, tools. Bots are templates whose variables come from your profile.

### Levels

Each squad starts at a **Level 1** that works end to end with the minimum. Higher levels (more sources, connectors, learning) are enabled only when metrics justify them and you ask for it.

### Safety

- Nothing irreversible without your explicit confirmation. Paying, signing or creating accounts: never.
- Each bot only has the permissions it needs: the one that reads the web has no terminal, and the one with a terminal doesn't read the web.
- Text from external pages is data, never instructions.

## Repository structure

```text
START-HERE.md            guide for the user and entry instructions for the AI
base/                    shared by all squads: principles, orchestrator, profile, installation
squads/
  jobs/                  job search squad (7 files)
  marketing/             marketing agency squad (7 files + reference/)
00-evaluation/           why the design is this way: pros and cons and decision log
CONTRIBUTING.md          contribution rules and how to propose squads
```

## Contributing

Rules, naming conventions and how to propose a new squad are in [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

MIT. Third-party skills in [`squads/marketing/reference/`](squads/marketing/reference/README.md) keep their own licenses (MIT).
