"""One employer posting is one opening, whatever portal title or city it is listed under.

The case: Blacksmith Agency mass-posts one Ashby requisition under about six LinkedIn city titles. The squad applied
to "LLM Engineer (Remote, Cali)" on 2026-10-27; on 2026-11-02 "AI Automation Engineer (Remote, Pereira)" (same Ashby
apply_url, another LinkedIn id) got a new key, passed every gate and went through a writer round and two reviews. Only
the manager reading both apply_url values at the digest stopped a second application. These tests drive the scripts
the bots run, on that project shape.
"""
import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "squads" / "jobs" / "skills"
SCRIPTS = SKILLS / "jobs-contract" / "scripts"
SEEN = SCRIPTS / "seen_state.py"
JOB_KEY = SCRIPTS / "job_key.py"
APPLY_LINK = SCRIPTS / "apply_link.py"
SCORE = SKILLS / "analyzing-jobs" / "scripts" / "score_analysis.py"
CHECK = SKILLS / "submitting-applications" / "scripts" / "check_submission.py"

ASHBY = "https://jobs.ashbyhq.com/Blacksmith%20Agency/5dfccfc8-a527-44b9-b3ec-eaee25fc3f0f"
OTHER_ASHBY = "https://jobs.ashbyhq.com/Blacksmith%20Agency/0a1b2c3d-1111-4222-8333-944455566677"
FIRST = "JOB-20261027-blacksmith-agency-llm-engineer"
SECOND = "JOB-20261102-blacksmith-agency-ai-automation"
CALI = ("blacksmith-agency_llm-engineer-remote-cali", "LLM Engineer (Remote, Cali)",
        "https://co.linkedin.com/jobs/view/llm-engineer-remote-cali-at-blacksmith-agency-4484221651")
PEREIRA = ("blacksmith-agency_ai-automation-engineer-remote-pereira", "AI Automation Engineer (Remote, Pereira)",
           "https://co.linkedin.com/jobs/view/ai-automation-engineer-remote-pereira-at-blacksmith-agency-4485919429")


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True, timeout=120)


def ok(script, *args):
    proc = run(script, *args)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def opening(project, oid, title, url, apply_url, status="found"):
    folder = project / "openings" / oid
    folder.mkdir(parents=True)
    apply_line = f"apply_url: {apply_url}" if apply_url else "apply_url: null"
    (folder / "opening.md").write_text(
        f"---\nid: {oid}\ncompany: \"Blacksmith Agency\"\nrole: \"{title}\"\nurl: {url}\n{apply_line}\n"
        f"source: linkedin\n---\n\nPosting.\n", encoding="utf-8")
    (folder / "status.json").write_text(json.dumps({"id": oid, "status": status, "history": [
        {"date": "2026-10-27T17:06", "status": status, "by": "jobs-scout"}]}), encoding="utf-8")
    return folder


def entry(listing, opening_id=None, employer_url=None, company="Blacksmith Agency", first_seen=None):
    key, title, url = listing
    row = {"key": key, "company": company, "title": title, "url": url, "portal": "linkedin",
           "posted_at": "2026-10-27", "deadline": None}
    if opening_id:
        row["opening_id"] = opening_id
    if employer_url:
        row["employer_url"] = employer_url
    return row


def add(project, rows, today):
    batch = project / f"batch-{today}.json"
    batch.write_text(json.dumps(rows), encoding="utf-8")
    return ok(SEEN, "add", "--project", project, "--file", batch, "--today", today)


def candidates(project):
    return ok(SEEN, "candidates", "--project", project, "--saved", "--limit", "0")


def seen(project):
    return json.loads((project / "searches" / "seen.json").read_text(encoding="utf-8"))["seen"]


def history(folder):
    return json.loads((folder / "status.json").read_text(encoding="utf-8"))


@pytest.fixture
def project(tmp_path):
    (tmp_path / "profile.md").write_text("---\nsearch: active\n---\n", encoding="utf-8")
    (tmp_path / "searches").mkdir()
    return tmp_path


# --- must collapse to one ------------------------------------------------------------------------------------------

