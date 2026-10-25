# Desktop plugins

## Contents

- What a plugin is
- Surfaces a plugin can add
- Host doors
- Hard limits
- Working around a missing surface
- Packaging and loading
- Pitfalls

## What a plugin is

One ESM file, `plugin.js`, evaluated in the Desktop renderer with full app authority. It imports only
`@hermes/plugin-sdk`, `react` and `react/jsx-runtime`; anything else fails the load. No JSX in a disk plugin:
use `jsx()`/`jsxs()`. `register(ctx)` adds contributions; every id is namespaced `<pluginId>:<localId>`.
The loader isolates errors (each contribution has an error boundary), not authority: a plugin can do what the app
can, including `window.hermesDesktop` (files, git, terminal).

## Surfaces a plugin can add

| Surface | Area |
|---|---|
| Pane in the layout (sidebar, right column, bottom) | `PANES_AREA` |
| Full page with a route, sidebar nav entry | `ROUTES_AREA`, `SIDEBAR_NAV_AREA` |
| Status bar item | `STATUSBAR_AREAS.left/right` |
| Title bar tool | `TITLEBAR_AREAS.left/center/right` |
| Command palette entry, rebindable shortcut | `PALETTE_AREA`, `KEYBINDS_AREA` |
| Theme (light + dark, fonts) | `THEMES_AREA` |
| Layout preset in the layout editor | `'layouts'` |
| Composer slots, middleware, `@` completions, model pill label | `COMPOSER_AREAS.*` |
| Session row leading/trailing decoration | `SESSION_ROW_AREAS` |
| Empty state of an existing session (not the new-draft splash) | `CHAT_EMPTY_AREA` |
| Inline component the model writes in a reply | `TRANSCRIPT_DIRECTIVE_AREA` |
| Model menu row badge | `MODEL_MENU_ROW_AREA` |
| Settings page under Settings > Plugins; Appearance extras | `ctx.registerSettingsPage`, `APPEARANCE_AREAS.extra` |

## Host doors

- `host.state.*` atoms: focused session (runtime and stored id, profile), `busyBySession`, cwd, model, viewport.
- `host.request` (active gateway JSON-RPC) and `host.requestProfile(route, ...)`: any profile's RPC without
  switching the window's profile. `foreground` spawn priority for user actions.
- `host.openSession(id, { profile, intent: 'tab' })`, `host.newChat`, `host.openWorkspace` (a plugin tab in the
  main zone), `host.revealPane`, `host.paneVisibility`.
- `host.onEvent` / `ctx.onEvent`: the gateway event stream (message deltas, session lifecycle, tools).
- `host.sessions.pin/reorder/setColor`, `host.skills`, `host.toolsets`, `host.profiles`, `host.settings`
  (an allowlist of appearance keys, `intro-splash.v1` included).
- `ctx.runAction(id)`: view and navigation actions only (`view.toggleSidebar`, `view.showBrowser`,
  `view.toggleReview`, `nav.cron`, `session.new`...). Archive, profile/model switches, terminals and new windows
  are refused.
- `ctx.os.notify` (native notification while the app is unfocused), `openExternal`, `revealPath`,
  `writeClipboard`; `ctx.pet.say` (a line in the pet bubble).
- `ctx.storage` (namespaced localStorage), `ctx.rest` / `ctx.socket` to the plugin's own Python backend
  (`dashboard/plugin_api.py`, imported only when the plugin is in `plugins.enabled`), which can push events with
  `broadcast_plugin_event`.

## Hard limits

- No area for the new-draft splash, the title-bar layout, the tab strip or the pane chrome. Restyling them is CSS
  over core's DOM, which a Desktop update can break.
- Core keyboard shortcuts cannot be redefined. A plugin can add its own rebindable keybind, or intercept keys in the
  capture phase, which is fragile.
- Destructive or privileged actions (delete sessions, approvals, model/provider changes, updates) are not
  reachable through `runAction`. The RPC behind them may still be callable through `host.request`: treat that as
  the user's action and confirm first.
- `.env` and other sensitive files are blocked from Desktop's viewer by design (`hardening.ts`). Open them in the
  system editor; never read their content.
- Narrow-window overlays (hover-reveal sides) only apply under a fixed breakpoint; a plugin that wants them wider
  re-implements them in CSS.
- Pane hosts render outside the split tree, anchored to their zone (CSS anchor positioning): moving a zone moves
  its content, but `visibility` and `opacity` do not inherit across that gap and must be set on the host too.
- `ctx.socket` is a no-op on OAuth remotes; always poll as a fallback.

## Working around a missing surface

In order of preference:

1. A real area or host door (above).
2. Restyling core DOM through stable `data-*` hooks (`data-tree-split`, `data-tree-group`, `data-pane-host`,
   `data-slot`, `data-titlebar-cluster`) with an injected `<style>` removed on dispose.
3. Changing text nodes in place (the splash wordmark): same nodes, so React's tree is untouched. Watch with one
   `MutationObserver`, batched per frame, disconnected on dispose.
4. Never replace or reorder core nodes React owns: the next render throws or duplicates them.

Anything reaching into core DOM is opt-in in the plugin's settings, and a Desktop update is tested before release.

## Packaging and loading

- Disk door: `<HERMES_HOME>/desktop-plugins/<id>/plugin.js`, hot-reloaded on save.
- Unified package: `plugins/<name>/desktop/plugin.js` beside the agent half; Electron copies it into
  `desktop-plugins/` (refreshed on Rescan, install or restart; a symlinked checkout re-syncs on every save).
- `defaultEnabled: false` ships it opt-in; the user turns it on in Capabilities > Plugins.

## Pitfalls

- Globals are not tracked: `window.addEventListener`, `setInterval` or an appended `<style>` outlive disable and
  stack on every hot reload. Use `ctx.setTimeout` / `ctx.addEventListener` or pair each with `ctx.onDispose`, and
  reset module state yourself.
- A module-level constant named like a global (`CSS`) shadows it (`CSS.escape` undefined).
- `h()` helpers that always pass `children` break `dangerouslySetInnerHTML`; use `jsx()` for raw SVG.
- A pointer timer re-armed on every `pointermove` only fires once the pointer stops; arm once on entry.
- Core's side toggles fold a zone to its tab rail; a plugin that floats the sides must intercept them.
- Read atoms with `.get()` inside handlers; subscribe with `useValue` only where the value renders.
