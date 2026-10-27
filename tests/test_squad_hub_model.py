"""Squad Hub desktop plugin: the pure model (bots shown, bot -> project -> folder -> lane -> chat tree, search,
preview memory) and the load contract of the single-file disk plugin.

The model lives between the MODEL markers of `squads/_plugins/squad-hub/desktop/plugin.js` with no imports; each
case extracts it and runs it under node on payloads shaped like the real gateway answers (profiles.list rows with
`ui_meta`, `/api/profiles/sessions` rows with cwd / git_repo_root / git_branch, projects.list rows with folders,
`git worktree list` rows)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "squads" / "_plugins" / "squad-hub" / "desktop" / "plugin.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is needed to run the plugin model")

EXPORTS = ("baseName HUMAN_SOURCES isKanbanWorktree chatState activeIn projectOpensWide projectDigest folderOpensByDefault needsYou botDigest whereOf isEnvFile pendingAcross nextPending folderIcon iconFor groupIconFor sectionOf botRole botTitle isHumanChat visibleBots folderOf laneOf buildBotTree filterTree "
           "shortAge slugify rememberPreview previewsFor rekeyPreviews sessionTime projectOpensInFocus looseSplit bellGroups upgradePrefs squadMembers cleanupPlan boardDigest boardForBot taskAssignees timelineOf issuesOf bellItems newSince bellFresh dismissKey bellVisible cardState cardNeeds historyOf boardManager cardRef boardRef laneStatus mergeActive keepLastBoards windowTasks boardOfTask introName staleChatDismissals STATES HISTORY_KINDS bindRuntime NO_PREVIEWS openState toggledCollapsed zonesOf zonesOfAll parseLayout sideSignature isReveal cardsToSwitch withTimeout workspaceGroup boardWaiting chatAlone").split()


def _model_source() -> str:
    text = PLUGIN.read_text(encoding="utf-8")
    start = text.index("// ───────────────────────────── MODEL (pure)")
    end = text.index("// ─────────────────────────── END MODEL (pure)")
    return text[start:end] + "\nexport { " + ", ".join(EXPORTS) + " }\n"


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    d = tmp_path_factory.mktemp("squad-hub")
    (d / "model.mjs").write_text(_model_source(), encoding="utf-8")
    (d / "package.json").write_text('{"type": "module"}', encoding="utf-8")

    def run_js(body: str):
        """Arbitrary JS against the model module (values JSON cannot carry: Sets, Maps, identity, timers)."""
        script = f"import * as m from './model.mjs'; const out = await (async () => {{ {body} }})(); console.log(JSON.stringify(out === undefined ? null : out));"
        done = subprocess.run([NODE, "--input-type=module", "-e", script], cwd=d, capture_output=True, text=True, timeout=30)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    def call(fn: str, *args):
        script = (f"import * as m from './model.mjs'; const a = JSON.parse(process.argv[1]); "
                  f"const r = await m.{fn}(...a); console.log(JSON.stringify(r === undefined ? null : r));")
        out = subprocess.run([NODE, "--input-type=module", "-e", script, json.dumps(args)], cwd=d,
                             capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)
    call.js = run_js
    return call


# ---- payload builders (shapes taken from a real Hermes 0.22 desktop) ----------------------------------------

def profile(name, *, section=None, default=False, title=None):
    meta = {}
    if section or title:
        meta["hermes-bots"] = {k: v for k, v in {"sectionName": section, "title": title}.items() if v}
    return {"name": name, "is_default": default, "display_name": name, "ui_meta": meta}


def chat(cid, cwd, *, profile_name="web", title="a chat", source="desktop", last=1000.0, branch="main", root=None,
         messages=2, **extra):
    return {"id": cid, "profile": profile_name, "source": source, "title": title, "cwd": cwd, "git_branch": branch,
            "git_repo_root": root if root is not None else cwd, "message_count": messages, "last_active": last,
            "started_at": last, "hidden": False, "archived": False, **extra}


SQUADS_HOME = [
    profile("default", default=True),
    profile("builder", section="Managers"),
    profile("jobs", section="Managers"), profile("marketing", section="Managers"), profile("web", section="Managers"),
    profile("jobs-writer", section="Jobs"), profile("jobs-scout", section="Jobs"),
    profile("web-frontend", section="Web"), profile("marketing-ads", section="Marketing"),
    profile("side-project", section="Personal"),
    profile("scratch"),
]


# ---- which bots show ----------------------------------------------------------------------------------------

def test_workers_never_show_and_the_talkable_bots_come_first(model):
    bots = model("visibleBots", SQUADS_HOME, {"scratch": 9}, {})
    assert [b["name"] for b in bots] == ["default", "builder", "jobs", "marketing", "web", "scratch"]
    assert [b["role"] for b in bots] == ["default", "builder", "manager", "manager", "manager", "other"]
    assert bots[-1]["other"] is True and not any(b["other"] for b in bots[:-1])


def test_a_worker_somebody_chats_with_is_listed_under_other_bots(model):
    bots = model("visibleBots", SQUADS_HOME, {"jobs-writer": 1}, {})
    names = {b["name"]: b for b in bots}
    assert "jobs-writer" in names and names["jobs-writer"]["other"] is True
    assert "jobs-scout" not in names and "web-frontend" not in names


def test_hidden_pinned_and_manual_order_preferences(model):
    prefs = {"hidden": ["marketing"], "pinned": ["web-frontend"], "order": ["web", "default"]}
    bots = model("visibleBots", SQUADS_HOME, {}, prefs)
    names = [b["name"] for b in bots]
    assert "marketing" not in names
    assert names[:2] == ["web", "default"], "a manual order wins over the role order"
    assert "web-frontend" in names and next(b for b in bots if b["name"] == "web-frontend")["other"] is False


def test_squad_identity_beats_the_section_stamp(model):
    p = profile("ops", section="Whatever")
    p["ui_meta"]["hermes-squads"] = {"role": "manager", "name": "Operations"}
    bots = model("visibleBots", [p], {}, {})
    assert bots[0]["role"] == "manager" and bots[0]["title"] == "Operations"


def test_a_squad_without_a_manager_groups_its_bots_under_its_section(model):
    """A local squad that has bots but no manager yet (its own Desktop section) shows as one group."""
    home = SQUADS_HOME + [profile("shopbot", section="Storefronts"), profile("shop-ads", section="Storefronts")]
    bots = model("visibleBots", home, {"shopbot": 1, "shop-ads": 3}, {})
    by = {b["name"]: b for b in bots}
    assert by["shopbot"]["group"] == "Storefronts" and by["shop-ads"]["group"] == "Storefronts"
    assert by["web"]["group"] == "" and by["default"]["group"] == ""


def test_a_section_holding_one_bot_puts_that_bot_on_the_first_level(model):
    """A hand-made bot filed alone under its company's section (Acme > acmebot) is no squad: it shows beside the
    managers, not as a group with one member, nor under Other bots."""
    home = SQUADS_HOME + [profile("acmebot", section="Acme")]
    bots = model("visibleBots", home, {"acmebot": 4, "side-project": 1}, {})
    by = {b["name"]: b for b in bots}
    assert by["acmebot"]["group"] == "" and by["acmebot"]["other"] is False
    assert by["side-project"]["group"] == "" and by["side-project"]["other"] is False


def test_a_worker_of_a_squad_that_has_a_manager_is_not_a_group(model):
    bots = model("visibleBots", SQUADS_HOME, {"jobs-writer": 1}, {})
    assert next(b for b in bots if b["name"] == "jobs-writer")["group"] == "", "Jobs has a manager"


def test_icons_read_what_a_bot_does_and_an_explicit_choice_wins(model):
    assert model("iconFor", {"name": "web", "title": "Web manager"}) == "globe"
    assert model("iconFor", {"name": "shop", "title": "Ecommerce manager"}) == "shopping-bag"
    assert model("iconFor", {"name": "x", "title": "Data reports"}) == "chart-line"
    assert model("iconFor", {"name": "zzz", "title": "Zzz"}) == "bot"
    assert model("iconFor", {"name": "web", "title": "Web"}, {"web": "rocket"}) == "rocket"
    assert model("groupIconFor", "Storefronts") == "store", "a squad of online shops reads as a storefront"
    assert model("groupIconFor", "Personal") == "users"
    assert model("groupIconFor", "Storefronts", {"group:Storefronts": "package"}) == "package"


def test_every_icon_the_model_can_pick_ships_in_the_plugin():
    text = PLUGIN.read_text(encoding="utf-8")
    shipped = set(re.findall(r'^\s*"([a-z-]+)": "<', text[text.index("const LUCIDE = "):text.index("const ICON_TINT")], re.M))
    src = _model_source()
    tables = src[src.index("const ICON_BY_KEY"):src.index("function iconFor")]
    picked = set(re.findall(r": '([a-z-]+)'", tables.split("\n")[0])) | set(re.findall(r"/[a-z]*, '([a-z-]+)'\]", tables))
    picked |= {"bot", "users", "store"}
    assert len(picked) >= 10
    assert picked <= shipped, picked - shipped


# ---- what needs you: working and unread chats ---------------------------------------------------------------

SITES = ["/w/seculus", "/w/mondaine", "/w/timex", "/w/nordic", "/w/shared"]


def many_folders_tree(model, chats, worktrees=None):
    project = {"id": "p1", "name": "Storefronts", "folders": [{"path": p, "label": Path(p).name, "is_primary": i == 0}
                                                             for i, p in enumerate(SITES)]}
    return model("buildBotTree", {"name": "web"}, [project], chats, worktrees or {})["projects"][0]


def test_a_chat_with_a_running_turn_is_working_and_an_unread_one_waits_until_you_open_it(model):
    running = chat("c1", "/w/seculus")
    answered = chat("c2", "/w/seculus", unread=True)
    quiet = chat("c3", "/w/seculus")
    assert model("chatState", running, {"live": ["c1"]}) == "working"
    assert model("chatState", answered, {}) == "unread"
    assert model("chatState", quiet, {}) == ""
    assert model("chatState", answered, {"focused": "c2"}) == "current", "the chat you are reading is not unread, yet stays listed"
    assert model("chatState", {**answered, "id": "c1"}, {"live": ["c1"]}) == "working", "working outranks unread"


def test_a_chat_that_finished_while_you_were_elsewhere_counts_even_before_the_backend_says_so(model):
    """Desktop keeps its own finished-while-away marker; the backend flag lags or never comes."""
    assert model("chatState", chat("n1", "/w/nordic"), {"unread": ["n1"]}) == "unread"
    assert model("chatState", chat("n1", "/w/nordic"), {"unread": ["other"]}) == ""
    assert model("chatState", chat("n1", "/w/nordic"), {"unread": ["n1"], "focused": "n1"}) == "current"


def test_paths_from_any_os_end_in_their_own_name(model):
    assert model("isEnvFile", model("baseName", "C:\\work\\shop\\.env.local")) is True


def test_the_digest_lists_only_what_needs_you_loudest_first_with_where_it_lives(model):
    chats = [chat("a", "/w/seculus", title="PR 74", last=100.0),
             chat("b", "/w/mondaine", title="Landing", last=300.0, unread=True),
             chat("c", "/w/timex", title="Quiet one", last=900.0),
             chat("d", "/w/mondaine", title="Bugs 267", last=200.0)]
    project = many_folders_tree(model, chats)
    items = model("activeIn", project["folders"], {"live": ["d"]})
    assert [(x["session"]["id"], x["state"], Path(x["folder"]["path"]).name) for x in items] == [
        ("d", "working", "mondaine"), ("b", "unread", "mondaine")], "working first, the quiet and the plain chats left out"


def test_a_project_with_many_folders_opens_as_a_digest_and_a_small_one_opens_whole(model):
    big = many_folders_tree(model, [chat("a", "/w/seculus")])
    small = model("buildBotTree", {"name": "web"}, [{"id": "p2", "name": "Solo", "folders": [{"path": "/w/solo"}]}],
                  [chat("z", "/w/solo")], {})["projects"][0]
    assert model("projectOpensWide", big) is False
    assert model("projectOpensWide", small) is True


def test_the_closed_project_row_lists_the_pending_chats_of_every_folder_so_no_folder_needs_opening(model):
    """The shortcut list under a closed many-folder project: what works, what is unread, and the chat in view,
    wherever they live; quiet chats stay inside their folded folders."""
    chats = [chat("a", "/w/seculus", unread=True, last=500.0), chat("b", "/w/timex", last=900.0),
             chat("c", "/w/nordic", last=100.0), chat("d", "/w/shared", last=50.0)]
    project = many_folders_tree(model, chats)
    digest = model("projectDigest", project, {"live": ["c"], "focused": "d"}, False)
    assert [(x["session"]["id"], x["state"], Path(x["folder"]["path"]).name) for x in digest] == [
        ("c", "working", "nordic"), ("a", "unread", "seculus"), ("d", "current", "shared")]
    assert [x["session"]["id"] for x in model("needsYou", digest)] == ["c", "a"], "a folded folder signals only what needs you"


def test_a_folded_bot_lists_every_pending_chat_with_where_it_lives_worktrees_and_loose_chats_included(model):
    """Shortcuts at the bot level: no bot, project or folder to open to reach a chat that needs you."""
    shop = {"id": "p1", "name": "Storefronts", "folders": [{"path": p, "is_primary": i == 0} for i, p in enumerate(SITES)]}
    solo = {"id": "p2", "name": "Docs", "folders": [{"path": "/w/docs"}]}
    wts = {"/w/timex": [{"path": "/w/timex", "branch": "main", "isMain": True},
                        {"path": "/w/timex/.worktrees/feat-x", "branch": "feat/x", "isMain": False}]}
    chats = [chat("wt", "/w/timex/.worktrees/feat-x", root="/w/timex", branch="feat/x", unread=True, last=800.0),
             chat("dc", "/w/docs", last=700.0), chat("q", "/w/nordic", last=999.0),
             chat("lo", "/elsewhere", unread=True, last=100.0)]
    tree = model("buildBotTree", {"name": "web"}, [shop, solo], chats, wts)
    digest = model("botDigest", tree, {"live": ["dc"]})
    assert [(x["session"]["id"], x["state"]) for x in digest] == [("dc", "working"), ("wt", "unread"), ("lo", "unread")]
    assert [model("whereOf", x) for x in digest] == ["Docs", "Storefronts · timex · feat-x", ""]


def test_a_closed_single_folder_project_still_lists_what_needs_you(model):
    small = model("buildBotTree", {"name": "web"}, [{"id": "p2", "name": "Solo", "folders": [{"path": "/w/solo"}]}],
                  [chat("z", "/w/solo", unread=True), chat("y", "/w/solo")], {})["projects"][0]
    assert [x["session"]["id"] for x in model("projectDigest", small, {}, False)] == ["z"]


def test_env_files_are_the_ones_people_edit_never_the_templates(model):
    """The same files Desktop's viewer blocks (any `.env.<suffix>` but the shared templates), so a double-click on one
    never ends in "Preview unavailable"."""
    for name in [".env", ".env.local", ".env.production", ".env.dev-2", ".env.development.local", ".env.production.local"]:
        assert model("isEnvFile", name) is True, name
    for name in [".env.example", ".env.sample", ".env.template", ".env.dist", "env", ".envrc", "x.env", ".env.", ".env/x"]:
        assert model("isEnvFile", name) is False, name


def test_next_pending_walks_every_bot_loudest_first_and_wraps(model):
    """The shortcut that jumps between chats needing you: working first, then unread, across bots, then around."""
    shop = {"id": "p1", "name": "Storefronts", "folders": [{"path": p, "is_primary": i == 0} for i, p in enumerate(SITES)]}
    web = model("buildBotTree", {"name": "web", "title": "Web"}, [shop],
                [chat("w1", "/w/seculus", unread=True, last=500.0), chat("w2", "/w/timex", last=900.0)], {})
    jobs = model("buildBotTree", {"name": "jobs", "title": "Jobs"}, [],
                 [chat("j1", "/x/cv", profile_name="jobs", last=700.0), chat("j2", "/x/cv", profile_name="jobs", unread=True, last=800.0)], {})
    items = model("pendingAcross", [web, jobs], {"live": ["j1"], "focused": "w2"})
    assert [(x["session"]["id"], x["bot"]["name"]) for x in items] == [("j1", "jobs"), ("j2", "jobs"), ("w1", "web")], \
        "working before unread, newest first, the quiet chat in view left out"
    assert model("nextPending", items, "j1")["session"]["id"] == "j2"
    assert model("nextPending", items, "w1")["session"]["id"] == "j1", "wraps to the first"
    assert model("nextPending", items, "elsewhere")["session"]["id"] == "j1"
    assert model("nextPending", [], "j1") is None


def test_folder_glyphs_tell_the_main_folder_a_repo_and_a_plain_folder_apart(model):
    assert model("folderIcon", {"primary": True}, True) == "house"
    assert model("folderIcon", {"primary": False}, True) == "folder-git-2"
    assert model("folderIcon", {"primary": False}, False) == "folder"


def test_a_project_carries_its_own_desktop_icon_and_colour_and_folders_know_they_are_repos(model):
    project = {"id": "p1", "name": "Shop", "icon": "rocket", "color": "hsl(30 70% 65%)",
               "folders": [{"path": "/w/a", "is_primary": True}, {"path": "/w/b"}]}
    tree = model("buildBotTree", {"name": "web"}, [project], [], {"/w/a": [{"path": "/w/a", "branch": "main", "isMain": True}]})
    p = tree["projects"][0]
    assert (p["icon"], p["color"]) == ("rocket", "hsl(30 70% 65%)")
    assert [f["repo"] for f in p["folders"]] == [True, False]


def test_a_single_folder_project_has_no_shortcut_list_it_shows_whole(model):
    small = model("buildBotTree", {"name": "web"}, [{"id": "p2", "name": "Solo", "folders": [{"path": "/w/solo"}]}],
                  [chat("z", "/w/solo", unread=True)], {})["projects"][0]
    assert model("projectDigest", small, {}) == []


def test_a_worktree_chat_is_found_inside_its_folder_lane(model):
    chats = [chat("w1", "/w/timex/.worktrees/feat-x", root="/w/timex", branch="feat/x", unread=True)]
    wts = {"/w/timex": [{"path": "/w/timex", "branch": "main", "isMain": True},
                        {"path": "/w/timex/.worktrees/feat-x", "branch": "feat/x", "isMain": False}]}
    items = model("activeIn", many_folders_tree(model, chats, wts)["folders"], {})
    assert len(items) == 1 and items[0]["lane"]["label"] == "feat-x" and Path(items[0]["folder"]["path"]).name == "timex"


# ---- which chats count --------------------------------------------------------------------------------------

@pytest.mark.parametrize("source", ["kanban", "oneshot", "cron", "subagent", "discord"])
def test_machine_made_chats_are_not_human_chats(model, source):
    assert model("isHumanChat", chat("c", "/w", source=source), 5000.0) is False


def test_hidden_archived_and_stale_empty_chats_are_dropped_but_a_fresh_one_shows(model):
    now = 10000.0
    assert model("isHumanChat", chat("a", "/w", hidden=True), now) is False
    assert model("isHumanChat", chat("a", "/w", archived=True), now) is False
    assert model("isHumanChat", chat("a", "/w", messages=0, title="", last=now - 3600), now) is False
    assert model("isHumanChat", chat("a", "/w", messages=0, title="", last=now - 30), now) is True, "just started"
    assert model("isHumanChat", chat("a", "/w", messages=0, title="Named", last=now - 3600), now) is True


# ---- the tree: bot -> project -> folder -> lane -> chat ----------------------------------------------------

SITE, API = "/work/shop/site", "/work/shop/api"
BOT = {"name": "web", "title": "Web", "role": "manager", "other": False}
SHOP = {"id": "p_shop", "name": "Shop", "archived": False,
        "folders": [{"path": SITE, "label": "site", "is_primary": True}, {"path": API, "label": "api", "is_primary": False}]}
WORKTREES = {
    SITE: [{"path": SITE, "branch": "main", "isMain": True},
           {"path": SITE + "/.worktrees/checkout", "branch": "hermes/checkout", "isMain": False},
           {"path": "/elsewhere/site-hotfix", "branch": "hotfix/pay", "isMain": False}],
    API: [{"path": API, "branch": "develop", "isMain": True}],
}


def tree(model, chats, projects=None, worktrees=None):
    return model("buildBotTree", BOT, projects if projects is not None else [SHOP], chats,
                 WORKTREES if worktrees is None else worktrees)


def lanes_of(t, folder_label):
    project = t["projects"][0]
    return next(f for f in project["folders"] if f["label"] == folder_label)["lanes"]


def test_a_project_with_two_folders_each_with_its_own_worktrees(model):
    chats = [
        chat("m1", SITE, title="main work", last=3000),
        chat("w1", SITE + "/.worktrees/checkout", title="checkout work", branch="hermes/checkout", root=SITE, last=5000),
        chat("a1", API, title="api work", branch="develop", last=2000),
    ]
    t = tree(model, chats)
    assert [p["name"] for p in t["projects"]] == ["Shop"] and t["loose"] == []
    site, api = lanes_of(t, "site"), lanes_of(t, "api")
    assert [(lane["label"], lane["main"]) for lane in site] == [("main", True), ("checkout", False), ("site-hotfix", False)]
    assert site[0]["branch"] == "main" and site[1]["branch"] == "hermes/checkout"
    assert [s["id"] for s in site[0]["sessions"]] == ["m1"] and [s["id"] for s in site[1]["sessions"]] == ["w1"]
    assert site[2]["sessions"] == [], "a worktree nobody chats in is still a lane, ready for its first chat"
    assert [(lane["label"], len(lane["sessions"])) for lane in api] == [("main", 1)]
    assert api[0]["branch"] == "develop"


def test_a_chat_in_a_worktree_outside_the_folder_still_belongs_to_the_repo(model):
    t = tree(model, [chat("h1", "/elsewhere/site-hotfix", branch="hotfix/pay", root=SITE, title="hotfix")])
    lane = next(lane for lane in lanes_of(t, "site") if lane["label"] == "site-hotfix")
    assert [s["id"] for s in lane["sessions"]] == ["h1"] and t["loose"] == []


def test_a_worktree_chat_lands_in_its_lane_before_git_has_answered(model):
    """The list of worktrees arrives after the tree paints; a `.worktrees/<name>` cwd must not wait for it."""
    t = tree(model, [chat("w1", API + "/.worktrees/auth-fix", branch="fix/auth", root=API)], worktrees={})
    lanes = lanes_of(t, "api")
    assert [(lane["label"], lane["main"], lane["branch"]) for lane in lanes] == [("main", True, ""), ("auth-fix", False, "fix/auth")]
    assert [s["id"] for s in lanes[1]["sessions"]] == ["w1"]


def test_chats_outside_every_project_stay_loose_and_projects_sort_by_activity(model):
    other = {"id": "p_docs", "name": "Docs", "archived": False, "folders": [{"path": "/work/docs", "is_primary": True}]}
    chats = [chat("d1", "/work/docs", last=9000), chat("s1", SITE, last=100), chat("x1", "/tmp/scratch", title="scratch", last=50)]
    t = tree(model, chats, projects=[SHOP, other])
    assert [p["name"] for p in t["projects"]] == ["Docs", "Shop"]
    assert [s["id"] for s in t["loose"]] == ["x1"]


def test_an_archived_project_is_gone_and_its_chats_become_loose(model):
    t = tree(model, [chat("s1", SITE)], projects=[{**SHOP, "archived": True}])
    assert t["projects"] == [] and [s["id"] for s in t["loose"]] == ["s1"]


def test_the_deepest_folder_claims_a_chat_and_no_chat_is_listed_twice(model):
    nested = {"id": "p_n", "name": "Mono", "archived": False,
              "folders": [{"path": "/mono", "is_primary": True}, {"path": "/mono/packages/ui", "is_primary": False}]}
    t = tree(model, [chat("u1", "/mono/packages/ui/src", root="/mono"), chat("r1", "/mono/tools", root="/mono")], projects=[nested], worktrees={})
    ui = next(f for f in t["projects"][0]["folders"] if f["path"] == "/mono/packages/ui")
    root = next(f for f in t["projects"][0]["folders"] if f["path"] == "/mono")
    assert [s["id"] for lane in ui["lanes"] for s in lane["sessions"]] == ["u1"]
    assert [s["id"] for lane in root["lanes"] for s in lane["sessions"]] == ["r1"]


def test_newest_chat_first_and_busiest_worktree_before_quiet_ones(model):
    chats = [chat("o", SITE, last=10), chat("n", SITE, last=90),
             chat("q", SITE + "/.worktrees/checkout", root=SITE, last=20)]
    site = lanes_of(tree(model, chats), "site")
    assert [s["id"] for s in site[0]["sessions"]] == ["n", "o"]
    assert site[0]["main"] is True and site[1]["label"] == "checkout"


def test_kanban_worker_checkouts_are_not_lanes_unless_somebody_chats_there(model):
    wts = {SITE: [{"path": SITE, "branch": "main", "isMain": True},
                  {"path": SITE + "/.worktrees/t_ab12cd34", "branch": "kanban/t_ab12cd34", "isMain": False},
                  {"path": SITE + "/.worktrees/checkout", "branch": "hermes/checkout", "isMain": False}]}
    one_folder = {**SHOP, "folders": [SHOP["folders"][0]]}
    t = tree(model, [chat("m1", SITE)], projects=[one_folder], worktrees=wts)
    assert [lane["label"] for lane in lanes_of(t, "site")] == ["main", "checkout"]
    t = tree(model, [chat("k1", SITE + "/.worktrees/t_ab12cd34", root=SITE)], projects=[one_folder], worktrees=wts)
    assert "t_ab12cd34" in [lane["label"] for lane in lanes_of(t, "site")], "a chat opened in it keeps it visible"
    assert model("isKanbanWorktree", "/r/.worktrees/t_0f9e") is True
    assert model("isKanbanWorktree", "/r/.worktrees/t_feature") is False


def test_an_unknown_squad_role_sorts_after_the_known_ones_deterministically(model):
    odd = profile("mid", section="Jobs")
    odd["ui_meta"]["hermes-squads"] = {"role": "worker"}
    ps = [odd, profile("zed", default=True), profile("alpha", section="Managers")]
    for order in (ps, list(reversed(ps))):
        assert [b["name"] for b in model("visibleBots", order, {"mid": 1}, {})] == ["zed", "alpha", "mid"]


# ---- search -------------------------------------------------------------------------------------------------

def _filtered(model, query, chats=None):
    chats = chats or [chat("m1", SITE, title="fix the login form", last=3000),
                      chat("w1", SITE + "/.worktrees/checkout", title="stripe webhooks", branch="hermes/checkout", root=SITE, last=5000),
                      chat("x1", "/tmp/s", title="grocery list", last=10)]
    return model("filterTree", tree(model, chats), query)


def test_search_keeps_only_the_matching_chats_inside_their_lane(model):
    t = _filtered(model, "stripe")
    site = lanes_of(t, "site")
    assert [lane["label"] for lane in site] == ["checkout"] and [s["id"] for s in site[0]["sessions"]] == ["w1"]
    assert t["loose"] == []


def test_a_project_or_bot_name_keeps_everything_under_it(model):
    assert len(lanes_of(_filtered(model, "shop"), "site")) == 3
    assert _filtered(model, "web")["loose"] and len(_filtered(model, "web")["projects"]) == 1


def test_search_by_branch_finds_the_lane_and_nothing_matching_is_null(model):
    t = _filtered(model, "hotfix/pay")
    assert [lane["label"] for lane in lanes_of(t, "site")] == ["site-hotfix"]
    assert _filtered(model, "zzz-nothing") is None


# ---- previews remembered per chat ---------------------------------------------------------------------------

def test_a_reopened_preview_moves_to_the_front_without_a_duplicate(model):
    m = {}
    for i, url in enumerate(["/a.html", "/b.html", "/a.html"]):
        m = model("rememberPreview", m, "chat1", {"url": url, "label": url, "at": i})
    assert [p["url"] for p in m["chat1"]] == ["/a.html", "/b.html"]


def test_previews_are_capped_per_chat_and_the_oldest_chats_are_evicted(model):
    m = {}
    for i in range(12):
        m = model("rememberPreview", m, "chat1", {"url": f"/p{i}.html", "at": i}, 5, 200)
    assert [p["url"] for p in m["chat1"]] == [f"/p{i}.html" for i in (11, 10, 9, 8, 7)]
    m = {}
    for i in range(6):
        m = model("rememberPreview", m, f"c{i}", {"url": "/x.html", "at": i}, 5, 3)
    assert sorted(m) == ["c3", "c4", "c5"], "the least recently used chats go first"


def test_a_preview_without_a_chat_or_an_url_is_not_remembered(model):
    assert model("rememberPreview", {}, "", {"url": "/a.html"}) == {}
    assert model("rememberPreview", {}, "chat1", {"url": ""}) == {}


# ---- small helpers ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("delta,expected", [(10, "now"), (300, "5m"), (3590, "59m"), (7200, "2h"), (86390, "23h"),
                                            (86400 * 3, "3d"), (86400 * 65, "2mo")])
def test_short_age(model, delta, expected):
    assert model("shortAge", 1_000_000 - delta, 1_000_000) == expected
    assert model("shortAge", 0, 1_000_000) == ""


def test_worktree_names_are_slugged_for_git_and_the_filesystem(model):
    assert model("slugify", "Rediseño: Checkout (v2)!") == "rediseno-checkout-v2"
    assert model("slugify", "  ---  ") == ""
    assert len(model("slugify", "x" * 200)) == 48


# ---- the load contract of a disk plugin ---------------------------------------------------------------------

def test_the_plugin_imports_only_what_the_desktop_resolves():
    text = PLUGIN.read_text(encoding="utf-8")
    specs = set(re.findall(r"^import .* from '([^']+)'", text, re.M))
    assert specs <= {"@hermes/plugin-sdk", "react", "react/jsx-runtime"}, specs
    assert not re.search(r"\bawait import\(|\bimport\(", text), "dynamic imports fail the load"


def test_the_plugin_has_no_jsx_and_no_hardcoded_colors():
    text = PLUGIN.read_text(encoding="utf-8")
    assert not re.search(r"return\s*\(\s*<[A-Za-z]", text) and not re.search(r"=>\s*<[A-Za-z]", text), "disk plugins load uncompiled"
    css = text[text.index("const CSS = `"):text.index("export default")]
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\(", css), "colors come from theme variables"


def test_the_model_markers_exist_once_and_the_model_has_no_imports():
    text = PLUGIN.read_text(encoding="utf-8")
    assert text.count("MODEL (pure)") == 2
    assert "import " not in _model_source()


# ---- squads at work: boards, timeline, issues, the bell, cards in replies -----------------------------------
# Shapes from a real Hermes 0.22 kanban dashboard API: /board columns of task rows, /tasks/<id> runs, /diagnostics.

NOW = 1_793_000_000


def task(tid, status, *, assignee="web-frontend", created=NOW - 7200, started=None, completed=None, block_kind=None,
         parents=0, runs=None, title=None, summary=None):
    return {"id": tid, "title": title or f"card {tid}", "status": status, "assignee": assignee, "created_at": created,
            "started_at": started, "completed_at": completed, "block_kind": block_kind,
            "link_counts": {"parents": parents, "children": 0}, "latest_summary": summary,
            **({"runs": runs} if runs is not None else {})}


def run(profile, start, end, outcome, summary=None):
    return {"profile": profile, "started_at": start, "ended_at": end, "outcome": outcome, "status": outcome,
            "summary": summary}


def board(*tasks):
    cols = {}
    for t in tasks:
        cols.setdefault(t["status"], []).append(t)
    names = ["triage", "todo", "scheduled", "ready", "running", "blocked", "review", "done"]
    return {"columns": [{"name": n, "tasks": cols.get(n, [])} for n in names]}


def test_the_board_digest_counts_columns_and_only_blocks_a_human_answers(model):
    b = board(task("t_aa01", "blocked", block_kind="needs_input"), task("t_aa02", "blocked", block_kind="dependency"),
              task("t_aa03", "blocked", block_kind="transient"), task("t_aa04", "blocked", block_kind="capability"),
              task("t_aa05", "blocked"), task("t_aa06", "review"), task("t_aa07", "running"), task("t_aa08", "todo"),
              task("t_aa09", "ready"), task("t_aa10", "done"))
    d = model("boardDigest", b)
    assert (d["blocked"], d["review"], d["running"], d["queued"], d["done"]) == (5, 1, 1, 2, 1)
    assert [t["id"] for t in d["needsYou"]] == ["t_aa01", "t_aa04", "t_aa05"]


def test_a_manager_finds_its_board_by_name_then_by_its_own_workers(model):
    boards = [{"slug": "web", "assignees": ["web", "web-qa"]},
              {"slug": "shopfront", "assignees": ["shop", "shop-scout"]},
              {"slug": "default", "assignees": ["builder", "default"]}]
    assert model("boardForBot", "web", boards)["slug"] == "web"
    assert model("boardForBot", "shop", boards)["slug"] == "shopfront"
    # the builder takes cards on `default` but has no workers there: that board is not its squad's
    assert model("boardForBot", "builder", boards) is None


def test_a_board_belongs_to_the_bots_that_took_its_cards_not_to_every_profile(model):
    """The real /board payload lists every profile on disk under `assignees`; the default board would then claim
    every manager. Only the cards say whose board it is."""
    default = {**board(task("t_ab01", "done", assignee="builder"), task("t_ab02", "done", assignee="default")),
               "assignees": ["builder", "default", "shop", "shop-scout", "web", "web-qa"]}
    shopb = board(task("t_ab03", "blocked", assignee="shop-scout"), task("t_ab04", "done", assignee="shop"))
    boards = [{"slug": "default", "assignees": model("taskAssignees", default)},
              {"slug": "shopfront", "assignees": model("taskAssignees", shopb)}]
    assert boards[0]["assignees"] == ["builder", "default"]
    assert model("boardForBot", "shop", boards)["slug"] == "shopfront"


def test_the_timeline_draws_each_run_in_its_bots_lane_and_the_wait_before_it(model):
    t1 = task("t_bb01", "done", assignee="web-frontend", created=NOW - 9000,
              runs=[run("web-frontend", NOW - 8000, NOW - 7000, "crashed"),
                    run("web-frontend", NOW - 6900, NOW - 6000, "completed")])
    t2 = task("t_bb02", "review", assignee="web-qa", created=NOW - 5000,
              runs=[run("web-qa", NOW - 4000, None, None)])
    t3 = task("t_bb03", "todo", assignee="web-frontend", created=NOW - 3000, runs=[])
    tl = model("timelineOf", [t1, t2, t3], NOW, NOW - 86400)
    lanes = {l["name"]: l["bars"] for l in tl["lanes"]}
    assert set(lanes) == {"web-frontend", "web-qa"}
    fe = lanes["web-frontend"]
    assert [b["kind"] for b in fe] == ["wait", "run", "run", "wait"]
    assert fe[0] == {**fe[0], "start": NOW - 9000, "end": NOW - 8000}
    assert [b.get("tone") for b in fe if b["kind"] == "run"] == ["fail", "done"]
    assert fe[-1]["open"] and fe[-1]["end"] == NOW  # never picked up yet: waits until now
    qa = lanes["web-qa"]
    assert qa[-1]["open"] and qa[-1]["end"] == NOW and qa[-1]["tone"] == "run"


def test_the_timeline_keeps_only_what_touches_the_window(model):
    old = task("t_cc01", "done", created=NOW - 900_000, runs=[run("web-qa", NOW - 800_000, NOW - 799_000, "completed")])
    tl = model("timelineOf", [old], NOW, NOW - 86400)
    assert tl["lanes"] == []


def test_issues_put_core_diagnostics_first_and_add_only_what_timing_shows(model):
    crashy = task("t_dd01", "blocked", assignee="jobs-writer", block_kind="needs_input",
                  runs=[run("jobs-writer", NOW - 9000, NOW - 8900, "crashed"),
                        run("jobs-writer", NOW - 8000, NOW - 7900, "crashed")])
    slow = task("t_dd02", "done", assignee="jobs-scout", created=NOW - 20000,
                runs=[run("jobs-scout", NOW - 10000, NOW - 9000, "completed")])
    gated = task("t_dd03", "done", assignee="jobs-scout", created=NOW - 20000, parents=1,
                 runs=[run("jobs-scout", NOW - 10000, NOW - 9000, "completed")])
    forgotten = task("t_dd04", "blocked", assignee="jobs", block_kind="needs_input", created=NOW - 200000,
                     runs=[run("jobs", NOW - 100000, NOW - 99000, "blocked")])
    diags = [{"task_id": "t_dd01", "task_title": "Apply LinkedIn", "task_assignee": "jobs-writer",
              "diagnostics": [{"kind": "repeated_failures", "severity": "error", "title": "Agent crash x2",
                               "last_seen_at": NOW - 7900, "count": 2}]}]
    issues = model("issuesOf", [crashy, slow, gated, forgotten], diags, NOW)
    kinds = [(i["kind"], i["taskId"]) for i in issues]
    assert kinds[0] == ("repeated_failures", "t_dd01")
    # the crash core already reported is not reported twice
    assert ("run_failed", "t_dd01") not in kinds
    assert ("slow_start", "t_dd02") in kinds
    # a card that waited for its parent was not slow to start
    assert ("slow_start", "t_dd03") not in kinds
    assert ("waiting_on_you", "t_dd04") in kinds


def test_a_failed_run_core_did_not_flag_is_an_issue(model):
    t = task("t_ee01", "done", runs=[run("web-qa", NOW - 900, NOW - 800, "timed_out"),
                                      run("web-qa", NOW - 700, NOW - 600, "completed")])
    issues = model("issuesOf", [t], [], NOW)
    assert [(i["kind"], i["severity"], i["text"]) for i in issues] == [("run_failed", "warning", "timed_out")]


def test_the_bell_lists_parked_chats_then_cards_waiting_on_you(model):
    active = [{"id": "r1", "session_key": "s1", "status": "waiting", "title": "Publish the site?"},
              {"id": "r2", "session_key": "s2", "status": "working", "title": "busy"},
              {"id": "r3", "session_key": "s3", "status": "idle", "title": "quiet"}]
    chats = [{"id": "s1", "profile": "web", "title": "Bakery site"}]
    boards = [{"slug": "jobs", "digest": {"needsYou": [task("t_ff01", "blocked", assignee="jobs", block_kind="needs_input",
                                                            title="Digest: Truelogic", summary="approve?")]}}]
    items = model("bellItems", active, chats, boards)
    assert [(x["type"], x["key"]) for x in items] == [("chat", "chat:s1"), ("card", "card:jobs:t_ff01")]
    assert items[0]["profile"] == "web" and items[1]["summary"] == "approve?"
    assert model("newSince", ["chat:s1"], items) == [items[1]]


def test_the_notification_skips_what_was_already_waiting_and_names_each_new_card_once(model):
    """Opening Hermes with five cards already blocked must not fire five notifications; a card that blocks later
    fires once, and a chat asking a question never does (Desktop notifies those itself)."""
    old = {"key": "card:jobs:t_aa01", "type": "card"}
    chat = {"key": "chat:s9", "type": "chat"}
    assert model("bellFresh", None, [old, chat]) == []
    new = {"key": "card:jobs:t_aa02", "type": "card"}
    assert model("bellFresh", ["card:jobs:t_aa01"], [old, new, chat]) == [new]
    assert model("bellFresh", ["card:jobs:t_aa01", "card:jobs:t_aa02"], [old, new]) == []


def test_the_timeline_names_what_a_card_waited_for_and_where_it_sits_now(model):
    """A card gated on a parent waited on another card, not on a bot; a card blocked after its run sits blocked up to
    now in that bot's lane; a card sent back to the queue waits again."""
    gated = task("t_gg01", "done", assignee="web-qa", created=NOW - 9000, parents=1,
                 runs=[run("web-qa", NOW - 5000, NOW - 4000, "completed")])
    asks = task("t_gg02", "blocked", assignee="jobs", block_kind="needs_input", created=NOW - 2910,
                runs=[run("jobs", NOW - 2900, NOW - 2800, "blocked")])
    review = task("t_gg03", "review", assignee="web-frontend", created=NOW - 1995,
                  runs=[run("web-frontend", NOW - 1990, NOW - 1000, "review_requested")])
    tl = model("timelineOf", [gated, asks, review], NOW, NOW - 86400)
    lanes = {l["name"]: l["bars"] for l in tl["lanes"]}
    assert [(b["kind"], b["state"]) for b in lanes["web-qa"]] == [("wait", "dep"), ("run", "done")]
    assert [(b["kind"], b["state"]) for b in lanes["jobs"]] == [("run", "block"), ("state", "block")]
    assert lanes["jobs"][-1]["start"] == NOW - 2800 and lanes["jobs"][-1]["end"] == NOW and lanes["jobs"][-1]["open"]
    assert [(b["kind"], b["state"]) for b in lanes["web-frontend"]] == [("run", "review"), ("state", "review")]


