# Squads Hub Plus

Repo-only companion of [`squad-hub`](../squad-hub). **Not in the Hermes plugin catalog**, by design: the catalog lists
Desktop plugins that stay inside the plugin SDK, and every feature here needs a door the SDK does not have yet.

`squadctl apply` installs it exactly where it installs `squad-hub` — every squad manager and the builder, same opt-out
(`plugins: {disable: [squad-hub-plus]}`) — and enables it. Desktop copies `desktop/plugin.js` to its own plugins folder
like any other package.

## What it carries, and why it cannot be in the catalog copy

| Feature | Why it is outside the SDK | Upstream issue |
|---|---|---|
| Floating sides: the outer layout columns leave the flow, slide in at a screen edge, dock from the title-bar buttons, resize by a grip, keep their widths | Needs the app's layout markup (`[data-tree-split]`, `[data-tree-group]`, `[data-pane-host]`, `[data-persistent-terminal]`, `[data-titlebar-cluster]`) and writes attributes/inline styles onto core nodes; there is no auto-hide hook | [NousResearch/hermes-agent#146514](https://github.com/NousResearch/hermes-agent/issues/146514) |
| Hiding Desktop's profile rail and Bots tab | CSS on the app's own `data-slot` / `data-tree-tab` hooks; there is no SDK verb for hiding core chrome or another plugin's pane | [NousResearch/hermes-agent#146513](https://github.com/NousResearch/hermes-agent/issues/146513) |
| Creating and removing git worktrees, the base-branch list | No SDK verb for a worktree; the plugin would have to shell out through the app's private git bridge | [NousResearch/hermes-agent#146515](https://github.com/NousResearch/hermes-agent/issues/146515) |
| Opening a `.env` file from the file tree (double-click) and listing a folder's env files | Desktop blocks sensitive files in its viewer on purpose; a plugin that opens one by path hands it to the OS's file association, so the name rule refuses every executable suffix | — |
| The native multi-folder picker | `ctx.os.pickOpenPath` picks one file; there is no directory or multi-select mode | — |
| The Kanban page's own board preselection | The page keeps the board in its own storage and only offers a menu; picking it means clicking that menu | — |
| PR / dirty-worktree chips | Reading a PR takes GitHub and reading a checkout takes git: the app's private git bridge again | [NousResearch/hermes-agent#146515](https://github.com/NousResearch/hermes-agent/issues/146515) |
| Opening files and the terminal once when the Squads layout is picked | Detecting the pick reads the root split's id from core layout markup | [NousResearch/hermes-agent#146514](https://github.com/NousResearch/hermes-agent/issues/146514) |

Every one of these was in `squad-hub` before the catalog review; nothing was dropped. As the issues land, a feature can
move back into the catalog copy.

## The handshake

Plain DOM events, no shared module and no shared storage. `squad-hub` dispatches `squad-hub:<action>` with a mutable
`detail` and `cancelable: true`; this plugin calls `preventDefault()` synchronously when it takes the action (squad-hub
then skips its SDK fallback) and does the work after.

| Event | Detail | Taken over by plus |
|---|---|---|
| `squad-hub:pick-folders` | `{ id, title, defaultPath }` | the native folder picker; answers `squad-hub:folders-picked` `{ id, paths }` |
| `squad-hub:worktree-add` | `{ folder, name, branch, base }` | `git worktree add` through the app's git bridge |
| `squad-hub:worktree-remove` | `{ folder, path }` | `git worktree remove` |
| `squad-hub:open-board` | `{ slug, name }` | the Kanban page's own board menu, and the slug it stores |
| `squad-hub:env-files` | `{ folder, label }` | the env-file dialog (list, open one) |
| `squad-hub:lane-chips` | `{ folder, lanes }` | one `prList` per repo and one `repoStatus` per lane; answers `squad-hub:lane-status` `{ folder, statuses }` |

Without this plugin squad-hub still works: the picker falls back to a typed folder path, a worktree action copies the
exact `git worktree …` command and says so, "Env files…" reveals the folder in the file manager, and no chips show.

## Settings

**Settings > Plugins > Squads Hub Plus**: floating sides, the `.env` double-click, hiding the Bots tab, hiding the
profile selector, and the button that takes you to the layout picker. A choice made in squad-hub before the split is
read once from its old prefs key, so nothing resets.

## Tests

`tests/test_squad_hub_plus_host.py` runs this plugin's `register()` against the fake Desktop host: the floating sides
(dock, grip, terminal, dispose), the chrome CSS, the prefs migration, the `.env` double-click and the handshake from
both sides.
