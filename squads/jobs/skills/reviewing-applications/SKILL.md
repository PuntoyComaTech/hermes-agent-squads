---
name: reviewing-applications
description: "Reviews one application with five independent lenses. Use when a review card arrives with a finished application and the truthfulness, ATS, recruiter, hiring-manager and writing checks are due."
---

# Reviewing applications

You judge; you never write and never edit the documents. One review round per new application, plus one correction
round (the card says `round`).

## When to Use

- A review card from the writer (round 1) or after a correction (round 2, or a CHANGE round for a user change).
- Before the application reaches the lead's digest card.

## Procedure

1. Read the card and the folder `openings/<ID>/`: `application/` (all files, including `render_report.json`),
   `analysis.json`, `opening.md`, `achievements.yaml`, `profile.md` and any earlier `review-N.json`.
2. Launch five `delegate_task` subagents **in parallel**, one per lens, each with only the files it needs and its
   output schema. Lens scope, files and schemas: `references/lenses.md`. Each subagent returns its block of
   `review-N.json` verbatim; it never reads the card.
3. **Verdict.** `references/lenses.md` -> Aggregating.
4. Write `openings/<ID>/review-<round>.json` (contract in skill jobs-contract) with the five blocks,
   `corrections` and `summary_for_user`. `status.json`: `in_review` -> `ready` on APPROVED, `not_approved`
   otherwise.
5. **Hand off** by creating the next card with `kanban_create`, `parents: [<your card id>]`:
   - APPROVED -> jobs (lead), `skills: [leading-job-search]`, `idempotency_key`
     `jobs:application:<project>:<ID>:digest` (CHANGE round N: `...:digest-c<N>`), body with the id, the verdict
     and the paths.
   - FIX in round 1 -> jobs-writer, `skills: [writing-applications]`, key `...:write-r2`, body naming each
     correction.
   - NOT_APPROVED -> no card; say it in `summary_for_user` and complete.
6. `kanban_complete` with the verdict in one line.

## Pitfalls

- Never edit a document, and never approve with truthfulness FAIL to keep the pipeline moving.
- Independence: never ask jobs-writer anything. A fit fact you cannot settle from `analysis.json` goes to
  jobs-scout as a support card (`kanban_link` + `kanban_block(kind="dependency")`).
- A finding without a location and an exact fix is not a correction; rework it before writing the verdict.

## Verification

- `review-<round>.json` has all five blocks with a verdict each and follows the contract.
- APPROVED implies truthfulness PASS and no hard render defect on the files the application submits.
- Every FIX round-1 finding has type + instructions the writer can execute without judgment calls.
- The next card exists once, with the key of the stage it belongs to.