def test_a_card_reads_as_one_of_the_legend_states(model):
    cases = [(task("t_hh01", "todo"), "queued"), (task("t_hh02", "todo", parents=1), "dep"),
             (task("t_hh03", "ready"), "queued"), (task("t_hh04", "running"), "run"),
             (task("t_hh05", "blocked", block_kind="needs_input"), "block"), (task("t_hh06", "review"), "review"),
             (task("t_hh07", "done"), "done")]
    for t, want in cases:
        assert model("cardState", t) == want, t["id"]


def test_cleared_bell_items_stay_cleared_until_the_card_blocks_again(model):
    """Clearing the bell hides each item; the same card blocked again (a new recurrence or run) comes back, and the
    newest card is listed first."""
    def bl(tid, started, rec=1):
        return {**task(tid, "blocked", assignee="jobs", block_kind="needs_input", started=started), "block_recurrences": rec}
    boards = [{"slug": "jobs", "digest": {"needsYou": [bl("t_ii01", NOW - 200000), bl("t_ii02", NOW - 100)]}}]
    items = model("bellItems", [], [], boards)
    assert [x["taskId"] for x in items] == ["t_ii02", "t_ii01"], "newest first"
    dismissed = {model("dismissKey", x): NOW for x in items}
    assert model("bellVisible", items, dismissed) == []
    again = [{"slug": "jobs", "digest": {"needsYou": [bl("t_ii01", NOW - 50, rec=2), bl("t_ii02", NOW - 100)]}}]
    back = model("bellVisible", model("bellItems", [], [], again), dismissed)
    assert [x["taskId"] for x in back] == ["t_ii01"]


