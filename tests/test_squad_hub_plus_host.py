"""squad-hub-plus desktop plugin: the register() wiring, run for real.

`squads/_plugins/squad-hub-plus/desktop/plugin.js` is loaded under node against the same fake Desktop host the
catalog copy uses (`tests/fixtures/squad_hub_harness.mjs`). What is tested here is what the plugin SDK cannot
express and the catalog copy therefore does not carry: floating sides, the hidden profile rail and Bots tab, the
`.env` double-click, the layout pick, and the handshake squad-hub speaks to hand those actions over.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUS = REPO / "squads" / "_plugins" / "squad-hub-plus" / "desktop" / "plugin.js"
HUB = REPO / "squads" / "_plugins" / "squad-hub" / "desktop" / "plugin.js"
HARNESS = REPO / "tests" / "fixtures" / "squad_hub_harness.mjs"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is needed to run the plugin")

PRELUDE = """
import { boot } from './harness.mjs'
const w = await boot({ pluginPath: new URL('./plugin.mjs', import.meta.url).pathname })
const out = {}
"""

MODEL_EXPORTS = ("trimPath baseName slugify upgradePrefs workspaceGroup chatAlone zonesOf zonesOfAll "
                 "parseLayout sideSignature isReveal DEFAULT_PREFS").split()


def _model_source() -> str:
    text = PLUS.read_text(encoding="utf-8")
    start = text.index("// ───────────────────────────── MODEL (pure)")
    end = text.index("// ─────────────────────────── END MODEL (pure)")
    return text[start:end] + "\nexport { " + ", ".join(MODEL_EXPORTS) + " }\n"


@pytest.fixture(scope="module")
def desk(tmp_path_factory):
    """The plus plugin with the SDK and react stubbed, and a runner for scenarios."""
    d = tmp_path_factory.mktemp("squad-hub-plus")
    text = PLUS.read_text(encoding="utf-8")
    wiring = text[text.index("// ───────────────────────────── host wiring"):]
    sdk_names = re.search(r"const \{([^}]*)\} = sdk", wiring).group(1)
    names = [n.strip() for n in sdk_names.split(",") if n.strip()]
    names += ["TITLEBAR_AREAS", "PALETTE_AREA", "KEYBINDS_AREA", "usePluginI18n", "ToggleRow", "Button", "Codicon"]
    (d / "plugin.mjs").write_text(text, encoding="utf-8")
    (d / "package.json").write_text('{"type": "module"}', encoding="utf-8")
    stubs = {
        ("@hermes/plugin-sdk", "index.js"): "const s = globalThis.__SQH_SDK__\n" + "".join(f"export const {n} = s.{n}\n" for n in sorted(set(names))),
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


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    d = tmp_path_factory.mktemp("squad-hub-plus-model")
    (d / "model.mjs").write_text(_model_source(), encoding="utf-8")
    (d / "package.json").write_text('{"type": "module"}', encoding="utf-8")

    def call(fn: str, *args):
        script = (f"import * as m from './model.mjs'; const a = JSON.parse(process.argv[1]); "
                  f"const r = await m.{fn}(...a); console.log(JSON.stringify(r === undefined ? null : r));")
        out = subprocess.run([NODE, "--input-type=module", "-e", script, json.dumps(args)], cwd=d,
                             capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)

    def run_js(body: str):
        script = f"import * as m from './model.mjs'; const out = await (async () => {{ {body} }})(); console.log(JSON.stringify(out === undefined ? null : out));"
        done = subprocess.run([NODE, "--input-type=module", "-e", script], cwd=d, capture_output=True, text=True, timeout=30)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)
    call.js = run_js
    return call


# ---- the layout helpers it inherited from squad-hub ------------------------------------------------

def test_a_zone_that_shows_another_pane_is_a_reveal_and_the_first_look_is_not(model):
    tree = {"type": "split", "id": "r", "children": [
        {"type": "group", "id": "sqh-left", "panes": ["squad-hub:pane"], "active": "squad-hub:pane"},
        {"type": "group", "id": "sqh-files", "panes": ["files", "terminal"], "active": "files"}]}
    zones = model("zonesOfAll", [model("parseLayout", json.dumps(tree))])
    assert zones == {"sqh-left": "squad-hub:pane", "sqh-files": "files"}
    side = {"groups": ["sqh-files"], "open": False, "pinned": False}
    before = model("sideSignature", side["groups"], zones)
    other = model("sideSignature", side["groups"], {**zones, "sqh-files": "review"})
    assert model("isReveal", before, other, side) is True, "another pane took the zone: a reveal from a shortcut"
    assert model("isReveal", before, before, side) is False
    assert model.js("return m.isReveal(undefined, 'a=b', { groups: ['a'], open: false, pinned: false })") is False, \
        "the first look is no change"
    folded = model("sideSignature", side["groups"], {**zones, "sqh-files": "review:min"})
    assert model("isReveal", before, folded, side) is False, "a side the user just folded stays folded"


def test_the_workspace_group_is_found_through_any_depth_and_the_chat_alone_is_measured(model):
    tree = {"type": "split", "id": "r", "children": [
        {"type": "group", "id": "left", "panes": ["sessions"]},
        {"type": "split", "id": "mid", "children": [{"type": "group", "id": "g-main", "panes": ["workspace"]}]}]}
    assert model("workspaceGroup", tree) == "g-main"
    assert model("workspaceGroup", {"type": "group", "id": "g", "panes": ["files"]}) is None
    assert model("chatAlone", [0, 0]) is True and model("chatAlone", [420]) is False


# ---- floating sides: the row, the grip and the title-bar button -----------------------------------

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
w.time.advance(1300)
out.still = docked()
press()
out.released = docked()
""")
    assert got["floating"] == {"dock": "0px", "flag": False, "shown": False}, "a floating side takes no width until pinned"
    assert got["swallowed"], "Desktop's own toggle would fold the floating side to its rail"
    assert got["pinned"] == {"dock": "340px", "flag": True, "shown": True}, "the button gives the side its width in the row"
    assert got["still"] == got["pinned"]
    assert got["released"] == {"dock": "0px", "flag": False, "shown": False}, "a second press lets it float and hide again"


