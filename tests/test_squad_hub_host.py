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
PLUS = REPO / "squads" / "_plugins" / "squad-hub-plus" / "desktop" / "plugin.js"
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
    names = [n.strip() for n in sdk_names.split(",") if n.strip()] + ["TITLEBAR_AREAS", "KANBAN_CARD_AREAS"]
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

    def run(scenario: str, plus: bool = False):
        prelude = PRELUDE
        if plus:
            # the companion plugin beside it, the way squadctl installs both
            (d / "plus.mjs").write_text(PLUS.read_text(encoding="utf-8"), encoding="utf-8")
            prelude = ("import { boot } from './harness.mjs'\n"
                       "const w = await boot({ pluginPath: new URL('./plugin.mjs', import.meta.url).pathname, "
                       "secondPluginPath: new URL('./plus.mjs', import.meta.url).pathname })\nconst out = {}\n")
        (d / "scenario.mjs").write_text(prelude + scenario + "\nconsole.log(JSON.stringify(out))\n", encoding="utf-8")
        done = subprocess.run([NODE, "scenario.mjs"], cwd=d, capture_output=True, text=True, timeout=60)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout.strip().splitlines()[-1])
    run.plus = True
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
    """The two window listeners of the handshake, the style tag and the global are gone; and the delayed refresh a
    gateway event arms never fires after the plugin was switched off."""
    got = desk(f"""
const empty = w.leftBehind()
w.register()
w.focus('{CHAT_A}', 'rt-a')
w.emit('session.info', 'rt-a', {{ stored_session_id: '{CHAT_A}' }})
out.running = w.leftBehind()
out.armed = w.time.pending()
w.dispose()
out.after = w.leftBehind()
const before = w.calls.length
w.time.advance(60000)
out.latecomers = w.calls.slice(before)
out.empty = empty
""")
    assert got["running"]["listeners"] and got["running"]["styles"], "the plugin did start"
    assert got["armed"] > 0, "a gateway event arms a delayed refresh"
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


def test_a_new_chat_opens_in_place_and_shows_its_auto_title_at_once(desk):
    """Every "+" stacked a session tab (they piled up and came back on restart), and the row read "New chat" until
    the next list refetch although Hermes had already named it (`session.title`)."""
    got = desk("""
const opened = []
w.host.openSession = async (id, o) => void opened.push([id, o.intent])
w.host.requestProfile = async (bot, method) => method === 'session.create'
  ? { session_id: 'rt-n', stored_session_id: 'local-new', info: {} } : { projects: [] }
w.host.listPersistedSessions = async () => ({ sessions: [] })
w.host.request = async () => ({ profiles: [{ name: 'default', is_default: true }] })
w.register()
await w.exports().newChat('default')
w.emit('session.title', 'rt-n', { session_id: 'local-new', title: 'Fix the side panels' })
const snap = await w.exports().loadSnapshot()
out.opened = opened
out.title = snap.chats.find(c => c.id === 'local-new')?.title
""")
    assert got["opened"] == [["local-new", "in-place"]]
    assert got["title"] == "Fix the side panels"


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


def test_the_squads_layout_it_registers_fits_three_columns_with_the_crons_on_the_right(desk):
    """Review follows the chat (each agent opens its own); a global Review zone in the layout would show the wrong one.
    Three columns only, crons in front of the files over the terminal: a fourth column left the chat a sliver at the
    1280px first-launch window, and the crons pane rendered cramped."""
    got = desk("""
w.register()
const panes = []
const walk = n => n.type === 'group' ? panes.push(...n.panes) : n.children.forEach(walk)
const layout = w.contribution('layout')
walk(layout.data)
out.panes = panes; out.area = layout.area
const root = layout.data
out.columns = root.children.length
const right = root.children[2]
out.rightOrientation = right.orientation
out.rightGroups = right.children.map(g => [g.panes, g.active])
out.cronPane = w.contribution('crons')?.data
out.hubWidth = w.contribution('pane')?.data.width
""")
    assert got["area"] == "layouts"
    assert {"squad-hub:pane", "workspace", "files", "terminal", "squad-hub:crons"} <= set(got["panes"]) and "review" not in got["panes"]
    assert got["columns"] == 3, "list, chat, one right column"
    assert got["rightOrientation"] == "column"
    assert got["rightGroups"] == [[["squad-hub:crons", "files"], "squad-hub:crons"], [["terminal"], "terminal"]], \
        "the crons in front, the files one tab away, the terminal under them"
    assert got["cronPane"]["placement"] == "right" and got["cronPane"]["dock"] == {"pane": "files", "pos": "center"}, \
        "outside the Squads layout too, a tab beside the files on the right"
    side = int(got["cronPane"]["width"].rstrip("px")) + int(got["hubWidth"].rstrip("px"))
    assert 1280 / 1.1 - side >= 600, "the chat keeps 600px at the default window and zoom"


