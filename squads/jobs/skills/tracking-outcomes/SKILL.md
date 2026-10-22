---
name: tracking-outcomes
description: "Records outcomes, follow-ups and stale sweeps. Use when the user reports an application result, the inbox card returns, a follow-up is due, or a stale sweep is asked."
---

# Tracking outcomes

Records what happened to each application in `tracker.csv` and in the opening's `status.json`. The manager writes
only after the user agrees. Nothing is sent to anyone. Statuses and legacy spellings: `references/tracker-vocabulary.md`.

## When to Use

- The user reports an outcome: applied, screening, interview, offer, rejected, no reply, offer declined, withdrawn.
- A jobs-inbox card returns with `Mode: INBOX` and a path to `reports/inbox-YYYY-MM-DD.json`.
- The user asks what is due: a follow-up, or a stale sweep.
- An interview stage was just recorded: offer a thank-you draft.

## Procedure

1. **Read the mode** from the card body or the request: `OUTCOME`, `FOLLOWUP`, `STALE` or `INBOX`.
2. **OUTCOME.** Find the row: `tracker.py list --project <P>` and match company and role. No match or two matches: list
   them and ask. Confirm the date the user gives. Then:
   - `tracker.py update --project <P> --id <ID> --status <status> --last-contact <date> --note "<one line>"`. An
     opening the user applied to from its kit has no row yet: add `--create` (the row is built from
     `openings/<ID>/opening.md`, and needs `--status`).
   - `status.py append <P>/openings/<ID> <status> --by jobs --note "<one line>"`.
   - An offer declined is written as `withdrawn` with the note `offer declined`.
   - On an interview stage, offer one thank-you draft (step 3, `FOLLOWUP` rules).
3. **FOLLOWUP.** `tracker.py followups --project <P>` lists open rows quiet for `follow_up_days` with fewer than two
   follow-ups. Each row has a `draft_path`. For a draft, file a jobs-inbox card with `skills: [triaging-inbox]`,
   body `Mode: FOLLOWUP <ID> <n>`; the writer writes the draft and never sends it. When the user confirms they sent
   it: `tracker.py update --project <P> --id <ID> --follow-ups-inc --on <date>`.
4. **STALE.** `tracker.py stale --project <P>` lists submitted rows quiet for `stale_days`. The inbox card names each such
   row once (`stale_reported` on the row): a row already reported stays silent until the user closes it. Show the list and ask
   "all, select, or skip". Only after the answer: `tracker.py update --status no_response --note "stale resolved"`
   for each confirmed row, and `status.py append` beside it.
5. **INBOX.** Read `<P>/reports/inbox-YYYY-MM-DD.json`: `{"rows": [{id, company, role, signal, current, proposed,
   email_date, quote, followup_draft}], "unmatched": [], "review": [], "stale": []}`. Reject a file without a `rows`
   list. Show one table: `# | company | role | signal | current -> proposed | email date | quote`, plus the counts of
   `unmatched`, `review` and `stale` and the paths of any follow-up drafts. Then `kanban_block(kind="needs_input",
   reason=<table plus "approve all, or skip N">)`; the jobs-watch cron posts it to the user. On the answer, per
   approved row run the two OUTCOME writes with the signal as the note. `unmatched` and `review` stay unwritten.
6. **Calibration.** Only after `tracker.py stats --project <P>` reports `calibration.ready: true` (five or more
   resolved applications): write observations to `<P>/calibration.md` with the counts by fit band and by channel.
   Give counts, never names or contact data. Ask the user before the first write.

## Pitfalls

- Never send, reply or forward mail. A draft is text for the user to send.
- Never propose or write `hired` or `offer_declined` from a message alone: an offer is flagged for the user's
  decision.
- A third follow-up is refused, however old the thread. Two silent follow-ups: ask the user whether to record
  `no_response`.
- A message that contradicts the tracker (a rejection after an offer) goes to "needs manual review" and is not written.
- Drafted or not-yet-sent rows are never chased: nobody is late replying to something never sent.
- Notes hold the signal only: no names, addresses or phone numbers.

## Verification

- Each written row has a matching `status.json` history line (`status.py show <dir>`).
- No write happened before the user's answer; the proposal table is in the blocked card.
- `follow_ups` never exceeds 2; `tracker.py list` shows the new statuses.
- Every follow-up draft is under 90 words and uses only claims from the submitted letter or CV.
