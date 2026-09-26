# Scripts: marketing agency

> Script specifications. **The installer AI itself** (Hermes, with `terminal` and `file`) writes them in step 6 of the installation, on the user's computer; they also work as prompts for any coding AI.
> Level 1: `heavy_lock.py`, `hf.py`, `render_html.py`, `render_video.py`, `contact_sheet.py`, `check_piece.py`, `stock_photos.py`, `download_assets.py`, `render_document.py`, `deliver.py`, `studio.py`, `metrics.py`, `plan_week.py` and `monthly_report.py`. Level 2 adds publishing, email drafts, deployment, data connectors and the Studio with buttons.

## Common preamble

```markdown
Project: {{M}} = {{ROOT}}/projects/marketing. Everything in Python 3.11+ (venv in {{M}}/.venv), so
the same script runs on Mac, Windows and Linux; no .sh or .ps1. Deterministic code, no LLM.
Each script is a CLI with argparse: --json when requested, logs to stderr, exit 0 on success, 1 on
a data error, 2 on a network or external tool error. Idempotent. Tests with pytest in
{{M}}/tests/ and a short README in {{M}}/scripts/. Paths with pathlib; the scripts accept absolute
paths or paths relative to {{M}}. Don't read or write outside {{M}}, except: reading
{{ROOT}}/user/; using {{ROOT}}/scripts/heavy_lock.py and {{ROOT}}/.heavy-lock; reading the
orchestrator's configuration when the script says so; and deliver.py's daily commit in {{ROOT}}.
Secrets only from {{M}}/.env (ignored by git): crons don't inherit Hermes' keys. Everything heavy
(Chrome, rendering, FFmpeg, local voice, transcription, HyperFrames) goes through the lock. The
data contracts are in 02-architecture.md (attached).
```

### Traps that have already cost a real installation

These are not hypothetical. Each one was hit while building this squad and each one fails
quietly or misleadingly:

1. **`mjml` is npm, not Python.** `pip install mjml` installs an unrelated third-party
   reimplementation that does not compile MJML markup. Use `npm i -D mjml` and `npx mjml`.
2. **Weekday keys are English, always.** `datetime.weekday()` is 0=Monday, and YAML
   `notify_window.days` may be written as `lun`, `mon` or `Monday`. Normalize to
   `["mon","tue","wed","thu","fri","sat","sun"]` before comparing, or the window never matches
   and **no message is ever delivered** — with no error anywhere.
3. **PyYAML turns ISO dates into `datetime` objects.** Any `card.md` header parsed with
   `yaml.safe_load` gives you `datetime` for `publish_at` and `updated`, and
   `json.dumps()` then raises `TypeError: Object of type datetime is not JSON serializable`.
   Convert to `str`/`isoformat()` at the parse boundary, and pass `default=str` as a backstop.
4. **Cron `--script` only resolves inside `$HERMES_HOME/scripts/`.** That is
   `~/.hermes/profiles/<profile>/scripts/` for a named profile, and it does not exist on a fresh
   profile. Create the directory first; Hermes rejects any path that escapes it.
5. **The gateway hosts the Kanban dispatcher.** No gateway means no task ever starts, and the
   symptom looks like a broken squad. Diagnose it in step 1 of the base installation.
6. **A shared lock is reentrant only by token.** `render_video.py` calls `contact_sheet.py`, and
   the child must not block on the parent. Export `HEAVY_LOCK_TOKEN` when acquiring and compare it
   on re-entry, instead of blindly waiting.
7. **A batch delivery has three distinct gates**: the notify window, the batch being complete,
   and `batch_wait_hours` since the first piece arrived. Test all three explicitly; a test that
   only exercises the happy path proves nothing.

## Level 1

### `heavy_lock.py` (shared)

```markdown
Create {{ROOT}}/scripts/heavy_lock.py if it doesn't exist (the whole ecosystem shares it; if
another squad already created it, use that one). It manages the heavy-work lock
{{ROOT}}/.heavy-lock.
- As a module: `with heavy_lock("render_video", max_wait=1800): ...`
- As a CLI: `python heavy_lock.py run --name <x> --wait 1800 -- <command ...>`
Rules:
- It is taken atomically (exclusive creation of the file, with PID, name, time and a token).
- It is reentrant: when taken, it exports HEAVY_LOCK_TOKEN to the environment; a child process
  that arrives with the same token doesn't wait (so render_video.py can call contact_sheet.py
  without getting blocked).
- If the owner PID no longer exists or the lock is more than 45 minutes old, it is considered
  abandoned and replaced.
- While waiting, it retries every 5 s; if the wait runs out, exit 1 with a clear message.
- It is always released, also on an error or Ctrl+C.
Tests: two processes at once (the second one waits), a child with the token (doesn't wait) and
an abandoned lock.
```