def test_every_command_and_keybinding_it_registers_runs_without_a_chat_open(desk):
    """The palette must never throw: each entry is run with nothing focused and nothing loaded."""
    got = desk("""
w.register()
const failed = []
const ids = []
for (const id of ['cmd-open', 'cmd-preview', 'key-preview', 'cmd-layout', 'cmd-next', 'key-next', 'cmd-theme', 'cmd-board', 'cmd-new-project']) {
  const c = w.contribution(id)
  if (!c) { failed.push(id + ': not registered'); continue }
  ids.push(c.data.id)
  try { await c.data.run() } catch (e) { failed.push(id + ': ' + e.message) }
}
out.failed = failed
out.ids = ids
""")
    assert got["failed"] == []
    assert len(got["ids"]) == 9


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


def test_the_cron_pane_lists_the_squads_jobs_with_their_bot_and_what_they_do(desk):
    """Payloads shaped like `cron.manage list` (tools/cronjob_job_args.py _format_job): one list per bot of the squad
    of the chat in view, each card naming the job, the bot that runs it and what it does, next run first. The card is
    built from the app's own pieces (Bot Mode's Cronjobs row: RowButton, Switch), and its switch pauses the job on the
    bot that owns it."""
    jobs = {
        "jobs": {"jobs": [{"job_id": "a1", "name": "jobs-watch", "script": "board_watch.py", "no_agent": True, "enabled": True,
                           "state": "scheduled", "schedule": "*/30 * * * *", "next_run_at": "2099-01-01T10:30:00+00:00"}]},
        "jobs-scout": {"jobs": [{"job_id": "b1", "name": "scout-digest", "skill": "finding-jobs", "prompt_preview": "",
                                 "enabled": True, "state": "scheduled", "schedule": "0 9 * * *", "next_run_at": "2099-01-01T09:00:00+00:00"}]},
        "jobs-writer": {"jobs": [{"job_id": "c1", "name": "old-one", "script": "x.py", "no_agent": True, "enabled": False,
                                  "state": "paused", "schedule": "0 8 * * *"}]},
    }
    got = desk(WALK + f"""
const snap = {{ profiles: [
  {{ name: 'jobs', ui_meta: {{ 'hermes-bots': {{ squadName: 'Jobs', sectionName: 'Managers', title: 'Jobs manager' }} }} }},
  {{ name: 'jobs-scout', ui_meta: {{ 'hermes-bots': {{ squadName: 'Jobs', sectionName: 'Jobs', title: 'Jobs scout' }} }} }},
  {{ name: 'jobs-writer', ui_meta: {{ 'hermes-bots': {{ squadName: 'Jobs', sectionName: 'Jobs', title: 'Jobs writer' }} }} }},
  {{ name: 'web', ui_meta: {{ 'hermes-bots': {{ squadName: 'Web', sectionName: 'Managers' }} }} }}],
  chats: [{{ id: 'c1', profile: 'jobs-scout' }}] }}
w.queries.set(JSON.stringify(['squad-hub', 'snapshot']), snap)
w.register()
w.translate('en')
w.focus('c1')
const asked = []
globalThis.__SQH_QUERIES__ = options => {{
  if (options.queryKey?.[1] === 'snapshot') return {{ data: snap }}
  if (options.queryKey?.[1] === 'crons') {{ asked.push(options.queryKey[2]); return {{ data: {json.dumps(jobs)} }} }}
  return {{}}
}}
const pane = w.contribution('crons')
const cards = []
walk(pane.render(), n => {{
  if (typeof n.type === 'function' && n.type.name === 'CronPane') walk(n.type(n.props), v => v.type?.name === 'CronCard' && cards.push(v))
}})
const strings = node => {{ const s = []; walk(node, v => {{ for (const k of [].concat(v.props?.children ?? [])) if (typeof k === 'string') s.push(k) }}); return s.join(' | ') }}
out.asked = asked
out.cards = cards.map(c => {{
  const drawn = c.type(c.props)
  const kinds = []
  walk(drawn, v => typeof v.type === 'function' && kinds.push(v.type.name))
  const sw = []
  walk(drawn, v => v.type?.name === 'Switch' && sw.push(v.props))
  return {{ state: drawn.props['data-state'], text: strings(drawn), kinds, checked: sw[0]?.checked, toggle: sw[0]?.onCheckedChange }}
}})
await out.cards[0].toggle(false)
out.paused = w.calls.filter(c => c.method === 'cron.manage')
out.cards = out.cards.map(({{ toggle, ...c }}) => c)
""")
    assert got["asked"] == ["jobs,jobs-scout,jobs-writer"], "the squad of the chat in view, manager first, never another squad"
    names = [next(n for n in ("jobs-watch", "scout-digest", "old-one") if n in c["text"]) for c in got["cards"]]
    assert names == ["scout-digest", "jobs-watch", "old-one"], "next run first, paused last"
    by = dict(zip(names, got["cards"]))
    assert "Jobs manager" in by["jobs-watch"]["text"] and "cards that wait on your answer" in by["jobs-watch"]["text"], "the bot and what the job does"
    assert "Jobs scout" in by["scout-digest"]["text"] and "Runs the finding-jobs skill" in by["scout-digest"]["text"], "an agent job says which skill it runs"
    assert "every 30 min" in by["jobs-watch"]["text"] and "daily 09:00" in by["scout-digest"]["text"], "the schedule in words"
    assert "Next:" in by["scout-digest"]["text"] and "paused" in by["old-one"]["text"], "Hermes' own words for next run and paused"
    assert [c["state"] for c in got["cards"]] == ["ok", "ok", "paused"]
    assert [c["checked"] for c in got["cards"]] == [True, True, False]
    assert all({"RowButton", "Switch"} <= set(c["kinds"]) for c in got["cards"]), "Bot Mode's own row pieces"
    assert [(c["params"]["action"], c["params"]["name"], c["params"]["profile"]) for c in got["paused"]] == [("pause", "b1", "jobs-scout")], \
        "the switch pauses the job on the bot that owns it"

