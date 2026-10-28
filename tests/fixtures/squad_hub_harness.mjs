// Runs the real squads/_plugins/squad-hub/desktop/plugin.js against a fake Hermes Desktop host.
//
// The fakes follow the Desktop contracts the plugin relies on: nanostores-style atoms (`get`, `set`, `listen`),
// `ctx.onEvent` / `ctx.onDispose` / `ctx.register` that hand back a disposer, gateway events shaped like the ones the
// gateway emits (`{ type, session_id, payload }`), a virtual clock for setTimeout / setInterval, and a document that
// counts the listeners and <style> tags the plugin leaves behind. Nothing here renders React: the plugin's register()
// wiring is what runs.
import { pathToFileURL } from 'node:url'

export function atom(initial) {
  let value = initial
  const listeners = new Set()
  return {
    get: () => value,
    set(next) {
      if (Object.is(next, value)) return
      const old = value
      value = next
      for (const fn of [...listeners]) fn(value, old)
    },
    listen(fn) {
      listeners.add(fn)
      return () => listeners.delete(fn)
    },
    subscribe(fn) {
      fn(value)
      return this.listen(fn)
    },
    listeners: () => listeners.size
  }
}

// addEventListener's third argument: a boolean, or an options object whose `capture` field counts
const capturing = opts => (opts && typeof opts === 'object' ? Boolean(opts.capture) : Boolean(opts))

function clock() {
  let now = 0
  let seq = 0
  const timers = new Map()
  const add = (fn, ms, every) => {
    const id = ++seq
    timers.set(id, { fn, at: now + Math.max(0, ms || 0), every: every ? Math.max(1, ms) : 0 })
    return id
  }
  return {
    setTimeout: (fn, ms) => add(fn, ms, false),
    setInterval: (fn, ms) => add(fn, ms, true),
    clear: id => void timers.delete(id),
    pending: () => timers.size,
    elapsed: () => now,
    advance(ms) {
      const end = now + ms
      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= end).sort((a, b) => a[1].at - b[1].at || a[0] - b[0])[0]
        if (!due) break
        const [id, t] = due
        now = t.at
        if (t.every) t.at += t.every
        else timers.delete(id)
        t.fn()
      }
      now = end
    }
  }
}

