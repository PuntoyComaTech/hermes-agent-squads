# Changelog

All notable changes to hermes-agent-squads. The builder's update watcher reads this file
(`scripts/watch_upstream.py`); keep entries short and dated.

## 2.14.3 - 2026-10-24

### Fixed

- Root cause of the home-folder search: a bot's skills told it to run a script of a skill another bot holds, so the
  script was not in its profile and the bot went looking for it. `tests/test_skill_ownership.py` now walks every bot of
  every squad and fails when a skill it holds runs a script (by `$HERMES_HOME/skills/...` path or by name after
  "run") from a skill it does not hold; it caught two more such orders in jobs.
- jobs 4.5.3: the manager computes the consent kit hash with `jobs-contract/scripts/kit_hash.py` (one definition in
  `jobs_common.kit_sha256`, which the submit gate also uses) instead of the applier's `check_submission.py`. Adding a
  job board moves to the scout, which holds `portals.py`: the manager asks the five answers and files a
  `Mode: PORTAL` card.
- Every bot's base: a tool, access or file its skills name that is missing is reported to the user for the builder,
  never hunted for.

## 2.14.2 - 2026-10-24

### Fixed

- Bots no longer search the home folder or `/`: on macOS that walk raised a privacy prompt for each private folder
  (Desktop, Downloads, Photos, other apps' data), attributed to `osascript` because the gateway runs under it. The base
  SOUL now says so next to the project rule.
- jobs 4.5.2: the manager presenting the LinkedIn copy reads the writer's files and no longer looks for the writer's
  check scripts, which live in the writer's profile; that hunt was what reached the home folder.

## 2.14.1 - 2026-10-24

### Fixed

- jobs 4.5.1: the review no longer loops. `aggregate_review.py --apply` (the reviewer always passes it) writes every
  wording, spelling and positioning fix itself (`applied`; a re-run finds it in place) and lists judgement fixes under
  `polish`, which the reviewer carries out and re-renders (it now holds rendering-cv). Only hard items decide the
  verdict: truth, dropped company claims, render defects, keyword coverage, market and language rules, unanswerable
  stretches, confidential terms. A real application took 7 rounds for 3 spellings and 1 phrasing; it now closes in one.
- The reviewer and the manager asked the user for facts the user had already given. Grounding now reads every file the
  user wrote (`achievements.yaml`, `profile.md`, `application-data.yaml` saved answers, the user's own CV in
  `documents/cv/`); the manager searches them and its memory before asking, and copies a fact it finds into
  `achievements.yaml`. A detail no document claims (which vector store sat behind "vector retrieval") is an interview
  question, never a block or a question to the user.

## 2.14.0 - 2026-10-24

### Fixed

- jobs 4.5.0: a LinkedIn optimisation covers the whole profile in every profile language. A real run drafted roles
  under the titles in `achievements.yaml`, so three roles LinkedIn names differently were never paired and kept no
  description; education and the skills under each role had no copy; and both languages were verified against one
  capture of a page that mixes them, so `verify` said 4 of 12 and the run called it noise.
  - `check_profile_copy.py --current` refuses a copy that leaves a role or school of the profile uncovered
    (`role_not_covered`, `education_not_covered`), names one the profile does not hold (`unknown_role`,
    `unknown_education`) or is written in a language the profile does not have (`wrong_language`). Education blocks
    (400 characters), `role_skills` (5 per role) and `top_skills` (5) are checked like the rest.
  - `parse_profile.py` reads the profile's own "Profile language" card (`profile_languages`), moves LinkedIn's
    "Top skills" line out of the About text (`top_skills`), and no longer takes a role's first bullet for its location.
  - `profile_diff.py verify` takes one capture per language and checks each approved row against its own language;
    skills compare as a set, ignoring LinkedIn's order and casing. `diff` offers education, role skills and top skills.
  - The capture reference documents the language card, the per-language edit forms and the education form.

## 2.13.2 - 2026-10-24

### Added

- jobs 4.4.2: related tools play for the candidate. `jobs-contract/scripts/skill_families.json` groups tools a holder
  of one picks up in days (SQL dialects and managed SQL; GitHub, GitLab and their CLIs; Jest and Vitest; Express,
  Koa and Fastify; LangChain and LlamaIndex; ...). A posting tool whose family the candidate holds is covered in the
  analysis (no gap), may sit next to the held tool in the CV ("SQL (PostgreSQL, Azure SQL)": `render_cv.py` reports
  `related_tool`, never `unsupported_tool`), is grounded for the review, and a form's "have you used <tool>?" is
  answered yes naming the held tool, never "not familiar". Another paradigm (React vs Angular) is never one family.
- `jobs-notices` runs hourly; the hour's sends each arrive in their own message with their own CV (`hermes send` for
  all but the newest). LinkedIn Easy Apply keeps `easy_apply_gap_minutes` (default 1) between two submissions: a
  closer gate says `easy_apply_gap` and the seconds to wait, never a kit.
- The CV a recruiter receives is `CV_<Name>_<Surname>.pdf`: `render_cv.py` writes it as a byte copy of `cv_ats.pdf`
  (which the review, the gates and the kit hash keep reading), ASCII, given name and first surname, or
  `contact.yaml` `short_name`. A re-render or a failed render removes earlier copies; the notice attaches it only
  while it matches `cv_ats.pdf` byte for byte.

## 2.13.1 - 2026-10-24

### Added

- jobs 4.4.1: `profile.md` `keep_off_public_profile` for names a CV, letter or form answer sent to one employer may
  carry but a public profile may not (clients of the current employer, team size). Only the LinkedIn copy checker
  refuses them (`not_public`); `confidential_terms` stays the never-anywhere list. The manager files a name the user
  keeps off LinkedIn into the scoped list without asking.

### Fixed

- web 3.7.1: the versions gate (`tools/quality/fresh.mjs`) read only pnpm 9 lockfiles. pnpm 12 quotes scoped names
  with double quotes, so every scoped package of a fresh base was reported "the lockfile nothing" and `pnpm quality`
  failed on a site nobody had touched.

## 2.13.0 - 2026-10-24

### Added

