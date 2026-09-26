# Ecosystem base architecture

> Base prompt. Describes the components shared by all squads: the orchestrator, the `~/Hermes` folder, the messaging channels, how rules and skills are shared, and how work runs on its own.
> Hermes facts verified against the official documentation (`NousResearch/hermes-agent`, `website/docs`, September 2026). If something doesn't match during installation, the documentation wins.

## 1. Components

```text
   User ◄──── Telegram / Discord / WhatsApp / … ────► orchestrator (Base section)
                                                          │  talks to the user,
                                                          │  launches flows on request,
                                                          │  handles changes and confirmations
        cron ──► Kanban task ──► specialist ──► specialist ──► … ──► outbox/ready/
                                 (each one creates the task for the next)  │
                                                                           ▼
                                                              delivery script ──► message to the user
```

| Component | What it is in Hermes | How many |
| --- | --- | --- |
| **Orchestrator** | A profile (Bot) connected to the user's messaging channel | 1 for the whole ecosystem |
| **Squad** | Profiles with the same prefix, in a Hermes Desktop *Section*, plus a folder in `~/Hermes/projects/` and an orchestration skill | 1 per domain |
| **Specialist** | A profile with its own SOUL, model and toolsets | 2 to 5 per squad |
| **Skill** | A reusable procedure in `SKILL.md` | As many as needed |
| **Script** | A deterministic program, run by a bot or by a `--no-agent` cron | As many as needed |

### About Hermes Desktop folders (Sections)

*Sections* are **visual-only** folders: they organize the sidebar; they don't share configuration or change routing. One **Base** section is used for the `orchestrator`, and one per squad (**Job search**, etc.). What really ties a squad together is its name prefix, its data folder and its `AGENTS.md`.

## 2. Names

- Profiles: `<squad>-<role>`, lowercase and without accents. E.g.: `jobs-analyst`. The orchestrator is called `orchestrator`.
- Each profile is created with a one-line `--description` that says what it does and what it delivers.

## 3. The `~/Hermes` folder

`~` is the user's home folder on any system (`/Users/<user>` on Mac, `C:\Users\<user>` on Windows, `/home/<user>` on Linux). Everything visible in the ecosystem lives there. In the plans it is written as `{{ROOT}}`, and by default it is `~/Hermes`.

