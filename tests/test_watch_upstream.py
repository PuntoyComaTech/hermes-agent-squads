"""watch_upstream: release gate against recorded GitHub API/atom fixtures served by a local HTTP server."""
import json
import os
import re
import stat
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
FIX = REPO / "tests" / "fixtures" / "upstream"
sys.path.insert(0, str(SCRIPTS))
import gate_lib  # noqa: E402
import watch_upstream as wu  # noqa: E402

LOCAL = "0.22.0+2.gd97007c"  # from hermes-version.txt
ETAG = json.loads((FIX / "releases.meta.json").read_text())["etag"]


class Upstream:
    """Serves the recorded fixtures. `routes` maps a path to (status, body); /releases honours If-None-Match."""

    def __init__(self):
        self.routes = {
            "/releases": (200, (FIX / "releases.json").read_bytes()),
            "/atom": (200, (FIX / "releases.atom.xml").read_bytes()),
            "/squads/distribution.yaml": (200, (FIX / "squads-distribution.yaml").read_bytes()),
            "/squads/CHANGELOG.md": (200, (FIX / "squads-changelog.md").read_bytes()),
        }
        self.etag = ETAG
        self.log: list[tuple[str, int]] = []
        upstream = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                path = self.path.split("?")[0]
                status, body = upstream.routes.get(path, (404, b""))
                if path == "/releases" and status == 200 and self.headers.get("If-None-Match") == upstream.etag:
                    status, body = 304, b""
                upstream.log.append((path, status))
                self.send_response(status)
                if path == "/releases" and status in (200, 304):
                    self.send_header("ETag", upstream.etag)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def hits(self, path, status=None):
        return [s for p, s in self.log if p == path and (status is None or s == status)]

    def set_api(self, releases):
        self.routes["/releases"] = (200, json.dumps(releases).encode())


@pytest.fixture
def up():
    server = Upstream()
    yield server
    server.server.shutdown()


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


def seed(home, **reviewed):
    gate_lib.save_state("watch", {"reviewed": reviewed}, home / "local" / "state")


def run_gate(up, home, *extra, hermes_version=LOCAL, capsys=None):
    args = ["--home", str(home), "--releases-url", f"{up.base}/releases", "--atom-url", f"{up.base}/atom",
            "--squads-url", f"{up.base}/squads", "--hermes-version", hermes_version, *extra]
    assert wu.main(args) == 0
    out = capsys.readouterr().out
    assert len(out.strip().splitlines()) == 1, "a gate prints exactly one line"
    assert gate_lib.parse_gate(out) is json.loads(out)["wakeAgent"]
    return json.loads(out)


def state(home):
    return json.loads((home / "local" / "state" / "watch.json").read_text())


# --- gate contract ----------------------------------------------------------------------------------------------

def test_same_tag_does_not_wake(up, home, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL, squads=None)
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}
    assert not (home / "local" / "state" / "releases").exists()


def test_new_tag_wakes_with_a_filtered_file_under_the_cap(up, home, capsys):
    seed(home, release="v0.22.0", hermes=LOCAL, squads=None)
    out = run_gate(up, home, capsys=capsys)
    ctx = out["context"]
    assert out["wakeAgent"] is True and ctx["tags"] == ["v0.22.1"] and ctx["changed"] == ["release"]
    (filtered,) = [Path(p) for p in ctx["filtered"]]
    full = home / "local" / "state" / "releases" / "v0.22.1.md"
    assert full.read_text() == json.loads((FIX / "releases.json").read_text())[0]["body"]
    text = filtered.read_text()
    assert len(text) <= 15000 < len(full.read_text())
    assert re.search(r"kanban", text, re.I) and re.search(r"cron", text, re.I)
    assert "(https://" not in text  # commit links are stripped
    assert state(home)["reviewed"]["release"] == "v0.22.1"


def test_two_new_tags_share_the_cap(up, home, capsys):
    seed(home, release="v0.21.7", hermes=LOCAL, squads=None)
    ctx = run_gate(up, home, capsys=capsys)["context"]
    assert ctx["tags"] == ["v0.22.1", "v0.22.0"]
    assert sum(len(Path(p).read_text()) for p in ctx["filtered"]) <= 15000


