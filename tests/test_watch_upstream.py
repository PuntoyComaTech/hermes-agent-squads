"""watch_upstream: release gate against recorded GitHub API/atom fixtures served by a local HTTP server."""
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from _real import needs_hermes

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
            "--hermes-version", hermes_version, *extra]
    assert wu.main(args) == 0
    out = capsys.readouterr().out
    assert len(out.strip().splitlines()) == 1, "a gate prints exactly one line"
    assert gate_lib.parse_gate(out) is json.loads(out)["wakeAgent"]
    return json.loads(out)


def state(home):
    return json.loads((home / "local" / "state" / "watch.json").read_text())


def digest(home):
    """What the tracking-updates agent writes after a wake; it confirms the pending change as reviewed."""
    d = home / "local" / "state" / "digests"
    d.mkdir(parents=True, exist_ok=True)
    (d / "2026-10-15.json").write_text('{"date": "2026-10-15", "tags": [], "items": []}')


# --- gate contract ----------------------------------------------------------------------------------------------

def test_same_tag_does_not_wake(up, home, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}
    assert not (home / "local" / "state" / "releases").exists()


def test_new_tag_wakes_with_a_filtered_file_under_the_cap(up, home, capsys):
    seed(home, release="v0.22.0", hermes=LOCAL)
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
    assert state(home)["reviewed"]["release"] == "v0.22.0"  # reviewed only once the digest exists
    assert state(home)["pending"]["reviewed"]["release"] == "v0.22.1"


def test_two_new_tags_share_the_cap(up, home, capsys):
    seed(home, release="v0.21.7", hermes=LOCAL)
    ctx = run_gate(up, home, capsys=capsys)["context"]
    assert ctx["tags"] == ["v0.22.1", "v0.22.0"]
    assert sum(len(Path(p).read_text()) for p in ctx["filtered"]) <= 15000


def test_second_run_after_a_digest_is_silent(up, home, capsys):
    seed(home, release="v0.22.0", hermes=LOCAL)
    assert run_gate(up, home, capsys=capsys)["wakeAgent"] is True
    digest(home)
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}
    assert state(home)["reviewed"]["release"] == "v0.22.1" and "pending" not in state(home)


def test_a_failed_digest_turn_wakes_again(up, home, capsys):
    """No digest file after a wake (the agent turn failed): the change is not lost, the next run reports it."""
    seed(home, release="v0.22.0", hermes=LOCAL)
    assert run_gate(up, home, capsys=capsys)["wakeAgent"] is True
    again = run_gate(up, home, capsys=capsys)
    assert again["wakeAgent"] is True and again["context"]["tags"] == ["v0.22.1"]
    assert state(home)["reviewed"]["release"] == "v0.22.0"


def test_a_digest_older_than_the_wake_does_not_confirm_it(up, home, capsys):
    seed(home, release="v0.22.0", hermes=LOCAL)
    digest(home)
    old = home / "local" / "state" / "digests" / "2026-10-15.json"
    os.utime(old, (1, 1))
    assert run_gate(up, home, capsys=capsys)["wakeAgent"] is True
    assert run_gate(up, home, capsys=capsys)["wakeAgent"] is True


def test_etag_gives_304_and_stored_etag_survives(up, home, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)
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
    seed(home, release="v0.22.1", hermes=LOCAL)
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}
    assert state(home)["latest_tag"] == "v0.22.1"


def test_api_rate_limit_falls_back_to_atom(up, home, capsys):
    up.routes["/releases"] = (403, b"")
    seed(home, release="v0.21.7", hermes=LOCAL)
    out = run_gate(up, home, "--json", capsys=capsys)
    assert out["report"]["source"] == "atom" and out["context"]["tags"] == ["v0.22.1"]  # rc and canary entries skipped
    text = Path(out["context"]["filtered"][0]).read_text()
    assert re.search(r"^- .*(plugin|desktop|gateway)", text, re.I | re.M)  # html bodies come back as bullets
    assert state(home)["etag"] is None


def test_atom_parser_orders_by_date_and_drops_non_final():
    rels = wu.parse_atom((FIX / "releases.atom.xml").read_bytes())
    assert [r["tag"] for r in rels] == ["v0.22.1"]


# --- local hermes signal -------------------------------------------------------------------------------------------

def test_local_hermes_change_wakes(up, home, capsys):
    seed(home, release="v0.22.1", hermes="0.21.7")
    out = run_gate(up, home, capsys=capsys)
    assert out["context"]["changed"] == ["hermes"] and out["context"]["hermes"] == {"from": "0.21.7", "to": LOCAL}
    digest(home)
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}