def test_the_two_real_blacksmith_openings_are_one_candidate(project):
    # The state the project held on 2026-11-02: two folders, two seen entries, one Ashby apply_url.
    opening(project, FIRST, CALI[1], CALI[2], ASHBY, status="applied")
    opening(project, SECOND, PEREIRA[1], PEREIRA[2], ASHBY)
    add(project, [entry(CALI, FIRST)], "2026-10-27")
    add(project, [entry(PEREIRA, SECOND)], "2026-11-02")
    out = candidates(project)
    assert [row["key"] for row in out["selected"]] == [CALI[0]], out
    assert out["excluded_as_relisting"] == [{"key": PEREIRA[0], "alias_of": CALI[0]}]
    audit = ok(SEEN, "audit", "--project", project)
    assert audit["same_employer_posting"][0]["keys"] == [CALI[0], PEREIRA[0]]


def test_a_relisting_with_the_resolved_ats_url_becomes_an_alias_and_never_resurrects(project):
    opening(project, FIRST, CALI[1], CALI[2], ASHBY, status="applied")
    add(project, [entry(CALI, FIRST, employer_url=ASHBY)], "2026-10-27")
    out = add(project, [entry(PEREIRA, employer_url=ASHBY + "?utm_source=linkedin")], "2026-11-02")
    assert out["added"] == [] and out["relisted"][0]["alias_of"] == CALI[0], out
    state = seen(project)
    assert list(state) == [CALI[0]], "one entry per employer posting"
    assert [a["title"] for a in state[CALI[0]]["aliases"]] == [PEREIRA[1]]
    assert state[CALI[0]]["aliases"][0]["url"] == PEREIRA[2]
    # Rule 5: the duplicate is recorded on the existing opening, its status untouched.
    doc = history(project / "openings" / FIRST)
    assert doc["status"] == "applied"
    assert PEREIRA[1] in doc["history"][-1]["note"] and PEREIRA[2] in doc["history"][-1]["note"]
    # A third run of the same listing (portal key only, no employer URL yet) stays an alias.
    again = add(project, [entry(PEREIRA)], "2026-11-03")
    assert again["added"] == [] and list(seen(project)) == [CALI[0]]


def test_apply_link_discards_the_relisting_and_names_it_on_the_first_opening(project):
    # The scout resolves the employer posting after saving the folder: that is where the second listing is caught.
    opening(project, FIRST, CALI[1], CALI[2], ASHBY, status="applied")
    second = opening(project, SECOND, PEREIRA[1], PEREIRA[2], None)
    add(project, [entry(CALI, FIRST)], "2026-10-27")
    add(project, [entry(PEREIRA, SECOND)], "2026-11-02")
    assert len(candidates(project)["selected"]) == 2, "control: without an apply_url the second looks new"
    out = ok(APPLY_LINK, second, ASHBY, "--by", "jobs-scout", "--json")
    assert out["duplicate_of"] == FIRST and out["duplicate_status"] == "applied", out
    assert history(second)["status"] == "discarded"
    assert FIRST in history(second)["history"][-1]["note"]
    first_doc = history(project / "openings" / FIRST)
    assert first_doc["status"] == "applied" and SECOND in first_doc["history"][-1]["note"]
    state = seen(project)
    assert list(state) == [CALI[0]] and state[CALI[0]]["aliases"][0]["opening_id"] == SECOND
    assert [row["key"] for row in candidates(project)["selected"]] == [CALI[0]]


def test_the_relisting_never_reaches_analysis_or_the_submit_gate(project):
    opening(project, FIRST, CALI[1], CALI[2], ASHBY, status="applied")
    second = opening(project, SECOND, PEREIRA[1], PEREIRA[2], ASHBY)
    (second / "analysis.json").write_text(json.dumps({"requirements": {}, "company": {}, "fit": {}}), "utf-8")
    proc = run(SCORE, "check", second, "--project", project)
    assert "same employer posting as " + FIRST in proc.stdout + proc.stderr, proc.stdout + proc.stderr
    app = second / "application"
    app.mkdir()
    gate = run(CHECK, app / "submission.json", "--gate", "--method", "no_login_form")
    assert gate.returncode == 1 and f"same employer posting as {FIRST}" in gate.stderr, gate.stderr


