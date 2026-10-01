# Marketing squad: how many bots, who leads, and with which tools

2026-09-25 · Squad: marketing · Outcomes: D-012 to D-023 in `02-decisions.md`

> Criterion: it works for anyone on Mac, Windows or Linux. We pick the best tool that installs locally and is lightweight, so the machine does not freeze when a flow uses several tools at once.
> Hermes facts come from its official documentation (September 2026); third-party figures from their official sites or 2026 comparisons. Memory figures marked "(est.)" are estimates, measured during installation.

## Requirements

An in-house squad covering motion and video, plans and guides, social media and copywriting, data analysis, creatives, market and trend research, landing pages, design and email. Each delivery is a **proposal refined** with the user. The user talks to a **director** who delegates. **Several projects run at once**. A **visual place** on the computer shows everything. Condition: **more complex is not necessarily better.**

---

## 1. How many specialists?

Twelve roles were requested. According to the base (`01-principles.md` §1.3), a bot is justified only by independence, permissions, model capability or context.

| Option | Pros | Cons |
| --- | --- | --- |
| **A · One bot per role (12)** | Familiar names; each SOUL very focused | 12 profiles to configure. Long chains: each Kanban handoff adds up to a minute, plus an agent's startup. Roles that always work together (idea and copy, design and motion) pass files to each other for no reason. More points of failure. Exceeds the base's maximum of 5 |
| **B · By discipline (7)**: strategist, researcher, writer, designer, motion, developer, reviewer | Separates research and the web | The researcher and the strategist read the same things. Designer, motion and developer use the same tools (code, rendering and vision). 7 exceeds the maximum of 5 |
| **C · By type of work and permissions (4)** | Each bot has a reason from the base. A typical piece goes through 3 bots. Related disciplines share tools. Up to 4 bots move forward in parallel on different brands | The producer piles up many skills (Hermes loads them only when needed). The strategist also acts as researcher and analyst |
| **D · Minimal (2)**: one bot that does everything plus a reviewer | The simplest | Combines reading the web (untrusted text) with the terminal. Everything goes in single file, because a bot works on one task at a time. A generic SOUL performs worse |

**Recommendation: C.**

| Bot | Requested roles it covers | Why it is a separate bot |
| --- | --- | --- |
| `marketing-strategist` | Market research, trends, competitors, data analysis, plans, calendars, campaign briefs and guides | **Permissions**: it is the only one that reads the web. It thinks before the others produce |
| `marketing-creative` | Ideas and concepts, copywriting (social, ads, email, landing pages), scripts and storyboards | **Permissions**: it never reads the web, so what goes out to the public is not contaminated by instructions hidden in external pages. It works in parallel with the strategist |
| `marketing-producer` | Design, images, motion and video, landing pages, HTML emails and document layout | **Permissions and model**: it is the only one with a terminal for rendering, and it can use a model that is stronger at design with code (§5) |
| `marketing-reviewer` | Quality control of everything before it reaches the user | **Independence**: whoever made a piece never reviews it |

**When to split** (base criteria, §7):

- Full websites belong to the web squad (D-030); the producer keeps campaign landing pages.
- Split `marketing-analyst` off from the strategist if there is a lot of connected data.

---

## 2. Who is "the director"?

| Option | Pros | Cons |
| --- | --- | --- |
| **A · The orchestrator, with the `orchestration-marketing` skill** | A single point of contact for the whole ecosystem (D-004). It already has a channel, memory and questions with buttons. No extra hops | Its skill grows, although it is only loaded when talking about marketing |
| **B · A `marketing-director` bot behind the orchestrator** | All the marketing know-how in a single bot | Double interpretation (user → orchestrator → director). One more hop and one more startup on every request. The director does not talk to the user |
| **C · A director with its own channel** (another Telegram bot or a Discord channel) | A separate marketing conversation | Breaks the single point of contact. Two bots may write at the same time. More configuration |

**Recommendation: A.** The separation that C is after can be achieved without another bot:

- **One Telegram topic (or Discord channel) per brand.** Each one has its own session and context. Hermes supports this with `dm_topics` and can load a different skill in each topic. Topics are set up by the installer AI, never by a script, and while a brand does not have its own, it uses the main chat with its name.
- **The heavy marketing work is done by the strategist**, for example breaking a campaign or a week down into pieces. The director routes, asks and presents.

