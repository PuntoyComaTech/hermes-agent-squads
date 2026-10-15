# Bot Mode and Desktop

## Contents

- [Bot Mode](#bot-mode)
- [Bots pane and ui_meta](#bots-pane-and-ui_meta)
- [Routines](#routines)
- [Profile rail](#profile-rail)
- [Kanban plugin](#kanban-plugin)

## Bot Mode

- Bot Mode turns profiles into bots with titles and avatars; the desktop plugin
  creates each bot's canonical session titled exactly `Bot Chat`
  (`website/docs/user-guide/bot-mode.md`).
- The `ui_meta: {hermes-bots: ...}` block in a profile's `profile.yaml` is the
  "Bot-Mode-managed" marker; the gate scans every profile, so one marked profile
  marks the install (`website/docs/user-guide/bot-mode.md`).

## Bots pane and ui_meta

- The Bots pane (`apps/desktop/src/plugins/hermes-bots/`) owns the roster: bot
  rows, creation, group chats, sections and hiding.
- Hidden bots keep working (dispatch, routines) but stay out of the roster;
  `hidden` rides the bot's `ui_meta` next to `title`
  (`apps/desktop/src/plugins/hermes-bots/types.ts`;
  `apps/desktop/src/plugins/hermes-bots/hidden-bots.ts`; `scripts/squadctl.py`).
- Sections file bots in the pane: the bot's `ui_meta` carries `sectionId` and
  `sectionName` (`apps/desktop/src/plugins/hermes-bots/data.bot-meta.test.ts`).
  Squad tooling writes them from the manifest's `section:`
  (`scripts/squadctl.py`).

## Routines

- A bot's scheduled routines are ordinary Hermes cron jobs named
  `[bot:<name>] <routine>`; they appear in `hermes cron list` and the core Cron
  page and their runs land in the bot's own chat history
  (`website/docs/user-guide/bot-mode.md`).

## Profile rail

- The profile rail lists every profile of the gateway and has no per-profile
  hide setting; "Hide Bot" affects the Bots roster only
  (`apps/desktop/src/app/chat/sidebar/profile-switcher.tsx`).
- Above 13 profiles the rail condenses into a dropdown
  (`PROFILE_DROPDOWN_THRESHOLD = 13`,
  `apps/desktop/src/app/chat/sidebar/profile-switcher.tsx`).
- The rail can be toggled off from the command palette ("Toggle profile rail");
  with a full squad install the Bots pane is the better selector
  (`README.md`).

## Kanban plugin

- The Desktop Kanban plugin ships disabled by default
  (`defaultEnabled: false`, `apps/desktop/src/plugins/kanban/plugin.tsx`); enable
  it under Capabilities to see boards.
- The kanban dispatcher runs in the gateway regardless of the plugin
  (`website/docs/user-guide/features/kanban.md`).