def test_the_tracker_row_alone_excludes_a_relisting(project):
    # The 30-day company-and-role rule: the applied row is matched on its apply_url, not on the portal title.
    with (project / "tracker.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "id", "company", "role", "status", "apply_url"])
        writer.writerow(["2026-10-27", FIRST, "Blacksmith Agency", CALI[1], "applied", ASHBY])
    opening(project, SECOND, PEREIRA[1], PEREIRA[2], ASHBY)
    add(project, [entry(PEREIRA, SECOND)], "2026-11-02")
    out = candidates(project)
    assert out["selected"] == [] and out["excluded_by_tracker"] == 1, out


def test_an_alias_title_matches_the_tracker_role(project):
    with (project / "tracker.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "id", "company", "role", "status", "apply_url"])
        writer.writerow(["2026-11-02", SECOND, "Blacksmith Agency", PEREIRA[1], "applied", ""])
    opening(project, FIRST, CALI[1], CALI[2], None)
    add(project, [entry(CALI, FIRST, employer_url=ASHBY)], "2026-10-27")
    add(project, [entry(PEREIRA, employer_url=ASHBY)], "2026-11-02")
    assert candidates(project)["excluded_by_tracker"] == 1


def test_two_portals_with_different_tracking_parameters_are_one_entry(project):
    a = ("blacksmith-agency_ai-developer", "AI Developer", "https://www.linkedin.com/jobs/view/4485216439")
    b = ("blacksmith-agency_ai-engineer", "AI Engineer", "https://www.getonbrd.com/jobs/ai-engineer-blacksmith")
    add(project, [entry(a, employer_url=ASHBY + "/application?utm_source=linkedin&utm_medium=jobs")], "2026-10-29")
    out = add(project, [entry(b, employer_url=ASHBY.replace("%20", " ") + "?src=getonbrd#apply")], "2026-10-30")
    assert out["relisted"][0]["alias_of"] == a[0] and list(seen(project)) == [a[0]], out


# --- must stay separate -------------------------------------------------------------------------------------------

def test_same_company_with_another_ashby_posting_is_a_new_opening(project):
    opening(project, FIRST, CALI[1], CALI[2], ASHBY, status="applied")
    other = opening(project, SECOND, PEREIRA[1], PEREIRA[2], None)
    add(project, [entry(CALI, FIRST)], "2026-10-27")
    add(project, [entry(PEREIRA, SECOND, employer_url=OTHER_ASHBY)], "2026-11-02")
    assert len(candidates(project)["selected"]) == 2
    out = ok(APPLY_LINK, other, OTHER_ASHBY, "--by", "jobs-scout", "--json")
    assert "duplicate_of" not in out and history(other)["status"] == "found"


def test_two_companies_on_one_job_board_host_stay_apart(project):
    acme = ("acme_data-engineer", "Data Engineer", "https://www.linkedin.com/jobs/view/4400000001")
    beta = ("beta_data-engineer", "Data Engineer", "https://www.linkedin.com/jobs/view/4400000002")
    out = add(project, [entry(acme, company="Acme", employer_url="https://boards.greenhouse.io/acme/jobs/123"),
                        entry(beta, company="Beta", employer_url="https://boards.greenhouse.io/beta/jobs/123")],
              "2026-11-02")
    assert out["added"] == [acme[0], beta[0]] and out["relisted"] == []
    # A job board link is not an employer posting: two rows on one board never merge through it.
    board = ok(JOB_KEY, "--employer-url", "https://www.getonbrd.com/jobs/data-engineer-acme")
    assert board["employer_url"] is None


def test_a_null_apply_url_falls_back_to_the_portal_key(project):
    opening(project, FIRST, CALI[1], CALI[2], None)
    out = add(project, [entry(CALI, FIRST)], "2026-10-27")
    assert out["added"] == [CALI[0]] and "employer_url" not in seen(project)[CALI[0]]
    assert [row["key"] for row in candidates(project)["selected"]] == [CALI[0]]


def test_a_portal_link_given_as_employer_url_is_refused(project):
    proc = subprocess.run([sys.executable, str(SEEN), "add", "--project", str(project), "--file", "-"],
                          input=json.dumps([entry(CALI, employer_url=CALI[2])]), capture_output=True, text=True)
    assert proc.returncode == 1 and "employer_url is not an employer posting" in proc.stdout, proc.stdout
    assert not (project / "searches" / "seen.json").exists()


def test_an_unknown_company_hash_keeps_its_url_hash_key():
    key = subprocess.run([sys.executable, str(JOB_KEY), "--company", "5dfccfc8-a527-44b9-b3ec-eaee25fc3f0f",
                          "--title", "AI Engineer", "--url", ASHBY], capture_output=True, text=True, check=True)
    assert key.stdout.startswith("unknown-company-") and key.stdout.strip().endswith("_ai-engineer")
