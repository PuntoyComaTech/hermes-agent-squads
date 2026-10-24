"""Guards for the manager side of the jobs squad: tracker.py, build_dashboard.py, skill_gaps.py and the four manager skills.

Local fixtures only (pytest tmp_path): no network, nothing under ~/.hermes. Scripts run as subprocesses with the same
interpreter as pytest, and --today pins every date so the results do not move with the calendar.
"""
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "squads" / "jobs" / "skills"
SCRIPTS = SKILLS / "jobs-contract" / "scripts"
TRACKER = SCRIPTS / "tracker.py"
DASHBOARD = SCRIPTS / "build_dashboard.py"
GAPS = SCRIPTS / "skill_gaps.py"
HPY = REPO / "scripts" / "hpy"
MANAGER_SKILLS = ("leading-job-search", "profiling-candidates", "tracking-outcomes", "planning-upskilling")
COLUMNS = ["date", "id", "company", "role", "status", "channel", "fit_score", "apply_url", "deadline", "applied_at",
           "last_contact", "follow_ups", "notes", "cv_file", "cover_letter_file", "source"]
PROFILE = ("---\nfollow_up_days: 10\nstale_days: 60\n"
           "scoring:\n  bands: {strong: 75, good: 60, moderate: 45, weak: 30}\n---\n\nFictional candidate: Ana Example.\n")
ID_ACME = "JOB-20261001-acme-data-analyst"
ID_BETA = "JOB-20261005-beta-bi-analyst"
ID_GAMMA = "JOB-20261010-gamma-pm"
TODAY = "2026-10-20"

# Fragments are joined at run time so this file never holds the words it guards against.
FOREIGN = ["cla" + "ude", "anthro" + "pic", "lorent" + "zen", "ai-job" + "-search", "dan" + "ish", "den" + "mark",
           "dan" + "sk", "jobin" + "dex", "jobn" + "et", "jobb" + "ank", "jobdan" + "mark", "la" + "tex",
           "modern" + "cv", "no" + "tion", "framework" + "_version", "fo" + "rk", "mad" + "s"]
SLASH = re.compile(r"(?<![\w/])/(apply|scrape|setup|outcome|rank|upskill|interview|expand|reset|html-report|"
                   "no" + r"tion-sync|gmail-sync|add-portal)\b")


# --- helpers ------------------------------------------------------------------------------------------------------

def run(script, *args):
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, cwd=str(REPO),
                          timeout=120)


def cli(command, project, *args, today=TODAY):
    return run(TRACKER, command, "--project", str(project), "--today", today, *args)