### `hf.py`

```markdown
Create {{M}}/scripts/hf.py: the single entry point to HyperFrames. It uses the version pinned in
{{M}} (npx hyperframes with the version from package.json), takes the lock and passes the
arguments through: `python hf.py <subcommand> [args...]` for tts, transcribe, lint, check,
snapshot, add and render.
- render_mode light (marketing-profile.yaml): adds the low-memory flag and 1 worker.
- It never opens preview or studio (it exits with an error if they are requested).
- Telemetry was already turned off during installation; if it detects it is on, it turns it off.
- It returns HyperFrames' exit code and leaves its output on stderr.
```

### `render_html.py`

```markdown
Create {{M}}/scripts/render_html.py. It renders HTML to PNG or PDF with Playwright using the
system browser: Chrome with channel "chrome", or Chromium with executablePath. If there is
neither, it uses Playwright's own browser and says so.
Input: --html <file> --output <file|folder> --sizes 1080x1350[,1080x1080...]
[--pdf a4|letter] [--scale 1|2] [--web-screenshots] [--slide-selector .slide].
- It waits for the fonts (document.fonts.ready) and images to load before capturing.
- With several sizes, one file per size (<name>-<width>x<height>.png).
- With --slide-selector, one PNG per element (slides/01.png…) and a PDF with all of them
  (carousel for LinkedIn).
- With --web-screenshots (landings and emails): mobile.png at 390 px wide and desktop.png at
  1440 px, full page.
- It verifies with Pillow that each PNG has exactly the requested size; if not, exit 1.
It takes the lock. No network, except what the HTML loads from the brand folder.
```

### `render_video.py`

```markdown
Create {{M}}/scripts/render_video.py.
Input: --project <v<N>/source/> --output <v<N>/video.mp4> --quality draft|standard|high
[--fps 30] [--mode light|normal] (by default, the render_mode from marketing-profile.yaml).
1. It takes the lock (the scripts it calls inherit it).
2. It renders with hf.py render. It never opens preview or studio.
3. It verifies with ffprobe: H.264, dimensions, fps, duration, and an audio track if the
   composition declares one.
4. It creates preview/video-light.mp4 of 45 MB or less (H.264 and AAC, with the bitrate
   calculated from the duration) to send it over messaging.
5. It calls contact_sheet.py.
JSON output with paths, duration, file size and render time. Exit 1 if ffprobe doesn't confirm the
expected dimensions or duration (±0.2 s).
```

### `contact_sheet.py`

```markdown
Create {{M}}/scripts/contact_sheet.py. With FFmpeg it extracts one frame every 2 s (12 at most)
and builds preview/contact-sheet.png as a grid, with the second marked on each frame. It also
extracts preview/cover.png: the frame at --cover <second>, or at second 1. It takes the lock
(reentrant).
```

### `check_piece.py`

```markdown
Create {{M}}/scripts/check_piece.py. Input: --piece brands/<slug>/pieces/<ID> --version N.
It reads card.md (type, channel, format) and v<N>/, and writes v<N>/checks.json:
{"id","version","date","checks":[{"name","ok":true|false,"detail"}],"all_ok":bool}.
Checks by type (02-architecture.md §2):
- exact size and aspect ratio of each image or video (Pillow and ffprobe);
- video duration, fps, codec and file size; subtitles in reel and video;
- maximum file size and text lengths per network, according to {{M}}/scripts/limits.yaml
  (reference values with the date they were reviewed; edited without touching code): caption,
  title, subject, preheader;
- links in copy.md with the correct UTM (utm_source, utm_medium, utm_campaign and utm_content =
  piece ID) and no UTM on internal links within the same site;
- DESIGN.md contrast (npx @google/design.md lint, pinned version) and the generic-design detector
  (npx impeccable detect, pinned version) on HTML pieces;
- hf.py lint and check on video pieces;
- concepts: one sketch per territory; diagnosis: identity sheet and a valid DESIGN.md;
- on every piece: preview/cover.png and sources.md.
Exit 0 if it could run the checks (the result goes in the JSON); exit 1 only if it couldn't read
the piece. It takes the lock only for what opens Chrome.
```