**Revisit if:** there are many brands or clients and the orchestrator gets overloaded. Then switch to option B, in Level 3.

---

## 3. Several projects at once

| Option | Pros | Cons |
| --- | --- | --- |
| **A · One folder per brand and a Kanban `tenant`** | Isolation by folder: each task carries its brand's workspace. A label on the board: the visual Kanban filters by tenant. The same bots serve all brands. It is the pattern Hermes documents: "one specialist fleet can serve multiple businesses" | Soft isolation: it depends on rules and paths |
| **B · One Kanban board per brand** | Hard isolation | Every command and every script must specify the board, and a board has to be created at each onboarding |
| **C · One squad per brand** | None | Duplicates the bots for every brand. Rejected |

**Recommendation: A**, plus one topic or channel per brand in the messaging app.

---

## 4. How is work reviewed?

| Option | Pros | Cons |
| --- | --- | --- |
| **A · Reviewer bot with its own card**, as in the job search squad | Proven. Independent. Uses 5 lenses in subagents and controls the correction round | One more handoff per piece |
| **B · Native Kanban review** (`kanban_request_review` / `kanban_request_changes`) | A single card per piece; it returns the piece to whoever made it without creating new tasks | By default Hermes launches the review with a software review skill (`sdlc-review`). How to use your own is not documented |
| **C · No reviewer**: the user reviews | Faster | Errors reach them, there are more rounds of changes and their time is wasted |

**Recommendation: A.** B is tested during installation and adopted if it respects the squad's own skill.

---

## 5. The producer's model

In motion and design with code, the model makes a visible difference; in September 2026 Claude Opus 5.5 stands out.

| Option | Pros | Cons |
| --- | --- | --- |
| **A · Everyone on the `main_model`** | The simplest | The quality of design and motion made with code depends heavily on the model |
| **B · The producer on `production_model`** | A capability exception, provided for in D-011: the producer is the one who writes visual code. It is a single value in its configuration, and if the user has no access to a better model, the main one is used | The producer's tasks cost more |
| **C · Only the motion cards on another model** (`--model` per task) | Cheaper | The `kanban_create` tool the bots use does not document the model parameter; only the CLI and the dashboard have it |

**Recommendation: B.** If `kanban_create` accepts `model` during installation, you can switch to C.

Vision is a separate matter: if a bot's model cannot see images, `auxiliary.vision` is configured and the bot keeps its model (D-021).

---

## 6. The visual board ("Studio")

The starting point is that **the files are the source of truth**. Each piece has a folder with a `card.md` (YAML header with status, brand, channel, date and cover) and subfolders `v1/`, `v2/`… Any board is just a window onto those files.

| Option | Load on the machine | Pros | Cons |
| --- | --- | --- | --- |
| **A · Custom static generator**: `studio.py` writes an `index.html` | No service: it runs for a few seconds | Nothing to install, and the same on all three operating systems. Tailor-made: covers, side-by-side versions, video, landing page, calendar and history. It grows with use. In Hermes Desktop it opens next to the chat (`desktop_preview`) | Read-only: approving is still done through chat |
| **B · Studio as a Hermes plugin**: a Desktop page and a web dashboard tab, with a `plugin_api.py` backend | No extra process: the backend runs inside Hermes | Buttons to approve and request changes, with a native look. No build step: one file for Desktop, another for the dashboard, and the backend in Python (official SDK) | More code. The SDK is recent and has to be enabled in the configuration |
| **C · Obsidian** as a viewer | Only while it is open: 300-600 MB (est.) | Free, including for commercial use. Reads the same properties: cards with covers and an editable table | A separate app. Its native kanban is still in paid early access, and it has no native calendar |
| **D · Apps with their own server or database**: NocoDB, Baserow, Teable, Plane, Penpot, Anytype, AFFiNE, SiYuan | Docker or always-on services, 1 to 4 GB. Docker Desktop alone uses 1.2-2.5 GB before starting anything | Rich views | Heavy, or with the data trapped in their own format. **Rejected** |

**Recommendation:**

- **Level 1:** A.
- **Level 2:** B, which reads the same files, with nothing to migrate.
- **C** is optional, for anyone who already uses Obsidian.

Also, the Kanban board that comes with Hermes (in Desktop and in `hermes dashboard`) shows **what is in production** for free, filtered by brand.