def test_a_card_blocked_for_the_user_wears_a_badge_on_desktops_kanban_board(desk):
    """The official board stays Hermes's (its fixes arrive with Hermes updates); squad-hub only paints a badge on the
    cards that wait on the user, through the SDK slot, never DOM edits."""
    got = desk("""
w.queries.set(JSON.stringify(['squad-hub', 'boards']), [{ slug: 'web', digest: { needsYou: [{ id: 't_ask' }] } }])
w.register()
const c = w.contribution('card-badges')
out.area = c && c.area
out.ask = c.data.decorate({ id: 't_ask', status: 'blocked', tenant: null, assignee: 'web' })
out.running = c.data.decorate({ id: 't_run', status: 'running', tenant: null, assignee: 'web' })
out.unblocked = c.data.decorate({ id: 't_ask', status: 'ready', tenant: null, assignee: 'web' })
""")
    assert got["area"] == "kanban.card.badges"
    assert got["ask"]["tone"] == "red" and got["ask"]["label"]
    assert got["running"] is None and got["unblocked"] is None


def test_prefs_default_shows_desktops_kanban_row(desk):
    got = desk("w.register(); out.prefs = JSON.parse(w.store.get('prefs'))")
    assert "kanban:nav" not in got["prefs"]["hiddenNav"]


