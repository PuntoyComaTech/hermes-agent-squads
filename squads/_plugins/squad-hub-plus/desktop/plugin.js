// Hermes Agent Squads Hub Plus (key `squad-hub-plus`) — the repo-only companion of squad-hub.
//
// Hermes's plugin catalog only lists Desktop plugins that stay inside the plugin SDK, so squad-hub's
// catalog copy keeps the list, the panes and every SDK door it has. The features below need doors the
// SDK does not have yet, and they are not deleted: they live here, and `squadctl` installs this plugin
// beside squad-hub on every manager (never through the catalog).
//
//   * auto-hiding (floating) layout sides and their grips     -> NousResearch/hermes-agent#146514
//   * creating/removing git worktrees from a plugin           -> NousResearch/hermes-agent#146515
//   * a native multi-folder picker (ctx.os.pickOpenPath is one file) -> no directory mode
//   * the Kanban page's own board preselection (its localStorage slug + its menu)
//   * Desktop's Kanban plugin kept on for a manager's window (the SDK's pluginDecisions is read-only)
//
// Handshake with squad-hub: plain DOM events, no shared module, no shared storage.
// squad-hub dispatches `squad-hub:<action>` with a mutable `detail` and `cancelable: true`. This plugin
// calls `preventDefault()` when it took the action; squad-hub then uses its SDK fallback instead.
//   squad-hub:pick-folders    { id, title, defaultPath }      -> plus answers `squad-hub:folders-picked`
//   squad-hub:worktree-add    { folder, name, branch, base }  -> plus runs `git worktree add`
//   squad-hub:worktree-remove { folder, path }                -> plus runs `git worktree remove`
//   squad-hub:open-board      { slug, name }                  -> plus preselects the board
//   squad-hub:lane-chips      { folder, lanes }               -> plus answers with `squad-hub:lane-status`
// This plugin dispatches back:
//   squad-hub:folders-picked  { id, paths }                   -> the folders the user chose
//   squad-hub:lane-status     { folder, statuses }            -> squad-hub stores and renders the chips
//   squad-hub:lanes-changed   {}                              -> squad-hub refetches the lanes
//
// Single file by design: a disk plugin loads uncompiled and only resolves `@hermes/plugin-sdk`, `react`
// and `react/jsx-runtime`. The pure helpers between the MODEL markers are extracted and tested by
// tests/test_squad_hub_plus_host.py, which runs them under node.
import * as sdk from '@hermes/plugin-sdk'
import { Fragment as React_Fragment, useEffect, useMemo, useState, useSyncExternalStore } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

// ───────────────────────────── MODEL (pure) ─────────────────────────────
// Everything between the MODEL markers is plain JS with no imports: the repo's tests extract it and
// run it under node against the real layout payloads.
const trimPath = p => String(p || '').replace(/[/\\]+$/, '')
const baseName = p => trimPath(p).split(/[/\\]/).pop() || String(p || '')

function slugify(name) {
  return String(name || '')
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48)
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


/** This plugin's prefs, brought once to its defaults. A user who had squad-hub before the split keeps the
 *  choices those settings carried: they are read once from squad-hub's own storage key. */
const PREFS_VERSION = 1
const DEFAULT_PREFS = { floatSides: true, prefsVersion: PREFS_VERSION }
const LEGACY_PREFS_KEY = 'hermes.plugin.squad-hub.prefs'
function upgradePrefs(stored, defaults, legacy) {
  const base = stored || legacy || null
  const p = { ...defaults, floatSides: base && 'floatSides' in base ? base.floatSides !== false : defaults.floatSides }
  p.prefsVersion = PREFS_VERSION
  return p
}
// ─────────────────────────── END MODEL (pure) ───────────────────────────

// ───────────────────────────── host wiring ─────────────────────────────
const {
  host, atom, useValue, Button
} = sdk

