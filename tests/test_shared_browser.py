"""Shared signed-in browser: tab release and sweep against a real headless Chromium, and the plugin's hooks.

A bot run holds its tab through a browser-harness daemon attached over CDP. Here a small holder process plays
that daemon: it attaches to one tab (the tab reads `attached` to every other client) and carries
`browser_harness.daemon` in its command line, which is what `daemon_pid` verifies before signalling. Nothing here
touches the real shared browser, its port or the owner's profile.
"""
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import textwrap
import threading
import time
import types
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import shared_browser as sb  # noqa: E402
import shared_browser_tabs as tabs  # noqa: E402


def _chromium() -> str | None:
    exe = os.environ.get("HERMES_SHARED_BROWSER_EXE")
    if exe:
        return exe
    for p in sorted((Path.home() / ".hermes" / "tools").glob("chromium-*/chrome-*/*.app/Contents/MacOS/*")):
        if os.access(p, os.X_OK):
            return str(p)
    return shutil.which("chromium") or shutil.which("google-chrome")


CHROMIUM = _chromium()
needs_chromium = pytest.mark.skipif(CHROMIUM is None, reason="no Chromium (Hermes installs one with the browser tools)")


# --- the profile probe (#1) --------------------------------------------------------------------------------------

def test_profile_in_use_sees_a_process_that_holds_the_profile_dir(tmp_path, monkeypatch):
    """The probe's pattern starts with `--`, which pgrep reads as an option unless it follows `--`.

    A real process whose argv carries `--user-data-dir=<dir>` is the case `install`, `stop` and `login` depend on:
    with the option-reading bug pgrep exits 2, its output is empty, and every caller is told the profile is free.
    """
    profile = tmp_path / "profile"
    profile.mkdir()
    monkeypatch.setattr(sb, "PROFILE_DIR", profile)
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                                f"--user-data-dir={profile}"])
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not sb.profile_in_use():
            time.sleep(0.1)
        assert sb.profile_in_use() is True
        monkeypatch.setattr(sb, "PROFILE_DIR", tmp_path / "other")
        assert sb.profile_in_use() is False
    finally:
        sleeper.kill()
        sleeper.wait()


def test_a_failed_pgrep_is_an_error_never_an_empty_answer(tmp_path, monkeypatch, capsys):
    """An emulated exit 2 (what the old command line produced) must not read as "no browser holds the profile"."""
    monkeypatch.setattr(sb.subprocess, "run",
                        lambda *a, **k: subprocess.CompletedProcess(a, 2, "", "pgrep: illegal option -- -"))
    with pytest.raises(RuntimeError):
        sb.profile_in_use()
    # `stop` said "stopped: true" on that error; now it fails with a message.
    assert sb.main(["stop"]) == 1
    assert "cannot tell whether a browser holds" in capsys.readouterr().err


# --- no host is blocked: bots use any site, Google apps included -------------------------------------------------

def test_the_service_job_blocks_no_host():
    """The owner wants the bots free: neither the service nor the sign-in window carries a resolver rule."""
    for argv in (sb.service_argv("/opt/chrome"), sb.service_plist("/opt/chrome")["ProgramArguments"],
                 sb.login_argv("/opt/chrome", ["https://accounts.google.com/"])):
        assert not any(a.startswith("--host-resolver-rules") for a in argv), argv


def _page_socket(port: int, match: str = "about:blank") -> tabs.Cdp:
    """CDP on a page target's own websocket: Page.navigate / Runtime.evaluate need the page domain."""
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as r:
        pages = [p for p in json.load(r) if p.get("type") == "page"]
    page = next((p for p in pages if p.get("url") == match), pages[0])
    return tabs.Cdp(port, ws_url=page["webSocketDebuggerUrl"])


def _wait_title(page: tabs.Cdp, want: str, seconds: float = 10.0) -> str:
    deadline, title = time.monotonic() + seconds, ""
    while time.monotonic() < deadline:
        try:
            title = str(page.send("Runtime.evaluate", expression="document.title")["result"].get("value") or "")
        except (RuntimeError, OSError):
            title = ""
        if title == want:
            return title
        time.sleep(0.2)
    return title


