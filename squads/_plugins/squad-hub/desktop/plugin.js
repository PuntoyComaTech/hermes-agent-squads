// Hermes Agent Squads Hub (key `squad-hub`) — a Hermes Desktop plugin for the Hermes Agent Squads way of working.
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
import { Fragment as React_Fragment, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
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
/** The big lettering of an empty chat: the squad the bot belongs to (stamped by squadctl), else its own title. */
const introName = bot => {
  const squad = String(bot.squadName || bot.ui_meta?.['hermes-bots']?.squadName || '').trim()
  return squad || bot.title || bot.name
}

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
    bots.push({ name: p.name, title: botTitle(p), role, other: !core, section: sectionOf(p), squadName: String(p.ui_meta?.['hermes-bots']?.squadName || '').trim() })
  }
  const managed = new Set(bots.filter(b => b.role === 'manager').map(b => b.title.replace(/\s+manager$/i, '').toLowerCase()))
  for (const b of bots) b.group = b.other && b.section && b.section !== 'Managers' && !managed.has(b.section.toLowerCase()) ? b.section : ''
  // A section holding one bot is no squad: that bot stands on the first level, like a manager, not inside a group
  const members = {}
  for (const b of bots) if (b.group) members[b.group] = (members[b.group] || 0) + 1
  for (const b of bots) {
    if (b.group && members[b.group] === 1) {
      b.group = ''
      b.other = false
    }
  }
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
  const { live, unread, focused } = attentionSets(attention)
  if (live.has(session.id)) return 'working'
  if (session.id === focused) return 'current'
  return session.unread || unread.has(session.id) ? 'unread' : ''
}
/** `attention` is built once per render and read for every chat of the list, so its id lists become sets once. */
const ATTENTION_SETS = new WeakMap()
const NO_ATTENTION = { live: new Set(), unread: new Set(), focused: null }
function attentionSets(attention) {
  if (!attention || typeof attention !== 'object') return NO_ATTENTION
  let sets = ATTENTION_SETS.get(attention)
  if (!sets) {
    sets = { live: new Set(attention.live || []), unread: new Set(attention.unread || []), focused: attention.focused ?? null }
    ATTENTION_SETS.set(attention, sets)
  }
  return sets
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
/** Past this many folders a project never unfolds inside the list: a click opens it in its own view, with a way back. */
const FOCUS_FOLDERS = 3
const projectOpensInFocus = project => project.folders.length > FOCUS_FOLDERS

/** A bot's chats outside any project: what needs you (working, unread, in view) plus the newest `keep`, newest
 *  first; the rest fold under one \"older chats\" row. */
function looseSplit(loose, attention, keep = 3) {
  const shown = []
  const rest = []
  ;[...(loose || [])].sort((a, b) => sessionTime(b) - sessionTime(a)).forEach((s, i) => (i < keep || chatState(s, attention) ? shown : rest).push(s))
  return { shown, rest }
}

/** The bell's rows: chats parked on a question first, then the cards grouped by board, the board with the newest
 *  card first and its cards newest first. */
function bellGroups(items) {
  const chats = (items || []).filter(x => x.type === 'chat')
  const by = new Map()
  for (const x of items || []) {
    if (x.type !== 'card') continue
    if (!by.has(x.board)) by.set(x.board, [])
    by.get(x.board).push(x)
  }
  const boards = [...by.entries()]
    .map(([board, list]) => ({ key: 'board:' + board, board, items: list.sort((a, b) => b.at - a.at) }))
    .sort((a, b) => b.items[0].at - a.items[0].at)
  return [...(chats.length ? [{ key: 'chats', board: '', items: chats }] : []), ...boards]
}

/** Prefs saved by an older version, brought once to this version's defaults: floating sides on, the Kanban sidebar
 *  row hidden (squads read their boards here), the Squads theme on every bot. A choice made after that is kept. */
const PREFS_VERSION = 3
function upgradePrefs(stored, defaults) {
  const p = { ...defaults, ...(stored || {}) }
  // the version saved with the prefs, never the defaults' own: prefs from before versioning have none
  const from = stored ? Number(stored.prefsVersion) || 0 : PREFS_VERSION
  if (from < 2) {
    p.floatSides = true
    p.squadsTheme = true
    p.hiddenNav = [...new Set([...(p.hiddenNav || []), 'kanban:nav'])]
  }
  // 1.3.0 hid Desktop's own profile selector and Bots tab by default: they come back, hiding them is a choice
  if (from < 3) {
    p.hideRail = false
    p.hideBotsTab = false
  }
  p.prefsVersion = PREFS_VERSION
  return p
}

/** The layout group that holds the chat (`workspace`), read from the layout tree Desktop persists. A zone whose tab
 *  strip is off (or that fronts a session tab) has no `workspace` tab in the DOM, so the tree is the only sure way. */
function workspaceGroup(node) {
  if (!node || typeof node !== 'object') return null
  if (node.type === 'group') return (node.panes || []).includes('workspace') ? node.id : null
  for (const c of node.children || []) {
    const id = workspaceGroup(c)
    if (id) return id
  }
  return null
}

/** Whether the chat takes the whole row while the sides float. `widths`: the widths of the row's other columns that
 *  stay in the flow (sides excluded). Only when none shows: beside a preview both keep the split Desktop holds, so a
 *  sash the user drags still decides it (forcing the chat to grow put it back on the default split). */
const chatAlone = widths => !(widths || []).some(w => w > 0)

/** The cards on a board that wait on you and were not cleared from the bell: what a manager's row counts. */
const boardWaiting = (board, dismissed) => (board ? bellVisible(bellItems([], [], [board]), dismissed) : [])

/** The bots of one squad, the manager first: those stamped with the same squad name, or (a fleet with no stamp) filed
 *  in a Desktop section named like the manager ("Acme shop manager" -> section "Acme shop"). Empty when the bot
 *  stands alone, so a lone bot gets no picker. */
function squadMembers(profiles, name) {
  const me = (profiles || []).find(p => p.name === name)
  if (!me) return []
  const own = p => String(p.ui_meta?.['hermes-bots']?.squadName || p.ui_meta?.['hermes-squads']?.name || '').trim().toLowerCase()
  const sec = p => sectionOf(p).toLowerCase()
  const key = own(me) || (botRole(me) === 'manager' ? botTitle(me).replace(/\s+manager$/i, '').toLowerCase() : sec(me))
  if (!key || key === 'managers') return []
  const rows = profiles.filter(p => p.name === name || own(p) === key || (!own(p) && sec(p) === key))
  rows.sort((a, b) => Number(b.name === name) - Number(a.name === name) || (botRole(a) === 'manager' ? 0 : 1) - (botRole(b) === 'manager' ? 0 : 1) || a.name.localeCompare(b.name))
  return rows.length > 1 ? rows.map(p => ({ name: p.name, title: botTitle(p), role: botRole(p) })) : []
}

/** What a project can shed, for the Clean up dialog. Chats: idle ones (not working, unread, in view or pinned) not
 *  used for `days`, plus the idle chats of a worktree that goes. Worktrees: linked checkouts with nothing to lose (no
 *  uncommitted files, nothing unpushed, no chat that needs you, no open or draft PR); ticked when their PR is merged
 *  or closed, or when their last chat is older than `days` (a removed worktree frees its disk space and keeps its
 *  branch, so its commits stay). A worktree with no chat at all has no known age: offered unticked. `statuses` maps a
 *  lane key to laneStatus(); a checkout whose status could not be read is left alone. Nothing is deleted from
 *  history: chats are archived. */
function cleanupPlan(project, statuses, attention, now, days = 2) {
  const worktrees = []
  const goes = new Set()
  const idle = t => t > 0 && now - t > days * 86400
  for (const f of project.folders) {
    for (const lane of f.lanes) {
      if (lane.main || isKanbanWorktree(lane.path)) continue
      const st = (statuses || {})[lane.key]
      if (!st || !st.known || st.changed > 0 || st.ahead > 0) continue
      if (lane.sessions.some(x => chatState(x, attention))) continue
      const pr = st.pr?.state || ''
      if (pr === 'open' || pr === 'draft') continue
      const last = laneTime(lane)
      const reason = pr === 'merged' || pr === 'closed' ? pr : idle(last) ? 'idle' : last ? 'recent' : 'nochats'
      worktrees.push({ key: lane.key, path: lane.path, folderPath: f.path, label: lane.label, branch: lane.branch, folder: f.label, reason, last, pre: reason !== 'recent' && reason !== 'nochats' })
      if (reason !== 'recent' && reason !== 'nochats') goes.add(lane.key)
    }
  }
  const chats = []
  for (const f of project.folders) {
    for (const lane of f.lanes) {
      for (const x of lane.sessions) {
        if (chatState(x, attention) || x.pinned) continue
        const old = idle(sessionTime(x))
        if (old || goes.has(lane.key)) chats.push({ session: x, folder: f.label, lane: lane.main ? '' : lane.label, pre: true })
      }
    }
  }
  chats.sort((a, b) => sessionTime(a.session) - sessionTime(b.session))
  return { worktrees, chats }
}

/** The chats a closed project lists right under its own row: what is working, unread or in view, each a shortcut
 *  that skips opening the project. An open project lists none: every chat shows once, inside its own folder. */
const projectDigest = (project, attention, open = true) => (open ? [] : activeIn(project.folders, attention))

/** A folder of an open project starts unfolded when a chat in it needs you, so that chat shows where it lives;
 *  quiet folders start folded. The user's own open/closed choice always wins. */
const folderOpensByDefault = (folder, attention) => needsYou(activeIn(folder, attention)).length > 0

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
const NO_PREVIEWS = Object.freeze([])
/** The previews remembered for a chat. A chat with none gets one shared empty list, so a component reading it
 *  through useSyncExternalStore sees the same snapshot every time and re-renders only when its own chat changes. */
const previewsFor = (map, storedId) => (map && map[storedId]) || NO_PREVIEWS
/** A conversation that moved to a new stored id (compression) keeps its previews under the new id: newest first, one
 *  per url, capped. Desktop re-keys its own tabs the same way. */
function rekeyPreviews(map, from, to, perChat = 8) {
  if (!from || !to || from === to || !map[from]) return map
  const seen = new Set()
  const list = [...(map[to] || []), ...map[from]]
    .sort((a, b) => (b.at || 0) - (a.at || 0))
    .filter(p => !seen.has(p.url) && seen.add(p.url))
    .slice(0, perChat)
  const next = { ...map, [to]: list }
  delete next[from]
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
// ── squads at work: boards, timeline, what went wrong, what waits for you ──
/** Blocks a human answers: the bot asked (`needs_input`), lacks access (`capability`), or an older block without a
 *  kind. A `dependency` or `transient` block clears on its own. */
const HUMAN_BLOCKS = new Set(['needs_input', 'capability', '', null, undefined])
const boardTasks = board => (board?.columns || []).flatMap(c => c.tasks || [])

/** A board payload as the counts a squad row, the bell and the timeline read. */
function boardDigest(board) {
  const n = {}
  for (const c of board?.columns || []) n[c.name] = (c.tasks || []).length
  const needsYou = boardTasks(board).filter(t => t.status === 'blocked' && HUMAN_BLOCKS.has(t.block_kind))
  return {
    blocked: n.blocked || 0,
    review: n.review || 0,
    running: n.running || 0,
    queued: (n.triage || 0) + (n.todo || 0) + (n.scheduled || 0) + (n.ready || 0),
    done: n.done || 0,
    needsYou
  }
}

/** The bots that actually took cards on a board. The board payload's own `assignees` lists every profile on disk
 *  (it feeds the assignee picker), so it cannot say whose board it is. */
const taskAssignees = board => [...new Set(boardTasks(board).map(t => t.assignee).filter(Boolean))].sort()

/** The board a bot leads: the board named like it (squads name the board after the manager), else the board its own
 *  workers (`<bot>-<role>`) take cards from. `boards`: [{ slug, assignees }]. */
function boardForBot(name, boards) {
  return (
    boards.find(b => b.slug === name) ||
    boards.find(b => (b.assignees || []).includes(name) && (b.assignees || []).some(a => a.startsWith(name + '-'))) ||
    null
  )
}

const FAILED_RUNS = new Set(['crashed', 'timed_out', 'gave_up', 'spawn_failed'])
const RUN_TONE = { completed: 'done', done: 'done', running: 'run', blocked: 'block', review_requested: 'review', changes_requested: 'review', reclaimed: 'stop', stale: 'stop', rate_limited: 'stop', scheduled: 'queued', dependency_wait: 'dep' }
/** Every state the timeline, the cards and the legend speak, in the order a card moves through them. */
const STATES = ['queued', 'dep', 'run', 'block', 'review', 'done', 'fail', 'stop']
const QUEUED = new Set(['triage', 'todo', 'ready', 'scheduled'])
/** Where a card sits now, in the legend's words. A queued card with parents waits on another card. */
function cardState(t) {
  if (!t) return 'queued'
  if (t.status === 'blocked') return 'block'
  if (t.status === 'review') return 'review'
  if (t.status === 'running') return 'run'
  if (t.status === 'done' || t.status === 'archived') return 'done'
  return (t.link_counts?.parents || 0) > 0 && t.status === 'todo' ? 'dep' : 'queued'
}
const runTone = outcome => (FAILED_RUNS.has(outcome) ? 'fail' : RUN_TONE[outcome] || (outcome ? 'stop' : 'run'))

/** One lane per bot that ran work. Each card draws the wait before its first run (queued, or waiting on another
 *  card when it has parents), one bar per run, and where it sits since its last run (blocked, in review, queued
 *  again) up to now. A task without its run list draws one bar from its own stamps. Times are unix seconds. */
function timelineOf(tasks, now, from) {
  const lanes = new Map()
  const lane = name => {
    if (!lanes.has(name)) lanes.set(name, { name, bars: [] })
    return lanes.get(name).bars
  }
  for (const t of tasks) {
    const runs = Array.isArray(t.runs) && t.runs.length
      ? t.runs
      : t.started_at
        ? [{ profile: t.assignee, started_at: t.started_at, ended_at: t.completed_at || (t.status === 'running' ? null : t.started_at), outcome: t.status === 'done' ? 'completed' : t.status === 'running' ? null : t.status }]
        : []
    const first = runs.reduce((m, r) => Math.min(m, r.started_at || Infinity), Infinity)
    const owner = t.assignee || runs[0]?.profile || 'unassigned'
    const waiting = (t.link_counts?.parents || 0) > 0 ? 'dep' : 'queued'
    const base = { taskId: t.id, title: t.title, status: t.status }
    if (t.created_at && first !== Infinity && first - t.created_at > 60) {
      lane(owner).push({ ...base, kind: 'wait', state: waiting, start: t.created_at, end: first })
    } else if (t.created_at && first === Infinity && !['done', 'archived'].includes(t.status)) {
      lane(owner).push({ ...base, kind: 'wait', state: t.status === 'blocked' ? 'block' : waiting, start: t.created_at, end: now, open: true })
    }
    let lastEnd = 0
    let lastProfile = owner
    let open = false
    for (const r of runs) {
      if (!r.started_at) continue
      const tone = runTone(r.ended_at ? r.outcome : null)
      lane(r.profile || owner).push({ ...base, kind: 'run', state: tone, tone, start: r.started_at, end: r.ended_at || now, open: !r.ended_at, outcome: r.outcome || (r.ended_at ? '' : 'running'), summary: r.summary || r.error || '' })
      if (!r.ended_at) open = true
      else if (r.ended_at >= lastEnd) {
        lastEnd = r.ended_at
        lastProfile = r.profile || owner
      }
    }
    const sitting = t.status === 'blocked' ? 'block' : t.status === 'review' ? 'review' : QUEUED.has(t.status) ? waiting : ''
    if (!open && lastEnd && sitting && now - lastEnd > 60) {
      lane(t.status === 'blocked' ? lastProfile : owner).push({ ...base, kind: 'state', state: sitting, start: lastEnd, end: now, open: true })
    }
  }
  const out = []
  for (const l of lanes.values()) {
    const bars = l.bars.filter(b => b.end >= from && b.start <= now).sort((a, b) => a.start - b.start)
    if (bars.length) out.push({ name: l.name, bars })
  }
  return { from, to: now, lanes: out.sort((a, b) => a.name.localeCompare(b.name)) }
}

const SEVERITY_RANK = { critical: 0, error: 1, warning: 2, info: 3 }
const LONG_WAIT = 2 * 3600
const LONG_BLOCK = 12 * 3600

/** What went wrong on a board, loudest and newest first: core's own diagnostics (repeated crashes, stuck blocks,
 *  block/unblock cycling, invented cards…) plus what only timing shows: failed runs, cards that waited hours before a
 *  bot picked them up, and blocks that have waited on a human for half a day. */
function issuesOf(tasks, diagnostics, now) {
  const out = []
  const covered = new Set()
  for (const row of diagnostics || []) {
    for (const d of row.diagnostics || []) {
      covered.add(row.task_id + ':' + d.kind)
      covered.add(row.task_id)
      out.push({ kind: d.kind, severity: d.severity || 'warning', taskId: row.task_id, title: row.task_title || row.task_id, assignee: row.task_assignee || '', at: d.last_seen_at || now, text: d.title || d.message || d.summary || '', count: d.count || 1, source: 'hermes' })
    }
  }
  for (const t of tasks) {
    const runs = Array.isArray(t.runs) ? t.runs : []
    const failed = runs.filter(r => FAILED_RUNS.has(r.outcome))
    if (failed.length && !covered.has(t.id)) {
      const last = failed[failed.length - 1]
      out.push({ kind: 'run_failed', severity: failed.length > 1 ? 'error' : 'warning', taskId: t.id, title: t.title, assignee: last.profile || t.assignee || '', at: last.ended_at || now, text: last.outcome, count: failed.length, source: 'timeline' })
    }
    const first = runs.reduce((m, r) => Math.min(m, r.started_at || Infinity), t.started_at || Infinity)
    const parents = t.link_counts?.parents || 0
    if (t.created_at && first !== Infinity && !parents && first - t.created_at > LONG_WAIT) {
      out.push({ kind: 'slow_start', severity: 'info', taskId: t.id, title: t.title, assignee: t.assignee || '', at: first, text: String(Math.round((first - t.created_at) / 3600)) + 'h', count: 1, source: 'timeline' })
    }
    if (t.status === 'blocked' && HUMAN_BLOCKS.has(t.block_kind) && !covered.has(t.id + ':stuck_in_blocked')) {
      const since = runs.filter(r => r.outcome === 'blocked').reduce((m, r) => Math.max(m, r.ended_at || 0), 0) || t.completed_at || t.started_at || t.created_at || now
      if (now - since > LONG_BLOCK) out.push({ kind: 'waiting_on_you', severity: 'warning', taskId: t.id, title: t.title, assignee: t.assignee || '', at: since, text: String(Math.round((now - since) / 3600)) + 'h', count: 1, source: 'timeline' })
    }
  }
  return out.sort((a, b) => (SEVERITY_RANK[a.severity] ?? 4) - (SEVERITY_RANK[b.severity] ?? 4) || b.at - a.at)
}

/** Everything waiting on the user, chats first (a bot is parked on an approval or a question), then cards a bot
 *  blocked for a human answer. `active`: session.active_list rows; `chats`: stored chat rows; `boards`:
 *  [{ slug, digest }]. Keys are stable, so a new item can be told from one already seen. */
function bellItems(active, chats, boards) {
  const byId = new Map((chats || []).map(c => [c.id, c]))
  const items = []
  for (const r of active || []) {
    if (r.status !== 'waiting') continue
    const chat = byId.get(r.session_key) || null
    items.push({ key: 'chat:' + r.session_key, stamp: '', at: r.last_active || 0, type: 'chat', runtimeId: r.id, storedId: r.session_key, title: r.title || chat?.title || 'Chat', profile: chat?.profile || '' })
  }
  const cards = []
  for (const b of boards || []) {
    for (const t of b.digest?.needsYou || []) cards.push({ key: 'card:' + b.slug + ':' + t.id, stamp: (t.block_recurrences || 0) + ':' + (t.started_at || t.created_at || 0), at: t.started_at || t.created_at || 0, type: 'card', board: b.slug, taskId: t.id, title: t.title, profile: t.assignee || '', summary: t.latest_summary || '' })
  }
  return items.concat(cards.sort((x, y) => y.at - x.at))
}
/** One row per live chat across backends: a shared backend answers for several bots, so the same chat comes back
 *  once per ask; `waiting` wins over any other status reported for it. */
function mergeActive(lists) {
  const by = new Map()
  for (const list of lists || []) {
    for (const r of list || []) {
      const key = r.session_key || r.id
      const had = by.get(key)
      if (!had || (r.status === 'waiting' && had.status !== 'waiting')) by.set(key, r)
    }
  }
  return [...by.values()]
}
/** A board whose read failed this round keeps its last known digest, so its waiting cards do not vanish and come
 *  back as new (a second notification for the same card). Boards that left the list are dropped. */
function keepLastBoards(results, slugs, previous) {
  const fresh = (results || []).filter(Boolean) // a failed read is null
  const got = new Set(fresh.map(b => b.slug))
  const kept = (previous || []).filter(b => slugs.includes(b.slug) && !got.has(b.slug))
  return [...fresh, ...kept].sort((a, b) => slugs.indexOf(a.slug) - slugs.indexOf(b.slug))
}
const TIMELINE_CAP = 150
const OPEN_STATUSES = new Set(['running', 'blocked', 'review', 'ready', 'todo', 'triage', 'scheduled'])
/** Cards that touch the window: open cards, and finished or archived cards that ended inside it (an archived card with
 *  no end stamp is out). Blocked and in-review first, then newest activity, so a cap never hides a stuck card. */
function windowTasks(tasks, now, from) {
  const last = t => t.completed_at || t.started_at || t.created_at || 0
  const stuck = t => (t.status === 'blocked' || t.status === 'review' ? 0 : 1)
  return (tasks || [])
    .filter(t => OPEN_STATUSES.has(t.status) || (t.completed_at && t.completed_at >= from))
    .sort((a, b) => stuck(a) - stuck(b) || last(b) - last(a))
}
/** A dismissal names one occurrence: a card blocked again (a new run, a new recurrence) or a chat parked again
 *  comes back to the bell. */
const dismissKey = x => x.key + '@' + (x.stamp || '')
const bellVisible = (items, dismissed) => items.filter(x => !(dismissed || {})[dismissKey(x)])
/** Chat dismissals that no longer match a waiting chat: a chat that stopped waiting and asks again rings again. */
const staleChatDismissals = (items, dismissed) => {
  const waiting = new Set(items.filter(x => x.type === 'chat').map(dismissKey))
  return Object.keys(dismissed || {}).filter(k => k.startsWith('chat:') && !waiting.has(k))
}
const newSince = (seen, items) => items.filter(x => !seen.includes(x.key))
/** What to notify about: nothing on the first look (the state the user opened Hermes to), then only the cards that
 *  were not in the previous look. A parked chat already gets Desktop's own "needs input" notification. */
const bellFresh = (known, items) => {
  if (!known) return []
  const had = new Set(known)
  return items.filter(x => x.type === 'card' && !had.has(x.key))
}

/** A squad card reference from model-written directive attributes: ids only, never content. */
const TASK_ID_RE = /^t_[0-9a-f]{4,32}$/
const BOARD_SLUG_RE = /^[a-z0-9][a-z0-9_-]{0,63}$/
function cardRef(attrs) {
  const id = String(attrs?.id || '')
  const board = String(attrs?.board || '')
  if (!TASK_ID_RE.test(id) || (board && !BOARD_SLUG_RE.test(board))) return null
  return { id, board }
}
function boardRef(attrs) {
  const board = String(attrs?.board || '')
  return BOARD_SLUG_RE.test(board) ? { board } : null
}

/** A worktree's pull request and checkout as one quiet chip: PR number and state, files changed, commits to push.
 *  `known` is false when the checkout could not be read: its zeros then say nothing, and the chip stays quiet. */
function laneStatus(pr, repo) {
  const state = pr ? (pr.draft ? 'draft' : pr.state || 'open') : ''
  const url = /^https:\/\/[^/\s]+\//.test(String(pr?.url || '')) ? pr.url : ''
  return { pr: pr ? { number: pr.number, state, url, title: pr.title } : null, changed: repo?.changed || 0, ahead: repo?.ahead || 0, behind: repo?.behind || 0, known: Boolean(repo) }
}
/** Block reasons core writes for itself, not for the user. */
const MACHINE_REASONS = new Set(['initial_status', 'parent_not_done', ''])
/** What a card asks of the user: the reason of its last block (a bot writes it there), else its latest summary. */
function cardNeeds(task, events, comments) {
  const last = (events || []).filter(e => e.kind === 'blocked').pop()
  const said = String(last?.payload?.reason || '').trim()
  const note = (comments || []).filter(c => (c.created_at || 0) >= (last?.created_at || 0)).pop()
  const reason = !MACHINE_REASONS.has(said) ? said : String(note?.body || task?.latest_summary || task?.body || '').trim()
  return { reason, at: last?.created_at || 0, kind: last?.payload?.kind || task?.block_kind || '' }
}
const HISTORY_KINDS = new Set(['created', 'promoted', 'dependency_wait', 'claimed', 'blocked', 'unblocked', 'review_requested', 'changes_requested', 'completed', 'crashed', 'timed_out', 'gave_up', 'reclaimed', 'scheduled', 'archived'])
/** A card's story, newest first, without heartbeats, spawns and comments. */
const historyOf = (events, limit = 8) => (events || []).filter(e => HISTORY_KINDS.has(e.kind)).map(e => ({ kind: e.kind, at: e.created_at || 0 })).sort((a, b) => b.at - a.at).slice(0, limit)
/** The board holding a card id, for a card line written without one: the boards already loaded carry every task. */
function boardOfTask(id, boards) {
  for (const b of boards || []) if (boardTasks(b.board).some(t => t.id === id)) return b.slug
  return ''
}
/** The manager to answer a board's card to: the bot named like the board, else the one whose workers take its cards. */
function boardManager(slug, profileNames, assignees) {
  if ((profileNames || []).includes(slug)) return slug
  const a = assignees || []
  return a.find(x => a.some(y => y.startsWith(x + '-'))) || ''
}

/** Folded/unfolded rows. `collapsed` maps a row key to true (folded) or false (unfolded); a row never touched has no
 *  entry and follows its default. */
const openState = (flag, defaultOpen) => (flag === undefined ? defaultOpen : !flag)
const toggledCollapsed = (collapsed, key, defaultCollapsed = false) => ({ ...collapsed, [key]: !(key in collapsed ? collapsed[key] : defaultCollapsed) })

/** Which stored chat a runtime id serves. `session.info` and `session.create` name it for certain (`sure`). The pair
 *  of focused atoms is read while Desktop moves them one after the other (the stored id first, the primary runtime a
 *  resume later), so it only fills a gap and never overwrites what a sure source said. `from` is the stored id a sure
 *  binding moved away from (a compressed conversation), so what was filed under it can follow. */
function bindRuntime(bound, runtime, stored, sure = false) {
  const had = bound.get(runtime)
  if (!runtime || !stored || (!sure && had?.sure)) return { changed: false, from: '' }
  bound.set(runtime, { stored, sure })
  return { changed: true, from: sure && had?.sure && had.stored !== stored ? had.stored : '' }
}

/** What each zone of the layout Desktop persists (`hermes.desktop.layoutTree.v2`) shows: { zone id: active pane,
 *  suffixed ':min' when the zone is folded }. */
function zonesOf(node, out = {}) {
  if (!node) return out
  if (node.type === 'group') out[node.id] = node.active + (node.minimized ? ':min' : '')
  else for (const c of node.children || []) zonesOf(c, out)
  return out
}
/** The zones of every layout tree given (a mode's tree can be missing); a later tree wins where they share a zone. */
function zonesOfAll(trees) {
  const out = {}
  for (const tree of trees) zonesOf(tree, out)
  return out
}
/** A layout tree from its stored text: undefined when it is not JSON, null when there is none. */
function parseLayout(raw) {
  try {
    return JSON.parse(raw || 'null')
  } catch {
    return undefined
  }
}
const sideSignature = (groups, zones) => groups.map(id => id + '=' + (zones[id] || '')).join('|')
/** A change on a hidden, unpinned side that leaves it unfolded is a reveal from elsewhere (⌃`, ⌘J, ⌘G, a menu). The
 *  first look (`previous` undefined) is no change. */
const isReveal = (previous, signature, side) =>
  previous !== undefined && signature !== previous && !signature.includes(':min') && side.groups.length > 0 && !side.open && !side.pinned

/** The managers whose Desktop-cards setting still has to be written: not done, and not tried within `retryMs` (a bot
 *  without the agent half answers an error every time; asking again at every refresh would wake its backend for nothing). */
const CARDS_RETRY_MS = 10 * 60 * 1000
function cardsToSwitch(managers, done, triedAt, now, retryMs = CARDS_RETRY_MS) {
  const have = new Set(done)
  return managers.filter(bot => !have.has(bot) && !(triedAt[bot] && now - triedAt[bot] < retryMs))
}

/** `promise` or a rejection after `ms`, whichever comes first, with the timer cleared either way. */
function withTimeout(promise, ms, message = 'timeout') {
  let timer
  const limit = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(message)), ms)
  })
  return Promise.race([promise, limit]).finally(() => clearTimeout(timer))
}
// ─────────────────────────── END MODEL (pure) ───────────────────────────

