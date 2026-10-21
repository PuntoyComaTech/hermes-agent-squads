"""Offline tests for the portal wrapper (searching-portals/scripts/portals.py) and its CLIs.

The wrapper tests run portals.py as a subprocess against fake portals built in a temp directory, and against the
shipped manifests on the paths that never reach the network. No test sends a request anywhere. The bun suites run
only when bun is installed and are skipped otherwise.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "squads" / "jobs" / "skills"
SKILL = SKILLS / "searching-portals"
SCRIPTS = SKILL / "scripts"
PORTALS = SCRIPTS / "portals.py"
TEMPLATE = SKILLS / "adding-portals" / "templates" / "portal-cli"
TODAY = "2026-10-20"

sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location("portals", PORTALS)
portals = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(portals)

_BUN_HOME = Path.home() / ".bun" / "bin" / "bun"
BUN = shutil.which("bun") or (str(_BUN_HOME) if _BUN_HOME.is_file() else None)
needs_bun = pytest.mark.skipif(BUN is None, reason="bun is not installed")

FAKE_CLI = r'''import json
import sys
from pathlib import Path

ALWAYS_RATE = __RATE__
HOST = "__HOST__"
ROWS = {
    "ok": [("1", "Data Analyst", "Acme", "2026-10-14", None)],
    "dated": [("2", "Old Job", "Acme", "2026-09-01", None),
              ("3", "Fresh Job", "Acme", "2026-10-18", None),
              ("4", "Undated Job", "Acme", None, None)],
    "nocompany": [("5", "Analyst", None, "2026-10-14", None)],
    "html": [("6", "Data &amp; <b>BI</b>", "Acme", "2026-10-14", None)],
    "offhost": [("7", "Analyst", "Acme", "2026-10-14", "https://elsewhere.example/7")],
    "baddetail": [("bad", "Analyst", "Acme", "2026-10-14", None)],
    "remote_mix": [("10", "Analista de dados sênior / Presencial Ciudad Ejemplo", "Acme", "2026-10-20", None),
                   ("11", "Talent Data Analyst - Remote", "Acme", "2026-10-19", None),
                   ("12", "Data Analyst", "Acme", "2026-10-18", None)],
    "hashco": [("13", "Data Analyst", "8a78826757bc744e0157bf0e31470032", "2026-10-16", None)],
}


def fail(message, code):
    sys.stderr.write(json.dumps({"error": message, "code": code}) + "\n")
    sys.exit(1)


argv = sys.argv[1:]
Path(__file__).with_name("last.json").write_text(json.dumps(argv), encoding="utf-8")
cmd = argv[0] if argv else ""


def value(flag):
    return argv[argv.index(flag) + 1] if flag in argv else None


if cmd == "search":
    query = value("--query") or ""
    if ALWAYS_RATE or query == "rate":
        fail("Request failed: 429 Too Many Requests", "SEARCH_FAILED")
    if query == "boom":
        fail("parser exploded", "PARSE_FAILED")
    if query == "junk":
        print("<html>not json</html>")
        sys.exit(0)
    rows = []
    for ident, title, company, date, url in ROWS.get(query, []):
        rows.append({"id": ident, "title": title, "company": company, "location": "Lima, Peru",
                     "date": date, "url": url or f"https://{HOST}/jobs/{ident}"})
    print(json.dumps({"meta": {"count": len(rows)}, "results": rows}))
    sys.exit(0)

if cmd == "detail":
    ident = argv[1].rstrip("/").rsplit("/", 1)[-1]
    if ident in ("missing", "bad"):
        fail("job not found", "NOT_FOUND")
    print(json.dumps({"id": ident, "title": "Data Analyst", "company": "Acme", "location": "Lima, Peru",
                      "date": "2026-10-14", "url": f"https://{HOST}/jobs/{ident}",
                      "description": "Build reports\nSQL & Python", "isActive": True}))
    sys.exit(0)

fail(f"unknown command {cmd!r}", "BAD_CMD")
'''


def manifest(name, **over):
    spec = {
        "name": name,
        "description": f"{name} test portal",
        "hosts": [f"{name}.example"],
        "url_hosts": [f"{name}.example"],
        "enabled": True,
        "markets": ["PE"],
        "cmd": ["{python}", "{dir}/cli.py"],
        "search_flags": {"query": "--query", "location": "--location", "jobage": "--jobage",
                         "limit": "--limit", "page": "--page", "remote": "--remote", "format": "--format"},
        "search_defaults": [],
        "required_search": [],
        "example_query": "ok",
        "retry_query": "empty",
    }
    spec.update(over)
    return spec


def make_portal(root, name, *, rate=False, **over):
    directory = root / name
    directory.mkdir(parents=True)
    source = FAKE_CLI.replace("__RATE__", "True" if rate else "False").replace("__HOST__", f"{name}.example")
    (directory / "cli.py").write_text(source, encoding="utf-8")
    (directory / "portal.json").write_text(json.dumps(manifest(name, **over)), encoding="utf-8")
    return directory


def run(args, root=None, timeout=120):
    cmd = [sys.executable, "-B", str(PORTALS)]
    if root is not None:
        cmd += ["--root", str(root)]
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run(cmd + list(args), capture_output=True, text=True, timeout=timeout, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def stdout_json(text):
    return json.loads(text)


def stderr_json(text):
    lines = [line for line in text.strip().splitlines() if line.startswith("{")]
    assert lines, f"no JSON error on stderr: {text!r}"
    return json.loads(lines[-1])


def last_argv(root, name):
    return json.loads((root / name / "last.json").read_text(encoding="utf-8"))


# --- manifests ----------------------------------------------------------------------------------------------------

class TestManifests:
    def test_shipped_manifests_validate(self):
        code, out, err = run(["list"], root=SCRIPTS)
        assert code == 0, err
        data = stdout_json(out)
        assert data["problems"] == []
        assert [p["name"] for p in data["portals"]] == ["freehire", "linkedin"]
        assert all(p["enabled"] for p in data["portals"])

    def test_broken_manifests_are_reported_not_skipped(self, tmp_path):
        make_portal(tmp_path, "good")
        bad_name = tmp_path / "wrongname"
        bad_name.mkdir()
        (bad_name / "portal.json").write_text(json.dumps(manifest("other")), encoding="utf-8")
        not_json = tmp_path / "notjson"
        not_json.mkdir()
        (not_json / "portal.json").write_text("{", encoding="utf-8")
        code, out, _ = run(["list"], root=tmp_path)
        assert code == 0
        data = stdout_json(out)
        assert [p["name"] for p in data["portals"]] == ["good"]
        problems = {p["portal"]: p["error"] for p in data["problems"]}
        assert "name must equal the directory name" in problems["wrongname"]
        assert problems["notjson"]

    def test_named_broken_portal_is_refused(self, tmp_path):
        bad = tmp_path / "broken"
        bad.mkdir()
        (bad / "portal.json").write_text(json.dumps(manifest("broken", cmd=[])), encoding="utf-8")
        code, out, err = run(["search", "-q", "ok", "--portal", "broken"], root=tmp_path)
        assert code == 1 and out == ""
        assert stderr_json(err)["code"] == "BAD_PORTAL"

    @pytest.mark.parametrize("change, fragment", [
        (lambda s: s.pop("cmd"), "lacks cmd"),
        (lambda s: s.update(name="other"), "name must equal"),
        (lambda s: s["search_flags"].pop("format"), "format"),
        (lambda s: s.update(required_search=["remote", "page"],
                            search_flags={"format": "--format", "remote": "--remote"}),
         "required_search names a key"),
        (lambda s: s.update(required_search=["location"]), "example_location"),
        (lambda s: s.update(enabled="yes"), "enabled"),
        (lambda s: s.update(example_query="  "), "example_query"),
        (lambda s: s.update(url_hosts="fake.example"), "url_hosts"),
        (lambda s: s["search_flags"].update(bogus="--bogus"), "unknown keys"),
    ])
    def test_validate_manifest_rejects_each_bad_shape(self, change, fragment):
        spec = manifest("fake")
        change(spec)
        with pytest.raises(portals.PortalError) as err:
            portals.validate_manifest(spec, Path("fake"))
        assert fragment in str(err.value)


# --- search -------------------------------------------------------------------------------------------------------

class TestSearch:
    def test_default_search_returns_normalised_rows(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, out, err = run(["search", "-q", "ok", "--today", TODAY], root=tmp_path)
        assert code == 0, err
        data = stdout_json(out)
        assert data["meta"]["count"] == 1 and data["meta"]["failed"] == [] and data["meta"]["skipped"] == []
        row = data["results"][0]
        assert set(row) == {"id", "title", "company", "location", "date", "url", "portal"}
        assert row == {"id": "1", "title": "Data Analyst", "company": "Acme", "location": "Lima, Peru",
                       "date": "2026-10-14", "url": "https://fake.example/jobs/1", "portal": "fake"}

    def test_window_drops_old_rows_and_keeps_undated_ones(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, out, _ = run(["search", "-q", "dated", "--today", TODAY], root=tmp_path)
        assert code == 0
        data = stdout_json(out)
        assert [r["id"] for r in data["results"]] == ["3", "4"]
        assert data["results"][1]["date"] is None
        portal_meta = data["meta"]["portals"][0]
        assert portal_meta["dropped_older"] == 1 and portal_meta["undated"] == 1

    def test_limit_caps_each_portal(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, out, _ = run(["search", "-q", "dated", "--today", TODAY, "--limit", "1"], root=tmp_path)
        assert code == 0
        assert [r["id"] for r in stdout_json(out)["results"]] == ["3"]

    def test_only_mapped_flags_are_sent_in_order(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, _, _ = run(["search", "-q", "ok", "--today", TODAY], root=tmp_path)
        assert code == 0
        assert last_argv(tmp_path, "fake") == ["search", "--query", "ok", "--jobage", "14", "--limit", "20",
                                               "--format", "json"]

    def test_passthrough_reaches_a_named_portal(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, _, err = run(["search", "-q", "ok", "--portal", "fake", "--today", TODAY, "--", "--country", "PE"],
                           root=tmp_path)
        assert code == 0, err
        assert last_argv(tmp_path, "fake")[-2:] == ["--country", "PE"]

    def test_partial_failure_keeps_the_good_rows(self, tmp_path):
        make_portal(tmp_path, "good")
        make_portal(tmp_path, "down", rate=True)
        code, out, err = run(["search", "-q", "ok", "--today", TODAY], root=tmp_path)
        assert code == 1
        data = stdout_json(out)
        assert [r["portal"] for r in data["results"]] == ["good"]
        assert data["meta"]["failed"] == [{"portal": "down", "code": "SEARCH_FAILED",
                                           "error": "Request failed: 429 Too Many Requests"}]
        assert stderr_json(err)["portal"] == "down"

    def test_location_only_portal_is_skipped_without_a_place(self, tmp_path):
        make_portal(tmp_path, "geo", required_search=["location"], example_location="Lima, Peru")
        make_portal(tmp_path, "plain", search_flags={"query": "--query", "limit": "--limit", "format": "--format"})
        code, out, _ = run(["search", "-q", "ok", "--today", TODAY], root=tmp_path)
        assert code == 0
        data = stdout_json(out)
        assert [s["portal"] for s in data["meta"]["skipped"]] == ["geo"]
        assert data["meta"]["skipped"][0]["code"] == "MISSING_ARG"
        assert {r["portal"] for r in data["results"]} == {"plain"}

    def test_facet_only_portal_is_skipped_when_a_place_is_given(self, tmp_path):
        make_portal(tmp_path, "plain", search_flags={"query": "--query", "limit": "--limit", "format": "--format"})
        code, out, err = run(["search", "-q", "ok", "-l", "Lima, Peru", "--today", TODAY], root=tmp_path)
        assert code == 1 and out == ""
        assert stderr_json(err)["code"] == "NO_PORTALS"

    def test_named_portal_that_cannot_take_the_request_fails(self, tmp_path):
        make_portal(tmp_path, "plain", search_flags={"query": "--query", "limit": "--limit", "format": "--format"})
        code, out, _ = run(["search", "-q", "ok", "--portal", "plain", "-l", "Lima"], root=tmp_path)
        assert code == 1
        assert stdout_json(out)["meta"]["failed"][0]["code"] == "UNSUPPORTED_FLAG"

    @pytest.mark.parametrize("args", [
        ["search", "-q", "-x"],
        ["search", "-q", "ok", "--max-age-days", "0"],
        ["search", "-q", "ok", "--limit", "0"],
        ["search", "-q", "ok", "--today", "2026-13-01"],
        ["search", "-q", "ok", "--remote", "remotely"],
    ])
    def test_bad_values_are_refused_before_any_cli_runs(self, tmp_path, args):
        make_portal(tmp_path, "fake")
        code, out, err = run(args, root=tmp_path)
        assert code == 1 and out == ""
        assert stderr_json(err)["code"] == "BAD_ARG"
        assert not (tmp_path / "fake" / "last.json").exists()

    def test_no_enabled_portal_is_an_error(self, tmp_path):
        make_portal(tmp_path, "fake", enabled=False)
        code, out, err = run(["search", "-q", "ok"], root=tmp_path)
        assert code == 1
        assert stderr_json(err)["code"] == "NO_PORTALS"


# --- detail -------------------------------------------------------------------------------------------------------

class TestDetail:
    def test_bare_id_needs_a_portal(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, _, err = run(["detail", "1"], root=tmp_path)
        assert code == 1 and stderr_json(err)["code"] == "BAD_ARG"

    def test_bare_id_with_portal_returns_cleaned_detail(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, out, err = run(["detail", "1", "--portal", "fake"], root=tmp_path)
        assert code == 0, err
        job = stdout_json(out)
        assert job["id"] == "1" and job["portal"] == "fake"
        assert job["description"] == "Build reports\nSQL & Python"
        assert job["details"]["isActive"] is True

    def test_url_routes_to_the_portal_that_owns_the_host(self, tmp_path):
        make_portal(tmp_path, "fake")
        make_portal(tmp_path, "other")
        code, out, err = run(["detail", "https://fake.example/jobs/1"], root=tmp_path)
        assert code == 0, err
        assert stdout_json(out)["portal"] == "fake"

    def test_foreign_host_is_refused_before_any_cli_runs(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, out, err = run(["detail", "https://boards.greenhouse.io/acme/jobs/1"], root=tmp_path)
        assert code == 1 and out == ""
        assert stderr_json(err)["code"] == "BAD_ID"
        assert not (tmp_path / "fake" / "last.json").exists()

    def test_named_portal_must_own_the_url_host(self, tmp_path):
        make_portal(tmp_path, "fake")
        make_portal(tmp_path, "other")
        code, _, err = run(["detail", "https://fake.example/jobs/1", "--portal", "other"], root=tmp_path)
        assert code == 1 and stderr_json(err)["code"] == "BAD_ID"

    def test_not_found_is_reported_on_stderr(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, out, err = run(["detail", "missing", "--portal", "fake"], root=tmp_path)
        assert code == 1 and out == ""
        assert stderr_json(err)["code"] == "NOT_FOUND"

    def test_detail_takes_no_portal_flags(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, _, err = run(["detail", "1", "--portal", "fake", "--", "--country", "PE"], root=tmp_path)
        assert code == 1 and stderr_json(err)["code"] == "BAD_ARG"


# --- health -------------------------------------------------------------------------------------------------------

class TestHealth:
    def health(self, root, name, *extra):
        code, out, err = run(["health", "--portal", name, "--today", TODAY, *extra], root=root)
        assert code == 0, err
        return stdout_json(out)["portals"][0]

    def test_healthy_portal(self, tmp_path):
        make_portal(tmp_path, "fake")
        report = self.health(tmp_path, "fake")
        assert report["status"] == "healthy" and report["reasons"] == [] and report["probes"] == 1

    def test_detail_check_adds_one_probe(self, tmp_path):
        make_portal(tmp_path, "fake")
        report = self.health(tmp_path, "fake", "--detail")
        assert report["status"] == "healthy" and report["probes"] == 2

    def test_empty_example_query_retries_once_with_the_retry_word(self, tmp_path):
        make_portal(tmp_path, "fake", example_query="empty", retry_query="ok")
        report = self.health(tmp_path, "fake")
        assert report["status"] == "healthy" and report["probes"] == 2
        assert any("retry_query" in note for note in report["notes"])

    def test_zero_results_twice_is_broken(self, tmp_path):
        make_portal(tmp_path, "fake", example_query="empty", retry_query="empty")
        report = self.health(tmp_path, "fake")
        assert report["status"] == "broken"
        assert "0 results" in report["reasons"][0]

    def test_rate_limit_is_inconclusive_and_never_retried(self, tmp_path):
        make_portal(tmp_path, "fake", example_query="rate")
        report = self.health(tmp_path, "fake")
        assert report["status"] == "inconclusive"
        assert report["probes"] == 1

    def test_always_rate_limited_portal_is_inconclusive(self, tmp_path):
        make_portal(tmp_path, "fake", rate=True)
        assert self.health(tmp_path, "fake")["status"] == "inconclusive"

    @pytest.mark.parametrize("query, fragment", [
        ("nocompany", "company null or empty"),
        ("html", "undecoded HTML"),
        ("offhost", "not on fake.example"),
    ])
    def test_degraded_scan_flags(self, tmp_path, query, fragment):
        make_portal(tmp_path, "fake", example_query=query)
        report = self.health(tmp_path, "fake")
        assert report["status"] == "degraded"
        assert any(fragment in reason for reason in report["reasons"])

    def test_unparseable_output_is_broken(self, tmp_path):
        make_portal(tmp_path, "fake", example_query="junk")
        assert self.health(tmp_path, "fake")["status"] == "broken"

    def test_cli_error_without_a_block_signal_is_broken(self, tmp_path):
        make_portal(tmp_path, "fake", example_query="boom")
        report = self.health(tmp_path, "fake")
        assert report["status"] == "broken" and "PARSE_FAILED" in report["reasons"][0]

    def test_failed_detail_degrades_a_healthy_search(self, tmp_path):
        make_portal(tmp_path, "fake", example_query="baddetail")
        report = self.health(tmp_path, "fake", "--detail")
        assert report["status"] == "degraded" and report["reasons"][0].startswith("detail")

    def test_unknown_portal_is_an_error(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, _, err = run(["health", "--portal", "nope"], root=tmp_path)
        assert code == 1 and stderr_json(err)["code"] == "UNKNOWN_PORTAL"


# --- shipped portals, offline paths -------------------------------------------------------------------------------

class TestShippedPortalsOffline:
    def test_linkedin_search_needs_a_place_and_never_runs(self):
        code, out, _ = run(["search", "-q", "data analyst", "--portal", "linkedin"], root=SCRIPTS)
        assert code == 1
        assert stdout_json(out)["meta"]["failed"][0]["code"] == "MISSING_ARG"

    def test_freehire_refuses_a_place_argument(self):
        code, out, _ = run(["search", "-q", "engineer", "-l", "Lima, Peru", "--portal", "freehire"], root=SCRIPTS)
        assert code == 1
        assert stdout_json(out)["meta"]["failed"][0]["code"] == "UNSUPPORTED_FLAG"

    def test_remote_mode_is_a_closed_choice(self):
        code, _, err = run(["search", "-q", "engineer", "--remote", "remotely", "--portal", "freehire"], root=SCRIPTS)
        assert code == 1 and stderr_json(err)["code"] == "BAD_ARG"

    def test_detail_refuses_a_greenhouse_link(self):
        code, out, err = run(["detail", "https://boards.greenhouse.io/acme/jobs/1"], root=SCRIPTS)
        assert code == 1 and out == "" and stderr_json(err)["code"] == "BAD_ID"

    def test_detail_refuses_a_linkedin_url_for_freehire(self):
        code, _, err = run(["detail", "https://www.linkedin.com/jobs/view/4000000001", "--portal", "freehire"],
                           root=SCRIPTS)
        assert code == 1 and stderr_json(err)["code"] == "BAD_ID"

    def test_help_exits_zero(self):
        assert run(["--help"])[0] == 0
        assert run(["search", "--help"])[0] == 0

    def test_no_command_is_a_usage_error(self):
        code, _, err = run([], root=SCRIPTS)
        assert code == 1 and stderr_json(err)["code"] == "BAD_ARG"


# --- work mode, shortfall, identifiers and the blocklist ---------------------------------------------------------------

def run_env(args, root, env_extra):
    cmd = [sys.executable, "-B", str(PORTALS), "--root", str(root), *args]
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", **env_extra}
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=env)
    return proc.returncode, proc.stdout, proc.stderr


class TestWorkMode:
    def test_remote_request_drops_onsite_keeps_unstated_flagged_and_reports_the_shortfall(self, tmp_path):
        # Asked for 15 remote rows; the portal sent 3 rows: one in-person, one remote, one that says nothing about the
        # place of work (most LinkedIn rows). The in-person row goes; the unstated one stays, marked unconfirmed, so a
        # real remote opening is not lost before the location gate reads its body.
        make_portal(tmp_path, "fake")
        code, out, err = run(["search", "-q", "remote_mix", "--remote", "remote", "--limit", "15", "--today", TODAY],
                             root=tmp_path)
        assert code == 0, err
        data = stdout_json(out)
        rows = {r["id"]: r for r in data["results"]}
        assert rows["11"]["work_mode"] == "remote" and not rows["11"].get("work_mode_unconfirmed")
        unstated = [r for r in data["results"] if r.get("work_mode_unconfirmed")]
        assert len(unstated) == 1 and unstated[0].get("work_mode") is None
        assert all(r.get("work_mode") != "onsite" for r in data["results"])
        meta = data["meta"]["portals"][0]
        assert (meta["asked"], meta["returned"], meta["count"], meta["shortfall"]) == (15, 3, 2, 13)
        assert meta["dropped_work_mode"] == {"onsite": 1}
        assert meta["unconfirmed_work_mode"] == 1

    def test_presencial_row_is_labelled_onsite_without_a_remote_filter(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, out, _ = run(["search", "-q", "remote_mix", "--today", TODAY], root=tmp_path)
        assert code == 0
        rows = {r["id"]: r for r in stdout_json(out)["results"]}
        assert rows["10"]["work_mode"] == "onsite", rows["10"]
        assert "work_mode" not in rows["12"], "a row that says nothing is not labelled"
        assert rows["11"]["work_mode"] == "remote"

    def test_a_portal_work_mode_label_wins_over_the_title(self, tmp_path):
        make_portal(tmp_path, "fake")
        assert portals.normalise({"id": "1", "title": "Data Analyst - Presencial", "company": "Acme",
                                  "date": "2026-10-14", "url": "https://fake.example/1",
                                  "work_mode": "remote"}, "fake")["work_mode"] == "remote"

    @pytest.mark.parametrize("text,expected", [
        ("Presencial Lima", "onsite"), ("On-site in Bogotá", "onsite"), ("Remote (LatAm)", "remote"),
        ("Trabajo remoto desde casa", "remote"), ("Híbrido 3 días", "hybrid"), ("Remote or hybrid", None),
        ("Presencial o remoto", None), ("Data Analyst", None), ("Talent Data Analyst - Remote", "remote"),
    ])
    def test_work_mode_words_are_read_and_an_ambiguous_row_is_not_forced(self, text, expected):
        assert portals.infer_work_mode(text) == expected

    def test_a_remote_row_with_an_office_mention_in_the_description_stays_remote(self):
        row = portals.normalise({"id": "1", "title": "Data Analyst", "company": "Acme", "date": "2026-10-14",
                                 "url": "https://fake.example/1", "location": "Lima",
                                 "description": "Fully remote role; the team has an office in Lima."}, "fake")
        assert row["work_mode"] == "remote", row


class TestIdentifiers:
    def test_a_hash_company_is_returned_as_null_and_the_search_flags_it(self, tmp_path):
        # A freehire row carried a 22-hex id as its company. The company must not be a name in the output.
        make_portal(tmp_path, "fake")
        code, out, _ = run(["search", "-q", "hashco", "--today", TODAY], root=tmp_path)
        assert code == 0
        row = stdout_json(out)["results"][0]
        assert row["company"] is None
        assert row["title"] == "Data Analyst"

    def test_health_reports_an_identifier_company_as_degraded(self, tmp_path):
        make_portal(tmp_path, "fake", example_query="hashco", retry_query="hashco")
        code, out, _ = run(["health", "--portal", "fake", "--today", TODAY], root=tmp_path)
        assert code == 0
        report = stdout_json(out)["portals"][0]
        assert report["status"] == "degraded" and any("identifier" in r for r in report["reasons"]), report


class TestBlocklist:
    def test_a_default_search_skips_a_blocklisted_portal_and_never_runs_its_cli(self, tmp_path):
        # The user's JOBS_BLOCKLIST refuses a host, so the portal CLI is not started for it.
        make_portal(tmp_path, "fake")
        make_portal(tmp_path, "good")
        code, out, _ = run_env(["search", "-q", "ok", "--today", TODAY], tmp_path, {"JOBS_BLOCKLIST": "fake.example"})
        assert code == 0
        data = stdout_json(out)
        assert [s["code"] for s in data["meta"]["skipped"]] == ["BLOCKED"]
        assert {r["portal"] for r in data["results"]} == {"good"}
        assert not (tmp_path / "fake" / "last.json").exists(), "a blocked portal's CLI must not run"

    def test_a_named_blocklisted_portal_fails_with_blocked(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, out, _ = run_env(["search", "-q", "ok", "--portal", "fake", "--today", TODAY], tmp_path,
                               {"JOBS_BLOCKLIST": "fake.example"})
        assert code == 1
        assert stdout_json(out)["meta"]["failed"][0]["code"] == "BLOCKED"
        assert not (tmp_path / "fake" / "last.json").exists()

    def test_a_subdomain_of_a_blocklisted_host_is_refused_too(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, out, _ = run_env(["search", "-q", "ok", "--portal", "fake", "--today", TODAY], tmp_path,
                               {"JOBS_BLOCKLIST": "example"})
        assert stdout_json(out)["meta"]["failed"][0]["code"] == "BLOCKED"

    def test_detail_refuses_a_blocklisted_portal_before_its_cli_runs(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, out, err = run_env(["detail", "https://fake.example/jobs/1"], tmp_path, {"JOBS_BLOCKLIST": "fake.example"})
        assert code == 1 and out == "" and stderr_json(err)["code"] == "BLOCKED"
        assert not (tmp_path / "fake" / "last.json").exists()

    def test_health_reports_a_blocklisted_portal_as_blocked_with_no_probe(self, tmp_path):
        make_portal(tmp_path, "fake")
        code, out, _ = run_env(["health", "--portal", "fake", "--today", TODAY], tmp_path,
                               {"JOBS_BLOCKLIST": "fake.example"})
        assert code == 0
        report = stdout_json(out)["portals"][0]
        assert report["status"] == "blocked" and report["probes"] == 0
        assert not (tmp_path / "fake" / "last.json").exists()

    def test_the_linkedin_portal_is_not_blocked_by_the_default_list(self):
        # The built-in linkedin.com entry is for the browser and fetch tools. The sanctioned LinkedIn portal CLI runs
        # when JOBS_BLOCKLIST is empty.
        assert portals.user_blocklist({}) == []
        assert portals.blocked_portal(type("P", (), {"hosts": ["linkedin.com"]})(), portals.user_blocklist({})) is None


class TestShippedPortalPolicy:
    def test_freehire_search_is_lean_by_default_and_the_skill_says_so(self):
        manifest = json.loads((SCRIPTS / "freehire" / "portal.json").read_text(encoding="utf-8"))
        assert "--no-description" in manifest["search_defaults"]
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        assert "already carries full descriptions" not in text
        assert "no description" in text and "at most 5" in text

    def test_linkedin_policy_is_written_in_the_intake_reference(self):
        intake = (SKILLS / "finding-jobs" / "references" / "intake-safety.md").read_text(encoding="utf-8")
        assert "LinkedIn policy" in intake and "JOBS_BLOCKLIST" in intake and "public guest listings" in (
            SKILL / "SKILL.md").read_text(encoding="utf-8")


# --- repository hygiene -------------------------------------------------------------------------------------------

def _w(*parts):
    """Join fragments so this file never carries a banned word literally."""
    return "".join(parts)


FOREIGN = [
    _w("cla", "ude"), _w("anthro", "pic"), _w("ma", "ds"), _w("lore", "ntzen"), _w("ai-job-", "search"),
    _w("dan", "ish"), _w("den", "mark"), _w("dan", "sk"), _w("job", "index"), _w("job", "net"),
    _w("job", "bank"), _w("job", "danmark"), _w("la", "tex"), _w("modern", "cv"), _w("xe", "latex"),
    _w("lua", "latex"), _w(".cla", "ude"), _w("CLA", "UDE.md"), _w("framework", "_version"), _w("fo", "rk"),
    _w("no", "tion"), _w("up", "stream"), _w("copen", "hagen"), _w("ber", "lin"), _w("ger", "many"),
    _w("lon", "don"), _w("mum", "bai"), _w("bengal", "uru"), _w("hydera", "bad"), _w("zen", "sar"),
    _w("porta", "pulito"), _w("linkedin", "-search"), _w("freehire", "-search"), _w("/ap", "ply"),
    _w("/scr", "ape"), _w("/se", "tup"), _w("/add-", "portal"),
]
FOREIGN_RE = re.compile("|".join(r"\b" + re.escape(term) + r"\b" if term[0].isalnum() else re.escape(term)
                                 for term in FOREIGN) + r"|(?<![&\w])#\d{3,}\b", re.IGNORECASE)
TEXT_SUFFIXES = {".md", ".ts", ".json", ".py", ".html", ".yaml", ".txt"}


class TestRepoHygiene:
    def test_no_foreign_traces_in_the_skills(self):
        hits = []
        for skill in (SKILL, SKILLS / "adding-portals"):
            for path in skill.rglob("*"):
                if path.is_file() and path.suffix in TEXT_SUFFIXES:
                    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                        if FOREIGN_RE.search(line):
                            hits.append(f"{path.relative_to(REPO)}:{number}: {line.strip()[:120]}")
        assert hits == []

    def test_no_install_artifacts_in_the_skills(self):
        for skill in (SKILL, SKILLS / "adding-portals"):
            for name in ("node_modules", "bun.lock", "bun.lockb", "package-lock.json", "__pycache__"):
                assert not list(skill.rglob(name)), f"{name} found under {skill.relative_to(REPO)}"


# --- bun suites (skipped without bun) -----------------------------------------------------------------------------

def bun_test(directory):
    return subprocess.run([BUN, "test", "--timeout", "30000"], cwd=str(directory), capture_output=True, text=True,
                          timeout=600)


@needs_bun
@pytest.mark.parametrize("portal", ["linkedin", "freehire"])
def test_portal_cli_suite_passes(portal):
    done = bun_test(SCRIPTS / portal)
    output = done.stdout + done.stderr
    assert done.returncode == 0, output[-2000:]
    assert re.search(r"\b0 fail\b", output), output[-500:]


@needs_bun
@pytest.mark.parametrize("portal", ["linkedin", "freehire"])
def test_portal_cli_help_exits_zero(portal):
    done = subprocess.run([BUN, "run", "src/cli.ts", "--help"], cwd=str(SCRIPTS / portal), capture_output=True,
                          text=True, timeout=60)
    assert done.returncode == 0, done.stderr


@needs_bun
def test_template_suite_runs_from_a_copy(tmp_path):
    copy = tmp_path / "portal-cli"
    shutil.copytree(TEMPLATE, copy)
    done = bun_test(copy)
    assert done.returncode == 0, (done.stdout + done.stderr)[-2000:]


# --- search speed: the prefilter reads the search rows before any detail call ---------------------------------------

PREFILTER_PROFILE = """\
---
user_language: es
search_keywords: {en: ["data analyst", "BI analyst"], es: ["analista de datos"]}
target_roles: ["Data analyst", "BI analyst"]
acceptable_roles: ["Operations analyst, data focus"]
work_mode: [remote_region, hybrid]
search_days: 14
---
Fictional person for the prefilter tests.
"""

MATCHING_TITLES = ["Data Analyst", "BI Analyst", "Senior Data Analyst", "Analista de datos",
                   "Operations Analyst, data focus"]
OTHER_TITLES = ["Sales Manager", "Frontend Developer", "Registered Nurse", "Warehouse Associate", "Chef de cuisine",
                "Customer Success Lead", "Mechanical Engineer", "Accountant", "Recruiter", "Marketing Coordinator"]


def fictional_rows(total: int, matching: int, today: str = TODAY) -> list:
    """Search rows as a portal returns them: id, title, company, location, date, url, portal. Fictional companies.
    The first `matching` rows carry a profile title; the rest carry titles no profile term names."""
    import datetime as dt
    start = dt.date.fromisoformat(today)
    rows = []
    for i in range(total):
        title = MATCHING_TITLES[i % len(MATCHING_TITLES)] if i < matching else OTHER_TITLES[i % len(OTHER_TITLES)]
        rows.append({"id": f"row-{i}", "title": title, "company": f"Example Co {i % 17}", "location": "Lima, Peru",
                     "date": (start - dt.timedelta(days=i % 13)).isoformat(),
                     "url": f"https://fake.example/jobs/{i}", "portal": "linkedin" if i % 2 else "freehire"})
    return rows


def prefilter(tmp_path, rows, profile=PREFILTER_PROFILE, project=None, today=TODAY):
    tmp_path.mkdir(parents=True, exist_ok=True)
    profile_path = tmp_path / "profile.md"
    profile_path.write_text(profile, encoding="utf-8")
    rows_path = tmp_path / "rows.json"
    rows_path.write_text(json.dumps({"meta": {"count": len(rows)}, "results": rows}, ensure_ascii=False), encoding="utf-8")
    args = ["prefilter", "--profile", str(profile_path), "--input", str(rows_path), "--today", today]
    if project is not None:
        args += ["--project", str(project)]
    return run(args)


def test_a_169_row_search_keeps_every_matching_title_and_stays_within_the_caps(tmp_path):
    # A 169-row search: 40 rows carry a profile title. Every one of them is kept; the detail calls stay at the cap.
    rows = fictional_rows(169, matching=40)
    code, out, err = prefilter(tmp_path, rows)
    assert code == 0, err
    data = stdout_json(out)
    assert data["meta"]["input"] == 169
    kept = {r["id"] for r in data["candidates"]}
    assert {r["id"] for r in rows[:40]} <= kept, "a row with a matching title was dropped"
    profile_words = {"data", "analyst", "bi", "analista", "de", "datos", "operations", "focus"}
    for r in data["candidates"]:
        assert set(r["title"].lower().replace(",", " ").split()) & profile_words, f"non-matching title kept: {r['title']}"
    assert len(data["candidates"]) <= 60 and len(data["detail_targets"]) <= 15
    assert data["meta"]["max_detail_calls"] == 15 and data["meta"]["max_candidates"] == 60


def test_the_candidate_cap_keeps_the_newest_rows(tmp_path):
    # 75 matching rows against the default cap of 60: 60 are read, the newest first, and 15 are reported over the cap.
    rows = fictional_rows(75, matching=75)
    code, out, err = prefilter(tmp_path, rows)
    assert code == 0, err
    data = stdout_json(out)
    assert len(data["candidates"]) == 60 and data["meta"]["over_candidate_cap"] == 15
    dates = [r["date"] for r in data["candidates"]]
    assert dates == sorted(dates, reverse=True), "candidates are not newest first"


def test_detail_calls_follow_the_profile_key_and_default_to_fifteen(tmp_path):
    rows = fictional_rows(40, matching=40)
    code, out, _ = prefilter(tmp_path, rows, profile=PREFILTER_PROFILE.replace("search_days: 14",
                                                                               "search_days: 14\nmax_detail_calls: 3"))
    assert code == 0
    assert len(stdout_json(out)["detail_targets"]) == 3
    code, out, _ = prefilter(tmp_path / "again", rows)
    assert len(stdout_json(out)["detail_targets"]) == 15


def test_a_profile_without_search_terms_is_refused_not_guessed(tmp_path):
    code, out, err = prefilter(tmp_path, fictional_rows(5, matching=5),
                               profile="---\nuser_language: es\n---\nNo terms here.\n")
    assert code == 1
    assert stderr_json(err)["code"] == "NO_TERMS", err


def _write_opening(project: Path, name: str, date: str, status: str = "found") -> None:
    folder = project / "openings" / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "status.json").write_text(json.dumps({"id": name, "status": status, "history": [
        {"date": date, "status": "found", "by": "jobs-scout", "note": ""}]}), encoding="utf-8")


def test_the_analysis_cap_counts_this_projects_cards_filed_today_only(tmp_path):
    # Three cards filed today in this project, two yesterday, and four today in another project: 3 of 5 used.
    mine, other = tmp_path / "ana-search", tmp_path / "other-search"
    for i in range(3):
        _write_opening(mine, f"JOB-A-{i}", "2026-10-20T08:14")
    for i in range(2):
        _write_opening(mine, f"JOB-Y-{i}", "2026-10-19T08:14")
    for i in range(4):
        _write_opening(other, f"JOB-O-{i}", "2026-10-20T08:14")
    code, out, err = prefilter(tmp_path / "run", fictional_rows(5, matching=5), project=mine)
    assert code == 0, err
    cap = stdout_json(out)["analysis_cap"]
    assert (cap["max"], cap["used_today"], cap["left"]) == (5, 3, 2), cap
    assert cap["summary"] == "3 of 5 used today; 2 left", cap
    assert sorted(cap["openings"]) == ["JOB-A-0", "JOB-A-1", "JOB-A-2"], cap


def test_a_full_analysis_cap_says_when_the_next_analysis_is_possible(tmp_path):
    mine = tmp_path / "ana-search"
    for i in range(5):
        _write_opening(mine, f"JOB-F-{i}", "2026-10-20T08:14")
    code, out, _ = prefilter(tmp_path / "run", fictional_rows(5, matching=5), project=mine)
    cap = stdout_json(out)["analysis_cap"]
    assert cap["left"] == 0
    assert cap["summary"] == "5 of 5 used today; next: tomorrow or ask me to analyze <id>", cap


def test_an_avoided_company_a_wrong_work_mode_and_a_stale_row_are_dropped_before_any_detail(tmp_path):
    # Each drop is counted under its own reason, and the row that says nothing about its work mode is kept and counted.
    profile = PREFILTER_PROFILE.replace("search_days: 14", "search_days: 14\navoid_companies: [\"Old Co\"]")

    def row(ident, title, company, date, mode=None):
        found = {"id": ident, "title": title, "company": company, "location": "Lima, Peru", "date": date,
                 "url": f"https://fake.example/jobs/{ident}", "portal": "linkedin"}
        if mode:
            found["work_mode"] = mode
        return found

    rows = [row("keep-1", "Data Analyst", "Example Co", TODAY, "remote"),
            row("avoid-1", "Data Analyst", "Old Co", TODAY, "remote"),
            row("onsite-1", "Data Analyst", "Example Co", TODAY, "onsite"),
            row("stale-1", "Data Analyst", "Example Co", "2026-08-01", "remote"),
            row("unstated-1", "BI Analyst", "Example Co", TODAY)]
    code, out, err = prefilter(tmp_path, rows, profile=profile)
    assert code == 0, err
    data = stdout_json(out)
    assert {r["id"] for r in data["candidates"]} == {"keep-1", "unstated-1"}, data["candidates"]
    assert data["meta"]["dropped"] == {"title": 0, "company": 1, "work_mode": 1, "date": 1, "duplicate": 0}, data["meta"]
    assert data["meta"]["unconfirmed_work_mode"] == 1