const ID = 'squad-hub-plus'
const h = (type, props, ...kids) => {
  const { key, ...rest } = props || {}
  return jsxs(type, { ...rest, children: kids.flat(Infinity).filter(k => k !== null && k !== undefined && k !== false) }, key)
}

const MESSAGES = {
  en: {
    setup: 'Workspace',
    floatSides: 'Floating sides',
    floatSidesHint: 'The left list and the right files/terminal take no width: bring the pointer near a screen edge and they slide over the chat, then hide when you leave. The side buttons in the title bar dock them beside the chat.',
    layoutName: 'Squads layout', layoutHint: 'Squads left, chat in the middle, files over a short terminal on the right.',
    layoutPick: 'Pick “Squads” under Layout.', creditsBy: 'Made by', creditsPart: 'part of',
    cmdFloat: 'Squads: floating sides on/off', cmdPinLeft: 'Squads: pin or hide the left side',
    cmdPinRight: 'Squads: pin or hide the right side'
  },
  es: {
    setup: 'Espacio de trabajo',
    floatSides: 'Costados flotantes',
    floatSidesHint: 'La lista izquierda y los archivos/terminal de la derecha no ocupan ancho: acerca el puntero a un borde y se deslizan sobre el chat; al salir se ocultan. Los botones laterales de la barra de título los acoplan junto al chat.',
    layoutName: 'Layout Squads', layoutHint: 'Squads a la izquierda, el chat al centro, archivos sobre una terminal baja a la derecha.',
    layoutPick: 'Elige “Squads” en Layout.', creditsBy: 'Hecho por', creditsPart: 'parte de',
    cmdFloat: 'Squads: costados flotantes sí/no', cmdPinLeft: 'Squads: fijar u ocultar el costado izquierdo',
    cmdPinRight: 'Squads: fijar u ocultar el costado derecho'
  }
}
const fmt = (s, ...a) => String(s).replace(/\{(\d+)\}/g, (_, i) => a[i] ?? '')
let ctxRef = null
/** The plugin's strings in the app's own language, for code outside React. */
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
const useT = () => {
  const t = sdk.usePluginI18n(ID)
  return (k, ...a) => fmt(t(k), ...a)
}

// ───────────────────────────── state ─────────────────────────────
let storage = null
const prefsAtom = atom({ ...DEFAULT_PREFS })
const savePrefs = patch => {
  prefsAtom.set({ ...prefsAtom.get(), ...patch })
  storage?.set('prefs', prefsAtom.get())
  applyFloat()
}
const usePrefs = () => useValue(prefsAtom)

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

/** A floating side leaves the flow, so Desktop's own sash resizes a track the side no longer reads. Each shown side
 *  gets its own grip on its inner edge instead: dragging it sets the side's width (and a docked side's room in the
 *  row), kept across restarts. The grip is placed from the row's edge, never the panel's, so a slide in progress never
 *  misplaces it. */
