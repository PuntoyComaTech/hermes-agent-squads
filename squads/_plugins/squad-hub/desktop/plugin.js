// Squad Hub — a Hermes Desktop plugin for the Hermes Agent Squads way of working.
//
//   Bot  →  Project  →  Folder  →  Lane (main checkout | worktree)  →  Chat
//
// One list for the bots you talk to (default, builder, squad managers; workers never show). A chat opens as a
// tab under its own bot, so several bots and projects stay open side by side without the profile switch that
// reloads the window. Each folder of a project can hold its own worktrees; "+" starts a chat in one.
// Previews a chat opened are remembered, so a closed one is one click to reopen.
//
// Single file by design: a disk plugin loads uncompiled and only resolves `@hermes/plugin-sdk`, `react` and
// `react/jsx-runtime`. The pure model between the MODEL markers is extracted and tested by
// tests/test_squad_hub_model.py, which runs it under node.
import * as sdk from '@hermes/plugin-sdk'
import { useEffect, useMemo, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

// ───────────────────────────── MODEL (pure) ─────────────────────────────
// Everything between the MODEL markers is plain JS with no imports: the repo's
// tests extract it and run it under node against real payload shapes.
const HUMAN_SOURCES = new Set(['desktop', 'tui', 'cli'])
const ROLE_ORDER = { default: 0, builder: 1, manager: 2, other: 3 }

const trimPath = p => String(p || '').replace(/[/\\]+$/, '')
const underPath = (path, root) => {
  const a = trimPath(path)
  const b = trimPath(root)
  return Boolean(a && b) && (a === b || a.startsWith(b + '/'))
}
const baseName = p => trimPath(p).split(/[/\\]/).pop() || String(p || '')
const sessionTime = s => s.last_active || s.last_activity_at || s.started_at || 0

function botRole(profile) {
  const squad = profile.ui_meta?.['hermes-squads']
  if (squad?.role) return squad.role
  if (profile.is_default) return 'default'
  if (profile.name === 'builder') return 'builder'
  if (profile.ui_meta?.['hermes-bots']?.sectionName === 'Managers') return 'manager'
  return 'other'
}

function botTitle(profile) {
  return (
    profile.ui_meta?.['hermes-squads']?.name ||
    profile.ui_meta?.['hermes-bots']?.title ||
    profile.display_name ||
    (profile.is_default ? 'Hermes' : profile.name)
  )
}

/** A chat a person had: Desktop / TUI / CLI, not hidden, not archived, not empty.
 *  Kanban runs, one-shots, cron and subagents are the squad's own work. */
function isHumanChat(s, now = Date.now() / 1000) {
  const fresh = now - (s.started_at || 0) < 600 // a chat just started shows at once; an unused one drops off
  return HUMAN_SOURCES.has(s.source) && !s.hidden && !s.archived && ((s.message_count || 0) > 0 || Boolean(s.title) || fresh)
}

/** The Desktop section a profile is filed under (`ui_meta.hermes-bots.sectionName`), '' for none. */
const sectionOf = profile => String(profile.ui_meta?.['hermes-bots']?.sectionName || '').trim()

/** The bots a squads user talks to. Default, the builder and squad managers always show;
 *  any other profile only when it has a human chat (squad workers never do). A bot outside those whose
 *  Desktop section has no manager (a squad still without one) is grouped under that section. */
function visibleBots(profiles, humanByProfile, prefs = {}) {
  const hidden = new Set(prefs.hidden || [])
  const pinned = new Set(prefs.pinned || [])
  const bots = []
  for (const p of profiles) {
    if (hidden.has(p.name)) continue
    const role = botRole(p)
    const core = role === 'default' || role === 'builder' || role === 'manager' || pinned.has(p.name)
    if (!core && !(humanByProfile[p.name] > 0)) continue
    bots.push({ name: p.name, title: botTitle(p), role, other: !core, section: sectionOf(p) })
  }
  const managed = new Set(bots.filter(b => b.role === 'manager').map(b => b.title.replace(/\s+manager$/i, '').toLowerCase()))
  for (const b of bots) b.group = b.other && b.section && b.section !== 'Managers' && !managed.has(b.section.toLowerCase()) ? b.section : ''
  const order = prefs.order || []
  return bots.sort((a, b) => {
    const ia = order.indexOf(a.name)
    const ib = order.indexOf(b.name)
    if (ia !== -1 || ib !== -1) return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
    return (ROLE_ORDER[a.role] ?? 3) - (ROLE_ORDER[b.role] ?? 3) || a.title.localeCompare(b.title)
  })
}

/** The project folder a chat belongs to: its cwd under a folder (deepest wins), else its
 *  git root equal to a folder (a worktree outside the folder still belongs to its repo). */
function folderOf(session, folders) {
  const cwd = trimPath(session.cwd)
  const root = trimPath(session.git_repo_root)
  const deep = [...folders].sort((a, b) => trimPath(b.path).length - trimPath(a.path).length)
  return deep.find(f => underPath(cwd, f.path)) || deep.find(f => root && trimPath(f.path) === root) || null
}

/** Lane of a chat inside a folder: a linked worktree (from `git worktree list`, or a
 *  `.worktrees/<name>` path before that list arrives), else the main checkout. */
function laneOf(session, folderPath, worktrees) {
  const cwd = trimPath(session.cwd)
  const linked = (worktrees || []).filter(w => !w.isMain).sort((a, b) => trimPath(b.path).length - trimPath(a.path).length)
  const hit = linked.find(w => underPath(cwd, w.path))
  if (hit) return { key: trimPath(hit.path), path: trimPath(hit.path), label: baseName(hit.path), branch: hit.branch || '', main: false }
  const m = cwd.match(/^(.*\/\.worktrees\/[^/]+)/)
  if (m) return { key: m[1], path: m[1], label: baseName(m[1]), branch: session.git_branch || '', main: false }
  const main = (worktrees || []).find(w => w.isMain)
  return { key: trimPath(folderPath), path: trimPath(folderPath), label: 'main', branch: main?.branch || '', main: true }
}

const laneTime = lane => Math.max(0, ...lane.sessions.map(sessionTime))
/** Kanban dispatcher checkouts (`.worktrees/t_<hex>`): the squad's workers' own, never a lane to chat in or remove. */
const isKanbanWorktree = p => /[/\\]\.worktrees[/\\]t_[0-9a-f]+[/\\]?$/.test(String(p || ''))

/** One bot's tree: projects → folders → lanes → chats, plus the chats in no project.
 *  `projects` are projects.list rows; `worktrees` maps a folder path to its git worktrees. */
function buildBotTree(bot, projects, chats, worktrees = {}) {
  const used = new Set()
  const out = []
  for (const project of projects.filter(p => !p.archived)) {
    const declared = (project.folders || []).length
      ? project.folders
      : project.primary_path
        ? [{ path: project.primary_path, is_primary: true }]
        : []
    const folders = declared.map(f => ({ path: trimPath(f.path), label: f.label || baseName(f.path), primary: !!f.is_primary, lanes: new Map() }))
    for (const s of chats) {
      if (used.has(s.id)) continue
      const f = folderOf(s, folders)
      if (!f) continue
      const lane = laneOf(s, f.path, worktrees[f.path])
      if (!f.lanes.has(lane.key)) f.lanes.set(lane.key, { ...lane, sessions: [] })
      f.lanes.get(lane.key).sessions.push(s)
      used.add(s.id)
    }
    for (const f of folders) {
      const wts = worktrees[f.path] || []
      if (!f.lanes.has(f.path)) f.lanes.set(f.path, { key: f.path, path: f.path, label: 'main', branch: '', main: true, sessions: [] })
      const main = f.lanes.get(f.path)
      if (!main.branch) main.branch = wts.find(w => w.isMain)?.branch || ''
      for (const w of wts) {
        const key = trimPath(w.path)
        if (w.isMain || (isKanbanWorktree(key) && !f.lanes.has(key))) continue
        if (f.lanes.has(key)) f.lanes.get(key).branch = w.branch || f.lanes.get(key).branch
        else f.lanes.set(key, { key, path: key, label: baseName(key), branch: w.branch || '', main: false, sessions: [] })
      }
      f.lanes = [...f.lanes.values()].sort((a, b) => Number(b.main) - Number(a.main) || laneTime(b) - laneTime(a) || a.label.localeCompare(b.label))
      for (const l of f.lanes) l.sessions.sort((a, b) => sessionTime(b) - sessionTime(a))
    }
    const last = Math.max(0, ...folders.flatMap(f => f.lanes.map(laneTime)))
    for (const f of folders) f.repo = Boolean((worktrees[f.path] || []).length)
    out.push({ id: project.id, name: project.name, icon: project.icon || '', color: project.color || '', folders, last, chats: folders.reduce((n, f) => n + f.lanes.reduce((m, l) => m + l.sessions.length, 0), 0) })
  }
  out.sort((a, b) => b.last - a.last || a.name.localeCompare(b.name))
  const loose = chats.filter(s => !used.has(s.id)).sort((a, b) => sessionTime(b) - sessionTime(a))
  return { bot, projects: out, loose }
}

/** What a chat asks of you right now: 'working' (a turn is running in it), 'unread' (it answered while you were
 *  elsewhere), 'current' (the chat in view, so it does not vanish from the shortcut list the moment you open it),
 *  '' (nothing). The chat you are looking at is never unread: you are reading it. `live` is the set of
 *  stored ids with a running turn. */
function chatState(session, attention) {
  const { live = [], unread = [], focused = null } = attention || {}
  if (new Set(live).has(session.id)) return 'working'
  if (session.id === focused) return 'current'
  return session.unread || new Set(unread).has(session.id) ? 'unread' : ''
}
const STATE_RANK = { working: 0, unread: 1, current: 2 }

/** The chats of a folder (or a whole project) that are working or unread, loudest first, newest first within a
 *  state. Each keeps its folder and lane so a digest can say where it is. `attention` is
 *  { live, unread, focused }: stored ids with a running turn, ids Desktop flagged unread, the chat in view. */
function activeIn(folders, attention) {
  const out = []
  for (const f of [].concat(folders)) {
    for (const lane of f.lanes) {
      for (const session of lane.sessions) {
        const state = chatState(session, attention)
        if (state) out.push({ session, state, folder: f, lane })
      }
    }
  }
  return sortByAttention(out)
}

/** How a project opens by default. A project with several folders is a digest until you open it: only the chats
 *  that need you show under it. A single-folder project is small enough to show whole. */
const projectOpensWide = project => project.folders.length <= 1

/** The chats a project with several folders lists right under its own row, open or closed: what is working,
 *  unread or in view, each a shortcut that skips opening its folder. A single-folder project shows whole instead. */
const projectDigest = (project, attention, open = true) =>
  project.folders.length > 1 || !open ? activeIn(project.folders, attention) : []

/** A folded bot's shortcut list: what needs you in every project and in its loose chats, loudest first, so a pending
 *  chat (or one in a worktree) is one click away without opening the bot, the project or the folder. */
function botDigest(tree, attention) {
  const out = []
  for (const project of tree.projects) for (const x of activeIn(project.folders, attention)) out.push({ ...x, project })
  for (const session of tree.loose) {
    const state = chatState(session, attention)
    if (state) out.push({ session, state, project: null, folder: null, lane: null })
  }
  return sortByAttention(out)
}

const sortByAttention = items =>
  items.sort((a, b) => STATE_RANK[a.state] - STATE_RANK[b.state] || sessionTime(b.session) - sessionTime(a.session))

/** Where a shortcut lives, as short as it can be said: project, then the folder when the project has several, then
 *  the worktree when it is not the main checkout. */
const whereOf = x =>
  [x.project?.name, x.project && x.project.folders.length > 1 ? x.folder?.label : '', x.lane && !x.lane.main ? x.lane.label : '']
    .filter(Boolean)
    .join(' · ')

/** What a folded folder signals: the chats that need you (the one merely in view does not). */
const needsYou = items => items.filter(x => x.state !== 'current')

const matchesQuery = (text, q) => !q.trim() || String(text || '').toLowerCase().includes(q.trim().toLowerCase())

/** Keep what matches `q`; a matching bot or project keeps everything under it. */
function filterTree(tree, q) {
  if (!q.trim() || matchesQuery(tree.bot.title, q) || matchesQuery(tree.bot.name, q)) return tree
  const projects = []
  for (const p of tree.projects) {
    if (matchesQuery(p.name, q)) {
      projects.push(p)
      continue
    }
    const folders = []
    for (const f of p.folders) {
      const lanes = []
      for (const l of f.lanes) {
        const sessions = l.sessions.filter(s => matchesQuery(s.title || s.preview, q))
        if (sessions.length) lanes.push({ ...l, sessions })
        else if (matchesQuery(l.label, q) || matchesQuery(l.branch, q) || matchesQuery(f.label, q)) lanes.push(l)
      }
      if (lanes.length) folders.push({ ...f, lanes })
    }
    if (folders.length) projects.push({ ...p, folders })
  }
  const loose = tree.loose.filter(s => matchesQuery(s.title || s.preview, q))
  return projects.length || loose.length ? { ...tree, projects, loose } : null
}

function shortAge(seconds, now = Date.now() / 1000) {
  if (!seconds) return ''
  const d = Math.max(0, now - seconds)
  if (d < 60) return 'now'
  if (d < 3600) return Math.floor(d / 60) + 'm'
  if (d < 86400) return Math.floor(d / 3600) + 'h'
  if (d < 86400 * 30) return Math.floor(d / 86400) + 'd'
  return Math.floor(d / (86400 * 30)) + 'mo'
}

function slugify(name) {
  return String(name || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48)
}

/** Remember a preview for a chat: newest first, one entry per url, capped. */
function rememberPreview(map, storedId, entry, perChat = 8, maxChats = 200) {
  if (!storedId || !entry?.url) return map
  const list = [entry, ...(map[storedId] || []).filter(p => p.url !== entry.url)].slice(0, perChat)
  const next = { ...map, [storedId]: list }
  const ids = Object.keys(next)
  if (ids.length > maxChats) {
    ids.sort((a, b) => (next[b][0]?.at || 0) - (next[a][0]?.at || 0))
    for (const id of ids.slice(maxChats)) delete next[id]
  }
  return next
}
/** A Lucide icon for a bot or a squad group, read from what it does: an explicit choice wins, then the squad
 *  key, then words in its name. A group (a squad without a manager) of shops reads as a storefront. */
const ICON_BY_KEY = { default: 'sparkles', builder: 'hammer', jobs: 'briefcase-business', marketing: 'megaphone', web: 'globe' }
const ICON_WORDS = [
  [/commerce|shop|store|tienda|retail|ecom/i, 'shopping-bag'],
  [/\bweb|site|front/i, 'globe'],
  [/job|career|hiring|empleo/i, 'briefcase-business'],
  [/market|ads?\b|growth|social/i, 'megaphone'],
  [/code|dev|infra|engineer|tech/i, 'code'],
  [/data|analy|report|metric/i, 'chart-line'],
  [/design|creative|brand|art/i, 'palette'],
  [/ops|deploy|server|cloud/i, 'server'],
  [/launch|startup|product/i, 'rocket'],
  [/team|people|support|crm/i, 'users']
]
function iconFor(bot, overrides = {}) {
  if (overrides[bot.name]) return overrides[bot.name]
  if (bot.icon) return bot.icon
  if (ICON_BY_KEY[bot.name]) return ICON_BY_KEY[bot.name]
  const text = `${bot.name} ${bot.title || ''}`
  return ICON_WORDS.find(([re]) => re.test(text))?.[1] || 'bot'
}
function groupIconFor(section, overrides = {}) {
  const key = 'group:' + section
  if (overrides[key]) return overrides[key]
  const icon = ICON_WORDS.find(([re]) => re.test(section))?.[1] || 'users'
  return icon === 'shopping-bag' ? 'store' : icon
}
/** Env files a project keeps beside its code, the ones people edit by hand: `.env`, `.env.local`, `.env.production`…
 *  Never the shared templates (`.env.example`), which the normal file tree already opens. */
const isEnvFile = name => /^\.env(\.[\w.-]+)?$/.test(name) && !/\.$/.test(name) && !/^\.env\.(example|sample|template|dist)$/.test(name)

/** The chats that need you across every visible bot, loudest first: what the global counter counts and what
 *  "next pending chat" walks. `trees` are buildBotTree results. */
function pendingAcross(trees, attention) {
  const out = []
  for (const tree of trees) for (const x of botDigest(tree, attention)) if (x.state !== 'current') out.push({ ...x, bot: tree.bot })
  return sortByAttention(out)
}

/** The chat after `currentId` in the pending list, wrapping; the first when the current one is not pending. */
function nextPending(items, currentId) {
  if (!items.length) return null
  const i = items.findIndex(x => x.session.id === currentId)
  return items[(i + 1) % items.length]
}

/** Folder glyph: the project's main folder, a git repo, or a plain folder. */
const folderIcon = (folder, isRepo) => (folder.primary ? 'house' : isRepo ? 'folder-git-2' : 'folder')
// ─────────────────────────── END MODEL (pure) ───────────────────────────

// ───────────────────────────── host wiring ─────────────────────────────
const {
  host, atom, useValue, useQuery, queryClient, usePluginI18n, Codicon, DisclosureCaret, SearchField, Tip, Button, Input,
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
  SessionStatusDot, COMPOSER_AREAS, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, ToggleRow, EmptyState,
  CapabilitiesView, ColorSwatches, PROFILE_SWATCHES, CHAT_EMPTY_AREA, profileColor, haptic, isSubmitEnter, requestTheme, useTheme, THEMES_AREA, STATUSBAR_AREAS, PALETTE_AREA, KEYBINDS_AREA, SIDEBAR_NAV_PREFS_AREA
} = sdk

const ID = 'squad-hub'
const SNAPSHOT_KEY = ['squad-hub', 'snapshot']
const h = (type, props, ...kids) => {
  const { key, ...rest } = props || {}
  return jsxs(type, { ...rest, children: kids.flat(Infinity).filter(k => k !== null && k !== undefined && k !== false) }, key)
}
const git = () => window.hermesDesktop?.git || null
const stop = e => e.stopPropagation()
const rpc = (method, params) => host.request(method, params)

const MESSAGES = {
  en: {
    search: 'Search chats, projects, worktrees', refresh: 'Refresh', loading: 'Loading…', loadFailed: 'Could not load',
    newChatWith: 'New chat with {0}', newChatIn: 'New chat in {0}', newChatHere: 'New chat here', chats: 'Chats',
    outside: 'Chats outside a project', noChats: 'No chats yet', noProjects: 'No projects yet', createOne: 'create one',
    otherBots: 'Other bots', nothingMatches: 'Nothing matches', noBots: 'No bots yet', noBotsHint: 'Ask the Builder to install a squad.',
    newProject: 'New project…', addFolder: 'Add folders…', removeFolder: 'Remove folder from project', newWorktree: 'New worktree…',
    removeWorktree: 'Remove worktree', renameProject: 'Rename project…', removeProject: 'Remove project (keeps the folders)',
    scheduled: 'Scheduled jobs', messaging: 'Messaging', capabilities: 'Capabilities…', kanban: 'Kanban board', pinTop: 'Pin to top',
    unpin: 'Unpin', hideBot: 'Hide from Squads', copyPath: 'Copy path', reveal: 'Reveal in Finder', terminal: 'Terminal here',
    openWindow: 'Open in a new window', rename: 'Rename…', archive: 'Archive', previews: 'Previews', reopenPreview: 'Reopen preview',
    noPreviews: 'No previews saved for this chat', primary: 'primary', name: 'Name', folders: 'Folders', none: 'None yet',
    cancel: 'Cancel', create: 'Create', creating: 'Creating…', save: 'Save', remove: 'Remove', projectIn: 'New project in {0}',
    projectHelp: 'A project groups one or more folders. Each folder can get its own worktrees.', projectName: 'e.g. Website redesign',
    worktreeIn: 'New worktree in {0}', worktreeHelp: 'A separate checkout under .worktrees/ with its own branch, so chats work in parallel.',
    branch: 'Branch (optional)', startFrom: 'Start from', defaultTag: '(default)', worktreeReady: 'Worktree ready: {0}',
    removeWorktreeAsk: 'Remove worktree?', removeWorktreeBody: 'Git refuses if it has uncommitted changes. The branch is kept.',
    renameChat: 'Rename chat', chatNow: 'Working here', setup: 'Workspace', envDoubleClick: 'Open .env files on double-click', envDoubleClickHint: 'In the file tree they open in your system editor; off leaves the tree as Hermes made it.', creditsBy: 'Made by', creditsPart: 'part of', hideBotsTab: 'Hide the Bots tab',
    hideBotsTabHint: 'Squads replaces it: bots, projects and chats live in one list.', hideRail: 'Hide the profile selector',
    hideRailHint: 'The bottom strip that switches the whole window between bots. Squads opens each chat under its own bot instead.',
    showOthers: 'Show other bots that have chats', showOthersHint: 'Bots that are not default, the builder or a squad manager.',
    sortRecent: 'Order bots by recent activity', sortRecentHint: 'Off: default, builder, then managers.', navRows: 'Sidebar rows',
    visibleBots: 'Visible bots', allVisible: 'Every bot you can talk to is listed here; squad workers never are.',
    ctxPreviews: 'Previews', ctxFiles: 'Files', ctxReview: 'Review', ctxTerminal: 'Terminal', botCaps: 'Capabilities of {0}',
    cmdOpen: 'Squads: focus the list', cmdNext: 'Squads: next chat that needs you', cmdFloat: 'Squads: floating sides on/off', cmdPinLeft: 'Squads: pin or hide the left side', cmdPinRight: 'Squads: pin or hide the right side', cmdLayout: 'Squads: choose the Squads layout', nothingPending: 'Nothing is waiting for you', pendingTip: 'Chats working or unread, across every bot', working: 'working', unread: 'unread', introHint: 'Works in the place below. Ask away.', alsoPending: 'Also waiting here', floatSides: 'Floating sides', floatSidesHint: 'The left list and the right files/terminal take no width: bring the pointer near a screen edge and they slide over the chat, then hide when you leave. The side buttons in the title bar pin them.', layoutName: 'Squads layout', layoutHint: 'Squads left, chat in the middle, files over a short terminal on the right.', layoutPick: 'Pick “Squads” under Layout.', openBrowser: 'Open the browser', envFiles: 'Env files…', appearance: 'Icon and colour…', appearanceOf: 'Look of {0}', appearanceHelp: 'Shown here and in Sessions.', defaultIcon: 'Default', defaultColor: 'Bot colour', envIn: 'Env files in {0}', envHelp: 'They hold secrets, so Hermes keeps them out of its own viewer; each opens in your editor for that file.', openInEditor: 'Open in editor', noEnv: 'No .env file in this folder.', envOpenFailed: 'Could not open it. Is an app set to open this file type?', showMore: 'Show {0} more', cmdTheme: 'Squads: use the Squads theme', themeName: 'Squads theme', themeHint: 'Catppuccin-inspired, low contrast: cream by day, mocha by night. Follows the light/dark switch.', themeUse: 'Use it', themeActive: 'In use', cmdNewProject: 'Squads: new project…', cmdPreview: 'Squads: reopen a preview', pane: 'Squads'
  },
  es: {
    search: 'Buscar chats, proyectos, worktrees', refresh: 'Actualizar', loading: 'Cargando…', loadFailed: 'No se pudo cargar',
    newChatWith: 'Nuevo chat con {0}', newChatIn: 'Nuevo chat en {0}', newChatHere: 'Nuevo chat aquí', chats: 'Chats',
    outside: 'Chats fuera de un proyecto', noChats: 'Aún no hay chats', noProjects: 'Aún no hay proyectos', createOne: 'crea uno',
    otherBots: 'Otros bots', nothingMatches: 'Nada coincide', noBots: 'Aún no hay bots', noBotsHint: 'Pídele al Builder que instale un squad.',
    newProject: 'Nuevo proyecto…', addFolder: 'Añadir carpetas…', removeFolder: 'Quitar carpeta del proyecto', newWorktree: 'Nuevo worktree…',
    removeWorktree: 'Quitar worktree', renameProject: 'Renombrar proyecto…', removeProject: 'Quitar proyecto (conserva las carpetas)',
    scheduled: 'Tareas programadas', messaging: 'Mensajería', capabilities: 'Capacidades…', kanban: 'Tablero Kanban', pinTop: 'Fijar arriba',
    unpin: 'Desfijar', hideBot: 'Ocultar de Squads', copyPath: 'Copiar ruta', reveal: 'Mostrar en Finder', terminal: 'Terminal aquí',
    openWindow: 'Abrir en otra ventana', rename: 'Renombrar…', archive: 'Archivar', previews: 'Previews', reopenPreview: 'Reabrir preview',
    noPreviews: 'No hay previews guardadas de este chat', primary: 'principal', name: 'Nombre', folders: 'Carpetas', none: 'Ninguna aún',
    cancel: 'Cancelar', create: 'Crear', creating: 'Creando…', save: 'Guardar', remove: 'Quitar', projectIn: 'Nuevo proyecto en {0}',
    projectHelp: 'Un proyecto agrupa una o varias carpetas. Cada carpeta puede tener sus propios worktrees.', projectName: 'p. ej. Rediseño web',
    worktreeIn: 'Nuevo worktree en {0}', worktreeHelp: 'Una copia aparte bajo .worktrees/ con su propia rama, para que los chats trabajen en paralelo.',
    branch: 'Rama (opcional)', startFrom: 'Partir de', defaultTag: '(por defecto)', worktreeReady: 'Worktree listo: {0}',
    removeWorktreeAsk: '¿Quitar el worktree?', removeWorktreeBody: 'Git se niega si tiene cambios sin confirmar. La rama se conserva.',
    renameChat: 'Renombrar chat', chatNow: 'Trabajando aquí', setup: 'Espacio de trabajo', envDoubleClick: 'Abrir los .env con doble clic', envDoubleClickHint: 'En el árbol de archivos se abren en tu editor del sistema; apagado deja el árbol como lo hace Hermes.', creditsBy: 'Hecho por', creditsPart: 'parte de', hideBotsTab: 'Ocultar la pestaña Bots',
    hideBotsTabHint: 'Squads la reemplaza: bots, proyectos y chats en una sola lista.', hideRail: 'Ocultar el selector de perfiles',
    hideRailHint: 'La franja de abajo que cambia toda la ventana de bot. Squads abre cada chat bajo su propio bot.',
    showOthers: 'Mostrar otros bots que tengan chats', showOthersHint: 'Bots que no son default, el builder ni un manager de squad.',
    sortRecent: 'Ordenar bots por actividad reciente', sortRecentHint: 'Apagado: default, builder y luego managers.', navRows: 'Filas de la barra lateral',
    visibleBots: 'Bots visibles', allVisible: 'Aquí está cada bot con el que puedes hablar; los workers de un squad nunca salen.',
    ctxPreviews: 'Previews', ctxFiles: 'Archivos', ctxReview: 'Revisión', ctxTerminal: 'Terminal', botCaps: 'Capacidades de {0}',
    cmdOpen: 'Squads: enfocar la lista', cmdNext: 'Squads: siguiente chat pendiente', cmdFloat: 'Squads: costados flotantes sí/no', cmdPinLeft: 'Squads: fijar u ocultar el costado izquierdo', cmdPinRight: 'Squads: fijar u ocultar el costado derecho', cmdLayout: 'Squads: elegir el layout Squads', nothingPending: 'Nada te está esperando', pendingTip: 'Chats trabajando o sin leer, de todos los bots', working: 'trabajando', unread: 'sin leer', introHint: 'Trabaja en el lugar de abajo. Pídele lo que necesites.', alsoPending: 'También pendiente aquí', floatSides: 'Costados flotantes', floatSidesHint: 'La lista izquierda y los archivos/terminal de la derecha no ocupan ancho: acerca el puntero a un borde y se deslizan sobre el chat; al salir se ocultan. Los botones laterales de la barra de título los fijan.', layoutName: 'Layout Squads', layoutHint: 'Squads a la izquierda, el chat al centro, archivos sobre una terminal baja a la derecha.', layoutPick: 'Elige “Squads” en Layout.', openBrowser: 'Abrir el navegador', envFiles: 'Archivos .env…', appearance: 'Icono y color…', appearanceOf: 'Apariencia de {0}', appearanceHelp: 'Se ve aquí y en Sessions.', defaultIcon: 'Por defecto', defaultColor: 'Color del bot', envIn: 'Archivos .env en {0}', envHelp: 'Guardan secretos, así que Hermes no los abre en su visor; cada uno se abre en tu editor para ese archivo.', openInEditor: 'Abrir en el editor', noEnv: 'No hay archivo .env en esta carpeta.', envOpenFailed: 'No se pudo abrir. ¿Hay una app asignada a este tipo de archivo?', showMore: 'Mostrar {0} más', cmdTheme: 'Squads: usar el tema Squads', themeName: 'Tema Squads', themeHint: 'Inspirado en Catppuccin, de bajo contraste: crema de día, mocha de noche. Sigue el modo claro/oscuro.', themeUse: 'Usarlo', themeActive: 'En uso', cmdNewProject: 'Squads: nuevo proyecto…', cmdPreview: 'Squads: reabrir una preview', pane: 'Squads'
  }
}
const fmt = (s, ...a) => String(s).replace(/\{(\d+)\}/g, (_, i) => a[i] ?? '')
const useT = () => {
  const t = usePluginI18n(ID)
  return (k, ...a) => fmt(t(k), ...a)
}
const patchSession = (bot, id, body) =>
  window.hermesDesktop.api({ path: `/api/sessions/${encodeURIComponent(id)}`, method: 'PATCH', profile: bot.name, body: { ...body, profile: bot.name } })

// ───────────────────────────── state ─────────────────────────────
const DEFAULT_PREFS = { envDoubleClick: true, floatSides: false, hidden: [], pinned: [], order: [], showOthers: true, sortRecent: false, hideBotsTab: true, hideRail: true, hiddenNav: [] }
let storage = null
let ctxRef = null
const prefsAtom = atom({ ...DEFAULT_PREFS })
const collapsedAtom = atom({})
const previewsAtom = atom({})
const liveAtom = atom([])
const unreadAtom = atom([])
const savePrefs = patch => {
  prefsAtom.set({ ...prefsAtom.get(), ...patch })
  storage?.set('prefs', prefsAtom.get())
  applyChrome()
  applyFloat()
}
const toggleCollapsed = (key, def = false) => {
  const cur = collapsedAtom.get()
  const next = { ...cur, [key]: !(key in cur ? cur[key] : def) }
  collapsedAtom.set(next)
  storage?.set('collapsed', next)
}
const isOpen = (collapsed, key, def = true) => (key in collapsed ? !collapsed[key] : def)

/** Stored ids of chats with a running turn: Desktop's own busy flags (runtime ids) joined to stored ids through the
 *  session.info events and the focused pair. A chat this window has not heard from stays unknown; its unread flag
 *  still comes from the backend. */
/** Desktop flags a chat that finished while you were elsewhere in its own persisted marker (the backend learns
 *  about it later, if at all); this reads that same marker so the list agrees with the dots everywhere else. */
function readUnreadMarkers() {
  try {
    const raw = JSON.parse(localStorage.getItem('hermes.desktop.unreadFinishedSessions') || '{}')
    return [...new Set(Object.values(raw).flat().filter(id => typeof id === 'string'))].sort()
  } catch {
    return []
  }
}
let liveKey = ''
function syncLive() {
  const focusedRuntime = host.state.focusedSessionId.get()
  const focusedStored = host.state.focusedStoredSessionId.get()
  if (focusedRuntime && focusedStored) runtimeToStored.set(focusedRuntime, focusedStored)
  const ids = []
  for (const [runtime, busy] of Object.entries(host.state.busyBySession.get() || {})) {
    const stored = busy ? runtimeToStored.get(runtime) : null
    if (stored) ids.push(stored)
  }
  ids.sort()
  const unread = readUnreadMarkers()
  if (unread.join('|') !== unreadAtom.get().join('|')) unreadAtom.set(unread)
  const key = ids.join('|')
  if (key === liveKey) return
  // a turn that just ended may have left the chat unread: let the backend say so
  if (liveKey && liveKey.split('|').some(id => id && !ids.includes(id))) refreshSoon()
  liveKey = key
  liveAtom.set(ids)
}

let styleEl = null
let chromeEl = null
/** Chrome the plugin can quiet without touching core: the Bots tab and the profile selector are hidden by CSS keyed
 *  on core's own data-slot / data-tree-tab hooks; sidebar rows go through the nav-prefs area (re-registered on change,
 *  the previous registration disposed first). */
let navDispose = null
let navHidden = ''
function applyChrome() {
  const p = prefsAtom.get()
  const rules = []
  if (p.hideBotsTab) rules.push('[data-tree-tab="hermes-bots:pane"]{display:none!important}')
  if (p.hideRail) rules.push('[data-slot="profile-rail"],[data-slot="profile-dropdown"]{display:none!important}')
  if (chromeEl) chromeEl.textContent = rules.join('\n')
  const hide = (p.hiddenNav || []).filter(id => id !== 'capabilities')
  if (!ctxRef || (navDispose && navHidden === hide.join(','))) return
  navDispose?.()
  navHidden = hide.join(',')
  navDispose = ctxRef.register({ id: 'nav-prefs', area: SIDEBAR_NAV_PREFS_AREA, data: { hide } })
}

// ───────────────────────────── floating sides ─────────────────────────────
/** Floating sides: the outer columns of the layout leave the flow, so the chat keeps the whole width, and slide in
 *  over it when the pointer touches that screen edge, like an auto-hiding OS dock. They hide again a moment after
 *  the pointer leaves, never while focus is inside (typing in the terminal), a menu is open, or the side is pinned.
 *  Desktop draws each pane in a host anchored to its zone, so a zone that moves takes its pane with it; the hosts
 *  of a floating side are lifted above the chat by their zone id. */
const cssEscape = v => (window.CSS?.escape ? window.CSS.escape(v) : String(v).replace(/["\\]/g, '\\$&'))
const FLOAT_EDGE = 40
const FLOAT_HIDE_MS = 160 // pointer just past the panel's edge
const FLOAT_HIDE_FAR_MS = 40 // pointer clearly back in the chat
const FLOAT_FAR_PX = 90
const floatNear = {}
const FLOAT_SHOW_MS = 70
const floatState = { left: { open: false, pinned: false, groups: [] }, right: { open: false, pinned: false, groups: [] } }
let floatTimers = {}
let floatStyle = null
let floatOff = null

function sideWrappers() {
  // The row the chat sits in, climbed from the workspace: a column-root layout (Terminal deck, Quad) keeps its
  // bottom rail and never has a top or bottom child mistaken for a side.
  const ws = document.querySelector('[data-tree-tab="workspace"]')?.closest('[data-tree-group]') ||
    document.querySelector(`[data-tree-group="${cssEscape(document.querySelector('[data-pane-host="workspace"]')?.getAttribute('data-tree-group') || '')}"]:not([data-pane-host])`)
  let root = ws?.closest('[data-tree-split]')
  while (root && getComputedStyle(root).flexDirection !== 'row') root = root.parentElement?.closest('[data-tree-split]')
  if (!root) return {}
  const kids = [...root.children]
  const mainAt = kids.findIndex(el => el.contains(ws))
  if (mainAt < 0) return {}
  return { root, main: kids[mainAt], left: mainAt > 0 ? kids[0] : null, right: mainAt < kids.length - 1 ? kids[kids.length - 1] : null }
}

let floatCss = ''
function paintFloat() {
  if (!floatOff) return
  const { root, main, left, right } = sideWrappers()
  for (const el of document.querySelectorAll('[data-sqh-side], [data-sqh-main], [data-sqh-float-root]')) {
    const keep = (el === left && el.dataset.sqhSide === 'left') || (el === right && el.dataset.sqhSide === 'right') || (el === main && 'sqhMain' in el.dataset) || (el === root && 'sqhFloatRoot' in el.dataset)
    if (keep) continue
    delete el.dataset.sqhSide
    delete el.dataset.sqhOpen
    delete el.dataset.sqhMain
    delete el.dataset.sqhFloatRoot
    el.style.removeProperty('--sqh-w')
  }
  if (!root) {
    floatState.left.groups = []
    floatState.right.groups = []
    return
  }
  root.dataset.sqhFloatRoot = ''
  main.dataset.sqhMain = ''
  const rules = []
  for (const [side, el] of [['left', left], ['right', right]]) {
    const st = floatState[side]
    const groups = el ? [...el.querySelectorAll('[data-tree-group]')].map(g => g.getAttribute('data-tree-group')) : []
    if (!el || !groups.length) {
      st.groups = []
      continue
    }
    if (el.dataset.sqhSide !== side) {
      const w = Math.round(el.getBoundingClientRect().width)
      el.style.setProperty('--sqh-w', Math.max(side === 'left' ? 260 : 300, w || 0) + 'px')
      el.dataset.sqhSide = side
    }
    st.groups = groups
    const show = st.open || st.pinned
    if (show) el.dataset.sqhOpen = ''
    else delete el.dataset.sqhOpen
    // pane hosts sit outside the split tree: lift them with their side, and hide them with it so a closed side
    // can neither be focused off-screen nor shift the window
    for (const id of groups) rules.push(`[data-pane-host][data-tree-group="${cssEscape(id)}"]{z-index:46!important;background:var(--sidebar,var(--ui-bg-chrome,var(--background)));${show ? 'opacity:1;transition:opacity var(--sqh-in) ease!important;' : 'opacity:.35;visibility:hidden!important;transition:opacity var(--sqh-out) ease-in,visibility 0s linear var(--sqh-out)!important;'}}`)
  }
  const css = rules.join('\n')
  if (floatStyle && css !== floatCss) floatStyle.textContent = floatCss = css
  document.documentElement.dataset.sqhFloat = ''
}

/** What each side's zones show, from the layout Desktop persists: the active pane and whether the zone is folded. A
 *  change on a hidden side is a reveal from elsewhere (⌃`, ⌘J, ⌘G, a menu) and slides that side in. */
const sideSig = {}
function zonesOf(node, out = {}) {
  if (!node) return out
  if (node.type === 'group') out[node.id] = node.active + (node.minimized ? ':min' : '')
  else for (const c of node.children || []) zonesOf(c, out)
  return out
}
function watchReveals() {
  if (!floatOff) return
  let zones
  try {
    zones = zonesOf(JSON.parse(localStorage.getItem('hermes.desktop.layoutTree.v2') || 'null'))
  } catch {
    return
  }
  for (const side of ['left', 'right']) {
    const st = floatState[side]
    const sig = st.groups.map(id => id + '=' + (zones[id] || '')).join('|')
    if (sideSig[side] !== undefined && sig !== sideSig[side] && !sig.includes(':min') && st.groups.length && !st.open && !st.pinned) {
      st.revealed = true
      setSide(side, true)
    }
    sideSig[side] = sig
  }
}

/** A reveal from anywhere (⌃`, ⌘J, a menu, focus moving in) shows the side it lands in. */
function onFloatFocus(e) {
  for (const side of ['left', 'right']) {
    const st = floatState[side]
    if (st.open || st.pinned || !st.groups.length) continue
    const g = e.target?.closest?.('[data-tree-group]')?.getAttribute('data-tree-group')
    if (g && st.groups.includes(g)) setSide(side, true)
  }
}

const inSide = (side, x, y) => {
  const el = document.querySelector(`[data-sqh-side="${side}"]`)
  if (!el) return false
  const r = el.getBoundingClientRect()
  return x >= r.left - 8 && x <= r.right + 8 && y >= r.top && y <= r.bottom
}
const focusInSide = side => {
  const a = document.activeElement
  if (!a || a === document.body) return false
  const host = a.closest?.('[data-pane-host]')
  const group = host?.getAttribute('data-tree-group') || a.closest?.('[data-tree-group]')?.getAttribute('data-tree-group')
  return Boolean(group && floatState[side].groups.includes(group))
}
const menuOpen = () => Boolean(document.querySelector('[role="menu"], [role="dialog"], [data-radix-popper-content-wrapper]'))

function setSide(side, open) {
  clearTimeout(floatTimers[side])
  floatTimers[side] = null
  if (floatState[side].open === open) return
  floatState[side].open = open
  paintFloat()
}

function onFloatPointer(e) {
  const x = e.clientX
  const y = e.clientY
  for (const side of ['left', 'right']) {
    const st = floatState[side]
    if (!st.groups.length || st.pinned) continue
    // the band is measured from the chat's own edge, so a profile rail or a window inset never pushes it outward
    const main = document.querySelector('[data-sqh-main]')?.getBoundingClientRect()
    const atEdge = side === 'left' ? x <= (main ? Math.max(0, main.left) : 0) + FLOAT_EDGE : x >= (main ? Math.min(window.innerWidth, main.right) : window.innerWidth) - FLOAT_EDGE
    if (!st.open) {
      // armed once on entering the band and kept while the pointer moves inside it: re-arming on every move meant the
      // side only appeared once the pointer stopped, which in practice was at the window edge
      if (!atEdge || y <= 36) {
        clearTimeout(floatTimers[side])
        floatTimers[side] = null
      } else if (!floatTimers[side]) floatTimers[side] = setTimeout(() => setSide(side, true), FLOAT_SHOW_MS)
    } else if (inSide(side, x, y)) {
      clearTimeout(floatTimers[side])
      floatTimers[side] = null
      st.revealed = false
    } else if (!st.revealed) {
      // a pointer that brushed past the panel's edge gets a short grace; one clearly back in the chat hides it now
      const el = document.querySelector(`[data-sqh-side="${side}"]`)?.getBoundingClientRect()
      const far = el ? (side === 'left' ? x - el.right : el.left - x) > FLOAT_FAR_PX : true
      if (floatTimers[side] && !(far && floatNear[side])) continue
      clearTimeout(floatTimers[side])
      floatNear[side] = !far
      floatTimers[side] = setTimeout(() => {
        floatTimers[side] = null
        if (focusInSide(side) || menuOpen()) return
        setSide(side, false)
      }, far ? FLOAT_HIDE_FAR_MS : FLOAT_HIDE_MS)
    }
  }
}

/** While floating, Desktop's own side toggles (the title-bar buttons, ⌘B, ⌘J) would fold the zone to its rail of
 *  vertical tab titles inside the floating panel. They pin or release the side instead; capture phase, so core's
 *  handler never runs. A zone already folded is unfolded, so a side always floats whole. */
const SIDE_ICON = { 'codicon-layout-sidebar-left': 'left', 'codicon-layout-sidebar-right': 'right' }
function sideOfToggle(target) {
  const btn = target?.closest?.('[data-titlebar-cluster] button')
  if (!btn) return null
  for (const [cls, side] of Object.entries(SIDE_ICON)) if (btn.querySelector('.' + cls)) return side
  return null
}
function onToggleClick(e) {
  const side = sideOfToggle(e.target)
  if (!side) return
  e.stopPropagation()
  e.preventDefault()
  // every click toggles, however fast (the OS numbers a burst 1, 2, 3…); the dblclick event itself is only swallowed
  if (e.type === 'click') togglePin(side)
}
function onToggleKey(e) {
  if (!(e.metaKey || e.ctrlKey) || e.shiftKey || e.altKey) return
  const side = e.key === 'b' || e.key === 'B' ? 'left' : e.key === 'j' || e.key === 'J' ? 'right' : null
  if (!side || !floatState[side].groups.length) return
  e.stopPropagation()
  e.preventDefault()
  togglePin(side)
}
/** A side zone left folded (by a toggle before floating was on) unfolds through Desktop's own toggle once. */
function unfoldSides() {
  let tree
  try {
    tree = JSON.parse(localStorage.getItem('hermes.desktop.layoutTree.v2') || 'null')
  } catch {
    return
  }
  const folded = zonesOf(tree)
  for (const side of ['left', 'right']) {
    if (floatState[side].groups.some(id => String(folded[id] || '').endsWith(':min'))) {
      ctxRef?.runAction?.(side === 'left' ? 'view.toggleSidebar' : 'view.toggleRightSidebar')
      delete sideSig[side] // an unfold is housekeeping, not a reveal
    }
  }
}

/** Pin keeps a side shown (still floating); a second toggle lets it hide again. */
function togglePin(side) {
  clearTimeout(floatTimers[side]) // a show/hide armed by the pointer must not undo the pin a moment later
  floatTimers[side] = null
  floatState[side].revealed = false
  floatState[side].pinned = !floatState[side].pinned
  floatState[side].open = floatState[side].pinned
  paintFloat()
  return floatState[side].pinned
}

function startFloat() {
  if (floatOff) return
  floatStyle = document.createElement('style')
  floatStyle.dataset.squadHub = 'float'
  document.head.append(floatStyle)
  const onKey = e => {
    if (e.key !== 'Escape' || e.defaultPrevented) return
    for (const side of ['left', 'right']) if (floatState[side].open && !floatState[side].pinned && !focusInSide(side)) {
      floatState[side].revealed = false
      setSide(side, false)
    }
  }
  const timer = setInterval(paintFloat, 1200)
  const revealTimer = setInterval(watchReveals, 250)
  document.addEventListener('pointermove', onFloatPointer, { passive: true })
  document.addEventListener('keydown', onKey)
  document.addEventListener('focusin', onFloatFocus)
  for (const type of ['click', 'dblclick', 'pointerdown', 'mousedown']) document.addEventListener(type, onToggleClick, true)
  window.addEventListener('keydown', onToggleKey, true)
  setTimeout(unfoldSides, 400)
  floatOff = () => {
    clearInterval(timer)
    clearInterval(revealTimer)
    for (const k of Object.keys(sideSig)) delete sideSig[k]
    document.removeEventListener('pointermove', onFloatPointer)
    document.removeEventListener('keydown', onKey)
    document.removeEventListener('focusin', onFloatFocus)
    for (const type of ['click', 'dblclick', 'pointerdown', 'mousedown']) document.removeEventListener(type, onToggleClick, true)
    window.removeEventListener('keydown', onToggleKey, true)
    for (const side of ['left', 'right']) {
      clearTimeout(floatTimers[side])
      floatState[side] = { open: false, pinned: false, groups: [] }
    }
    floatTimers = {}
    floatCss = ''
    for (const el of document.querySelectorAll('[data-sqh-main], [data-sqh-float-root]')) {
      delete el.dataset.sqhMain
      delete el.dataset.sqhFloatRoot
    }
    for (const el of document.querySelectorAll('[data-sqh-side]')) {
      delete el.dataset.sqhSide
      delete el.dataset.sqhOpen
      el.style.removeProperty('--sqh-w')
    }
    delete document.documentElement.dataset.sqhFloat
    floatStyle?.remove()
    floatStyle = null
    floatOff = null
  }
  paintFloat()
}

/** A double-click on an env file in Desktop's file tree hits its sensitive-file block ("Preview unavailable"): open
 *  it in the system editor instead. Capture phase, so core's handler never runs for these rows; every other file
 *  keeps core's preview. */
function onTreeDoubleClick(e) {
  if (prefsAtom.get().envDoubleClick === false) return
  const item = e.target?.closest?.('[role="treeitem"]')
  if (!item || item.hasAttribute('aria-expanded')) return // a folder named .env (a virtualenv) keeps core's toggle
  const path = item.querySelector('[title]')?.getAttribute('title') || ''
  if (!path || !isEnvFile(baseName(path))) return
  e.stopPropagation()
  e.preventDefault()
  ctxRef?.os?.openExternal?.(path).then(ok => {
    if (ok === false) host.notify({ kind: 'error', message: fmt(lang().envOpenFailed) })
  })
}

let lastRoot = ''
/** Picking the Squads layout opens files and the terminal once. Desktop's apply left the files zone closed when the
 *  pane had been closed before (seen live), so the pick says what it places. */
function watchLayoutPick() {
  const root = document.querySelector('[data-tree-split]')?.getAttribute('data-tree-split') || ''
  if (root === lastRoot) return
  const picked = root === SQUADS_LAYOUT.id && lastRoot !== ''
  lastRoot = root
  if (!picked) return
  host.revealPane('files')
  setTimeout(() => host.revealPane('terminal'), 250)
}

const stopFloat = () => floatOff?.()
const applyFloat = () => (prefsAtom.get().floatSides ? startFloat() : stopFloat())

/** A plugin registers a layout but cannot apply one (only the picker and set_theme do): take the user to the picker. */
function applySquadsLayout() {
  host.navigate('/settings?tab=appearance&page=window-layout')
  host.notify({ kind: 'info', message: fmt(lang().layoutPick) })
}

/** The "Squads" layout (no Review: that pane follows the chat and each agent opens its own): the squad list left, the chat, then files over a short terminal on the right. */
const SQUADS_LAYOUT = {
  type: 'split', id: 'sqh-root', orientation: 'row', weights: [1, 3.6, 1.3],
  children: [
    { type: 'group', id: 'sqh-left', panes: ['squad-hub:pane', 'sessions'], active: 'squad-hub:pane' },
    { type: 'group', id: 'sqh-main', panes: ['workspace'], active: 'workspace' },
    {
      type: 'split', id: 'sqh-right', orientation: 'column', weights: [3.4, 1],
      children: [
        { type: 'group', id: 'sqh-files', panes: ['files'], active: 'files' },
        { type: 'group', id: 'sqh-term', panes: ['terminal'], active: 'terminal' }
      ]
    }
  ]
}

// ───────────────────────────── data ─────────────────────────────
const SOURCES = 'desktop,tui,cli'
const refresh = () => queryClient.invalidateQueries({ queryKey: ['squad-hub'] }, { cancelRefetch: false })
let refreshTimer = null
/** Gateway events (state.db moves on every kanban run) coalesce into one refetch at most every 2.5 s. */
const refreshSoon = () => {
  if (refreshTimer) return
  refreshTimer = setTimeout(() => {
    refreshTimer = null
    refresh()
  }, 2500)
}

/** A chat started from "+" has no row in the session DB until its first message; it is listed from here until
 *  the DB has it (or ten minutes pass), so the tree answers the click at once, in the lane it was started in. */
const pendingChats = new Map()

async function loadChats() {
  const r = await window.hermesDesktop.api({
    path: `/api/profiles/sessions?limit=500&offset=0&min_messages=0&archived=exclude&order=recent&profile=all&sources=${SOURCES}`
  })
  const rows = r.sessions || []
  const now = Date.now() / 1000
  for (const [id, chat] of pendingChats) {
    if (rows.some(x => x.id === id) || now - chat.started_at > 600) pendingChats.delete(id)
  }
  return [...pendingChats.values(), ...rows].filter(x => isHumanChat(x))
}

/** The raw snapshot: every profile, the human chats, and each candidate bot's projects. Which bots show is decided
 *  at render from the prefs (`visibleBots`), so hiding or pinning a bot never waits for a refetch. */
async function loadSnapshot() {
  const [profilesRes, chats] = await Promise.all([rpc('profiles.list', {}), loadChats()])
  const profiles = (profilesRes.profiles || []).map(p => ({ name: p.name, is_default: p.is_default, display_name: p.display_name, ui_meta: p.ui_meta }))
  const humanBy = {}
  for (const s of chats) humanBy[s.profile] = (humanBy[s.profile] || 0) + 1
  // Projects for every bot that can show (hidden ones too, so unhiding is instant); a pinned worker needs a refetch.
  const candidates = visibleBots(profiles, humanBy, { pinned: prefsAtom.get().pinned })
  const projectsBy = {}
  await Promise.all(
    candidates.map(async b => {
      try {
        projectsBy[b.name] = (await rpc('projects.list', { profile: b.name })).projects || []
      } catch {
        projectsBy[b.name] = []
      }
    })
  )
  const snap = { at: Date.now(), profiles, humanBy, chats, projectsBy }
  persistSnapshot(snap)
  return snap
}

let lastPersist = 0
/** The cached snapshot paints the list before the first fetch; written at most every 10 s. */
function persistSnapshot(snap) {
  if (Date.now() - lastPersist < 10000) return
  lastPersist = Date.now()
  try {
    storage?.set('snapshot.v3', snap)
  } catch {
    /* quota */
  }
}

function readCachedSnapshot() {
  const snap = storage?.get('snapshot.v3', null)
  return snap && Array.isArray(snap.profiles) && Array.isArray(snap.chats) && snap.projectsBy ? snap : undefined
}

const snapshotQuery = () => ({
  queryKey: SNAPSHOT_KEY,
  queryFn: loadSnapshot,
  initialData: readCachedSnapshot,
  initialDataUpdatedAt: 0,
  staleTime: 15000,
  refetchInterval: 30000,
  refetchOnWindowFocus: true
})

const botsOf = (snap, prefs) => (snap ? visibleBots(snap.profiles, snap.humanBy, prefs) : [])

const botLast = tree =>
  Math.max(0, ...tree.loose.map(sessionTime), ...tree.projects.map(p => p.last))

const folderPathsOf = snap => {
  const set = new Set()
  for (const list of Object.values(snap?.projectsBy || {})) {
    for (const p of list) {
      if (p.archived) continue
      for (const f of p.folders || []) set.add(trimPath(f.path))
      if (p.primary_path) set.add(trimPath(p.primary_path))
    }
  }
  return [...set].sort()
}

/** `git worktree list` runs on the local disk through Electron: a slow or blocked folder must never stall
 *  the tree, so the tree paints first and every repo has its own deadline. */
async function loadWorktrees(paths, ms = 6000) {
  const g = git()
  const out = {}
  if (!g?.worktreeList) return out
  await Promise.all(
    paths.map(async path => {
      try {
        out[path] = await Promise.race([g.worktreeList(path), new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms))])
      } catch {
        /* not a git folder, or too slow */
      }
    })
  )
  return out
}

// ───────────────────────────── actions ─────────────────────────────
async function openChat(bot, id, intent = 'tab') {
  try {
    await host.openSession(id, { profile: bot, intent })
  } catch (e) {
    host.notifyError(e, 'Could not open the chat')
  }
}

async function newChat(bot, cwd) {
  try {
    const params = { profile: bot, source: 'desktop', cols: 96 }
    if (cwd) Object.assign(params, { cwd, cwd_explicit: true })
    const created = host.requestProfile
      ? await host.requestProfile(bot, 'session.create', params, undefined, { spawnPriority: 'foreground' })
      : await rpc('session.create', params)
    if (created.session_id) runtimeToStored.set(created.session_id, created.stored_session_id)
    pendingChats.set(created.stored_session_id, {
      id: created.stored_session_id,
      profile: bot,
      source: 'desktop',
      title: '',
      message_count: 0,
      started_at: Date.now() / 1000,
      last_active: Date.now() / 1000,
      cwd: cwd || '',
      git_repo_root: '',
      git_branch: created.info?.branch || ''
    })
    refresh()
    await host.openSession(created.stored_session_id, { profile: bot, intent: 'tab' })
    haptic?.('tap')
  } catch (e) {
    host.notifyError(e, 'Could not start the chat')
  }
}

const pickFolders = async (title, defaultPath) =>
  (await window.hermesDesktop?.selectPaths?.({ title, directories: true, multiple: true, defaultPath })) || []

/** Open a bot's own page (cron, messaging, kanban). Those pages follow the window's profile, so the profile is
 *  switched first; the switch is the gateway swap only (tens of ms), no pane or list reloads. */
async function openBotPage(bot, path) {
  try {
    await host.ensureAgent(null, bot)
    host.navigate(path)
  } catch (e) {
    host.notifyError(e, 'Could not open the page')
  }
}

function focusedChat() {
  const id = host.state.focusedStoredSessionId.get()
  const snap = queryClient.getQueryData(SNAPSHOT_KEY)
  return { id, session: snap?.chats?.find(c => c.id === id) || null, snap }
}

/** Previews are remembered per chat: a closed preview is one click to reopen, no prompt to the bot. */
const runtimeToStored = new Map()
let openDialog = null
let reopening = 0
function reopenPreview(entry) {
  // The reopen is the app's own `preview.open` handler, fed the event the agent's tool emits; the plugin's own
  // listener skips it (the entry is already remembered under its chat).
  const hub = host.getGateway()?.events
  if (!hub?.dispatch) {
    host.notify({ kind: 'error', message: 'This Desktop cannot reopen previews from a plugin.' })
    return
  }
  reopening++
  try {
    hub.dispatch({ type: 'preview.open', payload: { url: entry.url, label: entry.label || undefined } })
  } finally {
    reopening--
  }
}

// ───────────────────────────── UI pieces ─────────────────────────────
function IconBtn({ icon, label, onClick }) {
  return jsx(Tip, {
    label,
    children: jsx('button', {
      type: 'button',
      className: 'sqh-ib',
      'aria-label': label,
      onClick: e => {
        e.stopPropagation()
        onClick(e)
      },
      children: jsx(Codicon, { name: icon, size: '0.8125rem' })
    })
  })
}

function MenuBtn({ items, icon = 'ellipsis', label = 'More' }) {
  const shown = items.filter(Boolean)
  if (!shown.length) return null
  return jsxs(DropdownMenu, {
    children: [
      jsx(DropdownMenuTrigger, {
        asChild: true,
        children: jsx('button', { type: 'button', className: 'sqh-ib', 'aria-label': label, onClick: e => e.stopPropagation(), children: jsx(Codicon, { name: icon, size: '0.8125rem' }) })
      }),
      jsx(DropdownMenuContent, {
        align: 'end',
        children: shown.map((it, i) =>
          it === 'sep' ? jsx(DropdownMenuSeparator, {}, 'sep' + i) : jsx(DropdownMenuItem, { onSelect: it.run, disabled: it.disabled, children: it.label }, it.label + i)
        )
      })
    ]
  })
}

/** A line glyph in the row's own colour (folders, projects, worktrees): Lucide, like the bot tiles. */
function Glyph({ name, size = 14, color, className = '' }) {
  return jsx('svg', {
    viewBox: '0 0 24 24',
    width: size,
    height: size,
    fill: 'none',
    stroke: color || 'currentColor',
    strokeWidth: 1.8,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    className: 'sqh-glyph ' + className,
    'aria-hidden': true,
    dangerouslySetInnerHTML: { __html: UI_ICONS[name] || LUCIDE[name] || UI_ICONS.folder }
  })
}

function IconTile({ icon, size = 18, title }) {
  const name = LUCIDE[icon] ? icon : 'bot'
  const tint = ICON_TINT[name] || '#b4befe'
  return h(
    'span',
    { className: 'sqh-tile', title, style: { width: size, height: size, background: `linear-gradient(140deg, ${tint}, color-mix(in srgb, ${tint} 72%, #1e1e2e))` } },
    jsx('svg', {
      viewBox: '0 0 24 24',
      width: Math.round(size * 0.66),
      height: Math.round(size * 0.66),
      fill: 'none',
      stroke: '#1e1e2e',
      strokeWidth: 2.1,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
      'aria-hidden': true,
      dangerouslySetInnerHTML: { __html: LUCIDE[name] }
    })
  )
}

function Row({ depth, active, onClick, className = '', children }) {
  return h('div', { className: 'sqh-row ' + className, 'data-active': active ? 'true' : 'false', style: { paddingLeft: 6 + depth * 14 }, onClick, role: 'button' }, children)
}

function ChatRow({ bot, session, depth, activeId, ctl, hint }) {
  const t = useT()
  const previews = useValue(previewsAtom)[session.id] || []
  const items = [
    previews.length
      ? { label: t('previews') + ' (' + previews.length + ')', disabled: true, run: () => {} }
      : null,
    ...previews.slice(0, 5).map(p => ({ label: '↗ ' + (p.label || p.url).slice(0, 48), run: () => reopenPreview(p) })),
    previews.length ? 'sep' : null,
    { label: t('rename'), run: () => ctl.renameChat(bot, session) },
    { label: t('openWindow'), run: () => openChat(bot.name, session.id, 'window') },
    session.cwd ? { label: t('copyPath'), run: () => ctxRef?.os?.writeClipboard?.(session.cwd) } : null,
    'sep',
    { label: t('archive'), run: () => ctl.archiveChat(bot, session) }
  ]
  return h(
    Row,
    { depth, active: activeId === session.id, onClick: () => openChat(bot.name, session.id) },
    jsx(SessionStatusDot, { storedSessionId: session.id, session }),
    h('span', { className: 'sqh-label', title: session.title || '' }, session.title || session.preview || 'New chat'),
    hint ? h('span', { className: 'sqh-where', title: hint }, hint.split(' · ').pop()) : null,
    previews.length ? h('span', { className: 'sqh-pv', title: t('previews') }, jsx(Codicon, { name: 'link-external', size: '0.625rem' })) : null,
    h('span', { className: 'sqh-actions', onClick: stop, onPointerDown: stop }, jsx(MenuBtn, { items })),
    h('span', { className: 'sqh-age' }, shortAge(sessionTime(session)))
  )
}

function LaneBlock({ bot, folder, lane, depth, activeId, ctl, query }) {
  const t = useT()
  const key = `lane:${bot.name}:${lane.key}`
  const collapsed = useValue(collapsedAtom)
  const open = query.trim() ? true : isOpen(collapsed, key, true)
  return h(
    'div',
    {},
    h(
      Row,
      { depth, className: 'sqh-lane', onClick: () => toggleCollapsed(key, false) },
      jsx(DisclosureCaret, { open }),
      jsx(Glyph, { name: 'git-branch', size: 13, className: lane.main ? '' : 'sqh-wt' }),
      h('span', { className: 'sqh-label' }, lane.main ? 'main' : lane.label, lane.branch && lane.branch !== lane.label && !(lane.main && lane.branch === 'main') ? h('span', { className: 'sqh-branch' }, ' ', lane.branch) : null),
      h(
        'span',
        { className: 'sqh-actions', onClick: stop, onPointerDown: stop },
        jsx(IconBtn, { icon: 'add', label: t('newChatHere'), onClick: () => newChat(bot.name, lane.path) }),
        jsx(MenuBtn, {
          items: [
            { label: t('reveal'), run: () => ctxRef?.os?.revealPath?.(lane.path) },
            { label: t('copyPath'), run: () => ctxRef?.os?.writeClipboard?.(lane.path) },
            !lane.main && !isKanbanWorktree(lane.path) && git()?.worktreeRemove ? 'sep' : null,
            !lane.main && !isKanbanWorktree(lane.path) && git()?.worktreeRemove ? { label: t('removeWorktree'), run: () => ctl.removeWorktree(folder, lane) } : null
          ]
        })
      ),
      h('span', { className: 'sqh-age' }, shortAge(laneTime(lane)))
    ),
    open ? lane.sessions.map(s => h(ChatRow, { key: s.id, bot, session: s, depth: depth + 1, activeId, ctl })) : null,
    open && !lane.sessions.length ? h('div', { className: 'sqh-empty', style: { paddingLeft: 6 + (depth + 1) * 14 + 8 } }, t('noChats')) : null
  )
}

/** The dot a closed folder or project wears when something inside needs you: core's own status dot of the loudest
 *  chat (so the colour means what it means everywhere else) and how many there are. */
function ActivityBadge({ items }) {
  if (!items.length) return null
  return h(
    'span',
    { className: 'sqh-activity', title: items.map(x => x.session.title || x.session.preview || '').filter(Boolean).slice(0, 5).join('\n') },
    jsx(SessionStatusDot, { storedSessionId: items[0].session.id, session: items[0].session }),
    items.length > 1 ? h('span', {}, items.length) : null
  )
}

/** What needs you, as the model reads it: running turns, chats Desktop flagged unread, and the one in view. */
function useAttention(focused) {
  const live = useValue(liveAtom)
  const unread = useValue(unreadAtom)
  return useMemo(() => ({ live, unread, focused }), [live, unread, focused])
}

const laneHint = (folder, lane, multi) => [multi ? folder.label : '', lane.main ? '' : lane.label].filter(Boolean).join(' · ')

function FolderBlock({ bot, project, folder, activeId, ctl, query, attention }) {
  const t = useT()
  const key = `folder:${bot.name}:${project.id}:${folder.path}`
  const collapsed = useValue(collapsedAtom)
  const active = needsYou(activeIn(folder, attention))
  const wide = false
  const open = query.trim() ? true : isOpen(collapsed, key, wide)
  const chats = folder.lanes.reduce((n, l) => n + l.sessions.length, 0)
  return h(
    'div',
    {},
    h(
      Row,
      { depth: 2, className: 'sqh-folder', onClick: () => toggleCollapsed(key, !wide) },
      jsx(DisclosureCaret, { open }),
      jsx(Glyph, { name: folderIcon(folder, folder.repo), size: 13 }),
      h('span', { className: 'sqh-label', title: folder.path }, folder.label),
      open ? null : jsx(ActivityBadge, { items: active }),
      h(
        'span',
        { className: 'sqh-actions', onClick: stop, onPointerDown: stop },
        jsx(IconBtn, { icon: 'add', label: t('newChatIn', folder.label), onClick: () => newChat(bot.name, folder.path) }),
        git()?.worktreeAdd ? jsx(IconBtn, { icon: 'git-branch-create', label: t('newWorktree'), onClick: () => ctl.newWorktree(bot, folder) }) : null,
        jsx(MenuBtn, { items: [{ label: t('envFiles'), run: () => ctl.envFiles(folder) }, { label: t('reveal'), run: () => ctxRef?.os?.revealPath?.(folder.path) }, 'sep', { label: t('removeFolder'), run: () => ctl.removeFolder(bot, project, folder) }] })
      ),
      open || active.length ? null : h('span', { className: 'sqh-age' }, chats ? shortAge(laneTime({ sessions: folder.lanes.flatMap(l => l.sessions) })) : '')
    ),
    open ? folder.lanes.map(l => h(LaneBlock, { key: l.key, bot, folder, lane: l, depth: 3, activeId, ctl, query })) : null
  )
}

/** A project wears a small filled tile (its own Desktop icon and colour when set, else a stack in its bot's tint),
 *  so it never reads as one of its folders, which are line glyphs. */
function ProjectMark({ project, bot }) {
  const prefs = useValue(prefsAtom)
  const tint = project.color || ICON_TINT[iconFor(bot, prefs.icons || {})] || '#b4befe'
  return h(
    'span',
    { className: 'sqh-pmark', style: { color: tint, background: `color-mix(in srgb, ${tint} 22%, transparent)` } },
    project.icon ? jsx(Codicon, { name: project.icon, size: '0.6875rem' }) : jsx(Glyph, { name: 'layers', size: 11, color: 'currentColor' })
  )
}

function ProjectBlock({ bot, project, activeId, ctl, query }) {
  const t = useT()
  const key = `proj:${bot.name}:${project.id}`
  const collapsed = useValue(collapsedAtom)
  const attention = useAttention(activeId)
  const multi = project.folders.length > 1
  const wide = projectOpensWide(project)
  const open = query.trim() ? true : isOpen(collapsed, key, wide)
  const primary = project.folders.find(f => f.primary) || project.folders[0]
  // One folder holding only its main checkout: the chats hang straight under the project, no "main" row.
  const flat = project.folders.length === 1 && project.folders[0].lanes.length === 1 && project.folders[0].lanes[0].main ? project.folders[0].lanes[0] : null
  // A project with several folders lists what needs you right under it, each chat with where it lives; its folders
  // start folded (those chats are already one click away) and a folded folder still wears their dot.
  const digest = query.trim() ? [] : projectDigest(project, attention, open)
  return h(
    'div',
    {},
    h(
      Row,
      { depth: 1, className: 'sqh-proj', onClick: () => toggleCollapsed(key, !wide) },
      jsx(DisclosureCaret, { open }),
      jsx(ProjectMark, { project, bot }),
      h('span', { className: 'sqh-label' }, project.name),
      multi && !open ? h('span', { className: 'sqh-count', title: t('folders') }, project.folders.length) : null,
      h(
        'span',
        { className: 'sqh-actions', onClick: stop, onPointerDown: stop },
        jsx(IconBtn, { icon: 'add', label: t('newChatIn', project.name), onClick: () => newChat(bot.name, primary?.path) }),
        jsx(MenuBtn, {
          items: [
            { label: t('addFolder'), run: () => ctl.addFolder(bot, project) },
            git()?.worktreeAdd && !multi && primary ? { label: t('newWorktree'), run: () => ctl.newWorktree(bot, primary) } : null,
            { label: t('openBrowser'), run: () => ctxRef?.runAction?.('view.showBrowser') },
            !multi && primary ? { label: t('envFiles'), run: () => ctl.envFiles(primary) } : null,
            'sep',
            { label: t('appearance'), run: () => ctl.appearance(bot, project) },
            { label: t('renameProject'), run: () => ctl.renameProject(bot, project) },
            { label: t('removeProject'), run: () => ctl.removeProject(bot, project) }
          ]
        })
      ),
      h('span', { className: 'sqh-age' }, shortAge(project.last))
    ),
    digest.map(x => h(ChatRow, { key: x.session.id, bot, session: x.session, depth: 2, activeId, ctl, hint: laneHint(x.folder, x.lane, multi) })),
    open && flat
      ? [
          ...flat.sessions.map(sx => h(ChatRow, { key: sx.id, bot, session: sx, depth: 2, activeId, ctl })),
          flat.sessions.length ? null : h('div', { key: 'empty', className: 'sqh-empty' }, t('noChats'))
        ]
      : null,
    open && !flat
      ? multi
        ? project.folders.map(f => h(FolderBlock, { key: f.path, bot, project, folder: f, activeId, ctl, query, attention }))
        : project.folders.map(f => h('div', { key: f.path }, f.lanes.map(l => h(LaneBlock, { key: l.key, bot, folder: f, lane: l, depth: 2, activeId, ctl, query }))))
      : null
  )
}

function BotBlock({ tree, activeId, ctl, query }) {
  const t = useT()
  const { bot } = tree
  const key = `bot:${bot.name}`
  const collapsed = useValue(collapsedAtom)
  const prefs = useValue(prefsAtom)
  const open = query.trim() ? true : isOpen(collapsed, key, true)
  const [looseToggled, setLoose] = useState(null)
  const [looseLimit, setLooseLimit] = useState(30)
  const looseOpen = query.trim() ? true : looseToggled === null ? false : looseToggled
  const pinned = prefs.pinned.includes(bot.name)
  const attention = useAttention(activeId)
  const digest = open ? [] : botDigest(tree, attention)
  return h(
    'div',
    {},
    h(
      Row,
      { depth: 0, className: 'sqh-bot', onClick: () => toggleCollapsed(key, false) },
      jsx(DisclosureCaret, { open }),
      jsx(IconTile, { icon: iconFor(bot, prefs.icons || {}) }),
      h('span', { className: 'sqh-label' }, bot.title),
      h(
        'span',
        { className: 'sqh-actions', onClick: stop, onPointerDown: stop },
        jsx(IconBtn, { icon: 'add', label: t('newChatWith', bot.title), onClick: () => newChat(bot.name) }),
        jsx(MenuBtn, {
          items: [
            { label: t('newProject'), run: () => ctl.newProject(bot) },
            'sep',
            { label: t('scheduled'), run: () => openBotPage(bot.name, '/cron') },
            { label: t('messaging'), run: () => openBotPage(bot.name, '/messaging') },
            { label: t('kanban'), run: () => openBotPage(bot.name, '/kanban') },
            { label: t('capabilities'), run: () => ctl.capabilities(bot) },
            'sep',
            { label: pinned ? t('unpin') : t('pinTop'), run: () => { refreshSoon(); savePrefs({ pinned: pinned ? prefs.pinned.filter(n => n !== bot.name) : [...prefs.pinned, bot.name], order: pinned ? prefs.order : [bot.name, ...prefs.order.filter(n => n !== bot.name)] }) } },
            bot.role === 'default' ? null : { label: t('hideBot'), run: () => { savePrefs({ hidden: [...prefs.hidden, bot.name] }) } }
          ]
        })
      )
    ),
    digest.map(x => h(ChatRow, { key: x.session.id, bot, session: x.session, depth: 1, activeId, ctl, hint: whereOf(x) })),
    open ? tree.projects.map(p => h(ProjectBlock, { key: p.id, bot, project: p, activeId, ctl, query })) : null,
    open && !tree.projects.length && !tree.loose.length
      ? h('div', { className: 'sqh-empty' }, t('noProjects'), ' · ', h('a', { href: '#', onClick: e => { e.preventDefault(); ctl.newProject(bot) }, style: { color: 'var(--ui-accent)' } }, t('createOne')))
      : null,
    open && tree.loose.length && !tree.projects.length
      ? tree.loose.slice(0, looseLimit).map(sx => h(ChatRow, { key: sx.id, bot, session: sx, depth: 1, activeId, ctl }))
      : null,
    open && tree.loose.length && tree.projects.length
      ? [
          h(Row, { key: 'loose', depth: 1, className: 'sqh-lane', onClick: () => setLoose(!looseOpen) }, jsx(DisclosureCaret, { open: looseOpen }), jsx(Codicon, { name: 'comment-discussion', size: '0.8125rem' }), h('span', { className: 'sqh-label' }, t('outside')), h('span', { className: 'sqh-age' }, tree.loose.length)),
          looseOpen ? tree.loose.slice(0, looseLimit).map(sx => h(ChatRow, { key: sx.id, bot, session: sx, depth: 2, activeId, ctl })) : null
        ]
      : null,
    open && (looseOpen || !tree.projects.length) && tree.loose.length > looseLimit
      ? h('div', { className: 'sqh-empty' }, h('a', { href: '#', onClick: e => { e.preventDefault(); setLooseLimit(looseLimit + 30) }, style: { color: 'var(--ui-accent)' } }, t('showMore', tree.loose.length - looseLimit)))
      : null
  )
}

/** A squad that has no manager yet: its bots sit under the squad's Desktop section. */
function GroupBlock({ section, members, activeId, ctl, query }) {
  const key = 'group:' + section
  const collapsed = useValue(collapsedAtom)
  const prefs = useValue(prefsAtom)
  const open = query.trim() ? true : isOpen(collapsed, key, true)
  const attention = useAttention(activeId)
  const digest = open ? [] : sortByAttention(members.flatMap(tr => botDigest(tr, attention).map(x => ({ ...x, bot: tr.bot }))))
  return h(
    'div',
    {},
    h(
      Row,
      { depth: 0, className: 'sqh-bot sqh-group', onClick: () => toggleCollapsed(key, false) },
      jsx(DisclosureCaret, { open }),
      jsx(IconTile, { icon: groupIconFor(section, prefs.icons || {}) }),
      h('span', { className: 'sqh-label' }, section),
      h('span', { className: 'sqh-age' }, members.length)
    ),
    digest.map(x => h(ChatRow, { key: x.session.id, bot: x.bot, session: x.session, depth: 1, activeId, ctl, hint: [x.bot.title, whereOf(x)].filter(Boolean).join(' · ') })),
    open ? h('div', { className: 'sqh-group-body' }, members.map(tr => h(BotBlock, { key: tr.bot.name, tree: tr, activeId, ctl, query }))) : null
  )
}

// ───────────────────────────── dialogs ─────────────────────────────
function FolderChips({ folders, onRemove, t }) {
  return h('div', { style: { display: 'grid', gap: 4 } }, folders.map((f, i) => h('div', { key: f, className: 'sqh-chip' }, jsx(Codicon, { name: 'folder', size: '0.8125rem' }), h('span', { title: f }, f), i === 0 ? h('em', { className: 'sqh-hint' }, t('primary')) : null, jsx(IconBtn, { icon: 'close', label: t('remove'), onClick: () => onRemove(f) }))))
}

function ProjectDialog({ state, close }) {
  const t = useT()
  const [name, setName] = useState('')
  const [folders, setFolders] = useState([])
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    setName('')
    setFolders([])
  }, [state?.bot?.name])
  if (!state) return null
  const submit = async () => {
    setBusy(true)
    try {
      await rpc('projects.create', { profile: state.bot.name, name: name.trim(), folders, primary_path: folders[0] })
      await refresh()
      close()
    } catch (e) {
      host.notifyError(e, 'Could not create the project')
    } finally {
      setBusy(false)
    }
  }
  return jsx(Dialog, {
    open: true,
    onOpenChange: o => !o && close(),
    children: jsxs(DialogContent, {
      children: [
        jsxs(DialogHeader, { children: [jsx(DialogTitle, { children: t('projectIn', state.bot.title) }), jsx(DialogDescription, { children: t('projectHelp') })] }),
        h(
          'div',
          { className: 'sqh-form' },
          h('label', {}, t('name'), jsx(Input, { value: name, autoFocus: true, onChange: e => setName(e.target.value), placeholder: t('projectName') })),
          h('label', {}, t('folders'), folders.length ? jsx(FolderChips, { folders, t, onRemove: f => setFolders(folders.filter(x => x !== f)) }) : h('span', { className: 'sqh-hint' }, t('none'))),
          jsx(Button, { variant: 'outline', onClick: async () => { const picked = await pickFolders(t('addFolder')); setFolders(prev => [...new Set([...prev, ...picked])]) }, children: t('addFolder') })
        ),
        jsxs(DialogFooter, { children: [jsx(Button, { variant: 'ghost', onClick: close, children: t('cancel') }), jsx(Button, { disabled: busy || !name.trim() || !folders.length, onClick: submit, children: busy ? t('creating') : t('create') })] })
      ]
    })
  })
}

