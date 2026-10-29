# Profile optimisation and platform research

The manager's side of `Mode: PROFILE`, `Mode: PLATFORMS`, `Mode: MARKET` and `Mode: PROFILE-APPLY`. Cards go to the
scout and the writer; the manager never browses.

## Contents

- Consent for LinkedIn
- The cards
- Presenting the result
- Applying the approved edits

## Consent for LinkedIn

`linkedin_browse` in `profile.md` (default true, asked once at onboarding) lets the scout read hiring posts, the writer
read and edit the user's own profile, and the applier use Easy Apply, all in the user's signed-in session. When it is
false, file no LinkedIn work and say so once. The user's session is set up by the builder (`shared_browser.py login`).

## The cards

One request files three cards on board `jobs`, each `workspace_kind: dir` with `workspace_path: <P>`:

| Card | Assignee and skill | Parents | Key suffix | Body |
|---|---|---|---|---|
| platforms | jobs-scout, `recommending-platforms` | none | `platforms` | `Mode: PLATFORMS`, project path, `User language` |
| market | jobs-scout, `browsing-linkedin` | platforms | `market` | `Mode: MARKET`, `Window: 168 h`, the consent line when given |
| profile | jobs-writer, `optimizing-profiles` | market | `profile` | `Mode: PROFILE`, the platform the user named or `default` |

Keys are `jobs:profile:<project>:<YYYY-MM-DD>:<suffix>`. "Which job sites fit my place?" alone files only the platforms
card. "Scan the market" alone files platforms (when no file from the last 90 days exists) and market. A pasted profile
text goes to `<P>/documents/linkedin/` first, after the user's ok.

## Emerging roles

The market card's `offer_positioning` names role families the user's own work fits but `profile.md` does not name
(an emerging one first). Offer each once, in one line with its one-sentence definition from `role_families.json` and
the postings count: "your work fits Forward Deployed Engineer (N postings this week): position you as one?". A yes
adds it to `positioning_titles` and its titles to `search_keywords` at once, no further question; the next profile
and CV use it. An `unmapped title` the scout reports twice: look it up (`web_search`, the employers' own postings),
and when its definition fits the user's work, offer it the same way and ask the builder to add the family upstream.

## Presenting the result

A card with `Mode: PROFILE-PRESENT` carries the writer's file paths, and the writer's checks have already passed. Read
the audit and those files; never rerun or look for the writer's scripts, which live in the writer's profile. Then
`kanban_block(kind="needs_input", reason=<message>)` in `user_language`: the platforms list (top three, and any the user
must search by hand), the three biggest profile changes, the keyword gaps (terms the market wants that the user has not
declared, with "tell me if you do have it" so a real skill can enter `achievements.yaml` after their ok), and the paths of
`profiles/<platform>.md` to paste. Say plainly that nothing was sent to any platform.

## Applying the approved edits

Show the final copy once, all fields in one message, and ask one question: "apply all, or name the fields to leave
out". A correction the user gives instead is applied by the writer (CHANGE card) and the new copy goes straight to
apply when it only carries that correction. Only the approved fields go into `<P>/profiles/approved.json`; the card body says that file wins over any earlier
diff, so a wording fix made after the review is not reverted.

The platform is watched: the apply card asks for one field at a time with normal pauses, and when the platform caps
changes per session the writer applies what fits and reports the rest. Never promise the user that automation is
invisible. Structure edits (a title, the dates, a new position or school, a deletion) are `structure` rows in the
approved file: the audit's structure rows enter it at the user's yes, and the writer fills those forms with its script.
Then file a jobs-writer card (`skills: [optimizing-profiles]`, body `Mode: PROFILE-APPLY` and that path, key
`jobs:profile:<project>:<YYYY-MM-DD>:apply`). Report the writer's verify result in one line per field: applied, or
failed with the reason. The top-skill pins follow the approved `skills` list. Photo, banner, custom URL, Featured
and Open to Work are the user's to set.

A paste-kit platform (Upwork: its terms ban bots on an account) has no apply card. After the user's yes, write
`<P>/profiles/approved-<platform>.json` and ask the user to paste the fields, then to open the profile, expand every
"more", copy the whole page and paste it into the chat. Save it as `<P>/profiles/<platform>-page-<YYYY-MM-DD>.txt`
and file a jobs-writer card (`Mode: PROFILE-VERIFY`, both paths); report its result in one line per field.

The copy check runs with `--structure` whenever the structure file exists: without it a right draft for a role those
rows rename or create fails as `role_not_covered` / `unknown_role` and reads as a bad draft.