def test_second_run_after_a_wake_is_silent(up, home, capsys):
    seed(home, release="v0.22.0", hermes=LOCAL, squads=None)
    assert run_gate(up, home, capsys=capsys)["wakeAgent"] is True
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}


def test_etag_gives_304_and_stored_etag_survives(up, home, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL, squads=None)
    run_gate(up, home, capsys=capsys)
    assert up.hits("/releases", 200) == [200] and state(home)["etag"] == ETAG
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}
    assert up.hits("/releases", 304) == [304]
    assert state(home)["latest_tag"] == "v0.22.1" and state(home)["etag"] == ETAG


def test_pending_change_on_304_refetches_without_etag(up, home, capsys):
    gate_lib.save_state("watch", {"etag": ETAG, "latest_tag": "v0.22.1",
                                  "reviewed": {"release": "v0.22.0", "hermes": LOCAL}}, home / "local" / "state")
    out = run_gate(up, home, capsys=capsys)
    assert out["context"]["tags"] == ["v0.22.1"]
    assert up.hits("/releases") == [304, 200]


def test_rc_canary_prerelease_and_calver_tags_are_skipped(up, home, capsys):
    api = json.loads((FIX / "releases.json").read_text())
    stub = {"body": "x", "draft": False, "prerelease": False, "published_at": "2026-10-15T00:00:00Z"}
    extra = [{**stub, "tag_name": "rc.6-v0.22.2"}, {**stub, "tag_name": "v0.22.2+canary.20261015T000000Z"},
             {**stub, "tag_name": "v0.22.2-rc.1"}, {**stub, "tag_name": "v0.22.2", "prerelease": True},
             {**stub, "tag_name": "v0.22.2", "draft": True}, {**stub, "tag_name": "v2026.10.15"}]
    up.set_api(extra + api)
    up.etag = "W/\"changed\""
    seed(home, release="v0.22.1", hermes=LOCAL, squads=None)
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}
    assert state(home)["latest_tag"] == "v0.22.1"


def test_api_rate_limit_falls_back_to_atom(up, home, capsys):
    up.routes["/releases"] = (403, b"")
    seed(home, release="v0.21.7", hermes=LOCAL, squads=None)
    out = run_gate(up, home, "--json", capsys=capsys)
    assert out["report"]["source"] == "atom" and out["context"]["tags"] == ["v0.22.1"]  # rc and canary entries skipped
    text = Path(out["context"]["filtered"][0]).read_text()
    assert re.search(r"^- .*(plugin|desktop|gateway)", text, re.I | re.M)  # html bodies come back as bullets
    assert state(home)["etag"] is None


def test_atom_parser_orders_by_date_and_drops_non_final():
    rels = wu.parse_atom((FIX / "releases.atom.xml").read_bytes())
    assert [r["tag"] for r in rels] == ["v0.22.1"]


# --- local hermes and squads signals ----------------------------------------------------------------------------

def test_local_hermes_change_wakes(up, home, capsys):
    seed(home, release="v0.22.1", hermes="0.21.7", squads=None)
    out = run_gate(up, home, capsys=capsys)
    assert out["context"]["changed"] == ["hermes"] and out["context"]["hermes"] == {"from": "0.21.7", "to": LOCAL}
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}


def test_local_version_parsed_from_the_hermes_binary(tmp_path):
    fake = tmp_path / "hermes"
    fake.write_text(f"#!/bin/sh\ncat {FIX / 'hermes-version.txt'}\necho 'Install directory: x'\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    assert wu.local_hermes_version(str(fake)) == LOCAL
    assert wu.local_hermes_version(str(tmp_path / "missing")) is None


def test_squads_version_on_main_wakes_once(up, home, capsys):
    (home / "distribution.yaml").write_text('name: builder\nversion: 2.0.0\n')
    seed(home, release="v0.22.1", hermes=LOCAL, squads="2.0.0")
    out = run_gate(up, home, capsys=capsys)
    sq = out["context"]["squads"]
    assert sq["from"] == "2.0.0" and sq["to"] == "2.1.0" and "studio" in sq["changelog_excerpt"]
    assert "2.0.0 - 2026-10-15" not in sq["changelog_excerpt"]
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}  # reviewed, not installed: no daily nagging


