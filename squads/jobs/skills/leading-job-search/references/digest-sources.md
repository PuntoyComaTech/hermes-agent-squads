# Where a digest's fields actually live

`analysis.json` has no top-level `score`, `role`, company string or `apply_url`. Reading those keys off it returns
null for every opening and makes a finished analysis look broken. Each field comes from a different place:

| Digest field | Source |
|---|---|
| score, band, verdict word | `status.json` -> last non-empty `history[].note` ("PURSUE 80 (band strong)"); some openings also carry `fit.score`, `fit.band`, `fit.decision` |
| role | `opening.md` title line (the ATS title, e.g. "Senior Software Engineer - Colombia") |
| company | `analysis.json` -> `company.name` — a dict with `summary`, `team_signals`, `news`, `sources`, never a plain string |
| work mode | `gates.location` plus `remote_eligibility`; the posting title usually states it ("Remote - North America - South America") |
| apply link | `link_verification.url`, then `link_resolution.apply_url` / `canonical_url`, then `official_posting.url`, then any URL in `opening.md` |
| CV | `<opening>/application/cv_ats.pdf`; `cover_letter.md` and `answers.md` sit beside it |
| gates | `analysis.json` -> `gates.{eligibility,language,location,seniority}` with a `*_note` each |
| review outcome | highest-numbered `review-N.json` -> `verdict` (`APPROVE` / `FIX` / `NOT_APPROVED`) and `summary_for_user` |

`scripts/digest_fields.py <project>` prints all of the above in one pass; run it instead of re-reading whole JSON
files by hand.

## Reading order (three rules)

- Read `status.json` `history` backwards first. It is the authoritative verdict and is often newer than the analysis
  body, because a re-run fixes a gate that was wrong (a location FAIL that later passes once `work_mode` is right).
  Quoting the body without checking history repeats a superseded rejection.
- `status.json` `status` is the stage: `found` (not analysed yet), `analyzed`, `in_review` (kit on disk), `delivered`
  (digest sent), `applying` / `applied`, `skipped`, `discarded`, `not_approved`. A digest is owed for `delivered`-to-be
  (`in_review`); an `analyzed` WATCH is only mentioned, not offered.
- A `review-1 FIX` note followed by a **newer** `cv_ats.pdf` mtime means the corrections are already in; an **older**
  PDF means the writer is still rewriting the kit, so say that in one line instead of presenting a stale kit as final.

## No ATS link

When `link_resolution.found` is false (or no `link_*` block exists at all) there is no employer ATS page: the live
surface is the aggregator or LinkedIn URL in `opening.md`. Put that URL in the digest and say in the warning line that
the application goes through LinkedIn, because nothing else can be submitted to.