def _network() -> bool:
    try:
        socket.create_connection(("www.google.com", 443), timeout=3).close()
        return True
    except OSError:
        return False


def _service_args(profile: Path, port: int) -> list[str]:
    """The service command line with the profile and port pinned to a temp dir and a free port.

    Built from `service_argv` by substitution, so the args under test are the ones the launchd job carries, and the
    owner's profile directory (the module default) is provably never launched.
    """
    args = sb.service_argv(CHROMIUM)
    out, seen_dir, seen_port = [], False, False
    for arg in args:
        if arg.startswith("--user-data-dir="):
            arg, seen_dir = f"--user-data-dir={profile}", True
        elif arg.startswith("--remote-debugging-port="):
            arg, seen_port = f"--remote-debugging-port={port}", True
        out.append(arg)
    assert seen_dir and seen_port, args
    assert str(sb.PROFILE_DIR) not in " ".join(out), "a test must never launch the owner's profile"
    return out


@pytest.fixture
def local_site():
    """A page that needs no network: the positive control for a service browser that still loads ordinary sites."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - http.server's name
            body = b"<!doctype html><title>shared-browser positive control</title>ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: N802 - http.server's name
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/"
    server.shutdown()
    server.server_close()


@needs_chromium
def test_a_service_browser_reaches_google_apps(tmp_path, local_site):
    """The service command line, on its own Chromium, port and temp profile, loads Gemini and Gmail hosts.

    Used verbatim apart from the profile and port, so a block re-added to `service_argv` fails here.
    """
    port = _free_port()
    proc = subprocess.Popen(_service_args(tmp_path / "svc", port), stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            try:
                tabs.page_states(port)
                break
            except OSError:
                time.sleep(0.2)
        else:
            pytest.fail("the service Chromium did not open its CDP port")
        page = _page_socket(port, match="about:blank")
        try:
            loaded = page.send("Page.navigate", url=local_site)
            assert not loaded.get("errorText"), loaded
            assert _wait_title(page, "shared-browser positive control") == "shared-browser positive control"
            if not _network():
                pytest.skip("no network to reach Google")
            for host in ("gemini.google.com", "aistudio.google.com", "mail.google.com", "docs.google.com"):
                reached = page.send("Page.navigate", url=f"https://{host}/")
                assert not reached.get("errorText"), f"{host} blocked: {reached}"
        finally:
            page.close()
    finally:
        proc.kill()
        proc.wait()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def browser(tmp_path, monkeypatch):
    port = _free_port()
    proc = subprocess.Popen([CHROMIUM, "--headless=new", f"--remote-debugging-port={port}",
                             "--remote-debugging-address=127.0.0.1", f"--user-data-dir={tmp_path / 'profile'}",
                             "--no-first-run", "--no-default-browser-check", "--use-mock-keychain", "about:blank"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            tabs.page_states(port)
            break
        except OSError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.skip("Chromium did not open its CDP port")
    monkeypatch.setenv("HERMES_SHARED_BROWSER_STATE", str(tmp_path / "state"))
    monkeypatch.setenv("BH_RUNTIME_DIR", str(tmp_path / "bh"))
    (tmp_path / "bh").mkdir()
    yield types.SimpleNamespace(port=port, tmp=tmp_path, holders=[])
    proc.kill()
    proc.wait()


HOLDER = textwrap.dedent("""
    import sys, time
    sys.path.insert(0, sys.argv[1])
    import shared_browser_tabs as tabs
    port, url = int(sys.argv[2]), sys.argv[3]
    cdp = tabs.Cdp(port)
    tid = cdp.send("Target.createTarget", url=url)["targetId"]
    cdp.send("Target.attachToTarget", targetId=tid, flatten=True)
    print(tid, flush=True)
    time.sleep(600)