def test_a_card_detail_shows_what_it_asks_and_its_story(model):
    events = [{"kind": "created", "created_at": NOW - 900}, {"kind": "heartbeat", "created_at": NOW - 800},
              {"kind": "claimed", "created_at": NOW - 700},
              {"kind": "blocked", "created_at": NOW - 600, "payload": {"reason": "Approve the hero copy?", "kind": "needs_input"}},
              {"kind": "commented", "created_at": NOW - 500}]
    t = task("t_jj01", "blocked", block_kind="needs_input", summary="old note")
    needs = model("cardNeeds", t, events)
    assert needs == {"reason": "Approve the hero copy?", "at": NOW - 600, "kind": "needs_input"}
    assert model("cardNeeds", t, [])["reason"] == "old note"
    # a gate filed already blocked: core writes `initial_status` as the reason; the question is the card's body
    gate = {**task("t_jj02", "blocked", block_kind="needs_input"), "body": "Founder picks A, B or C."}
    filed = [{"kind": "blocked", "created_at": NOW - 60, "payload": {"reason": "initial_status"}}]
    assert model("cardNeeds", gate, filed)["reason"] == "Founder picks A, B or C."
    asked = [{"body": "Which design, A or B?", "created_at": NOW - 30}]
    assert model("cardNeeds", gate, filed, asked)["reason"] == "Which design, A or B?"
    assert [e["kind"] for e in model("historyOf", events)] == ["blocked", "claimed", "created"]


