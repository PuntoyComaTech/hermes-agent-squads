"""Squad Hub desktop plugin: the register() wiring, run for real.

`squads/_plugins/squad-hub/desktop/plugin.js` is loaded under node against a fake Hermes Desktop host
(`tests/fixtures/squad_hub_harness.mjs`): atoms, `ctx.onEvent` / `ctx.onDispose`, gateway events shaped like the real
ones (`{type, session_id, payload}`), a virtual clock and a document that counts the listeners and <style> tags left
behind. Each case plays what a user does (switch chats, a bot opens a preview, the plugin is switched off and on) and
reads what the plugin did to the host."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "squads" / "_plugins" / "squad-hub" / "desktop" / "plugin.js"
HARNESS = REPO / "tests" / "fixtures" / "squad_hub_harness.mjs"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is needed to run the plugin")

PRELUDE = """
import { boot } from './harness.mjs'
const w = await boot({ pluginPath: new URL('./plugin.mjs', import.meta.url).pathname })
const out = {}
"""


@pytest.fixture(scope="module")
def desk(tmp_path_factory):
    """A directory holding the plugin with the three modules it imports stubbed, and a runner for scenarios."""
    d = tmp_path_factory.mktemp("squad-hub-host")
    text = PLUGIN.read_text(encoding="utf-8")
    wiring = text[text.index("// ───────────────────────────── host wiring"):]
    sdk_names = re.search(r"const \{([^}]*)\} = sdk", wiring).group(1)
    names = [n.strip() for n in sdk_names.split(",") if n.strip()] + ["TITLEBAR_AREAS"]
    (d / "plugin.mjs").write_text(text, encoding="utf-8")
    (d / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    stubs = {
        ("@hermes/plugin-sdk", "index.js"): "const s = globalThis.__SQH_SDK__\n" + "".join(f"export const {n} = s.{n}\n" for n in names),
        ("react", "index.js"): "export const Fragment = Symbol('fragment')\nexport const useEffect = () => {}\n"
                               "export const useMemo = f => f()\nexport const useState = v => [v, () => {}]\n"
                               "export const useSyncExternalStore = (sub, get) => ((globalThis.__SQH_SUBS__ ||= []).push(sub), get())\n",
        ("react", "jsx-runtime.js"): "export const jsx = (type, props, key) => ({ type, props, key })\nexport const jsxs = jsx\n",
    }
    for (pkg, name), body in stubs.items():
        (d / "node_modules" / pkg).mkdir(parents=True, exist_ok=True)
        (d / "node_modules" / pkg / name).write_text(body, encoding="utf-8")
    for pkg in ("@hermes/plugin-sdk", "react"):
        exports = {".": "./index.js", "./jsx-runtime": "./jsx-runtime.js"}
        (d / "node_modules" / pkg / "package.json").write_text(json.dumps({"type": "module", "exports": exports}), encoding="utf-8")
    shutil.copy(HARNESS, d / "harness.mjs")

    def run(scenario: str):
        (d / "scenario.mjs").write_text(PRELUDE + scenario + "\nconsole.log(JSON.stringify(out))\n", encoding="utf-8")
        done = subprocess.run([NODE, "scenario.mjs"], cwd=d, capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout.strip().splitlines()[-1])
    return run


CHAT_A, CHAT_B = "20261025_011740_e8a885", "20261025_093012_7c41d0"
URL = "http://localhost:4321"


# ---- the user report: previews "come back" every time a chat is entered ------------------------------------

def test_coming_back_to_a_chat_never_opens_a_preview_on_its_own(desk):
    """The chat showed a preview, the user went to another chat and came back; Desktop kept the tab in a bucket that
    is not in view, so the pane is empty on return. Dispatching a synthetic `preview.open` there lands in whatever
    bucket is in view and stacks another tab on every visit: the plugin must dispatch nothing by itself."""
    got = desk(f"""