function WorktreeDialog({ state, close }) {
  const t = useT()
  const [name, setName] = useState('')
  const [branch, setBranch] = useState('')
  const [base, setBase] = useState('')
  const [bases, setBases] = useState([])
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!state) return
    setName('')
    setBranch('')
    setBase('')
    git()?.baseBranchList?.(state.folder.path).then(list => {
      setBases(list)
      setBase((list.find(b => b.isDefault) || list[0])?.name || '')
    }).catch(() => setBases([]))
  }, [state?.folder?.path])
  if (!state) return null
  const slug = slugify(name)
  const submit = async () => {
    setBusy(true)
    try {
      const res = await git().worktreeAdd(state.folder.path, { name: slug, branch: branch.trim() || undefined, base: base || undefined })
      await refresh()
      close()
      host.notify({ kind: 'success', message: t('worktreeReady', res.branch) })
    } catch (e) {
      host.notifyError(e, 'Could not create the worktree')
    } finally {
      setBusy(false)
    }
  }
  return jsx(Dialog, {
    open: true,
    onOpenChange: o => !o && close(),
    children: jsxs(DialogContent, {
      children: [
        jsxs(DialogHeader, { children: [jsx(DialogTitle, { children: t('worktreeIn', state.folder.label) }), jsx(DialogDescription, { children: t('worktreeHelp') })] }),
        h(
          'div',
          { className: 'sqh-form' },
          h('label', {}, t('name'), jsx(Input, { value: name, autoFocus: true, onChange: e => setName(e.target.value), placeholder: 'checkout-redesign' })),
          h('label', {}, t('branch'), jsx(Input, { value: branch, onChange: e => setBranch(e.target.value), placeholder: slug ? 'hermes/' + slug : 'hermes/<name>' })),
          bases.length
            ? h('label', {}, t('startFrom'), jsxs(Select, { value: base, onValueChange: setBase, children: [jsx(SelectTrigger, { children: jsx(SelectValue, {}) }), jsx(SelectContent, { children: bases.map(b => jsx(SelectItem, { value: b.name, children: b.name + (b.isDefault ? ' ' + t('defaultTag') : '') }, b.name)) })] }))
            : null
        ),
        jsxs(DialogFooter, { children: [jsx(Button, { variant: 'ghost', onClick: close, children: t('cancel') }), jsx(Button, { disabled: busy || !slug, onClick: submit, children: busy ? t('creating') : t('create') })] })
      ]
    })
  })
}