### `stock_photos.py`

```markdown
Create {{M}}/scripts/stock_photos.py. It searches for and downloads commercially licensed photos
or videos from stock libraries with a free API: Pexels (photos and videos), Pixabay and Unsplash,
with the keys the user has put in {{M}}/.env (all optional; it uses whichever are there).
Input: --brand <slug> --piece <ID> --version N --search "<terms>" [--orientation vertical]
[--type photo|video] [--count 3].
- It downloads to pieces/<ID>/v<N>/source/stock/ and adds to sources.md: library, author, URL,
  license and the suggested credit.
- It follows each API's rules: on Unsplash it registers the download at its endpoint; on Pixabay
  it caches for 24 h and doesn't hotlink; on Pexels it leaves the credit when possible.
- Without keys, exit 1 with a message that explains which ones to get (they are free).
```

### `download_assets.py`

```markdown
Create {{M}}/scripts/download_assets.py. It downloads the assets the strategist listed in
brands/<slug>/identity/observed.md (logo, icons, photos, fonts from the brand's own website).
- Only URLs from that list. Only image types (png, jpg, webp, svg) and font types (woff2, woff,
  ttf, otf), checked by header and by content; 20 MB per file at most.
- It never executes or interprets what it downloads. SVGs are stripped of scripts.
- It saves to identity/ with clear names and records origin and date in identity/observed.md.
```

### `render_document.py`

```markdown
Create {{M}}/scripts/render_document.py. It converts v<N>/document.md into v<N>/document.pdf
with the brand identity: it applies the tokens from brands/<slug>/DESIGN.md to
templates/document.html (cover with the brand name and the date, table of contents, readable
tables, footer with page number) and renders with render_html.py --pdf, in A4 or letter
according to the brand's country. It verifies that the PDF opens and that no table runs off the
page; if something fails, exit 1 with the details. No network.
```

### `deliver.py`

```markdown
Create {{M}}/scripts/deliver.py. It runs every 15 min via cron --no-agent in the orchestrator
profile. It is the only exit point toward the user.

0. Its own lock {{M}}/outbox/.deliver.lock: if another run is still active, it exits without
   doing anything (so there are never double sends).
1. It loads user/profile.md (main channel), marketing-profile.yaml (notify_window,
   quiet_until, batch_wait_hours, reminder_minutes_before, proposal_detail, review_on) and
   the settings.yaml of ALL brands, active or not.
2. Each brand's destination:
   - destination topic: the thread_id of the "<emoji> <name>" topic in the orchestrator's
     config.yaml (platforms.telegram.extra.dm_topics), read-only, and it sends with --to
     telegram:<chat_id>:<thread_id>;
   - destination channel: --to discord:#<slug>;
   - destination main, or a topic without a thread_id yet: the main channel, with
     "<emoji> <Brand> ·" at the start of the message.
   It never edits the Hermes configuration or restarts the gateway.
3. Metrics: if there are new files in any brand's data/inbox/ (outside processed/), it runs
   metrics.py for that brand.
4. Proposals. Only within notify_window and if quiet_until has passed. It reads
   outbox/ready/*.json:
   - approval_mode batch and a batch not sent yet: it waits until all the pieces in the batch are
     in outbox/ready/, discarded or blocked, or until batch_wait_hours have passed since the
     first one. Then it sends a batch message: header (emoji, brand, batch), one numbered line
     per piece with title, channel and publish date (and the reviewer's "why" if
     proposal_detail is with_why), the lettered concepts or the extra ideas if there are any,
     and the replies line ("approve all" · "approve 1 and 3" · "change 2: …" · "no to 4");
   - a single piece, a new version (v2, v3…) or a piece that arrives late to a batch already
     sent: its own message, which cites its batch number if it has one ("✏️ v2 of 2");
   - attachments: the covers with [[as_document]]; the video-light.mp4 if review_on is phone,
     or only the cover with the note "video in the Studio" if it is computer;
   - document: it generates the PDF with render_document.py and attaches it. If the lock is busy
     for more than 60 s, it leaves it for the next run;
   - sending: hermes -p orchestrator send --to <destination> "<message> MEDIA:<absolute path> …";
   - if it works: it moves the JSON to outbox/sent/, sets status proposed in the card with a
     line in History, and marks the batch as sent. If it fails, it leaves it for the next run
     and prints the error.
5. Reminders (publishing manual). For each approved card whose publish_at (with its time zone)
   is within reminder_minutes_before and has reminded: false: "🔔 <Brand> · time to post
   <title> on <network> at <time>", with the full copy to post (ready to copy) and the final
   files. It sets reminded: true.
6. Export reminder: on the last day of the month at 18:00, for brands with the reports service
   and no connectors: one line with what to export from each network and where to put it.
7. Blocked tasks: hermes kanban list --status blocked --json. For each task with a brand's
   tenant that hasn't been notified before (ids in outbox/.blocked_notified), one line to its
   destination: "⚠️ <Brand> · <task> needs your answer: <reason>. Reply to me here."
8. It runs studio.py (every run; it takes less than 2 s).
9. Once a day, after 23:00: a commit in {{ROOT}} with the new text, according to the
   .gitignore files.
10. It never publishes or writes to third parties: only to the user.
No output if everything went well (silent cron). --simulate mode: it prints the messages instead
of sending them. Tests with two sample brands, an incomplete batch, a v2, a topic without a
thread_id and the simulated send command.
```