// ───────────────────────────── host wiring ─────────────────────────────
const {
  host, atom, useValue, useQuery, queryClient, usePluginI18n, Codicon, DisclosureCaret, SearchField, Tip, Button, Input,
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
  SessionStatusDot, COMPOSER_AREAS, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, ToggleRow, EmptyState,
  CapabilitiesView, ColorSwatches, PROFILE_SWATCHES, CHAT_EMPTY_AREA, haptic, isSubmitEnter, requestTheme, useTheme, THEMES_AREA, STATUSBAR_AREAS, PALETTE_AREA, KEYBINDS_AREA, SIDEBAR_NAV_PREFS_AREA,
  TRANSCRIPT_DIRECTIVE_AREA, Skeleton, Wordmark, ackStoredSessionId
} = sdk

/** Read a chat in Desktop's own unread store, in its own bot's bucket and on the backend. Desktop acks the chat in view
 *  under the window's profile only, so a chat of another bot opened as a tab kept its "unread" mark for good. */
async function markRead(bot, id) {
  if (!id) return
  try {
    const row = (queryClient.getQueryData(SNAPSHOT_KEY)?.chats || []).find(c => c.id === id && (!bot || c.profile === bot))
    const ids = row ? chatIds(row) : [id]
    const raw = JSON.parse(localStorage.getItem('hermes.desktop.unreadFinishedSessions') || '{}')
    for (const x of ids) {
      // the owner's bucket; other buckets only when the owner is unknown (another bot's same-named chat stays)
      const buckets = bot ? [bot] : [null, ...Object.keys(raw).filter(p => (raw[p] || []).includes(x))]
      for (const p of buckets) ackStoredSessionId?.(x, p)
    }
  } catch {}
  if (bot) await patchSession({ name: bot }, id, { unread: false }).catch(() => null)
}

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
    chipWaiting: '{0} waiting on you', chipBlocked: '{0} waiting on you · seen', chipRunning: '{0} running', chipReview: '{0} in review', chipHead: 'Cards on the {0} board that wait on you', chipTimeline: 'Open the timeline', cleanMenu: 'Clean up…', cleanTitle: 'Clean up {0}', cleanHelp: 'Pick what to tidy. Chats are archived; a removed worktree frees its disk space and keeps its branch, so no commit is lost.', cleanNothing: 'Nothing to clean: every chat is recent or needs you, and every worktree is in use.', cleanWorktrees: 'Worktrees with nothing to lose', cleanChats: 'Chats unused for 2+ days', cleanWhy_merged: 'PR merged', cleanWhy_closed: 'PR closed', cleanWhy_idle: 'unused for 2+ days', cleanWhy_recent: 'used recently', cleanWhy_nochats: 'no chats, check it first', cleanMore: '{0} more are not shown', cleanKeeps: 'Kept: chats working, unread, in view or pinned; worktrees with changes, unpushed commits or an open PR.', cleanGo: 'Clean up ({0})', cleaning: 'Cleaning…', cleanDone: '{0} cleaned up.', cleanFailed: '{0} could not be.', squadBots: 'Squad bots', 
    openProject: 'Open the project', back: 'Back to the list', foldersN: '{0} folders', olderChats: 'Older chats', bellChats: 'Chats asking you', bellClearGroup: 'Clear', 
    search: 'Search chats, projects, worktrees', refresh: 'Refresh', loading: 'Loading…', loadFailed: 'Could not load',
    newChatWith: 'New chat with {0}', newChatIn: 'New chat in {0}', newChatHere: 'New chat here', 
    outside: 'Chats outside a project', noChats: 'No chats yet', noProjects: 'No projects yet', createOne: 'create one',
    otherBots: 'Other bots', nothingMatches: 'Nothing matches', noBots: 'No bots yet', noBotsHint: 'Ask the Builder to install a squad.',
    newProject: 'New project…', addFolder: 'Add folders…', removeFolder: 'Remove folder from project', newWorktree: 'New worktree…',
    removeWorktree: 'Remove worktree', renameProject: 'Rename project…', removeProject: 'Remove project (keeps the folders)',
    scheduled: 'Scheduled jobs', messaging: 'Messaging', capabilities: 'Capabilities…', kanban: 'Kanban board', pinTop: 'Pin to top',
    unpin: 'Unpin', hideBot: 'Hide from Squads', copyPath: 'Copy path', reveal: 'Reveal in Finder', 
    openWindow: 'Open in a new window', rename: 'Rename…', archive: 'Archive', previews: 'Previews', 
    noPreviews: 'No previews saved for this chat', primary: 'primary', name: 'Name', folders: 'Folders', none: 'None yet',
    cancel: 'Cancel', create: 'Create', creating: 'Creating…', save: 'Save', remove: 'Remove', projectIn: 'New project in {0}',
    projectHelp: 'A project groups one or more folders. Each folder can get its own worktrees.', projectName: 'e.g. Website redesign',
    worktreeIn: 'New worktree in {0}', worktreeHelp: 'A separate checkout under .worktrees/ with its own branch, so chats work in parallel.',
    branch: 'Branch (optional)', startFrom: 'Start from', defaultTag: '(default)', worktreeReady: 'Worktree ready: {0}',
    removeWorktreeAsk: 'Remove worktree?', removeWorktreeBody: 'Git refuses if it has uncommitted changes. The branch is kept.',
    renameChat: 'Rename chat', setup: 'Workspace', envDoubleClick: 'Open .env files on double-click', envDoubleClickHint: 'In the file tree they open in your system editor; off leaves the tree as Hermes made it.', creditsBy: 'Made by', creditsPart: 'part of', hideBotsTab: 'Hide the Bots tab',
    hideBotsTabHint: 'Squads replaces it: bots, projects and chats live in one list.', hideRail: 'Hide the profile selector',
    hideRailHint: 'The bottom strip that switches the whole window between bots. Squads opens each chat under its own bot instead.',
    showOthers: 'Show other bots that have chats', showOthersHint: 'Bots that are not default, the builder or a squad manager.',
    sortRecent: 'Order bots by recent activity', sortRecentHint: 'Off: default, builder, then managers.', navRows: 'Sidebar rows',
    visibleBots: 'Visible bots', allVisible: 'Every bot you can talk to is listed here; squad workers never are.',
    ctxFiles: 'Files', ctxReview: 'Review', ctxTerminal: 'Terminal', botCaps: 'Capabilities of {0}',
    cmdOpen: 'Squads: focus the list', cmdNext: 'Squads: next chat that needs you', cmdFloat: 'Squads: floating sides on/off', cmdPinLeft: 'Squads: pin or hide the left side', cmdPinRight: 'Squads: pin or hide the right side', cmdLayout: 'Squads: choose the Squads layout', nothingPending: 'Nothing is waiting for you', pendingTip: 'Chats working or unread, across every bot', working: 'working', unread: 'unread', alsoPending: 'Also waiting here', floatSides: 'Floating sides', floatSidesHint: 'The left list and the right files/terminal take no width: bring the pointer near a screen edge and they slide over the chat, then hide when you leave. The side buttons in the title bar pin them.', layoutName: 'Squads layout', layoutHint: 'Squads left, chat in the middle, files over a short terminal on the right.', layoutPick: 'Pick “Squads” under Layout.', openBrowser: 'Open the browser', envFiles: 'Env files…', appearance: 'Icon and colour…', appearanceOf: 'Look of {0}', appearanceHelp: 'Shown here and in Sessions.', defaultIcon: 'Default', defaultColor: 'Bot colour', envIn: 'Env files in {0}', envHelp: 'They hold secrets, so Hermes keeps them out of its own viewer; each opens in your editor for that file.', openInEditor: 'Open in editor', noEnv: 'No .env file in this folder.', envOpenFailed: 'Could not open it. Is an app set to open this file type?', showMore: 'Show {0} more', cmdTheme: 'Squads: use the Squads theme', themeName: 'Squads theme', themeHint: 'On every bot: Catppuccin-inspired, low contrast, cream by day and mocha by night. Off, each bot keeps the theme you pick for it.', themeUse: 'Use it', cmdNewProject: 'Squads: new project…', cmdPreview: 'Squads: reopen a preview', pane: 'Squads', cmdTimeline: 'Squads: open the timeline', introNoProject: 'Chat outside a project', chatWordmark: 'Squad name on empty chats', chatWordmarkHint: 'An empty chat shows its squad in large letters and, below, the project, folder and worktree it works in.', tlSkipped: '{0} older cards are not drawn; pick a shorter window.', out_spawn_failed: 'did not start', out_stale: 'went stale', out_review_requested: 'sent to review', out_changes_requested: 'changes requested', out_scheduled: 'scheduled', iss_stranded_in_ready: 'Ready but nobody picks it up', iss_triage_aux_unavailable: 'Triage could not run', bellClear: 'Clear all', bellDismiss: 'Clear from the bell', bellMore: '{0} more', close: 'Close', noManager: 'No manager found for this board', replyDraft: 'About card {0} ("{1}") on the {2} board: ', cardOn: '{0} board · {1}', cardNeedsYou: 'What it asks you', cardLatest: 'Latest note', cardStory: 'History', cardReply: 'Answer in a chat', cardDetail: 'Details', tlHint: 'Hover a bar for details; click it for the card.', tlStill: 'still', st_queued: 'Queued', st_dep: 'Waiting on another card', st_run: 'In progress', st_block: 'Blocked', st_review: 'In review (QA)', st_done: 'Done', st_fail: 'Failed', st_stop: 'Stopped', sth_queued: 'Waiting for a bot to pick it up.', sth_dep: 'It starts by itself when the card it depends on is done.', sth_run: 'A bot is working on it right now.', sth_block: 'Stopped until someone answers: you, when it asks for input.', sth_review: 'Finished by its bot; a reviewer checks it before it is done.', sth_done: 'Finished and accepted.', sth_fail: 'A run crashed, timed out or gave up; the card retries or waits.', sth_stop: 'A run was taken back or paused (rate limit, manual reclaim).', ev_created: 'Created', ev_promoted: 'Ready to start', ev_dependency_wait: 'Waiting on another card', ev_claimed: 'A bot picked it up', ev_blocked: 'Blocked', ev_unblocked: 'Unblocked', ev_review_requested: 'Sent to review', ev_changes_requested: 'Changes requested', ev_completed: 'Done', ev_crashed: 'Run crashed', ev_timed_out: 'Run timed out', ev_gave_up: 'Gave up after retries', ev_reclaimed: 'Taken back', ev_scheduled: 'Scheduled', ev_archived: 'Archived', timeline: 'Timeline', timelineTitle: 'Squads timeline', timelineEmpty: 'No board with work yet', timelineEmptyHint: 'A squad’s board appears here once its manager files cards.', timelineQuiet: 'Nothing ran in this window.', issuesTitle: 'What went wrong', issuesNone: 'Nothing to look at in this window.', iss_repeated_failures: 'Repeated failures', iss_repeated_crashes: 'Repeated crashes', iss_stuck_in_blocked: 'Stuck blocked', iss_block_unblock_cycling: 'Blocked again and again', iss_hallucinated_cards: 'Invented cards', iss_prose_phantom_refs: 'Refers to cards that do not exist', iss_review_dependency_deadlock: 'Review deadlock', iss_running_with_open_parents: 'Ran before its parents finished', iss_run_failed: 'A run failed', iss_slow_start: 'Waited long to start', iss_waiting_on_you: 'Waiting on you', out_completed: 'done', out_crashed: 'crashed', out_timed_out: 'timed out', out_blocked: 'blocked', out_reclaimed: 'reclaimed', out_rate_limited: 'rate limited', out_gave_up: 'gave up', out_running: 'running', boardTip: '{0}: {1} blocked · {2} in review · {3} running. Click for the cards waiting on you; the timeline is at the bottom.', pr_open: 'open', pr_draft: 'draft', pr_merged: 'merged', pr_closed: 'closed', changedFiles: '{0} files changed', toPush: '{0} commits to push', bell: 'Waiting on you', bellHead: 'Waiting on you', bellNone: 'Nothing is waiting on you', bellCount: '{0} waiting on you', bellChat: '{0} asks you in its chat', notifyCard: '{0}: a card needs your answer', notifyMany: '{0} cards need your answer', cardInvalid: 'Not a valid card reference', cardMissing: 'Card not found', cardFailed: '{0} failed runs', cardTimeline: 'Timeline', cardBoard: 'Board', notifyAway: 'Notify me when a squad needs me', notifyAwayHint: 'A system notification (and a line from the pet, if one is out) when a card blocks for your answer while Hermes is in the background.'
  },
  es: {
    chipWaiting: '{0} te esperan', chipBlocked: '{0} te esperan · vistas', chipRunning: '{0} en curso', chipReview: '{0} en revisión', chipHead: 'Tarjetas del tablero {0} que te esperan', chipTimeline: 'Abrir la línea de tiempo', cleanMenu: 'Limpiar…', cleanTitle: 'Limpiar {0}', cleanHelp: 'Elige qué ordenar. Los chats se archivan; un worktree quitado libera su espacio en disco y conserva su rama, así que no se pierde ningún commit.', cleanNothing: 'Nada que limpiar: todos los chats son recientes o te necesitan y todos los worktrees están en uso.', cleanWorktrees: 'Worktrees sin nada que perder', cleanChats: 'Chats sin uso hace 2+ días', cleanWhy_merged: 'PR fusionado', cleanWhy_closed: 'PR cerrado', cleanWhy_idle: 'sin uso hace 2+ días', cleanWhy_recent: 'usado hace poco', cleanWhy_nochats: 'sin chats, revísalo antes', cleanMore: 'Hay {0} más que no se muestran', cleanKeeps: 'Se conservan: chats trabajando, sin leer, a la vista o fijados; worktrees con cambios, commits sin subir o un PR abierto.', cleanGo: 'Limpiar ({0})', cleaning: 'Limpiando…', cleanDone: '{0} limpiados.', cleanFailed: '{0} no se pudieron.', squadBots: 'Bots del squad', 
    openProject: 'Abrir el proyecto', back: 'Volver a la lista', foldersN: '{0} carpetas', olderChats: 'Chats anteriores', bellChats: 'Chats que te preguntan', bellClearGroup: 'Limpiar', 
    search: 'Buscar chats, proyectos, worktrees', refresh: 'Actualizar', loading: 'Cargando…', loadFailed: 'No se pudo cargar',
    newChatWith: 'Nuevo chat con {0}', newChatIn: 'Nuevo chat en {0}', newChatHere: 'Nuevo chat aquí', 
    outside: 'Chats fuera de un proyecto', noChats: 'Aún no hay chats', noProjects: 'Aún no hay proyectos', createOne: 'crea uno',
    otherBots: 'Otros bots', nothingMatches: 'Nada coincide', noBots: 'Aún no hay bots', noBotsHint: 'Pídele al Builder que instale un squad.',
    newProject: 'Nuevo proyecto…', addFolder: 'Añadir carpetas…', removeFolder: 'Quitar carpeta del proyecto', newWorktree: 'Nuevo worktree…',
    removeWorktree: 'Quitar worktree', renameProject: 'Renombrar proyecto…', removeProject: 'Quitar proyecto (conserva las carpetas)',
    scheduled: 'Tareas programadas', messaging: 'Mensajería', capabilities: 'Capacidades…', kanban: 'Tablero Kanban', pinTop: 'Fijar arriba',
    unpin: 'Desfijar', hideBot: 'Ocultar de Squads', copyPath: 'Copiar ruta', reveal: 'Mostrar en Finder', 
    openWindow: 'Abrir en otra ventana', rename: 'Renombrar…', archive: 'Archivar', previews: 'Previews', 
    noPreviews: 'No hay previews guardadas de este chat', primary: 'principal', name: 'Nombre', folders: 'Carpetas', none: 'Ninguna aún',
    cancel: 'Cancelar', create: 'Crear', creating: 'Creando…', save: 'Guardar', remove: 'Quitar', projectIn: 'Nuevo proyecto en {0}',
    projectHelp: 'Un proyecto agrupa una o varias carpetas. Cada carpeta puede tener sus propios worktrees.', projectName: 'p. ej. Rediseño web',
    worktreeIn: 'Nuevo worktree en {0}', worktreeHelp: 'Una copia aparte bajo .worktrees/ con su propia rama, para que los chats trabajen en paralelo.',
    branch: 'Rama (opcional)', startFrom: 'Partir de', defaultTag: '(por defecto)', worktreeReady: 'Worktree listo: {0}',
    removeWorktreeAsk: '¿Quitar el worktree?', removeWorktreeBody: 'Git se niega si tiene cambios sin confirmar. La rama se conserva.',
    renameChat: 'Renombrar chat', setup: 'Espacio de trabajo', envDoubleClick: 'Abrir los .env con doble clic', envDoubleClickHint: 'En el árbol de archivos se abren en tu editor del sistema; apagado deja el árbol como lo hace Hermes.', creditsBy: 'Hecho por', creditsPart: 'parte de', hideBotsTab: 'Ocultar la pestaña Bots',
    hideBotsTabHint: 'Squads la reemplaza: bots, proyectos y chats en una sola lista.', hideRail: 'Ocultar el selector de perfiles',
    hideRailHint: 'La franja de abajo que cambia toda la ventana de bot. Squads abre cada chat bajo su propio bot.',
    showOthers: 'Mostrar otros bots que tengan chats', showOthersHint: 'Bots que no son default, el builder ni un manager de squad.',
    sortRecent: 'Ordenar bots por actividad reciente', sortRecentHint: 'Apagado: default, builder y luego managers.', navRows: 'Filas de la barra lateral',
    visibleBots: 'Bots visibles', allVisible: 'Aquí está cada bot con el que puedes hablar; los workers de un squad nunca salen.',
    ctxFiles: 'Archivos', ctxReview: 'Revisión', ctxTerminal: 'Terminal', botCaps: 'Capacidades de {0}',
    cmdOpen: 'Squads: enfocar la lista', cmdNext: 'Squads: siguiente chat pendiente', cmdFloat: 'Squads: costados flotantes sí/no', cmdPinLeft: 'Squads: fijar u ocultar el costado izquierdo', cmdPinRight: 'Squads: fijar u ocultar el costado derecho', cmdLayout: 'Squads: elegir el layout Squads', nothingPending: 'Nada te está esperando', pendingTip: 'Chats trabajando o sin leer, de todos los bots', working: 'trabajando', unread: 'sin leer', alsoPending: 'También pendiente aquí', floatSides: 'Costados flotantes', floatSidesHint: 'La lista izquierda y los archivos/terminal de la derecha no ocupan ancho: acerca el puntero a un borde y se deslizan sobre el chat; al salir se ocultan. Los botones laterales de la barra de título los fijan.', layoutName: 'Layout Squads', layoutHint: 'Squads a la izquierda, el chat al centro, archivos sobre una terminal baja a la derecha.', layoutPick: 'Elige “Squads” en Layout.', openBrowser: 'Abrir el navegador', envFiles: 'Archivos .env…', appearance: 'Icono y color…', appearanceOf: 'Apariencia de {0}', appearanceHelp: 'Se ve aquí y en Sessions.', defaultIcon: 'Por defecto', defaultColor: 'Color del bot', envIn: 'Archivos .env en {0}', envHelp: 'Guardan secretos, así que Hermes no los abre en su visor; cada uno se abre en tu editor para ese archivo.', openInEditor: 'Abrir en el editor', noEnv: 'No hay archivo .env en esta carpeta.', envOpenFailed: 'No se pudo abrir. ¿Hay una app asignada a este tipo de archivo?', showMore: 'Mostrar {0} más', cmdTheme: 'Squads: usar el tema Squads', themeName: 'Tema Squads', themeHint: 'En todos los bots: inspirado en Catppuccin, de bajo contraste, crema de día y mocha de noche. Apagado, cada bot conserva el tema que le elijas.', themeUse: 'Usarlo', cmdNewProject: 'Squads: nuevo proyecto…', cmdPreview: 'Squads: reabrir una preview', pane: 'Squads', cmdTimeline: 'Squads: abrir la línea de tiempo', introNoProject: 'Chat fuera de un proyecto', chatWordmark: 'Nombre del squad en chats vacíos', chatWordmarkHint: 'Un chat vacío muestra su squad en letras grandes y, debajo, el proyecto, la carpeta y el worktree donde trabaja.', tlSkipped: '{0} tarjetas más antiguas no se dibujan; elige un periodo más corto.', out_spawn_failed: 'no arrancó', out_stale: 'quedó colgada', out_review_requested: 'enviada a revisión', out_changes_requested: 'pidieron cambios', out_scheduled: 'programada', iss_stranded_in_ready: 'Lista pero nadie la toma', iss_triage_aux_unavailable: 'El triage no pudo correr', bellClear: 'Limpiar todo', bellDismiss: 'Quitar de la campana', bellMore: '{0} más', close: 'Cerrar', noManager: 'No encontré un manager para este tablero', replyDraft: 'Sobre la tarjeta {0} ("{1}") del tablero {2}: ', cardOn: 'tablero {0} · {1}', cardNeedsYou: 'Lo que te pide', cardLatest: 'Última nota', cardStory: 'Historial', cardReply: 'Responder en un chat', cardDetail: 'Detalle', tlHint: 'Pasa el puntero por una barra para ver el detalle; haz clic para abrir la tarjeta.', tlStill: 'sigue así', st_queued: 'En cola', st_dep: 'Espera otra tarjeta', st_run: 'En progreso', st_block: 'Bloqueada', st_review: 'En revisión (QA)', st_done: 'Finalizada', st_fail: 'Falló', st_stop: 'Detenida', sth_queued: 'Espera que un bot la tome.', sth_dep: 'Arranca sola cuando termine la tarjeta de la que depende.', sth_run: 'Un bot está trabajando en ella ahora.', sth_block: 'Parada hasta que alguien responda: tú, cuando pide tu respuesta.', sth_review: 'Su bot la terminó; un revisor la valida antes de darla por finalizada.', sth_done: 'Terminada y aceptada.', sth_fail: 'Una ejecución se cayó, se pasó de tiempo o se rindió; la tarjeta reintenta o espera.', sth_stop: 'Una ejecución se retiró o pausó (límite de uso, reclamo manual).', ev_created: 'Creada', ev_promoted: 'Lista para empezar', ev_dependency_wait: 'Espera otra tarjeta', ev_claimed: 'Un bot la tomó', ev_blocked: 'Bloqueada', ev_unblocked: 'Desbloqueada', ev_review_requested: 'Enviada a revisión', ev_changes_requested: 'Pidieron cambios', ev_completed: 'Finalizada', ev_crashed: 'La ejecución se cayó', ev_timed_out: 'Se pasó de tiempo', ev_gave_up: 'Se rindió tras reintentos', ev_reclaimed: 'Retirada', ev_scheduled: 'Programada', ev_archived: 'Archivada', timeline: 'Línea de tiempo', timelineTitle: 'Línea de tiempo de los squads', timelineEmpty: 'Aún no hay tableros con trabajo', timelineEmptyHint: 'El tablero de un squad aparece aquí cuando su manager crea tarjetas.', timelineQuiet: 'Nada se ejecutó en este periodo.', issuesTitle: 'Qué salió mal', issuesNone: 'Nada que revisar en este periodo.', iss_repeated_failures: 'Fallos repetidos', iss_repeated_crashes: 'Caídas repetidas', iss_stuck_in_blocked: 'Bloqueada hace tiempo', iss_block_unblock_cycling: 'Se bloquea una y otra vez', iss_hallucinated_cards: 'Tarjetas inventadas', iss_prose_phantom_refs: 'Menciona tarjetas que no existen', iss_review_dependency_deadlock: 'Revisión trabada', iss_running_with_open_parents: 'Corrió antes que sus dependencias', iss_run_failed: 'Una ejecución falló', iss_slow_start: 'Tardó en empezar', iss_waiting_on_you: 'Te está esperando', out_completed: 'hecha', out_crashed: 'se cayó', out_timed_out: 'se pasó de tiempo', out_blocked: 'bloqueada', out_reclaimed: 'reclamada', out_rate_limited: 'límite de uso', out_gave_up: 'abandonada', out_running: 'en curso', boardTip: '{0}: {1} bloqueadas · {2} en revisión · {3} en curso. Clic para ver las tarjetas que te esperan; la línea de tiempo está al final.', pr_open: 'abierto', pr_draft: 'borrador', pr_merged: 'fusionado', pr_closed: 'cerrado', changedFiles: '{0} archivos cambiados', toPush: '{0} commits por subir', bell: 'Te esperan', bellHead: 'Te esperan', bellNone: 'Nada te está esperando', bellCount: '{0} te esperan', bellChat: '{0} te pregunta en su chat', notifyCard: '{0}: una tarjeta necesita tu respuesta', notifyMany: '{0} tarjetas necesitan tu respuesta', cardInvalid: 'Referencia de tarjeta no válida', cardMissing: 'No se encontró la tarjeta', cardFailed: '{0} ejecuciones fallidas', cardTimeline: 'Línea de tiempo', cardBoard: 'Tablero', notifyAway: 'Avisarme cuando un squad me necesite', notifyAwayHint: 'Una notificación del sistema (y una línea de la mascota, si hay una) cuando una tarjeta se bloquea esperando tu respuesta y Hermes está en segundo plano.'
  }
}
const fmt = (s, ...a) => String(s).replace(/\{(\d+)\}/g, (_, i) => a[i] ?? '')
const useT = () => {
  const t = usePluginI18n(ID)
  const tr = (k, ...a) => fmt(t(k), ...a)
  /** A key built from data (`out_<outcome>`, `iss_<kind>`): the fallback when no string exists for it. */
  tr.or = (k, fallback) => {
    const v = t(k)
    return v && v !== k ? v : fallback
  }
  return tr
}
const patchSession = (bot, id, body) =>
  window.hermesDesktop.api({ path: `/api/sessions/${encodeURIComponent(id)}`, method: 'PATCH', profile: bot.name, body: { ...body, profile: bot.name } })