/** Run a dialog action: report a failure and keep the dialog; close only on success. */
async function runAction(state, close, setBusy, ...args) {
  setBusy(true)
  try {
    await state.run(...args)
    close()
  } catch (e) {
    host.notifyError(e, state.title)
  } finally {
    setBusy(false)
  }
}

function TextDialog({ state, close }) {
  const t = useT()
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => setValue(state?.value || ''), [state])
  if (!state) return null
  const submit = () => value.trim() && !busy && runAction(state, close, setBusy, value.trim())
  return jsx(Dialog, {
    open: true,
    onOpenChange: o => !o && close(),
    children: jsxs(DialogContent, {
      children: [
        jsx(DialogHeader, { children: jsx(DialogTitle, { children: state.title }) }),
        jsx(Input, { value, autoFocus: true, onChange: e => setValue(e.target.value), onKeyDown: e => { if ((isSubmitEnter ? isSubmitEnter(e) : e.key === 'Enter')) { e.preventDefault(); submit() } } }),
        jsxs(DialogFooter, { children: [jsx(Button, { variant: 'ghost', onClick: close, children: t('cancel') }), jsx(Button, { disabled: busy || !value.trim(), onClick: submit, children: t('save') })] })
      ]
    })
  })
}

/** The glyphs Desktop's own project Appearance offers, so a pick here shows the same in Sessions. */
const PROJECT_GLYPHS = ['folder-library', 'repo', 'rocket', 'beaker', 'flame', 'star-full', 'heart', 'zap', 'target', 'lightbulb', 'tools', 'device-desktop', 'device-mobile', 'terminal', 'dashboard', 'globe', 'broadcast', 'cloud', 'database', 'package', 'book', 'organization', 'bug', 'shield']