- jobs 4.4.0: cron `jobs-notices` (`application_notices.py`, every 5 minutes, `notify: true`) posts each sent
  application once, one per message, read at a glance on a phone: role and company, score, work mode, posted and sent
  dates, a one-line `brief` of the job (new `analysis.json` key, written by analyzing-jobs in the user's language) and
  the apply link, with the CV that was sent attached through a `MEDIA:` line. Its first run marks older applications as
  posted, so an install never replays history.
- Manatal career pages (`careers-page.com/<board>`, where recruitment agencies publish) are a known ATS for
  `link_check.py`; their postings were `unverified` and could never be applied to automatically.

### Changed

- Under `auto_apply: auto` the owner's channel gets only sent applications and questions the squad cannot answer: an
  approved match files the applier card with no digest, a search ends with `kanban_complete`, WATCH, NOT_APPROVED,
  NOT_POSSIBLE and non-eligibility FLAGs stay in the project files (`show my pipeline`, then `force <ID>`), an
  eligibility FLAG is one line ("Do you qualify?"), and NEEDS_DATA asks every question of a form in one message, then
  saves the answers. A notice needs `submission.json` `SUBMITTED`: an `applied` the owner reported is never announced
  as a send. `digest_fields.py` prints the brief, posted date and work mode. A digest under `try`/`ask` attaches its CV (`MEDIA:`) instead of
  printing a local path, and carries the brief.
- `board_watch.py` prints a card's block reason as the message itself (no board header, no indent); a worker's
  question names the worker and its card on one line, and a stale card keeps the first line of its reason. A run
  prints at most one card that carries a file (`MEDIA:`), so each CV arrives with its own opening.
- A bot with `notify: true` crons gets `cron.wrap_response: false`: a notice no longer arrives wrapped in "Cronjob
  Response" and "stop reminder" lines. The channel prompt `squadctl connect` writes says files go as `MEDIA:` lines.

### Fixed

- `board_watch.py` skipped every question of a chain filed from a Desktop or CLI session: those chains hand a `tui`
  notify subscription to each card, which the watch read as "a chat already got it". The owner, reading the squad from
  a phone channel, received nothing until they asked. Only a messaging-platform subscription counts now.

## 2.12.1 - 2026-10-24

### Added

- jobs 4.3.1: lessons a live jobs manager learned, merged back so updates keep them. `digest_fields.py` prints every
  opening's verdict, score, gates, apply link, kit and review in one pass (`references/digest-sources.md` says which
  file holds each field); `references/manager-pitfalls.md` covers delivery checks, corrections while applications are
  in flight, standing rules, `CONFIDENTIAL:` notes and easy-to-miss profile keys; promotions keep one experience entry
  per title (`jobs-contract/references/protected-facts.md`).

## 2.12.0 - 2026-10-24

### Added

- jobs 4.3.0: `profile.md` `confidential_terms` (clients, brands and internal projects of the current employer, a
  second job). The renderer (`confidential_term`), the LinkedIn copy checker, the review aggregator (a `privacy`
  correction no lens verdict can pass) and the submit gate all refuse an outward text that names one.
- Readable length as defects, not hints: a CV summary over 50 words, more than 5 bullets in the latest role or 3 in any
  other, a letter body over 250 words (`too_long`); a LinkedIn About over 1,500 characters or an experience description
  over 600.

### Changed

- The jobs manager asks only for a missing fact, an `apply`, a public write, `RESET`, a payment or a credential. A
  correction the user gives is the approval: it is written to the profile and every open document in the same turn
  and reported after (`leading-job-search/references/autonomy.md`). Stated facts no longer wait for a second "ok";
  stretch bullets are softened by the writer instead of stopping the card; LinkedIn is approved once, on the final copy.
- LinkedIn About and experience guidance: who you are in the first lines, no career history, two to four one-line
  bullets per role, sectors instead of client names.

### Removed

- The senior-stage warning asking for a number in the CV summary: it pushed team size into a public document.

## 2.11.0 - 2026-10-23

### Added

- `squadctl connect <bot> <platform>`: binds a manager to a Discord, Telegram, Slack, Mattermost or Matrix channel
  (home channel, mention-free replies, a channel prompt) and sends a test message through `hermes send`. On Discord it
  finds the channel by name or creates it with `--create`; before the invite is accepted it prints the invite link.
- Cron field `notify: true`: the job's output goes to the bot's connected channel, or to Bot Chat while none is
  connected or its token is gone. jobs 4.2.0 (`jobs-search`, `jobs-followups`, `jobs-watch`), web 3.7.0
  (`web-watch`) and marketing 3.4.0 (`marketing-plan-week`, `marketing-report`, `marketing-watch`) mark their
  owner-facing jobs.
- `doctor` checks each connected channel: token present, every notify job delivering there.

### Fixed

- `apply` and `upgrade` reset every squad cron to the manager's Bot Chat, so a job moved to a chat channel went back
  silently on the next update and the owner stopped receiving digests there.

## 2.10.2 - 2026-10-23

### Changed

- `hermes-platform` plugins reference: `plugins list` wraps long names, so check the Status column or the config
  list before reporting a plugin off.

## 2.10.1 - 2026-10-23

### Changed

- Builder skills carry the generic lessons learned on installed machines: model files the advisor's JSON shape only
  (`assigning-models`); real-run stage hand-offs and contract tests after lint (`authoring-skills`); composed SOULs
  checked by the update-path test (`changing-bots`); fetch, back up and renumber before a release, with history
  scrubbing in its own reference (`contributing-upstream`); machine-shared crons take a lock and a stamp
  (`designing-squads`); connector probes, pending sign-ins and client allowlists (`finding-capabilities`); apply traps
  in their own reference, per-bot content checks and one machine-wide sweep (`installing-squads`); exact project paths
  only (`managing-projects`).

## 2.10.0 - 2026-10-23

### Changed

- Every shipped bot that browses uses the machine's one shared signed-in browser: web 3.6.0 (`web-frontend`,
  `web-qa`, `web-frontend-pro`) and marketing 3.3.0 (`marketing-research`, `marketing-producer`) join jobs.
  GitHub, Cloudflare and Vercel stay on their CLIs.
- `squadctl` no longer mirrors the owner's `browser.use_real_profile` onto any bot, managers included; apply turns
  off a copy an older version left and clears its pin. The owner's own chats keep the setting.
- The browser sweep ships on every squad's manager but runs once per machine: a lock and a 150-minute stamp make the
  other fires exit untouched.
