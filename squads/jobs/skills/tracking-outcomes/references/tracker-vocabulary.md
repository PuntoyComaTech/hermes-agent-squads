# Tracker vocabulary

The `status` column of `tracker.csv` takes the squad statuses (jobs-contract `references/opening-files.md`), lowercase snake_case. The status history in
`openings/<ID>/status.json` takes the same list through `status.py`.

## Contents

- Statuses and buckets
- Legacy spellings
- Deadline flags
- Follow-up and stale rules

## Statuses and buckets

| Bucket | Statuses | Meaning |
|---|---|---|
| not sent | found, analyzed, in_preparation, in_review, not_approved, ready, delivered, applying, manual_application | nothing went to the employer; never chased |
| active | applied, followed_up, screening, waiting | submitted, no decision yet; chased after `follow_up_days` |
| interview | interview | an interview stage is booked or done |
| offer | offer | an offer is open; the user decides |
| hired | hired | accepted |
| closed | rejected, no_response, withdrawn, closed | final, no further follow-up |
| skipped | skipped, discarded | final, never submitted |

## Legacy spellings

Trackers written earlier may hold two other values. The tracker reads them as the squad status they stand for and
never writes them:

- `drafted` reads as `ready` (not sent).
- `offer_declined` reads as `withdrawn` (the candidate declined; the offer stage is not counted).

Space forms (`no response`, `offer declined`) are normalised to the underscore form on read.

## Deadline flags

The tracker reports data fields, never emoji:

- `deadline_flag`: `soon` (7 days or fewer), `passed`, `invalid` (not a YYYY-MM-DD date), or null.
- `deadline_soon` and `deadline_passed`: the booleans derived from the flag.

A passed deadline on a row that is still not sent is named in the report so the user can decide.

## Follow-up and stale rules

- Follow-up: quiet for `follow_up_days` from `profile.md` (default 10) and fewer than two follow-ups. The cap is 2.
- Stale: quiet for `stale_days` (default 60), submitted rows only, read-only until the user confirms.
- Quiet time counts from the most recent of `applied_at`, `last_contact` and a dated note stamp, never a future date.
