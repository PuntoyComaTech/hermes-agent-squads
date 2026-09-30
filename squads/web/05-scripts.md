# Scripts: web development agency

> Script specifications. The builder writes them in step 9 of the installation, on the user's computer; they also work as prompts for any coding AI.
> Level 1: `deliver.py` and `check_site.py`, plus the shared `heavy_lock.py`. Deploy commands are not scripts: `web-deployer` runs them following `deploy-cloudflare` (`02-architecture.md` §5).

## Common preamble

```markdown
Project: {{W}} = {{ROOT}}/projects/web. Python 3.11+ (venv in {{W}}/.venv), same script on Mac,
Windows and Linux; no .sh or .ps1. Deterministic code, no LLM. Each script is an argparse CLI:
--json when requested, logs to stderr, exit 0 on success, 1 on a data error, 2 on a network or
external tool error. Idempotent. Tests with pytest in {{W}}/tests/; a short README in
{{W}}/scripts/. pathlib paths; absolute or relative to {{W}}. Never read or write outside {{W}},
except: reading {{ROOT}}/user/; {{ROOT}}/scripts/heavy_lock.py and {{ROOT}}/.heavy-lock; reading
the orchestrator's config when stated; deliver.py's daily commit in {{ROOT}}. No secrets: these
scripts never need the Cloudflare or GitHub tokens. Everything that opens Chrome or runs
Lighthouse goes through the lock. Data contracts: 02-architecture.md (attached).
```

Traps already hit by other squads apply here too (`squads/marketing/05-scripts.md`, "Traps"): weekday keys normalized to English, PyYAML dates converted to strings before `json.dumps`, cron scripts only inside `$HERMES_HOME/scripts/`, the reentrant lock token, the gateway's `HERMES_BIN`, Discord's User-Agent and `DISCORD_HOME_CHANNEL` as a bare ID.

## Level 1

### `heavy_lock.py` (shared)

Specified in `squads/marketing/05-scripts.md`. Create it in `{{ROOT}}/scripts/` only if it does not exist. This squad uses the CLI form for installs and builds (`python {{ROOT}}/scripts/heavy_lock.py run --name pnpm-build --wait 1800 -- pnpm build`) and the module form inside `check_site.py`.

### `check_site.py`

```markdown
Create {{W}}/scripts/check_site.py. Run by web-reviewer (full) and web-deployer (--smoke).
Input: --site <slug> --id <ID> --round R (--url <https url> | --dir <static build folder>)
[--smoke] [--pages <path,...>]. Pages default to the Pages table of sites/<slug>/spec.md, per
language. --dir serves the folder on 127.0.0.1 on a free port for the duration of the run and
stops it before exiting (tests and local fixtures only; nothing is left running).

Output folder: sites/<slug>/reviews/<ID>-r<R>/ (--smoke: smoke.json in the same folder).
checks.json: {"id","round","url","date","thresholds","checks":[{"name","page","ok","detail",
"severity":"critical|warn"}],"scores":{...},"all_ok":bool}.

Checks, full mode:
- HTTP: every page returns 200; a missing path returns 404; redirects at most 1 hop.
- Links: crawl same-origin links from the pages (max 200 URLs); every internal link and asset
  200 (critical). External links: HEAD, then GET on 405; failures are warn only.
- Meta: title, description, lang, canonical, Open Graph title and image, viewport; sitemap.xml
  and robots.txt present when the spec has more than one page; hreflang per language.
- Lighthouse (npx lighthouse, pinned, mobile preset, --output json, system Chrome through
  CHROME_PATH): performance, accessibility, best-practices, seo per page against thresholds in
  web-profile.yaml (lighthouse_mobile_ssr for dynamic_seo and saas). Under threshold: critical.
- Accessibility: Playwright (system Chrome) loads each page, injects axe-core (pinned, from
  {{W}}/node_modules), runs WCAG 2.2 AA rules; counts by impact against axe_max.
- Screenshots: each page at 390x844 (mobile-<page>.png) and 1440x900 (desktop-<page>.png),
  full page. Console errors per page (warn; uncaught exceptions critical).
- Security: response headers (Content-Security-Policy or at least X-Content-Type-Options,
  Referrer-Policy, frame protection, HSTS on https); mixed content; secret patterns in every
  loaded JS and HTML (API key shapes: sk_live_, AKIA, ghp_, github_pat_, xox, private key
  headers, JWT-like strings next to "secret"), critical. With --repo sites/<slug>/repo also scan
  the working tree and git history of the branch for the same patterns and for committed .env
  or .dev.vars files; and run pnpm audit --json --prod (high or critical: warn, listed).
- Forms: every form has an action or a handler and labeled inputs (static check).

Smoke mode (deployer, after each deploy): HTTP 200 on every page, the home page's title matches
the spec site name, no uncaught console exception, no secret pattern. No Lighthouse or axe.
Under 60 s.

Lock: one heavy_lock("check_site", max_wait=1800) around everything that opens Chrome or
Lighthouse; the HTTP-only checks run outside it. With 8 GB RAM, one page at a time.
Exit 0 if the checks ran (results in the JSON, even when some fail); 1 if the site cannot be
reached or the spec cannot be read; 2 if Chrome or Lighthouse cannot start.
Tests: a fixture static site with one broken link, one image without alt, one leaked fake key,
and a clean page; smoke and full modes; the lock waits when held.
```