const SIDE_MIN = 220
const clampSide = w => Math.round(Math.min(Math.max(w, SIDE_MIN), Math.min(900, (window.innerWidth || 1200) * 0.85)))
const grips = {}
let gripDrag = null
function placeGrip(side, el, root) {
  const grip = grips[side]
  if (!grip) return
  if (!el || !root) {
    if (!gripDrag || gripDrag.side !== side) grip.hidden = true
    return
  }
  const r = root.getBoundingClientRect()
  const w = parseFloat(el.style.getPropertyValue('--sqh-w')) || el.getBoundingClientRect().width
  grip.hidden = false
  grip.style.top = r.top + 'px'
  grip.style.height = (r.bottom - r.top) + 'px'
  grip.style.left = (side === 'left' ? r.left + w - 3 : r.right - w - 3) + 'px'
}
function makeGrip(side) {
  const grip = document.createElement('div')
  grip.dataset.sqhGrip = side
  grip.hidden = true
  grip.addEventListener('pointerdown', e => {
    if (e.button) return
    const el = document.querySelector(`[data-sqh-side="${side}"]`)
    const root = document.querySelector('[data-sqh-float-root]')
    if (!el || !root) return
    e.preventDefault()
    grip.setPointerCapture?.(e.pointerId)
    gripDrag = { side, el, root }
    document.documentElement.dataset.sqhResizing = ''
  })
  grip.addEventListener('pointermove', e => {
    if (gripDrag?.side !== side) return
    const r = gripDrag.root.getBoundingClientRect()
    const w = clampSide(side === 'left' ? e.clientX - r.left : r.right - e.clientX)
    gripDrag.el.style.setProperty('--sqh-w', w + 'px')
    if (floatState[side].pinned) gripDrag.root.style.setProperty(`--sqh-dock-${side}`, w + 'px')
    placeGrip(side, gripDrag.el, gripDrag.root)
  })
  const end = () => {
    if (gripDrag?.side !== side) return
    const w = parseFloat(gripDrag.el.style.getPropertyValue('--sqh-w'))
    if (w) storage?.set('sideWidths', { ...(storage?.get('sideWidths', {}) || {}), [side]: w })
    gripDrag = null
    delete document.documentElement.dataset.sqhResizing
    paintFloat()
  }
  grip.addEventListener('pointerup', end)
  grip.addEventListener('pointercancel', end)
  grip.addEventListener('dblclick', () => {
    // a double-click, like Desktop's sash, goes back to the default width
    const rest = { ...(storage?.get('sideWidths', {}) || {}) }
    delete rest[side]
    storage?.set('sideWidths', rest)
    const el = document.querySelector(`[data-sqh-side="${side}"]`)
    if (el) delete el.dataset.sqhSide // re-measured on the next paint
    paintFloat()
  })
  document.body.append(grip)
  grips[side] = grip
  return grip
}

/** Takes the docked widths off a row that no longer floats its sides. */
function undock(el) {
  delete el.dataset.sqhDockLeft
  delete el.dataset.sqhDockRight
  el.style.removeProperty('--sqh-dock-left')
  el.style.removeProperty('--sqh-dock-right')
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
    undock(el)
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
    // a pinned side is docked: the row gives it its width, so it sits beside the chat instead of over it
    const docked = Boolean(el && groups.length && st.pinned)
    if (!el || !groups.length) placeGrip(side, null, root)
    if (!docked) root.style.setProperty(`--sqh-dock-${side}`, '0px')
    if (docked) root.dataset[side === 'left' ? 'sqhDockLeft' : 'sqhDockRight'] = ''
    else delete root.dataset[side === 'left' ? 'sqhDockLeft' : 'sqhDockRight']
    if (!el || !groups.length) {
      st.groups = []
      const edge = document.querySelector(`[data-sqh-edge="${side}"]`)
      if (edge) edge.hidden = true
      continue
    }
    if (el.dataset.sqhSide !== side) {
      const w = storage?.get('sideWidths', {})?.[side] || Math.round(el.getBoundingClientRect().width)
      el.style.setProperty('--sqh-w', clampSide(Math.max(SIDE_MIN, w || 0)) + 'px')
      el.dataset.sqhSide = side
    }
    st.groups = groups
    // the docked room is the side's own width, never a measure taken while it slides
    if (docked) root.style.setProperty(`--sqh-dock-${side}`, el.style.getPropertyValue('--sqh-w') || Math.round(el.getBoundingClientRect().width) + 'px')
    const show = st.open || st.pinned
    if (show) el.dataset.sqhOpen = ''
    else delete el.dataset.sqhOpen
    // the edge strip only where this side floats hidden: never a dead band over a side that is shown or absent
    const edge = document.querySelector(`[data-sqh-edge="${side}"]`)
    if (edge) edge.hidden = show
    placeGrip(side, show ? el : null, root)
    // pane hosts sit outside the split tree: lift them with their side, and hide them with it so a closed side
    // can neither be focused off-screen nor shift the window
    for (const id of groups) rules.push(`[data-pane-host][data-tree-group="${cssEscape(id)}"]{z-index:46!important;background:var(--sidebar,var(--ui-bg-chrome,var(--background)));${show ? 'opacity:1;transition:opacity var(--sqh-in) ease!important;' : 'opacity:.35;visibility:hidden!important;transition:opacity var(--sqh-out) ease-in,visibility 0s linear var(--sqh-out)!important;'}}`)
    // Desktop's terminal is one fixed overlay chasing its slot (z-index 4), outside every pane host: the lifted host
    // covered it, so the terminal showed but took no keystroke. It rises and hides with the side that holds it.
    if (terminalIn(groups)) rules.push(`[data-persistent-terminal]{z-index:47!important;${show ? '' : 'visibility:hidden!important;pointer-events:none!important;'}}`)
  }
  const css = rules.join('\n')
  if (floatStyle && css !== floatCss) floatStyle.textContent = floatCss = css
  document.documentElement.dataset.sqhFloat = ''
}