function LookDialog({ state, close }) {
  const t = useT()
  const [icon, setIcon] = useState('')
  const [color, setColor] = useState('')
  useEffect(() => {
    setIcon(state?.project?.icon || '')
    setColor(state?.project?.color || '')
  }, [state])
  if (!state) return null
  const save = async () => {
    try {
      await rpc('projects.update', { profile: state.bot.name, id: state.project.id, icon: icon || '', color: color || '' })
      await refresh()
      close()
    } catch (e) {
      host.notifyError(e, 'Could not save the appearance')
    }
  }
  return jsx(Dialog, {
    open: true,
    onOpenChange: o => !o && close(),
    children: jsxs(DialogContent, {
      children: [
        jsxs(DialogHeader, { children: [jsx(DialogTitle, { children: t('appearanceOf', state.project.name) }), jsx(DialogDescription, { children: t('appearanceHelp') })] }),
        h(
          'div',
          { className: 'sqh-look' },
          h('span', { className: 'sqh-pmark sqh-pmark-lg', style: { color: color || 'var(--ui-accent)', background: `color-mix(in srgb, ${color || 'var(--ui-accent)'} 22%, transparent)` } }, icon ? jsx(Codicon, { name: icon, size: '1.1rem' }) : jsx(Glyph, { name: 'layers', size: 18, color: 'currentColor' })),
          h('div', { className: 'sqh-glyphgrid' }, ['', ...PROJECT_GLYPHS].map(name => h('button', { key: name || 'none', type: 'button', className: 'sqh-ib', 'data-on': icon === name ? 'true' : 'false', title: name || t('defaultIcon'), onClick: () => setIcon(name) }, name ? jsx(Codicon, { name, size: '0.875rem' }) : jsx(Glyph, { name: 'layers', size: 14 }))))
        ),
        ColorSwatches && PROFILE_SWATCHES ? jsx(ColorSwatches, { swatches: PROFILE_SWATCHES, value: color || null, onChange: c => setColor(c || ''), clearLabel: t('defaultColor') }) : null,
        jsxs(DialogFooter, { children: [jsx(Button, { variant: 'ghost', onClick: close, children: t('cancel') }), jsx(Button, { onClick: save, children: t('save') })] })
      ]
    })
  })
}