def test_opening_another_bots_chat_clears_its_pending_mark_in_that_bots_bucket(desk):
    """User report: "I open one of our tabs and it keeps its pending state". Desktop's dot reads a persisted marker per
    profile and an in-memory unread list; ack only retired the marker, and a chat of another bot (no row loaded in this
    window) stayed in the list. Opening it must clear both, in the owner's bucket, and tell the backend."""
    got = desk("""
globalThis.__SQH_API__ = []
const read = []
const getItem = globalThis.localStorage.getItem
globalThis.localStorage.getItem = k => (read.push(k), getItem(k))
const snap = { profiles: [], chats: [{ id: 'c9', profile: 'jobs', unread: true }] }
w.queries.set(JSON.stringify(['squad-hub', 'snapshot']), snap)
w.register()
await w.exports().openChat('jobs', 'c9', 'tab')
await new Promise(r => setImmediate(r))
out.unread = w.calls.filter(c => c.via === 'unread').map(c => [c.method, c.params[0], c.params[1]])
out.patch = globalThis.__SQH_API__.filter(r => r.method === 'PATCH')
out.private = read.filter(k => String(k).startsWith('hermes.'))
""")
    assert ["forget", ["c9"], "jobs"] in got["unread"], "the in-memory unread list, in the owner's bucket"
    assert ["ack", "c9", "jobs"] in got["unread"], "the stored marker of the owner, never another bot's"
    assert got["patch"] == [], "the backend watermark has no SDK door: nothing writes it behind the app's back"
    assert got["private"] == [], "no private localStorage key is read"


def test_the_kanban_button_opens_desktops_own_board_and_never_moves_the_current_board(desk):
    """The board button opens Desktop's Kanban page and offers the board to squad-hub-plus, which preselects it through
    the page's own switcher. What squad-hub never does is call the server's switch endpoint, which every
    `hermes kanban` command without --board would then follow."""
    got = desk("""
w.register()
w.host.pluginDecisions.set({ kanban: true })
const asked = []
window.addEventListener('squad-hub:open-board', e => asked.push(e.detail))
await w.exports().openBoard('jobs')
out.asked = [...asked]
out.nav = w.calls.filter(c => c.via === 'navigate').map(c => c.method)
out.server = w.calls.filter(c => String(c.method).includes('switch'))
out.slug = w.localStorage.get('hermes.plugin.kanban.boardSlug') || null
w.calls.length = 0
w.host.pluginDecisions.set({})
await w.exports().openBoard('jobs')
out.offNav = w.calls.filter(c => c.via === 'navigate').map(c => c.method)
out.offNotice = w.notices.length
w.calls.length = 0
w.host.pluginDecisions.set({ kanban: true })
await null
out.onNav = w.calls.filter(c => c.via === 'navigate').map(c => c.method)
out.onAsked = asked.length
w.calls.length = 0
w.host.pluginDecisions.set({ kanban: false })
w.host.pluginDecisions.set({ kanban: true })
await null
out.againNav = w.calls.filter(c => c.via === 'navigate').map(c => c.method)
""")
    assert got["asked"] == [{"slug": "jobs", "name": "jobs"}], "the board is offered to the plugin that can preselect it"
    assert got["nav"] == ["/kanban"] and got["slug"] is None, "the page opens; the board slug is not squad-hub's to store"
    assert got["server"] == [], "no /boards/<slug>/switch: that would retarget the CLI"
    assert got["offNav"] == ["/capabilities?tab=plugins&plugin=kanban"] and got["offNotice"] == 1, "Kanban off: open its own row"
    assert got["onNav"] == ["/kanban"] and got["onAsked"] == 2, "switching Kanban on opens the board that was asked for"
    assert got["againNav"] == [], "only once: a later toggle does not pull the user to the board"


# ---- the catalog gate: this copy uses the plugin SDK and nothing else -----------------------------

# What the catalog review refused and this copy must never carry again: the raw Desktop bridge, the app's private
# storage, selectors on core markup, a capture-phase double-click, and another plugin's REST namespace.
FORBIDDEN = {
    "the raw window.hermesDesktop bridge": r"window\.hermesDesktop",
    "the app's private localStorage": r"\blocalStorage\b",
    "a selector on core layout markup": r"data-tree-|data-pane-host|data-persistent-terminal|data-titlebar-cluster",
    "a selector on Desktop's own chrome": r"profile-rail|profile-dropdown|hermes-bots:pane",
    "a capture-phase double-click": r"dblclick",
    "another plugin's REST namespace": r"/api/plugins/",
}

_COMMENT = re.compile(
    r"(\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*'|`(?:[^`\\]|\\.)*`)"
    r"|/\*.*?\*/|(?<![:\\w])//[^\n]*",
    re.DOTALL,
)


def _code(path: Path) -> str:
    """The source with comments blanked, string literals kept (a URL inside a string is not a comment)."""
    return _COMMENT.sub(lambda m: m.group(1) or "\n" * m.group(0).count("\n"), path.read_text(encoding="utf-8"))