export async function boot({ pluginPath, stored = {}, local = {}, hidden = false, kanbanBadges = true } = {}) {
  const time = clock()
  const realNow = Date.now()
  Date.now = () => realNow + time.elapsed()
  globalThis.setTimeout = time.setTimeout
  globalThis.setInterval = time.setInterval
  globalThis.clearTimeout = id => time.clear(id)
  globalThis.clearInterval = id => time.clear(id)

  // ---- DOM: only what the plugin touches outside React
  const dom = { preview: false, root: '', hidden }
  const docListeners = []
  const styles = []
  const created = []
  const doc = {
    get hidden() { return dom.hidden },
    documentElement: { dataset: {} },
    head: { append: (...els) => els.forEach(el => ((el.attached = true), styles.push(el))) },
    createElement: tag => {
      const el = { tag, dataset: {}, style: { removeProperty() {} }, textContent: '', attached: false, hidden: false, on: {}, remove() { this.attached = false },
        addEventListener(type, fn) { (el.on[type] ||= []).push(fn) },
        setPointerCapture() {},
        fire(type, e = {}) { for (const fn of el.on[type] || []) fn({ type, ...e }) } }
      el.style = { removeProperty() {} }
      created.push(el)
      return el
    },
    addEventListener: (type, fn, capture) => docListeners.push({ target: 'document', type, fn, capture: capturing(capture) }),
    removeEventListener(type, fn, capture) {
      const i = docListeners.findIndex(l => l.target === 'document' && l.type === type && l.fn === fn && l.capture === capturing(capture))
      if (i >= 0) docListeners.splice(i, 1)
    },
    // `dom.preview`: Desktop shows a preview tab right now; `dom.root`: the layout tree's root split id
    querySelector(sel) {
      if (dom.preview && String(sel).includes('preview-tile:')) return {}
      if (dom.root && String(sel) === '[data-tree-split]') return { getAttribute: () => dom.root }
      return null
    },
    querySelectorAll: () => [],
    hasFocus: () => true,
    activeElement: null,
    body: { append: (...els) => els.forEach(el => ((el.attached = true), styles.push(el))) }
  }
  const win = {
    CSS: undefined,
    innerWidth: 1200,
    addEventListener: (type, fn, capture) => docListeners.push({ target: 'window', type, fn, capture: capturing(capture) }),
    removeEventListener(type, fn, capture) {
      const i = docListeners.findIndex(l => l.target === 'window' && l.type === type && l.fn === fn && l.capture === capturing(capture))
      if (i >= 0) docListeners.splice(i, 1)
    },
    hermesDesktop: { git: null, api: async () => ({}) }
  }
  const ls = new Map(Object.entries(local))
  globalThis.document = doc
  globalThis.window = win
  globalThis.localStorage = { getItem: k => (ls.has(k) ? ls.get(k) : null), setItem: (k, v) => ls.set(k, String(v)), removeItem: k => ls.delete(k) }
  globalThis.getComputedStyle = () => ({ flexDirection: 'row' })
  win.localStorage = globalThis.localStorage

  // ---- Desktop host
  const state = {
    focusedSessionId: atom(null),
    focusedStoredSessionId: atom(null),
    busyBySession: atom({}),
    profile: atom('default')
  }
  const dispatched = []
  const revealed = []
  const calls = []
  const notices = []
  const queries = new Map()
  const host = {
    state,
    request: async (method, params) => (calls.push({ via: 'primary', method, params }), {}),
    requestProfile: async (bot, method, params) => {
      calls.push({ via: bot, method, params })
      if (world.failProfile.has(bot)) throw new Error('plugin not found')
      return {}
    },
    // the real hub fans a dispatched event out to every listener, the plugin's own ctx.onEvent ones included
    getGateway: () => ({ events: { dispatch: e => (dispatched.push(e), deliver(e)) } }),
    notify: n => notices.push(n),
    notifyError: e => notices.push({ kind: 'error', message: String(e?.message || e) }),
    openSession: async () => {},
    revealPane: pane => revealed.push(pane),
    navigate: () => {},
    ensureAgent: async () => {},
    pluginDecisions: atom({})
  }
  const sdk = {
    host,
    atom,
    useValue: a => a?.get?.(),
    // a test answers the queries a component asks for: globalThis.__SQH_QUERIES__ = options => ({ data })
    useQuery: options => globalThis.__SQH_QUERIES__?.(options) || {},
    queryClient: {
      invalidateQueries: ({ queryKey }) => calls.push({ via: 'query', method: 'invalidate', params: queryKey }),
      getQueryData: key => queries.get(JSON.stringify(key)),
      getQueriesData: () => [],
      getQueryState: () => undefined,
      getQueryCache: () => ({ subscribe: () => () => {} }),
      fetchQuery: async () => ({})
    },
    usePluginI18n: () => k => k,
    STATUSBAR_AREAS: { left: 'statusbar.left', right: 'statusbar.right' },
    PALETTE_AREA: 'palette',
    KEYBINDS_AREA: 'keybinds',
    THEMES_AREA: 'themes',
    COMPOSER_AREAS: { atCompletions: 'at' },
    SIDEBAR_NAV_PREFS_AREA: 'nav-prefs',
    TRANSCRIPT_DIRECTIVE_AREA: 'directive',
    CHAT_EMPTY_AREA: 'empty',
    TITLEBAR_AREAS: { right: 'titleBar.right' },
    ...(!kanbanBadges ? {} : { KANBAN_CARD_AREAS: { badges: 'kanban.card.badges' } }),
    requestTheme: () => {}
  }
  globalThis.__SQH_SDK__ = sdk

  // ---- plugin context: records what register() takes and hands every disposer back
  const disposers = []
  const listeners = new Map()
  const registered = []
  const store = new Map(Object.entries(stored))
  const ctx = {
    storage: {
      get: (k, d) => (store.has(k) ? JSON.parse(store.get(k)) : d),
      set: (k, v) => void store.set(k, JSON.stringify(v))
    },
    i18n: { register: messages => (world.messages = messages), t: k => k },
    register(c) {
      registered.push(c)
      const dispose = () => void registered.splice(registered.indexOf(c), 1)
      disposers.push(dispose)
      return dispose
    },
    registerMany(cs) {
      cs.forEach(c => ctx.register(c))
    },
    registerSettingsPage() {},
    onDispose: fn => void disposers.push(fn),
    onEvent(type, fn) {
      const set = listeners.get(type) || new Set()
      set.add(fn)
      listeners.set(type, set)
      const dispose = () => set.delete(fn)
      disposers.push(dispose)
      return dispose
    },
    runAction() {},
    os: {}
  }

  const deliver = e => {
    for (const fn of [...(listeners.get(e.type) || [])]) fn(e)
  }
  const mod = await import(pathToFileURL(pluginPath).href)
  const world = {
    messages: null, host, ctx, state, dom, queries, revealed, dispatched, calls, notices, store, localStorage: ls, failProfile: new Set(), time,
    plugin: mod.default,
    register() {
      mod.default.register(ctx)
    },
    dispose() {
      while (disposers.length) disposers.pop()()
    },
    /** A gateway event, delivered the way ctx.onEvent listeners hear it. */
    emit(type, session_id, payload = {}) {
      deliver({ type, session_id, payload })
    },
    /** Desktop moving focus: stored id first, then the runtime id behind it (they are two atoms). */
    focus(storedId, runtimeId) {
      state.focusedStoredSessionId.set(storedId)
      if (runtimeId !== undefined) state.focusedSessionId.set(runtimeId)
    },
    /** A registered contribution by its plugin-local id (palette command, keybinding, pane…). */
    contribution: id => registered.find(c => c.id === id),
    /** The resize grips the plugin placed on the page, attached ones only. */
    grips: () => created.filter(el => el.attached && 'sqhGrip' in el.dataset),
    /** A DOM event as the document hears it, capture listeners first; returns whether a listener stopped it. */
    fire(type, event) {
      let stopped = false
      const e = { type, ...event, stopPropagation: () => (stopped = true), preventDefault() {} }
      for (const l of [...docListeners].sort((x, y) => y.capture - x.capture)) {
        if (l.type !== type) continue
        if (stopped) break
        l.fn(e)
      }
      return stopped
    },
    previews: () => JSON.parse(store.get('previews') || '{}'),
    leftBehind: () => ({
      listeners: docListeners.map(l => `${l.target}:${l.type}${l.capture ? ':capture' : ''}`),
      timers: time.pending(),
      styles: styles.filter(s => s.attached).length,
      registered: registered.length,
      eventListeners: [...listeners.values()].reduce((n, s) => n + s.size, 0),
      atomListeners: Object.values(state).reduce((n, a) => n + (a.listeners?.() || 0), 0),
      global: Boolean(win.__squadHub)
    }),
    exports: () => win.__squadHub
  }
  return world
}