- Base rule for every bot: signed-in browsing only through the shared browser.

## 2.9.2 - 2026-10-23

### Fixed

- `squadctl doctor` finds bun in `~/.bun/bin`, where its official installer puts it and where the portal wrapper runs
  it from; it warned "app bun not found" on machines where the job search worked.

## 2.9.1 - 2026-10-23

### Fixed

- `shared_browser.py install` reloads a changed service job: `launchctl bootout` returns while launchd still lists
  the job, so the reload was skipped and an update left the machine with no shared browser.

### Changed

- `designing-squads`: judging bots and their children take the reasoning lane; an account that must not meet browsing
  gets its own worker; read squadctl and the schema before proposing a topology; a publish needs the version bump, the
  CHANGELOG entry and an independent review. Irreversible steps may run on a recorded standing consent with caps.
- `installing-squads`: after an apply, check that the shared browser is listening.

## 2.9.0 - 2026-10-22

### Added

- Shared signed-in browser. A bot manifest with `shared_browser: true` (toolset `browser`) drives one headless
  Chromium per machine, signed in once by the owner, instead of a browser of its own. `squadctl` points the bot's
  `browser.cdp_url` at it, keeps `browser.use_real_profile` off, installs the `shared-browser-tabs` plugin (one tab per
  task, `new_tab` navigates in place, the tab and its harness daemon are closed when the turn ends) and adds a
  no-agent `browser-sweep` cron to the manager every 3 hours for tabs a crashed run left. `scripts/shared_browser.py`
  runs the browser as a launchd service and opens the sign-in window (`login <url>`: a plain window, because Google
  refuses sign-in where a debugging port is open). The builder profile and unmarked bots never use it.
- Jobs squad 4.1.0:
  - Portals `computrabajo`, `elempleo` and `talent` (zero dependencies, schema.org JSON-LD over HTTP).
  - `browsing-linkedin` (scout): LinkedIn hiring-post search in the shared browser, read-only, Boolean terms and a
    recency window; job listings stay with the portal tool.
  - `recommending-platforms` (scout): job platforms per country from independent evidence.
  - `optimizing-profiles` (writer): reads the user's own LinkedIn profile, drafts copy from verified achievements, and
    after the user approves each field edits it and re-reads to verify (`own_profile.py`, `profile_diff.py`,
    `check_profile_copy.py`).
  - `auto_apply: auto`: a standing consent recorded once, with `daily_apply_cap` and `daily_easy_apply_cap`;
    `check_submission.py` enforces an approved review, a PURSUE analysis with no gate FAIL, `apply_threshold` and the
    caps, under a project lock with a reservation per open gate (`apply_state.py`), so parallel applier runs never pass
    the cap and a real submit is never left unrecorded; the applier gains
    LinkedIn Easy Apply (`easy-apply.md`).
  - New optional bot `jobs-inbox` (Gmail connector, no web, no browser): job mail and the verification codes other
    bots ask for (`Mode: CODE`, `extract_code.py`). Gmail leaves `jobs-writer`.
- Profile key `linkedin_browse` (default true, asked once) and a `profile` chain.
- Reference `hermes-platform/references/browser.md`; decisions D-042 to D-044 and C-13.

### Changed

- `jobs-scout`, `jobs-writer` and `jobs-applier` run on the shared browser. Its headless service cannot resolve the
  Google mail, files and account hosts (`--host-resolver-rules`); the bots' blocklist is a literal-URL filter on top. `jobs-scout` and `jobs-applier` no longer block `linkedin.com`.
- `squadctl` no longer mirrors the owner's `browser.use_real_profile` to the builder itself, nor to a `shared_browser`
  bot: a builder chat browsing there opened the owner's sessions in a profile copy.
- The bots' base rule allows the shared browser (`browser.cdp_url`) besides the real-profile copy.
- `followup_gate.py` files its inbox card for `jobs-inbox` (`--inbox`; `--writer` still works).
- `squadctl`: a bot manifest with an empty `website_blocklist: []` clears a blocklist an earlier version installed.

## 2.8.0 - 2026-10-22

### Changed

- Every install goes through its official installer, never through files or versions written by hand. Web squad
  3.5.0: a new site starts from its framework's own create CLI (`create-astro`, `create-next-app`, the TanStack CLI);
  each package the template named is re-added with `pnpm add <name>@<its major>`, the squad's tools with
  `pnpm add -D <name>` and no version, Tailwind through `astro add`, Biome's config from the CLI or `biome init`,
  extending the squad's rules. `stacks.json` holds no package version except a stated constraint.
- One command lays a site's base: `site_base.py --site <folder>` reads stack, slug, provider and repo folder from
  `site.yaml`.
- Release-age rule from 14 to 3 days: known npm attacks were pulled within hours to two days. pnpm itself runs at its
  newest release 3 days old (12.14.0 today; the machines had 10.34.6), pinned per site with `npm pkg set
  packageManager`; build approvals move to `allowBuilds` (pnpm 12 fails on a setting it does not know).
