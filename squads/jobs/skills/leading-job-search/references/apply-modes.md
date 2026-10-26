# Apply modes and verification codes

## Contents

- Auto
- Try, ask, never
- Verification codes

## Auto

`auto_apply: auto` in `profile.md` is the user's standing yes (`auto_apply_since`, `daily_apply_cap`,
`daily_easy_apply_cap`). No digest reply is awaited, and the owner's channel gets only two kinds of message: a sent
application (the `jobs-notices` cron, CV attached) and a question the squad cannot answer from the project files.

1. At the digest stage, when the review is APPROVED, `gates.eligibility` is PASS and `fit.score` is at or above
   `apply_threshold`: set `applying` and file the jobs-applier card (`skills: [submitting-applications]`, key
   `jobs:application:<project>:<ID>:apply`) with the ID, the paths and the `apply:` line `scripts/digest_fields.py <P>`
   prints (the reviewed posting, else `opening.md` `apply_url`): never a URL copied from the opening body or a note. No `consent.json`. Then
   `kanban_complete` the digest card: no block, no message.
2. Below the threshold, WATCH or NOT_APPROVED: no message; the opening stays in the project files. The owner finds
   it by asking "show my pipeline" (`scripts/digest_fields.py` lists every opening with its id, verdict and score),
   then "force <ID>". The one question auto mode asks before a send is an eligibility FLAG: the scout blocks with one
   line (`<role> - <company>: <eligibility note>. Do you qualify?`), because only the owner knows the fact; the answer
   goes into `eligibility` in `profile.md` and settles every later posting of that kind. An unverified link, a FLAG
   on any other gate and a cap are never asked: they stay in the files.
3. The applier's result:
   - SUBMITTED: say nothing. `record_submission.py` wrote `applied`, and `jobs-notices` posts it with its CV.
   - NEEDS_DATA: one message with every question of that form (never a guess), then relaunch with the answers and
     save them in `application-data.yaml` so no later form asks again.
   - NOT_POSSIBLE (an account, a CAPTCHA, an unverified link): no message; `kit.md` and the dashboard keep it.
   - `daily_cap` (the applier completed with "goes tomorrow"): say nothing; the next day's search applies it.
4. A reply about a sent application ("change the CV for the next ones", "that one was wrong") is a preference or an
   achievement change (step 7 of the skill), applied to the next applications; a sent form is never resent.
5. Never write `auto_apply: auto` yourself: only after the user said yes in this chat, with today's date in
   `auto_apply_since` and the caps as asked (defaults 10 and 5), shown as a one-line diff first.

## Try, ask, never

As in step 6 of the skill: the manager asks with `clarify` when the user reads the digest, and the user's own answer (typed or the choice they clicked) writes `consent.json`.

## Verification codes

A card from another bot says a site mailed the user a code and gives the site and a window in minutes. File a
jobs-inbox card (`skills: [triaging-inbox]`, body `Mode: CODE`, the site domain and the window, key
`jobs:code:<ID>:<n>`) and make the asker's card its child (`kanban_link`): the code reaches the asker as the parent's
result. Never copy the code into a comment, a message to the user or memory.
