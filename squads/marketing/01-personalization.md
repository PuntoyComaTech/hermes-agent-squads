# Personalization: marketing agency

> There are two personalization moments:
> - **Agency profile**: in STEP 1 of the installation, only once. It says how the agency works for this user. It produces `marketing-profile.yaml` in `{{ROOT}}/projects/marketing/`.
> - **Onboarding of each brand**: every time the user onboards a project, during the installation or later, by chat with the orchestrator. It produces the brand's files in `brands/<slug>/`.
>
> **Do not repeat** what is already in `user/profile.md` (name, country, timezone, languages, channel, schedule, tone, autonomy, main model): read it and use it.

## Part 1 · How to run the interview (instructions for the AI)

1. Read `user/profile.md` and your memory. Start with two questions: **who the agency will work for** and **which brands the user wants to onboard** (name and website or social profiles). With the website and social profiles, the rest of the brand is researched, not asked.
2. Build a draft with what you infer and show it. Mark anything unconfirmed with `(?)`.
3. Ask for what is missing: required fields first, at most 5 at a time, with options when there are any.
4. If an answer is vague ("increase sales", "something modern"), ask for the concrete data the system needs ("How many sales per month do you have today, and how many do you want in 90 days?").
5. Do not set default values silently. If the user does not know, propose a value, explain its effect in one line and ask for confirmation.
6. Adapt your language to `marketing_experience`: with a beginner, no jargon; explain each term in one line.
7. Show the complete final YAML and ask for an "ok".

## Part 2 · Agency profile

### Required