- Security fixes never wait: `security_fix.py` installs the lowest release that clears every advisory (a direct
  dependency through `pnpm add`, a transitive one through an override). A fix younger than 3 days goes under
  `minimumReleaseAgeExclude` as exact releases, its own family only (next@16.4.1 with @next/*@16.4.1), is logged in
  the site's `decisions.md` and removed once old enough. The base runs it before the first gate; the deps gate
  names it when it fails.
- New gate step `quality:fresh` (12 steps): a dependency pnpm never resolved, an exact pin, or a major behind the
  newest one old enough to install fails. Exceptions live in `tools/quality/fresh-allow.json`, each with its reason:
  a major the create CLI chose, a stated constraint, `@types/node` following the runtime, or a trust hold.
- A release pnpm's trustPolicy flags as a possible takeover is never installed: the base holds the package at its
  last trusted release and says so (lefthook 2.2.2 was published by hand without the provenance of 2.2.1).
- The scanners install and update through Homebrew; nuclei's templates through nuclei, else a shallow clone of the
  official repository. The squad no longer downloads, pins or checksums a binary. `web` and `web-qa` require
  Homebrew.
- When the gate fails on the template's own code, `site_base.py` says so under `next`; the code is fixed, never a
  rule, and the same command finishes the base and its first commit.
- Every bot's base rules: libraries and new projects come from their official installer.

### Fixed

- type-coverage ignore globs reached `sh` unquoted and were expanded before the tool saw them; the gate's own
  scripts and reports were type-checked as project code under a template's `**/*` include.

## 2.7.0 - 2026-10-22

### Added

- Web squad 3.3.0: every site starts on a strict base the manager installs before the first card
  (`site_base.py --install`): strict TypeScript, Biome (no `any`, complexity, size and parameter caps), the SonarJS
  rules run locally through ESLint, dependency-cruiser architecture rules, jscpd, knip and Vitest coverage, as one
  `pnpm quality` gate that lefthook runs on every commit and push. All three stacks start green.
- `web_access.py`: reuses a GitHub or Cloudflare login the user already has; otherwise installs the CLI and starts
  its login, returning the approval page (code included) for the manager to open as a tab beside the chat.
- `live_view.py`: the manager keeps the site's dev server running and shows it in the tab beside the chat from the
  first minute; the tab reloads as files are saved.
- `save_progress.py`: builders commit each finished piece on `web/<ID>` (never `main`) and log it for status.

### Security and code quality for web sites

- The strict base grows from 7 to 11 steps: type coverage at 100 % (an `any` that arrives through a library is caught),
  gitleaks over the files and the whole history, a license check (GPL, AGPL, SSPL, non-commercial or unknown licenses
  cannot ship), and a vulnerability and malicious-package check with osv-scanner and `pnpm audit`.
  `eslint-plugin-security` and `no-unsanitized` join the Sonar rules; dependency-cruiser also keeps `src/domain` free
  of UI and framework imports. Response headers (CSP, HSTS, framing, referrer, permissions, cross-origin) ship from
  the first commit.
- Supply chain in every site's `pnpm-workspace.yaml`: no release younger than 14 days, no trust downgrade, no
  unapproved install script, a forced patched `sharp` (the previous base carried a high advisory through wrangler).
- `security_tools.py` installs osv-scanner, gitleaks, nuclei and Semgrep at pinned versions in one user folder: single
  binaries checked against the release's SHA-256 file, Semgrep through uv.
- Web QA reviews with six lenses: the new code-review lens (architecture, SOLID, scalability, security by trace, test
  quality) reads `engineering-rules.md`, and `code_audit.py` gives it evidence: each gate step, Semg

... [OUTPUT TRUNCATED - 1,078 chars omitted out of 51,006 total] ...

ver granted when the user has not, and never re-granted
  to a bot the user switched off. Every bot's base rules forbid the improvised routes: starting a browser, a
  debugging port, a copied profile, reading cookie or keychain files, asking for cookies.
- Every bot gets every provider the user connected, on every `squadctl apply` and every daily update: each API key
  found in the root or builder env file (copied into the bot's env file, mode 600, never printed) and each
  user-installed provider plugin, not only the providers of the bot's own lanes. Before, the copy waited for an
  `apply --yes` the builder's skills never passed, the daily update only printed a reminder, and a bot switched to
  another of the user's providers had no key for it. A copy follows a rotated source key; a key set by hand in a
  bot is kept. `local/providers-exclude.txt` keeps a provider out of the bots. `--yes` is accepted and no longer
  needed.
- `cf auth whoami` and `wrangler whoami` exit 0 when logged out; the access check now reads their answer.
- The deployer no longer asks the user to install or log in to a CLI: a missing login goes to the manager.
- Bots show a web page or dev server in the side tab, never inline in the chat.
- Independent review fixes: the live server is reused while it shows a compile error and is stopped when it never
  comes up; a progress save commits only the builder's own paths; only the manager switches the shared working tree's
  branch; CLIs are found in Homebrew, nvm and the user's bin on a bare PATH; a waiting login is reused, never doubled;
  Vercel logins go through the same tab flow; `cf` and `vercel` are pinned; a repo's own `quality` script and a
  commented `tsconfig.json` no longer escape the strict gate; a new base ships a seed test and fails with no tests.

## 2.6.2 - 2026-10-21

### Fixed

- `squadctl apply --yes` prepared only the provider of a bot's main model. Its `delegate_task` children, auxiliary
  slots, chain stages and fallback chain can run on other providers: a writer on a subscription with research
  children on an API provider failed every delegation with "no key". Apply now copies the key and the provider
  plugin for every provider the bot runs on; doctor checks them all, and `upgrade` names any key still waiting for
  `apply --yes`.

### Changed

- Bot SOUL base: preview tabs belong to the chat that opens them (one per session, project and bot), are opened
  again in the chat where the user wants them and are never pinned; outside the Desktop app the bot sends the URL.
  The jobs manager opens the pipeline dashboard as a tab.

## 2.6.1 - 2026-10-21

### Fixed

- `squadctl apply --yes` skipped the provider-key copy when `hermes auth list` showed the root key as an `env:` row:
  that row is the CLI's own environment, not the bot's store, so the bot started on its fallback model. Only stored
  credentials now count; the root key is copied into the bot (mode 600).

## 2.6.0 - 2026-10-21

Jobs squad 4.0: a job search built around one person.

### Added

- Personalised onboarding (`profiling-candidates`): reads `documents/`, a pasted CV or an interview; career stage,
  optional age, CEFR language levels, market CV conventions, eligibility per country, deal-breakers, energizers,
  writing style. Conflicts between sources are resolved with the user one at a time.
- Gates before scoring: scam or closed, eligibility, language (flag and discard gap steps), location, role,
  seniority, contract and salary, avoid lists and deal-breakers. Weights, bands and decisions are computed by
  `score_analysis.py`; the user tunes them in `profile.md`.
- Model survey per bot on every install: the advisor recommends economical models first (`cost` per candidate in
  `model-roles.yaml`); a premium model is the pick only on `critical` lanes (design-pro, code-complex, review) or when
  nothing cheaper is connected, and the reason says which.
- Fresh openings only: each weekday check reads the postings that appeared since the previous one (default one
  check at 12:00 in the user's time zone, up to four via `search_times`; Monday covers the weekend). The window goes to
  LinkedIn in minutes (`--max-age-hours`) and to `prefilter --since`.
- Portal search (`searching-portals`): LinkedIn public listings and freehire as zero-dependency bun tools behind
  `portals.py` (search, detail, health). `adding-portals` guides a board for any market.
- Batch ranking (`ranking-openings`) over `searches/seen.json` with deadline sweep, retry bookkeeping and staleness.
- Posting guard: fetched text is cleaned and flagged for hidden text, instructions aimed at an AI, hidden links and
  invisible characters. Polite fetch with robots.txt.
- Documents: three ATS-safe HTML templates, cover letter rendering, page budget from the market, relevance-weighted
  cutting, `verify_pdf.py` (text layer, page count, ASCII dates) and `verify_layout.py` (holes, stranded headings).
- Review: grounding across all sources, exact replace corrections, company claims kept only when verified from a
  page the reviewer found, language and market checks, interview-backtrack test; `aggregate_review.py`.
- Outcomes and follow-ups (`tracking-outcomes`, `tracker.py`), job mail through the Gmail connector on `jobs-writer`
  (`triaging-inbox`, read-only), cron `jobs-followups`, offline `reports/dashboard.html`, skill-gap study plans
  (`planning-upskilling`, `skill_gaps.py`), and a salary benchmark over the user's own data (`salary_lookup.py`).

### Changed

- `jobs-reviewer` gains `terminal` and `web` (company-claim checks); `jobs-applier` and the manager gain `terminal`.
- `jobs-scout` requires `bun`.

## 2.5.2 - 2026-10-21

### Fixed

- A data root outside the one that owns the installed Hermes (a test's temp root, the release gate's root) made
  Hermes sync its own ~350 MB dependency environment from an empty uv cache before answering; squadctl's 120 s
  runtime probe timed out on a loaded machine and the release gates went red for correct code. squadctl now asks
  the runtime from an empty home inside the owning root (no sync), and a borrowing root links its uv cache to the
  owner's shared cache. New `scripts/hermes_home.py`.

## 2.5.1 - 2026-10-21

### Changed

- `managing-projects`: pitfalls for bot-chosen folders, what `project_sync.py --setup` does, and repos without a
  `repo/` subfolder; gateway channels name the project folder in their prompt.

## 2.5.0 - 2026-10-21

### Changed

- Projects live where the user creates them. Squads no longer impose `~/Projects/<squad>/`: the bot base, the
  builder SOUL and the web, marketing and jobs managers work in the project the chat runs in (the folder the user
  picked with "+" in Desktop Sessions) and never choose a folder themselves. Squads 3.2.0.
- `project_sync.py --setup` (run by `apply`) creates no folder; it resets the `desktop.repo_scan_roots:
  [~/Projects/<squad>]` that 2.2.0-2.4.1 set in every bot to `[]` and keeps any other list.
- Web squad: the site repo is `site.yaml -> repo.path` (`repo` for a new site, `.` when the project folder already is
  the git repo); skills use `<repo>` and `check_site.py` defaults `--repo` to it.

### Fixed

- `squadctl apply --src <checkout>` ran the builder's installed `project_sync.py` instead of the one being applied.

## 2.4.1 - 2026-10-20

### Changed

- `contributing-upstream`: after an update, read every `Needs you:` line, move generic rules from the backups upstream and keep squad-, fleet- or user-specific ones local; never clear a merge conflict by overwriting the installed skill.

## 2.4.0 - 2026-10-20

Updates keep what the bots learned.

### Fixed

- Updates no longer overwrite skill improvements made on the machine. Hermes's background skill review patches the
  skills a session used, shipped ones included; `hermes profile update` (builder) and `squadctl apply`/`upgrade`
  (squad bots) replaced those skills whole. Both now merge the local edit with the new version (`scripts/merge3.py`,
  three-way, stdlib): an edit to a file the update did not change is kept, separate changes are combined, an overlap
  installs the new version and reports `Needs you` with the local copy in `local/backups/`.
- Runtime dot files under `skills/` (`.usage.json`, `.curator_ledger.jsonl`) are no longer reported as edited
  shipped files; edits are backed up only when an update actually replaces files.

### Changed

- `authoring-skills`: check every hand-off between stages and create every skill a manifest names before `plan`.
- `changing-bots`: confirm each listed squad skill exists before `plan`.
- `contributing-upstream`: run the release in the background, update the builder after it, and two test pitfalls
  (paths with spaces, `PYTHONPATH` in a Hermes shell).

## 2.3.1 - 2026-10-20

### Fixed

- `contributing-upstream`: create the test venv with `env -u PYTHONPATH`; a Hermes shell's `PYTHONPATH` hid the venv's packages and failed the schema gate test.

## 2.3.0 - 2026-10-20

The builder watches the Hermes docs, and its Hermes references are re-verified against v0.22.2.

### Added

- `watch_upstream.py` third signal: the local Hermes docs each `hermes-platform` reference was verified against
  (`scripts/data/doc-sources.json`). A change wakes the digest with a unified diff and the affected references;
  new and deleted docs pages are reported. The first run seeds the baseline silently; no tokens on quiet ticks.
- `squadctl doctor` warns on a paused squad cron job, with the resume command (a paused job never fires).
- `tracking-updates`: digests doc diffs, and an audit mode for each minor Hermes release.

### Changed

- All 18 `hermes-platform` references re-verified against Hermes v0.22.2 docs and source. Corrections include:
  `profile update` merges cron jobs by id and installs new ones paused; a failing cron script still wakes the agent
  with `## Script Error`; pinned cron jobs never use `fallback_providers`; cron script env is sanitized; scratch
  kanban workspaces are deleted on completion; `kanban_request_changes` lands `todo` while parents are open; the
  stale-claim reclaim needs a heartbeat over 1 h old; `--scheduled-at` is documented but absent from the CLI;
  `message_agent` needs a `Bot Chat` title plus a Bot-Mode-managed install; delegated children of a kanban worker
  cannot close cards; `approvals.mode`, `approvals.deny` and the yolo bypasses; plugin enablement is per profile,
  `--ref` pins and plugin packs; MCP `tools.include/exclude`, `${VAR}` and default-on sampling; the gateway's
  default-deny allowlist; default-off toolsets.
- `hermes-platform` points at `verified_against` in `doc-sources.json`.

### Fixed

- `test_watch_upstream.py`: the fake `hermes` binary quotes its fixture path (failed in a checkout path with spaces).

## 2.2.0 - 2026-10-17

One update path, bots composed from the installed Hermes, and squad Projects in the Desktop.

### Changed

- SOUL.md is composed from the installed Hermes identity, the Hermes base, the bot's role and an optional
  `local/squads/<key>/souls/<bot>.append.md` (kept across updates). A SOUL the user edited stays pending until
  `--confirm soul:<bot>`, then is backed up.
- Base toolsets come from the installed Hermes instead of a hard-coded list.
- One update path: `scripts/auto_update.py`, run daily by the no-agent cron `builder-update` and by "update yourself",
  updates the builder profile and runs `squadctl upgrade` on every installed squad. It keeps learned skills,
  memories, model choices and SOUL edits, and skips a squad with running cards until the next run.

### Added

- `keep_awake.py` cron (`<squad>-awake`): holds sleep off on macOS while cards run.
- `project_sync.py`: copies a manager's Projects to every worker of its squad and binds the squad board; cron
  `<squad>-projects` every 10 minutes (web, marketing, jobs). `apply <squad>` runs `project_sync.py --setup`, which
  creates `~/Projects/<squad>` and points each bot's Desktop repo scan at it.
- `web-frontend-pro` soul.

### Removed

- v1 migration (`migrate_v1.py`) and the old lane aliases.

## 2.1.0 - 2026-10-17

Every squad bot now starts from what makes the default Hermes profile work: Hermes context, web search, terminal and
delegation.

### Fixed

- `always_disabled` held `search`, which is `web_search`: every bot lost web search even with `web` on. It also held
  `desktop_ui` and `project`, so managers could never open the preview pane beside the chat, and `code_execution`.
- Bots had a role-only SOUL: they did not know they run inside Hermes. Every bot's SOUL.md now starts with
  `squads/_base/hermes-base.md` (identity, harness facts: preview pane, background servers, deferred tools,
  delegation to cheaper models, keyless web search, how to ask for a missing tool).
- Managers had no terminal, browser or cron. Bot toolsets are now the role's base (`BASE_TOOLSETS`, plus
  `MANAGER_TOOLSETS` for the manager) plus the manifest's; a worker drops a base toolset only with `withhold:`
  (web-deployer: web, code_execution; marketing-creative and jobs-writer: web). Managers never withhold.