""")


def hold_tab(b, name: str, url: str = "about:blank#work") -> str:
    """Start a daemon stand-in for session `name` holding one new tab; return the tab id."""
    script = b.tmp / "holder.py"
    script.write_text(HOLDER)
    proc = subprocess.Popen([sys.executable, str(script), str(REPO / "scripts"), str(b.port), url,
                             "browser_harness.daemon"], stdout=subprocess.PIPE, text=True)
    b.holders.append(proc)
    tid = proc.stdout.readline().strip()
    (b.tmp / "bh" / f"bu-{name}.pid").write_text(str(proc.pid))
    tabs.touch_lease(b.port, name)
    return tid


@pytest.fixture(autouse=True)
def _reap(request):
    yield
    b = request.node.funcargs.get("browser")
    for p in getattr(b, "holders", []):
        p.kill()


@needs_chromium
def test_release_closes_only_the_finished_runs_tab(browser):
    """Two bots work at once; one turn ends. Its tab closes, the other bot's tab and the blank anchor stay."""
    mine = hold_tab(browser, "sb-run-a")
    other = hold_tab(browser, "sb-run-b")
    result = tabs.release(browser.port, ["sb-run-a"], settle=0.5)
    states = tabs.page_states(browser.port)
    assert result["stopped"] == 1 and mine not in states
    assert states[other][0] is True, "the other run's tab must stay attached and open"
    assert any(url == "about:blank" for _a, url in states.values()), "the blank anchor stays"
    assert "sb-run-a" not in tabs.leases(browser.port) and "sb-run-b" in tabs.leases(browser.port)


@needs_chromium
def test_release_never_closes_a_tab_another_client_attaches_after_the_settle(browser):
    """Doubt: a release used to close every page that was free in both snapshots, not only its own run's tab.

    Another bot creates its tab before the release starts and attaches its daemon a second or two later (slower than
    the release settle). Its tab must survive: a release closes what was attached before the stop and free after it.
    """
    mine = hold_tab(browser, "sb-run-a")
    script = browser.tmp / "late_client.py"
    script.write_text(textwrap.dedent("""
        import sys, time
        sys.path.insert(0, sys.argv[1])
        import shared_browser_tabs as tabs
        cdp = tabs.Cdp(int(sys.argv[2]))
        tid = cdp.send("Target.createTarget", url="about:blank#late")["targetId"]
        print(tid, flush=True)
        time.sleep(float(sys.argv[3]))
        cdp.send("Target.attachToTarget", targetId=tid, flatten=True)
        time.sleep(60)
    """))
    late_proc = subprocess.Popen([sys.executable, str(script), str(REPO / "scripts"), str(browser.port), "2.0"],
                                 stdout=subprocess.PIPE, text=True)
    browser.holders.append(late_proc)
    late = late_proc.stdout.readline().strip()
    assert late and tabs.page_states(browser.port)[late][0] is False
    result = tabs.release(browser.port, ["sb-run-a"], settle=0.5)
    assert result["closed"] == 1 and mine not in tabs.page_states(browser.port)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not tabs.page_states(browser.port).get(late, (False, ""))[0]:
        time.sleep(0.1)
    states = tabs.page_states(browser.port)
    assert late in states and states[late][0], "another client's tab must never be closed by a release"


@needs_chromium
def test_release_closes_only_the_tabs_recorded_for_its_sessions(browser):
    """With recorded target ids the release is narrower still: an orphan page nobody holds is left to the sweep."""
    mine = hold_tab(browser, "sb-run-a")
    cdp = tabs.Cdp(browser.port)
    orphan = cdp.send("Target.createTarget", url="about:blank#orphan")["targetId"]
    cdp.close()
    result = tabs.release(browser.port, ["sb-run-a"], settle=0.3, held=[mine])
    states = tabs.page_states(browser.port)
    assert result["closed"] == 1 and mine not in states
    assert orphan in states and states[orphan][0] is False


@needs_chromium
def test_sweep_closes_tabs_left_by_a_crashed_run_and_keeps_live_ones(browser):
    """A run whose Hermes process died left its daemon and tab; the sweep stops that daemon and closes the tab.
    A run still alive keeps its tab. An orphan page nobody holds is closed too."""
    crashed = hold_tab(browser, "sb-crashed")
    live = hold_tab(browser, "sb-live")
    (tabs.leases_dir(browser.port) / "sb-crashed").write_text("999999")  # its Hermes pid is gone
    cdp = tabs.Cdp(browser.port)
    orphan = cdp.send("Target.createTarget", url="about:blank#orphan")["targetId"]
    cdp.close()
    result = tabs.sweep(browser.port, max_idle=3600, settle=0.5)
    states = tabs.page_states(browser.port)
    assert crashed not in states and orphan not in states
    assert live in states and states[live][0]
    assert result["stale_sessions"] == 1 and result["closed"] >= 2
    assert sum(1 for _a, url in states.values() if url == "about:blank") == 1


