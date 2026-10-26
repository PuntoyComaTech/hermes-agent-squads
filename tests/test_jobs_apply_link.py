"""apply_link.py: the employer's posting found after intake becomes apply_url, so the applier stops on no portal link.

The case: Truelogic came in as a LinkedIn listing; the scout found no Ashby posting, the reviewer later located the
exact requisition on Truelogic's Ashby board, and opening.md still sent the applier to LinkedIn. The run blocked.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "squads" / "jobs" / "skills" / "jobs-contract" / "scripts"
TOOL = SCRIPTS / "apply_link.py"
LINKEDIN = "https://www.linkedin.com/jobs/view/4483184903"
ASHBY = "https://jobs.ashbyhq.com/truelogic/67d297a2-a583-4d16-b6a4-7a48c2fa6174"
ID = "JOB-20261023-truelogic-senior-front-end-engineer"

OPENING = f"""---
id: {ID}
company: "Truelogic"
role: "Senior Front-End Engineer (Next.js/React) - Real Estate - Colombia"
url: https://co.linkedin.com/jobs/view/senior-front-end-engineer-at-truelogic-4483184903
apply_url: {LINKEDIN}
source: linkedin
gates: {{eligibility: PASS, language: PASS, location: PASS, role: PASS, seniority: PASS, contract: PASS, avoid: PASS}}
link_verdict: official_ats
---

Posting text: apply_url: https://evil.example/not-front-matter
"""


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True)


@pytest.fixture
def opening(tmp_path):
    folder = tmp_path / "openings" / ID
    folder.mkdir(parents=True)
    (folder / "opening.md").write_text(OPENING, encoding="utf-8")
    (folder / "status.json").write_text(json.dumps({"id": ID, "status": "ready", "history": [
        {"date": "2026-10-24T02:00", "status": "ready", "by": "jobs-reviewer", "note": "review-9 APPROVED"}]}))
    return folder


def front(folder):
    sys.path.insert(0, str(SCRIPTS))
    import jobs_common
    return jobs_common.read_front_matter(folder / "opening.md")


def test_the_reviewers_ashby_posting_replaces_the_linkedin_apply_url(opening):
    done = run(opening, ASHBY, "--by", "jobs-reviewer", "--source", "review-5")
    assert done.returncode == 0, done.stderr
    meta = front(opening)
    assert meta["apply_url"] == ASHBY
    assert meta["url"].startswith("https://co.linkedin.com/")  # the intake link stays
    assert meta["company"] == "Truelogic" and meta["gates"]["seniority"] == "PASS"
    body = (opening / "opening.md").read_text().split("\n---\n", 1)[1]
    assert "https://evil.example/not-front-matter" in body  # the posting text is untouched
    status = json.loads((opening / "status.json").read_text())
    assert status["status"] == "ready" and len(status["history"]) == 2
    assert status["history"][0]["note"] == "review-9 APPROVED"
    assert ASHBY in status["history"][-1]["note"] and status["history"][-1]["by"] == "jobs-reviewer"


def test_the_applier_gate_reads_the_new_link_as_an_employer_ats(opening):
    """Before: link_check calls the LinkedIn apply_url a portal, so the no_login_form gate refuses it."""
    sys.path.insert(0, str(SCRIPTS))
    import link_check as lc
    data = lc.load_data(lc.DATA_FILE)
    assert lc.classify(front(opening)["apply_url"], data)["kind"] == "portal"
    assert run(opening, ASHBY, "--by", "jobs-reviewer").returncode == 0
    assert lc.classify(front(opening)["apply_url"], data)["kind"] == "ats"


@pytest.mark.parametrize("bad", [
    "https://www.linkedin.com/jobs/view/4483184903",
    "https://echojobs.io/job/canals-ai-senior-software-engineer-colombia-za5hv",
    "https://boards-greenhouse.io/acme/jobs/123",
])
def test_a_portal_board_or_lookalike_is_refused_and_nothing_changes(opening, bad):
    before = (opening / "opening.md").read_bytes(), (opening / "status.json").read_bytes()
    done = run(opening, bad, "--by", "jobs-reviewer")
    assert done.returncode == 1 and "refused" in done.stderr
    assert ((opening / "opening.md").read_bytes(), (opening / "status.json").read_bytes()) == before


def test_twice_is_a_no_op(opening):
    assert run(opening, ASHBY, "--by", "jobs-scout").returncode == 0
    snapshot = (opening / "opening.md").read_bytes(), (opening / "status.json").read_bytes()
    again = run(opening, ASHBY, "--by", "jobs-scout")
    assert again.returncode == 0 and "already set" in again.stdout
    assert ((opening / "opening.md").read_bytes(), (opening / "status.json").read_bytes()) == snapshot


def test_an_opening_without_apply_url_gets_one_after_url(opening):
    text = (opening / "opening.md").read_text().replace(f"apply_url: {LINKEDIN}\n", "")
    (opening / "opening.md").write_text(text)
    assert run(opening, ASHBY, "--by", "jobs-scout").returncode == 0
    head = (opening / "opening.md").read_text().split("\n---\n", 1)[0].splitlines()
    assert head[head.index(next(l for l in head if l.startswith("url:"))) + 1] == f"apply_url: {ASHBY}"


def test_missing_opening_is_a_usage_error(tmp_path):
    assert run(tmp_path / "nope", ASHBY, "--by", "jobs-scout").returncode == 2


def test_help_runs():
    assert run("--help").returncode == 0