- Delegation ran on the bot's own model. Every bot's `delegation.model` now comes from the cheap `research` lane
  unless its manifest names another lane.
- A clean machine had no browser for the bots: `apply` runs `hermes tools post-setup agent_browser`. The builder's
  bootstrap config has web, browser and delegation before "set me up".

### Added

- `squadctl doctor`: a `<bot>:web` check (toolset on, `search` not disabled, a backend or the keyless tier).
- `leading-web`: live view step (dev server in the background + preview pane).
- Tests: no always-disabled toolset shares a tool with the base (checked against the Hermes source), every bot gets
  the Hermes base and its SOUL, managers cannot withhold, doctor fails a bot without web search, apply installs the
  browser.

## 2.0.11 - 2026-10-16

### Changed

- README and squad READMEs: descriptive titles, a plain first paragraph and a short FAQ so people and AI search
  find and quote the project. `llms.txt` summary matches.

### Fixed

- `release.py` no longer passes the Hermes runtime's `PYTHONPATH`/`PYTHONHOME` to the `--python` interpreter, which
  broke `jsonschema` in the test venv.

## 2.0.10 - 2026-10-16

### Fixed

- `test_readme_install_command_uses_real_flags` skips when `hermes` is not installed (CI) instead of failing.
- `release.py`: on red checks it pushes `release/<version>` and opens the PR with `gh pr create --head`; the old
  `--push` flag does not exist in `gh`.