/** Whether one of these zones shows Desktop's terminal (its active tab). */
const terminalIn = groups => groups.some(id => String(readLayouts().zones[id] || '').startsWith('terminal'))
/** The terminal overlay re-measures its slot on a window resize only; a side that slid in moved the slot without one,
 *  so the overlay stayed where the hidden side had been. */
let terminalTimer = null
function remeasureTerminal() {
  clearTimeout(terminalTimer)
  const fire = () => typeof Event === 'function' && window.dispatchEvent?.(new Event('resize'))
  fire()
  terminalTimer = setTimeout(fire, 320) // after the slide (--sqh-in is .26s)
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
  remeasureTerminal()
}

function onFloatPointer(e) {
  const x = e.clientX
  const y = e.clientY
  if (gripDrag) return
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
        if (focusInSide(side) || menuOpen() || gripDrag) return
        setSide(side, false)
      }, far ? FLOAT_HIDE_FAR_MS : FLOAT_HIDE_MS)
    }
  }
}

/** While floating, Desktop's own side toggles (the title-bar buttons, ⌘B, ⌘J) would fold the zone to its rail of
 *  vertical tab titles inside the floating panel. They dock or release the side instead (docked, it takes its width
 *  beside the chat); capture phase, so core's handler never runs. A zone already folded is unfolded, so a side always
 *  floats whole. */
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