def test_a_docked_side_is_still_docked_after_a_restart(desk):
    got = desk(ROW + """
w.register()
w.time.advance(1300)
press()
w.dispose()
out.afterDispose = docked()
w.register()
w.time.advance(1300)
out.restarted = docked()
""")
    assert got["afterDispose"]["flag"] is False, "switching the plugin off hands the row back to Desktop"
    assert got["restarted"] == {"dock": "340px", "flag": True, "shown": True}


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
press()
out.gripShown = !grip('right').hidden
drag('right', 1400 - 500)
out.width = right.vars['--sqh-w']
out.dock = row.vars['--sqh-dock-right']
w.dispose()
delete right.dataset.sqhSide
w.register()
w.time.advance(1300)
out.restarted = right.vars['--sqh-w']
""")
    assert got["gripShown"], "a shown side offers a grip: Desktop's sash cannot resize a side out of the flow"
    assert got["width"] == "500px" and got["dock"] == "500px"
    assert got["restarted"] == "500px", "the width dragged is kept across restarts"


def test_a_hidden_side_offers_no_grip(desk):
    got = desk(ROW + GRIP + """
w.register()
w.time.advance(1300)
out.hidden = grip('right').hidden
""")
    assert got["hidden"] is True, "a grip over a hidden side would be a dead strip over the chat"


def test_the_terminal_rises_and_hides_with_the_floating_side_that_holds_it(desk):
    got = desk(ROW + r"""
w.localStorage.set('hermes.desktop.layoutTree.v2', JSON.stringify({ type: 'split', id: 'sqh-root', children: [
  { type: 'group', id: 'sqh-left', panes: ['squad-hub:pane'], active: 'squad-hub:pane' },
  { type: 'group', id: 'sqh-main', panes: ['workspace'], active: 'workspace' },
  { type: 'split', id: 'r', children: [{ type: 'group', id: 'sqh-files', panes: ['files'], active: 'files' },
                                       { type: 'group', id: 'sqh-term', panes: ['terminal'], active: 'terminal' }] }] }))