---

## 7. Motion and video

| Option | Load (reference measurement: a 10 s clip at 1080×1920 on a 16 GB machine; varies by machine) | Pros | Cons |
| --- | --- | --- | --- |
| **A · HyperFrames** (HeyGen, Apache 2.0) | 124 MB package. **Uses the system Chrome and FFmpeg**. Peak of about 1.2 GB. With 8 GB or less it switches to low-memory mode on its own: one worker, which is a Chrome of about 256 MB | HTML, CSS and GSAP, which models write better than a framework. Hermes ships the `hyperframes` skill, which covers local voice-over, subtitles, identity through `DESIGN.md`, and contrast and overflow validation. It has `check` and `snapshot` for reviewing with vision. Free license, including for companies | Still before version 1.0, so the version is pinned. Sends telemetry by default (turned off during installation) |
| **B · Remotion** | 225 MB package, plus its own Chrome per project (193 MB) and its own FFmpeg. Peak of 1.4-1.9 GB | Very mature, with advanced animations | Teams of 4 or more people need a license (US$25 per seat per month). Requires macOS 15 or later. You need to know React |
| **C · AI video**: Veo 3.1 Fast (US$0.10-0.12/s), Kling 3.0 (~US$0.075/s) or Seedance, with the Hermes `video_generate` tool | Nothing local: it is an API | Shots that cannot be filmed | Paid per second, and gives less brand control. The Sora 2 API shut down on September 24, 2026 |

**Recommendation:**

- **A** by default.
- **C** as a Level 2 add-on, if there is budget. It is best to animate an already approved brand image and use that supporting shot inside a HyperFrames composition.
- **B** only if the user already uses it and complies with its license.

**Audio:**

- **Free voice:** Kokoro-82M, local, Apache 2.0, 86 to 326 MB, CPU only, with voices in several languages (3 of them in Spanish). HyperFrames integrates it.
- **Premium voice:** ElevenLabs.
- **Music:** ElevenLabs Music (commercial license) or free libraries such as Pixabay Music or Mixkit.
- **Subtitles:** whisper.cpp `base` or `small`, 0.4 to 0.85 GB of RAM.
- **Rejected:** Edge-TTS (no commercial license), MusicGen (non-commercial weights), Udio (does not allow downloads) and trending songs on business accounts.

**About the model:** Claude Opus 5.5 (September 2026) is the example for `production_model` (§5) because its release notes highlight graphics quality and the community pairs it with HyperFrames. Any model strong at code works; quality is validated with `check`, `snapshot` and the reviewer.

---

## 8. Images and design

| Option | Pros | Cons |
| --- | --- | --- |
| **A · Image AI only** | Fast | AI fails at text, logos and exact colors. `image_generate` only accepts three aspect ratios (landscape, square and portrait), and the model is set by the user, not the agent |
| **B · HTML/CSS with the brand's tokens plus AI for photos and illustrations** | Exact fonts, colors, logo and sizes (1080×1350, 1080×1920…). The HTML is rendered to PNG or PDF by a headless Chromium that runs for just a few seconds. AI only supplies the ingredients. With no budget, free stock libraries are used | Templates have to be maintained per format |
| **C · Cloud design tools** (Canva, Figma) through MCP connectors | Editable by the user | Needs an account and sometimes a paid plan. Left as a Level 3 option for those who already use them |

**Recommendation: B.**

- **Visual identity.** It lives in one `DESIGN.md` per brand: Google's open specification, with tokens and "do/don't" rules, which the `hyperframes`, `claude-design` and `design-md` skills already read and validate. During onboarding, the strategist uses the browser to note the colors, typefaces and assets of the brand's website; the producer downloads those assets (images and fonts only) and writes the `DESIGN.md`. This way the bot with a terminal does not read web pages.
- **Rendering.** HTML templates are rendered to PNG with Playwright using the same system Chrome as HyperFrames: a single browser on the machine.
- **Image model.** It is chosen during personalization based on the budget (`01-personalization.md`). September 2026 references, always through an API (running locally they would need 13 GB or more of video memory):

  | Use | Model |
  | --- | --- |
  | All-rounder | Nano Banana 2, with up to 14 reference images |
  | Main pieces and brand consistency | Nano Banana Pro |
  | Lots of text inside the image | GPT Image 2.5 |
  | Vectors | Recraft V4.1 |
  | Photorealism | FLUX.2 [pro] |

  Hermes offers them depending on the provider that is configured (FAL, OpenAI, OpenRouter…).