def test_a_new_build_suffix_of_the_same_release_is_silent(up, home, capsys):
    """`hermes update` on a git install changes only +N.g<sha>; that is not a Hermes change to digest."""
    seed(home, release="v0.22.1", hermes="0.22.0+1.g1111111")
    assert run_gate(up, home, hermes_version="0.22.0+9.gdeadbee", capsys=capsys) == {"wakeAgent": False}


def test_local_version_parsed_from_the_hermes_binary(tmp_path):
    fake = tmp_path / "hermes"
    fake.write_text(f"#!/bin/sh\ncat {shlex.quote(str(FIX / 'hermes-version.txt'))}\necho 'Install directory: x'\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    assert wu.local_hermes_version(str(fake)) == LOCAL
    assert wu.local_hermes_version(str(tmp_path / "missing")) is None


def test_first_run_baseline_is_the_local_version(up, home, capsys):
    out = run_gate(up, home, capsys=capsys)  # local 0.22.0, newest final v0.22.1
    assert out["context"]["tags"] == ["v0.22.1"] and out["context"]["release_from"] == "v0.22.0"
    assert state(home)["reviewed"] == {"release": "v0.22.0", "hermes": LOCAL}
    assert state(home)["pending"]["reviewed"] == {"release": "v0.22.1", "hermes": LOCAL}


def test_first_run_with_a_local_build_ahead_of_the_release_is_silent(up, home, capsys):
    assert run_gate(up, home, hermes_version="0.23.0+5.gabc", capsys=capsys) == {"wakeAgent": False}


def test_dead_network_is_silent_until_the_third_failure(home, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)
    dead = "http://127.0.0.1:1"
    args = ["--home", str(home), "--releases-url", dead, "--atom-url", dead,
            "--hermes-version", LOCAL, "--timeout", "2"]
    for _ in range(2):
        assert wu.main(args) == 0
        assert json.loads(capsys.readouterr().out) == {"wakeAgent": False}
    assert wu.main(args) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["wakeAgent"] is True and "releases:" in out["context"]["gate_error"]
    assert state(home)["error_count"] == 0


def test_dry_run_writes_nothing(up, home, capsys):
    seed(home, release="v0.22.0", hermes=LOCAL)
    before = (home / "local" / "state" / "watch.json").read_text()
    out = run_gate(up, home, "--dry-run", capsys=capsys)
    assert out["wakeAgent"] is True
    assert (home / "local" / "state" / "watch.json").read_text() == before
    assert not (home / "local" / "state" / "releases").exists()


# --- filter -----------------------------------------------------------------------------------------------------

def test_filter_keeps_priority_bullets_when_the_cap_bites():
    body = "# Release\n\n## Features\n" + "".join(f"- Plugin number {i} added with a long description " + "x" * 120 + "\n" for i in range(200))
    body += "- Remove the `cron.legacy_mode` flag\n- Kanban gets a new board command\n- Unrelated css tweak\n"
    out, overflow = wu.filter_release(body, "v9.9.9", 2000)
    assert len(out) <= 2000 and overflow == ""
    assert "cron.legacy_mode" in out and "Kanban gets" in out and "css tweak" not in out
    assert len(wu.filter_release(body, "v9.9.9", 300)[0]) <= 300


def test_filter_strips_link_noise_and_matches_config_keys():
    body = "## Fixes\n- Fix `kanban.failure_limit` default ([`abcdef12`](https://github.com/x/y/commit/abcdef12)) \u2014 @someone\n- Edit README.md\n"
    out, _ = wu.filter_release(body, "v1.2.3", 15000)
    assert "- Fix `kanban.failure_limit` default" in out and "abcdef12" not in out and "@someone" not in out
    assert "README.md" not in out


def test_filter_matches_the_heading_and_spills_priority_bullets():
    body = ("## Contributors\n- @someone did kanban work\n## Cron, Kanban & Delegation\n### Kanban\n"
            "- Workers ride out provider trouble\n### Cron\n- Jobs follow your main model\n## Misc\n- Faster css\n")
    out, overflow = wu.filter_release(body, "v1.0.0", 15000)
    assert "Workers ride out" in out and "Jobs follow your main model" in out
    assert "css" not in out and "@someone" not in out and overflow == ""
    out, overflow = wu.filter_release(body, "v1.0.0", 120)
    assert len(out) <= 120 and "Workers ride out" in overflow and "Jobs follow" in overflow


def test_filter_on_the_v0_22_0_release_keeps_section_scoped_changes():
    """Recorded v0.22.0 body: the bullets the keyword-only filter dropped survive, and nothing priority is lost."""
    body = (FIX / "release-v0.22.0.md").read_text()
    out, overflow = wu.filter_release(body, "v0.22.0", 15000 // 3)
    assert len(out) <= 15000 // 3
    both = out + overflow
    for needle in ("Workers ride out provider trouble", "Jobs follow your main model", "Model providers as plugins",
                   "Per-profile plugin host", "`delegation.fallback_providers`", "Memory providers moved to catalog plugins",
                   "**Connectors: Hermes works inside your apps**", "**/goal**", "`kanban_schedule`"):
        assert needle in both, needle
    assert "@teknium1" not in both  # Contributors section skipped
    assert "priority bullets in v0.22.0.overflow.md" in out


def test_overflow_file_is_written_and_listed(up, home, capsys):
    api = json.loads((FIX / "releases.json").read_text())
    api[0]["body"] = (FIX / "release-v0.22.0.md").read_text()
    up.set_api(api)
    up.etag = "W/\"fixture-v0.22.0\""
    seed(home, release="v0.22.0", hermes=LOCAL)
    ctx = run_gate(up, home, "--max-chars", "3000", capsys=capsys)["context"]
    (over,) = [Path(p) for p in ctx["overflow"]]
    assert over.name == "v0.22.1.overflow.md" and "Workers ride out provider trouble" in (
        over.read_text() + Path(ctx["filtered"][0]).read_text())


def test_help_works_without_network():
    proc = subprocess.run([sys.executable, str(SCRIPTS / "watch_upstream.py"), "--help"], capture_output=True, text=True,
                          env={**os.environ, "HTTPS_PROXY": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1"})
    assert proc.returncode == 0 and "wakeAgent" in proc.stdout


@needs_hermes
def test_real_hermes_version_is_parsed():
    assert re.match(r"\d+\.\d+\.\d+", wu.local_hermes_version("hermes") or "")


def test_squads_repo_is_not_watched(up, home, capsys):
    """Squad updates are cron builder-update's job (auto_update.py, no agent): this gate never fetches them."""
    (home / "distribution.yaml").write_text("name: builder\nversion: 1.0.0\n")
    seed(home, release="v0.22.1", hermes=LOCAL)
    assert run_gate(up, home, capsys=capsys) == {"wakeAgent": False}
    assert not [p for p, _ in up.log if "squads" in p]


# --- docs signal --------------------------------------------------------------------------------------------------

DOC_MAP = {"verified_against": "0.22.2", "references": {
    "_shared": ["reference/cli-commands.md"],
    "kanban.md": ["user-guide/features/kanban.md"],
    "cron-and-gates.md": ["user-guide/features/cron.md"],
}}


@pytest.fixture
def src(tmp_path):
    """A fake Hermes source root with the three mapped docs, an unmapped page and a generated skill page."""
    root = tmp_path / "hermes-src"
    docs = root / "website" / "docs"
    for rel, text in {"reference/cli-commands.md": "# CLI\n- hermes kanban\n",
                      "user-guide/features/kanban.md": "# Kanban\n- scratch workspaces persist\n",
                      "user-guide/features/cron.md": "# Cron\n- scripts inherit env\n",
                      "user-guide/features/other.mdx": "# Other\n",
                      "user-guide/skills/bundled/foo.md": "# generated\n"}.items():
        (docs / rel).parent.mkdir(parents=True, exist_ok=True)
        (docs / rel).write_text(text)
    (tmp_path / "doc-map.json").write_text(json.dumps(DOC_MAP))
    return root


def docs_gate(up, home, src, capsys, *extra):
    return run_gate(up, home, "--hermes-src", str(src), "--doc-map", str(src.parent / "doc-map.json"), *extra,
                    capsys=capsys)


def test_docs_first_run_seeds_the_baseline_silently(up, home, src, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)  # a state written before the docs signal existed
    assert docs_gate(up, home, src, capsys) == {"wakeAgent": False}
    snap = state(home)["reviewed"]["docs"]
    assert set(snap["files"]) == {"reference/cli-commands.md", "user-guide/features/kanban.md",
                                  "user-guide/features/cron.md"}
    assert "user-guide/features/other.mdx" in snap["pages"]
    assert not [p for p in snap["pages"] if p.startswith("user-guide/skills/")]  # generated pages are skipped
    assert len(list((home / "local" / "state" / "docs" / "blobs").glob("*.md"))) == 3
    assert docs_gate(up, home, src, capsys) == {"wakeAgent": False}


def test_a_changed_doc_wakes_with_a_diff_and_the_affected_reference(up, home, src, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)
    docs_gate(up, home, src, capsys)
    kanban = src / "website" / "docs" / "user-guide" / "features" / "kanban.md"
    kanban.write_text("# Kanban\n- scratch workspaces are deleted on completion\n")
    out = docs_gate(up, home, src, capsys)
    ctx = out["context"]
    assert out["wakeAgent"] is True and ctx["changed"] == ["docs"]
    assert ctx["docs"]["references"] == ["kanban.md"] and ctx["docs"]["verified_against"] == "0.22.2"
    assert ctx["docs"]["changed"] == [{"path": "user-guide/features/kanban.md", "refs": ["kanban.md"],
                                       "status": "changed"}]
    diff = Path(ctx["docs"]["diff"]).read_text()
    assert "-- scratch workspaces persist" in diff and "+- scratch workspaces are deleted on completion" in diff
    assert "References: kanban.md" in diff


def test_a_docs_wake_repeats_until_the_digest_exists(up, home, src, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)
    docs_gate(up, home, src, capsys)
    (src / "website" / "docs" / "user-guide" / "features" / "cron.md").write_text("# Cron\n- scripts get a sanitized env\n")
    assert docs_gate(up, home, src, capsys)["wakeAgent"] is True
    second = docs_gate(up, home, src, capsys)  # the digest turn failed: the same change wakes again
    assert second["wakeAgent"] is True and "-- scripts inherit env" in Path(second["context"]["docs"]["diff"]).read_text()
    digest(home)
    assert docs_gate(up, home, src, capsys) == {"wakeAgent": False}
    # the superseded reviewed copy is pruned once the new one is reviewed
    blobs = home / "local" / "state" / "docs" / "blobs"
    assert len(list(blobs.glob("*.md"))) == 3


def test_a_shared_doc_touches_every_reference(up, home, src, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)
    docs_gate(up, home, src, capsys)
    (src / "website" / "docs" / "reference" / "cli-commands.md").write_text("# CLI\n- hermes kanban\n- hermes pause\n")
    ctx = docs_gate(up, home, src, capsys)["context"]
    assert ctx["docs"]["references"] == ["*"]


def test_new_deleted_and_removed_pages_are_reported(up, home, src, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)
    docs_gate(up, home, src, capsys)
    docs = src / "website" / "docs"
    (docs / "user-guide" / "features" / "loops.md").write_text("# Loops\n")
    (docs / "user-guide" / "features" / "other.mdx").unlink()
    (docs / "user-guide" / "features" / "cron.md").unlink()
    (docs / "user-guide" / "skills" / "bundled" / "bar.md").write_text("# generated\n")
    ctx = docs_gate(up, home, src, capsys)["context"]["docs"]
    assert ctx["new_pages"] == ["user-guide/features/loops.md"]
    assert ctx["deleted_pages"] == ["user-guide/features/cron.md", "user-guide/features/other.mdx"]
    assert ctx["changed"] == [{"path": "user-guide/features/cron.md", "refs": ["cron-and-gates.md"],
                               "status": "removed"}]
    text = Path(ctx["diff"]).read_text()
    assert "## New docs pages" in text and "user-guide/features/loops.md" in text


def test_a_big_docs_diff_spills_whole_sections_to_overflow(up, home, src, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)
    docs_gate(up, home, src, capsys)
    docs = src / "website" / "docs" / "user-guide" / "features"
    (docs / "kanban.md").write_text("# Kanban\n" + "".join(f"- line {i} " + "k" * 80 + "\n" for i in range(60)))
    (docs / "cron.md").write_text("# Cron\n" + "".join(f"- line {i} " + "c" * 80 + "\n" for i in range(60)))
    ctx = docs_gate(up, home, src, capsys, "--max-chars", "6000")["context"]["docs"]
    diff, over = Path(ctx["diff"]).read_text(), Path(ctx["overflow"]).read_text()
    assert len(diff) <= 6000
    assert ("## user-guide/features/cron.md" in diff) != ("## user-guide/features/cron.md" in over)
    assert ("## user-guide/features/kanban.md" in diff) != ("## user-guide/features/kanban.md" in over)


def test_docs_dry_run_writes_nothing(up, home, src, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)
    docs_gate(up, home, src, capsys)
    before = (home / "local" / "state" / "watch.json").read_text()
    (src / "website" / "docs" / "user-guide" / "features" / "kanban.md").write_text("# Kanban\n- new\n")
    assert docs_gate(up, home, src, capsys, "--dry-run")["wakeAgent"] is True
    assert (home / "local" / "state" / "watch.json").read_text() == before
    assert not list((home / "local" / "state" / "docs").glob("*.diff.md"))


def test_no_docs_tree_skips_the_signal(up, home, tmp_path, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)
    out = run_gate(up, home, "--hermes-src", str(tmp_path / "pip-install"), "--json", capsys=capsys)
    assert out["wakeAgent"] is False and out["report"]["docs"].startswith("skipped")
    assert "docs" not in state(home)["reviewed"]


def test_install_directory_is_read_from_hermes_version(tmp_path, src):
    fake = tmp_path / "hermes"
    fake.write_text(f"#!/bin/sh\ncat {shlex.quote(str(FIX / 'hermes-version.txt'))}\n"
                    f"echo {shlex.quote('Install directory: ' + str(src))}\n")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    assert wu.hermes_version_info(str(fake)) == (LOCAL, str(src))


def test_a_docs_and_a_release_change_wake_once_together(up, home, src, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)
    docs_gate(up, home, src, capsys)
    seed_state = state(home)
    seed_state["reviewed"]["release"] = "v0.22.0"
    gate_lib.save_state("watch", seed_state, home / "local" / "state")
    (src / "website" / "docs" / "user-guide" / "features" / "kanban.md").write_text("# Kanban\n- new\n")
    ctx = docs_gate(up, home, src, capsys)["context"]
    assert ctx["changed"] == ["release", "docs"] and ctx["tags"] == ["v0.22.1"]
    digest(home)
    assert docs_gate(up, home, src, capsys) == {"wakeAgent": False}


def test_shipped_doc_map_points_at_real_docs_and_every_reference():
    """Every hermes-platform reference has docs in the map; with a Hermes checkout, every mapped path exists."""
    data = wu.load_doc_map(wu.DOC_MAP)
    refs = {p.name for p in (REPO / "skills" / "hermes-platform" / "references").glob("*.md")}
    assert set(data["references"]) - {"_shared"} == refs
    assert re.fullmatch(r"\d+\.\d+\.\d+", data["verified_against"])
    _, where = wu.hermes_version_info("hermes") if shutil.which("hermes") else (None, None)
    docs = Path(where or "/nonexistent") / "website" / "docs"
    if docs.is_dir():
        missing = [p for paths in data["references"].values() for p in paths if not (docs / p).is_file()]
        assert not missing, f"doc-sources.json names docs this Hermes does not have: {missing}"


def test_maintainer_mode_digests_a_docs_change_on_main_before_it_is_installed(up, home, src, capsys):
    """The owner's builder watches Hermes main: a docs change committed upstream (and not in the installed tree)
    wakes the digest with the affected reference; the installed tree alone stays silent."""
    import subprocess as sp
    git = lambda *a: sp.run(["git", "-C", str(src), *a], check=True, capture_output=True)
    git("init", "-q", "-b", "main"); git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
    seed(home, release="v0.22.1", hermes=LOCAL)
    docs_gate(up, home, src, capsys, "--docs-ref", "main")  # baseline
    assert docs_gate(up, home, src, capsys, "--docs-ref", "main")["wakeAgent"] is False
    git("checkout", "-q", "-b", "next")
    (src / "website/docs/user-guide/features/kanban.md").write_text("# Kanban\n- cards show plugin badges\n")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qam", "upstream change")
    git("checkout", "-q", "main")  # the installed tree keeps the old text
    out = docs_gate(up, home, src, capsys, "--docs-ref", "next")
    assert out["wakeAgent"] is True and out["context"]["docs"]["references"] == ["kanban.md"]
    assert "plugin badges" in Path(out["context"]["docs"]["diff"]).read_text()


def test_a_bad_docs_ref_keeps_the_reviewed_docs_and_reports_the_error(up, home, src, capsys):
    seed(home, release="v0.22.1", hermes=LOCAL)
    docs_gate(up, home, src, capsys)
    before = state(home)["reviewed"]["docs"]
    out = docs_gate(up, home, src, capsys, "--docs-ref", "no-such-ref", "--json")
    assert out["wakeAgent"] is False and any(e.startswith("docs-ref") for e in out["report"]["errors"])
    assert state(home)["reviewed"]["docs"] == before
