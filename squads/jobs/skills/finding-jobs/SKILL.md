---
name: finding-jobs
description: "Searches job boards and applies the hard filter. Use when a search card or a pasted link needs the opening saved, filtered and, when it passes, passed to analysis."
---

# Finding jobs

Your card says SEARCH (scheduled or on demand) or URL (the user pasted one or more links). You find real openings,
save their full text, apply the hard filter and hand every PASS opening to analysis.

## When to Use

- A search card from the `jobs-search` cron, or a URL card from the lead.
- Before saving any `opening.md` or creating an analyze card.

## Procedure

1. Read your card: mode, project slug and folder path, the "Analysis cards" line, and `profile.md`
   (`search_keywords`, `search_days`, `max_analyses_per_day`, `analyze_flagged`, `confidential_search`).
2. **Search** in this order: career pages of `profile.md -> target_companies`, public job boards,
   indexed results, and the URLs your card brings. Keywords in every language of `search_keywords`; openings
   posted within `search_days`. With `confidential_search: true`, never search the user's name or current
   employer.
3. **Deduplicate** before you save: same company and role with an existing folder under `openings/` within 30
   days is the same opening. Canonicalize URLs (drop `utm_*` and fragments) so one opening is one folder.
4. For each new opening, open the page and save the full text to `openings/<ID>/opening.md` with the front matter
   of skill jobs-contract, `references/opening-files.md`. Never log in.
5. **Filter** with `references/filter-rules.md`, in order: the first rule that discards, discards. Record
   `filter` (PASS, FLAG or DISCARD), `filter_reasons` (short, verifiable phrases) and `labels`.
6. Write `<P>/searches/YYYY-MM-DD-HH.md`: one row per candidate, PASS first, then FLAG, then DISCARD grouped by
   reason.
7. **Hand off** each PASS (and each FLAG when `analyze_flagged: true`), best apparent fit first, up to
   `max_analyses_per_day` analyses that day: `kanban_create` for jobs-scout with `skills: [analyzing-jobs]`,
   `parents: [<your card id>]`, `idempotency_key` `jobs:application:<project>:<ID>:analyze`, the project,
   `workspace_kind: dir` with `workspace_path` = the project folder, and `model`/`provider` from the "Analysis
   cards" line of your card body (they pin the review lane for the analysis). Without that line, file it without
   them.
8. `kanban_complete` with the counts (found, PASS, FLAG, DISCARD, cards filed). If no source responds or the
   project files are missing, `kanban_block` and say exactly what is missing.

## Pitfalls

- Do not repost the same opening under a second id because the URL changed: canonicalize and deduplicate first.
- Never solve a CAPTCHA or mass-extract a site whose terms forbid it.
- A DISCARD row never gets an analyze card.

## Verification

- Every `filter_reasons` entry can be checked by reading `opening.md`.
- One folder per opening; the search file lists every candidate you looked at.
- One analyze card per PASS opening with the expected idempotency key.