- **Logos.** Never a final logo made with AI: concepts are explored, vectorized and finished by a human.
- **No budget.** Own photos, or photos from stock libraries with a free API: Pexels (photos and video), Pixabay and Unsplash, each with its own attribution rules. Self-hosted Google Fonts typefaces and freely licensed icons (Lucide, Tabler, Phosphor).

---

## 9. Publishing, sending and measuring

| What | Level 1 | Level 2 | Rejected |
| --- | --- | --- | --- |
| **Social media** | Manual: the approved piece arrives with the copy ready and a reminder on publishing day | A cloud scheduler, with apps already approved by each network: **Postiz Cloud** (official guide for Hermes, direct upload) or **Buffer** (free with 3 channels; needs a public URL for the files). Always as a draft, and scheduled only with confirmation | Postiz or Mixpost self-hosted on the machine (8 containers, 4-8 GB and a developer app per network). Each network's direct APIs (app review; without an audit, TikTok and YouTube publish as private) |
| **Email** | HTML and text ready to paste into the provider | A draft through the API in **Brevo** (300 free sends per day) or **Kit** (for creators). HTML with MJML in Python. The user confirms sending | Free MailerLite and Mailchimp: they do not accept custom HTML through the API |
| **Data** | CSV exports plus a script | Read-only MCP connectors: official GA4 and Google Ads, community Search Console | Meta and TikTok connectors with write permission, unless they are limited to reporting |
| **Landing pages** | Local, with screenshots and a zip | Cloudflare with a brand subdomain, deployed only with confirmation | Vercel Hobby and GitHub Pages: they do not allow commercial use |

---

## 10. Load on the machine

| Component | What it leaves running | Resource use |
| --- | --- | --- |
| Hermes gateway (already there from the base) | One service | The only always-on one |
| Studio (static generator) | Nothing | Seconds when regenerating; one tab when viewing it |
| Piece rendering (Playwright with the system Chrome) | Nothing | One 150-300 MB tab, for a few seconds |
| Video rendering (HyperFrames) | Nothing | Peak of about 1.2 GB for a simple clip; 2 GB of free disk space for the frame cache |
| Local voice (Kokoro) and subtitles (whisper.cpp `base`/`small`) | Nothing | Less than 1 GB each, never at the same time as a render |
| Image, AI video and voice (APIs) | Nothing | 0 locally |
| Publishing, email and data (cloud or on-demand MCP) | Nothing | 0, or a small process only while in use |
| Obsidian (optional) | Only while open | 300-600 MB (est.) |

Minimal stack rules, which also work for 8 GB machines:

1. **No Docker, no databases and no self-hosted servers.** The only always-on service is the Hermes gateway.
2. **A single copy of each binary.** One system Chrome (HyperFrames uses it on its own, and Playwright with `channel: "chrome"`), one system FFmpeg, Node 22 and a Python `.venv` for the scripts.
3. **One heavy job at a time.** Video rendering, screenshots, local voice, transcription and the browser share a **lock**: the lock file `~/Hermes/.heavy-lock`. Kanban already limits each bot to one task; the lock covers the case of two different bots or two squads.
4. **With 8 GB:** `max_in_progress: 2`, HyperFrames in low-memory mode with `--workers 1` and 30 fps, internal drafts at `draft` quality, and Obsidian closed while rendering.
5. **Everything that publishes or sends runs in the cloud.** Image AI, video AI and premium voice go through APIs.

## What remains to be verified during installation

- Whether `kanban_create` accepts `model` (§5).
- Whether native Kanban review supports a custom skill (§4).
- How many subagents a Kanban worker allows (`delegation.oneshot_max_children`, 2 by default in non-interactive runs). The reviewer uses 5.
- Whether Telegram groups several `MEDIA:` items into an album, and the maximum video size the bot accepts. The Telegram documentation says 50 MB for bots.
- That Playwright uses the system Chrome (`channel: "chrome"`), as HyperFrames already does, and that the Hermes browser can share it.
- HyperFrames support on Windows with an ARM processor (not documented).
