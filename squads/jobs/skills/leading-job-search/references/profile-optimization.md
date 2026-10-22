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

## Presenting the result

A card with `Mode: PROFILE-PRESENT` carries the writer's file paths. Read the audit, then
`kanban_block(kind="needs_input", reason=<message>)` in `user_language`: the platforms list (top three, and any the user
must search by hand), the three biggest profile changes, the keyword gaps (terms the market wants that the user has not
declared, with "tell me if you do have it" so a real skill can enter `achievements.yaml` after their ok), and the paths of
`profiles/<platform>.md` to paste. Say plainly that nothing was sent to any platform.

## Applying the approved edits

Show the writer's diff (`profile_diff.py` output: field, before, after) and ask which fields to apply. Only what the
user approves goes into `<P>/profiles/approved.json`. Then file a jobs-writer card (`skills: [optimizing-profiles]`,
body `Mode: PROFILE-APPLY` and that path, key `jobs:profile:<project>:<YYYY-MM-DD>:apply`). Report the writer's verify
result in one line per field: applied, or failed with the reason. Settings (Open to Work, custom URL) stay the user's.