### `deliver.py`

```markdown
Create {{W}}/scripts/deliver.py. Runs every 15 min via cron --no-agent in the orchestrator
profile. The only exit point toward the user for this squad.

0. Own lock {{W}}/outbox/.deliver.lock: if another run is active, exit silently.
1. Load user/profile.md (main channel), web-profile.yaml (notify_window, quiet_until,
   technical_level) and the settings.yaml of every site.
2. Destination per site, read-only from the orchestrator's config:
   - destination topic: thread_id of the "<emoji> <name>" topic in
     platforms.telegram.extra.dm_topics; send with --to telegram:<chat_id>:<thread_id>;
   - destination channel: --to discord:#<slug>;
   - main, or a topic without thread_id yet: the main channel, prefixed "<emoji> <Name> ·".
   Never edit Hermes config or restart the gateway.
3. Outbox, only inside notify_window and after quiet_until. For each outbox/ready/*.json, by
   kind:
   - spec: "<emoji> <Name> · Your site plan" + the 3-5 summary lines + monthly cost line + open
     questions numbered + "Reply "ok" to start, or tell me what to change". Attach spec.md.
   - preview: title, URL, summary lines, the mobile screenshot of the home page
     (as a photo), the reply line. With approver client, add a
     forwardable paragraph.
   - production: "✅ <Name> is live: <url>" + what changed + "Say "rollback" if something is
     wrong."
   - domain: the registrar steps as a numbered list, then the confirmation question as sent by
     the deployer; or "✅ <domain> works with HTTPS".
   - rollback: "↩️ <Name> is back to the version from <date>: <url>".
   With technical_level developer, append PR and commit links from the deploy record.
   Send: hermes -p orchestrator send --to <destination> "<message> MEDIA:<absolute path> …".
   On success: move the JSON to outbox/sent/; for preview, set status delivered in the milestone
   note with a History line. On failure: leave it, print the error.
4. Blocked tasks: hermes kanban list --status blocked --json. For each task with a site tenant
   not yet notified (ids in outbox/.blocked_notified): "⚠️ <Name> · <title> needs your answer:
   <reason>. Reply to me here." A card blocked with kind dependency (a consultation) waits in
   todo, not blocked, so it is never reported.
5. Once a day after 23:00: a commit in {{ROOT}} with the squad's text (the .gitignore excludes
   sites/*/repo/).
6. Never publishes, deploys or writes to anyone but the user.
No output when all went well. --simulate prints the messages instead of sending. Tests: two
sites (one with topic, one main), each kind of outbox file, a blocked task notified once, a message held by quiet_until, the notify window with weekday
keys in two spellings.
```

## Level 2

Specified when the user moves up (`06-testing-and-operations.md` §5):

- `deps_update.py` (`--no-agent` cron, weekly, profile `web-developer`): for each active site without PAUSE, if `pnpm outdated --json` in `repo/` shows updates, creates a developer BUILD kind `change` with the list (idempotency key `<slug>-deps-<YYYY-WNN>`). It never updates packages itself.
- `perf_monitor.py` (`--no-agent` cron, daily, profile `orchestrator`): runs `check_site.py --smoke` plus a Lighthouse performance pass on each live URL; appends to `sites/<slug>/perf.csv` (`date,page,performance,lcp_ms,cls,status`); writes an outbox `alert` file only when a page drops below threshold twice in a row or returns non-200.