/** A folder's env files (`.env`, `.env.local`…). Desktop keeps them out of its own viewer on purpose (they hold
 *  secrets), so they open in the system's editor for that file type; the plugin never reads them. */
function EnvDialog({ state, close }) {
  const t = useT()
  const [files, setFiles] = useState(null)
  useEffect(() => {
    if (!state) return
    setFiles(null)
    if (!window.hermesDesktop?.readDir) {
      setFiles([])
      return
    }
    window.hermesDesktop.readDir(state.folder.path)
      .then(r => setFiles((r?.entries || []).filter(e => !e.isDirectory && isEnvFile(e.name)).map(e => e.path)))
      .catch(() => setFiles([]))
  }, [state?.folder?.path])
  if (!state) return null
  const open = async path => {
    const ok = await ctxRef?.os?.openExternal?.(path)
    if (ok === false) host.notify({ kind: 'error', message: t('envOpenFailed') })
    else close()
  }
  return jsx(Dialog, {
    open: true,
    onOpenChange: o => !o && close(),
    children: jsxs(DialogContent, {
      children: [
        jsxs(DialogHeader, { children: [jsx(DialogTitle, { children: t('envIn', state.folder.label) }), jsx(DialogDescription, { children: t('envHelp') })] }),
        files === null
          ? h('div', { className: 'sqh-hint' }, t('loading'))
          : files.length
            ? h('div', { style: { display: 'grid', gap: 4 } }, files.map(p => h('button', { key: p, type: 'button', className: 'sqh-envrow', onClick: () => open(p) }, jsx(Glyph, { name: 'file-key', size: 14 }), h('span', {}, baseName(p)), h('span', { className: 'sqh-hint' }, t('openInEditor')))))
            : h('div', { className: 'sqh-hint' }, t('noEnv')),
        jsxs(DialogFooter, { children: [jsx(Button, { variant: 'ghost', onClick: () => ctxRef?.os?.revealPath?.(state.folder.path), children: t('reveal') }), jsx(Button, { variant: 'ghost', onClick: close, children: t('cancel') })] })
      ]
    })
  })
}

function ConfirmBox({ state, close }) {
  const t = useT()
  const [busy, setBusy] = useState(false)
  if (!state) return null
  return jsx(Dialog, {
    open: true,
    onOpenChange: o => !o && close(),
    children: jsxs(DialogContent, {
      children: [
        jsxs(DialogHeader, { children: [jsx(DialogTitle, { children: state.title }), jsx(DialogDescription, { children: state.body })] }),
        jsxs(DialogFooter, { children: [jsx(Button, { variant: 'ghost', onClick: close, children: t('cancel') }), jsx(Button, { variant: 'destructive', disabled: busy, onClick: () => runAction(state, close, setBusy), children: state.action || t('remove') })] })
      ]
    })
  })
}

