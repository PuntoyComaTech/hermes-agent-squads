# Apply modes and verification codes

## Contents

- Auto
- Try, ask, never
- Verification codes

## Auto

`auto_apply: auto` in `profile.md` is the user's standing yes (`auto_apply_since`, `daily_apply_cap`,
`daily_easy_apply_cap`). No digest reply is awaited.

1. At the digest stage, when the review is APPROVED, `gates.eligibility` is PASS and `fit.score` is at or above
   `apply_threshold`: set `applying` and file the jobs-applier card (`skills: [submitting-applications]`, key
   `jobs:application:<project>:<ID>:apply`) with the ID, the paths and `apply_url`. No `consent.json`.
2. Below the threshold, or eligibility FLAG: send the digest as under `try` and wait for the user.
3. The applier's result decides the message, in `user_language`, one block per opening:
   - SUBMITTED: `Applied: <role> at <company>. CV: <cv_ats.pdf path>. Link: <apply_url>.`
   - NEEDS_DATA: ask each question; relaunch with the answers and offer to save them in `application-data.yaml`.
   - NOT_POSSIBLE: the reason in one line, the link and the kit path.
   - `daily_cap` (the applier completed with "goes tomorrow"): say nothing; the next day's search applies it.
4. Never write `auto_apply: auto` yourself: only after the user said yes in this chat, with today's date in
   `auto_apply_since` and the caps as asked (defaults 10 and 5), shown as a one-line diff first.

## Try, ask, never

As in step 6 of the skill: the digest asks, and the user's own words write `consent.json`.

## Verification codes

A card from another bot says a site mailed the user a code and gives the site and a window in minutes. File a
jobs-inbox card (`skills: [triaging-inbox]`, body `Mode: CODE`, the site domain and the window, key
`jobs:code:<ID>:<n>`) and make the asker's card its child (`kanban_link`): the code reaches the asker as the parent's
result. Never copy the code into a comment, a message to the user or memory.
