# Start here

> A guide for anyone, no technical knowledge needed. At the end, the instructions for the AI that installs the base.

## For the user

You get two assistants on your messaging app:

- the **orchestrator**, which manages your squads of specialist bots day to day. In the job search, for example, you get **the link to a job opening and a CV made for it**, and you reply "apply", "change this" or "no";
- the **builder**, which installs squads, creates new ones with you, and changes how everything is set up.

### What you need

1. A computer that stays on most of the day (Mac, Windows or Linux).
2. **Hermes Desktop**, from its official page (repository `github.com/NousResearch/hermes-agent`).
3. An **API key** from an AI model provider (recommended: OpenRouter). Hermes guides you the first time you open it.
4. Your messaging app: Telegram (recommended), Discord or WhatsApp. The installation tells you how to connect it.

### Steps

1. Download this repository into a folder called **`Hermes/plans`** in your home folder:
   - Mac: `/Users/<your user>/Hermes/plans`
   - Windows: `C:\Users\<your user>\Hermes\plans`
   - Linux: `/home/<your user>/Hermes/plans`

   With git: `git clone https://github.com/PuntoyComaTech/hermes-agent-squads.git ~/Hermes/plans`.
2. Open Hermes Desktop, go to the main chat and type:

   > Read the file `~/Hermes/plans/START-HERE.md` and follow the instructions for the AI.

3. Answer its questions (30 to 60 minutes). It installs the base: the orchestrator and the builder, each as its own bot on your app.
4. From then on, write to the **builder** to add squads:

   > Install the job search squad.

   > Install the marketing agency squad.

   > Install the web development agency squad.

   > Create a squad that helps me with <your goal>.

   Some squads need programs on your computer (marketing uses Chrome, Node and FFmpeg). The builder tells you what they are and how much space they take, and asks before installing. Nothing keeps running apart from Hermes.
5. Day to day, you talk to the **orchestrator**.

### Updating

When this repository gets new versions, write to the builder:

> Update my installation.

It explains each change, asks before applying it, and never overwrites your data or your changes. If your installation has no builder yet, type in the Hermes Desktop main chat:

> Read `~/Hermes/plans/START-HERE.md` and update my installation.

### What the `Hermes` folder is

It is where **your data and the bots' results** live: your profile, the generated CVs, your brands, your sites. They are regular files you can open. It sits in your home folder so it needs no administrator permissions and is included in your backups. Hermes also has a hidden internal folder, `.hermes`, with each bot's configuration: you don't touch it.

```text
~/Hermes/
├── plans/             these files (the instructions)
├── squads/            squads you create with the builder
├── user/              your profile: what the bots know about you
├── orchestrator/      which squads you have, and metrics
├── builder/           what is installed and the changes made
└── projects/
    ├── jobs/          everything for the job search
    ├── marketing/     your brands, their proposals and the Studio (visual board)
    └── web/           your websites
```

---

## For the installer AI

You are the installer of a bot ecosystem in Hermes, working from the `default` profile with the `terminal`, `file` and `skills` toolsets. The plans are in `~/Hermes/plans/` (if not, ask where). You only bootstrap: squads, configuration and later updates belong to the builder.

1. Read `plans/base/01-principles.md` and `plans/base/02-architecture.md` in full.
2. **Base not installed** (`~/Hermes/user/profile.md` or the `orchestrator` profile missing): follow `plans/base/06-base-installation.md`.
3. **"Update my installation" and no `builder` profile exists**: follow `plans/base/08-updates.md` (migration `0004-builder` creates the builder).
4. **Anything else** (install or create a squad, change configuration, update with a builder present): tell the user in one line to write it to the builder.
5. Talk in plain language. Explain each technical step in one line before doing it. Never ask the user to edit files by hand if you can do it.
6. Detect the operating system and paths yourself. `~` is the home folder on any system.
