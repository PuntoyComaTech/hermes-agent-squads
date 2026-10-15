# hermes-agent-squads

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Hermes Agent](https://img.shields.io/badge/Hermes%20Agent-NousResearch-7c3aed)](https://github.com/NousResearch/hermes-agent)

Ready-to-install **AI agent squads for [Hermes Agent](https://github.com/NousResearch/hermes-agent)**:
web development, marketing, job search and a studio, plus a **builder** that installs them,
creates new ones with you and keeps everything updated. The repo root is the builder's
**profile distribution**: one command installs it, one command updates it.

Each squad is one visible lead (the only bot you talk to) plus hidden workers that pass work
along a Kanban board. Irreversible steps — apply, publish, send, deploy — always wait for
your explicit yes.

## Install (3 commands)

```bash
hermes profile install github.com/PuntoyComaTech/hermes-agent-squads --name builder --alias
hermes -p builder model        # pick the builder's model (interactive, once)
builder chat                   # say "set me up" -> the builder runs squadctl apply --self
```

The `--alias` wrapper is written to `~/.local/bin`; keep that directory on your `PATH` to
use the short `builder chat` form (`hermes -p builder chat` always works).

You need Hermes Agent with a connected model provider, a machine that stays on for
automations, and (optional) a messaging platform where the leads deliver results.

The builder asks which model each bot gets, suggests from your connected providers
(`scripts/model_advisor.py`), and shows a diff before every change. Later updates:
ask the builder "what changed upstream", or run `hermes profile update builder`.

## Desktop setup

1. **Kanban plugin.** Enable Capabilities → Plugins → **Kanban** to see the boards
   (it ships disabled by default; the dispatcher runs in the gateway regardless).
2. **Bots pane.** The Bots tab is your roster: workers are hidden, so you see Home, the
   builder and one lead per squad. Sections come from each squad's manifest.
3. **Rail.** The profile rail lists every profile (a full install has 19) and condenses
   into a dropdown above 13; use ⌘K → *Toggle profile rail* and switch in the Bots pane.
4. **Projects.** Each site, brand or client is a Hermes Project; the builder registers it
   in the lead and the workers (`squadctl project add`), and the Desktop groups sessions
   by project.

## Squads

| Squad | Board | You get | Bots |
| --- | --- | --- | --- |
| [Web](squads/web/README.md) | `web` | Sites from idea to production behind a quality gate, preview link before publishing | lead, frontend, backend, qa, deployer |
| [Marketing](squads/marketing/README.md) | `marketing` | Dated research, 90-day plans, copy and assets for your brands, five-lens review | lead, research, creative, producer, reviewer |
| [Jobs](squads/jobs/README.md) | `jobs` | Matching openings with tailored applications; "apply" sends (or a manual kit) | lead, scout, writer, reviewer, applier |
| [Studio](squads/studio/README.md) | `studio` | Motion, video and 3D assets ordered by the other squads | lead, motion, 3d |
| Yours | — | Ask the builder: "create a squad for <goal>" | up to 5 |

### Web

```mermaid
flowchart LR
    U([you: "new site: idea"]) --> L["web (lead): spec + milestones"]
    L --> C["chain card 1: api (if backend)"] --> F["chain card 2: ui"]
    F --> P["chain card 3: preview"] --> Q["web-qa: 5 lenses"]
    Q -->|fail: fix card, max 2 rounds| F
    Q -->|pass| A{"you: publish?"}
    A -->|"yes"| D["web-deployer: GitHub, DNS, rollback"]
```

### Marketing

```mermaid
flowchart LR
    U([you: brand brief]) --> L["marketing (lead): plan + calendar"]
    L --> R["marketing-research: dated evidence"]
    R --> C["marketing-creative: concepts + copy"]
    C --> P["marketing-producer: assets, landings, emails"]
    P --> V["marketing-reviewer: 5 lenses"]
    V -->|one fix round| C
    V -->|approved| A{"you: publish?"}
```

### Jobs

```mermaid
flowchart LR
    U([cron: search slots]) --> L["jobs (lead): profile + criteria"]
    L --> S["jobs-scout: search + hard filter"]
    S --> W["jobs-writer: CV + letter"]
    W --> R["jobs-reviewer: 5 lenses"]
    R -->|one fix round| W
    R --> D["lead digest: match + link"]
    D --> A{"you: apply / change / no"}
    A -->|"apply"| J["jobs-applier: simple form or manual kit"]
```

### Studio

```mermaid
flowchart LR
    U(["card from web or marketing"]) --> L["studio (lead): storyboard + shot list"]
    L --> T{"3D needed?"}
    T -->|yes| G["studio-3d: Blender scenes + renders"]
    T -->|no| M["studio-motion: motion, video, demos"]
    G --> M
    M --> R["lead: render review (contact sheets)"]
    R -->|one fix round| M
    R --> D["delivered as a comment on the requester's card"]
```

## How work flows

A card is one bounded job; each stage creates the next as a dependent card
(`--parent`), so work moves without you relaying anything. Reviewers return one fix round,
then the lead asks you only what is yours to decide. Cron jobs run behind zero-LLM gates:
a quiet tick costs nothing.

## Repository map

```text
distribution.yaml      profile distribution manifest (what install/update touches)
SOUL.md  config.yaml   builder identity and minimal profile config
builder.yaml           builder bot spec; applied by scripts/hpy squadctl.py apply --self
CHANGELOG.md           what shipped, read by the update watcher
skills/                10 builder skills (hermes-platform = verified Hermes reference)
scripts/               squadctl, migrate_v1, model_advisor, catalog_search, skill_lint,
                       kanban_chain, watch_upstream + gate_lib, data/ lane tables
squads/<key>/          squad manifests, SOULs, skills, scripts (web, marketing, jobs, studio)
squads/_schema/        squad manifest JSON schema
docs/decisions.md      condensed decision log
tests/                 pytest against a temporary HERMES_HOME (not shipped)
```

## For AI agents

Read [`AGENTS.md`](AGENTS.md) first; short index in [`llms.txt`](llms.txt). Verified Hermes
behavior is in `skills/hermes-platform/references/` (every fact cites its docs path).
Contributions: [`CONTRIBUTING.md`](CONTRIBUTING.md) — or ask your builder, it can propose
them with your OK.

## License

MIT. Third-party skills and plugins keep their own licences; the builder quotes each one
before installing it.
