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
2. Start five `delegate_task` children in parallel, one per lens, in one call. Each gets its section of
   `references/lenses.md` as the goal, the files that lens names as context, and as its `output_schema` the exact
   JSON that `python3 "$HERMES_HOME/skills/squad-jobs/reviewing-applications/scripts/aggregate_review.py" --schema
   <lens>` prints, never a shorter one written by hand: Hermes checks the child's answer against it and gives the
   child one correction turn, so a block with wrong field names (`claim`/`issue` for `text`/`problem`) is fixed before
   it reaches you. Children never read the card and never write files. Only the truthfulness child searches the web,
   and only for company claims; the other children are told not to search. The run may spawn up to
   `delegation.oneshot_max_children` children in total (12 in this squad): five lenses plus re-runs.
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
   re-run that one child once with the rule quoted and the same `--schema` output. Still exit 1, or no child left to
   spawn: `kanban_block(kind="transient", reason="review round <N> cannot be aggregated: <rule>")`: a lens that broke
   the contract is a retry, never a question for the user. Exit 2 -> a lens block is not valid JSON or lacks a lens:
   re-run that child.
   **One round names every instance.** Each wrong claim (a truthfulness draft finding, an unanswerable stretch)
   carries `claim_terms`, the 1 to 4 words it ties together (`["Python", "FastAPI", "AI"]`). The script lists every
   sentence in the CV, letter, recruiter message and answers that makes the same claim (`instances`) and adds one hard
   correction for the instances no correction rewrites and the finding's `true_instances` (sentences the record
   supports) does not list. Before the `--out` run, turn each into a `replace` correction or a `true_instances` entry.
   The script also blocks, whatever the lenses say, a sentence saying the user works remotely now when no current
   experience in `achievements.yaml` records `work_mode: remote`, and an ILR/LinkedIn language label above the
   declared CEFR level ("Professional Working Proficiency" for a B2, notes included).

   Always add `--apply`: wording, spelling and positioning are yours to fix, never a reason for another round. With
   the verdict known, run it again with `--summary "<1 to 5 lines in the user's language>"` and
   `--out <P>/openings/<ID>/review-<N>.json`: it writes every soft `replace` (`applied`) into the files. Then carry
   out each `polish` instruction yourself, in the documents, without new facts. When `cv_content.json` or
   `cover_letter.md` changed, re-render with rendering-cv step 1 (and step 2 for the letter); a render defect makes it
   a FIX for the writer. The script writes nothing when a rule fails.
   **The reviewed posting is the apply link.** When the truthfulness lens checked the role on the employer's own
   requisition (an ATS posting, in the user's country when the role is posted for several cities) and `apply_url` in
   `opening.md` is any other link (LinkedIn, an aggregator, another city's requisition), add `--posting-url <that
   requisition>` (no `?action=apply`, no tracking query) to both runs: with `--out` it becomes `apply_url` (through
   `apply_link.py`) and the review records it, so the digest and the applier read the link you verified. An APPROVED
   verdict is refused while `apply_url` is an aggregator, a job board or an unknown host and no `--posting-url` is
   given. A correction inside internal text (a NOTE TO SELF, a heading, anything in `answers.md` outside [FIELD]
   blocks, `strategy.md`, `kit.md`) is applied in place and never decides the verdict: no employer reads it.
   `application/form_questions.json` (written by the writer) is read too: a required free-text question without its
   own [FIELD] in `answers.md` is a hard correction, so the kit is complete before it reaches the applier.
5. `status.json`: append one history line (never rewrite earlier ones). The review's `status` field gives the value:
   `ready` on APPROVED, `not_approved` on NOT_APPROVED, `in_review` on FIX.
6. Hand off with `kanban_create`, `parents: [<your card id>]`, `workspace_kind: dir`, `workspace_path: <P>`:
   - APPROVED -> jobs (manager), `skills: [leading-job-search]`, key from
     `python3 "$HERMES_HOME/skills/squad-jobs/jobs-contract/scripts/card_key.py" application <project slug> <ID> digest`
     (CHANGE round: stage `digest-c<N>`). A key never carries the project path. Body: id, verdict, review path, application folder.
   - FIX (round 1 only) -> jobs-writer, `skills: [writing-applications]`, key `...:write-r2`. Body: the `corrections`
     list in order (lens, type, location, mode, and the old/new pair or the instructions), copied verbatim, plus the
     `dropped_claims` list so the writer knows which company claims were removed and why.
   - NOT_APPROVED -> no card; the summary says so.
7. Teach the writer. For each correction whose defect you already corrected in another opening (your memory, an
   earlier `review-N.json`), run `python3 "$HERMES_HOME/skills/squad-jobs/jobs-contract/scripts/lessons.py" add
   --project <P> --source <ID> --text "<the rule the writer follows instead, one line>"`. The writer reads
   `writing-lessons.md` before every draft; your memory alone never reaches it. A full list: merge two lines in the
   file, then add again.
8. `kanban_complete` with the verdict on one line.

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
- An earlier review that approved a sentence is not evidence for it: each round grounds every claim again. A fact
  the user's search preferences state (profile.md `work_mode`, `career_goals`) is never a fact about the current job.
- No e-mail address or phone number in any block or summary; the script refuses them.

## Verification

- `review-<N>.json` exists once, from a run that exited 0, with five lens blocks, `verdict`, `status`, `corrections`
  (each with lens, type, location and mode), `dropped_claims`, `warnings` and `summary_for_user`.
- APPROVED implies truthfulness PASS, no hard defect, market and language checks PASS.
- The next card exists once, with the key of its stage.