def test_a_card_is_answered_to_its_boards_manager(model):
    assert model("boardManager", "web", ["web", "web-qa"], ["web-qa"]) == "web"
    assert model("boardManager", "shopfront", ["shop", "shop-scout"], ["shop", "shop-scout"]) == "shop"
    assert model("boardManager", "default", ["builder"], ["builder", "default"]) == ""


def test_card_directives_accept_ids_only(model):
    assert model("cardRef", {"id": "t_ab12", "board": "web"}) == {"id": "t_ab12", "board": "web"}
    assert model("cardRef", {"id": "t_ab12"}) == {"id": "t_ab12", "board": ""}
    for bad in [{"id": "ab12"}, {"id": "t_AB12"}, {"id": "t_ab12", "board": "../x"}, {"id": "t_ab12 x"},
                {"id": "t_ab12", "board": "https://evil"}, {}]:
        assert model("cardRef", bad) is None, bad
    assert model("boardRef", {"board": "jobs"}) == {"board": "jobs"}
    assert model("boardRef", {"board": "Jobs!"}) is None


def test_a_worktree_chip_reads_pr_state_and_local_changes(model):
    pr = {"branch": "feat-x", "draft": True, "number": 12, "state": "open", "title": "x", "url": "https://github.com/o/r/pull/12"}
    s = model("laneStatus", pr, {"changed": 3, "ahead": 2, "behind": 0})
    assert s == {"pr": {"number": 12, "state": "draft", "url": pr["url"], "title": "x"}, "changed": 3, "ahead": 2, "behind": 0,
                 "known": True}
    assert model("laneStatus", {**pr, "draft": False, "state": "merged"}, None)["pr"]["state"] == "merged"
    assert model("laneStatus", None, None) == {"pr": None, "changed": 0, "ahead": 0, "behind": 0, "known": False}


