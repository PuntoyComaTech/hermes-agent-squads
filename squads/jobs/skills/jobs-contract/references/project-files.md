# Project files

Everything in `<P>` outside `openings/`: the person's material, search state, the tracker and the reports.

## Layout

```
<P>/
  profile.md  achievements.yaml  contact.yaml  application-data.yaml  calibration.md
  documents/{cv,linkedin,diplomas,references,projects}/   # raw material the user drops in
  searches/YYYY-MM-DD-HH.md  searches/seen.json
  companies/<slug>.md
  openings/<ID>/...                                       # references/opening-files.md
  tracker.csv
  reports/dashboard.html  reports/upskill-YYYY-MM-DD.md
  reports/inbox-YYYY-MM-DD.json  reports/followups/<ID>-<n>.md
  reports/evidence-YYYY-MM-DD.json                        # jobs-scout, Mode: EVIDENCE
  templates/<name>.html [+ <name>.json]                    # user designs, usable only after template_check.py passes
  .trash/<timestamp>/  (RESET-MANIFEST.json + moved entries)   # reset_project.py; never deleted by the squad
```

A reset never deletes: it moves the entries into `.trash/<timestamp>/` at their original relative paths, with a
`RESET-MANIFEST.json` that lists them. Moving an entry back restores it.

`contact.yaml`, `application-data.yaml`, `documents/` and `tracker.csv` hold personal data: never commit them to a
public repository and never copy them into a card.

## searches/YYYY-MM-DD-HH.md (scout)

Table, one row per candidate: `id | company | role | work mode | required language | filter | reason | url`;
PASS first, then FLAG, then DISCARD grouped by reason. Referral search links follow the PASS and FLAG rows as plain
text for the user to open. Each search ends with its summary block (leading-job-search, step 5), which is a card, not a
file: the table is the record.

## searches/seen.json (scout, through seen_state.py)

```json
{"schema": 1, "seen": {"acme_data-analyst": {
  "company": "Acme", "title": "Data analyst", "url": "https://...", "portal": "linkedin",
  "opening_id": "JOB-20260925-acme-data-analyst", "first_seen": "2026-09-25",
  "posted_at": "2026-09-24", "deadline": null, "status": "ranked",
  "rank_score": 74, "rank_band": "good", "rank_date": "2026-09-25",
  "gates": {"eligibility": "PASS", "language": "FLAG", "location": "PASS"},
  "strengths": [], "gaps": [], "guard": "clean"}}}
```

Statuses: new, ranked, skipped, expired, unreachable. `seen_state.py add` registers, `apply` writes ranking results,
`sweep` expires passed deadlines, `audit` checks the file. A null deadline means none stated; it is never guessed.

## tracker.csv (manager, through tracker.py)

Columns: `date,id,company,role,status,channel,fit_score,apply_url,deadline,applied_at,last_contact,follow_ups,
notes,cv_file,cover_letter_file,source`. One row per application the user decided on. Statuses are the
`status.json` vocabulary. A cell starting with `=`, `+`, `-` or `@` is written with a leading apostrophe.
`tracker.py followups` lists quiet rows (at most 2 follow-ups each), `stale` lists rows past `stale_days`.
`record_submission.py` adds the row after a submit or a delivered kit (`tracker.py add --if-missing`).
`tracker.py list --json` prints the rows for other scripts; `update --create` builds a missing row from `opening.md`
(an opening applied to from its kit). `apply_url` is http or https, or `mailto:` with `--channel email`. The optional
column `stale_reported` is set by the follow-up gate so a stale row is reported once.

## reports/ (manager and writer)

- `dashboard.html`: `build_dashboard.py`, one offline file with no external requests.
- `upskill-YYYY-MM-DD.md`: skill planning-upskilling, from `skill_gaps.py`.
- `inbox-YYYY-MM-DD.json`, `followups/<ID>-<n>.md`: skill triaging-inbox (writer); the manager applies approved rows.

## calibration.md (manager)

Observations from resolved applications (which roles and bands reached interview), written only after 5 or more
resolved applications. It informs the user; it never changes `scoring` without the user's ok.