function CapsDialog({ state, close }) {
  const t = useT()
  if (!state) return null
  return jsx(Dialog, {
    open: true,
    onOpenChange: o => !o && close(),
    children: jsxs(DialogContent, {
      className: 'sqh-caps',
      children: [jsx(DialogHeader, { children: jsx(DialogTitle, { children: t('botCaps', state.bot.title) }) }), jsx(CapabilitiesView, { embedded: true, fixedProfile: state.bot.name })]
    })
  })
}

// ───────────────────────────── the pane ─────────────────────────────
function Hub() {
  const t = useT()
  const prefs = useValue(prefsAtom)
  const activeId = useValue(host.state.focusedStoredSessionId)
  const [query, setQuery] = useState('')
  const [dialog, setDialog] = useState(null)
  const [othersOpen, setOthersOpen] = useState(false)
  const q = useQuery(snapshotQuery())
  const paths = useMemo(() => folderPathsOf(q.data), [q.data])
  const wt = useQuery({ queryKey: ['squad-hub', 'worktrees', paths.join('|')], queryFn: () => loadWorktrees(paths), enabled: paths.length > 0, staleTime: 30000, refetchInterval: 60000, placeholderData: prev => prev })

  useEffect(() => {
    openDialog = setDialog
    return () => {
      if (openDialog === setDialog) openDialog = null
    }
  }, [])
  const ctl = useMemo(
    () => ({
      newProject: bot => setDialog({ kind: 'project', bot }),
      newWorktree: (bot, folder) => setDialog({ kind: 'worktree', bot, folder }),
      capabilities: bot => setDialog({ kind: 'caps', bot }),
      appearance: (bot, project) => setDialog({ kind: 'look', bot, project }),
      envFiles: folder => setDialog({ kind: 'env', folder }),
      addFolder: async (bot, project) => {
        const picked = await pickFolders(t('addFolder'), project.folders[0]?.path)
        try {
          for (const path of picked) await rpc('projects.add_folder', { profile: bot.name, id: project.id, path })
          if (picked.length) await refresh()
        } catch (e) {
          host.notifyError(e, 'Could not add the folder')
        }
      },
      removeFolder: (bot, project, folder) =>
        setDialog({ kind: 'confirm', title: t('removeFolder'), body: folder.path, run: async () => { await rpc('projects.remove_folder', { profile: bot.name, id: project.id, path: folder.path }); await refresh() } }),
      renameProject: (bot, project) =>
        setDialog({ kind: 'text', title: t('renameProject'), value: project.name, run: async name => { await rpc('projects.update', { profile: bot.name, id: project.id, name }); await refresh() } }),
      removeProject: (bot, project) =>
        setDialog({ kind: 'confirm', title: t('removeProject'), body: project.name, run: async () => { await rpc('projects.archive', { profile: bot.name, id: project.id }); await refresh() } }),
      removeWorktree: (folder, lane) =>
        setDialog({ kind: 'confirm', title: t('removeWorktreeAsk'), body: lane.path + ' — ' + t('removeWorktreeBody'), run: async () => { await git().worktreeRemove(folder.path, lane.path); await refresh() } }),
      renameChat: (bot, session) =>
        setDialog({ kind: 'text', title: t('renameChat'), value: session.title || '', run: async title => { await patchSession(bot, session.id, { title }); await refresh() } }),
      archiveChat: async (bot, session) => {
        try {
          await patchSession(bot, session.id, { archived: true })
          await refresh()
        } catch (e) {
          host.notifyError(e, 'Could not archive the chat')
        }
      }
    }),
    [t]
  )

  const trees = useMemo(() => {
    const snap = q.data
    if (!snap) return { main: [], groups: [], other: [] }
    const worktrees = wt.data || {}
    let all = botsOf(snap, prefs).map(bot =>
      buildBotTree(bot, snap.projectsBy[bot.name] || [], snap.chats.filter(c => c.profile === bot.name), worktrees)
    )
    if (prefs.sortRecent) all = all.sort((a, b) => botLast(b) - botLast(a))
    all = all.map(tr => filterTree(tr, query)).filter(Boolean)
    const groups = new Map()
    for (const x of all.filter(x => x.bot.group)) groups.set(x.bot.group, [...(groups.get(x.bot.group) || []), x])
    return {
      main: all.filter(x => !x.bot.other),
      groups: [...groups.entries()],
      other: prefs.showOthers ? all.filter(x => x.bot.other && !x.bot.group) : []
    }
  }, [q.data, wt.data, query, prefs])

  return h(
    'div',
    { className: 'sqh' },
    h('div', { className: 'sqh-top' }, jsx(SearchField, { placeholder: t('search'), value: query, onChange: setQuery }), jsx(IconBtn, { icon: 'refresh', label: t('refresh'), onClick: refresh })),
    h(
      'div',
      { className: 'sqh-scroll' },
      q.isLoading && !q.data ? h('div', { className: 'sqh-empty', style: { paddingLeft: 12 } }, t('loading')) : null,
      q.error && !q.data ? h('div', { className: 'sqh-empty', style: { paddingLeft: 12 } }, t('loadFailed') + ': ' + String(q.error?.message || q.error)) : null,
      trees.main.map(tr => h(BotBlock, { key: tr.bot.name, tree: tr, activeId, ctl, query })),
      trees.groups.map(([section, members]) => h(GroupBlock, { key: 'g:' + section, section, members, activeId, ctl, query })),
      trees.other.length
        ? [
            h(Row, { key: 'o', depth: 0, className: 'sqh-bot', onClick: () => setOthersOpen(v => !v) }, jsx(DisclosureCaret, { open: othersOpen || !!query.trim() }), h('span', { className: 'sqh-label' }, t('otherBots')), h('span', { className: 'sqh-age' }, trees.other.length)),
            othersOpen || query.trim() ? trees.other.map(tr => h(BotBlock, { key: tr.bot.name, tree: tr, activeId, ctl, query })) : null
          ]
        : null,
      q.data && !trees.main.length && !trees.groups.length && !trees.other.length ? jsx(EmptyState, { title: query ? t('nothingMatches') : t('noBots'), description: query ? undefined : t('noBotsHint') }) : null
    ),
    jsx(ProjectDialog, { state: dialog?.kind === 'project' ? dialog : null, close: () => setDialog(null) }),
    jsx(WorktreeDialog, { state: dialog?.kind === 'worktree' ? dialog : null, close: () => setDialog(null) }),
    jsx(TextDialog, { state: dialog?.kind === 'text' ? dialog : null, close: () => setDialog(null) }),
    jsx(ConfirmBox, { state: dialog?.kind === 'confirm' ? dialog : null, close: () => setDialog(null) }),
    jsx(CapsDialog, { state: dialog?.kind === 'caps' ? dialog : null, close: () => setDialog(null) }),
    jsx(LookDialog, { state: dialog?.kind === 'look' ? dialog : null, close: () => setDialog(null) }),
    jsx(EnvDialog, { state: dialog?.kind === 'env' ? dialog : null, close: () => setDialog(null) })
  )
}

/** `@` in the composer offers the folders and worktrees of the project the focused chat works in, so a path can be
 *  handed to the bot exactly. Synchronous by contract: it reads the cached snapshot. */
/** The composer's own folder reference, fenced like its picker writes it, so a path with spaces stays one chip. */
const folderRef = path => '@folder:' + (!path.includes('`') ? '`' + path + '`' : !path.includes('"') ? '"' + path + '"' : "'" + path + "'")

const latestWorktrees = () =>
  queryClient.getQueriesData({ queryKey: ['squad-hub', 'worktrees'] })
    .map(([key, data]) => ({ data, at: queryClient.getQueryState(key)?.dataUpdatedAt || 0 }))
    .sort((a, b) => b.at - a.at)[0]?.data || {}

function atFolders(query) {
  const snap = queryClient.getQueryData(SNAPSHOT_KEY)
  const id = host.state.focusedStoredSessionId.get()
  const chat = snap?.chats?.find(c => c.id === id)
  if (!snap || !chat) return []
  const wts = latestWorktrees()
  const project = (snap.projectsBy[chat.profile] || []).filter(p => !p.archived).find(p => (p.folders || []).some(f => folderOf(chat, [{ path: trimPath(f.path) }])))
  if (!project) return []
  const q = String(query || '').toLowerCase()
  const out = []
  for (const f of project.folders || []) {
    const path = trimPath(f.path)
    out.push({ insert: folderRef(path), display: f.label || baseName(path), meta: project.name, icon: 'folder' })
    for (const w of wts[path] || []) if (!w.isMain && !isKanbanWorktree(w.path)) out.push({ insert: folderRef(trimPath(w.path)), display: baseName(w.path), meta: (f.label || baseName(path)) + ' · ' + (w.branch || 'worktree'), icon: 'git-branch' })
  }
  return out.filter(x => !q || x.display.toLowerCase().includes(q) || x.meta.toLowerCase().includes(q)).slice(0, 12)
}

/** Every visible bot's tree, the way the list builds it, for the surfaces outside the list. */
function useTrees() {
  const prefs = useValue(prefsAtom)
  const q = useQuery(snapshotQuery())
  const paths = useMemo(() => folderPathsOf(q.data), [q.data])
  const wt = useQuery({ queryKey: ['squad-hub', 'worktrees', paths.join('|')], queryFn: () => loadWorktrees(paths), enabled: paths.length > 0, staleTime: 30000, placeholderData: prev => prev })
  return useMemo(() => treesOf(q.data, wt.data, prefs), [q.data, wt.data, prefs])
}

function treesOf(snap, worktrees, prefs) {
  if (!snap) return []
  return botsOf(snap, prefs).map(bot => buildBotTree(bot, snap.projectsBy[bot.name] || [], snap.chats.filter(c => c.profile === bot.name), worktrees || {}))
}

function attentionNow() {
  return { live: liveAtom.get(), unread: unreadAtom.get(), focused: host.state.focusedStoredSessionId.get() }
}

/** Jump to the next chat that needs you, across every bot: a working one first, then unread, wrapping around. */
function goNextPending() {
  const snap = queryClient.getQueryData(SNAPSHOT_KEY)
  const wts = latestWorktrees()
  const items = pendingAcross(treesOf(snap, wts, prefsAtom.get()), attentionNow())
  const current = host.state.focusedStoredSessionId.get()
  const next = nextPending(items, current)
  if (next && next.session.id !== current) openChat(next.bot.name, next.session.id)
  else host.notify({ kind: 'info', message: fmt(lang().nothingPending) })
}
const lang = () => (String(document.documentElement.lang || navigator.language || 'en').toLowerCase().startsWith('es') ? MESSAGES.es : MESSAGES.en)

/** Status bar: what needs you everywhere ("2 working · 3 unread"); a click opens the most urgent one. */
function PendingCount() {
  const t = useT()
  const trees = useTrees()
  const attention = useAttention(useValue(host.state.focusedStoredSessionId))
  const items = useMemo(() => pendingAcross(trees, attention), [trees, attention])
  if (!items.length) return null
  const working = items.filter(x => x.state === 'working').length
  const unread = items.length - working
  return jsxs(DropdownMenu, {
    children: [
      jsx(DropdownMenuTrigger, {
        asChild: true,
        children: h(
          'button',
          { type: 'button', className: 'sqh-pending', title: t('pendingTip') },
          jsx(SessionStatusDot, { storedSessionId: items[0].session.id, session: items[0].session }),
          working ? h('span', {}, h('b', {}, working), ' ', t('working')) : null,
          working && unread ? h('span', {}, '·') : null,
          unread ? h('span', {}, h('b', {}, unread), ' ', t('unread')) : null
        )
      }),
      jsx(DropdownMenuContent, {
        align: 'start',
        children: items.slice(0, 12).map(x =>
          jsx(DropdownMenuItem, { onSelect: () => openChat(x.bot.name, x.session.id), children: h('span', { className: 'sqh-menuchat' }, jsx(SessionStatusDot, { storedSessionId: x.session.id, session: x.session }), h('span', {}, (x.session.title || x.session.preview || 'Chat').slice(0, 48)), h('span', { className: 'sqh-hint' }, [x.bot.title, whereOf(x)].filter(Boolean).join(' · '))) }, x.session.id)
        )
      })
    ]
  })
}

/** An empty chat says whose it is and where it works, with that place's other chats one click away. */
function ChatIntro({ sessionId }) {
  const t = useT()
  const stored = useValue(host.state.focusedStoredSessionId)
  const trees = useTrees()
  const attention = useAttention(stored)
  const id = runtimeToStored.get(sessionId) || (host.state.focusedSessionId.get() === sessionId ? stored : null)
  const hit = useMemo(() => {
    for (const tree of trees) {
      for (const p of tree.projects) for (const f of p.folders) for (const l of f.lanes) if (l.sessions.some(s => s.id === id)) return { tree, project: p, folder: f, lane: l }
      if (tree.loose.some(s => s.id === id)) return { tree, project: null }
    }
    return null
  }, [trees, id])
  if (!id || !hit) return null
  const prefs = prefsAtom.get()
  const { tree, project, folder, lane } = hit
  const pending = (project ? activeIn(project.folders, attention) : botDigest(tree, attention)).filter(x => x.session.id !== id).slice(0, 5)
  const where = project ? [project.name, project.folders.length > 1 ? folder.label : '', lane && !lane.main ? lane.label : ''].filter(Boolean) : []
  return h(
    'div',
    { className: 'sqh-intro' },
    h('div', { className: 'sqh-intro-head' }, jsx(IconTile, { icon: iconFor(tree.bot, prefs.icons || {}), size: 34 }), h('div', {}, h('h2', {}, tree.bot.title), h('div', { className: 'sqh-hint' }, t('introHint')))),
    where.length ? h('div', { className: 'sqh-intro-where' }, where.map(w => h('span', { key: w, className: 'sqh-where' }, w))) : null,
    pending.length
      ? h('div', { className: 'sqh-intro-list' }, h('div', { className: 'sqh-hint' }, t('alsoPending')), pending.map(x => h(Row, { key: x.session.id, depth: 0, onClick: () => openChat(tree.bot.name, x.session.id) }, jsx(SessionStatusDot, { storedSessionId: x.session.id, session: x.session }), h('span', { className: 'sqh-label' }, x.session.title || x.session.preview || 'Chat'), h('span', { className: 'sqh-where' }, whereOf(x).split(' · ').pop() || tree.bot.title))))
      : null
  )
}

/** Status bar: where the focused chat works (bot · project · lane) and the tools that follow it. */
function ChatContext() {
  const t = useT()
  const id = useValue(host.state.focusedStoredSessionId)
  const previews = useValue(previewsAtom)[id] || []
  const { data: snap } = useQuery(snapshotQuery())
  const session = snap?.chats?.find(c => c.id === id)
  if (!id) return null
  const lane = session?.cwd ? baseName(session.cwd) : ''
  const branch = session?.git_branch || ''
  return jsxs(DropdownMenu, {
    children: [
      jsx(DropdownMenuTrigger, {
        asChild: true,
        children: h('button', { type: 'button', className: 'sqh-status' }, jsx(Codicon, { name: 'git-branch', size: '0.75rem' }), h('span', {}, [lane, branch && branch !== lane ? branch : ''].filter(Boolean).join(' · ') || t('pane')), previews.length ? h('span', { className: 'sqh-pv' }, previews.length) : null)
      }),
      jsxs(DropdownMenuContent, {
        align: 'start',
        children: [
          ...(previews.length ? previews.slice(0, 8).map(p => jsx(DropdownMenuItem, { onSelect: () => reopenPreview(p), children: '↗ ' + (p.label || p.url).slice(0, 56) }, p.url)) : [jsx(DropdownMenuItem, { disabled: true, children: t('noPreviews') }, 'none')]),
          jsx(DropdownMenuSeparator, {}, 's1'),
          jsx(DropdownMenuItem, { onSelect: () => host.revealPane('files'), children: t('ctxFiles') }, 'files'),
          jsx(DropdownMenuItem, { onSelect: () => host.revealPane('review'), children: t('ctxReview') }, 'review'),
          jsx(DropdownMenuItem, { onSelect: () => host.revealPane('terminal'), children: t('ctxTerminal') }, 'term'),
          session?.cwd ? jsx(DropdownMenuItem, { onSelect: () => ctxRef?.os?.revealPath?.(session.cwd), children: t('reveal') }, 'reveal') : null
        ].filter(Boolean)
      })
    ]
  })
}

function IconPick({ value, onChange }) {
  return jsxs(DropdownMenu, {
    children: [
      jsx(DropdownMenuTrigger, { asChild: true, children: h('button', { type: 'button', className: 'sqh-ib', style: { width: 26, height: 26 }, 'aria-label': 'Icon' }, jsx(IconTile, { icon: value, size: 22 })) }),
      jsx(DropdownMenuContent, { align: 'start', children: h('div', { className: 'sqh-icongrid' }, ICON_NAMES.map(n => h('button', { key: n, type: 'button', className: 'sqh-ib', style: { width: 30, height: 30 }, title: n, onClick: () => onChange(n) }, jsx(IconTile, { icon: n, size: 24 })))) })
    ]
  })
}

