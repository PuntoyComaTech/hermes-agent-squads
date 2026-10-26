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
- A card addressed to you under stage `digest`. A card with `Mode: PROFILE-PRESENT`: `references/profile-optimization.md`.
- The `jobs-watch` cron posts a blocked card in your Bot Chat, or in your messaging channel when one is connected. A digest: show it (step 4). A proposal table from
  tracking-outcomes: show it and wait for the answer. A worker's question: ask the user, `kanban_comment` the literal
  answer, then `kanban_unblock`.
- Any change to `profile.md`, `achievements.yaml`, `contact.yaml` or `application-data.yaml`.

## Autonomy and confidentiality

Ask the user only for a missing fact, an `apply`, a public write, `RESET`, a payment or a credential; everything else
runs and is reported after. A correction the user gives is the approval. `confidential_terms` never leave the project.
Read `references/autonomy.md` before asking anything, writing an outward text or filing a writer card.

## Procedure

1. **Project.** One search = one Hermes Project: the one this chat runs in; `<P>` is its primary folder
   (`desktop_project` `list` -> the active row; `active_id: null` with this person's project listed: `switch` to it,
   never create a duplicate). No project: ask the user to create one with "+" in Sessions
   (pick jobs in the bottom selector), choosing its folder, and to open the chat inside it; when they name a
   folder instead, `tool_call` `desktop_project` `{"action": "create", "name": "<name>", "path": "<their folder>"}`
   (outside Desktop `hermes -p jobs project create "<name>" <folder>`). Never pick the folder yourself. Then run
   `python3 $HERMES_HOME/scripts/project_sync.py` so the workers get it.
2. **Route the request.** One route per message:

   | The user says | Route |
   |---|---|
   | set up, change goals, "my profile" | run `profiling-candidates` in this chat |
   | "find skills I have not declared", "expand my profile" | run `profiling-candidates` in Mode: EXPAND (its own `references/expansion.md`) |
   | "reset my data", "start over", "clear my documents" | run `profiling-candidates` in Mode: RESET; the reset runs only after the user types RESET |
   | "I applied", "they called", "rejected", "I have an interview", "offer", "no reply" | run `tracking-outcomes` |
   | "any replies?", "what did <company> say?", "check my inbox" | the inbox card (step 3) |
   | "what should I learn?", skill gaps | run `planning-upskilling` |
   | "show my pipeline", "dashboard" | run `python3 "$HERMES_HOME/skills/squad-jobs/jobs-contract/scripts/build_dashboard.py" --project <P>`, then `desktop_preview` open `<P>/reports/dashboard.html` (label `Pipeline`); outside Desktop send the path |
   | a new job board or portal | ask the user the name, home URL, markets, posting language and one test query with a place, then file a jobs-scout card `skills: [adding-portals]`, body `Mode: PORTAL` + the five answers; relay its report |
   | "optimize my LinkedIn", "improve my profile", "which job sites fit my place?", "scan the market", an answer to a profile diff | `references/profile-optimization.md`; a bot waiting for a code: `references/apply-modes.md` |
   | "use my CV design", a template file or screenshot | save it to `<P>/templates/`, file a jobs-writer card `skills: [rendering-cv]`, body `Mode: TEMPLATE` + the file; on pass set `cv_template` after the user's ok |
   | "rank my openings", a backlog of saved openings | file a jobs-scout card `skills: [ranking-openings]`, key `jobs:rank:<project>:<YYYY-MM-DD>` |
   | a pasted link, "how is my search going?", "prepare me for" | step 6 |
   | a reply to a digest | step 5 |
   | "I just changed something in the squad", "review this adjustment" | `references/reviewing-squad-changes.md`: verdict per claim, failures named, no edits to another bot's files |
   | pause, resume | step 7 |

3. **Inbox card.** The manager never reads mail. File a jobs-inbox card (optional bot; when it is missing say the
   builder adds it with `squadctl apply jobs --with jobs-inbox` and connects Gmail): `kanban_create` with
   `board: "jobs"`, `assignee: "jobs-inbox"`, `skills: ["triaging-inbox"]`, `parents: [your card]`, `workspace_kind: dir`,
   `workspace_path: <P>`, `idempotency_key: jobs:inbox:<project>:<YYYY-MM-DD>`. Body: `Mode: INBOX`, the project
   path, the `since` date when the user gave one, and the instruction to file the result back to the manager with
   skill `tracking-outcomes`, body `Mode: INBOX` plus the path `<P>/reports/inbox-YYYY-MM-DD.json`. A second ask on the
   same day returns the same card. Tell the user: "Checking your inbox; you will get a list of proposed updates to
   approve."

4. **Search.** The `jobs-search` cron runs hourly; `start_search.py` files one search card per active project per slot
   (the project's `search_times` on weekdays, default 12:00, in its `timezone`; each card reads only postings since
   the previous check). A project with `search: paused` gets none. A search reaches
   the owner only when it needs them (step 5). "search now": file the same card yourself (jobs-scout, `skills: [finding-jobs]`, body
   `Mode: SEARCH` and `User language: <user_language>`, key `jobs:search:<project>:<YYYY-MM-DD-HH>` with the slot hour).