// ───────────────────────────── state ─────────────────────────────
const DEFAULT_PREFS = { notifyAway: true, envDoubleClick: true, floatSides: true, squadsTheme: true, hidden: [], pinned: [], order: [], showOthers: true, sortRecent: false, hideBotsTab: false, hideRail: false, hiddenNav: ['kanban:nav'], prefsVersion: PREFS_VERSION }
let storage = null
let ctxRef = null
const prefsAtom = atom({ ...DEFAULT_PREFS })
const collapsedAtom = atom({})
/** The project the list is focused on (`{ bot, id }`), or null: a big project opens here instead of unfolding. */
const focusAtom = atom(null)
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
  const next = toggledCollapsed(collapsedAtom.get(), key, def)
  collapsedAtom.set(next)
  storage?.set('collapsed', next)
}
/** A row reads only its own slice of an atom: it re-renders when that slice changes, not on every write to the atom
 *  (opening one folder used to re-render every row of the list; a preview opened in one chat, every chat row). */
const subscribeCollapsed = cb => collapsedAtom.listen(cb)
const subscribePreviews = cb => previewsAtom.listen(cb)
const useOpen = (key, defaultOpen) => openState(useSyncExternalStore(subscribeCollapsed, () => collapsedAtom.get()[key]), defaultOpen)
const usePreviews = storedId => useSyncExternalStore(subscribePreviews, () => previewsFor(previewsAtom.get(), storedId))
const rememberPreviews = next => {
  if (next === previewsAtom.get()) return
  previewsAtom.set(next)
  storage?.set('previews', next)
}