def _catalogs():
    """The plugin's own MESSAGES object, evaluated by node from plugin.js (no copy kept in the test)."""
    text = PLUGIN.read_text(encoding="utf-8")
    start = text.index("const MESSAGES = {")
    depth, i = 0, text.index("{", start)
    for i in range(i, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            break
    script = "const MESSAGES = " + text[text.index("{", start):i + 1] + "; console.log(JSON.stringify(MESSAGES))"
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_the_spanish_interface_has_every_string_the_english_one_has():
    m = _catalogs()
    assert set(m["en"]) == set(m["es"]), sorted(set(m["en"]) ^ set(m["es"]))
    assert all(str(v).strip() for v in m["es"].values())


def test_every_run_outcome_and_diagnostic_hermes_writes_has_a_label():
    """Outcomes from hermes_cli/kanban_db.py and diagnostic kinds from kanban_diagnostics.py (Hermes 0.22.2): a
    missing one shows as raw English in a Spanish app."""
    outcomes = ["blocked", "changes_requested", "completed", "crashed", "gave_up", "reclaimed", "review_requested",
                "scheduled", "spawn_failed", "stale", "timed_out"]
    kinds = ["block_unblock_cycling", "hallucinated_cards", "prose_phantom_refs", "repeated_crashes", "repeated_failures",
             "review_dependency_deadlock", "running_with_open_parents", "stranded_in_ready", "stuck_in_blocked",
             "triage_aux_unavailable"]
    for lang, cat in _catalogs().items():
        missing = [k for k in [f"out_{o}" for o in outcomes] + [f"iss_{k}" for k in kinds] if k not in cat]
        assert not missing, (lang, missing)


def test_a_run_that_never_started_reads_as_failed(model):
    t = task("t_kk01", "ready", runs=[run("web-qa", NOW - 900, NOW - 899, "spawn_failed")])
    lanes = model("timelineOf", [t], NOW, NOW - 86400)["lanes"]
    runs = [b for lane in lanes for b in lane["bars"] if b["kind"] == "run"]
    assert [b["state"] for b in runs] == ["fail"], lanes


def test_a_chat_waiting_in_any_bots_backend_is_listed_once(model):
    """A shared backend answers for several bots, so the primary and a bot's own route can report the same chat; the
    bot's own backend may be the only one that knows it is waiting."""
    primary = [{"id": "r1", "session_key": "s1", "status": "idle"}, {"id": "r2", "session_key": "s2", "status": "working"}]
    web = [{"id": "r1", "session_key": "s1", "status": "waiting"}, {"id": "r9", "session_key": "s9", "status": "waiting"}]
    merged = model("mergeActive", [primary, web, []])
    assert sorted((r["session_key"], r["status"]) for r in merged) == [("s1", "waiting"), ("s2", "working"), ("s9", "waiting")]


def test_a_board_that_failed_to_load_keeps_its_cards_so_nothing_renotifies(model):
    before = [{"slug": "jobs", "digest": {"needsYou": [{"id": "t_aa01"}]}}, {"slug": "web", "digest": {"needsYou": []}}]
    now = [None, {"slug": "web", "digest": {"needsYou": []}}]  # the jobs read timed out this round
    kept = model("keepLastBoards", now, ["jobs", "web"], before)
    assert [b["slug"] for b in kept] == ["jobs", "web"]
    known = [x["key"] for x in model("bellItems", [], [], before)]
    assert model("bellFresh", known, model("bellItems", [], [], kept)) == []
    # a board that is gone from the list is not kept
    assert [b["slug"] for b in model("keepLastBoards", now, ["web"], before)] == ["web"]


def test_the_timeline_reads_open_cards_and_cards_that_ended_in_the_window_newest_first(model):
    tasks = [task("t_ll01", "done", completed=NOW - 900_000), task("t_ll02", "done", completed=NOW - 100),
             task("t_ll03", "blocked", block_kind="needs_input", created=NOW - 500_000),
             {**task("t_ll04", "archived"), "completed_at": None}, task("t_ll05", "running", started=NOW - 50)]
    got = [t["id"] for t in model("windowTasks", tasks, NOW, NOW - 86400)]
    assert got == ["t_ll03", "t_ll05", "t_ll02"], "blocked first, then newest activity"


def test_a_pr_link_opens_only_over_https(model):
    pr = {"branch": "x", "draft": False, "number": 3, "state": "open", "title": "x", "url": "javascript:alert(1)"}
    assert model("laneStatus", pr, None)["pr"]["url"] == ""
    assert model("laneStatus", {**pr, "url": "https://github.com/o/r/pull/3"}, None)["pr"]["url"].startswith("https://")


def test_a_card_line_without_a_board_finds_the_board_that_holds_the_id(model):
    """A bot that filed a card without naming the board writes `::squad-task{id=...}`; asking the backend's current
    board would show "Card not found" when the card lives on its squad's board."""
    boards = [{"slug": "default", "board": board(task("t_mm01", "done"))},
              {"slug": "web", "board": board(task("t_mm02", "ready"), task("t_mm03", "blocked"))}]
    assert model("boardOfTask", "t_mm03", boards) == "web"
    assert model("boardOfTask", "t_mm99", boards) == ""


def test_an_empty_chat_is_titled_with_its_squad_then_the_bot(model):
    # managers sit in the shared "Managers" section: the squad name comes from its own stamp
    squad = {"name": "web", "title": "Web manager", "ui_meta": {"hermes-bots": {"sectionName": "Managers", "squadName": "Web"}}}
    assert model("introName", squad) == "Web"
    assert model("introName", {"name": "builder", "title": "Builder", "ui_meta": {}}) == "Builder"
    assert model("introName", {"name": "default", "title": "", "ui_meta": None}) == "default"


def test_a_cleared_chat_question_rings_again_only_after_it_stopped_waiting(model):
    """Opening a waiting chat bumps its last_active; the dismissal must not depend on it, or the row comes back while
    the same question is still open. Once the chat stops waiting, its dismissal is dropped so a new question rings."""
    waiting = [{"key": "chat:s1", "stamp": "", "type": "chat"}]
    dismissed = {model("dismissKey", waiting[0]): NOW}
    reopened = model("bellItems", [{"id": "r1", "session_key": "s1", "status": "waiting", "last_active": NOW + 5}], [], [])
    assert model("bellVisible", reopened, dismissed) == []
    assert model("staleChatDismissals", reopened, dismissed) == []
    assert model("staleChatDismissals", [], dismissed) == ["chat:s1@"]


def test_a_stuck_card_survives_the_timeline_cap_ahead_of_newer_work(model):
    tasks = [task("t_nn01", "running", started=NOW - 10), task("t_nn02", "blocked", block_kind="needs_input", created=NOW - 900_000),
             task("t_nn03", "done", completed=NOW - 20)]
    assert [t["id"] for t in model("windowTasks", tasks, NOW, NOW - 86400)][:1] == ["t_nn02"]


def test_the_empty_chat_names_the_squad_from_the_bot_the_pane_builds(model):
    """ChatIntro reads the bot `visibleBots` returns, not the raw profile: the squad name must survive that step,
    or every manager's empty chat reads "Web manager" instead of "Web"."""
    meta = {"hermes-bots": {"title": "Web manager", "sectionId": "managers", "sectionName": "Managers", "squadName": "Web"}}
    profiles = [{"name": "web", "ui_meta": meta}, {"name": "builder", "ui_meta": {"hermes-bots": {"title": "Builder"}}}]
    bots = {b["name"]: b for b in model("visibleBots", profiles, {}, {})}
    assert model("introName", bots["web"]) == "Web"
    assert model("introName", bots["builder"]) == "Builder"


# ---- quieter list: big projects, old chats, the bell, prefs from older versions --------------------------------

def _project(n):
    return {"id": "p", "name": "Shop", "folders": [{"path": f"/w/f{i}", "lanes": []} for i in range(n)]}


def test_a_project_past_three_folders_opens_in_its_own_view(model):
    assert model("projectOpensInFocus", _project(4)) is True
    assert model("projectOpensInFocus", _project(3)) is False, "three folders still unfold in the list"
    assert model("projectOpensInFocus", _project(1)) is False


def test_a_bot_lists_what_needs_you_and_its_three_newest_chats_the_rest_fold(model):
    loose = [chat(f"c{i}", "/x", last=1000.0 + i) for i in range(10)]
    attention = {"live": ["c1"], "unread": ["c0"], "focused": None}
    split = model("looseSplit", loose, attention)
    assert [s["id"] for s in split["shown"]] == ["c9", "c8", "c7", "c1", "c0"], "newest three, then what needs you"
    assert [s["id"] for s in split["rest"]] == ["c6", "c5", "c4", "c3", "c2"]
    assert model("looseSplit", loose[:2], {})["rest"] == [], "a short list shows whole"


def test_the_bell_groups_cards_by_board_newest_board_first(model):
    items = [
        {"key": "chat:a", "type": "chat", "at": 50},
        {"key": "card:omni:1", "type": "card", "board": "omni", "at": 100},
        {"key": "card:jobs:1", "type": "card", "board": "jobs", "at": 300},
        {"key": "card:omni:2", "type": "card", "board": "omni", "at": 200},
    ]
    groups = model("bellGroups", items)
    assert [g["key"] for g in groups] == ["chats", "board:jobs", "board:omni"]
    assert [x["key"] for x in groups[2]["items"]] == ["card:omni:2", "card:omni:1"]
    assert model("bellGroups", []) == []


def test_prefs_saved_by_an_older_version_get_the_new_defaults_once(model):
    defaults = {"floatSides": True, "squadsTheme": True, "hiddenNav": ["kanban:nav"], "prefsVersion": 2}
    old = {"floatSides": False, "hiddenNav": ["cron"], "hidden": ["web"]}
    up = model("upgradePrefs", old, defaults)
    assert up["floatSides"] is True and up["squadsTheme"] is True
    assert set(up["hiddenNav"]) == {"cron", "kanban:nav"} and up["hidden"] == ["web"]
    chosen = {**up, "floatSides": False, "hiddenNav": []}
    again = model("upgradePrefs", chosen, defaults)
    assert again["floatSides"] is False and again["hiddenNav"] == [], "a choice made after the upgrade is kept"
    assert model("upgradePrefs", None, defaults)["floatSides"] is True


def test_an_open_project_shows_each_chat_once_in_its_own_folder(model):
    """Opening a project drops the shortcut list: a pending chat would show twice, once as a shortcut above the
    folders and once inside its folder. Instead the folder holding it starts unfolded; quiet folders stay folded."""
    chats = [chat("a", "/w/seculus", unread=True, last=500.0), chat("b", "/w/timex", last=900.0),
             chat("c", "/w/nordic", last=100.0)]
    project = many_folders_tree(model, chats)
    attention = {"live": ["c"], "focused": None}
    assert model("projectDigest", project, attention, True) == []
    assert [x["session"]["id"] for x in model("projectDigest", project, attention, False)] == ["c", "a"]
    opens = {Path(f["path"]).name: model("folderOpensByDefault", f, attention) for f in project["folders"]}
    assert opens["seculus"] is True and opens["nordic"] is True, "a folder with a chat that needs you unfolds"
    assert opens["timex"] is False, "a quiet folder stays folded"
    focused_only = {"live": [], "focused": "b"}
    timex = next(f for f in project["folders"] if f["path"].endswith("timex"))
    assert model("folderOpensByDefault", timex, focused_only) is False, "the chat merely in view does not unfold it"


# ---- squad capabilities and project clean-up ------------------------------------------------------------------

def _stamped(name, squad, role="worker", title=None):
    p = profile(name, section="Managers" if role == "manager" else squad, title=title)
    p["ui_meta"]["hermes-bots"]["squadName"] = squad
    return p


def test_a_manager_reaches_the_capabilities_of_every_bot_of_its_squad(model):
    home = [profile("default", default=True), _stamped("jobs", "Jobs", "manager", "Jobs manager"),
            _stamped("jobs-writer", "Jobs"), _stamped("jobs-scout", "Jobs"), _stamped("web", "Web", "manager"),
            _stamped("web-qa", "Web")]
    assert [m["name"] for m in model("squadMembers", home, "jobs")] == ["jobs", "jobs-scout", "jobs-writer"]
    assert [m["name"] for m in model("squadMembers", home, "jobs-writer")][0] == "jobs-writer", "the bot asked about leads"
    assert model("squadMembers", home, "default") == [] and model("squadMembers", home, "ghost") == []


def test_an_unstamped_fleet_is_matched_through_the_manager_title_and_its_section(model):
    home = [profile("acme", section="Managers", title="Acme shop manager"), profile("acme-ads", section="Acme shop"),
            profile("acme-ops", section="Acme shop"), profile("other", section="Elsewhere")]
    assert [m["name"] for m in model("squadMembers", home, "acme")] == ["acme", "acme-ads", "acme-ops"]
    assert model("squadMembers", [profile("solo", section="Managers", title="Solo")], "solo") == []


def _lane_project(model, chats, worktrees):
    return model("buildBotTree", {"name": "web"}, [{"id": "p", "name": "Shop", "folders": [{"path": "/w/shop", "is_primary": True}]}],
                 chats, worktrees)["projects"][0]


WT = {"/w/shop": [{"path": "/w/shop", "branch": "main", "isMain": True},
                  {"path": "/w/shop/.worktrees/done", "branch": "feat/done", "isMain": False},
                  {"path": "/w/shop/.worktrees/idea", "branch": "feat/idea", "isMain": False},
                  {"path": "/w/shop/.worktrees/dirty", "branch": "feat/dirty", "isMain": False},
                  {"path": "/w/shop/.worktrees/wip", "branch": "feat/wip", "isMain": False},
                  {"path": "/w/shop/.worktrees/t_0a1b2c", "branch": "kanban/t", "isMain": False}]}


def _st(state=None, changed=0, ahead=0, known=True):
    return {"pr": {"number": 1, "state": state, "url": "", "title": ""} if state else None, "changed": changed, "ahead": ahead,
            "behind": 0, "known": known}


def test_clean_up_offers_only_worktrees_with_nothing_to_lose_and_ticks_merged_or_idle_ones(model):
    now = 1_000_000.0
    day = 86400
    wd = "/w/shop/.worktrees/"
    chats = [chat("i", wd + "idea", root="/w/shop", branch="feat/idea", last=now - 3 * day),
             chat("n", wd + "new", root="/w/shop", branch="feat/new", last=now - 3600)]
    wts = {"/w/shop": WT["/w/shop"] + [{"path": wd + "new", "branch": "feat/new", "isMain": False},
                                       {"path": wd + "bare", "branch": "feat/bare", "isMain": False}]}
    project = _lane_project(model, chats, wts)
    statuses = {wd + "done": _st("merged"), wd + "idea": _st(), wd + "new": _st(), wd + "bare": _st(),
                wd + "dirty": _st("merged", changed=2), wd + "wip": _st("open"), wd + "t_0a1b2c": _st("merged")}
    plan = model("cleanupPlan", project, statuses, {}, now)
    got = {w["label"]: (w["reason"], w["pre"]) for w in plan["worktrees"]}
    assert got == {"done": ("merged", True), "idea": ("idle", True), "new": ("recent", False), "bare": ("nochats", False)}, \
        "dirty, open-PR and kanban checkouts are never listed; a recent or chatless one is offered unticked"
    unpushed = model("cleanupPlan", project, {wd + "done": _st("merged", ahead=1)}, {}, now)
    assert unpushed["worktrees"] == [], "unpushed commits keep a worktree"
    assert model("cleanupPlan", project, {}, {}, now)["worktrees"] == [], "a checkout whose status is unknown is kept"


def test_clean_up_archives_idle_old_chats_and_the_chats_of_a_removed_worktree(model):
    now = 1_000_000.0
    day = 86400
    chats = [chat("old", "/w/shop", last=now - 3 * day), chat("fresh", "/w/shop", last=now - 1 * day),
             chat("pin", "/w/shop", last=now - 30 * day, pinned=True), chat("busy", "/w/shop", last=now - 20 * day),
             chat("unr", "/w/shop", last=now - 20 * day, unread=True),
             chat("inwt", "/w/shop/.worktrees/done", root="/w/shop", branch="feat/done", last=now - 1 * day)]
    plan = model("cleanupPlan", _lane_project(model, chats, WT), {"/w/shop/.worktrees/done": _st("merged")}, {"live": ["busy"]}, now)
    by = {c["session"]["id"]: c["pre"] for c in plan["chats"]}
    assert by == {"old": True, "inwt": True}, "pinned, working, unread and chats used in the last 2 days stay"
    keep = model("cleanupPlan", _lane_project(model, chats, WT), {"/w/shop/.worktrees/done": _st("merged")}, {"live": ["inwt"]}, now)
    assert keep["worktrees"] == [], "a worktree with a chat that needs you is not offered"


def test_prefs_from_1_3_bring_back_the_profile_selector_and_the_bots_tab(model):
    """1.3.0 hid Desktop's profile selector and Bots tab by default, and the owner lost the bot picker in Sessions
    without knowing why. Prefs saved by 1.3/1.4 (version 2, both on) get them back once; hiding them stays a choice."""
    defaults = model("upgradePrefs", None, {"floatSides": True, "hideRail": False, "hideBotsTab": False, "prefsVersion": 3})
    assert defaults["hideRail"] is False and defaults["hideBotsTab"] is False
    saved_by_1_4 = {"floatSides": True, "hideBotsTab": True, "hideRail": True, "hiddenNav": ["kanban:nav"], "prefsVersion": 2}
    up = model("upgradePrefs", saved_by_1_4, defaults)
    assert up["hideRail"] is False and up["hideBotsTab"] is False and up["prefsVersion"] == 3
    chosen = {**up, "hideRail": True}
    assert model("upgradePrefs", chosen, defaults)["hideRail"] is True, "hiding it again after the upgrade is kept"


def test_the_chat_zone_is_found_from_the_layout_even_with_its_tab_strip_off(model):
    """The owner's real layout: the chat zone fronts a session tab and hides its strip, so no `workspace` tab is in
    the DOM; floating sides found no chat zone and never started. The persisted tree still names it."""
    tree = {"type": "split", "id": "s-root", "orientation": "row", "children": [
        {"type": "group", "id": "g-left", "panes": ["sessions", "hermes-bots:pane", "squad-hub:pane"], "active": "squad-hub:pane"},
        {"type": "group", "id": "g-main", "panes": ["workspace", "terminal", "session-tile:20261026_221647_7354c3"],
         "active": "session-tile:20261026_221647_7354c3", "tabStrip": "never"},
        {"type": "group", "id": "g-preview", "panes": ["preview-tile:url:browser-1"], "active": "preview-tile:url:browser-1"},
        {"type": "split", "id": "s-right", "orientation": "column", "children": [
            {"type": "group", "id": "g-files", "panes": ["files"], "active": "files"}]}]}
    assert model("workspaceGroup", tree) == "g-main"
    assert model("workspaceGroup", {"type": "group", "id": "g", "panes": ["files"]}) is None
    assert model("workspaceGroup", None) is None


def test_a_manager_row_counts_the_cards_waiting_on_you_not_every_blocked_card(model):
    """The manager row showed a bare "8": every blocked card, even those cleared from the bell or blocked on another
    card. It now counts what waits on your answer and is still in the bell; cleared ones stay listed, uncounted."""
    b = board(task("t_aa01", "blocked", assignee="shop", block_kind="needs_input", started=100),
              task("t_aa02", "blocked", assignee="shop-scout", block_kind="needs_input", started=200),
              task("t_aa03", "blocked", assignee="shop", block_kind="dependency", started=300),
              task("t_aa04", "running", assignee="shop-ops"))
    entry = {"slug": "shop", "name": "Shop", "digest": model("boardDigest", b)}
    waiting = model("boardWaiting", entry, {})
    assert [x["taskId"] for x in waiting] == ["t_aa02", "t_aa01"], "newest first, the dependency wait is not yours"
    cleared = {model("dismissKey", waiting[0]): 1}
    assert [x["taskId"] for x in model("boardWaiting", entry, cleared)] == ["t_aa01"]
    assert model("boardWaiting", None, {}) == []

def test_a_worktree_whose_status_could_not_be_read_is_never_offered_for_removal(model):
    """`repoStatus` can fail (timeout, a broken checkout, an older Desktop). The chip then reads zero changes and zero
    unpushed commits, which is also what a clean checkout reads: clean up must not take silence for \"nothing to lose\"."""
    unreadable = model("laneStatus", {"branch": "feat/done", "draft": False, "number": 1, "state": "merged", "title": "", "url": ""}, None)
    assert unreadable["known"] is False and model("laneStatus", None, {"changed": 0, "ahead": 0})["known"] is True
    wd = "/w/shop/.worktrees/"
    wts = {"/w/shop": WT["/w/shop"][:2]}
    project = _lane_project(model, [], wts)
    assert [w["label"] for w in model("cleanupPlan", project, {wd + "done": _st("merged")}, {}, 1_000_000.0)["worktrees"]] == ["done"]
    plan = model("cleanupPlan", project, {wd + "done": unreadable}, {}, 1_000_000.0)
    assert plan["worktrees"] == []


# ---- previews: what a component reads, and where they go when a chat moves ------------------------------------------

def test_a_chat_without_previews_reads_one_shared_empty_list(model):
    """The row and the status-bar chip read their chat's previews through useSyncExternalStore, which re-renders on any
    snapshot that is not identical to the last: `map[id] || []` would hand out a new array on every read."""
    got = model.js("""
      const map = { c1: [{ url: '/a.html', at: 1 }] }
      return { empty: m.previewsFor(map, 'nobody') === m.previewsFor(map, 'other'),
               none: m.previewsFor(null, 'x') === m.previewsFor(undefined, 'x'),
               same: m.previewsFor(map, 'c1') === map.c1, noId: m.previewsFor(map, null).length }
    """)
    assert got == {"empty": True, "none": True, "same": True, "noId": 0}


def test_a_compressed_chat_takes_its_previews_to_the_new_stored_id(model):
    old, new = "20261025_011740_e8a885", "20261025_093012_zz9999"
    m = {old: [{"url": "http://localhost:4321", "label": "site", "at": 5}, {"url": "/a.html", "at": 3}],
         new: [{"url": "/a.html", "at": 9}], "other": [{"url": "/z.html", "at": 1}]}
    got = model("rekeyPreviews", m, old, new)
    assert old not in got and got["other"] == m["other"]
    assert [(p["url"], p["at"]) for p in got[new]] == [("/a.html", 9), ("http://localhost:4321", 5)], "newest first, one per url"
    assert model("rekeyPreviews", m, "ghost", new) == m, "nothing remembered under the old id: nothing moves"
    assert model("rekeyPreviews", m, old, old) == m and model("rekeyPreviews", m, old, "") == m
    many = {old: [{"url": f"/p{i}.html", "at": i} for i in range(8)], new: [{"url": f"/q{i}.html", "at": 100 + i} for i in range(8)]}
    assert len(model("rekeyPreviews", many, old, new)[new]) == 8, "capped like any chat"


# ---- which stored chat a runtime serves -----------------------------------------------------------------------------

def test_the_focused_pair_fills_a_gap_but_never_overwrites_what_session_info_said(model):
    got = model.js("""
      const bound = new Map()
      const out = {}
      out.fill = m.bindRuntime(bound, 'rt-a', 'chat-a', false)           // the pair, nothing known yet
      out.sure = m.bindRuntime(bound, 'rt-a', 'chat-a2', true)           // session.info: compression moved it
      out.lag = m.bindRuntime(bound, 'rt-a', 'chat-b', false)            // the stored atom already says B, the runtime atom not yet
      out.after = bound.get('rt-a')
      out.first = m.bindRuntime(bound, 'rt-b', 'chat-b', true)
      out.blank = [m.bindRuntime(bound, '', 'x', true).changed, m.bindRuntime(bound, 'rt-c', null, true).changed]
      return out
    """)
    assert got["fill"] == {"changed": True, "from": ""}
    assert got["sure"] == {"changed": True, "from": ""}, "an unsure earlier binding is not a rotation to follow"
    assert got["lag"] == {"changed": False, "from": ""} and got["after"] == {"stored": "chat-a2", "sure": True}
    assert got["first"] == {"changed": True, "from": ""} and got["blank"] == [False, False]
    rot = model.js("""
      const bound = new Map()
      m.bindRuntime(bound, 'rt-a', 'chat-a', true)
      return [m.bindRuntime(bound, 'rt-a', 'chat-a', true), m.bindRuntime(bound, 'rt-a', 'chat-a2', true)]
    """)
    assert rot == [{"changed": True, "from": ""}, {"changed": True, "from": "chat-a"}], "a sure binding that moves names where it came from"


# ---- folded rows ------------------------------------------------------------------------------------------------------

def test_a_row_folds_and_unfolds_from_its_default_and_remembers_the_choice(model):
    """A quiet folder starts folded, a lane starts unfolded; one click flips whichever it is, and the flag stored for the
    row wins from then on."""
    folded_by_default, unfolded_by_default = True, False
    c = model("toggledCollapsed", {}, "folder:web:p1:/w/a", folded_by_default)
    assert c == {"folder:web:p1:/w/a": False}, "a click on a folded folder opens it"
    assert model("openState", c["folder:web:p1:/w/a"], not folded_by_default) is True
    c = model("toggledCollapsed", c, "folder:web:p1:/w/a", folded_by_default)
    assert c["folder:web:p1:/w/a"] is True and model("openState", True, True) is False, "the user's fold beats an open default"
    lane = model("toggledCollapsed", {"other": True}, "lane:web:/w/a", unfolded_by_default)
    assert lane == {"other": True, "lane:web:/w/a": True}, "a row that starts unfolded folds on the first click"
    never = model.js("return [m.openState(undefined, true), m.openState(undefined, false)]")
    assert never == [True, False], "a row never touched has no entry (undefined): the default"


# ---- the layout poll and floating sides ---------------------------------------------------------------------------------

LAYOUT = {"type": "split", "id": "sqh-root", "orientation": "row", "weights": [1, 3.6, 1.3], "children": [
    {"type": "group", "id": "sqh-left", "panes": ["squad-hub:pane", "sessions"], "active": "squad-hub:pane"},
    {"type": "group", "id": "sqh-main", "panes": ["workspace"], "active": "workspace"},
    {"type": "split", "id": "sqh-right", "orientation": "column", "weights": [3.4, 1], "children": [
        {"type": "group", "id": "sqh-files", "panes": ["files"], "active": "files", "minimized": True},
        {"type": "group", "id": "sqh-term", "panes": ["terminal"], "active": "terminal"}]}]}


def _zones(model, *raws):
    return model.js("return m.zonesOfAll(%s.map(m.parseLayout).filter(Boolean))" % json.dumps(list(raws)))


def test_the_persisted_layouts_read_as_zones_and_bad_text_is_skipped(model):
    """Desktop persists one tree per interface mode; either can be missing or, after a crash, cut off mid-write."""
    zones = _zones(model, json.dumps(LAYOUT))
    assert zones == {"sqh-left": "squad-hub:pane", "sqh-main": "workspace", "sqh-files": "files:min", "sqh-term": "terminal"}
    assert _zones(model, None) == {} and _zones(model, "null", "") == {}, "no layout yet"
    assert _zones(model, "{not json", '{"type": "gro', json.dumps(LAYOUT)) == zones, "a garbled mode is skipped, the other read"
    simple = {"type": "group", "id": "sqh-term", "panes": ["terminal", "files"], "active": "files"}
    assert _zones(model, json.dumps(LAYOUT), json.dumps(simple))["sqh-term"] == "files", "a later mode wins where they share a zone"
    assert model.js("return [m.parseLayout('{not json') === undefined, m.parseLayout(null) === null, m.parseLayout('') === null]") == [True, True, True]


def test_a_side_slides_in_only_when_something_else_reveals_it(model):
    zones = _zones(model, json.dumps(LAYOUT))
    right = {"groups": ["sqh-files", "sqh-term"], "open": False, "pinned": False}
    before = model("sideSignature", right["groups"], {**zones, "sqh-files": "files"})
    assert before == "sqh-files=files|sqh-term=terminal"
    other = model("sideSignature", right["groups"], {**zones, "sqh-files": "review"})
    assert model("isReveal", before, other, right) is True, "another pane took the zone: a reveal from a shortcut or a menu"
    assert model.js("return m.isReveal(undefined, 'a=b', { groups: ['a'], open: false, pinned: false })") is False, "the first look is no change"
    assert model("isReveal", before, before, right) is False
    folded = model("sideSignature", right["groups"], zones)
    assert model("isReveal", before, folded, right) is False, "a side the user just folded stays folded"
    assert model("isReveal", before, other, {**right, "open": True}) is False and model("isReveal", before, other, {**right, "pinned": True}) is False
    assert model("isReveal", before, other, {**right, "groups": []}) is False, "no zones on that side"


# ---- Desktop cards setting ------------------------------------------------------------------------------------------------

def test_a_manager_that_failed_is_asked_again_only_after_ten_minutes(model):
    now = 1_000_000
    managers = ["builder", "jobs", "web"]
    assert model("cardsToSwitch", managers, [], {}, now) == managers
    got = model("cardsToSwitch", managers, ["web"], {"jobs": now - 5 * 60_000, "builder": now - 11 * 60_000}, now)
    assert got == ["builder"], "done is skipped, a try five minutes ago waits, one eleven minutes ago is retried"
    assert model("cardsToSwitch", managers, ["builder", "jobs", "web"], {}, now) == []


# ---- timeouts ----------------------------------------------------------------------------------------------------------

def test_a_timeout_rejects_a_slow_call_and_leaves_no_timer_behind_when_the_call_answers(model):
    got = model.js("""
      const live = () => process.getActiveResourcesInfo().filter(r => r === 'Timeout').length
      const out = {}
      out.value = await m.withTimeout(Promise.resolve({ entries: [] }), 60000)
      out.timersAfterAnswer = live()
      try { await m.withTimeout(new Promise(() => {}), 20, 'worktrees timed out') } catch (e) { out.slow = e.message }
      out.timersAfterTimeout = live()
      try { await m.withTimeout(Promise.reject(new Error('not a git folder')), 60000) } catch (e) { out.failed = e.message }
      out.timersAfterFailure = live()
      return out
    """)
    assert got == {"value": {"entries": []}, "timersAfterAnswer": 0, "slow": "worktrees timed out", "timersAfterTimeout": 0,
                   "failed": "not a git folder", "timersAfterFailure": 0}


def test_the_chat_list_reads_attention_the_same_for_a_big_list_as_for_one_chat(model):
    attention = {"live": ["c3"], "unread": ["c5"], "focused": "c7"}
    got = model.js("""
      const attention = %s
      const rows = Array.from({ length: 2000 }, (_, i) => ({ id: 'c' + i }))
      return rows.map(r => m.chatState(r, attention)).map((s, i) => [i, s]).filter(([, s]) => s)
    """ % json.dumps(attention))
    assert got == [[3, "working"], [5, "unread"], [7, "current"]]
    assert model("chatState", {"id": "c1"}, None) == "" and model("chatState", {"id": "c1"}, {}) == ""
    assert model("chatState", {"id": "c1"}, {"live": None, "unread": None}) == ""


# ---- every string the interface asks for exists, in both languages --------------------------------------------------------

def _strip_comments(text: str) -> str:
    return re.sub(r"^\s*(//|\*|/\*\*).*$", "", text, flags=re.M)


def test_every_string_the_code_asks_for_exists_in_both_languages(model):
    """A key missing from a catalog shows as the raw key (`cleanWhy_idle`) in the UI. Static keys are read from the
    calls, data-built ones (`st_<state>`, `cleanWhy_<reason>`, `ev_<kind>`) from the values the model can produce."""
    text = _strip_comments(PLUGIN.read_text(encoding="utf-8"))
    catalogs = _catalogs()
    wanted = set(re.findall(r"\bt\('([A-Za-z_]+)'(?!\s*\+)", text)) | set(re.findall(r"\blang\(\)\.([A-Za-z_]+)", text))
    wanted |= set(re.findall(r"MESSAGES\.en\.([A-Za-z_]+)", text)) | set(re.findall(r"\bm\.(notify[A-Za-z]+|noManager|replyDraft)", text))
    dyn = model.js("return { states: m.STATES, kinds: [...m.HISTORY_KINDS] }")
    now, day = 1_000_000.0, 86400
    wd = "/w/shop/.worktrees/"
    wts = {"/w/shop": WT["/w/shop"][:1] + [{"path": wd + n, "branch": "b/" + n, "isMain": False} for n in ("m", "c", "i", "r", "n")]}
    chats = [chat("i", wd + "i", root="/w/shop", last=now - 3 * day), chat("r", wd + "r", root="/w/shop", last=now - 60)]
    project = _lane_project(model, chats, wts)
    statuses = {wd + "m": _st("merged"), wd + "c": _st("closed"), wd + "i": _st(), wd + "r": _st(), wd + "n": _st()}
    reasons = {w["reason"] for w in model("cleanupPlan", project, statuses, {}, now)["worktrees"]}
    assert reasons == {"merged", "closed", "idle", "recent", "nochats"}, "every reason a clean-up row can carry"
    wanted |= {f"st_{x}" for x in dyn["states"]} | {f"sth_{x}" for x in dyn["states"]} | {f"cleanWhy_{r}" for r in reasons}
    wanted |= {f"ev_{k}" for k in dyn["kinds"]} | {f"pr_{x}" for x in ("draft", "open", "merged", "closed")}
    assert len(wanted) > 150
    for lang, cat in catalogs.items():
        assert not sorted(k for k in wanted if k not in cat), lang


def test_a_chat_beside_a_preview_keeps_the_width_the_user_dragged(model):
    """The owner dragged the sash between the chat and a preview and it snapped back: the plugin forced the chat to
    grow whenever the sides floated. The row read from his window (left list and files floating, two folded zones):
    the preview shows, so the chat must not take the row; with no preview it takes the room the sides left."""
    beside_preview = [1571, 0, 0]
    assert model("chatAlone", beside_preview) is False
    assert model("chatAlone", [0, 0]) is True, "only folded zones: the chat fills the row"
    assert model("chatAlone", []) is True


def test_the_plugin_never_forces_the_chat_width_outside_the_lone_chat_case():
    """The stylesheet rule that made every drag snap back. The chat may be forced to fill the row only when it is alone."""
    css = PLUGIN.read_text(encoding="utf-8")
    forced = re.findall(r"([^\n{}]*\[data-sqh-main\][^{]*)\{[^}]*flex:[^};]*!important", css)
    assert forced, "the lone-chat rule exists"
    assert all("[data-sqh-solo]" in sel for sel in forced), forced