/** Pin docks a side: shown, and the chat narrows to make room; a second toggle lets it float and hide again. */
function togglePin(side) {
  clearTimeout(floatTimers[side]) // a show/hide armed by the pointer must not undo the pin a moment later
  floatTimers[side] = null
  floatState[side].revealed = false
  floatState[side].pinned = !floatState[side].pinned
  floatState[side].open = floatState[side].pinned
  storage?.set('pinnedSides', { left: floatState.left.pinned, right: floatState.right.pinned })
  paintFloat()
  remeasureTerminal()
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
  const gripEls = ['left', 'right'].map(makeGrip)
  const timer = setInterval(whileVisible(paintFloat), 1200)
  const revealTimer = setInterval(whileVisible(watchReveals), 250)
  document.addEventListener('pointermove', onFloatPointer, { passive: true })
  document.addEventListener('keydown', onKey)
  document.addEventListener('focusin', onFloatFocus)
  for (const type of ['click', 'dblclick', 'pointerdown', 'mousedown']) document.addEventListener(type, onToggleClick, true)
  window.addEventListener('keydown', onToggleKey, true)
  const unfoldTimer = setTimeout(unfoldSides, 400)
  // a side the user docked stays docked across restarts, until the same button releases it
  const pinned = storage?.get('pinnedSides', null) || {}
  for (const side of ['left', 'right']) floatState[side].pinned = floatState[side].open = pinned[side] === true
  floatOff = () => {
    clearTimeout(unfoldTimer)
    for (const el of catchers) el.remove()
    for (const el of gripEls) el.remove()
    for (const k of Object.keys(grips)) delete grips[k]
    gripDrag = null
    delete document.documentElement.dataset.sqhResizing
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
    clearTimeout(terminalTimer)
    for (const k of Object.keys(floatNear)) delete floatNear[k]
    floatCss = ''
    for (const el of document.querySelectorAll('[data-sqh-main], [data-sqh-float-root]')) {
      delete el.dataset.sqhSolo
      delete el.dataset.sqhMain
      delete el.dataset.sqhFloatRoot
      undock(el)
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

/** The id of the layout squad-hub registers (`area: 'layouts'`): the picker applies it, Desktop persists it as the
 *  root split's id, and this watcher opens files and the terminal once when that happens. */
const SQUADS_LAYOUT = { id: 'sqh-root' }
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


// ───────────────────────────── the handshake ─────────────────────────────
/** Answer a `squad-hub:<action>` event. `can` is decided synchronously (squad-hub reads `defaultPrevented` as soon as
 *  the dispatch returns), so a capability check runs first and the work itself follows in a microtask: taking the
 *  action is a promise squad-hub can trust, and a plugin without the door leaves the event alone. */
function take(action, can, fn) {
  return ctxRef?.addEventListener(window, 'squad-hub:' + action, e => {
    const detail = e.detail || {}
    if (!can(detail)) return
    e.preventDefault()
    Promise.resolve()
      .then(() => fn(detail))
      .catch(err => host.notify({ kind: 'error', message: String(err?.message || err) }))
  })
}
const hasGit = door => Boolean(window.hermesDesktop?.git?.[door])
const announce = (action, detail = {}) => window.dispatchEvent(new CustomEvent('squad-hub:' + action, { detail }))

/** The native folder picker (multi-select, directories only): the SDK's pickOpenPath is one file. A native dialog
 *  cannot answer before the dispatch returns, so the folders come back as their own event, under the request id. */
async function pickFolders(detail) {
  const paths = await window.hermesDesktop.selectPaths({ title: detail.title, directories: true, multiple: true, defaultPath: detail.defaultPath })
  announce('folders-picked', { id: detail.id, paths: Array.isArray(paths) ? paths : [] })
  return true
}

async function worktreeAdd(detail) {
  const slug = slugify(detail.name)
  const res = await window.hermesDesktop.git.worktreeAdd(detail.folder, { name: slug, branch: String(detail.branch || '').trim() || undefined, base: detail.base || undefined })
  announce('lanes-changed')
  host.notify({ kind: 'success', message: 'Worktree ready: ' + (res?.branch || slug) })
  return true
}

async function worktreeRemove(detail) {
  await window.hermesDesktop.git.worktreeRemove(detail.folder, detail.path)
  announce('lanes-changed')
  return true
}

/** The Kanban page keeps the board it shows in its own storage and only offers a menu to change it: pick the board
 *  through that same menu (the page's own control) and store it for its next start. Never the server's current
 *  board, which every `hermes kanban` command without --board would then follow. */
const KANBAN_SLUG_KEY = 'hermes.plugin.kanban.boardSlug'
/** A manager works its squad on Desktop's Kanban page, a bundled plugin that ships off and that closing its tab
 *  switches off. Desktop reads this choice at launch: storing `kanban: true` makes the page there from the next start,
 *  every start, so nobody hunts for a switch. Other plugins' choices are kept as they are. */
const DECISIONS_KEY = 'hermes.desktop.pluginDecisions.v2'
function keepKanbanOn() {
  let d = {}
  try {
    d = JSON.parse(localStorage.getItem(DECISIONS_KEY) || '{}')
  } catch {
    d = {} // unreadable: Desktop itself would start from no choices
  }
  if (!d || typeof d !== 'object' || Array.isArray(d)) d = {}
  if (d.kanban === true) return false
  try {
    localStorage.setItem(DECISIONS_KEY, JSON.stringify({ ...d, kanban: true }))
  } catch {
    return false
  }
  return true
}
async function openBoard(detail) {
  const slug = String(detail.slug || '')
  const name = String(detail.name || slug)
  try {
    localStorage.setItem(KANBAN_SLUG_KEY, JSON.stringify(slug))
  } catch {
    /* a full quota is not a reason to lose the board */
  }
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 100))
    const trigger = [...document.querySelectorAll('button[aria-haspopup="menu"]')].find(b => b.querySelector('.codicon-project') && b.querySelector('.codicon-chevron-down'))
    if (!trigger) continue
    if (trigger.getAttribute('aria-label')?.endsWith(': ' + name)) return true
    trigger.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0, pointerType: 'mouse' }))
    for (let j = 0; j < 10; j++) {
      await new Promise(r => setTimeout(r, 50))
      const item = [...document.querySelectorAll('[role="menuitem"]')].find(el => el.textContent.trim().startsWith(name))
      if (item) {
        item.click()
        return true
      }
    }
    return true
  }
  return true
}

