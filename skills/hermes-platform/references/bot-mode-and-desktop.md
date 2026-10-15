# Bot Mode and Desktop

## Bot Mode

- Bot Mode turns profiles into bots with titles and avatars; each bot has one
  canonical session titled exactly `Bot Chat`
  (`website/docs/user-guide/bot-mode.md`).
- The `ui_meta: {hermes-bots: ...}` block in a profile's `profile.yaml` is the
  "Bot-Mode-managed" marker; the gate scans every profile, so one marked profile
  marks the install. No CLI command writes it
  (`website/docs/user-guide/bot-mode.md`, "What actually makes a chat a Bot
  Chat").

## Bots pane and ui_meta

- The Bots pane (`apps/desktop/src/plugins/hermes-bots/`) owns the roster: bot
  rows, creation, group chats, sections and hiding.
- `ui_meta` fields the Desktop reads include `title`, `hidden`, `pinned`,
  `sectionId` and `sectionName`
  (`apps/desktop/src/plugins/hermes-bots/types.ts`).
- Hidden bots keep working (dispatch, routines, @mentions) but stay out of the
  roster (`apps/desktop/src/plugins/hermes-bots/hidden-bots.ts`).
- Squad tooling writes `title`, `hidden` and the section from the manifest's
  `section:` (`scripts/squadctl.py`). How it writes: `soul-and-context-files.md`
  -> profile.yaml and ui_meta.

## Routines

- A bot's routines are ordinary cron jobs named `[bot:<name>] <routine>`; they
  appear in `hermes cron list` and their runs land in the bot's chat history
  (`website/docs/user-guide/bot-mode.md`).

## Profile rail

- The profile rail lists every profile of the gateway; "Hide Bot" affects the
  Bots roster only (`apps/desktop/src/app/chat/sidebar/profile-switcher.tsx`).
- Above 13 entries the rail condenses into a dropdown
  (`PROFILE_DROPDOWN_THRESHOLD`, same file).
- "Toggle profile rail" (`view.toggleProfileRail`) hides it
  (`apps/desktop/src/store/profile-rail-prefs.ts`).

## Kanban plugin

- The Desktop Kanban plugin ships disabled (`defaultEnabled: false`,
  `apps/desktop/src/plugins/kanban/plugin.tsx`); enable it under Capabilities to
  see boards.
- The kanban dispatcher runs in the gateway regardless of the plugin
  (`kanban.dispatch_in_gateway`, `website/docs/user-guide/features/kanban.md`).
