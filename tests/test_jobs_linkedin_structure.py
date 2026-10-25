"""The bot may edit the whole form: titles, dates, new positions, deletions.

The real run that prompted these tests listed five profile fixes (an Sample Co title and dates, a Contoso Retail title
and dates, a duplicate trainee entry to delete, a missing freelance position to add) as manual edits the user had to
make by hand, because the skill forbade the bot to touch anything but text. The user answered: it is just a form,
edit all of it. `approved.json` `structure` rows carry those edits and `verify` proves them landed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "squads" / "jobs" / "skills" / "optimizing-profiles" / "scripts"
COPY, DIFF = SCRIPTS / "check_profile_copy.py", SCRIPTS / "profile_diff.py"


def run(script, *args):
    return subprocess.run([sys.executable, "-B", str(script), *map(str, args)], capture_output=True, text=True,
                          timeout=60)


def write(path: Path, data) -> Path:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def role(company, title, dates, skills=()):
    return {"company": company, "title": title, "dates": dates, "description": "", "skills": list(skills)}


# The profile as the writer captured it before the edits: two Sample Co entries under the wrong titles and
# dates, two Contoso Retail entries (the trainee one is a duplicate of one real job), no freelance position.
BEFORE = {"platform": "linkedin", "language": "es", "profile_languages": ["es"], "headline": "x", "about": "x",
          "skills": ["SQL"], "top_skills": [], "experience": [
              role("Sample Labs", "Fullstack Software Developer", "May 2024 - Feb 2025 · 10 mos"),
              role("Sample Labs", "Software Developer", "Oct 2023 - Apr 2024 · 7 mos"),
              role("Contoso Retail", "Frontend Junior Analyst", "Oct 2022 - Oct 2023 · 1 yr 1 mo"),
              role("Contoso Retail", "Frontend Developer Trainee", "Apr 2022 - Oct 2022 · 7 mos")],
          "education": [{"institution": "Example Institute", "dates": "Feb 2021 – Dec 2021", "description": ""},
                        {"institution": "Sample University", "dates": "Jun 2024 – Dec 2026",
                         "description": ""}]}

# The same profile after the bot filled the forms: titles and dates as achievements.yaml has them, the trainee entry
# gone, the freelance position created, the studies the user keeps off the profile removed.
AFTER = {"platform": "linkedin", "language": "es", "profile_languages": ["es"], "headline": "x", "about": "x",
         "skills": ["SQL"], "top_skills": [], "experience": [
             role("Sample Labs", "Fullstack Software Developer", "Oct 2023 - Oct 2024 · 1 yr 1 mo"),
             role("Sample Labs", "Senior Software Developer (Full Stack)", "Oct 2024 - Feb 2025 · 5 mos"),
             role("Contoso Retail", "Frontend Developer", "Apr 2022 - Oct 2023 · 1 yr 7 mos"),
             role("Independent", "Freelance Developer", "Jan 2024 - Dec 2024 · 1 yr")],
         "education": [{"institution": "Example Institute", "dates": "Feb 2021 – Dec 2021", "description": ""}]}

STRUCTURE = [
    {"kind": "experience_title", "company": "Sample Labs", "title": "Senior Software Developer (Full Stack)",
     "was": "Software Developer"},
    {"kind": "experience_dates", "company": "Sample Labs", "title": "Fullstack Software Developer",
     "from": "Oct 2023", "to": "Oct 2024"},
    {"kind": "experience_dates", "company": "Sample Labs", "title": "Senior Software Developer (Full Stack)",
     "from": "Oct 2024", "to": "Feb 2025"},
    {"kind": "experience_title", "company": "Contoso Retail", "title": "Frontend Developer", "was": "Frontend Junior Analyst"},
    {"kind": "experience_dates", "company": "Contoso Retail", "title": "Frontend Developer", "from": "Apr 2022", "to": "Oct 2023"},
    {"kind": "experience_delete", "company": "Contoso Retail", "title": "Frontend Developer Trainee"},
    {"kind": "experience_create", "company": "Independent", "title": "Freelance Developer", "from": "Jan 2024",
     "to": "Dec 2024"},
    {"kind": "education_delete", "institution": "Sample University"},
]


def verify(tmp_path, structure, current):
    approved = write(tmp_path / "approved.json", {"fields": [], "structure": structure})
    p = run(DIFF, "verify", approved, write(tmp_path / "current.json", current), "--json")
    return p.returncode, json.loads(p.stdout)


def test_verify_proves_every_form_edit_landed(tmp_path):
    code, out = verify(tmp_path, STRUCTURE, AFTER)
    assert code == 0, out["failures"]
    assert out["counts"] == {"approved": len(STRUCTURE), "verified": len(STRUCTURE)}
    code, out = verify(tmp_path, STRUCTURE, BEFORE)
    assert code == 1
    failed = sorted(f["field"] for f in out["failures"])
    assert failed == sorted(f"structure:{r['kind']}:{r['title'] if 'title' in r else r['institution']}"
                            + (f" at {r['company']}" if r.get("company") else "") for r in STRUCTURE), failed


def test_a_form_edit_that_half_landed_is_named_precisely(tmp_path):
    half = json.loads(json.dumps(AFTER))           # renamed and re-dated, but the freelance position never appeared
    half["experience"] = [r for r in half["experience"] if r["company"] != "Independent"]
    code, out = verify(tmp_path, STRUCTURE, half)
    assert code == 1 and [f["field"] for f in out["failures"]] == ["structure:experience_create:Freelance Developer at "
                                                                  "Independent"]
    stale = json.loads(json.dumps(AFTER))
    stale["experience"].append(role("Contoso Retail", "Frontend Developer Trainee", "Apr 2022 - Oct 2022 · 7 mos"))
    code, out = verify(tmp_path, STRUCTURE, stale)
    assert code == 1 and out["failures"][0]["field"] == "structure:experience_delete:Frontend Developer Trainee at Contoso Retail"


def test_a_present_date_matches_whatever_the_platform_calls_it(tmp_path):
    rows = [{"kind": "experience_dates", "company": "Northwind", "title": "Technical Lead",
             "from": "Jun 2026", "to": "Present"}]
    now = dict(AFTER, experience=AFTER["experience"] + [role("Northwind", "Technical Lead",
                                                            "Jun 2026 - Present · 5 mos")])
    assert verify(tmp_path, rows, now)[0] == 0
    now["experience"][-1]["dates"] = "Jun 2026 - Actualidad · 5 mos"
    assert verify(tmp_path, rows, now)[0] == 0


def check(tmp_path, copy, structure=None, current=BEFORE):
    folder = tmp_path / "ana"
    folder.mkdir(exist_ok=True)
    (folder / "profile.md").write_text("---\ntarget_roles: [\"Full stack developer\"]\nkey_skills: [SQL]\n---\n")
    (folder / "achievements.yaml").write_text(
        "achievements:\n  - {id: ACH-001, en: \"Built SQL reports.\", verified: true}\n"
        "  - {id: ACH-002, en: \"Deployed a WhatsApp assistant on Railway.\", tags: [whatsapp, railway], verified: true}\n"
        "  - {id: ACH-003, en: \"Ran an Oracle migration.\", verified: false}\n"
        "skills:\n  - {name: SQL, achievements: [ACH-001]}\n")
    args = [write(tmp_path / "copy.json", copy), "--project", folder, "--json",
            "--current", write(tmp_path / "current.json", current)]
    if structure is not None:
        args += ["--structure", write(tmp_path / "structure.json", structure)]
    p = run(COPY, *args)
    assert p.returncode in (0, 1), p.stderr
    return p.returncode, json.loads(p.stdout)


def draft_for(after_titles):
    return {"platform": "linkedin", "language": "es", "skills": ["SQL"],
            "blocks": [{"section": "headline", "text": "Full stack developer", "achievements": ["ACH-001"]}]
            + [{"section": "experience", "company": c, "title": t, "text": "Did the work.", "no_claim": True}
               for c, t in after_titles]
            + [{"section": "education", "institution": "Example Institute", "text": "Web studies.",
                "no_claim": True}]}


FINAL = [("Sample Labs", "Fullstack Software Developer"),
         ("Sample Labs", "Senior Software Developer (Full Stack)"),
         ("Contoso Retail", "Frontend Developer"), ("Independent", "Freelance Developer")]


def test_a_copy_written_for_the_form_after_the_edits_passes_only_with_the_structure(tmp_path):
    code, report = check(tmp_path, draft_for(FINAL), STRUCTURE)
    assert code == 0, report["defects"]
    code, report = check(tmp_path, draft_for(FINAL))
    found = sorted(d["defect"] for d in report["defects"])
    assert code == 1 and found == ["education_not_covered", "role_not_covered", "role_not_covered",
                                   "role_not_covered", "unknown_role", "unknown_role", "unknown_role"], found


def test_a_role_skill_spelled_in_a_verified_claim_passes_and_one_that_is_not_verified_does_not(tmp_path):
    # the freelance position's own words ("WhatsApp assistant on Railway") prove its role skills; an unverified
    # claim ("Oracle migration") proves nothing, so that skill stays refused.
    copy = draft_for(FINAL)
    copy["skills"] += ["WhatsApp", "Railway", "Oracle"]
    freelance = next(b for b in copy["blocks"] if b.get("company") == "Independent")
    freelance["role_skills"] = ["WhatsApp", "Railway"]
    code, report = check(tmp_path, copy, STRUCTURE)
    assert code == 1 and [(d["defect"], d["where"]) for d in report["defects"]] == [("unsupported_skill", "Oracle")]
    copy["skills"].remove("Oracle")
    assert check(tmp_path, copy, STRUCTURE)[0] == 0


def test_a_role_skill_missing_from_the_profile_list_is_caught_before_linkedin_widens_the_list(tmp_path):
    # the real apply: a role skill not in `skills` was added by LinkedIn to the profile list, so `skills` never matched
    copy = draft_for(FINAL)
    next(b for b in copy["blocks"] if b.get("company") == "Independent")["role_skills"] = ["WhatsApp"]
    code, report = check(tmp_path, copy, STRUCTURE)
    assert code == 1 and [d["defect"] for d in report["defects"]] == ["role_skill_not_listed"]
    copy["skills"].append("WhatsApp")
    assert check(tmp_path, copy, STRUCTURE)[0] == 0