/** Desktop flags a chat that finished while you were elsewhere in its own persisted marker (the backend learns
 *  about it later, if at all); this reads that same marker so the list agrees with the dots everywhere else. */
const UNREAD_DAYS = 3
/** Every id a chat answers to: its own and, after auto-compression, its lineage root (where Desktop keys its marker). */
const chatIds = c => [...new Set([c.id, c._lineage_root_id, ...(Array.isArray(c._lineage_ids) ? c._lineage_ids : [])].filter(Boolean))]
function readUnreadMarkers() {
  try {
    const raw = JSON.parse(localStorage.getItem('hermes.desktop.unreadFinishedSessions') || '{}')
    // Desktop paints a chat's dot from its OWN profile's bucket only; a stale copy of the id under another profile
    // (left there by a window that had that profile up) is not unread, and nothing would ever clear it
    const chats = queryClient.getQueryData(SNAPSHOT_KEY)?.chats || []
    const owners = new Map()
    const old = new Set()
    const now = Date.now() / 1000
    for (const c of chats) {
      // a compressed chat's marker sits under its lineage root
      for (const id of chatIds(c)) {
        if (!owners.has(id)) owners.set(id, new Set())
        owners.get(id).add(c.profile || 'default')
        // a chat untouched for days is not news: its old marker would keep it in every shortcut list
        const t = sessionTime(c)
        if (t > 0 && now - t > UNREAD_DAYS * 86400) old.add(id)
      }
    }
    return [...new Set(Object.entries(raw).flatMap(([p, ids]) => (Array.isArray(ids) ? ids : []).filter(id => typeof id === 'string' && !old.has(id) && (!owners.has(id) || owners.get(id).has(p)))))].sort()
  } catch {
    return []
  }
}
/** Stored ids of chats with a running turn: Desktop's own busy flags (runtime ids) joined to stored ids through the
 *  session.info events and the focused pair. A chat this window has not heard from stays unknown; its unread flag
 *  still comes from the backend. */
