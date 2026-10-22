# Bot Mode and Desktop

## Bot Mode

- Bot Mode turns profiles into bots with titles and avatars; each bot has one canonical session titled
  exactly `Bot Chat`.
- The `ui_meta: {hermes-bots: ...}` block in a profile's `profile.yaml` is the "Bot-Mode-managed"
  marker; the gate scans every profile, so one marked profile marks the install. No Hermes CLI command
  writes it; squad tooling writes it on every bot it applies.
- A session gets the bot messaging protocol and `message_agent` only when both hold: its title is
  exactly `Bot Chat`, and the install is Bot-Mode-managed. `agent.bot_mode_protocol` (default true) is
  the master switch. Headless, open the chat with `hermes -p <bot> chat -c "Bot Chat"
  --create-if-missing`.
- In a Bot Chat, `/new` and `/reset` become `/compact`; archiving it retires it and the next open
  starts a new one; the idle auto-archive never retires it.

## Bots pane and ui_meta

- The Bots pane owns the roster: bot rows, creation, group chats, sections and hiding.
- `ui_meta` fields the Desktop reads: `title`, `description`, `hidden`, `pinned`, `sectionId`,
  `sectionName`, `color`, `image`, `imageKind`, `shape`, `group`, `groups`, `screenAutoOpen`,
  `custom`.
- Hidden bots keep working (dispatch, routines, @mentions, group memberships) but stay out of the
  roster; the eye toggle in the pane header shows them dimmed.
- Section membership lives on each bot (`sectionId`, `sectionName`); deleting a section returns its
  bots to Unassigned and deletes none.
- Squad tooling writes `title`, `hidden` and the section from the manifest's `section:`. How it
  writes: `soul-and-context-files.md` -> profile.yaml and ui_meta.
- Warm Bot Backends (Settings -> Advanced, default 3) caps how many local bots run at once; idle ones
  are reaped after 10 minutes, and a bot opened while every slot is busy fails after 30 s. Raise it
  for squads with many bots active at the same time.

## Routines

- A bot's routines are ordinary cron jobs named `[bot:<name>] <routine>`; they appear in
  `hermes cron list` and their runs land in the bot's chat history.

## Profile rail

- The profile rail lists every profile of the gateway; "Hide Bot" affects the Bots roster only.
- When profiles plus other agents exceed 13 entries the rail condenses into a dropdown
  (`PROFILE_DROPDOWN_THRESHOLD` in `apps/desktop/src/app/chat/sidebar/profile-switcher.tsx`).
- "Toggle profile rail" (`view.toggleProfileRail`) hides it.

## Kanban plugin

- The Desktop Kanban plugin ships disabled (`defaultEnabled: false`); enable it under Capabilities to
  see boards.
- The kanban dispatcher runs in the gateway regardless of the plugin (`kanban.dispatch_in_gateway`).

## Preview pane and GUI tools

- `desktop_preview(action="open", url=...)` opens a web URL, a localhost dev server or a file in the
  pane beside the chat; `close` and `read` complete it. It lives in the `desktop_ui` toolset, which
  Hermes adds to Desktop-app chats only, and it is deferred: the model calls it through
  `tool_describe` and `tool_call` (it is listed in the `tool_search` catalog). Kanban workers and cron
  runs never have it.
- Tabs are scoped (Hermes >= 0.22.0): each tab belongs to the stored session that opened it and the
  pane shows the focused session's tabs plus pinned ones; each profile keeps its own tab list. A pinned
  tab shows in every session of that profile, and tabs saved by a build before session scoping load as
  pinned, which looks like one pane shared across chats: unpin or close them. A chat that is not a
  Desktop session (messaging channel, Kanban worker, cron) has no `desktop_ui` and cannot open a tab.
- Never put `desktop_ui` or `project` in `agent.disabled_toolsets`: they are the client's own surface
  and squad bots need them in their Desktop chat.
- Showing a site while a worker builds it: the manager starts the dev server with
  `terminal(background=true, persist_on_release=true)` and opens `http://localhost:<port>` with
  `desktop_preview`. The browser tool reaches localhost directly
  (`browser.auto_local_for_private_urls`, default on).
