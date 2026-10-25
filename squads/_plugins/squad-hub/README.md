# Squad Hub

A Hermes Desktop plugin for the squads way of working, part of
[Hermes Agent Squads](https://github.com/PuntoyComaTech/hermes-agent-squads). Off until you turn it on in
**Capabilities > Plugins**.

```mermaid
flowchart TD
    B(["Bot"]):::lead --> P["Project"]:::bot
    P --> F["Folder"]:::bot
    F --> W["Main checkout or worktree"]:::bot
    W --> C(["Chat, as a tab"]):::done

    classDef lead fill:#fce7f3,stroke:#db2777,color:#831843
    classDef bot fill:#e0f2fe,stroke:#0284c7,color:#0c4a6e
    classDef done fill:#dcfce7,stroke:#16a34a,color:#14532d
```

- **One list, no profile switch.** A chat opens as a tab under its own bot, so several bots and projects stay open
  side by side. Opening one never reloads the window.
- **Only the bots you talk to.** Default, the builder and squad managers; squad workers never show, and a bot outside
  those shows under "Other bots" only while it has chats. Hide or pin any of them in Settings > Plugins > Squad Hub.
- **Projects with several folders, each with its own worktrees.** "+" on a project, folder or worktree starts a chat
  right there; "New worktree" makes a checkout under `.worktrees/` with its own branch.
- **Previews you can bring back.** Every preview a chat opens is remembered; the status-bar chip lists them and a
  click reopens one, no prompt to the bot.
- **A bot's own pages in one click.** Scheduled jobs, messaging, Kanban and capabilities (capabilities open in a
  dialog pinned to that bot).
- **Quiet big projects.** A project with several folders lists the chats that are working, unread or open right under
  its own row, each with the folder (and worktree) it lives in: one click opens the chat, no folder to unfold. Open
  the project to see its folders, folded, each wearing the dot of what needs you inside. Single-folder projects open
  whole. Fold a whole bot or squad and its pending chats stay listed under it, each tagged with the worktree, folder
  or project it lives in (the full path on hover). Your own open/closed choice always wins.
- **Floating sides (opt-in).** Turn on "Floating sides" in the plugin settings and the left list and the right
  files/terminal column stop taking width: bring the pointer within about 40 px of a screen edge and they slide over the chat like an
  auto-hiding dock, then hide a moment after it leaves (never while you type in them or a menu is open). The title-bar
  side buttons, ⌘B and ⌘J pin or release a side; the chat keeps a small margin so the edges stay free.
- **Squads layout.** The **Squads** layout (Layout editor in the title bar) puts files over a short terminal on the right.
- **Env files.** A project's `.env` files hold secrets, so Desktop's viewer refuses them. Double-click one in the file
  tree (a switch in the settings), or use "Env files…" on a folder or project, and it opens in your system editor; the
  plugin never reads it.
- **Everything that needs you, one key away.** The status bar counts chats working or unread across every bot (click
  for the list); `⌘⇧U` jumps to the next one. A new chat shows whose it is and where it works. `@` in the composer
  offers the project's folders and worktrees. A project's menu opens the browser and sets the project's icon and
  colour (shared with Sessions); projects wear a filled tile, folders a line glyph (a house for the main folder).
- **A look of its own.** Each bot wears a Lucide icon read from what it does (globe for Web, hammer for the
  builder, shopping bag for a store); change any of them in the plugin settings. A local squad that has no manager
  yet shows as one group, its bots under it. The plugin also ships the **Squads** theme (Catppuccin-inspired, low
  contrast, Inter): pick it in Settings > Appearance or in the plugin settings. Lucide's licence: `LICENSE-lucide.txt`.
- **A quieter window.** The plugin hides the Bots tab and the profile selector (switchable in its settings) and can
  hide sidebar rows.

Every change to Desktop's own window (floating sides, hidden Bots tab and profile selector, hidden sidebar rows, the
`.env` double-click) is a switch in **Settings > Plugins > Squad Hub**.

Not changed by the plugin: the Sessions tab, Files, Review, Terminal, artifacts, cron, Kanban and the chat itself.

The plugin is one file (`desktop/plugin.js`): a disk plugin loads uncompiled and resolves only `@hermes/plugin-sdk`,
`react` and `react/jsx-runtime`. `squadctl apply --self` copies the package into the builder profile; Desktop then
copies the desktop half to its own plugins folder. `tests/test_squad_hub_model.py` runs its pure model under node.

## Credits

Made by **PuntoyComaTech**, part of [Hermes Agent Squads](https://github.com/PuntoyComaTech/hermes-agent-squads) (MIT).
Icons: [Lucide](https://lucide.dev) (ISC). Follow along:
[GitHub](https://github.com/PuntoyComaTech) ·
[Instagram](https://www.instagram.com/puntoycomatech) ·
[X](https://x.com/PuntoyComaTech) ·
[YouTube](https://www.youtube.com/@PuntoyComaTech) ·
[TikTok](https://www.tiktok.com/@puntoycomatech)
