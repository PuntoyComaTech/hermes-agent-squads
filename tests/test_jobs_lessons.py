"""Writing lessons: what the review learns must reach the writer.

The scenario: the reviewer kept correcting the same defects (two achievements merged into one feature, "built X" where
the record says "built on X") in opening after opening, because those lessons lived only in the reviewer's own memory
and the writer never saw them. lessons.py keeps them in the project, where the writer reads them before each draft.
Every check runs the real script with fictional names.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "squads" / "jobs" / "skills" / "jobs-contract" / "scripts" / "lessons.py"
MERGE = "Never merge two achievements into one feature the record does not connect; ask whether X feeds Y."


def project(tmp_path: Path, extra: str = "") -> Path:
    (tmp_path / "profile.md").write_text(f"---\nsearch: active\n{extra}---\n\nAna Example.\n", encoding="utf-8")
    return tmp_path


def run(p: Path, *args: str):
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), *args, "--project", str(p), "--today", "2026-10-28"],
                       capture_output=True, text=True)
    return r.returncode, (json.loads(r.stdout) if r.returncode == 0 else None), r.stderr


def test_a_lesson_added_by_the_reviewer_is_what_the_writer_lists(tmp_path):
    p = project(tmp_path)
    code, out, _ = run(p, "add", "--text", MERGE, "--source", "JOB-20261023-acme-ai-engineer")
    assert code == 0 and out["result"] == "added"
    code, out, _ = run(p, "list")
    assert code == 0 and out["count"] == 1 and out["lessons"][0]["text"] == MERGE
    assert MERGE in (p / "writing-lessons.md").read_text(encoding="utf-8")


def test_the_same_defect_again_counts_instead_of_duplicating(tmp_path):
    p = project(tmp_path)
    run(p, "add", "--text", MERGE, "--source", "JOB-20261023-acme-ai-engineer")
    reworded = "Never merge two separate achievements into one feature that the record does not connect."
    code, out, _ = run(p, "add", "--text", reworded, "--source", "JOB-20261024-globex-backend")
    assert code == 0 and out["result"] == "seen_again" and out["lesson"]["count"] == 2
    other = "Write 'built on X' when the record says the work used X; 'built X' only when it says so."
    assert run(p, "add", "--text", other, "--source", "JOB-20261024-globex-backend")[1]["result"] == "added"
    assert run(p, "list")[1]["count"] == 2


def test_a_lesson_naming_a_confidential_client_or_contact_data_is_refused(tmp_path):
    p = project(tmp_path, 'confidential_terms: ["Northwind"]\n')
    code, _, err = run(p, "add", "--text", "Never tie the Northwind storefront to the Tech Lead role.",
                       "--source", "JOB-20261023-acme-ai-engineer")
    assert code == 1 and "Northwind" in err
    code, _, err = run(p, "add", "--text", "Never print ana@example.com in a bullet.",
                       "--source", "JOB-20261023-acme-ai-engineer")
    assert code == 1 and "e-mail" in err
    assert not (p / "writing-lessons.md").exists()


def test_a_full_list_refuses_until_one_is_merged(tmp_path):
    p = project(tmp_path)
    for i in range(25):
        assert run(p, "add", "--text", f"Lesson {i} about topic{i} wording{i} rule{i}.",
                   "--source", "JOB-20261023-acme-ai-engineer")[0] == 0
    code, _, err = run(p, "add", "--text", "One more distinct lesson about zebras.",
                       "--source", "JOB-20261023-acme-ai-engineer")
    assert code == 1 and "25 lessons" in err


def test_long_lessons_and_bad_sources_are_refused(tmp_path):
    p = project(tmp_path)
    assert run(p, "add", "--text", "x " * 200, "--source", "JOB-20261023-acme-ai-engineer")[0] == 1
    assert run(p, "add", "--text", MERGE, "--source", "../profile")[0] == 1
