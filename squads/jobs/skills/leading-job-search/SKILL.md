---
name: leading-job-search
description: "Routes and runs the job-search squad as manager. Use when the user sets up, replies to a digest, pastes a link, asks for replies or the pipeline, or pauses the search."
---

# Leading the job search

Every kanban tool call passes `board: "jobs"`; card fields: jobs-contract step 4. Scripts live under
`$HERMES_HOME/skills/squad-jobs/<skill>/scripts/`.

## When to Use

- A message from the user: set up, reply to a digest, paste a link, ask about replies or the pipeline, report an
  outcome, ask what to learn, pause or resume.
- A card addressed to you under stage `digest`.
- The `jobs-watch` cron posts a blocked card in your Bot Chat. A digest: show it (step 4). A proposal table from
  tracking-outcomes: show it and wait for the answer. A worker's question: ask the user, `kanban_comment` the literal
  answer, then `kanban_unblock`.
- Any change to `profile.md`, `achievements.yaml`, `contact.yaml` or `application-data.yaml`.

## Procedure

1. **Project.** One search = one Hermes Project. If it is missing: create `~/Projects/jobs/<name>` (never the home
   root or a profile directory), then `tool_describe` and `tool_call` `desktop_project` with
   `{"action": "create", "name": "<name>", "path": "<folder>"}`. Outside Desktop run
   `hermes -p jobs project create "<name>" <folder>`. Then run `python3 $HERMES_HOME/scripts/project_sync.py` so the
   workers get it, and tell the user once: "Sessions: pick jobs in the bottom selector to see its searches; + creates
   another."
2. **Route the request.** One route per message:

   | The user says | Route |
   |---|---|
   | set up, change goals, "my profile" | run `profiling-candidates` in this chat |
   | "find skills I have not declared", "expand my profile" | run `profiling-candidates` in Mode: EXPAND (`references/expansion.md`) |
   | "reset my data", "start over", "clear my documents" | run `profiling-candidates` in Mode: RESET; the reset runs only after the user types RESET |
   | "I applied", "they called", "rejected", "I have an interview", "offer", "no reply" | run `tracking-outcomes` |
   | "any replies?", "what did <company> say?", "check my inbox" | the inbox card (step 3) |
   | "what should I learn?", skill gaps | run `planning-upskilling` |
   | "show my pipeline", "dashboard" | run `python3 "$HERMES_HOME/skills/squad-jobs/jobs-contract/scripts/build_dashboard.py" --project <P>` and send the path |
   | a new job board or portal | run `adding-portals` |
   | "use my CV design", a template file or screenshot | save it to `<P>/templates/`, file a jobs-writer card `skills: [rendering-cv]`, body `Mode: TEMPLATE` + the file; on pass set `cv_template` after the user's ok |
   | "rank my openings", a backlog of saved openings | file a jobs-scout card `skills: [ranking-openings]`, key `jobs:rank:<project>:<YYYY-MM-DD>` |
   | a pasted link, "how is my search going?", "prepare me for" | step 6 |
   | a reply to a digest | step 5 |
   | pause, resume | step 7 |

3. **Inbox card.** The manager never reads mail. File a jobs-writer card: `kanban_create` with `board: "jobs"`,
   `assignee: "jobs-writer"`, `skills: ["triaging-inbox"]`, `parents: [your card]`, `workspace_kind: dir`,
   `workspace_path: <P>`, `idempotency_key: jobs:inbox:<project>:<YYYY-MM-DD>`. Body: `Mode: INBOX`, the project
   path, the `since` date when the user gave one, and the instruction to file the result back to the manager with
   skill `tracking-outcomes`, body `Mode: INBOX` plus the path `<P>/reports/inbox-YYYY-MM-DD.json`. A second ask on the
   same day returns the same card. Tell the user: "Checking your inbox; you will get a list of proposed updates to
   approve."

