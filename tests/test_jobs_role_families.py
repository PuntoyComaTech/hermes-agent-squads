"""Roles are recognised by the work, not by the literal word.

The real run that prompted these tests dropped "Forward Deployed Engineer" from a candidate's headline because no
achievement contained those words, although the achievements describe exactly that work: an end-to-end platform for
a client, MCP servers and agents inside the client's product, full-stack delivery. It also never offered the title,
though the market file held a "forward deployed engineer" posting, and the portal prefilter dropped FDE postings
because the title shares no word with "full stack developer". Each test replays one of those with fictitious data.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = REPO / "squads" / "jobs" / "skills"
sys.dont_write_bytecode = True  # importing skill scripts must not leave __pycache__ in the repo (repo hygiene test)
sys.path.insert(0, str(SKILLS / "jobs-contract" / "scripts"))
sys.path.insert(0, str(SKILLS / "searching-portals" / "scripts"))
import jobs_common as jc  # noqa: E402
import portals  # noqa: E402

COPY = SKILLS / "optimizing-profiles" / "scripts" / "check_profile_copy.py"
KEYWORDS = SKILLS / "browsing-linkedin" / "scripts" / "market_keywords.py"

# Ana's own words: a full-stack engineer who ships AI into a client's product end to end. Nothing says "forward".
ACHIEVEMENTS = (
    "experiences:\n  - {id: EXP-001, title: \"Senior Software Engineer\", company: \"Northwind\", from: 2024-01, to: current}\n"
    "achievements:\n"
    "  - id: ACH-001\n    experience: EXP-001\n    en: \"Built end-to-end the platform that centralises a client's quote workflow, "
    "integrated in production with their systems.\"\n    tags: [full stack, integration]\n    verified: true\n"
    "  - id: ACH-002\n    experience: EXP-001\n    en: \"Built MCP servers and LLM agents with RAG and LangGraph inside the "
    "customer's product.\"\n    tags: [ai, agents]\n    verified: true\n"
    "  - id: ACH-003\n    experience: EXP-001\n    en: \"Shipped React and NestJS features over a GraphQL API.\"\n    verified: true\n"
    "skills:\n  - {name: React, achievements: [ACH-003]}\n  - {name: NestJS, achievements: [ACH-003]}\n"
    "  - {name: LangChain, achievements: [ACH-002]}\n")


def project(tmp_path, extra="") -> Path:
    folder = tmp_path / "ana"
    folder.mkdir(exist_ok=True)
    (folder / "profile.md").write_text('---\ntarget_roles: ["Full stack developer", "AI engineer"]\n'
                                       'key_skills: [React, NestJS, LangChain]\n' + extra + "---\n")
    (folder / "achievements.yaml").write_text(ACHIEVEMENTS)
    return folder


def evidence(folder: Path) -> tuple[dict, str]:
    meta = jc.read_front_matter(folder / "profile.md")
    return meta, (folder / "profile.md").read_text() + json.dumps(jc.read_data(folder / "achievements.yaml"))


def test_the_work_is_recognised_as_forward_deployed_although_no_file_says_the_word(tmp_path):
    meta, ev = evidence(project(tmp_path))
    roles = {r["id"]: r for r in jc.recognised_roles(meta, ev)}
    assert roles["forward-deployed"]["by"] == "evidence" and roles["forward-deployed"]["emerging"] is True
    assert roles["full-stack"]["by"] == "named"
    # a pure data analyst's evidence is not stretched into an FDE
    analyst = {"target_roles": ["Data analyst"]}
    assert "forward-deployed" not in {r["id"] for r in jc.recognised_roles(analyst, "SQL reports in Excel and Power BI")}


def test_titles_companies_invent_map_to_the_same_work():
    for title in ("Senior Forward Deployed Engineer, Applied AI", "Staff FDE", "Forward Deployed Software Engineer - SF"):
        assert jc.family_of(title)["id"] == "forward-deployed", title
    assert jc.family_of("Desarrollador Full Stack Sr")["id"] == "full-stack"
    assert jc.family_of("Contador público") is None


def copy_with(headline, skills=("React", "NestJS", "LangChain")):
    return {"platform": "linkedin", "language": "en", "skills": list(skills),
            "blocks": [{"section": "headline", "text": headline, "achievements": ["ACH-001", "ACH-002"]},
                       {"section": "about", "text": "Forward deployed engineer with a full-stack background: I ship "
                        "AI into a client's product end to end.", "achievements": ["ACH-001", "ACH-002"]}]}


def check(tmp_path, copy, folder, market=None):
    (tmp_path / "copy.json").write_text(json.dumps(copy))
    args = [sys.executable, "-B", str(COPY), str(tmp_path / "copy.json"), "--project", str(folder), "--json"]
    if market:
        (tmp_path / "market.json").write_text(json.dumps(market))
        args += ["--market", str(tmp_path / "market.json")]
    p = subprocess.run(args, capture_output=True, text=True, timeout=60)
    return p.returncode, json.loads(p.stdout)


def test_an_fde_headline_and_skill_pass_for_the_work_that_fits_and_fail_for_work_that_does_not(tmp_path):
    folder = project(tmp_path)
    market = {"terms": [{"term": "forward deployed engineer", "in_profile": False},
                        {"term": "forward deployed", "in_profile": False}]}
    copy = copy_with("Forward Deployed Engineer · AI Engineer | Full Stack | MCP · RAG · LangGraph",
                     skills=("React", "NestJS", "LangChain", "Forward Deployed Engineering", "Full-Stack Development"))
    code, report = check(tmp_path, copy, folder, market)
    assert code == 0, report
    assert not [w for w in report["warnings"] if "first 70 characters" in w]
    # the same copy for a candidate whose work is SQL reporting: the FDE title and skill are a claim without evidence
    (folder / "achievements.yaml").write_text(
        "achievements:\n  - {id: ACH-001, en: \"Built SQL reports in Excel.\", verified: true}\n"
        "  - {id: ACH-002, en: \"Cleaned data in Excel.\", verified: true}\n"
        "skills:\n  - {name: React, achievements: [ACH-001]}\n  - {name: NestJS, achievements: [ACH-001]}\n"
        "  - {name: LangChain, achievements: [ACH-001]}\n")
    (folder / "profile.md").write_text('---\ntarget_roles: ["Data analyst"]\nkey_skills: [React, NestJS, LangChain]\n---\n')
    code, report = check(tmp_path, copy, folder, market)
    found = {(d["defect"], d["where"]) for d in report["defects"]}
    assert code == 1 and ("unsupported_skill", "Forward Deployed Engineering") in found
    assert any(d == "claims_a_gap" for d, _ in found)


def test_a_title_the_user_chose_is_theirs_even_before_the_evidence_reaches_the_threshold(tmp_path):
    folder = project(tmp_path, 'positioning_titles: ["Forward Deployed Engineer"]\n')
    (folder / "achievements.yaml").write_text("achievements:\n  - {id: ACH-001, en: \"Shipped React features.\", verified: true}\n"
                                              "  - {id: ACH-002, en: \"Shipped NestJS services.\", verified: true}\n"
                                              "skills:\n  - {name: React, achievements: [ACH-001]}\n"
                                              "  - {name: NestJS, achievements: [ACH-002]}\n  - {name: LangChain, achievements: [ACH-002]}\n")
    meta, ev = evidence(folder)
    assert {r["id"]: r["by"] for r in jc.recognised_roles(meta, ev)}["forward-deployed"] == "named"
    code, report = check(tmp_path, copy_with("Forward Deployed Engineer | React · NestJS"), folder)
    assert code == 0, report


def test_the_market_report_offers_the_emerging_role_the_work_fits(tmp_path):
    folder = project(tmp_path)
    texts = ["Forward Deployed Engineer. Embed with customers, build MCP servers and agents in Python and TypeScript.",
             "Senior FDE: own deployments end to end, full-stack, LLM agents in production.",
             "Full Stack Developer, React and Node.js."]
    path = tmp_path / "details.json"
    path.write_text(json.dumps({"results": [{"title": t.split(".")[0].split(":")[0], "url": f"https://x.example/{i}",
                                             "description": t} for i, t in enumerate(texts)]}))
    p = subprocess.run([sys.executable, "-B", str(KEYWORDS), "--input", str(path), "--project", str(folder),
                        "--min-docs", "2"], capture_output=True, text=True, timeout=60)
    data = json.loads(p.stdout)
    fams = {f["id"]: f for f in data["role_families"]}
    assert fams["forward-deployed"]["postings"] == 2 and fams["forward-deployed"]["recognised"] is True
    assert data["offer_positioning"] == ["Forward Deployed Engineer"]
    # once the user said yes (positioning_titles), it is no longer offered
    project(tmp_path, 'positioning_titles: ["Forward Deployed Engineer"]\n')
    p = subprocess.run([sys.executable, "-B", str(KEYWORDS), "--input", str(path), "--project", str(folder),
                        "--min-docs", "2"], capture_output=True, text=True, timeout=60)
    assert json.loads(p.stdout)["offer_positioning"] == []


def test_the_portal_prefilter_keeps_fde_postings_once_the_user_positions_there():
    rows = [{"portal": "x", "id": "1", "title": "Forward Deployed Engineer", "company": "Acme", "work_mode": "remote",
             "posted": "2026-10-24"},
            {"portal": "x", "id": "2", "title": "Staff FDE, Applied AI", "company": "Acme", "work_mode": "remote",
             "posted": "2026-10-24"},
            {"portal": "x", "id": "3", "title": "Accountant", "company": "Acme", "work_mode": "remote",
             "posted": "2026-10-24"}]
    base = {"target_roles": ["Full stack developer"], "search_keywords": {"en": ["full stack developer"]}}
    today = dt.date(2026, 10, 24)
    before = portals.prefilter_rows(base, rows, today, 10, 10)
    assert "2" not in [r["id"] for r in before["candidates"]]  # "Staff FDE" shares no word with full stack
    after = portals.prefilter_rows(dict(base, positioning_titles=["Forward Deployed Engineer"]), rows, today, 10, 10)
    assert sorted(r["id"] for r in after["candidates"]) == ["1", "2"]