## 2.0.9 - 2026-10-16

### Changed

- README: what the project does, the builder's flow as the only diagram, install, and a squad table linking to each
  squad's README. PuntoyComaTech header badges and footer.
- Squad READMEs (`squads/<key>/README.md`): purpose, a colored vertical flow, what you can ask, bots, schedule,
  requirements and files, with a link back and the same footer.

## 2.0.8 - 2026-10-16

Squads are opt-in: "set me up" installs the builder, then asks which squads to add.

### Changed

- `installing-squads`: after `apply --self` the builder asks once "Only the builder (default), Web, Marketing,
  Jobs, or Everything?" and installs nothing more without an answer. Several squads share one model table and
  one OK.
- README rewritten: what the project does, what a squad is, the install choice, and vertical diagrams.
  Squad READMEs use vertical diagrams too.
- `AGENTS.md` and `llms.txt`: an agent asked to install this repo installs only the builder; squads and models
  stay the user's choice.

### Added

- Tests: `apply --self` creates no squad profile; README diagrams are vertical, its squad links match the repo,
  its install flags exist in `hermes profile install --help`, and the agent install rule is present.

## 2.0.7 - 2026-10-16

Every bot gets the install's fallback chain, overlays edit repo lists in place, and `plan` names config it
will never touch.

### Added

- `fallback:` in the models file (provider/model/reasoning rows) reaches every bot as `fallback_providers`,
  its children as `delegation.fallback_providers` and `agent.reasoning_overrides`, and is saved in
  `installed.yaml`. `model_advisor.py` recommends a chain when a pick runs on a quota-limited provider.
- Overlay list edits: `skills.keep_add`/`keep_remove` and `plugins.enable_add`/`enable_remove` follow the repo
  lists instead of freezing a copy. A hub keep dropped from the manifest is uninstalled; a hub skill the bot
  installed itself stays.
- `squadctl plan` notes plugins enabled on a bot that its manifest does not declare (kept, never removed) and
  profile-level `kanban.*` keys, which the gateway dispatcher never reads.
- `catalog_search.py --shelf` and `--hermes-version`; plugin hits list `shelf`, `requires_hermes` and
  `known_issues`.
- `skill_lint.py` rule `no-issue-notes`: no upstream issue numbers or harmless-warning notes in bot context.
- References: `memory.md`; credential pools and `prompt_caching.cache_ttl`; Agent Plugins v1 packages and
  `plugins.isolation`; project-skill trust (`managing-projects` trusts a repo that ships skills); every
  auxiliary slot and its lane; connector guest identity and several accounts per app; the renamed tools
  `todo_list`, `cronjob_manage`, `process_manage` and the shipped `tools.tool_search.defer`; Hermes release
  channels (`--set-channel`).