def test_the_catalog_copy_reaches_into_nothing_the_plugin_sdk_does_not_offer():
    code = _code(PLUGIN)
    hits = {why: sorted(set(re.findall(pattern, code))) for why, pattern in FORBIDDEN.items()}
    assert {why: found for why, found in hits.items() if found} == {}, "the catalog copy steps outside the plugin SDK"


def test_the_companion_plugin_is_the_one_that_carries_what_the_catalog_copy_cannot():
    """The features are not deleted: every door the catalog copy gave up is in squad-hub-plus, and squadctl installs it."""
    plus = _code(PLUS)
    for token in ("window.hermesDesktop", "localStorage", "data-tree-split", "data-titlebar-cluster", "dblclick"):
        assert token in plus, token


# ---- the handshake with squad-hub-plus ------------------------------------------------------------

WORKTREE = """
w.register()
await w.exports().worktreeAction('worktree-add', { folder: '/w/shop', name: 'feat', branch: 'hermes/feat', base: '' },
  w.exports().worktreeAddCommand('/w/shop', 'feat', 'hermes/feat', ''), 'worktreeCopied')
out.copied = w.osCalls
out.notices = w.notices.map(n => n.message)
"""


def test_without_the_companion_plugin_a_worktree_action_copies_the_exact_command(desk):
    got = desk(WORKTREE)
    assert got["copied"] == [["writeClipboard", 'git -C "/w/shop" worktree add -b "hermes/feat" "/w/shop/.worktrees/feat"']], \
        "the SDK has no worktree verb: the command is what the user gets, never a silent no-op"
    assert got["notices"] and "Command copied" in got["notices"][0]


def test_with_the_companion_plugin_the_worktree_is_created_and_nothing_is_copied(desk):
    got = desk("""
const made = []
window.hermesDesktop.git = {
  worktreeAdd: async (folder, o) => (made.push([folder, o]), { branch: o.branch }),
  worktreeRemove: async (folder, path) => void made.push(['remove', folder, path]),
  repoStatus: async () => ({ changed: 2, ahead: 1 }),
  review: { prList: async () => ({ prs: [{ number: 7, state: 'open', branch: 'hermes/feat', url: 'https://github.com/o/r/pull/7', title: 'Feat' }] }) }
}
w.second.register()
w.register()
await w.exports().worktreeAction('worktree-add', { folder: '/w/shop', name: 'feat', branch: 'hermes/feat', base: '' },
  w.exports().worktreeAddCommand('/w/shop', 'feat', 'hermes/feat', ''), 'worktreeCopied')
out.made = made
out.copied = w.osCalls
// the chips: squad-hub asks, plus answers with what git and GitHub said
out.asked = w.exports().requestLaneChips({ path: '/w/shop', repo: true, lanes: [
  { key: '/w/shop', main: true, path: '/w/shop', branch: 'main' },
  { key: '/w/shop/.worktrees/feat', main: false, path: '/w/shop/.worktrees/feat', branch: 'hermes/feat' }] })
await new Promise(r => setImmediate(r))
out.status = w.exports().laneStatusAtom.get()['/w/shop']
""", plus=True)
    assert got["made"] == [["/w/shop", {"name": "feat", "branch": "hermes/feat"}]], "plus ran the command"
    assert got["copied"] == [], "and squad-hub copied nothing"
    assert got["asked"] is True, "squad-hub hands the chip request over"
    assert got["status"]["/w/shop/.worktrees/feat"]["pr"]["number"] == 7, "the chips squad-hub renders are plus's answer"
    assert got["status"]["/w/shop/.worktrees/feat"]["changed"] == 2


def test_the_folder_picker_is_the_companions_and_a_typed_path_is_the_fallback(desk):
    alone = desk("""
window.hermesDesktop.selectPaths = async () => ['/w/a']
w.register()
out.picked = await w.exports().pickFolders('Add folders…')
""")
    assert alone["picked"] == [], "no picker plugin: the dialog keeps its typed folder field"
    together = desk("""
window.hermesDesktop.selectPaths = async () => ['/w/a', '/w/b']
w.second.register()
w.register()
out.picked = await w.exports().pickFolders('Add folders…')
""", plus=True)
    assert together["picked"] == ["/w/a", "/w/b"], "the native multi-folder picker is back"


