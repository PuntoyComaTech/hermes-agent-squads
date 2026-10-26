---
name: reviewing-applications
description: "Reviews one application with five independent lenses. Use when a review card arrives with a finished application and the truthfulness, ATS, recruiter, hiring-manager and writing checks are due."
---

# Reviewing applications

One review per card. `review-1` is the first review; a correction or CHANGE review is `review-N` with N >= 2. The
second-round rule applies from N = 2: anything not approved is NOT_APPROVED.

## When to Use

- A review card from the writer: the first review, a correction round, or a CHANGE round after a user request.
- Before the application reaches the manager's digest card.

## Procedure

1. Read the card and `openings/<ID>/`: `application/` (every file, including `render_report.json` and
   `cv_content.json`), `analysis.json`, `opening.md`, `status.json`, `achievements.yaml`, `profile.md` (its front
   matter `market` and `reviewer_role`) and any earlier `review-N.json`.
2. Start five `delegate_task` children in parallel, one per lens. Each gets its section of `references/lenses.md` as
   the goal, the files that lens names as context, and the lens block shape as its `output_schema`. Children never
   read the card and never write files. Only the truthfulness child searches the web, and only for company claims;
   the other children are told not to search.
3. Save each block as `<lens>.json` (truthfulness, ats, recruiter, hiring_manager, writing) in a scratch folder inside
   your card's workspace, not in the project folder. Only `review-<N>.json` and `status.json` go into `openings/<ID>/`.
4. Aggregate. First run without `--out` to read the verdict:

   ```bash
   python3 "$HERMES_HOME/skills/squad-jobs/reviewing-applications/scripts/aggregate_review.py" \
     --lenses <L>/truthfulness.json <L>/ats.json <L>/recruiter.json <L>/hiring_manager.json <L>/writing.json \
     --round <N> --id <ID> --application-dir <P>/openings/<ID>/application --opening <P>/openings/<ID>/opening.md
   ```

   `<L>` is the scratch folder from step 3. `--application-dir` is required: the script reads
   `application/render_report.json`, and a missing report is a rule violation. Exit 1 prints `rule:` lines naming a lens:
   re-run that one child once with the rule quoted. Still exit 1 -> `kanban_block(kind="needs_input", reason="review round <N> cannot be aggregated: <rule>")`.
   Exit 2 -> a lens block is not valid JSON or lacks a lens: re-run that child.

   Always add `--apply`: wording, spelling and positioning are yours to fix, never a reason for another round. With
   the verdict known, run it again with `--summary "<1 to 5 lines in the user's language>"` and
   `--out <P>/openings/<ID>/review-<N>.json`: it writes every soft `replace` (`applied`) into the files. Then carry
   out each `polish` instruction yourself, in the documents, without new facts. When `cv_content.json` or
   `cover_letter.md` changed, re-render with rendering-cv step 1 (and step 2 for the letter); a render defect makes it
   a FIX for the writer. The script writes nothing when a rule fails.
   When the truthfulness lens located the employer's own posting of this role on an ATS (a `source_url` with an
   excerpt that names the role) and `apply_url` in `opening.md` is another link (a LinkedIn or portal page), set it:
   `python3 "$HERMES_HOME/skills/squad-jobs/jobs-contract/scripts/apply_link.py" <P>/openings/<ID> <posting url>
   --by jobs-reviewer --source "review-<N>"` (drop any `?action=apply` or tracking query). Exit 1 means the link is
   not an employer ATS: leave `apply_url` as it is and say so in the summary.
5. `status.json`: append one history line (never rewrite earlier ones). The review's `status` field gives the value:
   `ready` on APPROVED, `not_approved` on NOT_APPROVED, `in_review` on FIX.
6. Hand off with `kanban_create`, `parents: [<your card id>]`, `workspace_kind: dir`, `workspace_path: <P>`:
   - APPROVED -> jobs (manager), `skills: [leading-job-search]`, key `jobs:application:<project>:<ID>:digest`
     (CHANGE round: `digest-c<N>`). Body: id, verdict, review path, application folder.
   - FIX (round 1 only) -> jobs-writer, `skills: [writing-applications]`, key `...:write-r2`. Body: the `corrections`
     list in order (lens, type, location, mode, and the old/new pair or the instructions), copied verbatim, plus the
     `dropped_claims` list so the writer knows which company claims were removed and why.
   - NOT_APPROVED -> no card; the summary says so.
7. `kanban_complete` with the verdict on one line.

A file that names a `profile.md` `confidential_terms` entry comes back as a correction of lens `privacy`, added by the
script itself: it blocks whatever the lens verdicts say, so the writer always gets it.

## Corrections

- `replace` when the text is quotable: `old` is an exact span that occurs once in its file; `new` is the replacement.
- `instruction` for a judgement the writer can still execute without deciding a fact (reorder, shorten a named
  bullet, remove a named sentence). Never a vague instruction such as "make it stronger".
- A concern without a fix is a warning in the review, not a correction.

## Pitfalls

- Edit documents only for wording, spelling and positioning (`applied`, `polish`), never a fact: a fact is a hard
  item for the writer. Never ask the user a detail the documents do not claim.
- Never ask jobs-writer anything. A fit fact you cannot settle from `analysis.json` goes to jobs-scout as a support
  card (jobs-contract step 5).
- A company claim whose source URL came from `opening.md` is refused by the script. Locate the company page by search
  yourself and check the claim on that page. `source_located_by_reviewer: true` is not evidence on its own: a kept claim
  also carries `source_excerpt` (at least 40 characters copied from the fetched page) or `source_file` (a captured page
  in `application/`). Without either, the script refuses it.
- A render with a hard defect or measured keyword coverage below 0.8 is a blocking ats item: the ats lens says FIX
  with a correction; a PASS beside it is refused.
- Never patch a lens block by hand to make the script pass. Re-run the lens.
- No e-mail address or phone number in any block or summary; the script refuses them.

## Verification

- `review-<N>.json` exists once, from a run that exited 0, with five lens blocks, `verdict`, `status`, `corrections`
  (each with lens, type, location and mode), `dropped_claims`, `warnings` and `summary_for_user`.
- APPROVED implies truthfulness PASS, no hard defect, market and language checks PASS.
- The next card exists once, with the key of its stage.