/** A lane's PR and local changes, quiet: nothing when there is nothing to say. */
function laneStatus(pr, repo) {
  const state = pr ? (pr.draft ? 'draft' : pr.state || 'open') : ''
  const url = /^https:\/\/[^/\s]+\//.test(String(pr?.url || '')) ? pr.url : ''
  return { pr: pr ? { number: pr.number, state, url, title: pr.title } : null, changed: repo?.changed || 0, ahead: repo?.ahead || 0, behind: repo?.behind || 0, known: Boolean(repo) }
}

/** Worktree chips: one `prList` per repo (GitHub, read-only) and one `repoStatus` per lane. squad-hub asks for them
 *  through `squad-hub:lane-chips` (it has no git door of its own) and renders what comes back. */
async function laneChips(detail) {
  const g = window.hermesDesktop.git
  const folder = String(detail.folder || '')
  const lanes = Array.isArray(detail.lanes) ? detail.lanes.filter(l => l && l.key) : []
  const branches = [...new Set(lanes.map(l => l.branch).filter(b => b && b !== 'main' && b !== 'master'))]
  let prs = []
  try {
    prs = branches.length && g.review?.prList ? (await g.review.prList(folder, branches)).prs || [] : []
  } catch {
    prs = []
  }
  const statuses = {}
  await Promise.all(
    lanes.map(async l => {
      let st = null
      try {
        st = g.repoStatus ? await g.repoStatus(l.path || folder) : null
      } catch {
        st = null
      }
      statuses[l.key] = laneStatus(prs.find(p => p.branch === l.branch) || null, st)
    })
  )
  announce('lane-status', { folder, statuses })
  return true
}

// ───────────────────────────── settings ─────────────────────────────
/** A plugin registers a layout but cannot apply one (only the picker and set_theme do): take the user to the picker. */
function applySquadsLayout() {
  host.navigate('/settings?tab=appearance&page=window-layout')
  host.notify({ kind: 'info', message: fmt(lang().layoutPick) })
}

function SettingsPage() {
  const t = useT()
  const prefs = usePrefs()
  return h(
    'div',
    {},
    h('div', { className: 'sqhp-hint', style: { padding: '14px 0 4px' } }, t('setup')),
    jsx(sdk.ToggleRow, { checked: prefs.floatSides !== false, label: t('floatSides'), description: t('floatSidesHint'), onChange: on => savePrefs({ floatSides: on }) }),
    h('div', { style: { display: 'flex', alignItems: 'center', gap: 12, padding: '6px 0' } }, h('div', { style: { flex: 1 } }, h('div', { style: { color: 'var(--foreground)', fontWeight: 500 } }, t('layoutName')), h('div', { className: 'sqhp-hint' }, t('layoutHint'))), jsx(Button, { variant: 'outline', onClick: applySquadsLayout, children: t('layoutPick') })),
    h('div', { className: 'sqhp-credits' }, h('span', { className: 'sqhp-hint' }, t('creditsBy') + ' PuntoyComaTech · ' + t('creditsPart') + ' Hermes Agent Squads'))
  )
}

