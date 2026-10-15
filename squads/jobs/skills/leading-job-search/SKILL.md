---
name: leading-job-search
description: "Runs the job-search squad: interview, digests, tracking. Use when the user sets up their search, replies to a digest, pastes a job link, updates progress, or pauses or resumes the search."
---

# Leading the job search

Every kanban tool call passes `board: "jobs"`; card fields: jobs-contract step 4.

## When to Use

- A message from the user: set up the search, reply to a digest, paste a link, report progress, pause or resume.
- A card addressed to you under stage `digest`.
- The `jobs-watch` cron posts a blocked card in your Bot Chat. A digest: show it (step 4). A worker's question:
  ask the user, `kanban_comment` the literal answer, then `kanban_unblock`.
- Any change to `profile.md`, `achievements.yaml`, `contact.yaml` or `application-data.yaml`.

## Procedure

1. **Project.** One search = one Hermes Project. If it is missing, ask the user to have the builder run
   `squadctl project add jobs <name> <path>`.
2. **Interview** (first run, or when the user changes goals). Read `profile.md` if it exists, then ask at most 5
   questions per batch, required fields first, with options where possible. Write `profile.md`,
   `achievements.yaml`, `contact.yaml` and, when `auto_apply: try`, `application-data.yaml` (formats:
   skill jobs-contract, `references/profile-files.md`). Show the final YAML and change it only after the user's
   "ok". `verified: true` only on text the user confirmed. The user can add achievements later one at a time.
3. **Search.** The `jobs-search` cron files search cards (`start_search.py`) unless `profile.md` says
   `search: paused`. "search now": file the same card yourself (jobs-scout, `skills: [finding-jobs]`, body
   `Mode: SEARCH`, key `jobs:search:<project>:<YYYY-MM-DD-HH>`).
4. **Digest** (stage `digest`, a board run that cannot message the user). Read `review-N.json` and
   `analysis.json`, then `kanban_block(kind="needs_input", reason=<this message>)`; the `jobs-watch` cron posts
   it to your Bot Chat:

   ```text
   <score>/100 - <role> at <company> (<work mode>)
   Apply: <apply_url>
   CV: <absolute path of cv_ats.pdf>
   Reply: "apply", "change: <what>", "no"
   <ID>
   ```

   Add at most one warning line from `analysis.json`. Set `status.json` to `delivered`.
5. **Replies** (in Bot Chat). After acting on a reply, close its digest card:
   `kanban_complete(board: "jobs", task_id: <digest card>, summary: "<the reply>")`.
   - `apply` without jobs-applier (optional; no `jobs-applier` profile folder next to yours): answer with `apply_url`
     and the path of `answers.md`, and set `manual_application`.
   - `apply` with `auto_apply: never`: answer with the link and the manual kit path; when `kit.md` does not
     exist yet, file a jobs-applier card (`skills: [submitting-applications]`) with body `Mode: KIT`.
   - `apply` otherwise: set `applying` and file the jobs-applier card (`skills: [submitting-applications]`)
     whose body carries `Confirmed by <name>: '<their message>' (<date>)` plus ID, paths and `apply_url`. On
     wake-up: SUBMITTED -> "Applied to <company>" + the screenshot; NEEDS_DATA -> ask each question, relaunch
     with the answers, then offer to save them; NOT_POSSIBLE -> say why in one line with the link and the kit.
   - `change: <what>`: if it needs a fact that is not in `achievements.yaml`, ask for it first (a new achievement
     enters only with the user's confirmation). Then a jobs-writer card (`skills: [writing-applications]`,
     body `CHANGE` plus the request), key `jobs:application:<project>:<ID>:write-c<N>`.
   - `no`: `status.json` -> `skipped`, with the reason when given. Do not ask for one.
   - "why": 4 lines from `analysis.json` (score, two strengths, two gaps).
   - "I applied", "they called me", "rejected", "I have an interview": append the status (`applied`,
     `screening`, `interview`, `rejected`); for an interview, offer preparation.
6. **Requests.** A pasted link or "analyze this" -> jobs-scout card (`skills: [finding-jobs]`, body `Mode: URL`
   plus the links); when the analysis is REJECT or WATCH, say why in 2 lines and offer "force". "Prepare me for
   the interview with X" -> jobs-writer card with `skills: [preparing-interviews]`; deliver `interview.md` with
   the 3 key lines. "How is my search going?" -> 6 lines from the board plus the `status.json` files: found,
   delivered, applied, replies, pending. "Add this achievement" or a preference change -> show the exact diff in
   the YAML and write it after "ok".
7. **Pause / resume.** Edit `search: active|paused` in `profile.md` and confirm in one line. Structural changes
   (schedules, models, a bot, a skill) belong to the builder: say so in one line.

## Pitfalls

- Never apply, call or email anyone yourself, and never approve an application.
- An ambiguous `apply` (several delivered openings without a quote) is resolved with `clarify`, showing company
  and role as options.
- Anything researched comes from the scout's files.

## Verification

- `profile.md` and `achievements.yaml` changed only after the user's "ok".
- Every card you file names the project, the opening id, the paths and the language.
- The digest carries score, link, CV path and id, and no contact data.
- Each user reply ends with `status.json` updated, a card filed, or both.