The root of the disk (`/` or `C:\`) is not used: it requires administrator permissions and is left out of backups. On WSL2, `~/Hermes` goes on the Linux side, not in `/mnt/c` (the documentation warns that it is 10 to 100 times slower).

```text
~/Hermes/                     # local git repo
├── plans/                    # copy of this plans repository (instructions)
├── AGENTS.md                 # base rules for all bots (section 2 of 01-principles.md)
├── user/
│   ├── profile.md            # who they are and what they prefer (03-user-profile.md)
│   └── contact.yaml          # contact details and form data (sensitive)
├── orchestrator/
│   ├── registry.md           # installed squads, bots, flows, level
│   └── metrics.md
├── skills/                   # skills shared by all (if any)
├── scripts/                  # shared scripts (e.g. heavy_lock.py, §5)
└── projects/
    └── <squad>/              # e.g. jobs/
        ├── AGENTS.md         # squad rules
        ├── <squad>-profile.yaml
        ├── skills/           # includes orchestration-<squad>
        ├── scripts/
        ├── outbox/           # ready/ (to deliver) and sent/
        └── ...
```

Hermes's internal folder is a different one, and it is hidden: `~/.hermes/` on Mac, Linux and WSL2; `%LOCALAPPDATA%\hermes\` on Windows. It holds each bot's configuration and the Kanban board. The user doesn't touch it.

`.gitignore` for `~/Hermes`: `user/contact.yaml`, `.env`, `*.db`, `.venv/`, `plans/`.

### How rules reach each bot

- `SOUL.md` is per profile: the bot's identity and prohibitions.
- `AGENTS.md` files are merged from the root of the git repo down to the working directory. A bot working in `~/Hermes/projects/jobs/...` reads **`~/Hermes/AGENTS.md` + `~/Hermes/projects/jobs/AGENTS.md`**.
- Each profile has `terminal.cwd` pointing to its folder (`{{ROOT}}` for the orchestrator, `{{ROOT}}/projects/<squad>` for the specialists).
- Every Kanban task carries `--workspace dir:<absolute path>` inside `{{ROOT}}`. Without it, the worker uses a temporary directory and doesn't see `AGENTS.md` or the earlier files.

### How skills are shared

`skills.external_dirs` in each profile's `config.yaml`:

- Specialists: `[{{ROOT}}/projects/<squad>/skills]`.
- Orchestrator: `{{ROOT}}/skills` + the `skills/` folder of **each** installed squad. Installing a squad teaches the orchestrator its flows without touching its SOUL.
- If a squad splits its skills into folders by role (for example, the marketing agency, D-022), each specialist lists its role folder and the common one, and the orchestrator lists only that squad's `skills/orchestration/`. Do not assume that `external_dirs` reads subfolders.

## 4. Messaging channels

The orchestrator is the one who talks to the user. Its bot token goes in **its own** `.env` (`~/.hermes/profiles/orchestrator/.env`), not in the `default` profile: that way the gateway routes that channel to the orchestrator.

| Channel | Difficulty | What you need | Proactive messages and PDF | Recommendation |
| --- | --- | --- | --- | --- |
| **Telegram** | Easy | Create a bot with @BotFather (or the "Create with QR" button in Hermes Desktop), `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS` | Yes. Buttons in questions | **Recommended** |
| **Discord** | Medium | Create an application and a bot, enable the *Message Content* and *Server Members* intents, invite it with the *Attach Files* permission, `DISCORD_BOT_TOKEN`, `DISCORD_ALLOWED_USERS` | Yes. Buttons in questions | Good if the user already uses Discord |
| **WhatsApp (Baileys bridge)** | Easy | Node 18+, `hermes whatsapp` and scanning a QR code | Yes, but it is unofficial: **risk of the number being banned**; the documentation recommends a dedicated number and avoiding unsolicited messages | Only with a dedicated number and accepting the risk |
| **WhatsApp Business (Cloud API)** | Hard | Meta Business account, permanent token, public HTTPS webhook | Outside the 24 h window it requires approved templates, which Hermes does not support yet | **Not suitable** for automatic notifications |
| Others (Slack, Signal, Email, Matrix, Teams…) | Varies | See `website/docs/user-guide/messaging/` | Depends on the channel | If the user already uses them |

Common details:

- Files are sent by writing `MEDIA:/path/file.pdf` in the message; they arrive as a native attachment.
- For the orchestrator to be able to create tasks from the chat: `hermes -p orchestrator tools enable kanban --platform <channel>`.
- Questions with options: the `clarify` tool shows buttons on Telegram and Discord and a poll on WhatsApp (Baileys); it waits up to 1 hour by default.
- "Home" channel for notifications: `/sethome` in the chat, or `TELEGRAM_HOME_CHANNEL` / `DISCORD_HOME_CHANNEL`.

## 5. How work runs on its own

| Mechanism | What for |
| --- | --- |
| **`--no-agent` cron** | Run a script without an LLM: start the daily search, deliver results, ingest via API. The script lives in the profile's `$HERMES_HOME/scripts/`; empty output = no notification; error = alert |
| **Agent cron** | A periodic task with an LLM (weekly summary). Its response is delivered to the `deliver` target (`telegram`, `discord`, `whatsapp`, `origin`…) |
| **Kanban** | Pass work between bots. There is a single board, and the *dispatcher* lives in the **gateway** (it checks every 60 s). `parents=[...]` holds a task until its parents finish |
| **Handoff chain** | When each specialist finishes, it uses `kanban_create` to create the next one's task (workers have that tool without any configuration). It only creates it if its result justifies it: that way there are no useless branches and no coordinator spending tokens between stages |
| **`delegate_task`** | Anonymous subagents with a clean context **from the same bot** (it cannot call another profile). For parallel reviews and research with a separate context |
| **`hermes send`** | Send a message (with `MEDIA:`) from a script, without an LLM: `hermes -p orchestrator send --to <channel> "text MEDIA:/path"` |
| **Kanban subscriptions** | A task created by the orchestrator from the chat notifies that chat when it finishes or gets blocked; child tasks inherit the subscription |

The handoff chain goes against Hermes's general recommendation ("workers don't hand out work; the orchestrator does"). It is chosen on purpose: the chain is linear and fixed, and this way it works the same when a cron triggers it with nobody in the chat. See `00-evaluation/02-decisions.md` (D-007).

Kanban configuration (`default` profile, which owns the gateway):

```yaml
kanban:
  dispatch_in_gateway: true
  auto_decompose: false
  default_assignee: orchestrator
  max_in_progress: 3              # 2 if the machine has 8 GB of RAM
  max_in_progress_per_profile: 1
  failure_limit: 2
```

Handoff rules:

1. **Workers don't see sibling tasks.** Each task's body includes everything: identifier, exact input and output paths, language, decisions made.
2. Each task carries an `--idempotency-key` derived from its identifier and stage, so a retry doesn't duplicate work.
3. The last specialist doesn't write to the user: it leaves a file in `outbox/ready/`. A delivery script (`--no-agent` cron every 10-15 min) sends it over the channel and moves it to `outbox/sent/`. Zero tokens and a single exit point.
4. The same script sends a notice if there are blocked tasks waiting for the user.

### Keeping the computer on

Cron and Kanban only run while the computer is awake and the gateway is running (`hermes gateway install` sets it up as a service). If the computer sleeps, everything pauses and resumes when it wakes up. On Mac laptops, a closed lid puts the computer to sleep even with `caffeinate`.

### Heavy jobs

Rendering video, opening a headless Chrome, capturing pages, generating voice locally or transcribing use a lot of memory. So the computer doesn't freeze:

- Every script in any squad that does any of this takes the **lock** `{{ROOT}}/.heavy-lock`, so only one runs at a time even if different bots or squads ask for it. It is handled by the shared `{{ROOT}}/scripts/heavy_lock.py`. The first squad that needs it creates it; its specification is in `squads/marketing/05-scripts.md`.
- There is a single copy of each binary: the system's Chrome, one FFmpeg and one Node.
- Premium image, video and voice AI runs through an API: it uses no local memory.
- With 8 GB of RAM: `max_in_progress: 2`.

## 6. Memory

- Hermes memory (`MEMORY.md`, `USER.md`) is **per profile** and small.
- Only the **orchestrator** has memory enabled: a summary of the user and where their profile is.
- The shared source of truth is the files in `~/Hermes/user/` and each squad's profiles.
- Optional: the **Honcho** provider shares a model of the user across profiles. It is not needed to get started.

## 7. Criteria for splitting or merging bots

- **Promote a skill or subagent to its own bot** if its quality is repeatedly weak and it needs another model, if it needs permissions the current bot must not have, or if the context fills up.
- **Merge two bots** if they always run together, read the same things and neither needs independence from the other.
- **Turn a bot into a script** if its output is always the same for the same input.

Every structural change is recorded in `00-evaluation/02-decisions.md` in the plans repository.