const FLOAT_CSS = `html[data-sqh-float] [data-sqh-float-root]{position:relative;padding-left:var(--sqh-dock-left,0px);padding-right:var(--sqh-dock-right,0px);transition:padding var(--sqh-in) var(--sqh-ease-in)}
html[data-sqh-float] [data-sqh-dock-left]>[data-sqh-main]{padding-left:0}
html[data-sqh-float] [data-sqh-dock-right]>[data-sqh-main]{padding-right:0}
html[data-sqh-float] [data-sqh-dock-left]>[data-sqh-side=left],html[data-sqh-float] [data-sqh-dock-right]>[data-sqh-side=right]{box-shadow:none}
html[data-sqh-float] [data-sqh-main]{padding:0 calc(var(--sqh-gutter,40px) - 10px)}
html[data-sqh-float] [data-sqh-main][data-sqh-solo]{flex:1 1 0%!important}
html[data-sqh-float] [data-sqh-side]{position:absolute!important;top:0;bottom:0;z-index:45;width:var(--sqh-w)!important;min-width:0!important;max-width:min(var(--sqh-w),85vw)!important;flex:none!important;background:var(--sidebar,var(--ui-bg-chrome,var(--background)));transition:transform var(--sqh-in) var(--sqh-ease-in),opacity var(--sqh-in) ease;will-change:transform,opacity;box-shadow:0 18px 50px -12px color-mix(in srgb,black 45%,transparent)}
html[data-sqh-float] [data-sqh-side="left"]{left:0;transform:translateX(-100%);border-right:1px solid var(--ui-stroke-secondary,var(--border))}
html[data-sqh-float] [data-sqh-side="right"]{right:0;transform:translateX(100%);border-left:1px solid var(--ui-stroke-secondary,var(--border))}
html[data-sqh-float]{--sqh-in:.26s;--sqh-out:.17s;--sqh-ease-in:cubic-bezier(.22,1,.36,1);--sqh-ease-out:cubic-bezier(.4,0,.9,.6)}
html[data-sqh-float] [data-sqh-side]:not([data-sqh-open]){visibility:hidden;opacity:.35;transition:transform var(--sqh-out) var(--sqh-ease-out),opacity var(--sqh-out) ease-in,visibility 0s linear var(--sqh-out)}
html[data-sqh-float] [data-sqh-side][data-sqh-open]{transform:none;opacity:1}
[data-sqh-grip]{position:fixed;width:6px;z-index:47;cursor:col-resize;background:transparent;transition:background .15s}
[data-sqh-grip]:hover,html[data-sqh-resizing] [data-sqh-grip]{background:color-mix(in srgb,var(--ui-accent,currentColor) 35%,transparent)}
[data-sqh-grip][hidden]{display:none}
html[data-sqh-resizing],html[data-sqh-resizing] *{cursor:col-resize!important;user-select:none!important}
html[data-sqh-resizing] [data-sqh-side],html[data-sqh-resizing] [data-sqh-float-root]{transition:none!important}
[data-sqh-edge]{position:fixed;top:40px;bottom:28px;width:4px;z-index:44;background:transparent}
[data-sqh-edge=left]{left:0}
[data-sqh-edge=right]{right:0}
[data-sqh-edge][hidden]{display:none}
@media (prefers-reduced-motion:reduce){html[data-sqh-float]{--sqh-in:.01s;--sqh-out:.01s}}`
const CSS = FLOAT_CSS + `
.sqhp-hint{font-size:.75rem;color:var(--ui-text-tertiary)}
.sqhp-credits{margin-top:22px;padding-top:12px;border-top:1px solid var(--ui-stroke-tertiary,var(--border));display:grid;gap:6px}
`

/** Module state that belongs to one enabled run: switching the plugin off and on again runs register() again on
 *  this same module, and nothing noted by the previous run may read as news. */
function resetRun() {
  lastRoot = ''
  layoutSig = undefined
  layoutRead = { trees: [], zones: {} }
}