let liveKey = ''
function syncLive() {
  const focusedRuntime = host.state.focusedSessionId.get()
  const focusedStored = host.state.focusedStoredSessionId.get()
  bind(focusedRuntime, focusedStored, false)
  const ids = []
  for (const [runtime, busy] of Object.entries(host.state.busyBySession.get() || {})) {
    const stored = busy ? storedOf(runtime) : null
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

/** Desktop keeps one layout tree per interface mode (`.simple` suffix in Simple mode): read both. They are parsed again
 *  only when their stored text changed (the reveal poll reads them four times a second). */
const LAYOUT_KEYS = ['hermes.desktop.layoutTree.v2', 'hermes.desktop.layoutTree.v2.simple']
let layoutSig
let layoutRead = { trees: [], zones: {} }
function readLayouts() {
  const raws = LAYOUT_KEYS.map(k => localStorage.getItem(k))
  const sig = raws.join('\u0000')
  if (sig !== layoutSig) {
    layoutSig = sig
    const trees = raws.map(parseLayout).filter(Boolean)
    layoutRead = { trees, zones: zonesOfAll(trees) }
  }
  return layoutRead
}

function sideWrappers() {
  // The row the chat sits in, climbed from the workspace: a column-root layout (Terminal deck, Quad) keeps its
  // bottom rail and never has a top or bottom child mistaken for a side.
  const fromTree = readLayouts().trees.map(workspaceGroup).filter(Boolean).map(id => document.querySelector(`[data-tree-group="${cssEscape(id)}"]:not([data-pane-host])`)).find(Boolean)
  const ws = document.querySelector('[data-tree-tab="workspace"]')?.closest('[data-tree-group]') ||
    fromTree ||
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
    delete el.dataset.sqhSolo
    delete el.dataset.sqhFloatRoot
    el.style.removeProperty('--sqh-w')
  }
  if (!root) {
    floatState.left.groups = []
    floatState.right.groups = []
    for (const e of document.querySelectorAll('[data-sqh-edge]')) e.hidden = true
    return
  }
  root.dataset.sqhFloatRoot = ''
  main.dataset.sqhMain = ''
  // The sides leave the flow, so the chat must take their room. Alone in the row it takes all of it; beside another
  // column (a preview) both keep the widths Desktop holds for them, so a sash the user drags still decides the split.
  if (chatAlone([...root.children].filter(k => k !== left && k !== right && k !== main).map(k => k.getBoundingClientRect().width))) main.dataset.sqhSolo = ''
  else delete main.dataset.sqhSolo
  const rules = []
  for (const [side, el] of [['left', left], ['right', right]]) {
    const st = floatState[side]
    const groups = el ? [...el.querySelectorAll('[data-tree-group]')].map(g => g.getAttribute('data-tree-group')) : []
    if (!el || !groups.length) {
      st.groups = []
      const edge = document.querySelector(`[data-sqh-edge="${side}"]`)
      if (edge) edge.hidden = true
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
    // the edge strip only where this side floats hidden: never a dead band over a side that is shown or absent
    const edge = document.querySelector(`[data-sqh-edge="${side}"]`)
    if (edge) edge.hidden = show
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
/** A poll that does nothing while the window is hidden. */
const whileVisible = fn => () => {
  if (!document.hidden) fn()
}
function watchReveals() {
  if (!floatOff) return
  const zones = readLayouts().zones
  for (const side of ['left', 'right']) {
    const st = floatState[side]
    const sig = sideSignature(st.groups, zones)
    if (isReveal(sideSig[side], sig, st)) {
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
    // the band is measured from the layout's own outer edge, so a profile rail or a window inset never pushes it
    // outward, and a column between the chat and the side (a preview) never pulls it inward
    const main = document.querySelector('[data-sqh-float-root]')?.getBoundingClientRect()
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
  // a side that does not float keeps Desktop's own toggle: swallowing it would leave the button dead
  if (!side || !floatState[side].groups.length) return
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
  const folded = readLayouts().zones
  for (const side of ['left', 'right']) {
    if (floatState[side].groups.some(id => String(folded[id] || '').endsWith(':min'))) {
      ctxRef?.runAction?.(side === 'left' ? 'view.toggleSidebar' : 'view.toggleRightSidebar')
      delete sideSig[side] // an unfold is housekeeping, not a reveal
    }
  }
}

/** The side's own toggle: pin it while sides float, else fold it through Desktop's action. */
const pinSide = side => (prefsAtom.get().floatSides ? togglePin(side) : ctxRef?.runAction?.(side === 'left' ? 'view.toggleSidebar' : 'view.toggleRightSidebar'))

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
  // A preview (an Electron <webview>) swallows every pointer event over it, so a side whose screen edge it covers
  // never heard the pointer arrive. A thin strip on each edge, above the page, hears it instead.
  const catchers = ['left', 'right'].map(side => {
    const el = document.createElement('div')
    el.dataset.sqhEdge = side
    el.hidden = true
    el.addEventListener('pointerenter', () => {
      const st = floatState[side]
      if (st.groups.length && !st.open && !st.pinned && !floatTimers[side]) floatTimers[side] = setTimeout(() => setSide(side, true), FLOAT_SHOW_MS)
    })
    el.addEventListener('pointerleave', () => {
      // a pointer that only brushed the edge leaves before the side shows: nothing opens (a re-enter re-arms it)
      if (!floatState[side].open) {
        clearTimeout(floatTimers[side])
        floatTimers[side] = null
      }
    })
    document.body.append(el)
    return el
  })
  const timer = setInterval(whileVisible(paintFloat), 1200)
  const revealTimer = setInterval(whileVisible(watchReveals), 250)
  document.addEventListener('pointermove', onFloatPointer, { passive: true })
  document.addEventListener('keydown', onKey)
  document.addEventListener('focusin', onFloatFocus)
  for (const type of ['click', 'dblclick', 'pointerdown', 'mousedown']) document.addEventListener(type, onToggleClick, true)
  window.addEventListener('keydown', onToggleKey, true)
  const unfoldTimer = setTimeout(unfoldSides, 400)
  floatOff = () => {
    clearTimeout(unfoldTimer)
    for (const el of catchers) el.remove()
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
    for (const k of Object.keys(floatNear)) delete floatNear[k]
    floatCss = ''
    for (const el of document.querySelectorAll('[data-sqh-main], [data-sqh-float-root]')) {
      delete el.dataset.sqhSolo
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
let pickRevealTimer = null
/** Picking the Squads layout opens files and the terminal once. Desktop's apply left the files zone closed when the
 *  pane had been closed before (seen live), so the pick says what it places. */
function watchLayoutPick() {
  const root = document.querySelector('[data-tree-split]')?.getAttribute('data-tree-split') || ''
  if (root === lastRoot) return
  const picked = root === SQUADS_LAYOUT.id && lastRoot !== ''
  lastRoot = root
  if (!picked) return
  host.revealPane('files')
  clearTimeout(pickRevealTimer)
  pickRevealTimer = setTimeout(() => host.revealPane('terminal'), 250)
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
/** Session events move the chat list and the worktrees only; boards, PR chips, cards and the timeline keep their own
 *  slower timers (a `gh pr list` per folder on every kanban heartbeat would burn GitHub's rate limit). */
const refresh = () => {
  for (const key of [SNAPSHOT_KEY, ['squad-hub', 'worktrees']]) queryClient.invalidateQueries({ queryKey: key }, { cancelRefetch: false })
}
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
        out[path] = await withTimeout(g.worktreeList(path), ms)
      } catch {
        /* not a git folder, or too slow */
      }
    })
  )
  return out
}

// ───────────────────────────── squads at work (data) ─────────────────────────────
/** Kanban reads go through the app's own REST bridge to the bundled kanban backend (same API the Kanban page uses);
 *  every call is a GET. */
const kanban = (path, timeoutMs = 8000) => withTimeout(window.hermesDesktop.api({ path: '/api/plugins/kanban' + path }), timeoutMs)
const BOARDS_KEY = ['squad-hub', 'boards']

/** Every board with the bots that take its cards and its digest; one request per board, shared by every surface. */
async function loadBoards() {
  const { boards = [] } = await kanban('/boards')
  const live = boards.filter(b => !b.archived && (b.total || 0) > 0)
  const out = await Promise.all(
    live.map(async b => {
      try {
        const board = await kanban('/board?board=' + encodeURIComponent(b.slug))
        return { slug: b.slug, name: b.name || b.slug, icon: b.icon || '', color: b.color || '', assignees: taskAssignees(board), digest: boardDigest(board), board }
      } catch {
        return null
      }
    })
  )
  return keepLastBoards(out, live.map(b => b.slug), queryClient.getQueryData(BOARDS_KEY))
}
const boardsQuery = () => ({ queryKey: BOARDS_KEY, queryFn: loadBoards, staleTime: 15000, refetchInterval: 30000, retry: false })

/** Desktop's own Kanban page is a plugin that ships off; a link to it is offered only when it is on. */
const kanbanOn = () => {
  try {
    return host.pluginDecisions?.get?.()?.kanban === true
  } catch {
    return false
  }
}
/** React side: re-renders when the Kanban plugin is switched on or off. */
const useKanbanOn = () => {
  const d = useValue(host.pluginDecisions || atom({}))
  return d?.kanban === true
}
/** Bots this window has chats open or running for (their backends are up). */
function openChatBots(snap) {
  const ids = new Set([host.state.focusedStoredSessionId.get(), ...liveAtom.get()].filter(Boolean)) // live backends only: never wake one
  return [...new Set((snap?.chats || []).filter(c => ids.has(c.id)).map(c => c.profile).filter(Boolean))]
}
function useBotBoard(bot) {
  const { data } = useQuery(boardsQuery())
  return useMemo(() => (data ? boardForBot(bot.name, data) : null), [data, bot.name])
}

const LIVE_KEY = ['squad-hub', 'active']
/** Live sessions: a chat parked on an approval or a question reads `waiting`. Waiting chats live in each bot's own backend. One `session.active_list` per backend that is already up (a sleeping
 *  bot has nothing waiting and is never woken for this): the primary, plus every bot with a chat open in this window. */
async function loadActive() {
  const bots = ['', ...openChatBots(queryClient.getQueryData(SNAPSHOT_KEY))]
  const lists = await Promise.all(
    bots.map(bot =>
      (bot && host.requestProfile ? host.requestProfile(bot, 'session.active_list', {}, 6000, { spawnPriority: 'background' }) : rpc('session.active_list', {}))
        .then(r => r.sessions || [])
        .catch(() => [])
    )
  )
  return mergeActive(lists)
}
const activeQuery = () => ({ queryKey: LIVE_KEY, queryFn: loadActive, staleTime: 4000, refetchInterval: 8000, retry: false })

/** Worktree chips: one `prList` per repo (GitHub, read-only) and one `repoStatus` per lane, refreshed every minute. */
async function loadLaneStatus(repo, lanes) {
  const g = git()
  const out = {}
  if (!g) return out
  const branches = [...new Set(lanes.map(l => l.branch).filter(b => b && b !== 'main' && b !== 'master'))]
  let prs = []
  try {
    prs = branches.length && g.review?.prList ? (await g.review.prList(repo, branches)).prs || [] : []
  } catch {
    prs = []
  }
  await Promise.all(
    lanes.map(async l => {
      let st = null
      try {
        st = g.repoStatus ? await g.repoStatus(l.path) : null
      } catch {
        st = null
      }
      out[l.key] = laneStatus(prs.find(p => p.branch === l.branch) || null, st)
    })
  )
  return out
}

// ───────────────────────────── actions ─────────────────────────────
async function openChat(bot, id, intent = 'tab') {
  try {
    await host.openSession(id, { profile: bot, intent })
    markRead(bot, id).then(refreshSoon)
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
    bind(created.session_id, created.stored_session_id, true)
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
    return created.stored_session_id
  } catch (e) {
    host.notifyError(e, 'Could not start the chat')
    return null
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

/** runtime id -> { stored, sure } (see bindRuntime). Runtime ids outlive the plugin being switched off and on, so this
 *  survives it. */
const runtimeToStored = new Map()
const storedOf = runtime => runtimeToStored.get(runtime)?.stored || null
const bind = (runtime, stored, sure) => bindRuntime(runtimeToStored, runtime, stored, sure)

/** Previews are remembered per chat: a closed preview is one click to reopen, no prompt to the bot. The plugin never
 *  reopens one by itself: Desktop keeps a chat's tabs in the rail of the profile on screen when they were opened, so
 *  a chat entered again can find its tab in a rail that is not in view, and a synthetic `preview.open` from here
 *  would land in the rail that is, one more duplicate tab on every visit. */
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

/** The newest preview remembered for the chat in view, reopened; a notice when there is none. */
function reopenLastPreview() {
  const { id } = focusedChat()
  const last = previewsFor(previewsAtom.get(), id)[0]
  if (last) reopenPreview(last)
  else host.notify({ kind: 'info', message: fmt(lang().noPreviews) })
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
  const previews = usePreviews(session.id)
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

function LaneBlock({ bot, folder, lane, depth, activeId, ctl, query, status }) {
  const t = useT()
  const key = `lane:${bot.name}:${lane.key}`
  const stored = useOpen(key, true)
  const open = query.trim() ? true : stored
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
      status ? jsx(LaneChip, { status }) : null,
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
  const active = needsYou(activeIn(folder, attention))
  const wide = folderOpensByDefault(folder, attention)
  const stored = useOpen(key, wide)
  const open = query.trim() ? true : stored
  const chats = folder.lanes.reduce((n, l) => n + l.sessions.length, 0)
  const { data: laneStats } = useQuery({
    queryKey: ['squad-hub', 'lanes', folder.path, folder.lanes.map(l => l.key + '@' + l.branch).join('|')],
    queryFn: () => loadLaneStatus(folder.path, folder.lanes),
    enabled: open && Boolean(folder.repo) && Boolean(git()),
    staleTime: 60000,
    refetchInterval: 120000,
    retry: false
  })
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
    open ? folder.lanes.map(l => h(LaneBlock, { key: l.key, bot, folder, lane: l, depth: 3, activeId, ctl, query, status: laneStats?.[l.key] })) : null
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

function ProjectBlock({ bot, project, activeId, ctl, query, focused = false }) {
  const t = useT()
  const key = `proj:${bot.name}:${project.id}`
  const attention = useAttention(activeId)
  const multi = project.folders.length > 1
  const wide = projectOpensWide(project)
  const stored = useOpen(key, wide)
  // A big project never unfolds in the list: its row opens it in its own view (focused), with a way back
  const big = !focused && !query.trim() && projectOpensInFocus(project)
  const open = focused || (query.trim() ? true : big ? false : stored)
  const primary = project.folders.find(f => f.primary) || project.folders[0]
  // One folder holding only its main checkout: the chats hang straight under the project, no "main" row.
  const flat = project.folders.length === 1 && project.folders[0].lanes.length === 1 && project.folders[0].lanes[0].main ? project.folders[0].lanes[0] : null
  // A project with several folders lists what needs you right under it, each chat with where it lives; its folders
  // start folded (those chats are already one click away) and a folded folder still wears their dot.
  const digest = query.trim() || focused ? [] : projectDigest(project, attention, open)
  return h(
    'div',
    {},
    focused
      ? null
      : h(
      Row,
      { depth: 1, className: 'sqh-proj', onClick: () => (big ? focusAtom.set({ bot: bot.name, id: project.id }) : toggleCollapsed(key, !wide)) },
      big ? h('span', { className: 'sqh-enter', title: t('openProject') }, jsx(Codicon, { name: 'chevron-right', size: '0.75rem' })) : jsx(DisclosureCaret, { open }),
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
            { label: t('cleanMenu'), run: () => ctl.cleanup(bot, project) },
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
  const prefs = useValue(prefsAtom)
  const stored = useOpen(key, true)
  const open = query.trim() ? true : stored
  const [looseToggled, setLoose] = useState(null)
  const [looseLimit, setLooseLimit] = useState(30)
  const [olderOpen, setOlder] = useState(false)
  const looseOpen = query.trim() ? true : looseToggled === null ? false : looseToggled
  const pinned = prefs.pinned.includes(bot.name)
  const attention = useAttention(activeId)
  const digest = open ? [] : botDigest(tree, attention)
  // a bot with no project lists its loose chats: what needs you and the newest few, the rest under "older chats"
  const split = query.trim() ? { shown: tree.loose, rest: [] } : looseSplit(tree.loose, attention)
  const older = olderOpen ? split.rest.slice(0, looseLimit) : []
  return h(
    'div',
    {},
    h(
      Row,
      { depth: 0, className: 'sqh-bot', onClick: () => toggleCollapsed(key, false) },
      jsx(DisclosureCaret, { open }),
      jsx(IconTile, { icon: iconFor(bot, prefs.icons || {}) }),
      h('span', { className: 'sqh-label' }, bot.title),
      bot.role === 'manager' ? jsx(BoardChip, { bot }) : null,
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
            kanbanOn() ? { label: t('kanban'), run: () => openBotPage(bot.name, '/kanban') } : null,
            bot.role === 'manager' ? { label: t('timeline'), run: () => openTimeline(boardForBot(bot.name, queryClient.getQueryData(BOARDS_KEY) || [])?.slug || '') } : null,
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
      ? [
          ...split.shown.map(sx => h(ChatRow, { key: sx.id, bot, session: sx, depth: 1, activeId, ctl })),
          split.rest.length
            ? h(Row, { key: 'older', depth: 1, className: 'sqh-lane', onClick: () => setOlder(!olderOpen) }, jsx(DisclosureCaret, { open: olderOpen }), jsx(Codicon, { name: 'history', size: '0.8125rem' }), h('span', { className: 'sqh-label' }, t('olderChats')), h('span', { className: 'sqh-age' }, split.rest.length))
            : null,
          ...older.map(sx => h(ChatRow, { key: sx.id, bot, session: sx, depth: 2, activeId, ctl })),
          olderOpen && split.rest.length > looseLimit
            ? h('div', { key: 'more', className: 'sqh-empty' }, h('a', { href: '#', onClick: e => { e.preventDefault(); setLooseLimit(looseLimit + 30) }, style: { color: 'var(--ui-accent)' } }, t('showMore', split.rest.length - looseLimit)))
            : null
        ]
      : null,
    open && tree.loose.length && tree.projects.length
      ? [
          h(Row, { key: 'loose', depth: 1, className: 'sqh-lane', onClick: () => setLoose(!looseOpen) }, jsx(DisclosureCaret, { open: looseOpen }), jsx(Codicon, { name: 'comment-discussion', size: '0.8125rem' }), h('span', { className: 'sqh-label' }, t('outside')), h('span', { className: 'sqh-age' }, tree.loose.length)),
          looseOpen ? tree.loose.slice(0, looseLimit).map(sx => h(ChatRow, { key: sx.id, bot, session: sx, depth: 2, activeId, ctl })) : null
        ]
      : null,
    open && looseOpen && tree.projects.length && tree.loose.length > looseLimit
      ? h('div', { className: 'sqh-empty' }, h('a', { href: '#', onClick: e => { e.preventDefault(); setLooseLimit(looseLimit + 30) }, style: { color: 'var(--ui-accent)' } }, t('showMore', tree.loose.length - looseLimit)))
      : null
  )
}

/** A squad that has no manager yet: its bots sit under the squad's Desktop section. */
function GroupBlock({ section, members, activeId, ctl, query }) {
  const key = 'group:' + section
  const prefs = useValue(prefsAtom)
  const stored = useOpen(key, true)
  const open = query.trim() ? true : stored
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
  const { data: snap } = useQuery(snapshotQuery())
  const [target, setTarget] = useState('')
  useEffect(() => setTarget(state?.bot?.name || ''), [state?.bot?.name])
  const members = useMemo(() => (state && snap ? squadMembers(snap.profiles, state.bot.name) : []), [snap, state?.bot?.name])
  if (!state) return null
  const shown = target || state.bot.name
  const title = members.find(m => m.name === shown)?.title || state.bot.title
  return jsx(Dialog, {
    open: true,
    onOpenChange: o => !o && close(),
    children: jsxs(DialogContent, {
      className: 'sqh-caps',
      children: [
        jsx(DialogHeader, { children: jsx(DialogTitle, { children: t('botCaps', title) }) }),
        members.length
          ? h('div', { className: 'sqh-squadpick' }, h('span', { className: 'sqh-hint' }, t('squadBots')), h('div', { className: 'sqh-tl-boards' }, members.map(m => h('button', { key: m.name, type: 'button', 'data-on': m.name === shown ? 'true' : 'false', onClick: () => setTarget(m.name) }, m.title))))
          : null,
        jsx(CapabilitiesView, { key: shown, embedded: true, fixedProfile: shown })
      ]
    })
  })
}

/** Clean up a project: archive its idle chats and remove the worktrees with nothing to lose, each ticked by what is
 *  safe and all listed before anything happens. Nothing is deleted: chats are archived, a branch is kept. */
function CleanDialog({ state, close }) {
  const t = useT()
  const [picked, setPicked] = useState(null)
  const [busy, setBusy] = useState(false)
  const q = useQuery({
    queryKey: ['squad-hub', 'cleanup', state?.bot?.name, state?.project?.id],
    enabled: Boolean(state),
    gcTime: 0,
    retry: false,
    queryFn: async () => {
      const out = {}
      for (const f of state.project.folders) if (f.repo && git()) Object.assign(out, await loadLaneStatus(f.path, f.lanes))
      return out
    }
  })
  const plan = useMemo(() => (state && q.data ? cleanupPlan(state.project, q.data, attentionNow(), Date.now() / 1000) : null), [state, q.data])
  useEffect(() => {
    if (plan) setPicked(new Set([...plan.worktrees.filter(w => w.pre).map(w => 'wt:' + w.key), ...plan.chats.filter(c => c.pre).map(c => 'chat:' + c.session.id)]))
  }, [plan])
  if (!state) return null
  const toggle = key => setPicked(prev => { const n = new Set(prev); n.has(key) ? n.delete(key) : n.add(key); return n })
  const count = picked?.size || 0
  const run = async () => {
    setBusy(true)
    let done = 0
    let failed = 0
    let why = ''
    const fail = (name, e) => { failed++; why = why || `${name}: ${String(e?.message || e).replace(/^Error:\s*/, '').slice(0, 160)}` }
    for (const c of plan.chats) {
      if (!picked.has('chat:' + c.session.id)) continue
      try { await patchSession(state.bot, c.session.id, { archived: true }); done++ } catch (e) { fail(c.session.title || c.session.id, e) }
    }
    for (const w of plan.worktrees) {
      if (!picked.has('wt:' + w.key)) continue
      try { await git().worktreeRemove(w.folderPath, w.path); done++ } catch (e) { fail(w.label, e) }
    }
    setBusy(false)
    await refresh()
    host.notify({ kind: failed ? 'warning' : 'success', message: fmt(lang().cleanDone, done) + (failed ? ' ' + fmt(lang().cleanFailed, failed) + ' ' + why : '') })
    close()
  }
  const row = (key, main, sub, age) => h('label', { key, className: 'sqh-cleanrow' }, h('input', { type: 'checkbox', checked: picked?.has(key) || false, onChange: () => toggle(key) }), h('span', { className: 'sqh-cleanmain' }, h('span', { className: 'sqh-belltitle' }, main), sub ? h('span', { className: 'sqh-hint' }, sub) : null), age ? h('span', { className: 'sqh-bellage' }, age) : null)
  const empty = plan && !plan.chats.length && !plan.worktrees.length
  return jsx(Dialog, {
    open: true,
    onOpenChange: o => !o && close(),
    children: jsxs(DialogContent, {
      className: 'sqh-clean',
      children: [
        jsxs(DialogHeader, { children: [jsx(DialogTitle, { children: t('cleanTitle', state.project.name) }), jsx(DialogDescription, { children: t('cleanHelp') })] }),
        !plan ? h('div', { className: 'sqh-hint' }, t('loading')) : null,
        empty ? h('div', { className: 'sqh-hint' }, t('cleanNothing')) : null,
        plan && plan.worktrees.length ? h('div', { className: 'sqh-cleansec' }, h('div', { className: 'sqh-cd-sub' }, t('cleanWorktrees')), plan.worktrees.map(w => row('wt:' + w.key, w.label, [w.folder, w.branch, t('cleanWhy_' + w.reason)].filter(Boolean).join(' · ')))) : null,
        plan && plan.chats.length ? h('div', { className: 'sqh-cleansec' }, h('div', { className: 'sqh-cd-sub' }, t('cleanChats')), plan.chats.slice(0, 80).map(c => row('chat:' + c.session.id, c.session.title || c.session.preview || 'Chat', [c.folder, c.lane].filter(Boolean).join(' · '), shortAge(sessionTime(c.session))))) : null,
        plan && plan.chats.length > 80 ? h('div', { className: 'sqh-hint' }, t('cleanMore', plan.chats.length - 80)) : null,
        h('div', { className: 'sqh-hint' }, t('cleanKeeps')),
        jsxs(DialogFooter, { children: [jsx(Button, { variant: 'ghost', onClick: close, children: t('cancel') }), jsx(Button, { disabled: busy || !count, onClick: run, children: busy ? t('cleaning') : t('cleanGo', count) })] })
      ]
    })
  })
}

// ───────────────────────────── the pane ─────────────────────────────
/** Every dialog the list can open; the one named by `dialog.kind` gets its state, the others stay shut. */
function Dialogs({ dialog, close }) {
  const on = kind => (dialog?.kind === kind ? dialog : null)
  return h(
    React_Fragment,
    {},
    jsx(ProjectDialog, { state: on('project'), close }),
    jsx(WorktreeDialog, { state: on('worktree'), close }),
    jsx(TextDialog, { state: on('text'), close }),
    jsx(ConfirmBox, { state: on('confirm'), close }),
    jsx(CapsDialog, { state: on('caps'), close }),
    jsx(CleanDialog, { state: on('clean'), close }),
    jsx(LookDialog, { state: on('look'), close }),
    jsx(EnvDialog, { state: on('env'), close })
  )
}

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
      cleanup: (bot, project) => setDialog({ kind: 'clean', bot, project }),
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
    if (!q.data) return { main: [], groups: [], other: [] }
    let all = treesOf(q.data, wt.data, prefs)
    if (prefs.sortRecent) all = [...all].sort((a, b) => botLast(b) - botLast(a)) // the list is shared: sort a copy
    all = all.map(tr => filterTree(tr, query)).filter(Boolean)
    const groups = new Map()
    for (const x of all.filter(x => x.bot.group)) groups.set(x.bot.group, [...(groups.get(x.bot.group) || []), x])
    return {
      main: all.filter(x => !x.bot.other),
      groups: [...groups.entries()],
      other: prefs.showOthers ? all.filter(x => x.bot.other && !x.bot.group) : []
    }
  }, [q.data, wt.data, query, prefs])

  // A big project opened from its row fills the list, with a way back; it closes on its own when it disappears
  const focus = useValue(focusAtom)
  const focusTree = focus ? [...trees.main, ...trees.groups.flatMap(([, m]) => m), ...trees.other].find(tr => tr.bot.name === focus.bot) : null
  const focusProject = focusTree?.projects.find(p => p.id === focus.id) || null
  useEffect(() => {
    if (focus && q.data && !query.trim() && !focusProject) focusAtom.set(null)
  }, [focus, focusProject, q.data, query])
  if (focus && focusProject && !query.trim()) {
    const prefsIcons = prefs.icons || {}
    return h(
      'div',
      { className: 'sqh' },
      h(
        'div',
        { className: 'sqh-focushead' },
        h('button', { type: 'button', className: 'sqh-back', onClick: () => focusAtom.set(null), title: t('back') }, jsx(Codicon, { name: 'arrow-left', size: '0.8125rem' }), h('span', {}, focusTree.bot.title)),
        h('div', { className: 'sqh-focustitle' }, jsx(IconTile, { icon: iconFor(focusTree.bot, prefsIcons), size: 16 }), jsx(ProjectMark, { project: focusProject, bot: focusTree.bot }), h('span', { className: 'sqh-label' }, focusProject.name), h('span', { className: 'sqh-count' }, t('foldersN', focusProject.folders.length)), jsx(IconBtn, { icon: 'clear-all', label: t('cleanMenu'), onClick: () => ctl.cleanup(focusTree.bot, focusProject) }))
      ),
      h('div', { className: 'sqh-scroll' }, h(ProjectBlock, { bot: focusTree.bot, project: focusProject, activeId, ctl, query, focused: true })),
      jsx(Dialogs, { dialog, close: () => setDialog(null) })
    )
  }

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
    jsx(Dialogs, { dialog, close: () => setDialog(null) })
  )
}

/** The composer's own folder reference, fenced like its picker writes it, so a path with spaces stays one chip. */
const folderRef = path => '@folder:' + (!path.includes('`') ? '`' + path + '`' : !path.includes('"') ? '"' + path + '"' : "'" + path + "'")

const latestWorktrees = () =>
  queryClient.getQueriesData({ queryKey: ['squad-hub', 'worktrees'] })
    .map(([key, data]) => ({ data, at: queryClient.getQueryState(key)?.dataUpdatedAt || 0 }))
    .sort((a, b) => b.at - a.at)[0]?.data || {}

/** `@` in the composer offers the folders and worktrees of the project the focused chat works in, so a path can be
 *  handed to the bot exactly. Synchronous by contract: it reads the cached snapshot. */
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

/** Every visible bot's tree. The list, the status bar counter, each empty chat's intro and the shortcuts all need the
 *  same trees from the same snapshot, so the last build is kept: callers get the same array until the snapshot, the
 *  worktrees or the prefs change. Treat it as read-only. */
const NO_TREES = []
const NO_WORKTREES = {}
let treesMemo = null
function treesOf(snap, worktrees, prefs) {
  if (!snap) return NO_TREES
  const wts = worktrees || NO_WORKTREES
  if (treesMemo && treesMemo.snap === snap && treesMemo.wts === wts && treesMemo.prefs === prefs) return treesMemo.out
  const out = botsOf(snap, prefs).map(bot => buildBotTree(bot, snap.projectsBy[bot.name] || [], snap.chats.filter(c => c.profile === bot.name), wts))
  treesMemo = { snap, wts, prefs, out }
  return out
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
/** The plugin's strings in the app's own language (Settings > Language), for code outside React. */
const lang = () => {
  const tr = ctxRef?.i18n?.t
  if (typeof tr !== 'function') return MESSAGES.en
  const out = {}
  for (const k of Object.keys(MESSAGES.en)) {
    const v = tr(k)
    out[k] = v && v !== k ? v : MESSAGES.en[k]
  }
  return out
}

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

// ───────────────────────────── squads at work (UI) ─────────────────────────────
const PR_ICON = { draft: 'git-pull-request-draft', open: 'git-pull-request', merged: 'git-merge', closed: 'git-pull-request' }

/** A worktree's PR and local changes, quiet: nothing when there is nothing to say. */
function LaneChip({ status }) {
  const t = useT()
  const { pr, changed, ahead } = status
  if (!pr && !changed && !ahead) return null
  return h(
    'span',
    { className: 'sqh-lanechip', onClick: stop, onPointerDown: stop },
    pr
      ? h('button', { type: 'button', className: 'sqh-pr', 'data-state': pr.state, title: `#${pr.number} ${pr.title} · ${t.or('pr_' + pr.state, pr.state)}`, onClick: () => pr.url && ctxRef?.os?.openExternal?.(pr.url) }, jsx(Glyph, { name: PR_ICON[pr.state] || 'git-pull-request', size: 11 }), '#', pr.number)
      : null,
    changed ? h('span', { className: 'sqh-dirty', title: t('changedFiles', changed) }, '±', changed) : null,
    ahead ? h('span', { className: 'sqh-dirty', title: t('toPush', ahead) }, '↑', ahead) : null
  )
}

/** A squad's board on its manager's row, in words: the cards waiting on your answer ("8 waiting on you"), else
 *  what is running. A click lists those cards; each opens with the question it asks and a button to answer. */
function BoardChip({ bot }) {
  const t = useT()
  const b = useBotBoard(bot)
  const dismissed = useValue(bellDismissedAtom)
  if (!b) return null
  const { blocked, review, running } = b.digest
  // cleared from the bell = seen: the count goes quiet, but the cards stay listed here until they are answered
  const waiting = boardWaiting(b, {})
  const fresh = boardWaiting(b, dismissed).length
  const label = fresh ? t('chipWaiting', fresh) : waiting.length ? t('chipBlocked', waiting.length) : running ? t('chipRunning', running) : review ? t('chipReview', review) : ''
  if (!label) return null
  const tone = fresh ? 'blocked' : waiting.length ? 'seen' : running ? 'running' : 'review'
  const now = Date.now() / 1000
  return jsxs(DropdownMenu, {
    children: [
      jsx(DropdownMenuTrigger, {
        asChild: true,
        children: h(
          'button',
          { type: 'button', className: 'sqh-boardchip', 'data-tone': tone, title: t('boardTip', b.name, blocked, review, running), onClick: stop, onPointerDown: stop },
          h('span', { className: 'sqh-bc-' + tone }, h('i', {}), label)
        )
      }),
      jsx(DropdownMenuContent, {
        align: 'end',
        className: 'sqh-bellmenu',
        children: [
          h('div', { key: 'h', className: 'sqh-bellhead' }, h('span', {}, waiting.length ? t('chipHead', b.name) : b.name)),
          ...waiting.slice(0, 10).map(x =>
            jsx(DropdownMenuItem, {
              onSelect: () => openCard(x.board, x.taskId),
              children: h('span', { className: 'sqh-bellrow' }, jsx(Glyph, { name: 'clock', size: 13 }), h('span', { className: 'sqh-bellmain' }, h('span', { className: 'sqh-belltitle' }, String(x.title).slice(0, 70)), h('span', { className: 'sqh-hint' }, x.profile || '')), x.at ? h('span', { className: 'sqh-bellage' }, shortAge(x.at, now)) : null)
            }, x.key)
          ),
          waiting.length > 10 ? h('div', { key: 'more', className: 'sqh-bellhead' }, t('bellMore', waiting.length - 10)) : null,
          jsx(DropdownMenuSeparator, {}, 'sep'),
          jsx(DropdownMenuItem, { onSelect: () => openTimeline(b.slug), children: t('chipTimeline') }, 'tl')
        ].filter(Boolean)
      })
    ]
  })
}

// ── the bell: approvals, questions and blocked cards across every bot ──
const bellSeenAtom = atom([])
/** Dismissed occurrences (`key@stamp` → when), persisted: a card blocked again comes back on its own. */
const bellDismissedAtom = atom({})
function dismissBell(items) {
  const next = { ...bellDismissedAtom.get() }
  const now = Math.floor(Date.now() / 1000)
  for (const x of items) next[dismissKey(x)] = now
  // forget dismissals older than 30 days: their cards moved on long ago
  for (const [k, at] of Object.entries(next)) if (now - at > 30 * 86400) delete next[k]
  saveDismissed(next)
}
const saveDismissed = next => {
  bellDismissedAtom.set(next)
  storage?.set('bellDismissed', next)
}
function useBell() {
  const { data: active } = useQuery(activeQuery())
  const { data: boards } = useQuery(boardsQuery())
  const { data: snap } = useQuery(snapshotQuery())
  const dismissed = useValue(bellDismissedAtom)
  const all = useMemo(() => bellItems(active || [], snap?.chats || [], boards || []), [active, boards, snap])
  /** `ready`: the boards answered once, so a card missing from the list is known absent, not merely unloaded. */
  return useMemo(() => Object.assign(bellVisible(all, dismissed), { ready: boards !== undefined, all }), [all, dismissed, boards])
}

const boardName = slug => (queryClient.getQueryData(BOARDS_KEY) || []).find(b => b.slug === slug)?.name || slug

/** The Squads theme on every bot: Desktop keeps a theme per profile, so a bot never themed (or one that reverts on a
 *  profile switch) is given it again while the setting is on. Off, every bot keeps the theme picked for it. */
function ThemeKeeper() {
  const prefs = useValue(prefsAtom)
  const profile = useValue(host.state.profile)
  const theme = useTheme?.()
  useEffect(() => {
    if (prefs.squadsTheme === false || !theme || theme.themeName === 'squads') return
    requestTheme?.('squads')
  }, [prefs.squadsTheme, profile, theme?.themeName])
  return null
}

/** A click on a bell row is an answer in progress: the row leaves the count, and the place to answer opens. */
function openBellItem(item) {
  dismissBell([item])
  if (item.type === 'chat') {
    const bot = item.profile || host.state.profile.get()
    openChat(bot, item.storedId)
  } else openCard(item.board, item.taskId)
}

function Bell() {
  const t = useT()
  const items = useBell()
  const seen = useValue(bellSeenAtom)
  const fresh = newSince(seen, items).length
  const now = Date.now() / 1000
  return jsxs(DropdownMenu, {
    onOpenChange: open => open && bellSeenAtom.set(items.map(x => x.key)),
    children: [
      jsx(DropdownMenuTrigger, {
        asChild: true,
        children: h(
          'button',
          { type: 'button', className: 'sqh-bell', 'data-on': items.length ? 'true' : 'false', 'aria-label': t('bell'), title: items.length ? t('bellCount', items.length) : t('bellNone') },
          jsx(Glyph, { name: 'bell', size: 14 }),
          items.length ? h('span', { className: 'sqh-bell-n', 'data-fresh': fresh ? 'true' : 'false' }, items.length) : null
        )
      }),
      jsx(DropdownMenuContent, {
        align: 'end',
        className: 'sqh-bellmenu',
        children: items.length
          ? [
              h('div', { key: 'h', className: 'sqh-bellhead' }, h('span', {}, t('bellHead')), h('button', { type: 'button', className: 'sqh-bellclear', onClick: () => dismissBell(items) }, t('bellClear'))),
              ...bellGroups(items).flatMap(g => [
                h(
                  'div',
                  { key: g.key, className: 'sqh-bellgroup' },
                  h('span', {}, g.board ? boardName(g.board) : t('bellChats')),
                  h('span', { className: 'sqh-bellgroup-n' }, g.items.length),
                  g.board ? h('button', { type: 'button', className: 'sqh-bellclear', onClick: () => dismissBell(g.items) }, t('bellClearGroup')) : null
                ),
                ...g.items.slice(0, 6).map(x =>
                  jsx(
                    DropdownMenuItem,
                    {
                      onSelect: () => openBellItem(x),
                      children: h(
                        'span',
                        { className: 'sqh-bellrow' },
                        jsx(Glyph, { name: x.type === 'chat' ? 'circle-alert' : 'clock', size: 13 }),
                        h('span', { className: 'sqh-bellmain' }, h('span', { className: 'sqh-belltitle' }, String(x.title).slice(0, 60)), h('span', { className: 'sqh-hint' }, x.type === 'chat' ? t('bellChat', x.profile || '') : x.profile || '')),
                        x.at ? h('span', { className: 'sqh-bellage' }, shortAge(x.at, now)) : null
                      )
                    },
                    x.key
                  )
                ),
                g.items.length > 6 ? h('div', { key: g.key + ':more', className: 'sqh-bellhead' }, t('bellMore', g.items.length - 6)) : null
              ])
            ].filter(Boolean)
          : h('div', { className: 'sqh-bellhead' }, t('bellNone'))
      })
    ]
  })
}

/** A native notice for each new thing that needs you, only while Hermes is in the background (Desktop's own
 *  notifications already cover a chat you are looking at). The pet says it too when one is out. */
let bellKnown = null
function watchBell(items, ready = true) {
  if (!ready) return // before the boards load, every blocked card would look new
  const fresh = bellFresh(bellKnown, items)
  bellKnown = new Set(items.map(x => x.key))
  if (!fresh.length || !prefsAtom.get().notifyAway) return
  if (document.hasFocus()) return // the bell's count already says it; a notice is for when Hermes is behind
  const m = lang()
  const first = fresh[0]
  const name = (queryClient.getQueryData(BOARDS_KEY) || []).find(b => b.slug === first.board)?.name || first.board
  const title = fresh.length > 1 ? fmt(m.notifyMany, fresh.length) : fmt(m.notifyCard, name)
  ctxRef?.os?.notify?.({ title, body: String(first.title).slice(0, 120), onActivate: () => openBellItem(first) })
  try {
    if (ctxRef?.pet?.visible?.get?.()) ctxRef.pet.say(title, { id: 'bell', tone: 'wait', ttlMs: 12000 })
  } catch {
    /* no pet */
  }
}
function BellWatcher() {
  const items = useBell()
  useEffect(() => {
    watchBell(items, items.ready)
    const gone = staleChatDismissals(items.all || [], bellDismissedAtom.get())
    if (gone.length && items.ready) {
      const next = { ...bellDismissedAtom.get() }
      for (const k of gone) delete next[k]
      saveDismissed(next)
    }
  }, [items])
  return null
}

/** The agent half writes card lines only when this desktop half can draw them: it sets the plugin's own
 *  `desktop_cards` setting on each manager once per session of the app (a declared setting, written through Hermes'
 *  plugin settings route), and clears it when the plugin is disposed. */
const cardsSet = new Set()
let cardsTriedAt = {}
async function setDesktopCards(bot, on) {
  try {
    const params = { action: 'settings', key: ID, values: { desktop_cards: on } }
    await (bot && host.requestProfile ? host.requestProfile(bot, 'plugins.manage', params, 8000) : rpc('plugins.manage', params))
    if (on) cardsSet.add(bot)
  } catch {
    /* a bot without the agent half: nothing to switch */
  }
}
/** Turn the setting on for each manager (and the builder) once; one that failed is asked again after ten minutes, not
 *  at every refresh of the list (a bot without the agent half answers an error each time, and the ask wakes its backend). */
function syncCards(profiles) {
  const managers = (profiles || []).filter(p => botRole(p) === 'manager' || p.name === 'builder').map(p => p.name)
  const now = Date.now()
  for (const bot of cardsToSwitch(managers, cardsSet, cardsTriedAt, now)) {
    cardsTriedAt[bot] = now
    setDesktopCards(bot, true)
  }
}
function CardsSwitch() {
  const { data: snap } = useQuery(snapshotQuery())
  useEffect(() => syncCards(snap?.profiles), [snap])
  return null
}

// ── one card, read-only: where it is, what it asks of you, its story, and where to answer ──
const cardDialogAtom = atom(null)
function openCard(board, id) {
  if (TASK_ID_RE.test(String(id || ''))) cardDialogAtom.set({ board: board || '', id })
}

/** Answer a card where squads answer: in a new chat with the board's manager, the card named in the draft. */
async function replyToCard(board, task) {
  const snap = queryClient.getQueryData(SNAPSHOT_KEY)
  const boards = queryClient.getQueryData(BOARDS_KEY) || []
  const names = (snap?.profiles || []).map(p => p.name)
  const manager = boardManager(board, names, boards.find(b => b.slug === board)?.assignees || []) || (names.includes(task.created_by) ? task.created_by : '')
  if (!manager) return host.notify({ kind: 'error', message: lang().noManager })
  const stored = await newChat(manager)
  if (!stored) return
  const text = fmt(lang().replyDraft, task.id, task.title, board)
  for (let i = 0; i < 10; i++) {
    await new Promise(r => setTimeout(r, 300))
    if (await host.composer?.setDraft?.(stored || null, text)) return
  }
}

function StateChip({ state }) {
  const t = useT()
  return h('span', { className: 'sqh-st', 'data-state': state, title: t('sth_' + state) }, h('i', {}), t('st_' + state))
}

function CardDialogHost() {
  const sel = useValue(cardDialogAtom)
  return sel ? jsx(CardDialog, { sel, close: () => cardDialogAtom.set(null) }) : null
}
function CardDialog({ sel, close }) {
  const t = useT()
  const kanbanShown = useKanbanOn()
  const q = useQuery({
    queryKey: ['squad-hub', 'card', sel.board, sel.id],
    queryFn: () => kanban(`/tasks/${sel.id}${sel.board ? '?board=' + encodeURIComponent(sel.board) : ''}`),
    staleTime: 5000,
    retry: false
  })
  const task = q.data?.task
  const state = cardState(task)
  const needs = cardNeeds(task, q.data?.events, q.data?.comments)
  const story = historyOf(q.data?.events)
  const now = Date.now() / 1000
  const blockedForYou = task && task.status === 'blocked' && HUMAN_BLOCKS.has(task.block_kind)
  const bellItem = task ? (bellItems([], [], queryClient.getQueryData(BOARDS_KEY) || []).find(x => x.taskId === task.id) || null) : null
  return jsx(Dialog, {
    open: true,
    onOpenChange: o => !o && close(),
    children: jsxs(DialogContent, {
      className: 'sqh-cd',
      children: [
        jsxs(DialogHeader, {
          children: [
            jsx(DialogTitle, { children: task ? task.title : t('loading') }),
            jsx(DialogDescription, { children: task ? h('span', { className: 'sqh-cd-meta' }, jsx(StateChip, { state }), h('span', {}, t('cardOn', sel.board || '—', task.assignee || '—')), h('span', {}, task.id)) : '' })
          ]
        }),
        q.error ? h('div', { className: 'sqh-hint' }, t('cardMissing')) : null,
        task ? h('div', { className: 'sqh-cd-help' }, t('sth_' + state)) : null,
        task && needs.reason
          ? h('div', { className: 'sqh-cd-block' }, h('div', { className: 'sqh-cd-sub' }, blockedForYou ? t('cardNeedsYou') : t('cardLatest'), needs.at ? h('span', { className: 'sqh-hint' }, ' · ', shortAge(needs.at, now)) : null), h('div', { className: 'sqh-cd-reason' }, needs.reason.slice(0, 1600)))
          : null,
        story.length
          ? h('div', { className: 'sqh-cd-story' }, h('div', { className: 'sqh-cd-sub' }, t('cardStory')), story.map((e, i) => h('div', { key: i, className: 'sqh-cd-ev' }, h('span', {}, t.or('ev_' + e.kind, e.kind)), h('span', { className: 'sqh-hint' }, shortAge(e.at, now)))))
          : null,
        jsxs(DialogFooter, {
          children: [
            task && blockedForYou ? jsx(Button, { onClick: () => (close(), replyToCard(sel.board, task)), children: t('cardReply') }) : null,
            task ? jsx(Button, { variant: 'ghost', onClick: () => (close(), openTimeline(sel.board, task.id)), children: t('cardTimeline') }) : null,
            kanbanShown ? jsx(Button, { variant: 'ghost', onClick: () => (close(), host.navigate('/kanban')), children: t('cardBoard') }) : null,
            bellItem && !bellDismissedAtom.get()[dismissKey(bellItem)] ? jsx(Button, { variant: 'ghost', onClick: () => (dismissBell([bellItem]), close()), children: t('bellDismiss') }) : null,
            jsx(Button, { variant: 'ghost', onClick: close, children: t('close') })
          ].filter(Boolean)
        })
      ]
    })
  })
}

// ── cards inside a bot's reply: ::squad-task{board id} and ::squad-board{board} ──
function DirectiveNote({ text, source }) {
  return h('span', { className: 'sqh-cardnote', title: source }, jsx(Glyph, { name: 'circle-alert', size: 12 }), text)
}
function SquadTaskCard({ attrs, source, streaming }) {
  const t = useT()
  const kanbanShown = useKanbanOn()
  const { data: boards } = useQuery(boardsQuery())
  const raw = cardRef(attrs)
  const ref = raw && !raw.board ? { ...raw, board: boardOfTask(raw.id, boards) } : raw
  const q = useQuery({
    queryKey: ['squad-hub', 'card', ref?.board || '', ref?.id || ''],
    queryFn: () => kanban(`/tasks/${ref.id}${ref.board ? '?board=' + encodeURIComponent(ref.board) : ''}`),
    enabled: Boolean(ref) && !streaming,
    staleTime: 10000,
    refetchInterval: q => (['done', 'archived'].includes(q.state.data?.task?.status) ? false : 30000),
    retry: false
  })
  if (!ref) return jsx(DirectiveNote, { text: t('cardInvalid'), source })
  if (streaming || q.isLoading) return h('div', { className: 'sqh-card sqh-card-loading' }, jsx(Skeleton, { className: 'h-10 w-full' }))
  if (q.error || !q.data?.task) return jsx(DirectiveNote, { text: t('cardMissing'), source })
  const task = q.data.task
  const runs = q.data.runs || []
  const failed = runs.filter(r => FAILED_RUNS.has(r.outcome)).length
  return h(
    'div',
    { className: 'sqh-card', 'data-status': task.status },
    h('div', { className: 'sqh-card-top' }, jsx(StateChip, { state: cardState(task) }), h('span', { className: 'sqh-card-who' }, task.assignee || '—'), failed ? h('span', { className: 'sqh-card-fail' }, t('cardFailed', failed)) : null),
    h('div', { className: 'sqh-card-title' }, task.title),
    task.latest_summary ? h('div', { className: 'sqh-card-sum' }, String(task.latest_summary).slice(0, 220)) : null,
    h('div', { className: 'sqh-card-actions' }, h('button', { type: 'button', onClick: () => openCard(ref.board || '', ref.id) }, jsx(Glyph, { name: 'circle-alert', size: 12 }), t('cardDetail')), h('button', { type: 'button', onClick: () => openTimeline(ref.board || '', ref.id) }, jsx(Glyph, { name: 'chart-gantt', size: 12 }), t('cardTimeline')), kanbanShown ? h('button', { type: 'button', onClick: () => host.navigate('/kanban') }, jsx(Glyph, { name: 'layers', size: 12 }), t('cardBoard')) : null)
  )
}
function SquadBoardCard({ attrs, source, streaming }) {
  const t = useT()
  const kanbanShown = useKanbanOn()
  const ref = boardRef(attrs)
  const { data: boards, isLoading } = useQuery(boardsQuery())
  if (!ref) return jsx(DirectiveNote, { text: t('cardInvalid'), source })
  if (streaming || isLoading) return h('div', { className: 'sqh-card sqh-card-loading' }, jsx(Skeleton, { className: 'h-10 w-full' }))
  const b = (boards || []).find(x => x.slug === ref.board)
  if (!b) return jsx(DirectiveNote, { text: t('cardMissing'), source })
  const d = b.digest
  return h(
    'div',
    { className: 'sqh-card' },
    h('div', { className: 'sqh-card-title' }, b.name),
    h('div', { className: 'sqh-card-counts' }, [['block', d.blocked], ['review', d.review], ['run', d.running], ['queued', d.queued], ['done', d.done]].map(([k, n]) => h('span', { key: k, className: 'sqh-st', 'data-state': k, title: t('sth_' + k) }, h('i', {}), h('b', {}, n), ' ', t('st_' + k)))),
    h('div', { className: 'sqh-card-actions' }, h('button', { type: 'button', onClick: () => openTimeline(b.slug) }, jsx(Glyph, { name: 'chart-gantt', size: 12 }), t('cardTimeline')), kanbanShown ? h('button', { type: 'button', onClick: () => host.navigate('/kanban') }, jsx(Glyph, { name: 'layers', size: 12 }), t('cardBoard')) : null)
  )
}

// ── the squads timeline: who worked on what, when, how long cards waited, what failed ──
const RANGES = [['6h', 6 * 3600], ['24h', 86400], ['3d', 3 * 86400], ['7d', 7 * 86400]]
const timelineAtom = atom({ board: '', focus: '', range: 86400 })
let timelineDispose = null

/** Opens (or re-fronts) the Squads timeline tab on a board, optionally focused on one card. */
function openTimeline(board = '', focus = '') {
  timelineAtom.set({ ...timelineAtom.get(), board: board || timelineAtom.get().board, focus })
  if (typeof host.openWorkspace !== 'function') return
  timelineDispose = host.openWorkspace('squad-hub-timeline', { title: lang().timelineTitle, minWidth: '34rem', render: () => jsx(TimelinePage, {}), onClose: () => (timelineDispose = null) })
}

/** Runs of the cards that touch the window: the board rows carry no runs, so each card's runs come from its own
 *  task read (cached; done cards change rarely). */
async function loadTimeline(slug, range) {
  const now = Math.floor(Date.now() / 1000)
  const from = now - range
  const board = await kanban('/board?board=' + encodeURIComponent(slug) + '&include_archived=true')
  const touching = windowTasks(boardTasks(board), now, from)
  const tasks = touching.slice(0, TIMELINE_CAP)
  const full = await Promise.all(
    tasks.map(async t => {
      try {
        const d = await queryClient.fetchQuery({ queryKey: ['squad-hub', 'card', slug, t.id], queryFn: () => kanban(`/tasks/${t.id}?board=${encodeURIComponent(slug)}`), staleTime: t.status === 'done' ? 300000 : 15000 })
        return { ...t, runs: d.runs || [] }
      } catch {
        return t
      }
    })
  )
  let diagnostics = []
  try {
    diagnostics = (await kanban('/diagnostics?board=' + encodeURIComponent(slug))).diagnostics || []
  } catch {
    diagnostics = []
  }
  const inWindow = diagnostics.filter(d => (d.diagnostics || []).some(x => (x.last_seen_at || now) >= from))
  return { now, from, timeline: timelineOf(full, now, from), issues: issuesOf(full, inWindow, now), tasks: full.length, skipped: touching.length - tasks.length }
}

const ISSUE_ICON = { critical: 'circle-alert', error: 'circle-alert', warning: 'clock', info: 'clock' }
function TimelinePage() {
  const t = useT()
  const sel = useValue(timelineAtom)
  const { data: boards } = useQuery(boardsQuery())
  const slug = sel.board || boards?.[0]?.slug || ''
  const q = useQuery({ queryKey: ['squad-hub', 'timeline', slug, sel.range], queryFn: () => loadTimeline(slug, sel.range), enabled: Boolean(slug), staleTime: 20000, refetchInterval: 45000, retry: false })
  const [hover, setHover] = useState(null)
  const data = q.data
  const span = data ? Math.max(1, data.now - data.from) : 1
  const pct = v => ((v - data.from) / span) * 100
  const ticks = data ? Array.from({ length: 7 }, (_, i) => data.from + (span * i) / 6) : []
  const tickLabel = v => {
    const d = new Date(v * 1000)
    return sel.range > 86400 ? d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' }) + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit' }) : d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
  }
  const dur = s => (s >= 3600 ? (s / 3600).toFixed(s >= 36000 ? 0 : 1) + ' h' : Math.max(1, Math.round(s / 60)) + ' min')
  // the bars are rebuilt when the data, the selection or the language change, not at every hover over one of them
  const lanesView = useMemo(
    () => data && (data.timeline.lanes.length
      ? data.timeline.lanes.map(l =>
          h(
            'div',
            { key: l.name, className: 'sqh-tl-lane' },
            h('span', { className: 'sqh-tl-name', title: l.name }, l.name),
            h(
              'div',
              { className: 'sqh-tl-track' },
              l.bars.map((b, i) =>
                h('span', {
                  key: i,
                  className: 'sqh-tl-bar',
                  'data-kind': b.kind,
                  'data-state': b.state || b.tone || 'run',
                  'data-open': b.open ? 'true' : 'false',
                  'data-focus': sel.focus && sel.focus === b.taskId ? 'true' : 'false',
                  style: { left: Math.max(0, pct(b.start)) + '%', width: Math.max(0.35, pct(Math.min(b.end, data.now)) - Math.max(0, pct(b.start))) + '%' },
                  onMouseEnter: () => setHover({ ...b, lane: l.name }),
                  onMouseLeave: () => setHover(null),
                  onClick: () => (timelineAtom.set({ ...sel, focus: b.taskId }), openCard(slug, b.taskId))
                })
              )
            )
          )
        )
      : h('div', { className: 'sqh-empty' }, t('timelineQuiet'))),
    [data, sel, slug, t]
  )
  return h(
    'div',
    { className: 'sqh sqh-tl' },
    h(
      'div',
      { className: 'sqh-tl-head' },
      h('div', { className: 'sqh-tl-title' }, jsx(Glyph, { name: 'chart-gantt', size: 16 }), t('timelineTitle')),
      h('div', { className: 'sqh-tl-boards' }, (boards || []).map(b => h('button', { key: b.slug, type: 'button', 'data-on': b.slug === slug ? 'true' : 'false', onClick: () => timelineAtom.set({ ...sel, board: b.slug, focus: '' }) }, b.name, b.digest.blocked ? h('span', { className: 'sqh-bc-blocked' }, h('i', {}), b.digest.blocked) : null))),
      h('div', { className: 'sqh-tl-range' }, RANGES.map(([label, secs]) => h('button', { key: label, type: 'button', 'data-on': sel.range === secs ? 'true' : 'false', onClick: () => timelineAtom.set({ ...sel, range: secs }) }, label)), jsx(IconBtn, { icon: 'refresh', label: t('refresh'), onClick: () => q.refetch() }))
    ),
    !slug ? jsx(EmptyState, { title: t('timelineEmpty'), description: t('timelineEmptyHint') }) : null,
    slug && q.isLoading ? h('div', { className: 'sqh-tl-body' }, jsx(Skeleton, { className: 'h-40 w-full' })) : null,
    data
      ? h(
          'div',
          { className: 'sqh-tl-body' },
          h(
            'div',
            { className: 'sqh-tl-chart' },
            h('div', { className: 'sqh-tl-axis' }, h('span', { className: 'sqh-tl-name' }), h('div', { className: 'sqh-tl-track' }, ticks.map((v, i) => h('span', { key: i, className: 'sqh-tl-tick', style: { left: (i / 6) * 100 + '%' } }, tickLabel(v))))),
            lanesView,
            h('div', { className: 'sqh-tl-hover' }, hover ? [h('b', { key: 'a' }, hover.title), ' · ', hover.lane, ' · ', t('st_' + (hover.state || 'run')) + (hover.kind === 'run' && hover.outcome && hover.outcome !== 'running' ? ' (' + t.or('out_' + hover.outcome, hover.outcome) + ')' : '') + ' · ' + dur(hover.end - hover.start) + (hover.open ? ' · ' + t('tlStill') : ''), hover.summary ? h('span', { key: 's', className: 'sqh-hint' }, ' — ', String(hover.summary).slice(0, 140)) : null] : h('span', { className: 'sqh-hint' }, t('tlHint'))),
            h('div', { className: 'sqh-tl-legend' }, STATES.map(st => h('span', { key: st, className: 'sqh-st', 'data-state': st, title: t('sth_' + st) }, h('i', {}), t('st_' + st))))
          ),
          h(
            'div',
            { className: 'sqh-tl-issues' },
            h('div', { className: 'sqh-tl-sub' }, t('issuesTitle'), ' ', h('span', { className: 'sqh-hint' }, data.issues.length || '')),
            data.issues.length
              ? data.issues.slice(0, 40).map((x, i) =>
                  h(
                    'button',
                    { key: i, type: 'button', className: 'sqh-issue', 'data-sev': x.severity, 'data-focus': sel.focus === x.taskId ? 'true' : 'false', onClick: () => (timelineAtom.set({ ...sel, focus: x.taskId }), openCard(slug, x.taskId)) },
                    jsx(Glyph, { name: ISSUE_ICON[x.severity] || 'clock', size: 13 }),
                    h('span', { className: 'sqh-issue-main' }, h('span', { className: 'sqh-issue-kind' }, t.or('iss_' + x.kind, x.kind.replace(/_/g, ' ')), x.count > 1 ? ' ×' + x.count : '', x.source === 'timeline' && x.text ? ' · ' + (x.kind === 'run_failed' ? t.or('out_' + x.text, x.text) : x.text) : ''), h('span', { className: 'sqh-issue-title' }, x.title), h('span', { className: 'sqh-hint' }, [x.assignee, shortAge(x.at)].filter(Boolean).join(' · ')))
                  )
                )
              : h('div', { className: 'sqh-empty' }, t('issuesNone'))
          )
        )
      : null,
    data?.skipped ? h('div', { className: 'sqh-hint' }, t('tlSkipped', data.skipped)) : null,
    q.error ? h('div', { className: 'sqh-empty' }, t('loadFailed')) : null
  )
}

/** An empty chat says whose it is and where it works, with that place's other chats one click away. */
function ChatIntro({ sessionId }) {
  const t = useT()
  const stored = useValue(host.state.focusedStoredSessionId)
  const trees = useTrees()
  const attention = useAttention(stored)
  const id = storedOf(sessionId) || (host.state.focusedSessionId.get() === sessionId ? stored : null)
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
    h(
      'div',
      { className: 'sqh-intro-brand' },
      jsx(IconTile, { icon: iconFor(tree.bot, prefs.icons || {}), size: 44 }),
      Wordmark && prefs.chatWordmark !== false ? jsx(Wordmark, { className: 'sqh-intro-mark', text: introName(tree.bot), width: 'calc(80% - 1rem)' }) : h('h2', {}, introName(tree.bot)),
      h('div', { className: 'sqh-intro-place' }, where.length ? where.join(' · ') : t('introNoProject'))
    ),
    pending.length
      ? h('div', { className: 'sqh-intro-list' }, h('div', { className: 'sqh-hint' }, t('alsoPending')), pending.map(x => h(Row, { key: x.session.id, depth: 0, onClick: () => openChat(tree.bot.name, x.session.id) }, jsx(SessionStatusDot, { storedSessionId: x.session.id, session: x.session }), h('span', { className: 'sqh-label' }, x.session.title || x.session.preview || 'Chat'), h('span', { className: 'sqh-where' }, whereOf(x).split(' · ').pop() || tree.bot.title))))
      : null
  )
}

/** Status bar: where the focused chat works (bot · project · lane) and the tools that follow it. */
function ChatContext() {
  const t = useT()
  const id = useValue(host.state.focusedStoredSessionId)
  const previews = usePreviews(id)
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
  const prefs = useValue(prefsAtom)
  return h(
    'div',
    { style: { display: 'flex', alignItems: 'center', gap: 12, padding: '4px 0' } },
    h('div', { style: { display: 'flex', gap: 4 } }, ...['#1e1e2e', '#cba6f7', '#89b4fa', '#a6e3a1', '#f6f3ee'].map(c => h('span', { key: c, style: { width: 14, height: 14, borderRadius: 4, background: c, boxShadow: 'inset 0 0 0 1px color-mix(in srgb, currentColor 15%, transparent)' } }))),
    h('div', { style: { flex: 1 } }, jsx(ToggleRow, { checked: prefs.squadsTheme !== false, label: t('themeName'), description: t('themeHint'), onChange: on => savePrefs({ squadsTheme: on }) }))
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
  const nav = [['new-session', 'New session'], ['messaging', 'Messaging'], ['artifacts', 'Artifacts'], ['cron', 'Scheduled jobs'], ['kanban:nav', 'Kanban']]
  return h(
    'div',
    {},
    jsx(ThemeRow, {}),
    h('div', { className: 'sqh-hint', style: { padding: '14px 0 4px' } }, t('setup')),
    jsx(ToggleRow, { checked: prefs.floatSides, label: t('floatSides'), description: t('floatSidesHint'), onChange: on => savePrefs({ floatSides: on }) }),
    h('div', { style: { display: 'flex', alignItems: 'center', gap: 12, padding: '6px 0' } }, h('div', { style: { flex: 1 } }, h('div', { style: { color: 'var(--foreground)', fontWeight: 500 } }, t('layoutName')), h('div', { className: 'sqh-hint' }, t('layoutHint'))), jsx(Button, { variant: 'outline', onClick: applySquadsLayout, children: t('themeUse') })),
    jsx(ToggleRow, { checked: prefs.chatWordmark !== false, label: t('chatWordmark'), description: t('chatWordmarkHint'), onChange: on => savePrefs({ chatWordmark: on }) }),
    jsx(ToggleRow, { checked: prefs.notifyAway !== false, label: t('notifyAway'), description: t('notifyAwayHint'), onChange: on => savePrefs({ notifyAway: on }) }),
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
  "bell": "<path d=\"M10.268 21a2 2 0 0 0 3.464 0\" /> <path d=\"M3.262 15.326A1 1 0 0 0 4 17h16a1 1 0 0 0 .74-1.673C19.41 13.956 18 12.499 18 8A6 6 0 0 0 6 8c0 4.499-1.411 5.956-2.738 7.326\" />",
  "chart-gantt": "<path d=\"M10 6h8\" /> <path d=\"M12 16h6\" /> <path d=\"M3 3v16a2 2 0 0 0 2 2h16\" /> <path d=\"M8 11h7\" />",
  "git-pull-request": "<circle cx=\"18\" cy=\"18\" r=\"3\" /> <circle cx=\"6\" cy=\"6\" r=\"3\" /> <path d=\"M13 6h3a2 2 0 0 1 2 2v7\" /> <line x1=\"6\" x2=\"6\" y1=\"9\" y2=\"21\" />",
  "git-pull-request-draft": "<circle cx=\"18\" cy=\"18\" r=\"3\" /> <circle cx=\"6\" cy=\"6\" r=\"3\" /> <path d=\"M18 6V5\" /> <path d=\"M18 11v-1\" /> <line x1=\"6\" x2=\"6\" y1=\"9\" y2=\"21\" />",
  "git-merge": "<circle cx=\"18\" cy=\"18\" r=\"3\" /> <circle cx=\"6\" cy=\"6\" r=\"3\" /> <path d=\"M6 21V9a9 9 0 0 0 9 9\" />",
  "circle-alert": "<circle cx=\"12\" cy=\"12\" r=\"10\" /> <line x1=\"12\" x2=\"12\" y1=\"8\" y2=\"12\" /> <line x1=\"12\" x2=\"12.01\" y1=\"16\" y2=\"16\" />",
  "clock": "<path d=\"M12 6v6l4 2\" /> <circle cx=\"12\" cy=\"12\" r=\"10\" />",
  "folder": "<path d=\"M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z\" />",
  "folder-git-2": "<path d=\"M9 20H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H20a2 2 0 0 1 2 2v5\" /> <circle cx=\"13\" cy=\"12\" r=\"2\" /> <path d=\"M18 19c-2.8 0-5-2.2-5-5v8\" /> <circle cx=\"20\" cy=\"19\" r=\"2\" />",
  "layers": "<path d=\"M12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83z\" /> <path d=\"M2 12a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 12\" /> <path d=\"M2 17a1 1 0 0 0 .58.91l8.6 3.91a2 2 0 0 0 1.65 0l8.58-3.9A1 1 0 0 0 22 17\" />",
  "house": "<path d=\"M15 21v-8a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v8\" /> <path d=\"M3 10a2 2 0 0 1 .709-1.528l7-6a2 2 0 0 1 2.582 0l7 6A2 2 0 0 1 21 10v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z\" />",
  "git-branch": "<line x1=\"6\" x2=\"6\" y1=\"3\" y2=\"15\" /> <circle cx=\"18\" cy=\"6\" r=\"3\" /> <circle cx=\"6\" cy=\"18\" r=\"3\" /> <path d=\"M18 9a9 9 0 0 1-9 9\" />",
  "file-key": "<path d=\"M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z\" /> <circle cx=\"10\" cy=\"16\" r=\"2\" /> <path d=\"m16 10-4.5 4.5\" /> <path d=\"m15 11 1 1\" />"
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
html[data-sqh-float] [data-sqh-main]{padding:0 calc(var(--sqh-gutter,40px) - 10px)}
html[data-sqh-float] [data-sqh-main][data-sqh-solo]{flex:1 1 0%!important}
html[data-sqh-float] [data-sqh-side]{position:absolute!important;top:0;bottom:0;z-index:45;width:var(--sqh-w)!important;min-width:0!important;max-width:min(var(--sqh-w),85vw)!important;flex:none!important;background:var(--sidebar,var(--ui-bg-chrome,var(--background)));transition:transform var(--sqh-in) var(--sqh-ease-in),opacity var(--sqh-in) ease;will-change:transform,opacity;box-shadow:0 18px 50px -12px color-mix(in srgb,black 45%,transparent)}
html[data-sqh-float] [data-sqh-side="left"]{left:0;transform:translateX(-100%);border-right:1px solid var(--ui-stroke-secondary,var(--border))}
html[data-sqh-float] [data-sqh-side="right"]{right:0;transform:translateX(100%);border-left:1px solid var(--ui-stroke-secondary,var(--border))}
html[data-sqh-float]{--sqh-in:.26s;--sqh-out:.17s;--sqh-ease-in:cubic-bezier(.22,1,.36,1);--sqh-ease-out:cubic-bezier(.4,0,.9,.6)}
html[data-sqh-float] [data-sqh-side]:not([data-sqh-open]){visibility:hidden;opacity:.35;transition:transform var(--sqh-out) var(--sqh-ease-out),opacity var(--sqh-out) ease-in,visibility 0s linear var(--sqh-out)}
html[data-sqh-float] [data-sqh-side][data-sqh-open]{transform:none;opacity:1}
[data-sqh-edge]{position:fixed;top:40px;bottom:28px;width:4px;z-index:44;background:transparent}
[data-sqh-edge=left]{left:0}
[data-sqh-edge=right]{right:0}
[data-sqh-edge][hidden]{display:none}
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
.sqh-intro-brand{display:flex;flex-direction:column;align-items:center;text-align:center;gap:10px}
.sqh-intro-brand h2{margin:0;font-size:1.6rem;font-weight:600;color:var(--foreground)}
.sqh-intro-mark{margin:0}
.sqh-intro-place{font-size:12.5px;color:var(--muted-foreground);letter-spacing:.01em}
.sqh-intro-head h2{margin:0;font-size:1.05rem;font-weight:600;color:var(--foreground)}
.sqh-intro-where{display:flex;flex-wrap:wrap;gap:6px}
.sqh-intro .sqh-where{max-width:none;font-size:.75rem;padding:2px 9px}
.sqh-intro-list{display:grid;gap:2px}
.sqh-menuchat{display:flex;align-items:center;gap:8px;min-width:280px}
.sqh-menuchat span:nth-child(2){flex:1}
.sqh-boardchip{display:inline-flex;gap:6px;align-items:center;margin-left:auto;background:none;border:0;padding:0 2px;font-size:10.5px;color:var(--muted-foreground);cursor:pointer}
.sqh-boardchip span,.sqh-tl-boards span{display:inline-flex;align-items:center;gap:3px}
.sqh-boardchip i,.sqh-tl-boards i,.sqh-card-col i{width:6px;height:6px;border-radius:50%;display:inline-block}
.sqh-bc-blocked i{background:var(--dt-destructive)}
.sqh-bc-review i{background:var(--color-amber-500)}
.sqh-bc-running i{background:var(--ui-accent,var(--primary))}
.sqh-boardchip[data-tone=blocked]{color:var(--foreground);font-weight:500}
.sqh-bc-seen i{background:var(--muted-foreground);opacity:.6}
.sqh-lanechip{display:inline-flex;gap:6px;align-items:center;margin-left:auto;font-size:10.5px;color:var(--muted-foreground)}
.sqh-lane:hover .sqh-lanechip{display:none}
.sqh-pr{display:inline-flex;align-items:center;gap:2px;background:none;border:0;padding:0;color:inherit;cursor:pointer;font:inherit}
.sqh-pr[data-state=open]{color:var(--color-emerald-500)}
.sqh-pr[data-state=merged]{color:var(--color-violet-500)}
.sqh-pr[data-state=closed]{color:var(--dt-destructive)}
.sqh-dirty{opacity:.8}
.sqh-bell{position:relative;display:inline-flex;align-items:center;gap:4px;height:100%;padding:0 6px;background:none;border:0;color:var(--ui-text-secondary,var(--muted-foreground));cursor:pointer}
.sqh-bell[data-on=true]{color:var(--foreground)}
.sqh-bell-n{font-size:10px;font-weight:600;min-width:14px;height:14px;padding:0 3px;border-radius:7px;display:inline-flex;align-items:center;justify-content:center;background:color-mix(in srgb,var(--foreground) 14%,transparent)}
.sqh-bell-n[data-fresh=true]{background:color-mix(in srgb,var(--color-amber-500) 70%,transparent);color:var(--background)}
.sqh-bellmenu{min-width:300px;max-width:380px}
.sqh-bellhead{padding:6px 8px 4px;font-size:11px;color:var(--muted-foreground)}
.sqh-bellrow{display:flex;gap:8px;align-items:flex-start;min-width:0}
.sqh-bellmain{display:grid;min-width:0}
.sqh-belltitle{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sqh-card{margin:8px 0;max-width:560px;border:1px solid var(--ui-stroke-tertiary,var(--border));border-radius:10px;padding:10px 12px;background:color-mix(in srgb,var(--card,var(--background)) 70%,transparent);display:grid;gap:5px;font-size:13px}
.sqh-card-loading{padding:8px}
.sqh-card-top{display:flex;gap:10px;align-items:center;font-size:11px;color:var(--muted-foreground)}
.sqh-card-col{display:inline-flex;gap:5px;align-items:center}
.sqh-card-col[data-tone=bad] i{background:var(--dt-destructive)}
.sqh-card-col[data-tone=warn] i{background:var(--color-amber-500)}
.sqh-card-col[data-tone=good] i{background:var(--ui-accent,var(--primary))}
.sqh-card-col[data-tone=muted] i{background:color-mix(in srgb,var(--foreground) 35%,transparent)}
.sqh-card-fail{color:var(--dt-destructive)}
.sqh-card-title{color:var(--foreground);font-weight:500}
.sqh-card-sum{color:var(--muted-foreground);font-size:12px;line-height:1.45}
.sqh-card-counts{display:flex;flex-wrap:wrap;gap:12px;font-size:12px;color:var(--muted-foreground)}
.sqh-card-counts [data-tone=bad] b{color:var(--dt-destructive)}
.sqh-card-actions{display:flex;gap:6px;margin-top:2px}
.sqh-card-actions button,.sqh-tl-boards button,.sqh-tl-range button{display:inline-flex;gap:5px;align-items:center;font-size:11.5px;padding:3px 8px;border-radius:6px;border:1px solid var(--ui-stroke-tertiary,var(--border));background:none;color:var(--muted-foreground);cursor:pointer}
.sqh-card-actions button:hover,.sqh-tl-boards button:hover,.sqh-tl-range button:hover{color:var(--foreground)}
.sqh-tl-boards button[data-on=true],.sqh-tl-range button[data-on=true]{color:var(--foreground);background:color-mix(in srgb,var(--foreground) 7%,transparent)}
.sqh-cardnote{display:inline-flex;gap:5px;align-items:center;font-size:12px;color:var(--muted-foreground)}
.sqh-tl{height:100%;overflow:auto;padding:16px 20px;display:flex;flex-direction:column;gap:14px;container-type:inline-size}
.sqh-tl-head{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px}
.sqh-tl-title{display:flex;gap:8px;align-items:center;font-weight:600;color:var(--foreground);margin-right:6px}
.sqh-tl-boards,.sqh-tl-range{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.sqh-tl-range{margin-left:auto}
.sqh-tl-body{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:18px;align-items:start}
@container (max-width:900px){.sqh-tl-body{grid-template-columns:1fr}}
.sqh-tl-chart{display:grid;gap:6px;min-width:0}
.sqh-tl-axis,.sqh-tl-lane{display:grid;grid-template-columns:120px minmax(0,1fr);gap:10px;align-items:center}
.sqh-tl-name{font-size:12px;color:var(--muted-foreground);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sqh-tl-track{position:relative;height:20px;border-radius:5px;background:color-mix(in srgb,var(--foreground) 4%,transparent)}
.sqh-tl-axis .sqh-tl-track{background:none;height:16px}
.sqh-tl-tick{position:absolute;top:0;transform:translateX(-50%);font-size:10px;color:var(--muted-foreground);white-space:nowrap}
.sqh-tl-tick:first-child{transform:none}
.sqh-tl-tick:last-child{transform:translateX(-100%)}
.sqh-tl-bar{position:absolute;top:3px;bottom:3px;border-radius:4px;cursor:pointer;min-width:3px;transition:filter .12s}
.sqh-tl-bar:hover{filter:brightness(1.15)}
.sqh-tl-bar[data-open=true]{border-right:2px dashed color-mix(in srgb,var(--foreground) 50%,transparent)}
.sqh-tl-bar[data-focus=true]{outline:2px solid var(--foreground);outline-offset:1px}
.sqh-tl-hover{min-height:20px;font-size:12px;color:var(--foreground);padding-top:4px}
.sqh-tl-issues{display:grid;gap:4px;min-width:0}
.sqh-tl-sub{font-size:12px;font-weight:600;color:var(--foreground);padding-bottom:4px}
.sqh-issue{display:flex;gap:8px;align-items:flex-start;text-align:left;padding:7px 8px;border-radius:8px;border:1px solid transparent;background:none;color:var(--muted-foreground);cursor:pointer;min-width:0}
.sqh-issue:hover,.sqh-issue[data-focus=true]{background:color-mix(in srgb,var(--foreground) 5%,transparent);border-color:var(--ui-stroke-tertiary,var(--border))}
.sqh-issue[data-sev=error],.sqh-issue[data-sev=critical]{color:var(--dt-destructive)}
.sqh-issue[data-sev=warning]{color:var(--color-amber-500)}
.sqh-issue-main{display:grid;min-width:0;gap:1px}
.sqh-issue-kind{font-size:11px;font-weight:600}
.sqh-issue-title{font-size:12.5px;color:var(--foreground);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sqh-st{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:var(--muted-foreground);white-space:nowrap}
.sqh-st i{width:8px;height:8px;border-radius:2px;display:inline-block;background:var(--sqh-c)}
:is(.sqh-st,.sqh-tl-bar)[data-state=queued]{--sqh-c:color-mix(in srgb,var(--foreground) 22%,transparent)}
:is(.sqh-st,.sqh-tl-bar)[data-state=dep]{--sqh-c:color-mix(in srgb,var(--color-sky-500) 45%,transparent)}
:is(.sqh-st,.sqh-tl-bar)[data-state=run]{--sqh-c:var(--color-sky-500)}
:is(.sqh-st,.sqh-tl-bar)[data-state=block]{--sqh-c:var(--color-amber-500)}
:is(.sqh-st,.sqh-tl-bar)[data-state=review]{--sqh-c:var(--color-violet-500)}
:is(.sqh-st,.sqh-tl-bar)[data-state=done]{--sqh-c:var(--color-emerald-500)}
:is(.sqh-st,.sqh-tl-bar)[data-state=fail]{--sqh-c:var(--dt-destructive)}
:is(.sqh-st,.sqh-tl-bar)[data-state=stop]{--sqh-c:var(--color-zinc-400)}
.sqh-tl-bar[data-state]{background:var(--sqh-c)}
.sqh-tl-bar[data-kind=wait],.sqh-tl-bar[data-kind=state]{top:6px;bottom:6px;opacity:.75;background:repeating-linear-gradient(135deg,var(--sqh-c) 0 5px,color-mix(in srgb,var(--sqh-c) 55%,transparent) 5px 10px)}
.sqh-tl-legend{display:flex;flex-wrap:wrap;gap:6px 14px;padding-top:6px}
.sqh-bellhead{display:flex;align-items:center;justify-content:space-between;gap:8px}
.sqh-bellclear{background:none;border:0;padding:0;font-size:11px;color:var(--muted-foreground);cursor:pointer}
.sqh-bellclear:hover{color:var(--foreground);text-decoration:underline}
.sqh-bellage{margin-left:auto;font-size:10.5px;color:var(--muted-foreground);padding-left:8px;white-space:nowrap}
.sqh-enter{width:14px;display:grid;place-items:center;color:var(--ui-text-tertiary);flex:none}
.sqh-focushead{display:grid;gap:4px;padding:6px 8px 6px;border-bottom:1px solid var(--ui-stroke-tertiary,var(--border))}
.sqh-back{display:inline-flex;align-items:center;gap:6px;background:none;border:0;padding:3px 4px;border-radius:6px;color:var(--ui-text-tertiary);font-size:.75rem;cursor:pointer;justify-self:start}
.sqh-back:hover{color:var(--foreground);background:color-mix(in srgb,currentColor 10%,transparent)}
.sqh-focustitle{display:flex;align-items:center;gap:6px;padding:0 4px;font-weight:600;color:var(--foreground)}
.sqh-bellgroup{display:flex;align-items:center;gap:6px;padding:8px 8px 2px;font-size:11px;font-weight:600;color:var(--foreground)}
.sqh-bellgroup-n{font-weight:400;color:var(--muted-foreground)}
.sqh-bellgroup .sqh-bellclear{margin-left:auto}
.sqh-clean{max-width:560px;max-height:min(720px,86vh);overflow:auto}
.sqh-cleansec{display:grid;gap:2px}
.sqh-cleanrow{display:flex;align-items:center;gap:10px;padding:5px 6px;border-radius:7px;cursor:pointer}
.sqh-cleanrow:hover{background:color-mix(in srgb,var(--foreground) 5%,transparent)}
.sqh-cleanmain{display:grid;min-width:0;flex:1}
.sqh-squadpick{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.sqh-cd{max-width:560px}
.sqh-cd-meta{display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;font-size:12px}
.sqh-cd-help{font-size:12px;color:var(--muted-foreground)}
.sqh-cd-sub{font-size:11.5px;font-weight:600;color:var(--foreground);padding-bottom:4px}
.sqh-cd-reason{white-space:pre-wrap;font-size:12.5px;line-height:1.5;color:var(--foreground);max-height:240px;overflow:auto;padding:8px 10px;border-radius:8px;background:color-mix(in srgb,var(--foreground) 5%,transparent)}
.sqh-cd-story{display:grid;gap:3px}
.sqh-cd-ev{display:flex;justify-content:space-between;font-size:12px;color:var(--muted-foreground)}
`

/** Module state that belongs to one enabled run. Switching the plugin off and on again runs register() again on this
 *  same module, so nothing noted by the previous run may read as news: not the layout (a "pick" that already
 *  happened), not the bell (every waiting card would notify), not the busy list or the open dialogs. */
function resetRun() {
  liveKey = ''
  bellKnown = null
  lastRoot = ''
  lastPersist = 0
  reopening = 0
  openDialog = null
  layoutSig = undefined
  layoutRead = { trees: [], zones: {} }
  treesMemo = null
  cardsTriedAt = {}
  clearTimeout(pickRevealTimer)
  liveAtom.set([])
  focusAtom.set(null)
  cardDialogAtom.set(null)
  bellSeenAtom.set([])
  timelineAtom.set({ board: '', focus: '', range: 86400 })
}

export default {
  id: ID,
  name: 'Hermes Agent Squads Hub',
  description: 'One navigator for Hermes Agent Squads: bot → project → folder → worktree → chat, several bots open at once.',
  defaultEnabled: false,
  register(ctx) {
    resetRun()
    ctxRef = ctx
    storage = ctx.storage
    ctx.i18n?.register?.(MESSAGES)
    prefsAtom.set(upgradePrefs(ctx.storage.get('prefs', null), DEFAULT_PREFS))
    ctx.storage.set('prefs', prefsAtom.get())
    collapsedAtom.set(ctx.storage.get('collapsed', {}))
    previewsAtom.set(ctx.storage.get('previews', {}))
    bellDismissedAtom.set(ctx.storage.get('bellDismissed', {}))

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
    ctx.register({ id: 'bell', area: STATUSBAR_AREAS.right, order: 5, render: () => jsx(Bell, {}) })
    // the watcher, the cards switch and the card dialog must not live in a status-bar item the user can hide:
    // title-bar slots are permanent mount points and render nothing visible here
    ctx.register({ id: 'bell-host', area: sdk.TITLEBAR_AREAS?.right || 'titleBar.right', order: 999, render: () => h(React_Fragment, {}, jsx(BellWatcher, {}), jsx(CardDialogHost, {}), jsx(CardsSwitch, {}), jsx(ThemeKeeper, {})) })
    if (TRANSCRIPT_DIRECTIVE_AREA) {
      ctx.registerMany([
        { id: 'card-task', area: TRANSCRIPT_DIRECTIVE_AREA, data: { name: 'squad-task', render: p => jsx(SquadTaskCard, p) } },
        { id: 'card-board', area: TRANSCRIPT_DIRECTIVE_AREA, data: { name: 'squad-board', render: p => jsx(SquadBoardCard, p) } }
      ])
    }
    ctx.onDispose(() => timelineDispose?.())
    // forgotten at once, not when the request returns: a quick off/on must switch the cards on again, not find them "done"
    ctx.onDispose(() => { for (const bot of [...cardsSet]) (cardsSet.delete(bot), setDesktopCards(bot, false)) })
    let liveTimer = null
    const liveSoon = () => liveTimer || (liveTimer = setTimeout(() => ((liveTimer = null), queryClient.invalidateQueries({ queryKey: LIVE_KEY })), 1500))
    for (const type of ['approval.request', 'clarify.request', 'request.cancel', 'message.complete']) ctx.onEvent(type, liveSoon)
    ctx.onDispose(() => clearTimeout(liveTimer))
    ctx.onDispose(stopFloat)
    applyFloat()
    document.addEventListener('dblclick', onTreeDoubleClick, true)
    ctx.onDispose(() => document.removeEventListener('dblclick', onTreeDoubleClick, true))
    const pickTimer = setInterval(whileVisible(watchLayoutPick), 1000)
    ctx.onDispose(() => (clearInterval(pickTimer), clearTimeout(pickRevealTimer)))
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
          run: reopenLastPreview
        }
      },
      { id: 'cmd-timeline', area: PALETTE_AREA, data: { id: 'squad-hub.timeline', label: MESSAGES.en.cmdTimeline, keywords: ['gantt', 'timeline', 'kanban', 'runs', 'failures'], run: () => openTimeline() } },
      { id: 'cmd-next', area: PALETTE_AREA, data: { id: 'squad-hub.next-pending', label: MESSAGES.en.cmdNext, keywords: ['pending', 'unread', 'working', 'next'], run: goNextPending } },
      { id: 'key-next', area: KEYBINDS_AREA, data: { id: 'squad-hub.next-pending', label: MESSAGES.en.cmdNext, category: 'navigation', defaults: ['mod+shift+u'], run: goNextPending } },
      { id: 'cmd-float', area: PALETTE_AREA, data: { id: 'squad-hub.float', label: MESSAGES.en.cmdFloat, keywords: ['float', 'auto hide', 'sidebar', 'dock'], run: () => savePrefs({ floatSides: !prefsAtom.get().floatSides }) } },
      { id: 'key-pin-left', area: KEYBINDS_AREA, data: { id: 'squad-hub.pin-left', label: MESSAGES.en.cmdPinLeft, category: 'view', defaults: [], run: () => pinSide('left') } },
      { id: 'key-pin-right', area: KEYBINDS_AREA, data: { id: 'squad-hub.pin-right', label: MESSAGES.en.cmdPinRight, category: 'view', defaults: [], run: () => pinSide('right') } },
      { id: 'cmd-pin-left', area: PALETTE_AREA, data: { id: 'squad-hub.pin-left', label: MESSAGES.en.cmdPinLeft, keywords: ['pin', 'sidebar', 'left', 'float'], run: () => pinSide('left') } },
      { id: 'cmd-pin-right', area: PALETTE_AREA, data: { id: 'squad-hub.pin-right', label: MESSAGES.en.cmdPinRight, keywords: ['pin', 'files', 'terminal', 'right', 'float'], run: () => pinSide('right') } },
      { id: 'cmd-layout', area: PALETTE_AREA, data: { id: 'squad-hub.layout', label: MESSAGES.en.cmdLayout, keywords: ['layout', 'terminal', 'files'], run: () => host.navigate('/settings?tab=appearance&page=window-layout') } },
      { id: 'key-preview', area: KEYBINDS_AREA, data: { id: 'squad-hub.preview', label: MESSAGES.en.cmdPreview, category: 'view', defaults: [], run: reopenLastPreview } }
    ])

    ctx.onEvent('session.info', e => {
      const stored = e.payload?.stored_session_id || e.payload?.session_key
      if (!e.session_id || !stored) return
      // a conversation compressed into a new stored id takes its remembered previews along
      const { from } = bind(e.session_id, stored, true)
      if (from) rememberPreviews(rekeyPreviews(previewsAtom.get(), from, stored))
      if (runtimeToStored.size > 500) runtimeToStored.delete(runtimeToStored.keys().next().value)
      syncLive()
    })
    for (const atomLike of [host.state.busyBySession, host.state.focusedSessionId, host.state.focusedStoredSessionId]) {
      ctx.onDispose(atomLike.listen(syncLive))
    }
    // opening a chat marks it read in the backend: pick that up so its dot goes quiet here too
    let listTimer = null
    ctx.onDispose(host.state.focusedStoredSessionId.listen(() => (clearTimeout(listTimer), (listTimer = setTimeout(refreshSoon, 1200)))))
    ctx.onDispose(() => clearTimeout(listTimer))
    // the chat in view is read, whichever way it came to the front (a tab, Sessions, the bell) and whoever owns it
    const ownerOf = id => host.state.focusedSessionProfile?.get?.() || (queryClient.getQueryData(SNAPSHOT_KEY)?.chats || []).find(c => c.id === id)?.profile || ''
    let refreshedFor = null
    const readShown = () => {
      const id = host.state.focusedStoredSessionId.get()
      if (!id) return
      const row = (queryClient.getQueryData(SNAPSHOT_KEY)?.chats || []).find(c => c.id === id)
      // a chat the list does not know yet: one fetch per chat, never one per unread change
      if (!row && refreshedFor !== id) {
        refreshedFor = id
        refreshSoon()
      }
      const unread = unreadAtom.get()
      if ((row ? chatIds(row) : [id]).some(x => unread.includes(x))) markRead(ownerOf(id), id).then(syncLive)
    }
    let readTimer = null
    ctx.onDispose(host.state.focusedStoredSessionId.listen(() => {
      clearTimeout(readTimer)
      readTimer = setTimeout(readShown, 400)
    }))
    ctx.onDispose(() => clearTimeout(readTimer))
    ctx.onDispose(unreadAtom.listen(readShown))
    // the unread filters read the chat list: apply them again each time it arrives
    ctx.onDispose(queryClient.getQueryCache().subscribe(e => {
      if (e?.type === 'updated' && e.action?.type === 'success' && e.query?.queryKey?.[1] === SNAPSHOT_KEY[1] && e.query.queryKey[0] === SNAPSHOT_KEY[0]) syncLive()
    }))
    syncLive()
    ctx.onEvent('preview.open', e => {
      if (reopening) return
      const url = String(e.payload?.url || '').trim()
      // A runtime id we never saw a session.info for is a chat this window cannot name: skip it, never guess.
      const owner = e.session_id ? storedOf(e.session_id) : host.state.focusedStoredSessionId.get()
      if (!url || !owner) return
      rememberPreviews(rememberPreview(previewsAtom.get(), owner, { url, label: String(e.payload?.label || '').trim(), at: Date.now() }))
    })
    for (const type of ['session.title', 'sessions.changed']) ctx.onEvent(type, () => refreshSoon())
    ctx.onDispose(() => {
      clearTimeout(refreshTimer)
      refreshTimer = null
    })
    ctx.registerSettingsPage?.({ id: 'settings', title: 'Hermes Agent Squads Hub', icon: 'organization', render: () => jsx(SettingsPage, {}) })

    window.__squadHub = { syncCards, treesOf, useOpen, usePreviews, Dialogs, TimelinePage, openCard, dismissBell, bellDismissedAtom, openTimeline, loadBoards, loadTimeline, setSide, newChat, atFolders, savePrefs, floatState, goNextPending, applyTheme: () => requestTheme?.('squads'), host, queryClient, refresh, refreshSoon, loadSnapshot, loadWorktrees, buildBotTree, visibleBots, prefsAtom, previewsAtom, reopenPreview }
    ctx.onDispose(() => {
      delete window.__squadHub
    })
  }
}