### `studio.py`

```markdown
Create {{M}}/scripts/studio.py: the static board from 02-architecture.md §7.
- It reads {{M}}/brands/*/ (settings.yaml, cards, batches, DESIGN.md, brand files) and writes
  {{M}}/studio/index.html: a single file with the data embedded as JSON (under file:// the
  browser blocks fetch) and the media linked by relative path.
- Home, Brand and Piece views, with anchor navigation (#brand/<slug>, #piece/<ID>), without
  external libraries or CDNs: its own HTML, CSS and JavaScript, readable and accessible, with
  light and dark themes.
- Piece view by type: image, carousel with arrows, <video controls>, landing and email in an
  <iframe>, PDF as a link; the copy to post with a copy button; review (lenses and score);
  history; sources.
- A monthly calendar per brand with the publish dates and the status of each piece.
- Link to the Kanban: the hermes dashboard command and the tenant filter.
- If marketing-profile.yaml has obsidian: true and they don't exist, it creates in
  studio/obsidian/ the Bases views "Proposals.base" (cards with cover, grouped by status),
  "Calendar.base" (table sorted by publish_at) and "By brand.base".
If studio is false in the profile, it does nothing. Under 2 s with 500 pieces, no network, no
server. Test with a sample brand.
```

### `metrics.py`

```markdown
Create {{M}}/scripts/metrics.py [--brand <slug>]. It normalizes the exports in data/inbox/ (CSV
or XLSX) into data/metrics.csv in the long format date,channel,piece_id,metric,value,source.
It recognizes the source by the headers: Meta Business Suite (Instagram and Facebook), TikTok,
LinkedIn, YouTube Studio, Google Analytics 4, Search Console and the usual email providers (Brevo,
Mailchimp, Kit). It takes piece_id from utm_content when it exists; if not, it matches by date
and channel with published.csv. It moves what it processed to data/inbox/processed/. What it
doesn't recognize, it leaves in place and logs in data/inbox/UNRECOGNIZED.md so the strategist
can read it directly. Tests with a made-up export from each source.
```

### `plan_week.py`

```markdown
Create {{M}}/scripts/plan_week.py. It runs every hour via cron --no-agent in the
marketing-strategist profile. If {{M}}/PAUSE exists, it exits without printing anything.
For each brands/<slug>/ with active: true, no PAUSE and planning other than "none":
- it calculates this week's planning time (planning from settings.yaml, or otherwise the one
  from marketing-profile.yaml, in the user's time zone);
- if that time has passed, it creates the task for the following week (if it already exists,
  the idempotency-key prevents the duplicate):
    hermes kanban create "CALENDAR · <slug> · week <YYYY-WNN>" --assignee marketing-strategist
      --tenant <slug> --workspace dir:{{M}}/brands/<slug> --idempotency-key <slug>-cal-<YYYY-WNN>
      --max-runtime 30m --body "<body from 02-architecture.md §8: ID <slug>-W<YYYY>-<WW>, Mode
      CALENDAR, week to plan, quota, input and output>"
Silent if all goes well; if a command fails, it prints the error and exits with 1 (the cron
reports it).
```

### `monthly_report.py`

```markdown
Create {{M}}/scripts/monthly_report.py. It runs every day at 08:00 via cron --no-agent in the
marketing-strategist profile. If {{M}}/PAUSE exists, it exits. For each active brand, without a
PAUSE and with the reports service: it runs metrics.py and creates REPORT · <slug> · <YYYY-MM>
for the previous month for the strategist (tenant, workspace, idempotency-key
<slug>-rep-<YYYY-MM>). Since it runs daily, if the computer was off on the 1st, the report is
created when it is back on. Silent if all goes well.
```