export default {
  id: ID,
  name: 'Squads Hub Plus',
  description: 'Repo-only companion of squad-hub: floating sides, worktrees, the folder picker, the Kanban board preselection and Kanban kept on — the features the catalog SDK cannot express.',
  defaultEnabled: true,
  register(ctx) {
    resetRun()
    ctxRef = ctx
    storage = ctx.storage
    ctx.i18n?.register?.(MESSAGES)
    let legacy = null
    try {
      legacy = JSON.parse(localStorage.getItem(LEGACY_PREFS_KEY) || 'null')
    } catch {
      legacy = null
    }
    keepKanbanOn()
    // closing the Kanban tab stores `kanban: false` mid-session; store it back once Desktop has written (it sets the
    // atom first, then localStorage), so the next start has the board again
    let kanbanTimer = null
    const offKanban = host?.pluginDecisions?.listen?.(d => {
      if (d?.kanban === true) return
      clearTimeout(kanbanTimer)
      kanbanTimer = setTimeout(keepKanbanOn, 0)
    })
    ctx.onDispose(() => (clearTimeout(kanbanTimer), offKanban?.()))
    prefsAtom.set(upgradePrefs(ctx.storage.get('prefs', null), DEFAULT_PREFS, legacy))
    ctx.storage.set('prefs', prefsAtom.get())

    const styleEl = document.createElement('style')
    styleEl.dataset.squadHubPlus = 'ui'
    styleEl.textContent = CSS
    document.head.append(styleEl)
    ctx.onDispose(() => {
      styleEl.remove()
      ctxRef = null
    })
    ctx.onDispose(stopFloat)
    applyFloat()

    const pickTimer = ctx.setInterval(whileVisible(watchLayoutPick), 1000)
    ctx.onDispose(() => {
      clearTimeout(pickRevealTimer)
      pickTimer?.()
    })

    // the floating-side commands moved here with the feature: same ids, same keys, so a rebind still finds them
    ctx.registerMany([
      { id: 'cmd-float', area: sdk.PALETTE_AREA, data: { id: 'squad-hub.float', label: MESSAGES.en.cmdFloat, keywords: ['float', 'auto hide', 'sidebar', 'dock'], run: () => savePrefs({ floatSides: prefsAtom.get().floatSides === false }) } },
      { id: 'cmd-pin-left', area: sdk.PALETTE_AREA, data: { id: 'squad-hub.pin-left', label: MESSAGES.en.cmdPinLeft, keywords: ['pin', 'sidebar', 'left', 'float'], run: () => pinSide('left') } },
      { id: 'cmd-pin-right', area: sdk.PALETTE_AREA, data: { id: 'squad-hub.pin-right', label: MESSAGES.en.cmdPinRight, keywords: ['pin', 'files', 'terminal', 'right', 'float'], run: () => pinSide('right') } },
      { id: 'key-pin-left', area: sdk.KEYBINDS_AREA, data: { id: 'squad-hub.pin-left', label: MESSAGES.en.cmdPinLeft, category: 'view', defaults: [], run: () => pinSide('left') } },
      { id: 'key-pin-right', area: sdk.KEYBINDS_AREA, data: { id: 'squad-hub.pin-right', label: MESSAGES.en.cmdPinRight, category: 'view', defaults: [], run: () => pinSide('right') } }
    ])
    ctx.registerSettingsPage?.({ id: 'settings', title: 'Squads Hub Plus', icon: 'organization', render: () => jsx(SettingsPage, {}) })

    take('pick-folders', () => Boolean(window.hermesDesktop?.selectPaths), pickFolders)
    take('worktree-add', d => hasGit('worktreeAdd') && d.folder && slugify(d.name), worktreeAdd)
    take('worktree-remove', d => hasGit('worktreeRemove') && d.folder && d.path, worktreeRemove)
    take('open-board', d => Boolean(d.slug), openBoard)
    take('lane-chips', d => hasGit('repoStatus') && d.folder && Array.isArray(d.lanes) && d.lanes.length > 0, laneChips)
  }
}