| Field | Question | Why it matters |
| --- | --- | --- |
| `works_for` | Who will the agency work for? my own business · clients (I'm a freelancer or an agency) · the company I work for · my personal brand · several of these | Who approves, how proposals are presented, and the separation between client brands |
| `marketing_experience` | How much do you know about marketing? I'm just starting · I get by · it's my job | How the director explains each proposal |
| `initial_brands` | Which projects do you want to onboard first? Name and website or social profiles for each | They are onboarded when the installation finishes |
| `services` | What do you want the agency to do? Choose several: social media content · ads · video and motion · email · landing pages · plan and strategy · results reports · visual identity · articles and SEO. And, if needed: influencers · community · partnerships · press · pricing and offers | Which flows are enabled, which skills are installed in each bot, and whether the video engine is installed |
| `approval_mode` | How do you prefer to approve? all together once a week (recommended) · piece by piece as they are ready | Whether proposals arrive as a batch or one by one |
| `planning` | What day and time should I plan the following week? (each brand can have its own, or "none") | Time of the weekly automation; the batch arrives a few hours later |
| `review_minutes_per_week` | How many minutes per week can you spend reviewing proposals? | Used to suggest the quota and the length of messages |
| `weekly_quota_per_brand` | How many pieces per week and per brand, at most? (each brand can have its own) | Pace and spending limit. Suggestion: 3-5 for a small brand |
| `ai_budget_usd_month` | How much can you spend per month on AI-generated images, video or voice? With 0 it still works: design with code, free stock photos or your own, and a free voice | Which providers are configured, and the monthly cap the producer tracks in `ai-spend.csv` |
| `notify_window` | On which days and at what times can the agency message you? (suggestion: the schedule in your profile) | Window in which `deliver.py` sends; outside it, messages are held |

### Technical (the AI detects them; ask only for what it cannot see)

| Field | How it is decided | Effect |
| --- | --- | --- |
| `machine` | OS, RAM and free disk space (the AI reads them) | `render_mode`: `light` with 8 GB or less (one render at a time, 30 fps video up to 60 s); `normal` with more |
| `production_model` | Propose the model with the best results in design and motion with code that the user has access to (in September 2026, for example, Claude Opus 5.5). If they have no access to a better one, `main_model` is fine | The producer's model (D-016) |
| `image_ai` | Based on `ai_budget_usd_month`, **a single model** (Hermes does not let the bot change it per piece). **0**: no image AI; own photos or free stock photos, and illustrations in SVG or HTML. **Low**: a fast, cheap one, for example FLUX.2 [klein] or Nano Banana 2 Lite. **Medium or high**: the best all-rounder, Nano Banana 2 (it edits and accepts up to 14 references); if quality matters more than cost, Nano Banana Pro. If the brand lives on vector illustrations, Recraft V4.1. Always among those offered by the provider configured in Hermes | The producer's `image_gen.provider` and `image_gen.model` |
| `stock_photos` | Free keys for Pexels, Pixabay or Unsplash (recommended with a budget of 0: at least Pexels) | `stock_photos.py` uses them to search for photos and videos with a commercial license |
| `voice` | Free: Kokoro, local, openly licensed, with voices in several languages, including English and Spanish (HyperFrames integrates it). Premium: ElevenLabs or Gemini TTS, with a key. **Do not use Edge-TTS in public pieces**, because it has no commercial license | Voice-over for videos |
| `music` | No music. A free library (Pixabay Music, Mixkit) or the brand's own licensed music, in each brand's `identity/music/` folder. ElevenLabs Music, which has a commercial license (Level 2). Never trending songs on business accounts | Whether videos have music, and where it comes from |
| `topic_per_brand` | If the channel is Telegram or Discord: one topic or channel per brand? (recommended with 2 or more brands) | The installer AI creates the topic for each initial brand; later ones are added through the maintenance section of `04-installation.md`. Until it has a topic, a brand uses the main chat with its name |

### Optional

| Field | Question |
| --- | --- |
| `current_tools` | What do you use today? Canva, Figma, Meta Business Suite, Buffer, Metricool, Brevo, Mailchimp, Kit, Google Analytics, Shopify, WordPress, Webflow… |
| `review_on` | Do you review more on your phone or on your computer? (phone: covers and a lightweight video in the message; computer: details in the Studio) |
| `proposal_detail` | Short proposals, or with one line on why each one works? |
| `weekly_summary` | Do you want a summary every Monday with what was approved, what is pending and what is coming? |
| `monthly_report` | Do you want a results report on the 1st of each month? |
| `studio` | Do you want the visual board on your computer? (recommended) |
| `obsidian` | Do you use Obsidian? If so, it is also set up as a viewer |

### Automation (suggested values)

| Field | Suggested | What it controls |
| --- | --- | --- |
| `batch_wait_hours` | 6 | How long an incomplete batch waits before it is sent with whatever is ready |
| `reminder_minutes_before` | 30 | Reminder before posting time (Level 1) |
| `reviewer_rounds` | 1 | Automatic fixes before escalating to the user |
| `reviewer_threshold` | 80 | Minimum score (0-100) for a piece to reach the user |
| `quiet_until` | empty | Date until which `deliver.py` holds messages ("quiet until Monday") |

## Part 3 · What each answer changes

| Field | Effect on the system |
| --- | --- |
| `works_for` = clients | Each brand is created with `approver: client`. Proposals come with a text ready to forward to the client, and one brand's data never appears in another brand's messages |
| `marketing_experience` | **Beginner**: the director explains without jargon and justifies each proposal in one line. **Professional**: shorter messages, with assumptions and metrics |
| `services` | Which third-party skills each bot gets (`03-bots.md` §3), which piece types the calendar proposes, and whether HyperFrames and FFmpeg are installed |
| `approval_mode` | **Batch**: `deliver.py` groups by week or campaign. **Piece**: it sends each one when it is ready |
| `planning` | Time at which `plan_week.py` creates the weekly task for each brand |
| `review_minutes_per_week` and `weekly_quota_per_brand` | Limit of pieces per week in each calendar |
| `ai_budget_usd_month` | Image provider and model, premium voice and, at Level 2, AI video; monthly cap the producer tracks |
| `notify_window` and `quiet_until` | When `deliver.py` may write |
| `render_mode` | Render options and the limit of simultaneous tasks in Kanban |
| `topic_per_brand` | One topic or channel per brand, and `destination` in `settings.yaml` |
| `current_tools` | Extra delivery formats (for example, a PDF that Canva can import) and Level 2 connectors |
| `review_on` | What each message attaches, and whether it links to the Studio |
| `weekly_summary` / `monthly_report` | Orchestrator and strategist crons |

## Part 4 · `marketing-profile.yaml`

```yaml
# {{ROOT}}/projects/marketing/marketing-profile.yaml
version: 1
works_for: own_business           # own_business | clients | employer | personal_brand | mixed
marketing_experience: beginner    # beginner | intermediate | professional
services: [social, video, email, reports]   # social | ads | video | email | landings | strategy | reports | identity | seo | influencers | community | partnerships | pr | pricing
approval_mode: batch              # batch | piece
planning: "Thursday 10:00"        # in the timezone from user/profile.md
review_minutes_per_week: 30
weekly_quota_per_brand: 4
ai_budget_usd_month: 0
notify_window: {days: [mon, tue, wed, thu, fri, sat], from: "08:00", to: "20:00"}
quiet_until: null

technical:
  render_mode: light              # light | normal
  production_model: "{{main_model}}"
  image_ai: none                  # none | <provider>/<model>
  voice: kokoro                   # kokoro (local, free) | elevenlabs | gemini | <another with a commercial license>
  music: library                  # none | library | ai
  topic_per_brand: true
  stock_photos: [pexels]          # keys in {{M}}/.env

optional:
  current_tools: [canva, meta_business_suite]
  review_on: phone                # phone | computer
  proposal_detail: with_why       # short | with_why
  weekly_summary: false
  monthly_report: true
  studio: true
  obsidian: false

automation:
  batch_wait_hours: 6
  reminder_minutes_before: 30
  reviewer_rounds: 1
  reviewer_threshold: 80

level: 1
```

## Part 5 · Onboarding each brand

### Procedure

1. **Sources.** The user gives the name and whatever exists: website, social profiles, Google Maps, documents (brand manual, presentations, an already written product context). If they send files through the chat, their path is noted.
2. **Auto-draft.** The strategist (ONBOARDING mode) researches the public sources: website, social profiles, reviews and competitors. It writes:
   - the drafts of `context.md` and `brand.md`;
   - an empty `preferences.md`;
   - `settings.proposed.yaml`, with channels, frequencies and key dates;
   - `identity/observed.md`, with colors, typefaces and assets from the brand's website;
   - the diagnosis piece, with the missing questions.
3. **Visual identity.**
   - If the brand has a logo, colors and typefaces, the producer downloads the listed assets, organizes them in `identity/` and writes `DESIGN.md`.
   - If it does not, the producer proposes a basic identity: palette, typefaces, image style and templates.
   - A new logo only if the user asks for it.
4. **Questions.** When the diagnosis arrives, the director (orchestrator) asks only for what is missing: the required items below, at most 5 at a time.
5. **Approval.** The user approves `context.md`, `brand.md`, `DESIGN.md` and the proposed settings. They are the source of truth: every piece is judged against them. Until that "ok", the brand stays at `active: false`: it is not planned and does not take requests.
6. **Topic or channel.** If the user has topics or channels per brand, the director creates the brand's skill and tells the user how to request the topic. The installer AI adds the topic (maintenance section of `04-installation.md`).

### Required (10)

1. Name and what it does, in one sentence.
2. What it sells, and at roughly what price.
3. Who it is for, and who it is **not** for.
4. Country, city and markets. Language, variant and form of address the brand uses: informal, formal or voseo (in Spanish: "tú", "usted" or "vos").
5. Website and social profiles, if any.
6. Main goal for the next 90 days, and how you will know it was achieved.
7. Two or three competitors or alternatives.
8. How the brand speaks: 3 adjectives and banned words.
9. Logo, colors and typefaces (files), or permission to propose them.
10. Monthly budget for ads and tools. "Zero" is a valid answer.

### Recommended

- Which channels it uses today, which ones work, and how often it wants to post on each.
- What has already been done that is worth recognizing.
- Customers' literal phrases; testimonials with permission.
- Objections it hears.
- Legal or industry restrictions (health, finance, alcohol, minors).
- Who approves, if it is a client.
- What to ignore this quarter.
- Key dates: seasons, launches, local holidays.
- How bold the brand can be: conservative, balanced or bold.
- Available assets: photos, videos, products to photograph, licensed music.

### Only if applicable (B2B, SaaS, e-commerce with data)

- Buyer personas.
- Funnel numbers.
- Cost per customer, average order value and repeat purchases.
- Connected tools: Google Analytics, Search Console, CRM, email provider.

## Part 6 · Each brand's files

```text
brands/<slug>/
├── context.md         # strategy: business, audience, competitors, goals, restrictions
├── brand.md           # voice, verified proof points, distinctive assets, usage rules
├── DESIGN.md          # visual identity in Google's open format
├── preferences.md     # what was learned from the user's replies
├── settings.yaml      # how the agency operates for this brand
└── identity/          # logo, fonts, product photos, licensed music
```

### `context.md`

```markdown
---
brand: <slug>
version: 1
updated: <YYYY-MM-DD>
---
# Context · <Name>

## A. Fact sheet
- What it is, in one sentence:
- Archetype: local shop · local service · restaurant · independent professional · personal brand or creator · e-commerce · SaaS or app · B2B · nonprofit · other
- Relationship with the user: own · client · employer
- Country, city and markets:
- Language, variant, form of address, currency and timezone: in settings.yaml
- Website and social profiles:
- Stage: pre-launch · active · stalled · growing

## B. Offer
- Key products or services, with approximate price:
- Category (which "shelf" people look for it on):
- Business model:

## C. Audience
- Segments and ideal customer:
- Jobs it does for them (2-3):
- Stated problem vs. real problem:
- Who it is NOT for:

## D. Problem and change
- Core pain, why the alternatives fail and what that costs them:
- Forces of change: what pushes them, what pulls them, what habit holds them back, what they fear:
- Top three objections and their answers:

## E. Competitors
- Direct, secondary and indirect, and how each one falls short:
- Who is marketing to this same audience today, and whether they are growing or stalled:

## F. Customer language
- Literal phrases about the problem and the solution:
- Words they use and words they avoid:

## G. Goals and measurement
- 90-day business goal and how you will know:
- Key conversion action:
- Current metrics, if any:

## H. Current state
- Active channels and what works:
- What has already been done that is worth recognizing:
- Monthly budget (ads, tools, production):
- Who else touches the marketing:

## I. Restrictions
- Regulated industry, banned topics, approvals, trademarks, the country's disclosure rules:
- What to ignore this quarter:

## Changes
- v1 · <date> · Initial context (onboarding)
```

Versioning rule: every substantive change bumps the version, updates the date and **adds a line at the top** of "Changes" saying which sections changed and why. Past lines are never rewritten. A positioning change is announced to the user, because everything that comes after will be built on it.

### `brand.md`

```markdown
---
brand: <slug>
version: 1
updated: <YYYY-MM-DD>
---
# Brand · <Name>

## Voice
- 3 to 5 adjectives:
- Tone per channel (e.g., friendly on Instagram, expert on LinkedIn):
- Form of address and variant:
- Vocabulary YES:
- Vocabulary NO:
- Emojis and punctuation (which ones, how many):
- Call-to-action rules:
- Voice samples (2-3 texts the user approves as "this is how we talk"):

## Proof points (verified only)
| Proof point | Type (figure, testimonial, press, certification) | Verified | Permission to use | Source |
| --- | --- | --- | --- | --- |

## Distinctive assets
- What always makes it recognizable (colors, character, phrase, sound, format):

## Usage rules
- What never to say or show:
- Banned claims:
- Mandatory disclosure:
- Creative risk level: conservative · balanced · bold

## Changes
- v1 · <date> · Initial brand (onboarding)
```

### `DESIGN.md`

Visual identity in Google's open `DESIGN.md` format (alpha version, July 2026). It has a YAML header with tokens (colors, typography, radii, spacing, and components with references such as `{colors.primary}`) and sections in a fixed order: Overview, Colors, Typography, Layout, Elevation, Shapes, Components, Do's and Don'ts.

- The installer AI and the producer follow the current version of the specification with the `design-md` skill.
- It is validated with `npx -y @google/design.md lint DESIGN.md`, which checks contrast, among other things.
- It is exported to CSS variables with `export`.

It is used by the piece templates, HyperFrames, landing pages and documents.

### `preferences.md`

```markdown
# Learned preferences · <Name>
> Read by the creative, the producer and the reviewer before each piece. The orchestrator adds one line for
> each reply from the user; the strategist distills it every week into the three lists.

## Likes
## Dislikes
## Firm rules (stated by the user)

## Log
- <date> · <ID> vN · <approved | change: "literal text" | no: "reason">
```

### `settings.yaml`

```yaml
brand: cafe-luna
name: Café Luna
emoji: "☕"
active: true                    # false = not included in weekly planning
language: es-MX
address: informal               # informal | formal | voseo
currency: MXN
timezone: America/Mexico_City
services: [social, video, email, reports]   # subset of the agency's services
channels:
  - network: instagram
    formats: [carousel, reel, story]
    per_week: 3
    times: ["tue 09:00", "thu 18:00", "fri 12:00"]
  - network: tiktok
    formats: [reel]
    per_week: 1
  - network: email
    per_week: 1
planning: "Thursday 10:00"      # in the user's time; "none" = no weekly planning; if missing, the agency's value
weekly_quota: 4                 # if missing, the agency's weekly_quota_per_brand applies
approval_mode: batch            # batch | piece; if missing, the agency's value
current_site: {platform: none, url: ""}   # none | static | wordpress | webflow | shopify | other
approver: user                  # user | client
destination: topic              # topic | channel | main (filled in by the installation)
publishing: manual              # manual (Level 1) | scheduled (Level 2)
creative_risk: balanced         # conservative | balanced | bold
monthly_ad_budget: 0
key_dates:
  - "2026-11-02 Day of the Dead"
  - "2026-12-12 Christmas season"
```

## Part 7 · Examples (fictional people)

### Full example: neighborhood café, no budget

**Lucía**, owner of "Café Luna", a specialty coffee shop in Guadalajara (Mexico):

- She is new to marketing. She posts on Instagram when she can and wants to try TikTok.
- She has a list of 300 customers who left their email.
- She reviews on her phone and can spend 30 minutes per week.
- She does not want to spend on AI.
- Her channel is Telegram.
- Her computer is an 8 GB laptop.
- She has no access to a better model than her main one.

`marketing-profile.yaml`: the one in Part 4, as is. `brands/cafe-luna/settings.yaml`: the one in Part 6.

What it produces in the system:

- Planning runs on Thursdays at 10:00, and the batch of 4 proposals arrives the same afternoon, in the "☕ Café Luna" topic.
- Carousels are designed with HTML over her photos (she sends 20 photos of the café at onboarding). No image is generated with AI.
- The weekly reel is made with HyperFrames: low-memory mode, 30 fps, a free local voice in the brand's language (Kokoro) and subtitles. When the brand grows, it can move to a premium voice.
- The weekly email arrives as HTML and plain text, ready to paste into her provider.
- On the last day of each month, she gets a reminder to export her Instagram stats to the brand's folder; the report arrives on the 1st.
- Everything is explained to her without jargon, with one line on why each piece works.

### Other cases (what changes)

| Case | Differences in the profile | Effect |
| --- | --- | --- |
| **Andrés**, freelance B2B consultant in Madrid (Spain) | `services: [social, strategy, landings, email, seo]`; LinkedIn and newsletter; `approval_mode: piece`; es-ES with informal "tú" (tuteo); €20 per month for AI; has access to Claude Opus 5.5 | The producer uses Opus 5.5. Images with a cheap model. 90-day plan and articles. Landing page with a newsletter signup form. Short messages with metrics (`professional`) |
| **Estudio Nido**, a 3-person agency in Bogotá (Colombia) with 5 clients | `works_for: clients`; `topic_per_brand` on Discord, one channel per client; `weekly_quota_per_brand: 3`; monthly reports; Windows computer with 16 GB | Each client with `approver: client` and a text ready to forward to them. A dental clinic with industry restrictions (health): the reviewer escalates every medical claim. `render_mode: normal` |
| **Valentina**, course creator in Buenos Aires (Argentina) | YouTube, Instagram and email with Kit; launches; voseo (Argentine "vos"); 30 USD per month; WhatsApp as her channel (no topics) | Video as the main format. Launch campaign with 3 concepts. On WhatsApp, every message starts with the brand name. Premium voice if her budget allows |