w.register()
w.focus('{CHAT_A}', 'rt-a')
w.emit('session.info', 'rt-a', {{ stored_session_id: '{CHAT_A}' }})
w.emit('preview.open', 'rt-a', {{ url: '{URL}', label: '' }})
w.dom.preview = true                       // the preview is on screen while the user leaves
w.focus('{CHAT_B}', 'rt-b')
w.dom.preview = false                      // the other chat shows none
w.time.advance(3000)
w.focus('{CHAT_A}', 'rt-a')                // back: Desktop shows no preview for it
w.time.advance(3000)
for (let i = 0; i < 3; i++) {{ w.focus('{CHAT_B}', 'rt-b'); w.time.advance(900); w.focus('{CHAT_A}', 'rt-a'); w.time.advance(900) }}
out.dispatched = w.dispatched
out.remembered = w.previews()['{CHAT_A}'].map(p => p.url)
""")
    assert got["dispatched"] == [], "the plugin reopened a preview nobody asked for"
    assert got["remembered"] == [URL], "the preview stays remembered for the one-click reopen"


def test_the_one_click_reopen_dispatches_once_and_does_not_re_remember_it(desk):
    got = desk(f"""
w.register()
w.focus('{CHAT_A}', 'rt-a')
w.emit('session.info', 'rt-a', {{ stored_session_id: '{CHAT_A}' }})
w.emit('preview.open', 'rt-a', {{ url: '/tmp/older.html' }})
w.time.advance(5000)
w.emit('preview.open', 'rt-a', {{ url: '{URL}', label: 'site' }})
w.time.advance(5000)
const before = JSON.stringify(w.previews())
w.contribution('cmd-preview').data.run()   // reopens the newest one
out.dispatched = [...w.dispatched]
out.unchanged = JSON.stringify(w.previews()) === before
out.notices = w.notices
w.time.advance(5000)
w.exports().reopenPreview(w.previews()['{CHAT_A}'][1])       // the older one, from the chat's menu
out.afterMenu = w.dispatched.length
out.orderKept = JSON.stringify(w.previews()) === before
""")
    assert got["dispatched"] == [{"type": "preview.open", "payload": {"url": URL, "label": "site"}}]
    assert got["unchanged"], "a reopen is the app's own handler; the plugin must not add another entry for it"
    assert got["notices"] == [] and got["afterMenu"] == 2
    assert got["orderKept"], "reopening the older preview must not move it to the front of the remembered list"


def test_the_reopen_shortcut_and_the_palette_command_do_the_same(desk):
    got = desk(f"""
w.register()
w.focus('{CHAT_A}', 'rt-a')
w.emit('session.info', 'rt-a', {{ stored_session_id: '{CHAT_A}' }})
w.focus('{CHAT_B}', 'rt-b')                // nothing remembered for this chat
w.contribution('cmd-preview').data.run()
w.contribution('key-preview').data.run()
out.silent = w.dispatched.length
out.told = w.notices.map(n => n.kind)
w.emit('preview.open', 'rt-zzz', {{ url: '{URL}' }})  // a runtime no event or focus ever named: not remembered
out.unknown = Object.keys(w.previews())
w.emit('session.info', 'rt-b', {{ stored_session_id: '{CHAT_B}' }})
w.emit('preview.open', 'rt-b', {{ url: '{URL}' }})
w.contribution('key-preview').data.run()
out.fromKey = w.dispatched.length
""")
    assert got["silent"] == 0 and got["told"] == ["info", "info"], "both entries say there is nothing to reopen"
    assert got["unknown"] == [], "a preview from a runtime the plugin cannot name is not guessed into a chat"
    assert got["fromKey"] == 1


# ---- previews are filed under the chat that ran the tool -----------------------------------------------------

def test_a_preview_is_remembered_for_the_chat_that_opened_it_not_the_one_in_view(desk):
    got = desk(f"""
w.register()
w.focus('{CHAT_A}', 'rt-a')
w.emit('session.info', 'rt-a', {{ stored_session_id: '{CHAT_A}' }})
w.focus('{CHAT_B}', 'rt-b')
w.emit('session.info', 'rt-b', {{ stored_session_id: '{CHAT_B}' }})
w.emit('preview.open', 'rt-a', {{ url: '{URL}', label: ' site ' }})        // chat A's turn finishes while B is in view
w.emit('preview.open', 'rt-a', {{ url: '   ', label: '' }})                // an empty url is nothing
w.emit('preview.open', 'rt-a', {{ url: '{URL}', label: 'again' }})         // the same url moves to the front once
w.emit('preview.open', 'rt-a', {{ url: '/tmp/page.html', label: '' }})
out.previews = Object.fromEntries(Object.entries(w.previews()).map(([k, v]) => [k, v.map(p => [p.url, p.label])]))
""")
    assert got["previews"] == {CHAT_A: [["/tmp/page.html", ""], [URL, "again"]]}


def test_a_session_info_naming_only_a_session_key_still_binds_the_runtime(desk):
    got = desk(f"""
