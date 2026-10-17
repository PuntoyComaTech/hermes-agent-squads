# Bot Mode and Desktop

## Bot Mode

- Bot Mode turns profiles into bots with titles and avatars; each bot has one
  canonical session titled exactly `Bot Chat`.
- The `ui_meta: {hermes-bots: ...}` block in a profile's `profile.yaml` is the
  "Bot-Mode-managed" marker; the gate scans every profile, so one marked profile
  marks the install. No CLI command writes it.

## Bots pane and ui_meta

- The Bots pane owns the roster: bot
  rows, creation, group chats, sections and hiding.
- `ui_meta` fields the Desktop reads include `title`, `hidden`, `pinned`,
  `sectionId` and `sectionName`.
- Hidden bots keep working (dispatch, routines, @mentions) but stay out of the
  roster.
- Squad tooling writes `title`, `hidden` and the section from the manifest's
  `section:`. How it writes: `soul-and-context-files.md`
  -> profile.yaml and ui_meta.

## Routines

- A bot's routines are ordinary cron jobs named `[bot:<name>] <routine>`; they
  appear in `hermes cron list` and their runs land in the bot's chat history.

## Profile rail

- The profile rail lists every profile of the gateway; "Hide Bot" affects the
  Bots roster only.
- Above 13 entries the rail condenses into a dropdown
  (`PROFILE_DROPDOWN_THRESHOLD`, same file).
- "Toggle profile rail" (`view.toggleProfileRail`) hides it.

## Kanban plugin

- The Desktop Kanban plugin ships disabled (`defaultEnabled: false`); enable it under Capabilities to
  see boards.
- The kanban dispatcher runs in the gateway regardless of the plugin
  (`kanban.dispatch_in_gateway`).

## Preview pane and GUI tools

- `desktop_preview(action="open", url=...)` opens a web URL, a localhost dev
  server or a file in the pane beside the chat; `close` and `read` complete it.
  It lives in the `desktop_ui` toolset, which Hermes adds to Desktop-app chats
  only, and it is deferred: the model calls it through `tool_describe` and
  `tool_call` (it is listed in the `tool_search` catalog). Kanban workers and
  cron runs never have it.
- Never put `desktop_ui` or `project` in `agent.disabled_toolsets`: they are
  the client's own surface and squad bots need them in their Desktop chat.
- Showing a site while a worker builds it: the manager starts the dev server with
  `terminal(background=true, persist_on_release=true)` and opens
  `http://localhost:<port>` with `desktop_preview`. The browser tool reaches
  localhost directly (`browser.auto_local_for_private_urls`, default on).