def test_squads_not_published_or_not_installed_is_silent(up, home, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL, squads=None)
    up.routes["/squads/distribution.yaml"] = (404, b"")
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}
    up.routes["/squads/distribution.yaml"] = (200, (FIX / "squads-distribution.yaml").read_bytes())
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}  # no installed distribution.yaml


# --- baseline, failures, dry run --------------------------------------------------------------------------------

def test_first_run_baseline_is_the_local_version(up, home, capsys):
    out = run_gate(up, home, capsys=capsys)  # local 0.22.0, newest final v0.22.1
    assert out["context"]["tags"] == ["v0.22.1"] and out["context"]["release_from"] == "v0.22.0"
    assert state(home)["reviewed"] == {"release": "v0.22.1", "hermes": LOCAL, "squads": None}


def test_first_run_with_a_local_build_ahead_of_the_release_is_silent(up, home, capsys):
    assert run_gate(up, home, hermes_version="0.23.0+5.gabc", capsys=capsys) == {"wakeAgent": False}


def test_dead_network_is_silent_until_the_third_failure(home, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL, squads=None)
    dead = "http://127.0.0.1:1"
    args = ["--home", str(home), "--releases-url", dead, "--atom-url", dead, "--squads-url", dead,
            "--hermes-version", LOCAL, "--timeout", "2"]
    for _ in range(2):
        assert wu.main(args) == 0
        assert json.loads(capsys.readouterr().out) == {"wakeAgent": False}
    assert wu.main(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["wakeAgent"] is True and "releases:" in out["context"]["gate_error"]
    assert state(home)["error_count"] == 0


def test_dry_run_writes_nothing(up, home, capsys):
    seed(home, release="v0.22.0", hermes=LOCAL, squads=None)
    before = (home / "local" / "state" / "watch.json").read_text()
    out = run_gate(up, home, "--dry-run", capsys=capsys)
    assert out["wakeAgent"] is True
    assert (home / "local" / "state" / "watch.json").read_text() == before
    assert not (home / "local" / "state" / "releases").exists()


# --- filter -----------------------------------------------------------------------------------------------------

def test_filter_keeps_priority_bullets_when_the_cap_bites():
    body = "# Release\n\n## Features\n" + "".join(f"- Plugin number {i} added with a long description " + "x" * 120 + "\n" for i in range(200))
    body += "- Remove the `cron.legacy_mode` flag\n- Kanban gets a new board command\n- Unrelated css tweak\n"
    out = wu.filter_release(body, "v9.9.9", 2000)
    assert len(out) <= 2000
    assert "cron.legacy_mode" in out and "Kanban gets" in out and "css tweak" not in out
    assert len(wu.filter_release(body, "v9.9.9", 300)) <= 300


def test_filter_strips_link_noise_and_matches_config_keys():
    body = "## Fixes\n- Fix `kanban.failure_limit` default ([`abcdef12`](https://github.com/x/y/commit/abcdef12)) \u2014 @someone\n- Edit README.md\n"
    out = wu.filter_release(body, "v1.2.3", 15000)
    assert "- Fix `kanban.failure_limit` default" in out and "abcdef12" not in out and "@someone" not in out
    assert "README.md" not in out


def test_manifest_version():
    assert wu.manifest_version('name: b\nversion: "2.1.0"\n') == "2.1.0"
    assert wu.manifest_version("name: b\n") is None


# --- cli --------------------------------------------------------------------------------------------------------

def test_help_works_without_network():
    proc = subprocess.run([sys.executable, str(SCRIPTS / "watch_upstream.py"), "--help"], capture_output=True, text=True,
                          env={**os.environ, "HTTPS_PROXY": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1"})
    assert proc.returncode == 0 and "wakeAgent" in proc.stdout


@pytest.mark.skipif(not os.environ.get("RUN_HERMES_TESTS"), reason="needs the real hermes binary; set RUN_HERMES_TESTS=1")
def test_real_hermes_version_is_parsed():
    assert re.match(r"\d+\.\d+\.\d+", wu.local_hermes_version("hermes") or "")