## Level 2

### `publish.py` (social networks)

```markdown
Create {{M}}/scripts/publish.py, with its own cron --no-agent every 15 min in the orchestrator
profile. It processes outbox/schedule/*.json, which the orchestrator writes only after an
explicit confirmation from the user:
{"id","version","network","date","confirmed_by","confirmed_at"}.
Guards: the card must be in status approved and at the same version; if confirmed_by is missing,
it does nothing and notifies the user. Provider according to marketing-profile.yaml:
- Postiz Cloud: it uploads the files and creates the scheduled post with its CLI or API;
- Buffer: it creates the scheduled post; since Buffer requires a public URL for the files, the
  user chooses where to host them when installing Level 2.
It saves the response in v<N>/schedule.json, sets status scheduled and notifies "✅ Scheduled:
<title> · <network> · <date>". It never publishes instantly or without confirmation. Keys in
{{M}}/.env.
```

### `email_draft.py`

```markdown
Create {{M}}/scripts/email_draft.py. For an approved email piece, it creates the campaign as a
DRAFT in the brand's provider: in Brevo, POST /emailCampaigns, which creates a draft by
default; in Kit, a broadcast with no send date. It uses the HTML and the text from v<N>/, the
subject and the preheader. It sends the user the link to review it in their provider. It never
sends: sending is done by the user from their provider, or by this script with --send and an
explicit confirmation written in outbox/schedule/.
```

### `deploy_landing.py`

```markdown
Create {{M}}/scripts/deploy_landing.py. Two steps, each with its own confirmation:
1. Preview: it uploads v<N>/landing/ to a preview URL from the chosen provider (Cloudflare
   Pages, or Workers with static assets) and sends it to the user.
2. Production: with explicit confirmation, it publishes on the brand's subdomain (for example,
   promo.brand.com, with a CNAME that the user sets up) and verifies that it returns 200.
It records in v<N>/deploy.json the URL, the date and how to roll back. It never touches the
brand's main website; for WordPress, Webflow or Shopify, the package in v<N>/cms/ is delivered.
```

### Data connectors (read-only)

```markdown
In marketing-strategist's config.yaml, add the MCP servers the user connects, with
trust: untrusted and tools.include limited to read tools:
- Google Analytics 4: Google's official server (analytics-mcp), over stdio and only while it is
  in use.
- Google Ads: the official server (google-ads-mcp), read-only.
- Search Console: the community server mcp-gsc, with writing disabled (the default).
- Meta Ads and TikTok Ads: only if they can be limited to reports; if not, CSV exports are still
  used.
The user does the OAuth authorization. Test each connector with a query for the last 7
days.
```

### Studio with buttons (Hermes plugin)

```markdown
Create the plugin ~/.hermes/plugins/studio-marketing/ with the hermes-desktop-plugins skill and
the Extending the Dashboard documentation:
- dashboard/manifest.json: name studio-marketing, "Studio" tab and "api": "plugin_api.py".
- dashboard/plugin_api.py (FastAPI, runs inside the gateway): GET /brands, GET /brand/{slug},
  GET /piece/{id}, GET /file?path=… (only paths inside {{M}}, no "..") and
  POST /action {id, action: approve|changes|discard, text}. Approve and discard do the same as
  the orchestrator (card and preferences.md). For changes, it creates the creative's CHANGE task
  with the literal request, without classifying it: if the change is only visual, the creative
  carries the copy and the concept over to the new version and hands it to the producer.
- dashboard/dist/index.js: the web dashboard tab, in uncompiled JavaScript.
- desktop/plugin.js: a "Studio" page in the Desktop sidebar, which uses ctx.rest; no JSX, only
  the imports the SDK allows and the theme colors.
It is enabled in plugins.enabled in config.yaml and in Capabilities → Plugins. It is the same
view as the static Studio, plus the buttons.
```

### AI video

```markdown
Enable the video_gen toolset in marketing-producer with the provider and model the user
chooses (in September 2026, Veo 3.1 Fast or Kling 3.0) and a monthly cap in
marketing-profile.yaml. The producer uses it for B-roll shots, preferably animating an image
that is already approved, always inside a HyperFrames composition, and logs the cost in
ai-spend.csv.
```