function ThemeRow() {
  const t = useT()
  const theme = useTheme?.()
  const active = theme?.themeName === 'squads'
  return h(
    'div',
    { style: { display: 'flex', alignItems: 'center', gap: 12, padding: '4px 0' } },
    h('div', { style: { display: 'flex', gap: 4 } }, ...['#1e1e2e', '#cba6f7', '#89b4fa', '#a6e3a1', '#f6f3ee'].map(c => h('span', { key: c, style: { width: 14, height: 14, borderRadius: 4, background: c, boxShadow: 'inset 0 0 0 1px color-mix(in srgb, currentColor 15%, transparent)' } }))),
    h('div', { style: { flex: 1 } }, h('div', { style: { color: 'var(--foreground)', fontWeight: 500 } }, t('themeName')), h('div', { className: 'sqh-hint' }, t('themeHint'))),
    jsx(Button, { variant: active ? 'secondary' : 'default', disabled: active, onClick: () => requestTheme?.('squads'), children: active ? t('themeActive') : t('themeUse') })
  )
}

const CREDITS = {
  repo: 'https://github.com/PuntoyComaTech/hermes-agent-squads',
  links: [
    ['GitHub', 'https://github.com/PuntoyComaTech'],
    ['Instagram', 'https://www.instagram.com/puntoycomatech'],
    ['X', 'https://x.com/PuntoyComaTech'],
    ['YouTube', 'https://www.youtube.com/@PuntoyComaTech'],
    ['TikTok', 'https://www.tiktok.com/@puntoycomatech']
  ]
}
function Credits() {
  const t = useT()
  const open = url => ctxRef?.os?.openExternal?.(url)
  return h(
    'div',
    { className: 'sqh-credits' },
    h('div', { className: 'sqh-hint' }, t('creditsBy'), ' ', h('a', { href: '#', onClick: e => (e.preventDefault(), open(CREDITS.repo)) }, 'PuntoyComaTech'), ' · ', t('creditsPart'), ' ', h('a', { href: '#', onClick: e => (e.preventDefault(), open(CREDITS.repo)) }, 'Hermes Agent Squads')),
    h('div', { className: 'sqh-credit-links' }, CREDITS.links.map(([label, url]) => h('a', { key: label, href: '#', onClick: e => (e.preventDefault(), open(url)) }, label)))
  )
}

function SettingsPage() {
  const t = useT()
  const prefs = useValue(prefsAtom)
  const { data: snap } = useQuery(snapshotQuery())
  const nav = [['new-session', 'New session'], ['messaging', 'Messaging'], ['artifacts', 'Artifacts'], ['cron', 'Scheduled jobs']]
  return h(
    'div',
    {},
    jsx(ThemeRow, {}),
    h('div', { className: 'sqh-hint', style: { padding: '14px 0 4px' } }, t('setup')),
    jsx(ToggleRow, { checked: prefs.floatSides, label: t('floatSides'), description: t('floatSidesHint'), onChange: on => savePrefs({ floatSides: on }) }),
    h('div', { style: { display: 'flex', alignItems: 'center', gap: 12, padding: '6px 0' } }, h('div', { style: { flex: 1 } }, h('div', { style: { color: 'var(--foreground)', fontWeight: 500 } }, t('layoutName')), h('div', { className: 'sqh-hint' }, t('layoutHint'))), jsx(Button, { variant: 'outline', onClick: applySquadsLayout, children: t('themeUse') })),
    jsx(ToggleRow, { checked: prefs.envDoubleClick !== false, label: t('envDoubleClick'), description: t('envDoubleClickHint'), onChange: on => savePrefs({ envDoubleClick: on }) }),
    jsx(ToggleRow, { checked: prefs.hideBotsTab, label: t('hideBotsTab'), description: t('hideBotsTabHint'), onChange: on => savePrefs({ hideBotsTab: on }) }),
    jsx(ToggleRow, { checked: prefs.hideRail, label: t('hideRail'), description: t('hideRailHint'), onChange: on => savePrefs({ hideRail: on }) }),
    jsx(ToggleRow, { checked: prefs.showOthers, label: t('showOthers'), description: t('showOthersHint'), onChange: on => savePrefs({ showOthers: on }) }),
    jsx(ToggleRow, { checked: prefs.sortRecent, label: t('sortRecent'), description: t('sortRecentHint'), onChange: on => savePrefs({ sortRecent: on }) }),
    h('div', { className: 'sqh-hint', style: { padding: '14px 0 4px' } }, t('navRows')),
    nav.map(([id, label]) => jsx(ToggleRow, { key: id, checked: !(prefs.hiddenNav || []).includes(id), label, onChange: on => savePrefs({ hiddenNav: on ? prefs.hiddenNav.filter(x => x !== id) : [...(prefs.hiddenNav || []), id] }) })),
    h('div', { className: 'sqh-hint', style: { padding: '14px 0 4px' } }, t('visibleBots'), ' — ', t('allVisible')),
    (snap ? visibleBots(snap.profiles, snap.humanBy, { pinned: snap.profiles.map(p => p.name) }).filter(b => b.role !== 'other' || snap.humanBy[b.name]) : []).map(b => h('div', { key: b.name, className: 'sqh-setbot' }, jsx(IconPick, { value: iconFor(b, prefs.icons || {}), onChange: icon => savePrefs({ icons: { ...(prefs.icons || {}), [b.name]: icon } }) }), jsx(ToggleRow, { key: b.name, checked: !prefs.hidden.includes(b.name), label: b.title, description: b.name + ' · ' + b.role, onChange: on => savePrefs({ hidden: on ? prefs.hidden.filter(n => n !== b.name) : [...prefs.hidden, b.name] }) }))),
    jsx(Credits, {})
  )
}


// ───────────────────────────── theme ─────────────────────────────
// "Squads": Catppuccin-inspired (Mocha dark, Latte light), softened for long sessions. Dark keeps the Mocha
// base but dims the text and the borders; light trades Latte's cool grey for a warm cream. Accents carry dark
// text, so a mauve button never puts white on pastel. Inter for the interface, the bundled JetBrains Mono for code.
const SQUADS_THEME = {
  name: 'squads',
  label: 'Squads',
  description: 'Soft Catppuccin-inspired pastels — cream by day, mocha by night',
  colors: {
    background: '#f6f3ee', foreground: '#4c4f69', card: '#efebe4', cardForeground: '#4c4f69',
    muted: '#ece8e1', mutedForeground: '#6c6f85', popover: '#fbf9f5', popoverForeground: '#4c4f69',
    primary: '#8839ef', primaryForeground: '#ffffff', secondary: '#e6e1ec', secondaryForeground: '#4c4f69',
    accent: '#ebe5f3', accentForeground: '#4c4f69', border: '#dcd6cc', input: '#e4dfd6', ring: '#7287fd',
    midground: '#8839ef', midgroundForeground: '#ffffff', composerRing: '#7287fd',
    destructive: '#d20f39', destructiveForeground: '#ffffff', sidebarBackground: '#efebe4', sidebarBorder: '#e0dad0',
    userBubble: '#ebe4f5', userBubbleBorder: '#d9cfe8'
  },
  darkColors: {
    background: '#1e1e2e', foreground: '#cad0ea', card: '#232334', cardForeground: '#cad0ea',
    muted: '#2a2a3c', mutedForeground: '#a6adc8', popover: '#232334', popoverForeground: '#cad0ea',
    primary: '#cba6f7', primaryForeground: '#1e1e2e', secondary: '#313244', secondaryForeground: '#cdd6f4',
    accent: '#2f2d45', accentForeground: '#cdd6f4', border: '#34354a', input: '#313244', ring: '#b4befe',
    midground: '#cba6f7', midgroundForeground: '#1e1e2e', composerRing: '#b4befe',
    destructive: '#f38ba8', destructiveForeground: '#1e1e2e', sidebarBackground: '#181825', sidebarBorder: '#2a2b3d',
    userBubble: '#2c2a44', userBubbleBorder: '#3a3858'
  },
  typography: {
    fontSans: '"Inter", "SF Pro Text", -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif, "Apple Color Emoji", "Segoe UI Emoji", emoji',
    fontMono: '"JetBrains Mono", "SF Mono", ui-monospace, Menlo, Consolas, monospace',
    fontUrl: 'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap',
    letterSpacing: '-0.006em'
  },
  terminal: {
    foreground: '#4c4f69', cursor: '#dc8a78', selectionBackground: '#acb0be', black: '#5c5f77', red: '#d20f39',
    green: '#40a02b', yellow: '#df8e1d', blue: '#1e66f5', magenta: '#ea76cb', cyan: '#179299', white: '#acb0be',
    brightBlack: '#6c6f85', brightRed: '#de293e', brightGreen: '#49af3d', brightYellow: '#eea02d', brightBlue: '#456eff',
    brightMagenta: '#fe85d8', brightCyan: '#2d9fa8', brightWhite: '#bcc0cc'
  },
  darkTerminal: {
    foreground: '#cdd6f4', cursor: '#f5e0dc', selectionBackground: '#585b70', black: '#45475a', red: '#f38ba8',
    green: '#a6e3a1', yellow: '#f9e2af', blue: '#89b4fa', magenta: '#f5c2e7', cyan: '#94e2d5', white: '#a6adc8',
    brightBlack: '#585b70', brightRed: '#f37799', brightGreen: '#89d88b', brightYellow: '#ebd391', brightBlue: '#74a8fc',
    brightMagenta: '#f2aede', brightCyan: '#6bd7ca', brightWhite: '#bac2de'
  }
}

/** Lucide icons (lucide.dev, ISC licence, (c) Lucide Contributors), inner SVG of the 24px glyphs the list uses. */
const LUCIDE = {
  "sparkles": "<path d=\"M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z\" /> <path d=\"M20 2v4\" /> <path d=\"M22 4h-4\" /> <circle cx=\"4\" cy=\"20\" r=\"2\" />",
  "hammer": "<path d=\"m15 12-9.373 9.373a1 1 0 0 1-3.001-3L12 9\" /> <path d=\"m18 15 4-4\" /> <path d=\"m21.5 11.5-1.914-1.914A2 2 0 0 1 19 8.172v-.344a2 2 0 0 0-.586-1.414l-1.657-1.657A6 6 0 0 0 12.516 3H9l1.243 1.243A6 6 0 0 1 12 8.485V10l2 2h1.172a2 2 0 0 1 1.414.586L18.5 14.5\" />",
  "briefcase-business": "<path d=\"M12 12h.01\" /> <path d=\"M16 6V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2\" /> <path d=\"M22 13a18.15 18.15 0 0 1-20 0\" /> <rect width=\"20\" height=\"14\" x=\"2\" y=\"6\" rx=\"2\" />",
  "megaphone": "<path d=\"M11 6a13 13 0 0 0 8.4-2.8A1 1 0 0 1 21 4v12a1 1 0 0 1-1.6.8A13 13 0 0 0 11 14H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z\" /> <path d=\"M6 14a12 12 0 0 0 2.4 7.2 2 2 0 0 0 3.2-2.4A8 8 0 0 1 10 14\" /> <path d=\"M8 6v8\" />",
  "globe": "<circle cx=\"12\" cy=\"12\" r=\"10\" /> <path d=\"M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20\" /> <path d=\"M2 12h20\" />",
  "shopping-bag": "<path d=\"M16 10a4 4 0 0 1-8 0\" /> <path d=\"M3.103 6.034h17.794\" /> <path d=\"M3.4 5.467a2 2 0 0 0-.4 1.2V20a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6.667a2 2 0 0 0-.4-1.2l-2-2.667A2 2 0 0 0 17 2H7a2 2 0 0 0-1.6.8z\" />",
  "store": "<path d=\"M15 21v-5a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v5\" /> <path d=\"M17.774 10.31a1.12 1.12 0 0 0-1.549 0 2.5 2.5 0 0 1-3.451 0 1.12 1.12 0 0 0-1.548 0 2.5 2.5 0 0 1-3.452 0 1.12 1.12 0 0 0-1.549 0 2.5 2.5 0 0 1-3.77-3.248l2.889-4.184A2 2 0 0 1 7 2h10a2 2 0 0 1 1.653.873l2.895 4.192a2.5 2.5 0 0 1-3.774 3.244\" /> <path d=\"M4 10.95V19a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8.05\" />",
  "shopping-cart": "<circle cx=\"8\" cy=\"21\" r=\"1\" /> <circle cx=\"19\" cy=\"21\" r=\"1\" /> <path d=\"M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12\" />",
  "package": "<path d=\"M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z\" /> <path d=\"M12 22V12\" /> <polyline points=\"3.29 7 12 12 20.71 7\" /> <path d=\"m7.5 4.27 9 5.15\" />",
  "rocket": "<path d=\"M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z\" /> <path d=\"m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z\" /> <path d=\"M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0\" /> <path d=\"M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5\" />",
  "bot": "<path d=\"M12 8V4H8\" /> <rect width=\"16\" height=\"12\" x=\"4\" y=\"8\" rx=\"2\" /> <path d=\"M2 14h2\" /> <path d=\"M20 14h2\" /> <path d=\"M15 13v2\" /> <path d=\"M9 13v2\" />",
  "code": "<path d=\"m16 18 6-6-6-6\" /> <path d=\"m8 6-6 6 6 6\" />",
  "palette": "<path d=\"M12 22a1 1 0 0 1 0-20 10 9 0 0 1 10 9 5 5 0 0 1-5 5h-2.25a1.75 1.75 0 0 0-1.4 2.8l.3.4a1.75 1.75 0 0 1-1.4 2.8z\" /> <circle cx=\"13.5\" cy=\"6.5\" r=\".5\" fill=\"currentColor\" /> <circle cx=\"17.5\" cy=\"10.5\" r=\".5\" fill=\"currentColor\" /> <circle cx=\"6.5\" cy=\"12.5\" r=\".5\" fill=\"currentColor\" /> <circle cx=\"8.5\" cy=\"7.5\" r=\".5\" fill=\"currentColor\" />",
  "chart-line": "<path d=\"M3 3v16a2 2 0 0 0 2 2h16\" /> <path d=\"m19 9-5 5-4-4-3 3\" />",
  "users": "<path d=\"M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2\" /> <path d=\"M16 3.128a4 4 0 0 1 0 7.744\" /> <path d=\"M22 21v-2a4 4 0 0 0-3-3.87\" /> <circle cx=\"9\" cy=\"7\" r=\"4\" />",
  "server": "<rect width=\"20\" height=\"8\" x=\"2\" y=\"2\" rx=\"2\" ry=\"2\" /> <rect width=\"20\" height=\"8\" x=\"2\" y=\"14\" rx=\"2\" ry=\"2\" /> <line x1=\"6\" x2=\"6.01\" y1=\"6\" y2=\"6\" /> <line x1=\"6\" x2=\"6.01\" y1=\"18\" y2=\"18\" />"
  }
const UI_ICONS = {
  "folder": "<path d=\"M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z\" />",
  "folder-git-2": "<path d=\"M9 20H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H20a2 2 0 0 1 2 2v5\" /> <circle cx=\"13\" cy=\"12\" r=\"2\" /> <path d=\"M18 19c-2.8 0-5-2.2-5-5v8\" /> <circle cx=\"20\" cy=\"19\" r=\"2\" />",
  "layers": "<path d=\"M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z\" /> <path d=\"M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12\" /> <path d=\"M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17\" />",
  "house": "<path d=\"M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8\" /> <path d=\"M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z\" />",
  "git-branch": "<line x1=\"6\" x2=\"6\" y1=\"3\" y2=\"15\" /> <circle cx=\"18\" cy=\"6\" r=\"3\" /> <circle cx=\"6\" cy=\"18\" r=\"3\" /> <path d=\"M18 9a9 9 0 0 1-9 9\" />",
  "app-window": "<rect x=\"2\" y=\"4\" width=\"20\" height=\"16\" rx=\"2\" /> <path d=\"M10 4v4\" /> <path d=\"M2 8h20\" /> <path d=\"M6 4v4\" />",
  "file-key": "<path d=\"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z\" /> <circle cx=\"10\" cy=\"16\" r=\"2\" /> <path d=\"m16 10-4.5 4.5\" /> <path d=\"m15 11 1 1\" />",
  "panel-left": "<rect width=\"18\" height=\"18\" x=\"3\" y=\"3\" rx=\"2\" /> <path d=\"M9 3v18\" />",
  "panel-right": "<rect width=\"18\" height=\"18\" x=\"3\" y=\"3\" rx=\"2\" /> <path d=\"M15 3v18\" />",
  "pin": "<path d=\"M12 17v5\" /> <path d=\"M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z\" />",
  "pin-off": "<path d=\"M12 17v5\" /> <path d=\"M15 9.34V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H7.89\" /> <path d=\"m2 2 20 20\" /> <path d=\"M9 9v1.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h11\" />",
  "terminal": "<path d=\"M12 19h8\" /> <path d=\"m4 17 6-6-6-6\" />"
}
const ICON_TINT = {
  sparkles: '#cba6f7', hammer: '#fab387', 'briefcase-business': '#f9e2af', megaphone: '#f5c2e7', globe: '#89b4fa',
  'shopping-bag': '#a6e3a1', store: '#94e2d5', 'shopping-cart': '#a6e3a1', package: '#f9e2af', rocket: '#fab387',
  bot: '#b4befe', code: '#94e2d5', palette: '#f5c2e7', 'chart-line': '#89dceb', users: '#eba0ac', server: '#74c7ec'
}
const ICON_NAMES = Object.keys(LUCIDE)