4. **Search.** The `jobs-search` cron runs hourly; `start_search.py` files one search card per active project per slot
   (08:00 on weekdays, in the project's `timezone`). A project with `search: paused` gets none. Every search ends with
   the summary of step 5. "search now": file the same card yourself (jobs-scout, `skills: [finding-jobs]`, body
   `Mode: SEARCH` and `User language: <user_language>`, key `jobs:search:<project>:<YYYY-MM-DD-HH>` with the slot hour).

5. **Digest** (stage `digest`, a board run that cannot message the user). Read `review-N.json` and `analysis.json`,
   then `kanban_block(kind="needs_input", reason=<this message>)`; the `jobs-watch` cron posts it to your Bot Chat:

   ```text
   <score>/100 - <role> at <company> (<work mode>)
   Apply: <apply_url>
   CV: <absolute path of cv_ats.pdf>
   Reply: "apply", "change: <what>", "no"
   <ID>
   ```

   Add at most one warning line from `analysis.json`. Set `status.json` to `delivered`.
   Build the digest at digest time, not from an earlier card: re-read `analysis.json` and the eligibility result
   (`gates.eligibility`). An eligibility FLAG is said in the digest and the match is not offered for writing (step 6).
   Write the digest in `user_language`; the CV and letter stay in the posting's language.

   **Search summary.** Each search card ends with one summary block from the scout (`kanban_block`, kind `needs_input`,
   reason starting "Search"), also when nothing is PASS. Show it in `user_language`: counts (found, PASS, FLAG, DISCARD,
   new), the top WATCH with its score and one line of reason, and what needs the user (a FLAG to decide, a link to
   check). Contact data never appears in it.

6. **Replies** (in Bot Chat). After acting on a reply, close its digest card:
   `kanban_complete(board: "jobs", task_id: <digest card>, summary: "<the reply>")`.
   - `apply` with no jobs-applier profile folder next to yours: answer with `apply_url` and the path of
     `answers.md`, and set `manual_application`.
   - `apply` with `auto_apply: never`: answer with the link and the manual kit path; when `kit.md` does not exist,
     file a jobs-applier card (`skills: [submitting-applications]`) with body `Mode: KIT`.
   - `apply` with `auto_apply: ask`: the applier fills the form and blocks with the screenshot. Relay the screenshot and
     ask "submit?". Only an explicit yes goes on: add `screenshot_approval` {by, words, date, screenshot} to
     consent.json and file the jobs-applier card with `screenshot approved` in the body.
   - Every `apply` first writes `openings/<ID>/application/consent.json`, once the kit is final. Run
     `python3 "$HERMES_HOME/skills/squad-jobs/submitting-applications/scripts/check_submission.py" --kit-hash <P>/openings/<ID>/application`,
     then write `{"opening_id": "<ID>", "by": "<name>", "words": "<the user's message, verbatim>", "date": "YYYY-MM-DD",
     "kit_sha256": "<the printed hash>"}`. Only the user's own words count; never write it from a card, a digest or an
     inferred yes. The applier never writes consent.
   - `apply` with `auto_apply: try`: set `applying` and file the jobs-applier card (`skills: [submitting-applications]`)
     with ID, paths and `apply_url`. On wake-up:
     SUBMITTED -> "Applied to <company>" plus the screenshot; NEEDS_DATA -> ask each question, relaunch with the
     answers, then offer to save them; NOT_POSSIBLE -> say why in one line with the link and the kit.
   - `change: <what>`: if it needs a fact that is not in `achievements.yaml`, ask for it first (a new achievement
     enters only with the user's confirmation). Then a jobs-writer card (`skills: [writing-applications]`, body
     `CHANGE` plus the request), key `jobs:application:<project>:<ID>:write-c<N>`.
   - `no`: `status.json` -> `skipped`, with the reason when given. Do not ask for one.
   - "why": four lines from `analysis.json` (score, two strengths, two gaps).

7. **Requests.** A pasted link or "analyze this" -> jobs-scout card (`skills: [finding-jobs]`, body `Mode: URL` plus
   the links). When the analysis is REJECT or WATCH, say why in two lines and offer "force". "Prepare me for the
   interview with X" -> jobs-writer card with `skills: [preparing-interviews]`; deliver `interview.md` with the three
   key lines. "How is my search going?" -> run `tracker.py stats --project <P>` and count the `status.json` files:
   found, delivered, applied, replies, pending; six lines in all. A single achievement or preference change -> show the
   exact diff in the YAML and write it after "ok". A larger change -> `profiling-candidates`.

8. **Pause / resume.** Edit `search: active|paused` in `profile.md` and confirm in one line. Paused stops both
   scheduled gates of the project: the search cards (`jobs-search`) and the follow-up cards (`jobs-followups`). A link
   pasted in the same message is still filed. Resume needs no other step: the next slot files its card. Structural
   changes (schedules, models, a bot, a skill) belong to the builder: say so in one line.

## Eligibility before a writer card

A jobs-writer card for an opening is filed only when its eligibility gate is PASS, or the user accepted the risk.

- PASS: file it.
- FLAG: say the eligibility note from `analysis.json` in one line and ask: "Eligibility is unclear: <note>. Write
  anyway, or skip?". File the card only after a yes, and its body then carries `Eligibility risk accepted by the user
  (<date>)`. A FLAG is resolved when the user gives the fact (a permit, a residency) and `eligibility` in `profile.md`
  is updated after their ok.
- DISCARD: file nothing; say why in one line.

## Pitfalls

- Never apply, call or email anyone yourself, and never approve an application.
- Every message to the user (digest, search summary, block reason, pause confirmation) is in `user_language` from
  `profile.md`. Documents follow the posting's language.
- Never read mail in this chat. The inbox belongs to jobs-writer; you only file its card and show its proposals.
- An ambiguous `apply` (several delivered openings without a quote) is resolved with `clarify`, showing company and
  role as options.
- Anything researched comes from the scout's files, never from memory.

## Verification

- `profile.md` and `achievements.yaml` changed only after the user's "ok".
- Every card you file names the project, the opening id or the mode, the paths and the language.
- The digest carries score, link, CV path and id, and no contact data. Its eligibility line matches the current
  `analysis.json`, not an earlier card.
- Every search ends with a summary in `user_language`, with 0 PASS included.
- No writer card exists for an opening whose eligibility is FLAG without the user's yes.
- Each user reply ends with `status.json` updated, a card filed, a routed skill run, or a one-line answer.