# ---- the data the panes read ----------------------------------------------------------------------

def test_boards_and_cards_are_read_through_this_plugins_own_backend(desk):
    """`ctx.rest` is scoped to `/api/plugins/<id>`: the three Kanban reads come from squad-hub's own dashboard API, never
    from the Kanban plugin's namespace."""
    got = desk("""
globalThis.__SQH_REST__ = path => {
  if (path === '/boards') return { boards: [{ slug: 'jobs', name: 'Jobs', total: 2 }] }
  if (path.startsWith('/board?')) return { columns: [{ name: 'blocked', tasks: [
    { id: 't_ask', status: 'blocked', block_kind: 'needs_input', assignee: 'jobs', title: 'Which font?', latest_summary: 'Pick one' }] }] }
  return {}
}
w.register()
const boards = await w.exports().loadBoards()
out.paths = w.restCalls.map(c => c[0])
out.boards = boards.map(b => [b.slug, b.digest.blocked, b.assignees])
""")
    assert got["paths"] == ["/boards", "/board?board=jobs"]
    assert got["boards"] == [["jobs", 1, ["jobs"]]], "a card blocked for the user counts, from the backend's own payload"


def test_lanes_come_from_the_gateway_projects_call_not_from_git(desk):
    """`projects.project_sessions` groups a project into repos and lanes on the backend: the tree never shells out."""
    got = desk("""
const snap = { at: 1, profiles: [{ name: 'web', ui_meta: { 'hermes-squads': { role: 'manager', name: 'Web' } } }], humanBy: { web: 1 },
  chats: [{ id: 'c1', profile: 'web', source: 'desktop', title: 'wt', cwd: '/w/shop/.worktrees/feat', git_repo_root: '/w/shop',
            message_count: 2, last_active: 1000, started_at: 900 }],
  projectsBy: { web: [{ id: 'p1', name: 'Shop', folders: [{ path: '/w/shop', is_primary: true }] }] } }
w.queries.set(JSON.stringify(['squad-hub', 'snapshot']), snap)
const answers = { 'projects.project_sessions': { project: { repos: [{ path: '/w/shop', groups: [
  { id: 'main', label: 'main', path: '/w/shop', isMain: true },
  { id: 'feat', label: 'feat', path: '/w/shop/.worktrees/feat', isMain: false }] }] } } }
w.host.requestProfile = async (bot, method, params) => { w.calls.push({ via: bot, method, params }); return answers[method] || {} }
w.register()
const lanes = await w.exports().loadLanes(snap)
out.called = w.calls.filter(c => c.method === 'projects.project_sessions').map(c => [c.via, c.params.project_id])
out.lanes = lanes['/w/shop'].map(l => [l.branch, l.isMain])
const tree = w.exports().treesOf(snap, lanes, w.exports().prefsAtom.get())
out.worktreeLane = tree[0].projects[0].folders[0].lanes.map(l => [l.label, l.sessions.length])
""")
    assert got["called"] == [["web", "p1"]]
    assert got["lanes"] == [["main", True], ["feat", False]]
    assert sorted(got["worktreeLane"]) == [["feat", 1], ["main", 0]], "the chat in the worktree lands in its own lane"


def test_sessions_are_read_one_sdk_call_per_bot(desk):
    got = desk("""
const seen = []
w.host.listPersistedSessions = async (route, o) => (seen.push([route, o.profile]), { sessions: [
  { id: 'c1', profile: o.profile, source: 'desktop', title: 'a', message_count: 2, started_at: 900, last_active: 1000 },
  { id: 'c2', profile: o.profile, source: 'cron', title: 'job', message_count: 2, started_at: 900, last_active: 1000 }] })
w.host.request = async () => ({ profiles: [{ name: 'default', is_default: true }, { name: 'web', ui_meta: { 'hermes-squads': { role: 'manager', name: 'Web' } } }] })
w.host.requestProfile = async () => ({ projects: [] })
w.register()
const snap = await w.exports().loadSnapshot()
out.calls = seen
out.chats = snap.chats.map(c => c.id)
""")
    assert got["calls"] == [[None, "default"], [None, "web"]], "one SDK read per bot, the window's own connection"
    assert got["chats"] == ["c1", "c1"], "a cron run is not a human chat"
