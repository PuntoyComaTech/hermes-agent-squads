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

EXPORTS = ("baseName HUMAN_SOURCES isKanbanWorktree chatState activeIn projectOpensWide projectDigest needsYou botDigest whereOf isEnvFile pendingAcross nextPending folderIcon iconFor groupIconFor sectionOf botRole botTitle isHumanChat visibleBots folderOf laneOf buildBotTree filterTree "
           "shortAge slugify rememberPreview sessionTime").split()


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

    def call(fn: str, *args):
        script = (f"import * as m from './model.mjs'; const a = JSON.parse(process.argv[1]); "
                  f"const r = await m.{fn}(...a); console.log(JSON.stringify(r === undefined ? null : r));")
        out = subprocess.run([NODE, "--input-type=module", "-e", script, json.dumps(args)], cwd=d,
                             capture_output=True, text=True, timeout=30)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)
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
    bots = model("visibleBots", SQUADS_HOME, {"side-project": 9}, {})
    assert [b["name"] for b in bots] == ["default", "builder", "jobs", "marketing", "web", "side-project"]
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
    bots = model("visibleBots", SQUADS_HOME + [profile("shopbot", section="Storefronts")], {"side-project": 2, "shopbot": 1}, {})
    by = {b["name"]: b for b in bots}
    assert by["side-project"]["group"] == "Personal" and by["shopbot"]["group"] == "Storefronts"
    assert by["web"]["group"] == "" and by["default"]["group"] == ""


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


def test_the_project_row_lists_the_pending_chats_of_every_folder_so_no_folder_needs_opening(model):
    """The shortcut list under a many-folder project: what works, what is unread, and the chat in view, wherever
    they live; quiet chats stay inside their folded folders."""
    chats = [chat("a", "/w/seculus", unread=True, last=500.0), chat("b", "/w/timex", last=900.0),
             chat("c", "/w/nordic", last=100.0), chat("d", "/w/shared", last=50.0)]
    project = many_folders_tree(model, chats)
    digest = model("projectDigest", project, {"live": ["c"], "focused": "d"})
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


def test_the_squads_layout_places_files_over_the_terminal_and_never_review():
    """Review follows the chat (each agent opens its own); a global Review zone in the layout would show the wrong one."""
    text = PLUGIN.read_text(encoding="utf-8")
    layout = text[text.index("const SQUADS_LAYOUT = {"):text.index("// ───────────────────────────── data")]
    panes = re.findall(r"panes: \[([^\]]*)\]", layout)
    flat = {p.strip(" '") for group in panes for p in group.split(",")}
    assert {"squad-hub:pane", "workspace", "files", "terminal"} <= flat
    assert "review" not in flat


def test_the_plugin_is_opt_in_and_its_package_is_complete():
    text = PLUGIN.read_text(encoding="utf-8")
    assert "id: ID" in text and "const ID = 'squad-hub'" in text and "defaultEnabled: false" in text
    pkg = PLUGIN.parents[1]
    assert re.search(r"^name: squad-hub$", (pkg / "plugin.yaml").read_text(), re.M)
    assert (pkg / "__init__.py").is_file()


def test_the_model_markers_exist_once_and_the_model_has_no_imports():
    text = PLUGIN.read_text(encoding="utf-8")
    assert text.count("MODEL (pure)") == 2
    assert "import " not in _model_source()
