# Start here

> A guide for anyone, with no technical knowledge needed. At the end, the instructions for the AI that will do the installing.

## For the user

You will have an assistant (the **orchestrator**) that messages you on your messaging app and manages a team of specialist bots. In the job search, for example, you get a message with **the link to the job opening and a CV made for it**, and you just reply "apply", "change this" or "no".

### What you need

1. A computer that stays on most of the day (Mac, Windows or Linux).
2. **Hermes Desktop**, installed from its official page (repository `github.com/NousResearch/hermes-agent`).
3. An **API key** from an AI model provider (recommended: OpenRouter). Hermes guides you the first time you open it.
4. Your messaging app: Telegram, Discord or WhatsApp (the installation tells you what to do to connect it).

### Steps

1. In your home folder, create a folder called **`Hermes`** and, inside it, another one called **`plans`**. Copy all the files from this repository there.
   - Mac: `/Users/<your user>/Hermes/plans`
   - Windows: `C:\Users\<your user>\Hermes\plans`
   - Linux: `/home/<your user>/Hermes/plans`
2. Open Hermes Desktop, go to the main chat and type:

   > Read the file `~/Hermes/plans/START-HERE.md` and follow the instructions for the AI.

3. Answer the questions it asks you. It takes 30 to 60 minutes the first time.
4. When it's done, you no longer use that chat: you talk to the orchestrator on your messaging app.
5. To add another area, write to the main chat, for example:

   > Read `~/Hermes/plans/START-HERE.md` and install the job search squad.

   > Read `~/Hermes/plans/START-HERE.md` and install the marketing agency squad.

   Some squads need programs on your computer (the marketing one, for example, uses Chrome, Node and FFmpeg to design and make videos). The installation tells you what they are and how much space they take, and asks for your permission before installing them. Everything is lightweight: nothing keeps running apart from Hermes.

### What the `Hermes` folder is

It's where **your data and the bots' results** live: your profile, your achievements, the generated CVs, the tracking of your applications. You can open it and read everything; they are regular files. It's in your home folder (not at the root of the disk) because there you don't need administrator permissions, and it is included in your backups.

Hermes also has its own hidden internal folder, `.hermes`, with each bot's configuration. You don't touch that one.

```text
~/Hermes/
├── plans/             these files (the instructions)
├── user/              your profile: what the bots know about you
├── orchestrator/      which squads you have installed, and metrics
└── projects/
    ├── jobs/          everything for the job search
    └── marketing/     your brands, their proposals and the Studio (visual board)
```

---

## For the installer AI

You are the installer of a bot ecosystem in Hermes. The plans are in `~/Hermes/plans/` (if not, ask where they are). You work from the `default` profile with the `terminal`, `file` and `skills` toolsets.

1. Read `plans/base/01-principles.md` and `plans/base/02-architecture.md` in full.
2. **If the base is not installed** (`~/Hermes/user/profile.md` does not exist or the `orchestrator` profile does not exist): follow `plans/base/06-base-installation.md`, reading the files in `plans/base/` that it points to.
3. **If the user asks for a squad**: check that the base is installed; then follow `plans/squads/<squad>/04-installation.md`, reading the files it points to.
   **If they ask for maintenance of a squad that is already installed** (for example, "add the topic for <brand>" or "update the marketing skills"): follow the Maintenance section of that same file.
4. Talk to the user in plain language. Explain each technical step in one line before doing it. Never ask them to edit files by hand if you can do it yourself.
5. Detect the operating system and the paths yourself. `~` is the user's home folder on any system.
