"""upload_copy.py: the CV a form receives is named by the contact rule, never by the applier on the spot.

The case: a kit rendered before render_cv.py wrote CV_<Name>_<Surname>.pdf; the applier copied cv_ats.pdf to a name
it chose while every other application of the same user went out under the contact rule's name. Two recruiters, two
file names for one person.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "squads" / "jobs" / "skills" / "jobs-contract" / "scripts"
TOOL = SCRIPTS / "upload_copy.py"
ID = "JOB-20261023-truelogic-senior-front-end-engineer"


def run(*args):
    return subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True)


@pytest.fixture
def project(tmp_path):
    app = tmp_path / "openings" / ID / "application"
    app.mkdir(parents=True)
    (app / "cv_ats.pdf").write_bytes(b"%PDF-1.7 approved render")
    (tmp_path / "contact.yaml").write_text('name: "María José Pérez Gómez"\n', encoding="utf-8")
    return tmp_path, app


def test_a_kit_rendered_before_the_named_copy_gets_the_same_name_as_every_other_kit(project):
    root, app = project
    done = run(app)
    assert done.returncode == 0, done.stderr
    path = Path(done.stdout.strip())
    assert path.name == "CV_Maria_Perez.pdf"  # the name render_cv.py gives the other kits of this user
    assert path.read_bytes() == (app / "cv_ats.pdf").read_bytes()


def test_a_hand_named_copy_is_replaced_and_short_name_wins(project):
    root, app = project
    (app / "CV_Majo_Perez.pdf").write_bytes(b"%PDF old")
    (root / "contact.yaml").write_text('name: "María José Pérez Gómez"\nshort_name: "Majo Perez"\n')
    done = run(app)
    assert Path(done.stdout.strip()).name == "CV_Majo_Perez.pdf"
    assert [p.name for p in app.glob("CV_*.pdf")] == ["CV_Majo_Perez.pdf"]
    assert (app / "CV_Majo_Perez.pdf").read_bytes() == (app / "cv_ats.pdf").read_bytes()  # stale copy refreshed


def test_a_stale_copy_of_an_older_render_is_never_uploaded(project):
    root, app = project
    (app / "CV_Maria_Perez.pdf").write_bytes(b"%PDF earlier render")
    run(app)
    assert (app / "CV_Maria_Perez.pdf").read_bytes() == (app / "cv_ats.pdf").read_bytes()


def test_no_cv_or_no_name_refuses(project):
    root, app = project
    (root / "contact.yaml").write_text("email: x\n")
    assert run(app).returncode == 1
    (app / "cv_ats.pdf").unlink()
    assert run(app).returncode == 1


def test_help_runs():
    assert run("--help").returncode == 0