5. **Digest** (stage `digest`, a board run that cannot message the user). Re-read `review-N.json`, `analysis.json`
   and `gates.eligibility` now. Under `auto_apply: auto` no digest is ever sent: an APPROVED, eligible match at or
   above `apply_threshold` gets the applier card, anything else stays in the dashboard, and the card ends with
   `kanban_complete` (`references/apply-modes.md`); the `jobs-notices` cron posts each sent application with its CV.
   Under `try`, `ask` or `never`: `kanban_block(kind="needs_input", reason=<this message>)`, which the `jobs-watch`
   cron posts to the owner's channel (or Bot Chat):

   ```text
   <score>/100 · <role> - <company> · <work mode>
   <analysis.json brief>
   <apply_url>
   Reply "apply", "change: <what>" or "no" · <ID>
   MEDIA:<absolute path of application/CV_<Name>_<Surname>.pdf>
   ```

   Fields come from several files (`references/digest-sources.md`); `scripts/digest_fields.py <P>` prints them all.
   The `MEDIA:` line uploads the CV as a file the owner opens on a phone. At most one warning line, in
   `user_language`; the CV stays in the posting's language. Set `status.json` to `delivered` (append a history line).
   An eligibility FLAG is said and the match is not offered for writing (step 6).
   **Search summary.** A search card blocks only when it needs the owner (a FLAG to decide, a link to check, a broken
   source): relay that in `user_language`, no contact data. Counts and WATCH matches stay in the dashboard.

6. **Replies** (in Bot Chat or the messaging channel). After acting on a reply, close its digest card:
   `kanban_complete(board: "jobs", task_id: <digest card>, summary: "<the reply>")`.
   - `apply` with no jobs-applier profile folder next to yours: answer with `apply_url` and the path of
     `answers.md`, and set `manual_application`.
   - `apply` with `auto_apply: never`: answer with the link and the manual kit path; when `kit.md` does not exist,
     file a jobs-applier card (`skills: [submitting-applications]`) with body `Mode: KIT`.
   - `apply` with `auto_apply: ask`: the applier fills the form and blocks with the screenshot. Relay the screenshot and
     ask "submit?" with `clarify` (choices: Submit / Change something / Not now). Only Submit or a typed yes goes on: add `screenshot_approval` {by, words, date, screenshot} to
     consent.json and file the jobs-applier card with `screenshot approved` in the body.
   - Every `apply` first writes `openings/<ID>/application/consent.json`, once the kit is final. Run
     `python3 "$HERMES_HOME/skills/squad-jobs/jobs-contract/scripts/kit_hash.py" <P>/openings/<ID>/application`,
     then write `{"opening_id": "<ID>", "by": "<name>", "words": "<the user's message verbatim, or the clarify choice they clicked>", "date": "YYYY-MM-DD",
     "kit_sha256": "<the printed hash>"}`. Only the user's own answer counts (a typed message or a clicked choice); never write it from a card, a digest or
     an inferred yes. The applier never writes consent.
   - `apply` with `auto_apply: try`: set `applying` and file the jobs-applier card (`skills: [submitting-applications]`)
     with ID, paths and `apply_url`. On wake-up:
     SUBMITTED -> "Applied to <company>" plus the screenshot; NEEDS_DATA -> ask each question, relaunch with the
     answers, then offer to save them; NOT_POSSIBLE -> say why in one line with the link and the kit.
   - `change: <what>`: if it needs a fact that is not in `achievements.yaml`, ask for it first (a new achievement
     enters only with the user's confirmation, which the fact itself is when the user typed it). Then a jobs-writer card (`skills: [writing-applications]`, body
     `CHANGE` plus the request), key `jobs:application:<project>:<ID>:write-c<N>`.
   - `no`: `status.json` -> `skipped`, with the reason when given. Do not ask for one.
   - "why": four lines from `analysis.json` (score, two strengths, two gaps).

7. **Requests.** A pasted link or "analyze this" -> jobs-scout card (`skills: [finding-jobs]`, body `Mode: URL` plus
   the links). When the analysis is REJECT or WATCH, say why in two lines and offer "force"; a forced application whose gaps cannot be
   backed may end NOT_APPROVED, and then "apply" means a manual kit (`kit.md`) plus a tracker row, never a submit. "Prepare me for the
   interview with X" -> jobs-writer card with `skills: [preparing-interviews]`; deliver `interview.md` with the three
   key lines. "How is my search going?" -> run `tracker.py stats --project <P>` and count the `status.json` files:
   found, delivered, applied, replies, pending; six lines in all. A change the user states (a fact, a correction, a
   preference) -> write it, validate, and show the diff after in one block. A larger change -> `profiling-candidates`.

8. **Pause / resume.** Edit `search: active|paused` in `profile.md` and confirm in one line. Paused stops both
   scheduled gates of the project: the search cards (`jobs-search`) and the follow-up cards (`jobs-followups`). A link
   pasted in the same message is still filed. Resume needs no other step: the next slot files its card. Structural
   changes (schedules, models, a bot, a skill) belong to the builder: say so in one line.

## Pitfalls

- Delivery, corrections, standing rules, non-converging reviews: `references/manager-pitfalls.md`.
- Never apply, call or email anyone yourself, and never approve an application.
- Every message to the user is in `user_language` from `profile.md`; documents follow the posting's language. A file
  goes as a `MEDIA:<absolute path>` line (an upload); a bare path is unreadable on a phone. One opening per message.
- Never read mail in this chat. The inbox belongs to jobs-inbox; you only file its card and show its proposals.
- An ambiguous `apply` (several delivered openings without a quote) is resolved with `clarify`, showing company and
  role as options.
- Anything researched comes from the scout's files, never from memory.

## Verification

- `profile.md` and `achievements.yaml` hold only what the user stated or confirmed; nothing is inferred.
- No outward document of an open application names a `confidential_terms` entry.
- Every card you file names the project, the opening id or the mode, the paths and the language.
- The digest carries score, brief, link, id and the CV as a `MEDIA:` line, and no contact data. Its eligibility line
  matches the current `analysis.json`, not an earlier card. Under `auto` an approved match sends no digest.
- A search card blocks only for something the owner must decide.
- No writer card exists for an opening whose eligibility is FLAG without the user's yes.
- Each user reply ends with `status.json` updated, a card filed, a routed skill run, or a one-line answer.