@needs_chromium
def test_sweep_recreates_the_blank_anchor_when_none_is_left(browser):
    cdp = tabs.Cdp(browser.port)
    for tid in list(tabs.page_states(browser.port)):
        cdp.send("Target.closeTarget", targetId=tid)
    cdp.send("Target.createTarget", url="about:blank#x")
    cdp.close()
    tabs.sweep(browser.port, settle=0.2)
    assert [url for _a, url in tabs.page_states(browser.port).values()] == ["about:blank"]


def test_daemon_pid_never_signals_a_process_that_is_not_a_harness_daemon(tmp_path, monkeypatch):
    """A stale pid file can point at a reused pid: only a verified browser_harness.daemon is ever signalled."""
    monkeypatch.setenv("BH_RUNTIME_DIR", str(tmp_path))
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        (tmp_path / "bu-sb-x.pid").write_text(str(sleeper.pid))
        assert tabs.daemon_pid("sb-x") is None
        assert tabs.stop_daemon("sb-x") is True and sleeper.poll() is None, "the unrelated process must survive"
    finally:
        sleeper.kill()


def _plugin(monkeypatch, cdp_url: str):
    monkeypatch.setenv("BROWSER_CDP_URL", cdp_url)
    pkg = REPO / "squads" / "_plugins" / "shared-browser-tabs"
    spec = importlib.util.spec_from_file_location("sbt_plugin", pkg / "__init__.py",
                                                  submodule_search_locations=[str(pkg)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["sbt_plugin"] = mod
    sys.modules["sbt_plugin.tabs"] = tabs
    spec.loader.exec_module(mod)
    return mod


def test_plugin_gives_each_task_its_own_session_and_one_tab(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_SHARED_BROWSER_STATE", str(tmp_path))
    mod = _plugin(monkeypatch, "http://127.0.0.1:9333")
    a = mod._on_pre_tool_call("browser_exec", {"code": "new_tab('https://x')"}, task_id="t1")
    b = mod._on_pre_tool_call("browser_exec", {"code": "print(1)"}, task_id="t2")
    assert a["action"] == "modify" and a["args"]["session"] != b["args"]["session"]
    assert a["args"]["code"].startswith(mod.ONE_TAB_PREFIX) and a["args"]["code"].endswith("new_tab('https://x')")
    again = mod._on_pre_tool_call("browser_exec", {"code": a["args"]["code"], "session": a["args"]["session"]},
                                  task_id="t1")
    assert again is None, "an already prefixed call with a session is left alone"
    assert set(tabs.leases(9333)) == {a["args"]["session"], b["args"]["session"]}
    assert mod._on_pre_tool_call("terminal", {"command": "ls"}, task_id="t1") is None


def test_plugin_releases_exactly_the_sessions_of_the_ending_turn(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_SHARED_BROWSER_STATE", str(tmp_path))
    mod = _plugin(monkeypatch, "http://127.0.0.1:9333")
    monkeypatch.setattr(tabs, "attached_now", lambda port: {})
    released = []
    monkeypatch.setattr(tabs, "release",
                        lambda port, names, settle=1.0, held=None: released.append((port, names)) or {})
    mod._on_pre_tool_call("browser_exec", {"code": "x"}, task_id="t1")
    mod._on_pre_tool_call("browser_exec", {"code": "x", "session": "research-2"}, task_id="t1")
    mod._on_pre_tool_call("browser_exec", {"code": "x"}, task_id="t2")
    mod._on_session_end(task_id="t1")
    assert released == [(9333, sorted([tabs.session_name("t1", ""), "research-2"]))]
    mod._on_session_end(task_id="t1")
    assert len(released) == 1, "a second end of the same turn releases nothing"


def test_plugin_releases_the_sessions_of_an_interrupted_turn(monkeypatch, tmp_path):
    """#13: an interrupted turn ends with no task_id (cli_shutdown, tui gateway session_lifecycle).

    The session names were recorded under the task id, so the old key fell back to the session id and released
    nothing: the daemon, the tab and the `_used` entry stayed until the Hermes pid exited.
    """
    monkeypatch.setenv("HERMES_SHARED_BROWSER_STATE", str(tmp_path))
    mod = _plugin(monkeypatch, "http://127.0.0.1:9333")
    monkeypatch.setattr(tabs, "attached_now", lambda port: {})
    released = []
    monkeypatch.setattr(tabs, "release",
                        lambda port, names, settle=1.0, held=None: released.append((port, names)) or {})
    mod._on_pre_tool_call("browser_exec", {"code": "x"}, task_id="t-9", session_id="s-9")
    mod._on_session_end(session_id="s-9")  # no task_id: the interrupted path
    assert released == [(9333, [tabs.session_name("t-9", "s-9")])]
    mod._on_session_end(task_id="t-9", session_id="s-9")
    assert len(released) == 1, "the second end of the same turn releases nothing and leaks no entry"
    assert mod._used == {} and mod._held == {}


def test_plugin_records_the_tab_its_call_attached_so_release_closes_only_that(monkeypatch, tmp_path):
    """The post-call diff of the page targets names the tab of that run; release gets those ids, not the port's
    every free page."""
    monkeypatch.setenv("HERMES_SHARED_BROWSER_STATE", str(tmp_path))
    mod = _plugin(monkeypatch, "http://127.0.0.1:9333")
    before = {"anchor": True, "other": True}
    monkeypatch.setattr(tabs, "attached_now", lambda port: dict(before))
    monkeypatch.setattr(tabs, "claimed_targets",
                        lambda port, snap: {"anchor", "mine"} if snap == before else set())
    released = []
    monkeypatch.setattr(tabs, "release",
                        lambda port, names, settle=1.0, held=None: released.append((names, set(held or ()))) or {})
    name = tabs.session_name("t-1", "")
    mod._on_pre_tool_call("browser_exec", {"code": "x"}, task_id="t-1")
    mod._on_post_tool_call("browser_exec", {"code": "x", "session": name}, task_id="t-1")
    mod._on_session_end(task_id="t-1")
    assert released == [([name], {"anchor", "mine"})]
    assert mod._before == {}


def test_plugin_claims_nothing_without_a_pre_call_snapshot(monkeypatch, tmp_path):
    """NEW 3: a diff against {} claims every attached page, another bot's tab included.

    With no pre-call snapshot (a pre hook that failed, or a session named at the call) the post hook must record
    nothing and let `release` use its own before/after fallback.
    """
    monkeypatch.setenv("HERMES_SHARED_BROWSER_STATE", str(tmp_path))
    mod = _plugin(monkeypatch, "http://127.0.0.1:9333")
    seen = []
    monkeypatch.setattr(tabs, "claimed_targets", lambda port, snap: seen.append(snap) or {"another-bots-tab"})
    mod._on_post_tool_call("browser_exec", {"code": "x", "session": "sb-named"}, task_id="t-2", session_id="s-2")
    assert seen == [], "a claim with no snapshot must not run"
    assert mod._held == {}, "another bot's tab must never be recorded as this turn's"


@needs_chromium
def test_plugin_release_still_closes_the_runs_own_tab_when_the_claim_failed(browser, monkeypatch):
    """NEW 3: claimed_targets raised, so nothing was recorded. Before the fix `held` went to release as an empty
    set, no tab was closed, and the bot's tab survived until the 3-hourly sweep. held=None runs the fallback:
    the tab that was attached before the stop and free after it is the bot's own and closes."""
    mod = _plugin(monkeypatch, f"http://127.0.0.1:{browser.port}")
    name = tabs.session_name("t-claim", "")

    def boom(port, before):
        raise OSError("CDP closed mid-call")

    monkeypatch.setattr(tabs, "claimed_targets", boom)
    mine = hold_tab(browser, name)
    other = hold_tab(browser, "sb-other")
    real_release, released = tabs.release, []

    def spy(port, names, settle=1.0, held=None):
        released.append((list(names), held))
        return real_release(port, names, settle=0.4, held=held)

    monkeypatch.setattr(tabs, "release", spy)
    mod._on_pre_tool_call("browser_exec", {"code": "x"}, task_id="t-claim")
    mod._on_post_tool_call("browser_exec", {"code": "x", "session": name}, task_id="t-claim")
    assert mod._held == {}, "the failed claim recorded nothing"
    mod._on_session_end(task_id="t-claim")
    assert released == [([name], None)], "release must get held=None, not an empty set"
    states = tabs.page_states(browser.port)
    assert mine not in states, "the bot's own tab must close"
    assert states[other][0] is True, "the other bot's tab must stay open"


def test_plugin_is_inert_without_a_loopback_shared_browser(monkeypatch):
    for url in ("", "wss://connect.browserbase.com/x", "http://10.0.0.5:9222"):
        mod = _plugin(monkeypatch, url)
        assert mod._on_pre_tool_call("browser_exec", {"code": "x"}, task_id="t") is None


def test_sweep_cli_is_silent_on_success_and_reports_an_unreachable_browser(tmp_path):
    p = subprocess.run([sys.executable, str(REPO / "scripts" / "shared_browser_sweep.py"), "--cdp-url",
                        f"http://127.0.0.1:{_free_port()}"], capture_output=True, text=True)
    assert p.returncode == 1 and "not reachable" in json.loads(p.stderr)["error"]
    p = subprocess.run([sys.executable, str(REPO / "scripts" / "shared_browser_sweep.py"), "--cdp-url",
                        "http://example.com:9333"], capture_output=True, text=True)
    assert p.returncode == 2


# --- `login` always puts the service back (NEW 6) ----------------------------------------------------------------

def _login_stubs(monkeypatch, tmp_path, *, probe):
    """launchctl is recorded, never run; the probe is whatever the test needs."""
    calls = []
    monkeypatch.setattr(sb.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(sb, "loaded", lambda: True)
    monkeypatch.setattr(sb, "PLIST", tmp_path / "ai.hermes.shared-browser.plist")
    monkeypatch.setattr(sb, "chromium", lambda: "/opt/chrome")
    monkeypatch.setattr(sb, "listening", lambda: None)  # never query the live service
    monkeypatch.setattr(sb, "wait_for", lambda cond, seconds: cond())
    monkeypatch.setattr(sb, "launchctl",
                        lambda *args, check=False: calls.append(args) or subprocess.CompletedProcess(args, 0, "", ""))
    monkeypatch.setattr(sb, "profile_in_use", probe)
    return calls


def test_login_puts_the_service_back_when_the_profile_probe_fails(tmp_path, monkeypatch):
    """NEW 6: `login` booted the service out, then a ProbeError made it exit 1 and the squad had no browser.

    main() catches ProbeError and returns 1, so the restart cannot live there: it has to be `login`'s finally.
    """
    def probe():
        raise sb.ProbeError("pgrep exited 2")

    calls = _login_stubs(monkeypatch, tmp_path, probe=probe)
    assert sb.main(["login"]) == 1
    assert [c[0] for c in calls] == ["bootout", "bootstrap"], calls
    assert str(tmp_path / "ai.hermes.shared-browser.plist") == calls[1][2]


def test_login_puts_the_service_back_when_the_profile_stays_busy(tmp_path, monkeypatch):
    """A visible window the owner forgot to quit made `login` raise; the service still has to come back."""
    calls = _login_stubs(monkeypatch, tmp_path, probe=lambda: True)
    with pytest.raises(SystemExit):
        sb.main(["login"])
    assert [c[0] for c in calls] == ["bootout", "bootstrap"], calls


def test_login_puts_the_service_back_when_the_window_is_interrupted(tmp_path, monkeypatch):
    """Ctrl-C in the window wait (the owner changes their mind) must not cost the squad its browser."""
    calls = _login_stubs(monkeypatch, tmp_path, probe=lambda: False)
    monkeypatch.setattr(sb.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        sb.main(["login"])
    assert [c[0] for c in calls] == ["bootout", "bootstrap"], calls



def test_install_of_a_changed_job_loads_it_again_although_bootout_returns_before_the_job_is_gone(tmp_path, monkeypatch):
    """`launchctl bootout` returns while launchd is still removing the job. Reading `loaded()` right after it saw
    the old job, skipped the bootstrap, and the update left the owner's machine with no shared browser at all."""
    calls, state = [], {"loaded": True, "prints_left": 0}

    def launchctl(*args, check=False):
        calls.append(args[0])
        if args[0] == "bootout":
            state["prints_left"] = 3          # launchd still lists the job for a few probes
        if args[0] == "bootstrap":
            state["loaded"] = True
        return subprocess.CompletedProcess(args, 0, "", "")

    def loaded():
        if state["prints_left"]:
            state["prints_left"] -= 1
            if state["prints_left"] == 0:
                state["loaded"] = False
            return True
        return state["loaded"]

    monkeypatch.setattr(sb.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(sb, "ROOT", tmp_path / "sessions")
    monkeypatch.setattr(sb, "PROFILE_DIR", tmp_path / "sessions" / "hermes")
    monkeypatch.setattr(sb, "PLIST", tmp_path / "ai.hermes.shared-browser.plist")
    (tmp_path / "ai.hermes.shared-browser.plist").write_bytes(b"old job")
    monkeypatch.setattr(sb, "chromium", lambda: "/opt/chrome")
    monkeypatch.setattr(sb, "launchctl", launchctl)
    monkeypatch.setattr(sb, "loaded", loaded)
    monkeypatch.setattr(sb, "profile_in_use", lambda: False)
    monkeypatch.setattr(sb, "listening", lambda: {"browser": "x", "pages": 1} if "bootstrap" in calls else None)
    monkeypatch.setattr(sb.time, "sleep", lambda s: None)
    assert sb.main(["install"]) == 0
    assert calls.count("bootout") == 1 and calls[-1] == "bootstrap", calls


def test_the_machine_sweeps_once_although_every_squad_manager_carries_the_cron(tmp_path, monkeypatch):
    """jobs, web and marketing each ship the 3-hourly sweep on their manager, and all three fire at the same minute
    on one browser. The first sweeps; the others find it running (lock) or just done (stamp) and exit untouched.
    An unreachable port proves it: a sweep that really ran would report the browser missing with exit 1."""
    import fcntl
    monkeypatch.setenv("HERMES_SHARED_BROWSER_STATE", str(tmp_path))
    sweep = [sys.executable, str(REPO / "scripts" / "shared_browser_sweep.py"), "--cdp-url",
             f"http://127.0.0.1:{_free_port()}", "--verbose"]
    env = {**os.environ, "HERMES_SHARED_BROWSER_STATE": str(tmp_path)}
    assert subprocess.run(sweep, capture_output=True, text=True, env=env).returncode == 1  # nothing ran before
    port = int(sweep[3].rsplit(":", 1)[1])
    stamp = tmp_path / f"sweep-{port}.stamp"
    with open(stamp, "a+") as fh:  # another manager's sweep holds the lock right now
        fcntl.flock(fh, fcntl.LOCK_EX)
        assert subprocess.run(sweep, capture_output=True, text=True, env=env).returncode == 0
    stamp.write_text(str(int(time.time())))  # another manager's sweep just finished
    p = subprocess.run(sweep, capture_output=True, text=True, env=env)
    assert p.returncode == 0 and json.loads(p.stdout) == {"skipped": "another sweep ran recently"}
    old = time.time() - 3 * 3600
    os.utime(stamp, (old, old))  # three hours later the next fire sweeps again
    assert subprocess.run(sweep, capture_output=True, text=True, env=env).returncode == 1


def test_sweep_stops_a_copy_browser_only_when_its_profile_turned_real_profile_off(tmp_path):
    """A bot's real-profile copy browser outlived the toggle for days and held the owner's Brave app."""
    import shared_browser_sweep as sweep
    procs = {}
    for bot, on in (("off-bot", False), ("on-bot", True)):
        home = tmp_path / "profiles" / bot
        home.mkdir(parents=True)
        (home / "config.yaml").write_text(f"browser:\n  use_real_profile: {'true' if on else 'false'}\n")
        procs[bot] = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)",
                                       f"--user-data-dir={home}/browser-profile/brave", "--remote-debugging-port=0"])
    try:
        time.sleep(0.3)
        assert sweep.stop_stale_copy_browsers(tmp_path) == 1
        assert procs["off-bot"].wait(timeout=5) is not None
        assert procs["on-bot"].poll() is None
    finally:
        for p in procs.values():
            p.kill()