### Fixed

- `apply` fails when Hermes rejects a toolset (it exits 0 and prints "Unknown toolset"); invalid YAML names
  the file and line; a `bots:` model pin that beats its lane is a plan note.
- `cf` and `wrangler` run from PATH, a local npx copy or npx on first use; `doctor` never downloads.
- `model_advisor.py` counts providers available only through a credential pool, `custom:<name>` included.

### Tests

- QA pass merged: real-hermes tests run whenever `hermes` is on PATH; the fake's toolsets match real Hermes;
  the web fixture is the shipped manifest and test models cover every lane; a contract test fails when
  Hermes adds an auxiliary slot squadctl does not route.

## 2.0.6 - 2026-10-15

Bots keep what they learn: apply never deletes their skills, and every bot has memory by default.

### Changed

- `squadctl apply` records what it installed in `skills/.squad-installed.json` and removes only those paths
  (or `.squad-sha` copies, or symlinks into the squad source). Any other skill shows per bot as `learned`
  in `plan` and `apply` and stays.
- Built-in memory is on unless a bot sets `memory: false` (squadctl adds the `memory` toolset). Every SOUL
  has one line on what its memory holds: job pitfalls and fixes, never secrets.
- `designing-squads`: the QA lane is `kanban_request_review(reviewer=...)`; open-ended cards use `goal_mode`.

### Added

- `references/kanban.md`: Review lane, Dispatcher config (root-only keys with defaults), Goal-mode cards.
- `references/cron-and-gates.md`: `--pin`/`--unpin`, `--paused`, `--interpreter`, `--continuity`,
  `cron.catch_up_missed`, `[CRON_FAILURE]`, `cron.failure_repeat_alert_hours`, `hermes cron incidents`.
- `squadctl doctor` warns on a squad agent cron job with no model pin; `apply` restores it.

## 2.0.5 - 2026-10-15

The update watcher stops dropping section-scoped Hermes changes, and squads set no kanban cap.

### Fixed

- `watch_upstream.py` matches keywords against the bullet and its heading; every bullet under Upgrade notes,
  Kanban, Cron, Delegation, Plugin system, Skills and Profiles is priority, and priority bullets over the cap go to
  `<tag>.overflow.md` (`context.overflow`) instead of being dropped. Goal, delegation, memory providers, credential
  pools, connectors and provider plugins are priority keywords. Tested on the recorded v0.22.0 body.
- `watch_upstream.py --squads-ref` (default `HEAD`, the branch `hermes profile update` clones) replaces the
  hardcoded `main`.

### Removed

- The kanban cap: `apply --set-root-kanban-cap` and the `root` key of the apply output are gone. `squadctl doctor`
  warns on any home (root or profile) that sets `kanban.max_in_progress_per_profile`.
- Source citations, decision ids and decision-log pointers from bot-loaded files (`skills/`, `squads/`, script
  comments); `references/cost-levers.md`. A contract test keeps them out.

### Changed

- `references/delegation.md` documents `output_schema`, `images`, `steer`/`stop`, `independent_completions`,
  `fallback_providers` and `child_timeout_seconds`. `hermes-platform` finds the Hermes source through
  `hermes --version` and warns that `config get` flags valid keys outside the schema.

## 2.0.4 - 2026-10-15

The distribution ships the builder plus `web`, `marketing` and `jobs`: the web squad is web-only and
the root kanban cap is opt-in.

### Removed

- The `studio` squad (manifest, four skills, three souls). No board, profile, fixture or reference to
  it remains; `web-frontend-pro` asks the card's requester for offline renders instead of ordering them.

### Changed

- `web-frontend` and `web-frontend-pro` keep `impeccable`, `scrollcraft`, `claude-design`, `design-md`
  and `popular-web-designs`. `hyperframes`, `dream-loop` and `auteur` are out: video rendering and
  taste, not site work.
- `building-3d-motion` gains `references/animation-libraries.md` — GSAP/ScrollTrigger, Lenis, Motion,
  three.js/R3F + drei, Theatre.js and Lottie/Rive, each with its bundle cost and reduced-motion switch.
- `squadctl plan` and `squadctl doctor` never propose `kanban.max_in_progress_per_profile`; `apply
  --set-root-kanban-cap` is the only writer and runs on the user's ask (V-12).
- Squad `version` 3.1.1 in `web`, `marketing` and `jobs`.

### Fixed

- Stale references: `start_search.py --lead` is `--manager`, the marketing templates are named by the
  skill that owns them, `site-contract` names `check_site.py`, and the review-round wording in the
  jobs and web lenses and evals matches the rules that cap rounds.

## 2.0.3 - 2026-10-15

Fixes from the builder's real `web` install, and deploys through the vendors' own CLIs.

### Changed (deploys)

- Deploys ride on the CLIs' own logins (`gh auth login`, `cf auth login`, `wrangler login`; `vercel login` only
  where a project targets Vercel). `web-deployer` no longer passes `CLOUDFLARE_API_TOKEN`,
  `CLOUDFLARE_ACCOUNT_ID`, `GH_TOKEN` or `VERCEL_TOKEN` through its environment and no longer suggests
  `vercel_mcp`; tokens stay documented as the CI/headless path only (D-036).
- `web-deployer` declares `requires.apps: [cf, wrangler, gh]`. `squadctl doctor` reports each required app
  (PATH, the macOS app path, or `npx --no-install` for an npm-packaged CLI) and then its stored login, reading
  only the exit status of `gh auth status` / `cf auth whoami` / `wrangler whoami` — no account, masked token or
  other probe output can reach a check.
- `deploying-sites`: `cf` first (`cf cli search` before any remembered form, `cf schema`, `--dry-run`), Wrangler
  only for what `cf` lacks or for a project that ships a Wrangler config (then `cf migrate` before any
  `cf dev|build|deploy`); `deploy.md`'s third field is `creds` (logins by name, never values).

### Fixed

- squadctl `ensure_board`: inside a Kanban worker (delegated child context) it checks
  `hermes kanban boards list` first and reports "pending owner action: boards create"
  only when the board is actually missing.