def seed(project, rows):
    with (project / "tracker.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in COLUMNS})


def row(rid, company, status, applied, **extra):
    values = {"date": applied, "id": rid, "company": company, "role": "Data analyst", "status": status,
              "applied_at": applied, "follow_ups": "0"}
    values.update(extra)
    return values


def read_rows(project):
    with (project / "tracker.csv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def json_out(result):
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


@pytest.fixture
def project(tmp_path):
    (tmp_path / "profile.md").write_text(PROFILE, encoding="utf-8")
    return tmp_path


# --- help and the interface -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("script", [TRACKER, DASHBOARD, GAPS])
def test_help_exits_zero(script):
    result = run(script, "--help")
    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout.lower()


def test_update_help_documents_the_inbox_flags():
    result = run(TRACKER, "update", "--help")
    assert result.returncode == 0
    for flag in ("--id", "--status", "--note", "--last-contact", "--follow-ups-inc"):
        assert flag in result.stdout, f"update --help must document {flag}"


def test_new_scripts_make_no_network_calls():
    banned = re.compile(r"^\s*(import|from)\s+(urllib|http|socket|requests|subprocess|ssl)\b", re.M)
    for script in (TRACKER, DASHBOARD, GAPS):
        source = script.read_text(encoding="utf-8")
        assert not banned.search(source), f"{script.name} must not import a network or process module"


# --- tracker: file, injection guard, vocabulary ---------------------------------------------------------------------

def test_init_writes_the_canonical_header(project):
    result = cli("init", project)
    assert result.returncode == 0, result.stderr
    header = (project / "tracker.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header == ",".join(COLUMNS)


def test_formula_cells_get_a_leading_apostrophe(project):
    cli("init", project)
    result = cli("add", project, "--id", ID_ACME, "--company", "=cmd", "--role", "R", "--status", "applied",
                 "--source", "@SUM(1)", "--channel=-x")
    assert result.returncode == 0, result.stderr
    stored = read_rows(project)[0]
    assert stored["company"] == "'=cmd"
    assert stored["source"] == "'@SUM(1)"
    assert stored["channel"] == "'-x"


def test_tab_and_carriage_return_never_start_a_cell(project):
    cli("init", project)
    cli("add", project, "--id", ID_ACME, "--company", "Acme", "--role", "R", "--status", "applied",
        "--note", "\tsneaky\rtext")
    stored = read_rows(project)[0]
    assert not stored["notes"].startswith(("\t", "\r"))
    assert "\r" not in stored["notes"] and "\n" not in stored["notes"]


def test_unknown_and_legacy_statuses_are_refused_on_write(project):
    cli("init", project)
    unknown = cli("add", project, "--id", ID_ACME, "--company", "Acme", "--role", "R", "--status", "bogus")
    assert unknown.returncode == 1 and "unknown status" in unknown.stderr
    legacy = cli("add", project, "--id", ID_ACME, "--company", "Acme", "--role", "R", "--status", "drafted")
    assert legacy.returncode == 1 and "legacy spelling" in legacy.stderr
    assert read_rows(project) == []


def test_legacy_statuses_read_as_spec_statuses(project):
    seed(project, [row(ID_ACME, "Acme", "drafted", "2026-09-01"),
                   row(ID_BETA, "Beta", "offer declined", "2026-09-02")])
    rows = json_out(cli("list", project))["rows"]
    by_id = {r["id"]: r for r in rows}
    assert by_id[ID_ACME]["status"] == "ready" and by_id[ID_ACME]["bucket"] == "not_sent"
    assert by_id[ID_BETA]["status"] == "withdrawn" and by_id[ID_BETA]["bucket"] == "closed"


def test_add_refuses_a_duplicate_id(project):
    cli("init", project)
    cli("add", project, "--id", ID_ACME, "--company", "Acme", "--role", "R", "--status", "applied")
    again = cli("add", project, "--id", ID_ACME, "--company", "Acme", "--role", "R", "--status", "applied")
    assert again.returncode == 1 and "already tracked" in again.stderr


def test_bad_id_and_bad_score_are_refused(project):
    cli("init", project)
    assert cli("add", project, "--id", "bad id", "--company", "A", "--role", "B", "--status", "applied").returncode == 1
    bad_score = cli("add", project, "--id", ID_ACME, "--company", "A", "--role", "B", "--status", "applied",
                    "--fit-score", "140")
    assert bad_score.returncode == 1 and "0 to 100" in bad_score.stderr


# --- tracker: update, follow-ups, stale, deadlines ------------------------------------------------------------------

def test_update_leaves_every_other_row_byte_identical(project):
    seed(project, [row(ID_ACME, "Acme", "applied", "2026-10-01"), row(ID_BETA, "Beta", "applied", "2026-10-05")])
    before = (project / "tracker.csv").read_text(encoding="utf-8").splitlines()
    result = cli("update", project, "--id", ID_ACME, "--note", "portal confirmed")
    assert result.returncode == 0, result.stderr
    after = (project / "tracker.csv").read_text(encoding="utf-8").splitlines()
    assert after[0] == before[0]
    assert after[2] == before[2], "the other row must not change"
    assert after[1] != before[1]


def test_update_refuses_a_submitted_row_going_back_to_not_sent(project):
    seed(project, [row(ID_ACME, "Acme", "applied", "2026-10-01")])
    before = (project / "tracker.csv").read_text(encoding="utf-8")
    result = cli("update", project, "--id", ID_ACME, "--status", "ready")
    assert result.returncode == 1 and "cannot go back" in result.stderr
    assert (project / "tracker.csv").read_text(encoding="utf-8") == before


def test_update_needs_a_known_id_and_a_change(project):
    seed(project, [row(ID_ACME, "Acme", "applied", "2026-10-01")])
    assert cli("update", project, "--id", ID_GAMMA, "--note", "x").returncode == 1
    assert cli("update", project, "--id", ID_ACME).returncode == 1


def test_follow_up_cap_is_two(project):
    seed(project, [row(ID_ACME, "Acme", "applied", "2026-10-01")])
    first = json_out(cli("update", project, "--id", ID_ACME, "--follow-ups-inc", "--on", "2026-10-20"))
    assert first["row"]["follow_ups"] == "1" and first["row"]["status"] == "followed_up"
    second = json_out(cli("update", project, "--id", ID_ACME, "--follow-ups-inc", "--on", "2026-10-21"))
    assert second["row"]["follow_ups"] == "2"
    third = cli("update", project, "--id", ID_ACME, "--follow-ups-inc", "--on", "2026-10-22")
    assert third.returncode == 1 and "cap" in third.stderr


def test_followups_list_quiet_rows_and_cap_separately(project):
    seed(project, [
        row(ID_ACME, "Acme", "applied", "2026-10-01"),                                  # due: quiet 19 days
        row(ID_BETA, "Beta", "applied", "2026-10-15"),                                  # quiet 5: not due
        row(ID_GAMMA, "Gamma", "applied", "2026-10-01", follow_ups="2"),                # at the cap
        row("JOB-20260901-delta-pm", "Delta", "ready", "2026-09-01"),                   # never sent: never due
        row("JOB-20261002-echo-pm", "Echo", "applied", "2026-10-01", last_contact="2026-10-30"),  # future contact
    ])
    result = json_out(cli("followups", project))
    due = {item["id"] for item in result["items"]}
    assert due == {ID_ACME, "JOB-20261002-echo-pm"}
    assert result["at_cap"] == [ID_GAMMA]
    assert all("delta" not in item["id"] for item in result["items"])
    assert result["items"][0]["draft_path"].startswith("reports/followups/")


def test_stale_lists_submitted_rows_past_the_threshold(project):
    seed(project, [row(ID_ACME, "Acme", "applied", "2026-10-01"), row(ID_BETA, "Beta", "applied", "2026-12-20"),
                   row("JOB-20260901-delta-pm", "Delta", "ready", "2026-09-01")])
    result = json_out(cli("stale", project, today="2026-12-30"))
    ids = {item["id"] for item in result["items"]}
    assert ids == {ID_ACME}, "only the submitted row quiet for 60 days or more"


def test_deadline_flags_are_data_fields(project):
    seed(project, [
        row(ID_ACME, "Acme", "applied", "2026-10-01", deadline="2026-10-25"),       # soon
        row(ID_BETA, "Beta", "applied", "2026-10-01", deadline="2026-10-10"),       # passed
        row(ID_GAMMA, "Gamma", "applied", "2026-10-01", deadline="25/10/2026"),     # unreadable
    ])
    by_id = {r["id"]: r for r in json_out(cli("list", project))["rows"]}
    assert by_id[ID_ACME]["deadline_flag"] == "soon" and by_id[ID_ACME]["deadline_soon"] is True
    assert by_id[ID_BETA]["deadline_flag"] == "passed" and by_id[ID_BETA]["deadline_passed"] is True
    assert by_id[ID_GAMMA]["deadline_flag"] == "invalid"
    stats = json_out(cli("stats", project))
    assert stats["deadlines"] == {"soon": 1, "passed": 1, "invalid": 1}


def test_stats_reports_the_funnel_and_calibration_gate(project):
    seed(project, [row(ID_ACME, "Acme", "interview", "2026-10-01", fit_score="80"),
                   row(ID_BETA, "Beta", "rejected", "2026-10-01"),
                   row(ID_GAMMA, "Gamma", "ready", "2026-10-01")])
    stats = json_out(cli("stats", project))
    assert stats["total"] == 3 and stats["not_sent"] == 1
    assert stats["funnel"]["interview_or_later"] == 1
    assert stats["calibration"]["resolved"] == 1 and stats["calibration"]["ready"] is False


# --- build_dashboard.py ---------------------------------------------------------------------------------------------

def dashboard_fixture(project):
    seed(project, [
        row(ID_ACME, "<b>Acme & Co</b>", "applied", "2026-10-01", fit_score="72", notes="<script>x</script>"),
        row(ID_BETA, 'Beta "quoted"', "interview", "2026-10-01", deadline="2026-10-25"),
    ])
    (project / "searches").mkdir()
    (project / "searches" / "seen.json").write_text(json.dumps({"schema": 1, "seen": {
        "k1": {"company": "Zed <i>", "title": "<img src=x onerror=alert(1)>", "status": "ranked",
               "score": {"score": 68}},
        "k2": {"company": "Quiet", "title": "Idle", "status": "new"}}}), encoding="utf-8")
    opening = project / "openings" / ID_ACME
    opening.mkdir(parents=True)
    (opening / "status.json").write_text(json.dumps({"id": ID_ACME, "status": "applied", "history": [
        {"date": "2026-10-01T09:00", "status": "applied", "by": "jobs", "note": "</li><script>evil()</script>"}]}),
        encoding="utf-8")


def test_dashboard_is_one_offline_file(project):
    dashboard_fixture(project)
    summary = json_out(run(DASHBOARD, "--project", str(project), "--today", TODAY))
    assert summary["tracked"] == 2
    page = (project / "reports" / "dashboard.html").read_text(encoding="utf-8")
    lowered = page.lower()
    assert "<!doctype html>" in lowered and "<style>" in lowered
    # Attribute names inside escaped text ("&lt;img src=x") are harmless; only live tags and URLs matter.
    live_tag = re.compile(r"<(script|link|img|iframe|object|embed|a|form|input|video|audio|svg|style\s+src)\b")
    assert not live_tag.search(lowered), "offline page must hold no external or active tags"
    for needle in ("http://", "https://", "@import", "url("):
        assert needle not in lowered, f"offline page must not contain {needle!r}"


def test_dashboard_escapes_every_value(project):
    dashboard_fixture(project)
    run(DASHBOARD, "--project", str(project), "--today", TODAY)
    page = (project / "reports" / "dashboard.html").read_text(encoding="utf-8")
    assert "&lt;b&gt;Acme &amp; Co&lt;/b&gt;" in page, "company names are escaped"
    assert "Beta &quot;quoted&quot;" in page, "double quotes are escaped"
    assert "&lt;img src=x onerror=alert(1)&gt;" in page, "the shortlist title is escaped"
    assert "&lt;/li&gt;&lt;script&gt;evil()" in page, "timeline notes are escaped"
    assert "<script>" not in page and "<img" not in page and "<b>Acme" not in page
    assert "<i>Zed" not in page


def test_dashboard_shows_funnel_shortlist_deadlines_and_timeline(project):
    dashboard_fixture(project)
    run(DASHBOARD, "--project", str(project), "--today", TODAY)
    page = (project / "reports" / "dashboard.html").read_text(encoding="utf-8")
    assert "Funnel by status" in page and "Shortlist (ranked openings)" in page
    assert "Deadlines" in page and "Timelines" in page
    assert ID_ACME in page and "Zed" in page
    assert "<td>Quiet</td>" not in page, "only ranked entries are shortlisted"


def test_dashboard_refuses_a_broken_seen_file(project):
    seed(project, [row(ID_ACME, "Acme", "applied", "2026-10-01")])
    (project / "searches").mkdir()
    (project / "searches" / "seen.json").write_text("[not an object", encoding="utf-8")
    result = run(DASHBOARD, "--project", str(project), "--today", TODAY)
    assert result.returncode == 1 and "seen.json" in result.stderr


# --- skill_gaps.py -------------------------------------------------------------------------------------------------

def gaps_fixture(project):
    (project / "achievements.yaml").write_text(
        "skills:\n  - {name: SQL, proficiency: did}\n  - {name: Python}\n", encoding="utf-8")
    for opening, body in (
        (ID_BETA, {"must_have": ["SQL", "Power BI"], "nice_to_have": ["dbt"], "tools": ["Power BI"],
                   "keywords": ["ETL"]}),
        (ID_GAMMA, {"must_have": ["Power BI", "python "], "nice_to_have": [], "tools": [],
                    "keywords": ["etl"]}),
    ):
        folder = project / "openings" / opening
        folder.mkdir(parents=True)
        (folder / "analysis.json").write_text(json.dumps({"id": opening, "requirements": body}), encoding="utf-8")


def test_skill_gaps_counts_each_list_and_sorts_gaps(project):
    gaps_fixture(project)
    report = json_out(run(GAPS, "--project", str(project), "--json"))
    assert report["openings_analysed"] == 2
    names = [g["skill"] for g in report["gaps"]]
    assert names == ["Power BI", "dbt", "ETL"]
    power = report["gaps"][0]
    assert power["must_have"] == 2 and power["tools"] == 1 and power["openings"] == 2
    assert report["gaps"][2]["keywords"] == 2, "ETL and etl are the same skill"


def test_skill_gaps_never_lists_a_covered_or_unnamed_skill(project):
    gaps_fixture(project)
    report = json_out(run(GAPS, "--project", str(project), "--json"))
    names = {g["skill"] for g in report["gaps"]}
    assert "SQL" not in names and "Python" not in names, "covered by achievements.yaml"
    assert "Kubernetes" not in names, "never named by an analysis, so never listed"
    covered = {s["skill"] for s in report["skills"] if s["covered"]}
    assert covered == {"SQL", "python"} or covered == {"SQL", "Python"}


def test_skill_gaps_targeted_mode_and_determinism(project):
    gaps_fixture(project)
    first = json_out(run(GAPS, "--project", str(project), "--opening", ID_GAMMA, "--json"))
    assert first["openings_analysed"] == 1
    # The first spelling seen in the opening order is kept for display; matching is case-insensitive.
    assert [g["skill"].casefold() for g in first["gaps"]] == ["power bi", "etl"]
    again = run(GAPS, "--project", str(project))
    assert again.returncode == 0 and again.stdout == run(GAPS, "--project", str(project)).stdout


def test_skill_gaps_refuses_an_unknown_opening(project):
    gaps_fixture(project)
    result = run(GAPS, "--project", str(project), "--opening", "JOB-20260101-nobody-nothing")
    assert result.returncode == 1 and "analysis.json" in result.stderr


# --- manager skills -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("skill", MANAGER_SKILLS)
def test_manager_skill_has_exactly_three_scenarios(skill):
    data = json.loads((SKILLS / skill / "evals" / "evals.json").read_text(encoding="utf-8"))
    assert len(data["evals"]) == 3


@pytest.mark.parametrize("skill", MANAGER_SKILLS)
def test_manager_skill_has_the_four_sections(skill):
    text = (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
    for heading in ("## When to Use", "## Procedure", "## Pitfalls", "## Verification"):
        assert heading in text, f"{skill} is missing {heading}"


def test_leading_job_search_is_a_manager_and_routes_to_the_others():
    text = (SKILLS / "leading-job-search" / "SKILL.md").read_text(encoding="utf-8")
    assert len(text.splitlines()) <= 150
    for target in ("profiling-candidates", "tracking-outcomes", "planning-upskilling", "triaging-inbox",
                   "build_dashboard.py", "adding-portals", "Mode: PORTAL", "jobs:inbox:<project>:<YYYY-MM-DD>", "Mode: INBOX"):
        assert target in text, f"leading-job-search must route to or name {target}"
    assert "kanban_block" in text and "search: paused" in text


def test_tracking_outcomes_drives_the_inbox_proposal_flow():
    text = (SKILLS / "tracking-outcomes" / "SKILL.md").read_text(encoding="utf-8")
    assert "Mode: INBOX" in text and "reports/inbox-" in text
    assert "kanban_block(kind=\"needs_input\"" in text
    assert "tracker.py update" in text and "status.py append" in text
    assert "--follow-ups-inc" in text


def test_profiling_candidates_writes_nothing_before_the_ok():
    text = (SKILLS / "profiling-candidates" / "SKILL.md").read_text(encoding="utf-8")
    assert "after the user's \"ok\"" in text or "after the user's ok" in text
    assert "verified: true" in text
    for name in ("profile-keys.md", "market-conventions.md", "stage-playbook.md"):
        assert (SKILLS / "profiling-candidates" / "references" / name).is_file()
        assert name in text


def test_market_table_covers_twelve_or_more_markets():
    text = (SKILLS / "profiling-candidates" / "references" / "market-conventions.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| ") and "---" not in line[:6]]
    markets = [r for r in rows if re.match(r"\| [A-Z]{2} \|", r)]
    assert len(markets) >= 12


# --- lint and hygiene -----------------------------------------------------------------------------------------------

def test_squad_passes_skill_lint():
    result = subprocess.run([str(HPY), "skill_lint.py", "squads/jobs"], capture_output=True, text=True,
                            cwd=str(REPO), timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "0 findings" in result.stdout


def test_manager_files_carry_no_foreign_traces():
    paths = list(SCRIPTS.glob("tracker.py")) + list(SCRIPTS.glob("build_dashboard.py")) + \
        list(SCRIPTS.glob("skill_gaps.py")) + [Path(__file__)]
    for skill in MANAGER_SKILLS:
        paths += [p for p in (SKILLS / skill).rglob("*") if p.is_file()]
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        lowered = text.lower()
        if path == Path(__file__):
            # The guard itself names the words only through its fragments; check the fragments are not whole words.
            continue
        for word in FOREIGN:
            assert word not in lowered, f"{path.name} contains a foreign trace: {word!r}"
        assert not SLASH.search(text), f"{path.name} uses a slash command"


# --- tracker and seen_state integrity: producer, concurrency, input checks ------------------------------------------

SEEN = SCRIPTS.parent.parent / "jobs-contract" / "scripts" / "seen_state.py"
ID_OPEN = "JOB-20261001-acme-analyst"


def spawn(argv_list):
    """Start every process at once and wait for all: the concurrency the bots produce."""
    procs = [subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for argv in argv_list]
    return [(p.communicate(timeout=180), p.returncode) for p in procs]


def test_add_if_missing_keeps_the_row_a_repeated_applier_wrote(project):
    # The applier records a submit that may run twice: the second record must report the row, never add a second.
    cli("init", project)
    first = cli("add", project, "--id", ID_ACME, "--company", "Acme", "--role", "Analyst", "--status", "applied")
    assert first.returncode == 0, first.stderr
    again = json_out(cli("add", project, "--id", ID_ACME, "--company", "Acme", "--role", "Analyst",
                         "--status", "applied", "--if-missing"))
    assert again["already_tracked"] == ID_ACME and again["status"] == "applied"
    assert [r["id"] for r in read_rows(project)] == [ID_ACME]


@pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,<b>x</b>", "ftp://example.com/job"])
def test_a_tracker_row_refuses_a_non_web_apply_url(project, url):
    # A javascript: or data: link must never be stored as an apply_url.
    cli("init", project)
    result = cli("add", project, "--id", ID_ACME, "--company", "Acme", "--role", "Analyst", "--status", "applied",
                 "--apply-url", url)
    assert result.returncode == 1 and "must be an http or https link" in result.stderr
    assert read_rows(project) == []
    update = cli("add", project, "--id", ID_ACME, "--company", "Acme", "--role", "Analyst", "--status", "applied")
    assert update.returncode == 0
    assert cli("update", project, "--id", ID_ACME, "--apply-url", url).returncode == 1


def test_a_https_apply_url_is_stored(project):
    cli("init", project)
    cli("add", project, "--id", ID_ACME, "--company", "Acme", "--role", "Analyst", "--status", "applied",
        "--apply-url", "https://jobs.lever.co/acme/2f1c9a7e/apply")
    assert read_rows(project)[0]["apply_url"] == "https://jobs.lever.co/acme/2f1c9a7e/apply"


def test_list_takes_the_json_flag_the_inbox_skill_documents(project):
    # triaging-inbox runs `tracker.py list --project <P> --json`: the flag must be accepted.
    seed(project, [row(ID_ACME, "Acme", "applied", "2026-10-01")])
    skill = (SKILLS / "triaging-inbox" / "SKILL.md").read_text(encoding="utf-8")
    assert "list --project <P> --json" in skill
    result = cli("list", project, "--json")
    assert result.returncode == 0, result.stderr
    assert [r["id"] for r in json.loads(result.stdout)["rows"]] == [ID_ACME]


def test_thirty_concurrent_tracker_adds_all_persist(project):
    # Each add is one locked read-modify-write: concurrent adds keep every row.
    cli("init", project)
    argv_list = [[sys.executable, str(TRACKER), "add", "--project", str(project), "--today", TODAY,
                  "--id", f"JOB-20261001-co{n:02d}-analyst", "--company", f"Co{n:02d}", "--role", "Analyst",
                  "--status", "applied"] for n in range(30)]
    outcomes = spawn(argv_list)
    assert [rc for _, rc in outcomes] == [0] * 30, [err for (_, err), _ in outcomes if err]
    assert len({r["id"] for r in read_rows(project)}) == 30


def seen_state_run(project, *args):
    return subprocess.run([sys.executable, str(SEEN), *args, "--project", str(project), "--today", TODAY],
                          capture_output=True, text=True, cwd=str(REPO), timeout=120)


def test_thirty_concurrent_seen_adds_all_persist(project):
    # Each seen_state write is one locked read-modify-write: concurrent adds keep every key.
    batches = []
    for n in range(30):
        path = project / f"batch{n:02d}.json"
        path.write_text(json.dumps([{"key": f"key{n:02d}", "company": f"Co{n:02d}", "title": "Analyst"}]),
                        encoding="utf-8")
        batches.append(path)
    outcomes = spawn([[sys.executable, str(SEEN), "add", "--project", str(project), "--file", str(path),
                       "--today", TODAY] for path in batches])
    assert [rc for _, rc in outcomes] == [0] * 30, [err for (_, err), _ in outcomes if err]
    state = json.loads((project / "searches" / "seen.json").read_text(encoding="utf-8"))
    assert len(state["seen"]) == 30


def test_seen_state_refuses_an_opening_id_that_leaves_the_openings_folder(project):
    # An opening_id that leaves openings/ is refused at the entry point, never stored.
    bad = project / "bad.json"
    bad.write_text(json.dumps([{"key": "key-x", "company": "Acme", "title": "Analyst",
                                "opening_id": "../../outside_opening"}]), encoding="utf-8")
    result = seen_state_run(project, "add", "--file", str(bad))
    assert result.returncode == 1
    assert "opening_id must be JOB-YYYYMMDD-<slug>" in result.stdout
    assert not (project / "searches" / "seen.json").exists() or "key-x" not in (
        project / "searches" / "seen.json").read_text(encoding="utf-8")
    good = project / "good.json"
    good.write_text(json.dumps([{"key": "key-y", "company": "Acme", "title": "Analyst", "opening_id": ID_OPEN}]),
                    encoding="utf-8")
    assert seen_state_run(project, "add", "--file", str(good)).returncode == 0


def test_audit_flags_a_stored_opening_id_that_leaves_openings(project):
    state = project / "searches" / "seen.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"schema": 1, "seen": {"key-z": {
        "company": "Acme", "title": "Analyst", "status": "new", "opening_id": "../x"}}}), encoding="utf-8")
    result = seen_state_run(project, "audit", "--strict")
    assert result.returncode == 1 and "opening_id is not JOB-YYYYMMDD" in result.stdout