w.register()
w.emit('session.info', 'rt-x', {{ session_key: '{CHAT_B}' }})
w.emit('preview.open', 'rt-x', {{ url: '{URL}' }})
out.keys = Object.keys(w.previews())
""")
    assert got["keys"] == [CHAT_B]


def test_a_compressed_chat_keeps_the_previews_it_had_under_its_new_id(desk):
    """Compression moves a conversation to a new stored id (`session.info` carries it); Desktop re-keys its tabs, so
    the remembered previews must follow or the chip of the very same chat turns empty."""
    new_id = "20261025_093012_zz9999"
    got = desk(f"""
w.register()
w.focus('{CHAT_A}', 'rt-a')
w.emit('session.info', 'rt-a', {{ stored_session_id: '{CHAT_A}' }})
w.emit('preview.open', 'rt-a', {{ url: '{URL}', label: 'site' }})
w.emit('session.info', 'rt-a', {{ stored_session_id: '{new_id}' }})
w.emit('preview.open', 'rt-a', {{ url: '/tmp/page.html' }})
out.previews = Object.fromEntries(Object.entries(w.previews()).map(([k, v]) => [k, v.map(p => p.url)]))
""")
    assert got["previews"] == {new_id: ["/tmp/page.html", URL]}


def test_focus_moving_one_atom_at_a_time_does_not_move_a_runtime_to_the_wrong_chat(desk):
    """Desktop updates the stored id and the runtime id of the focused chat as two atoms, one after the other. Reading
    the pair in between pairs the chat just entered with the runtime of the chat just left."""
    got = desk(f"""
w.register()
w.focus('{CHAT_A}', 'rt-a')
w.emit('session.info', 'rt-a', {{ stored_session_id: '{CHAT_A}' }})
w.focus('{CHAT_B}')                        // the stored id flips first; the runtime atom still says rt-a
w.emit('preview.open', 'rt-a', {{ url: '{URL}' }})   // chat A's turn opens a preview in that gap
out.previews = Object.keys(w.previews())
""")
    assert got["previews"] == [CHAT_A]


# ---- disposing leaves nothing behind -------------------------------------------------------------------------

def test_disposing_the_plugin_removes_every_listener_timer_style_and_global(desk):
    got = desk(f"""
const empty = w.leftBehind()
w.register()
out.running = w.leftBehind()
w.focus('{CHAT_A}', 'rt-a')                // arms a delayed refresh
w.emit('session.info', 'rt-a', {{ stored_session_id: '{CHAT_A}' }})
w.dispose()
out.after = w.leftBehind()
const before = w.calls.length
w.time.advance(60000)
out.latecomers = w.calls.slice(before)
out.empty = empty
""")
    assert got["running"]["listeners"] and got["running"]["styles"] and got["running"]["timers"], "the plugin did start"
    assert got["after"] == got["empty"], got["after"]
    assert got["latecomers"] == [], "a delayed refresh fired after the plugin was disposed"


def test_switching_the_plugin_off_and_on_again_starts_clean(desk):
    """Disable then enable runs register() again on the same module: what the first run noted about the layout must
    not read as a change the user just made."""
    got = desk("""
w.dom.root = 'default-layout'
w.register()
w.time.advance(1000)                       // the layout poll notes the root split
w.dispose()
w.dom.root = 'sqh-root'                    // the layout changed while the plugin was off
w.register()
w.time.advance(1000)
out.revealed = w.revealed
""")
    assert got["revealed"] == [], "the Squads layout was already there; nothing was picked"


def test_picking_the_squads_layout_opens_files_then_the_terminal_once(desk):
    got = desk("""