const CSS = `
.sqh{display:flex;flex-direction:column;height:100%;min-height:0;font-size:.8125rem;color:var(--ui-text-secondary)}
.sqh-top{display:flex;align-items:center;gap:4px;padding:6px 8px 4px}
.sqh-top>div:first-child{flex:1;min-width:0}
.sqh-scroll{flex:1;min-height:0;overflow:auto;padding:2px 6px 14px}
.sqh-row{display:flex;align-items:center;gap:6px;min-height:27px;padding:0 4px 0 6px;border-radius:7px;cursor:pointer;user-select:none;transition:background-color .12s ease}
.sqh-row:hover{background:var(--ui-control-hover-background,color-mix(in srgb,currentColor 12%,transparent))}
.sqh-row[data-active="true"]{background:var(--ui-control-active-background,color-mix(in srgb,currentColor 20%,transparent));color:var(--foreground)}
.sqh-label{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sqh-age{font-size:.625rem;color:var(--ui-text-tertiary);flex:none}
.sqh-actions{display:none;gap:1px;align-items:center;flex:none}
.sqh-row:hover .sqh-actions,.sqh-actions:has([data-state="open"]){display:flex}
.sqh-row:hover .sqh-age,.sqh-row:has([data-state="open"]) .sqh-age{display:none}
.sqh-ib{background:transparent;border:0;color:var(--ui-text-tertiary);cursor:pointer;width:20px;height:20px;border-radius:4px;display:grid;place-items:center;padding:0}
.sqh-ib:hover{background:color-mix(in srgb,currentColor 22%,transparent);color:var(--foreground)}
.sqh-bot{margin-top:10px;font-weight:600;color:var(--foreground)}
.sqh-row[data-active="true"]{box-shadow:inset 2px 0 0 var(--midground,var(--ui-accent))}
.sqh-proj .sqh-label{font-weight:500}
.sqh-lane,.sqh-folder{color:var(--ui-text-tertiary)}
.sqh-lane .sqh-label,.sqh-folder .sqh-label{font-size:.75rem}
.sqh-branch{font-family:var(--font-mono,ui-monospace,monospace);font-size:.6875rem;color:var(--ui-text-tertiary)}
.sqh-tile{flex:none;display:grid;place-items:center;border-radius:5px;box-shadow:inset 0 0 0 1px color-mix(in srgb,currentColor 8%,transparent)}
.sqh-setbot{display:flex;align-items:center;gap:8px}
.sqh-setbot>:last-child{flex:1}
.sqh-icongrid{display:grid;grid-template-columns:repeat(4,30px);gap:4px;padding:6px}
.sqh-group-body{padding-left:14px}
.sqh-group-body .sqh-bot{margin-top:4px;font-weight:500}
.sqh-activity{display:inline-flex;align-items:center;gap:4px;font-size:.625rem;color:var(--ui-text-tertiary);flex:none}
.sqh-where{flex:none;max-width:42%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:.6875rem;padding:0 6px;border-radius:999px;color:var(--ui-text-tertiary);background:color-mix(in srgb,currentColor 10%,transparent)}
.sqh-count{font-size:.625rem;color:var(--ui-text-quaternary);flex:none}
.sqh-pv{display:inline-flex;align-items:center;gap:2px;font-size:.625rem;color:var(--ui-accent);flex:none}
.sqh-empty{padding:3px 8px 3px 40px;font-size:.75rem;color:var(--ui-text-quaternary)}
.sqh-form{display:grid;gap:10px}
.sqh-form label{display:grid;gap:4px;font-size:.75rem;color:var(--ui-text-tertiary)}
.sqh-chip{display:flex;align-items:center;gap:6px;padding:4px 8px;border:1px solid var(--ui-stroke-secondary,color-mix(in srgb,currentColor 30%,transparent));border-radius:6px;font-size:.75rem}
.sqh-chip span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sqh-hint{font-size:.75rem;color:var(--ui-text-tertiary)}
.sqh-credits{margin-top:22px;padding-top:12px;border-top:1px solid var(--ui-stroke-tertiary,var(--border));display:grid;gap:6px}
.sqh-credits a,.sqh-credit-links a{color:var(--muted-foreground);text-decoration:none}
.sqh-credits a:hover,.sqh-credit-links a:hover{color:var(--foreground)}
.sqh-credit-links{display:flex;gap:14px;font-size:12px}
.sqh-status{display:inline-flex;align-items:center;gap:5px;background:transparent;border:0;color:var(--ui-text-secondary);font-size:.6875rem;cursor:pointer;padding:0 6px;height:100%}
.sqh-status:hover{color:var(--foreground)}
.sqh-caps{max-width:min(960px,92vw);height:min(720px,86vh)}
html[data-sqh-float] [data-sqh-float-root]{position:relative}
html[data-sqh-float] [data-sqh-main]{flex:1 1 0%!important;padding:0 calc(var(--sqh-gutter,40px) - 10px)}
html[data-sqh-float] [data-sqh-side]{position:absolute!important;top:0;bottom:0;z-index:45;width:var(--sqh-w)!important;min-width:0!important;max-width:min(var(--sqh-w),85vw)!important;flex:none!important;background:var(--sidebar,var(--ui-bg-chrome,var(--background)));transition:transform var(--sqh-in) var(--sqh-ease-in),opacity var(--sqh-in) ease;will-change:transform,opacity;box-shadow:0 18px 50px -12px color-mix(in srgb,black 45%,transparent)}
html[data-sqh-float] [data-sqh-side="left"]{left:0;transform:translateX(-100%);border-right:1px solid var(--ui-stroke-secondary,var(--border))}
html[data-sqh-float] [data-sqh-side="right"]{right:0;transform:translateX(100%);border-left:1px solid var(--ui-stroke-secondary,var(--border))}
html[data-sqh-float]{--sqh-in:.26s;--sqh-out:.17s;--sqh-ease-in:cubic-bezier(.22,1,.36,1);--sqh-ease-out:cubic-bezier(.4,0,.9,.6)}
html[data-sqh-float] [data-sqh-side]:not([data-sqh-open]){visibility:hidden;opacity:.35;transition:transform var(--sqh-out) var(--sqh-ease-out),opacity var(--sqh-out) ease-in,visibility 0s linear var(--sqh-out)}
html[data-sqh-float] [data-sqh-side][data-sqh-open]{transform:none;opacity:1}
@media (prefers-reduced-motion:reduce){html[data-sqh-float]{--sqh-in:.01s;--sqh-out:.01s}}
.sqh-glyph{flex:none;opacity:.85}
.sqh-wt{color:var(--midground,var(--ui-accent))}
.sqh-pmark{flex:none;width:16px;height:16px;border-radius:5px;display:grid;place-items:center}
.sqh-pmark-lg{width:40px;height:40px;border-radius:11px}
.sqh-look{display:flex;gap:14px;align-items:flex-start}
.sqh-glyphgrid{display:grid;grid-template-columns:repeat(9,26px);gap:3px}
.sqh-glyphgrid .sqh-ib{width:26px;height:26px}
.sqh-ib[data-on="true"]{background:color-mix(in srgb,currentColor 18%,transparent);color:var(--foreground)}
.sqh-envrow{display:flex;align-items:center;gap:8px;padding:7px 10px;border-radius:8px;border:1px solid var(--ui-stroke-secondary,var(--border));background:transparent;color:var(--foreground);cursor:pointer;text-align:left}
.sqh-envrow span:nth-child(2){flex:1;font-family:var(--font-mono,ui-monospace,monospace);font-size:.75rem}
.sqh-envrow:hover{background:color-mix(in srgb,currentColor 8%,transparent)}
.sqh-pending{display:inline-flex;align-items:center;gap:6px;background:transparent;border:0;color:var(--ui-text-secondary);font-size:.6875rem;cursor:pointer;padding:0 6px;height:100%}
.sqh-pending:hover{color:var(--foreground)}
.sqh-pending b{font-weight:600;color:var(--foreground)}
.sqh-intro{max-width:520px;margin:12vh auto 0;padding:0 24px;display:grid;gap:14px;color:var(--ui-text-secondary)}
.sqh-intro-head{display:flex;align-items:center;gap:12px}
.sqh-intro-head h2{margin:0;font-size:1.05rem;font-weight:600;color:var(--foreground)}
.sqh-intro-where{display:flex;flex-wrap:wrap;gap:6px}
.sqh-intro .sqh-where{max-width:none;font-size:.75rem;padding:2px 9px}
.sqh-intro-list{display:grid;gap:2px}
.sqh-menuchat{display:flex;align-items:center;gap:8px;min-width:280px}
.sqh-menuchat span:nth-child(2){flex:1}
`

export default {
  id: ID,
  name: 'Squad Hub',
  description: 'One navigator for Hermes Agent Squads: bot → project → folder → worktree → chat, several bots open at once.',
  defaultEnabled: false,
  register(ctx) {
    ctxRef = ctx
    storage = ctx.storage
    ctx.i18n?.register?.(MESSAGES)
    prefsAtom.set({ ...DEFAULT_PREFS, ...ctx.storage.get('prefs', {}) })
    collapsedAtom.set(ctx.storage.get('collapsed', {}))
    previewsAtom.set(ctx.storage.get('previews', {}))

    styleEl = document.createElement('style')
    styleEl.dataset.squadHub = 'ui'
    styleEl.textContent = CSS
    chromeEl = document.createElement('style')
    chromeEl.dataset.squadHub = 'chrome'
    document.head.append(styleEl, chromeEl)
    ctx.onDispose(() => {
      styleEl?.remove()
      chromeEl?.remove()
      navDispose = null
      navHidden = ''
      ctxRef = null
    })
    applyChrome()

    ctx.register({
      id: 'pane',
      area: 'panes',
      title: 'Squads',
      data: { placement: 'left', width: '280px', collapsible: true, hideOnly: true, dock: { pane: 'sessions', pos: 'center', enforce: true } },
      render: () => jsx(Hub, {})
    })
    if (THEMES_AREA) ctx.register({ id: 'theme', area: THEMES_AREA, data: SQUADS_THEME })
    ctx.register({ id: 'layout', area: 'layouts', title: 'Squads', order: 50, data: SQUADS_LAYOUT })
    if (CHAT_EMPTY_AREA) ctx.register({ id: 'intro', area: CHAT_EMPTY_AREA, data: { render: props => jsx(ChatIntro, props) } })
    if (COMPOSER_AREAS?.atCompletions) ctx.register({ id: 'at-folders', area: COMPOSER_AREAS.atCompletions, data: { provide: atFolders } })
    ctx.register({ id: 'pending', area: STATUSBAR_AREAS.left, order: 29, render: () => jsx(PendingCount, {}) })
    ctx.onDispose(stopFloat)
    applyFloat()
    document.addEventListener('dblclick', onTreeDoubleClick, true)
    ctx.onDispose(() => document.removeEventListener('dblclick', onTreeDoubleClick, true))
    const pickTimer = setInterval(watchLayoutPick, 1000)
    ctx.onDispose(() => clearInterval(pickTimer))
    ctx.register({ id: 'context', area: STATUSBAR_AREAS.left, order: 30, render: () => jsx(ChatContext, {}) })
    ctx.registerMany([
      { id: 'cmd-new-project', area: PALETTE_AREA, data: { id: 'squad-hub.new-project', label: MESSAGES.en.cmdNewProject, keywords: ['squad', 'project', 'folder'], run: () => { host.revealPane('squad-hub:pane'); const snap = queryClient.getQueryData(SNAPSHOT_KEY); const bot = botsOf(snap, prefsAtom.get())[0]; if (bot) setTimeout(() => openDialog?.({ kind: 'project', bot }), 50) } } },
      { id: 'cmd-theme', area: PALETTE_AREA, data: { id: 'squad-hub.theme', label: MESSAGES.en.cmdTheme, keywords: ['theme', 'catppuccin', 'colors'], run: () => requestTheme?.('squads') } },
      { id: 'cmd-open', area: PALETTE_AREA, data: { id: 'squad-hub.open', label: MESSAGES.en.cmdOpen, keywords: ['squad', 'bots', 'projects'], run: () => host.revealPane('squad-hub:pane') } },
      {
        id: 'cmd-preview',
        area: PALETTE_AREA,
        data: {
          id: 'squad-hub.preview',
          label: MESSAGES.en.cmdPreview,
          keywords: ['preview', 'reopen'],
          run: () => {
            const { id } = focusedChat()
            const last = (previewsAtom.get()[id] || [])[0]
            if (last) reopenPreview(last)
            else host.notify({ kind: 'info', message: MESSAGES.en.noPreviews })
          }
        }
      },
      { id: 'cmd-next', area: PALETTE_AREA, data: { id: 'squad-hub.next-pending', label: MESSAGES.en.cmdNext, keywords: ['pending', 'unread', 'working', 'next'], run: goNextPending } },
      { id: 'key-next', area: KEYBINDS_AREA, data: { id: 'squad-hub.next-pending', label: MESSAGES.en.cmdNext, category: 'navigation', defaults: ['mod+shift+u'], run: goNextPending } },
      { id: 'cmd-float', area: PALETTE_AREA, data: { id: 'squad-hub.float', label: MESSAGES.en.cmdFloat, keywords: ['float', 'auto hide', 'sidebar', 'dock'], run: () => savePrefs({ floatSides: !prefsAtom.get().floatSides }) } },
      { id: 'key-pin-left', area: KEYBINDS_AREA, data: { id: 'squad-hub.pin-left', label: MESSAGES.en.cmdPinLeft, category: 'view', defaults: [], run: () => prefsAtom.get().floatSides ? togglePin('left') : ctxRef?.runAction?.('view.toggleSidebar') } },
      { id: 'key-pin-right', area: KEYBINDS_AREA, data: { id: 'squad-hub.pin-right', label: MESSAGES.en.cmdPinRight, category: 'view', defaults: [], run: () => prefsAtom.get().floatSides ? togglePin('right') : ctxRef?.runAction?.('view.toggleRightSidebar') } },
      { id: 'cmd-pin-left', area: PALETTE_AREA, data: { id: 'squad-hub.pin-left', label: MESSAGES.en.cmdPinLeft, keywords: ['pin', 'sidebar', 'left', 'float'], run: () => (prefsAtom.get().floatSides ? togglePin('left') : ctxRef?.runAction?.('view.toggleSidebar')) } },
      { id: 'cmd-pin-right', area: PALETTE_AREA, data: { id: 'squad-hub.pin-right', label: MESSAGES.en.cmdPinRight, keywords: ['pin', 'files', 'terminal', 'right', 'float'], run: () => (prefsAtom.get().floatSides ? togglePin('right') : ctxRef?.runAction?.('view.toggleRightSidebar')) } },
      { id: 'cmd-layout', area: PALETTE_AREA, data: { id: 'squad-hub.layout', label: MESSAGES.en.cmdLayout, keywords: ['layout', 'terminal', 'files'], run: () => host.navigate('/settings?tab=appearance&page=window-layout') } },
      { id: 'key-preview', area: KEYBINDS_AREA, data: { id: 'squad-hub.preview', label: MESSAGES.en.cmdPreview, category: 'view', defaults: [], run: () => { const { id } = focusedChat(); const last = (previewsAtom.get()[id] || [])[0]; if (last) reopenPreview(last) } } }
    ])

    ctx.onEvent('session.info', e => {
      const stored = e.payload?.stored_session_id || e.payload?.session_key
      if (e.session_id && stored) {
        runtimeToStored.set(e.session_id, stored)
        if (runtimeToStored.size > 500) runtimeToStored.delete(runtimeToStored.keys().next().value)
        syncLive()
      }
    })
    for (const atomLike of [host.state.busyBySession, host.state.focusedSessionId, host.state.focusedStoredSessionId]) {
      ctx.onDispose(atomLike.listen(syncLive))
    }
    // opening a chat marks it read in the backend: pick that up so its dot goes quiet here too
    ctx.onDispose(host.state.focusedStoredSessionId.listen(() => setTimeout(refreshSoon, 1200)))
    syncLive()
    ctx.onEvent('preview.open', e => {
      if (reopening) return
      const url = String(e.payload?.url || '').trim()
      // A runtime id we never saw a session.info for is a chat this window cannot name: skip it, never guess.
      const owner = e.session_id ? runtimeToStored.get(e.session_id) : host.state.focusedStoredSessionId.get()
      if (!url || !owner) return
      const next = rememberPreview(previewsAtom.get(), owner, { url, label: String(e.payload?.label || '').trim(), at: Date.now() })
      previewsAtom.set(next)
      storage?.set('previews', next)
    })
    for (const type of ['session.title', 'sessions.changed']) ctx.onEvent(type, () => refreshSoon())
    ctx.onDispose(() => {
      clearTimeout(refreshTimer)
      refreshTimer = null
    })
    ctx.registerSettingsPage?.({ id: 'settings', title: 'Squad Hub', icon: 'organization', render: () => jsx(SettingsPage, {}) })

    window.__squadHub = { setSide, newChat, atFolders, savePrefs, floatState, goNextPending, applyTheme: () => requestTheme?.('squads'), host, queryClient, refresh, refreshSoon, loadSnapshot, loadWorktrees, buildBotTree, visibleBots, prefsAtom, previewsAtom, reopenPreview }
    ctx.onDispose(() => {
      delete window.__squadHub
    })
  }
}