const resized = []
window.dispatchEvent = e => resized.push(e.type)
globalThis.Event = class { constructor(type) { this.type = type } }
w.register()
w.time.advance(1300)
const rule = () => (w.styles().map(s => s.textContent).join('\n').match(/\[data-persistent-terminal\]\{[^}]*\}/) || [''])[0]
out.hidden = rule()
w.edges().find(e => e.dataset.sqhEdge === 'right').fire('pointerenter')   // the pointer reaches the right edge
w.time.advance(100)
out.shown = rule()
w.time.advance(400)
out.resized = resized.length
""")
    assert "visibility:hidden" in got["hidden"] and "pointer-events:none" in got["hidden"], "a hidden side hides the terminal"
    assert "z-index:47" in got["shown"] and "visibility:hidden" not in got["shown"], "a shown side lifts it above its own host"
    assert got["resized"] >= 2, "the overlay re-measures its slot after the slide"


def test_the_stored_layout_is_parsed_once_while_it_does_not_change(desk):
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


def test_the_polls_do_not_read_the_layout_while_the_window_is_hidden(desk):
    got = desk("""
const key = 'hermes.desktop.layoutTree.v2'
let reads = 0
const getItem = globalThis.localStorage.getItem
globalThis.localStorage.getItem = k => (k === key && reads++, getItem(k))
w.register()
w.time.advance(1000)
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


def test_every_command_it_registers_runs_and_the_float_switch_flips_the_pref(desk):
    """The floating-side commands moved here with the feature: same ids, same keys, and the switch still toggles."""
    got = desk("""
w.register()
const failed = []
for (const id of ['cmd-float', 'cmd-pin-left', 'key-pin-left', 'cmd-pin-right', 'key-pin-right']) {
  const c = w.second_contribution = null
  const entry = w.contribution(id)
  if (!entry) { failed.push(id + ': not registered'); continue }
  try { await entry.data.run() } catch (e) { failed.push(id + ': ' + e.message) }
}
out.failed = failed
out.float = JSON.parse(w.store.get('prefs')).floatSides
""")
    assert got["failed"] == []
    assert got["float"] is False, "the palette switch turns floating sides off"


def test_the_old_squad_hub_prefs_are_read_once_so_a_choice_survives_the_split(desk):
    got = desk("""
w.localStorage.set('hermes.plugin.squad-hub.prefs', JSON.stringify({ floatSides: false, hideRail: true, hideBotsTab: true, envDoubleClick: true, prefsVersion: 4 }))
w.register()
out.prefs = JSON.parse(w.store.get('prefs'))
""")
    assert got["prefs"]["floatSides"] is False, "the pre-split choice carries over"
    assert set(got["prefs"]) == {"floatSides", "prefsVersion"}, "the retired switches (Bots tab, rail, .env double-click) are not kept"
    assert got["prefs"]["prefsVersion"] == 1, "and it is stamped as this plugin's own version"


# ---- its own stylesheet is attached ----------------------------------------------------------------

def test_its_own_stylesheet_is_attached_to_the_page_and_removed_on_dispose(desk):
    """`CSS` (the settings page and credits styles) was built and never appended, so nothing it styled showed up."""
    got = desk("""
w.register()
out.running = w.styles().filter(s => 'squadHubPlus' in s.dataset).length
w.dispose()
out.after = w.styles().filter(s => 'squadHubPlus' in s.dataset).length
""")
    assert got["running"] == 1, "the plugin's own <style> must be in the document while it runs"
    assert got["after"] == 0


# ---- disposing leaves nothing behind ---------------------------------------------------------------

def test_disposing_the_plugin_removes_every_listener_timer_and_style(desk):
    got = desk("""
const empty = w.leftBehind()
w.register()
out.running = w.leftBehind()
w.dispose()
out.after = w.leftBehind()
out.empty = empty
const before = w.calls.length
w.time.advance(60000)
out.latecomers = w.calls.slice(before)
""")
    assert got["running"]["listeners"] and got["running"]["styles"] and got["running"]["timers"], "the plugin did start"
    assert got["after"] == got["empty"], got["after"]
    assert got["latecomers"] == [], "a timer fired after the plugin was disposed"