- Credentials: `apply --yes` copies a provider's API key (name and value, never printed)
  from the root source into the bot's profile env file (mode 600); `doctor` checks per
  bot that the provider's key is present in the profile env file or the profile auth
  store, and `models ok` no longer passes for a bot that cannot authenticate.
- model_advisor: provider detection unions every probe (in-process, runtime,
  `hermes auth list`) with the provider key names in the root and profile env files
  (names only; values never leave the file), so a provider the first probe misses is
  still detected; key-home reporting counts the same names per scope.
- Per-card reasoning effort is documented as it really is: `kanban create`, `set-model`
  and the `kanban_create` tool carry model+provider only; the task's `reasoning_effort`
  (dispatcher passes `--reasoning`) is writable only from the kanban dashboard. CLI
  paths: `agent.reasoning_overrides`, `delegation.reasoning_effort`, cron
  `--reasoning-effort`, or a dedicated profile (V-07).
- Version: `distribution.yaml` is the single source of truth; the builder manifest is
  versionless and `status` reads the distribution version.

## 2.0.2 - 2026-10-15

Squad structure: managers, visible bots and sections, web roles and `web-frontend-pro` (S1-S3).

### Fixed (S1)

- squadctl apply: a board created from inside a Kanban worker becomes a pending owner
  action instead of failing the run; a provider that is a user plugin of the builder is
  copied into each bot's profile (and `doctor` flags a missing copy); `mcp add` answers
  the real prompt order and fails loudly when the server does not land enabled; a
  provider change clears the stale `model.base_url`/`api_mode`; the machine-wide
  `kanban.max_in_progress_per_profile` is reported by plan and written only by
  `apply --set-root-kanban-cap`; the provider key name is an owner note, never read;
  `doctor [<squad>]` filters to one squad.

### Changed (S2)

- model_advisor: per-provider auto-detection with key-home reporting, local
  `providers-exclude.txt` (detected, never recommended) and role lanes across families
  (`manager`, `frontend`, `design-pro`, `code-complex`, `code-routine`, `review`,
  `deploy`, `research`, `digest`, `aux`, `vision`) with alias compat for deprecated
  lane names.

### Changed (S3)

- Managers (C-11): exactly one manager per squad, profile name = the squad key, title
  `<Name> manager`; workers are `<key>-<role>`. The manifest field `lead` is now
  `manager` and role `lead` is `manager`; lane `lead` is `manager` in every shipped
  manifest (the aliases stay so older manifests resolve).
- All bots are visible: squadctl files the Desktop sections `Managers` (managers) and
  one section per squad (workers) through `ui_meta.hermes-bots` (V-12).
- Web squad: canonical lanes (`manager`, `frontend`, `code-routine`, `review`,
  `deploy`); `web-backend` runs `code-routine` and the manager pins the `code-complex`
  model per card on hard problems; optional `web-frontend-pro` (lane `design-pro`,
  installed only with `squadctl apply web --with web-frontend-pro`) with the new
  `building-3d-motion` skill (three.js/R3F, GSAP, Blender pipeline, perf budgets and
  fallbacks).
- `deploying-sites` refuses to deploy without the project's `deploy.md` (target,
  command, env names, rollback; template provided).
- `designing-squads` holds the squad Rules (naming, visibility, cap, credentials,
  skill sources) and the Topology (delegate_task subagents vs Kanban workers; single
  bot with or without a board; one board per squad, one Project per repo).

### Fixed (release gate)

- squadctl: provider plugins installed at the root home are copied like builder ones;
  providers with no API-key env var (OAuth, external process) get no credentials note.
- squadctl `inventory`: documents the local fleet read-only (C-12).
- hermes-platform references: tool-search bridge lists `tool_describe`; `message_agent`
  also reaches a Bot Chat opened from the CLI; per-profile credential and provider
  plugin resolution added.

## 2.0.1

- release.py: `private` gate blocks local-only names listed in the maintainer's `local/private-terms.txt`.
- contributing-upstream: never publish local fleets.

## 2.0.0 - 2026-10-15

Full redesign as a profile distribution (see `docs/decisions.md`).

### Added

- The repo root is the builder's profile distribution: `hermes profile install ... --name
  builder --alias`, updated with `hermes profile update builder` (V-01).
- `squadctl` (`plan`, `apply`, `uninstall`, `status`, `doctor`, `project`, `chain`) with an
  idempotent plan, OK, apply flow (V-10).
- `model_advisor.py` (lane table per bot from the user's providers), `catalog_search.py`
  (plugins, skills, MCP, connectors), `skill_lint.py` (format gate), `kanban_chain.py`
  (chain to dependent cards), `gate_lib.py` (wakeAgent helpers), `watch_upstream.py` (daily
  zero-LLM update gate) (V-08, V-09, V-14).
- `scripts/hpy` runs every tool under the Hermes runtime interpreter (no PyYAML needed);
  `scripts/release.py` gates maintainer pushes to main.
- `scripts/board_watch.py`: a `<key>-watch` cron on every manager posts blocked and stale cards
  to the manager's Bot Chat (V-05).
- Squad manifests schema 2 (`squads/_schema/squad.schema.json`) with bots, chains, cron
  gates and per-card lanes.
- Ten builder skills under `skills/`, including `hermes-platform` (18 verified Hermes
  reference topics with citations) (V-09).
- `scripts/migrate_v1.py`: detects a v1 install (legacy profiles, `~/Hermes/projects/*`,
  `deliver.py` crons), registers the folders as native Projects, removes the deliver crons and
  archives the orchestrator into `local/backups/`; `--dry-run` and `--json`.

### Changed

- One visible manager per squad replaces the global orchestrator; workers are hidden and run
  one card at a time (V-02, V-12).
- Native Hermes Projects replace imposed `~/Hermes` folder layouts (V-04).
- Kanban notify and `bot-chat:<manager>` delivery replace `deliver.py` and the outbox (V-05).
- Profiles are created with `--no-skills`, pruned per role; squad skills are copied with a
  sha marker (V-06).
- Real, tested scripts replace prose scripts (V-03).
- The jobs analyst merges into the scout; review work pins the review lane per card (V-17).

### Removed

- `base/`, `START-HERE.md`, `README.es.md`, `00-evaluation/` (decisions condensed in
  `docs/decisions.md`), the v1 prose migrations (replaced by `scripts/migrate_v1.py`).