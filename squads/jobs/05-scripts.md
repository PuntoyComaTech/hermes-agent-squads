# Scripts: job search

> Script specifications. **The installer AI itself** (Hermes, with `terminal` and `file`) writes them in step 5 of the installation: the user does not need any other tool. They also work as prompts for any coding AI.
> Level 1 needs four: `start_search.sh`, `deliver.py`, `render_cv.py` and `check_links.py`. API ingest is Level 2.

## Common preamble

```markdown
Project: {{J}} = {{ROOT}}/projects/jobs, Python 3.11+, venv in {{ROOT}}/projects/jobs/.venv.
Deterministic code, no LLM, no external services except the ones the prompt names. Each
script is a CLI with argparse, JSON output when --json is passed, logs to stderr, exit 0 on
success, 1 on a data error, 2 on a network error. Idempotent. Tests with pytest in tests/
and a short README. Do not read or write outside {{J}} (except reading {{ROOT}}/user/).
Secrets only from environment variables. Respect robots.txt and use an identifiable
User-Agent. The data contracts are in 02-architecture.md (attached).
```

## Level 1

### `start_search.sh`

```markdown
Create scripts/start_search.sh (and start_search.ps1 if the system is native Windows).
If outbox/PAUSE exists, exit without printing anything. Otherwise, run:
  hermes kanban create "Search <YYYY-MM-DD HH:00>" --assignee jobs-scout \
    --workspace dir:{{J}} --idempotency-key search-<YYYY-MM-DD-HH> \
    --body "Mode: SEARCH. Date: <date>. Follow your SOUL and the job-filter skill."
It prints nothing if all goes well (silent cron); if the command fails, it prints the error
and exits with 1 (cron sends an alert). It is linked in the $HERMES_HOME/scripts/ of the
jobs-scout profile.
```

### `deliver.py`

```markdown
Create scripts/deliver.py. It runs every 15 min via cron --no-agent in the orchestrator
profile. Steps:
1. Read ../../user/profile.md (schedule and channel) and jobs-profile.yaml
   (max_deliveries_per_day). If the current time is outside the schedule, skip to step 4.
2. For each outbox/ready/*.json, from the highest score to the lowest, without exceeding
   max_deliveries_per_day counting the ones sent today: build the message in the format of
   02-architecture.md §2 (for type change: "✏️ CV updated · <role> — <company>") and
   run
     hermes -p orchestrator send --to <channel> "<message> MEDIA:<cv path>"
   If the send works, move the JSON to outbox/sent/ and update status.json →
   DELIVERED. If it fails, leave it for next time and print the error.
3. Blocked tasks: hermes kanban list --status blocked --json; for each task from a
   jobs-* profile not notified before (save the ids in outbox/.blocked_notified), send
   one line: "⚠️ <JOB or task> needs your answer: <reason>. Reply to me here."
4. Regenerate tracking.csv from openings/*/ (opening.md, status.json, analysis.json,
   submission.json) with the header from 02-architecture.md.
It prints nothing except errors. No LLM. Tests with sample folders and a simulated send
command.
```

### `render_cv.py`

```markdown
Create scripts/render_cv.py. Input: --content application/cv_content.json
--template <cv-ats|cv-custom> [--analysis analysis.json] --output application/
[--pages N] [--engine weasyprint|chromium]. Jinja2 templates in
templates/<name>/{cv.html, styles.css, fonts/}.
Outputs:
1. cv_ats.pdf (cv-ats template, weasyprint): one column, no icons or tables, standard
   section headings based on content.language (Experiencia/Experience,
   Formación/Education, Habilidades/Skills, Idiomas/Languages), real clickable links,
   fonts embedded from templates/cv-ats/fonts/.
2. cv_custom.pdf if templates/cv-custom/ exists (same content, selectable text, links
   preserved; --engine chromium uses headless playwright).
3. cv.docx with python-docx and native Word styles for the headings.
4. cv_ats.txt with pdftotext -layout on cv_ats.pdf.
5. render_report.json: pages, expected_pages, selectable_text, links[],
   embedded_fonts, reading_order_ok (section order in cv_ats.txt = cv_content),
   contact {email, phone, links}, keyword_coverage (share of
   analysis.requirements.keywords present in cv_ats.txt, normalizing accents and
   case), missing_keywords[], defects[].
No network. Same input → same result, except date metadata. Exit 1 if pages !=
expected_pages or selectable_text = false. Include the cv-ats template and a sample
cv_content.json in Spanish and another one in English, with their tests.
Dependencies: jinja2, weasyprint, python-docx, pdfplumber; system pdftotext (poppler).
```

### `check_links.py`

```markdown
Create scripts/check_links.py: it takes URLs as arguments or --from-content
application/cv_content.json (header.links and the strategy pieces, if any).
It does a HEAD request and, if that fails, a GET with a 10 s timeout, follows redirects and
writes application/links.json with [{url, status_code, final_url, ok}]. No cache.
Dependency: httpx.
```

## Level 2 (do not install until moving up a level)

### `normalize.py` and `ingest_<source>.py`

```markdown
Create scripts/normalize.py with: canonical_url(url) (removes utm_*, fragments, sorts the
query); norm(text) (lowercase, no accents or punctuation); fingerprint(company, role,
location) = sha1 of the normalized values; language(title, description) with
lingua-language-detector; work_mode(text, location) using the opening.md values;
required_language(text) with the CEFR table in 02-architecture.md §4. Tests with 30 real
titles in the languages of application_languages.

Create one script scripts/ingest_<source>.py for each source with via: api in
jobs-profile.yaml. Before coding, verify in each source's official documentation the
endpoint, the parameters and the usage limits, and note them in the README (do not use
endpoints from memory). Each script: queries with the search_keywords; normalizes;
discards fingerprints that already exist in openings/ or tracking.csv; for each new
opening, writes openings/<ID>/opening.md with filter: PENDING; prints one line
"<source>: N new", or nothing if there are none (empty output = silent cron). Respects
limits with backoff.
```

Operation at Level 2 (the installer sets it up when the decision to move up is made):

- `--no-agent` cron in the `jobs-scout` profile, one job per ingest script, every 2-4 h (scripts linked in its `$HERMES_HOME/scripts/`).
- The scout's scheduled search (Level 1) now starts with the `opening.md` files that have `filter: PENDING`, and only then searches the web: more coverage with less spend.

## Sources: how to choose them for each user

The personalizing AI proposes sources based on country and occupation, and the user confirms. Order of preference:

1. **Public API** of the job board, or of the target companies' ATS (Greenhouse, Lever, Ashby, Workable and similar ones publish listings per company).
2. **Public page** without login, read by the scout.
3. **Indexed results** in search engines (`web_search`), for job boards that block scraping.
4. **Manual**: the user pastes the URL. It is the only way for LinkedIn.

Examples worth verifying case by case: Get on Board (LATAM, tech and design), Computrabajo and Bumeran (LATAM, no API), InfoJobs (Spain), Remotive, Remote OK and We Work Remotely (global remote), Dribbble and Behance Jobs (design), the country's public job portals.