w.dom.root = 'default-layout'
w.register()
w.time.advance(1000)
w.dom.root = 'sqh-root'
w.time.advance(1000)
w.time.advance(500)
w.time.advance(5000)
out.revealed = w.revealed
""")
    assert got["revealed"] == ["files", "terminal"]


# ---- Desktop's side buttons dock a floating side ----------------------------------------------------------------

# A row as Desktop renders it: the Squads list, the chat, then files over the terminal; the right title-bar button.
ROW = r"""
const el = (attrs = {}, kids = [], width = 0) => {
  const node = { attrs, children: kids, dataset: {}, vars: {}, parentElement: null,
    style: { setProperty: (k, v) => (node.vars[k] = v), removeProperty: k => delete node.vars[k], getPropertyValue: k => node.vars[k] || '' },
    getAttribute: k => attrs[k] ?? null,
    getBoundingClientRect: () => ({ width, left: 0, right: 1400, top: 0, bottom: 900 }),
    contains: x => x === node || kids.some(k => k.contains(x)),
    all: () => [node, ...kids.flatMap(k => k.all())],
    querySelectorAll: sel => (sel === '[data-tree-group]' ? node.all().slice(1).filter(n => 'data-tree-group' in n.attrs) : []),
    closest(sel) {
      const key = sel.match(/\[([a-z-]+)/)[1]
      for (let n = node; n; n = n.parentElement) if (key in n.attrs) return n
      return null
    } }
  for (const k of kids) k.parentElement = node
  return node
}
const tab = el({ 'data-tree-tab': 'workspace' })
const chat = el({ 'data-tree-group': 'sqh-main' }, [tab], 800)
const left = el({}, [el({ 'data-tree-group': 'sqh-left' })], 280)
const right = el({}, [el({ 'data-tree-group': 'sqh-files' }), el({ 'data-tree-group': 'sqh-term' })], 340)
const row = el({ 'data-tree-split': 'sqh-root' }, [left, chat, right])
document.querySelector = sel => {
  if (sel === '[data-tree-tab="workspace"]') return tab
  const side = sel.match(/^\[data-sqh-side="(\w+)"\]$/)
  if (side) return row.all().find(n => n.dataset.sqhSide === side[1]) || null
  if (sel === '[data-sqh-float-root]') return 'sqhFloatRoot' in row.dataset ? row : null
  return null
}
// the plugin finds what it marked through its own data-sqh-* attributes
const camel = a => a.replace(/^data-/, '').replace(/-(\w)/g, (_, c) => c.toUpperCase())
document.querySelectorAll = sel => row.all().filter(n => [...sel.matchAll(/\[(data-sqh-[a-z-]+)\]/g)].some(m => camel(m[1]) in n.dataset))
const icon = { querySelector: sel => (sel === '.codicon-layout-sidebar-right' ? {} : null) }
const button = { closest: sel => (sel === '[data-titlebar-cluster] button' ? icon : null) }
const press = () => w.fire('click', { target: button })
const docked = () => ({ dock: row.vars['--sqh-dock-right'] || '0px', flag: 'sqhDockRight' in row.dataset, shown: 'sqhOpen' in right.dataset })
"""


def test_desktops_right_button_docks_the_side_beside_the_chat_and_releases_it(desk):
    got = desk(ROW + """
w.register()
w.time.advance(1300)
out.floating = docked()
out.swallowed = press()
out.pinned = docked()
w.time.advance(1300)                      // the repaint poll keeps it docked
out.still = docked()
press()
out.released = docked()
""")
    assert got["floating"] == {"dock": "0px", "flag": False, "shown": False}, "a floating side takes no width until pinned"
    assert got["swallowed"], "Desktop's own toggle would fold the floating side to its rail"
    assert got["pinned"] == {"dock": "340px", "flag": True, "shown": True}, "the button must give the side its width in the row"
    assert got["still"] == got["pinned"]
    assert got["released"] == {"dock": "0px", "flag": False, "shown": False}, "a second press lets the side float and hide again"


def test_a_docked_side_is_still_docked_after_a_restart(desk):
    got = desk(ROW + """
w.register()
w.time.advance(1300)
press()
w.dispose()
out.afterDispose = docked()
w.register()                              // the app starting again: same stored prefs
w.time.advance(1300)
out.restarted = docked()
""")
    assert got["afterDispose"]["flag"] is False, "switching the plugin off must hand the row back to Desktop"
    assert got["restarted"] == {"dock": "340px", "flag": True, "shown": True}


# A grip on the side's inner edge: what the user drags to widen or narrow a floating side.
GRIP = """
const grip = side => w.grips().find(g => g.dataset.sqhGrip === side)
const drag = (side, x) => {
  const g = grip(side)
  g.fire('pointerdown', { button: 0, pointerId: 1, clientX: 1060, preventDefault() {} })
  g.fire('pointermove', { clientX: x })
  g.fire('pointerup', {})
}
"""


def test_dragging_a_floating_sides_grip_changes_its_width_and_keeps_it(desk):
    got = desk(ROW + GRIP + """
w.register()
w.time.advance(1300)
press()                                   // dock the right side: its grip shows
out.gripShown = !grip('right').hidden
drag('right', 1400 - 500)                 // the pointer 500 px from the row's right edge
out.width = right.vars['--sqh-w']
out.dock = row.vars['--sqh-dock-right']
w.dispose()
delete right.dataset.sqhSide
w.register()                              // restart
w.time.advance(1300)
out.restarted = right.vars['--sqh-w']
""")
    assert got["gripShown"], "a shown side must offer a grip: Desktop's sash cannot resize a side out of the flow"
    assert got["width"] == "500px", "the drag must set the side's width"
    assert got["dock"] == "500px", "a docked side's room in the row follows the drag"
    assert got["restarted"] == "500px", "the width dragged is kept across restarts"


def test_a_hidden_side_offers_no_grip(desk):
    got = desk(ROW + GRIP + """
w.register()
w.time.advance(1300)
out.hidden = grip('right').hidden
""")
    assert got["hidden"] is True, "a grip over a hidden side would be a dead strip over the chat"


def test_a_plain_click_on_a_chat_opens_it_in_place_and_cmd_click_in_a_new_tab(desk):
    got = desk("""
const opened = []
w.host.openSession = async (id, o) => void opened.push(o.intent)
w.register()
await w.exports().openChat('jobs', 's1', w.exports().intentOf({}))
await w.exports().openChat('jobs', 's2', w.exports().intentOf({ metaKey: true }))
out.opened = opened
""")
    assert got["opened"] == ["in-place", "tab"], "every plain click used to stack a new tab"


def test_polling_pauses_while_the_window_is_hidden(desk):
    got = desk("""
w.dom.root = 'default-layout'
w.register()
w.time.advance(1000)
w.dom.hidden = true
w.dom.root = 'sqh-root'
w.time.advance(30000)
out.whileHidden = w.revealed.slice()
w.dom.hidden = false
w.time.advance(1000)
out.afterShown = w.revealed.slice()
""")
    assert got["whileHidden"] == [], "the layout poll kept running in a hidden window"
    assert got["afterShown"] == ["files"]


# ---- the Desktop-cards switch the agent half reads ------------------------------------------------------------------

PROFILES = """[{ name: 'default', is_default: true }, { name: 'builder' }, { name: 'web-frontend' },
                { name: 'web', ui_meta: { 'hermes-squads': { role: 'manager', name: 'Web' } } }]"""
SETTLE = "const settle = () => new Promise(r => setImmediate(r))"


def test_the_cards_setting_written_is_one_the_agent_half_declares_and_reads(desk):
    """The desktop half switches `desktop_cards` on through `plugins.manage` for each manager and the builder; the
    agent half reads that same key from its manifest. A rename on either side leaves cards off without an error."""
    import yaml
    got = desk(f"""
{SETTLE}
w.register()
w.exports().syncCards({PROFILES})
await settle()
out.calls = w.calls.filter(c => c.method === 'plugins.manage')
""")
    manifest = yaml.safe_load((PLUGIN.parents[1] / "plugin.yaml").read_text())
    assert sorted((c["via"], c["params"]["key"], list(c["params"]["values"])[0], c["params"]["values"]["desktop_cards"],
                   c["params"]["action"]) for c in got["calls"]) == [
        ("builder", manifest["name"], "desktop_cards", True, "settings"), ("web", manifest["name"], "desktop_cards", True, "settings")]
    assert "desktop_cards" in manifest["config_schema"]


def test_a_bot_that_cannot_take_the_setting_is_not_asked_again_at_every_refresh(desk):
    """A bot without the agent half answers an error each time, and asking wakes its backend; the list refreshes every
    30 s. Retry after ten minutes, not before; a bot that took it is never asked again."""
    got = desk(f"""
{SETTLE}
w.failProfile.add('builder')
w.register()
const asks = () => w.calls.filter(c => c.method === 'plugins.manage').map(c => c.via).sort().join(',')
w.exports().syncCards({PROFILES}); await settle()
out.first = asks()
for (let i = 0; i < 5; i++) {{ w.time.advance(30000); w.exports().syncCards({PROFILES}); await settle() }}
out.fiveRefreshes = asks()
w.time.advance(8 * 60000); w.exports().syncCards({PROFILES}); await settle()
out.afterTen = asks()
""")
    assert got["first"] == "builder,web"
    assert got["fiveRefreshes"] == "builder,web", "a failing bot was asked again within ten minutes"
    assert got["afterTen"] == "builder,builder,web", "and it is asked again once the ten minutes passed"


def test_switching_the_plugin_off_and_on_quickly_leaves_the_cards_setting_on(desk):
    """Switching off clears the setting; switching straight back on must set it again, not find the bot \"done\" while
    the clearing request is still on its way."""
    got = desk(f"""
{SETTLE}
w.register()
w.exports().syncCards({PROFILES}); await settle()
w.dispose()
w.register()
w.exports().syncCards({PROFILES}); await settle()
out.web = w.calls.filter(c => c.via === 'web' && c.method === 'plugins.manage').map(c => c.params.values.desktop_cards)
""")
    assert got["web"] == [True, False, True]


# ---- what the plugin registers ----------------------------------------------------------------------------------------

def test_the_plugin_is_opt_in_and_named_like_its_package(desk):
    import yaml
    got = desk("out.id = w.plugin.id; out.optIn = w.plugin.defaultEnabled === false; out.name = w.plugin.name")
    manifest = yaml.safe_load((PLUGIN.parents[1] / "plugin.yaml").read_text())
    assert got["id"] == manifest["name"] == "squad-hub" and got["optIn"] is True
    assert (PLUGIN.parents[1] / "__init__.py").is_file()


def test_the_squads_layout_it_registers_places_files_over_the_terminal_and_never_review(desk):
    """Review follows the chat (each agent opens its own); a global Review zone in the layout would show the wrong one."""
    got = desk("""
w.register()
const panes = []
const walk = n => n.type === 'group' ? panes.push(...n.panes) : n.children.forEach(walk)
const layout = w.contribution('layout')
walk(layout.data)
out.panes = panes; out.area = layout.area
const files = w.contribution('layout').data.children[2]
out.rightColumn = files.children.map(g => g.panes[0])
""")
    assert got["area"] == "layouts"
    assert {"squad-hub:pane", "workspace", "files", "terminal"} <= set(got["panes"]) and "review" not in got["panes"]
    assert got["rightColumn"] == ["files", "terminal"], "files over the terminal"


def test_every_command_and_keybinding_it_registers_runs_without_a_chat_open(desk):
    """The palette must never throw: each entry is run with nothing focused and nothing loaded."""
    got = desk("""
w.register()
const failed = []
const ids = []
for (const id of ['cmd-open', 'cmd-preview', 'key-preview', 'cmd-pin-left', 'key-pin-left', 'cmd-pin-right', 'key-pin-right', 'cmd-float', 'cmd-layout', 'cmd-next', 'key-next', 'cmd-theme', 'cmd-timeline', 'cmd-new-project']) {
  const c = w.contribution(id)
  if (!c) { failed.push(id + ': not registered'); continue }
  ids.push(c.data.id)
  try { await c.data.run() } catch (e) { failed.push(id + ': ' + e.message) }
}
out.failed = failed
out.ids = ids
""")
    assert got["failed"] == []
    assert len(got["ids"]) == 14


# ---- what a component subscribes to ---------------------------------------------------------------------------------------

def test_a_row_re_renders_only_for_its_own_chat_and_its_own_fold(desk):
    """Rows read one slice of an atom through useSyncExternalStore. React re-renders a row when its snapshot changes
    and re-subscribes when the subscribe function changes: the snapshot must stay the same object for a chat whose
    previews did not change, and the subscribe function must be one function for every row."""
    got = desk(f"""
w.register()
w.focus('{CHAT_A}', 'rt-a')
w.emit('session.info', 'rt-a', {{ stored_session_id: '{CHAT_A}' }})
const {{ usePreviews, useOpen }} = w.exports()
const before = usePreviews('{CHAT_A}')
const quiet = usePreviews('{CHAT_B}')
out.subscribeShared = new Set(globalThis.__SQH_SUBS__).size === 1
const sub = globalThis.__SQH_SUBS__[0]
let wakeups = 0
const stop = sub(() => wakeups++)
w.emit('preview.open', 'rt-a', {{ url: '{URL}' }})
out.wokenByAPreview = wakeups
out.ownChatChanged = usePreviews('{CHAT_A}') !== before && usePreviews('{CHAT_A}')[0].url === '{URL}'
out.otherChatSame = usePreviews('{CHAT_B}') === quiet && quiet.length === 0
stop()
w.emit('preview.open', 'rt-a', {{ url: '/tmp/page.html' }})
out.afterUnsubscribe = wakeups
out.foldDefault = [useOpen('lane:web:/w/a', true), useOpen('folder:web:p1:/w/a', false)]
""")
    assert got["subscribeShared"] and got["wokenByAPreview"] == 1 and got["afterUnsubscribe"] == 1
    assert got["ownChatChanged"] and got["otherChatSame"]
    assert got["foldDefault"] == [True, False], "no choice stored: each row follows its default"


def test_every_consumer_of_the_trees_gets_the_same_build_until_the_data_changes(desk):
    """The list, the status-bar counter, each empty chat's intro and the shortcuts all need every visible bot's tree
    from the same snapshot; building it once per change is what keeps a refresh from costing four builds."""
    got = desk("""
w.register()
const { treesOf, prefsAtom } = w.exports()
const profile = (name, extra = {}) => ({ name, is_default: name === 'default', display_name: name, ui_meta: {}, ...extra })
const chats = [{ id: 'c1', profile: 'web', source: 'desktop', title: 'hero', cwd: '/w/shop', git_repo_root: '/w/shop', message_count: 3, last_active: 1000, started_at: 900 }]
const snap = { at: 1, profiles: [profile('default'), profile('web', { ui_meta: { 'hermes-squads': { role: 'manager', name: 'Web' } } })], humanBy: { web: 1 }, chats,
               projectsBy: { web: [{ id: 'p1', name: 'Shop', folders: [{ path: '/w/shop', is_primary: true }] }] } }
const prefs = prefsAtom.get()
const wts = {}
const first = treesOf(snap, wts, prefs)
out.names = first.map(t => t.bot.name)
out.chat = first[1].projects[0].folders[0].lanes[0].sessions.map(s => s.id)
out.same = treesOf(snap, wts, prefs) === first
out.sameWithoutWorktrees = treesOf(snap, undefined, prefs) === treesOf(snap, undefined, prefs)
out.newSnapshot = treesOf({ ...snap }, wts, prefs) !== first
out.newPrefs = treesOf(snap, wts, { ...prefs, hidden: ['web'] }).map(t => t.bot.name)
out.empty = treesOf(undefined, wts, prefs)
""")
    assert got["names"] == ["default", "web"] and got["chat"] == ["c1"]
    assert got["same"] and got["sameWithoutWorktrees"] and got["newSnapshot"]
    assert got["newPrefs"] == ["default"] and got["empty"] == []


def test_the_stored_layout_is_parsed_once_while_it_does_not_change(desk):
    """The reveal poll runs four times a second and the paint once a second; the layout Desktop persists is a few
    kilobytes of JSON that changes when the user moves a pane."""
    tree = {"type": "split", "id": "sqh-root", "orientation": "row", "children": [
        {"type": "group", "id": "sqh-main", "panes": ["workspace"], "active": "workspace"}]}
    other = {**tree, "children": [{"type": "group", "id": "sqh-main", "panes": ["workspace", "files"], "active": "files"}]}
    got = desk(f"""
const key = 'hermes.desktop.layoutTree.v2'
w.localStorage.set(key, {json.dumps(json.dumps(tree))})
let parses = 0
const parse = JSON.parse
JSON.parse = (text, ...rest) => (typeof text === 'string' && text.includes('sqh-root') && parses++, parse(text, ...rest))
w.register()
w.time.advance(10000)
out.steady = parses
w.localStorage.set(key, {json.dumps(json.dumps(other))})
w.time.advance(2000)
out.afterChange = parses
JSON.parse = parse
""")
    assert got == {"steady": 1, "afterChange": 2}


def test_the_polls_do_not_read_the_layout_while_the_window_is_hidden(desk):
    got = desk("""
const key = 'hermes.desktop.layoutTree.v2'
let reads = 0
const getItem = globalThis.localStorage.getItem
globalThis.localStorage.getItem = k => (k === key && reads++, getItem(k))
w.register()
w.time.advance(1000)                       // start-up reads (first paint, the one-off unfold check) are not polls
const base = reads
w.dom.hidden = true
w.time.advance(30000)
out.hidden = reads - base
w.dom.hidden = false
w.time.advance(3000)
out.visible = reads - base
""")
    assert got["hidden"] == 0, "the reveal and paint polls kept running in a hidden window"
    assert got["visible"] > 0


# ---- the components, drawn with stub React ----------------------------------------------------------------------------------

WALK = """
const walk = (node, visit) => {
  if (!node || typeof node !== 'object') return
  if (Array.isArray(node)) return node.forEach(n => walk(n, visit))
  visit(node)
  walk(node.props?.children, visit)
}
"""


def test_the_list_opens_only_the_dialog_that_was_asked_for(desk):
    got = desk(WALK + """
w.register()
const { Dialogs } = w.exports()
const open = kind => { const states = []; walk(Dialogs({ dialog: kind && { kind, bot: { name: 'web' } }, close: () => {} }), n => { if (n.props && 'state' in n.props) states.push(n.props.state) }); return states }
out.none = open(null).filter(Boolean).length
out.total = open(null).length
out.kinds = ['project', 'worktree', 'text', 'confirm', 'caps', 'clean', 'look', 'env'].map(k => open(k).filter(Boolean).length)
""")
    assert got["none"] == 0 and got["total"] == 8
    assert got["kinds"] == [1] * 8, "each kind opens exactly one dialog"


def test_the_timeline_draws_one_bar_per_run_in_its_bots_lane(desk):
    """Payload shaped like loadTimeline() returns: lanes of bars, times in unix seconds."""
    now = 1_793_000_000
    data = {"now": now, "from": now - 86400, "tasks": 2, "skipped": 0, "issues": [],
            "timeline": {"from": now - 86400, "to": now, "lanes": [
                {"name": "web-frontend", "bars": [
                    {"taskId": "t_aa01", "title": "hero", "status": "done", "kind": "wait", "state": "queued", "start": now - 9000, "end": now - 8000, "open": False},
                    {"taskId": "t_aa01", "title": "hero", "status": "done", "kind": "run", "state": "done", "tone": "done", "start": now - 8000, "end": now - 6000, "open": False, "outcome": "completed", "summary": ""}]},
                {"name": "web-qa", "bars": [
                    {"taskId": "t_aa02", "title": "qa", "status": "running", "kind": "run", "state": "run", "tone": "run", "start": now - 3000, "end": now, "open": True, "outcome": "running", "summary": ""}]}]}}
    got = desk(WALK + f"""
w.register()
globalThis.__SQH_QUERIES__ = options => {{
  const key = options.queryKey?.[1]
  if (key === 'boards') return {{ data: [{{ slug: 'web', name: 'Web', digest: {{ blocked: 0 }} }}] }}
  if (key === 'timeline') return {{ data: {json.dumps(data)}, isLoading: false, refetch() {{}} }}
  return {{}}
}}
const {{ TimelinePage }} = w.exports()
const bars = []; const lanes = []
walk(TimelinePage(), n => {{
  if (n.props?.className === 'sqh-tl-bar') bars.push(n.props)
  if (n.props?.className === 'sqh-tl-lane') lanes.push(n.key)
}})
out.lanes = lanes
out.bars = bars.map(b => [b['data-kind'], b['data-state'], b['data-open'], parseFloat(b.style.left) >= 0, parseFloat(b.style.left) + parseFloat(b.style.width) <= 100.001])
""")
    assert got["lanes"] == ["web-frontend", "web-qa"]
    assert got["bars"] == [["wait", "queued", "false", True, True], ["run", "done", "false", True, True], ["run", "run", "true", True, True]]
