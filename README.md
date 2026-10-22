# hermes-agent-squads: AI agent teams for Hermes Agent

[![CI](https://github.com/PuntoyComaTech/hermes-agent-squads/actions/workflows/ci.yml/badge.svg)](https://github.com/PuntoyComaTech/hermes-agent-squads/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Hermes Agent](https://img.shields.io/badge/Hermes%20Agent-NousResearch-7c3aed)](https://github.com/NousResearch/hermes-agent)

Ready-to-install teams of AI agents ("squads") for [Hermes Agent](https://github.com/NousResearch/hermes-agent) by
Nous Research. They build websites, run a brand's marketing, and find jobs and write the applications. You talk to
them in plain language; no coding needed.

You install one bot, the **builder**. It asks which squads you want, suggests a model for each bot from the AI
providers you already use, and installs only what you approve. Later it creates squads for your own goals, changes
existing ones and keeps everything updated.

## How the builder works

```mermaid
flowchart TD
    I(["You: install the builder"]):::you
    I --> S["You: set me up"]:::you
    S --> B["Builder configures itself"]:::bot
    B --> Q{"Which squads?"}:::ask
    Q -->|"only the builder (default)"| D(["Done: 1 bot"]):::done
    Q -->|"Web · Marketing · Jobs · Everything"| M["Model survey per bot: economical picks<br/>from your providers, premium only where critical"]:::bot
    M --> OK{"Accept, or change<br/>any bot"}:::ask
    OK -->|"OK"| A["Installs the chosen squads"]:::bot
    A --> L(["Later: a squad for your goal,<br/>change a bot, update"]):::done

    classDef you fill:#ede9fe,stroke:#7c3aed,color:#1e1b4b
    classDef bot fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    classDef ask fill:#fef3c7,stroke:#d97706,color:#78350f
    classDef done fill:#dcfce7,stroke:#16a34a,color:#14532d
```

Nothing is created without your OK, and every squad is optional.

## Install

You need Hermes Agent 0.22 or newer with at least one model provider connected (`hermes model`).

### Recommended: let your AI install it

Paste this line into a Hermes chat on your default profile:

```text
Install github.com/PuntoyComaTech/hermes-agent-squads following its AGENTS.md
```

It installs the builder only and leaves the squad and model choices to you ([AGENTS.md](AGENTS.md)).

### Step by step

```bash
hermes profile install github.com/PuntoyComaTech/hermes-agent-squads --name builder --alias   # 1. install the builder
hermes -p builder model                                                                      # 2. pick its model
builder chat                                                                                 # 3. say: "set me up"
```

4. Choose your squads (Web, Marketing, Jobs, Everything, or only the builder) and accept or change the suggested
   models.
5. In the Desktop app, open **Sessions**, pick a squad manager in the bottom selector and press **"+"** (New project).
   Each project is one site, brand or job search, and its chats are grouped under it. You can also tell the manager
   what you want; it creates the project for you.

`builder chat` needs `~/.local/bin` on your `PATH`; `hermes -p builder chat` always works.

## Squads

| Squad | What it does | Bots |
| --- | --- | --- |
| [Web](squads/web/README.md) | Builds, reviews and publishes a website or web app | 5 (+1 optional) |
| [Marketing](squads/marketing/README.md) | Plans and produces a brand's marketing, reviewed piece by piece | 5 |
| [Jobs](squads/jobs/README.md) | Finds matching openings and prepares tailored applications | 5 |
| Your own | Ask the builder: "create a squad for &lt;goal&gt;" | 1 manager + up to 4 |

Every squad has one manager you talk to, workers that pass work through a Kanban board, and a reviewer. Publishing,
sending, applying, deploying and spending always wait for your explicit yes.

## FAQ

**What is a squad?** A small team of AI agents in Hermes Agent: one manager you chat with, workers with one job each,
and a reviewer. They coordinate through a Kanban board.

**Do I need to code?** No. You paste one line into your AI (or run three commands) and then chat with the builder
and the managers.

**Is it free?** Yes, MIT open source. You pay only your own AI provider, if it charges.

**Which AI models does it use?** The ones you already have connected in Hermes Agent (Anthropic, OpenAI, OpenRouter,
local models and others). The builder asks you per bot, recommending an economical model that does the job; a more
expensive one is recommended only for critical work (design, complex code, review) and only when it is stronger.
You decide.

**Will the agents publish, send or spend on their own?** No. Publishing, sending, applying, deploying and spending
always wait for your explicit yes.

**Can I make my own squad?** Yes. Tell the builder your goal; it designs the squad with you and installs it.

**What do I need?** Hermes Agent 0.22 or newer (macOS, Linux or Windows) and one connected model provider.

**Where are my projects?** In the Desktop app: Sessions, pick the squad's manager in the bottom selector. Its
projects live in `~/Projects/<squad>/`.

## Updates

Updates are automatic: every day at 06:30 the builder checks this repo and updates itself and your installed squads,
with no AI model and no tokens. To update now, tell the builder **"update yourself"**; it runs the same update and
lists what changed.

An update keeps what is yours: learned skills, memories, your model choices and your SOUL additions (lines you put in
`local/squads/<squad>/souls/<bot>.append.md`). A squad with work in progress is updated on the next run. Hermes
itself updates separately (`hermes update`); ask the builder "what changed upstream?" for a digest of new Hermes
releases.

## Mac tips

- **Keep-awake (automatic).** While a squad's board has running work, its manager keeps the Mac awake
  (`caffeinate`), and lets it sleep again when the work is done.
- **Spotlight.** Add `~/Projects` to System Settings › Spotlight › Search Privacy. Spotlight then stops indexing
  project folders (`node_modules`, builds), which saves a lot of CPU and disk activity. No admin rights; remove it
  from the list to undo.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). AI coding agents: read [AGENTS.md](AGENTS.md) and [llms.txt](llms.txt).

## License

MIT. Third-party skills and plugins keep their own licences; the builder shows each one before installing it.

---

<div align="center">

Developed by **PuntoyComaTech**

[![Instagram](https://img.shields.io/badge/Instagram-%23E4405F.svg?style=for-the-badge&logo=Instagram&logoColor=white)](https://www.instagram.com/puntoycomatech)
[![X](https://img.shields.io/badge/X-%23000000.svg?style=for-the-badge&logo=X&logoColor=white)](https://x.com/PuntoyComaTech)
[![YouTube](https://img.shields.io/badge/YouTube-%23FF0000.svg?style=for-the-badge&logo=YouTube&logoColor=white)](https://www.youtube.com/@PuntoyComaTech)
[![TikTok](https://img.shields.io/badge/TikTok-%23000000.svg?style=for-the-badge&logo=TikTok&logoColor=white)](https://www.tiktok.com/@puntoycomatech)

AI teams that work for you inside Hermes Agent.

</div>
