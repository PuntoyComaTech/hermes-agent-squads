"""application_notices.py as the cron runs it: an application the applier recorded reaches the owner's phone once,
with the CV that was sent attached, and nothing else does.

Real scripts (status.py writes the history the applier writes), real argv, the fake hermes for the project list.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FAKES = REPO / "tests" / "fakes"
NOTICES = REPO / "squads" / "jobs" / "scripts" / "application_notices.py"
STATUS = REPO / "squads" / "jobs" / "skills" / "jobs-contract" / "scripts" / "status.py"
PROFILE = "---\nsearch: active\nuser_language: es\ntimezone: America/Bogota\nauto_apply: auto\n---\n"


def make_env(tmp: Path) -> tuple[dict, Path]:
    root = tmp / "hermes"
    (root / "profiles" / "jobs").mkdir(parents=True)
    bindir = tmp / "bin"
    bindir.mkdir()
    (bindir / "hermes").write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKES / "hermes.py"}" "$@"\n')
    (bindir / "hermes").chmod(0o755)
    env = {k: v for k, v in os.environ.items() if k != "HERMES_DELEGATED_CHILD_CONTEXT"}
    env.update({"PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}", "HERMES_HOME": str(root / "profiles" / "jobs")})
    folder = tmp / "search"
    folder.mkdir()
    (folder / "profile.md").write_text(PROFILE)
    done = subprocess.run(["hermes", "-p", "jobs", "project", "create", "Search", str(folder), "--slug", "search"],
                          capture_output=True, text=True, env={**env, "HERMES_HOME": str(root)})
    assert done.returncode == 0, done.stderr
    return env, folder


def opening(folder: Path, oid: str, company: str, *, cv: bool = True, brief: str = "") -> Path:
    d = folder / "openings" / oid
    (d / "application").mkdir(parents=True)
    (d / "opening.md").write_text(f"---\nid: {oid}\ncompany: {company}\nrole: Senior Backend Engineer\n"
                                  f"apply_url: https://jobs.lever.co/{company.lower()}/1/apply\nposted_at: 2026-10-20\n"
                                  f"work_mode: remote_country:co\n---\nBody\n")
    analysis = {"id": oid, "fit": {"score": 81, "decision": "PURSUE"},
                "company": {"summary": f"{company} sells order automation to distributors. It has 140 people."}}
    if brief:
        analysis["brief"] = brief
    (d / "analysis.json").write_text(json.dumps(analysis))
    if cv:
        (d / "application" / "cv_ats.pdf").write_bytes(b"%PDF-1.4\n")
    return d


def submitted(d: Path) -> None:
    """What record_submission.py leaves after a real click: the submission file the applier wrote."""
    (d / "application" / "submission.json").write_text(json.dumps({"id": d.name, "result": "SUBMITTED",
                                                                     "method": "no_login_form"}))


def status(d: Path, *steps: str) -> None:
    for step in steps:
        done = subprocess.run([sys.executable, "-I", str(STATUS), "append", str(d), step, "--by", "jobs-applier"],
                              capture_output=True, text=True)
        assert done.returncode == 0, done.stderr


def backdate(d: Path, when: str) -> None:
    doc = json.loads((d / "status.json").read_text())
    for line in doc["history"]:
        line["date"] = when
    (d / "status.json").write_text(json.dumps(doc))


def run(env, *extra):
    return subprocess.run([sys.executable, "-I", str(NOTICES), *extra], capture_output=True, text=True, env=env,
                          timeout=120)


def test_a_sent_application_is_posted_once_with_its_cv_attached(tmp_path):
    env, folder = make_env(tmp_path)
    d = opening(folder, "JOB-20261024-acme-backend", "Acme",
                brief="Backend de pedidos con IA para distribuidores; Node/AWS")
    status(d, "found", "analyzed", "ready", "applying", "applied")
    submitted(d)
    first = run(env)
    assert first.returncode == 0, first.stderr
    lines = first.stdout.strip().splitlines()
    assert lines[0] == "Postulé: Senior Backend Engineer - Acme"
    assert lines[1].startswith("81/100 · remoto CO · publicada 2026-10-20 · enviada 20")
    assert lines[2] == "Backend de pedidos con IA para distribuidores; Node/AWS"
    assert lines[3] == "https://jobs.lever.co/acme/1/apply"
    # the delivery uploads this file: an absolute path the owner never has to type on a phone
    assert lines[4] == f"MEDIA:{d / 'application' / 'cv_ats.pdf'}"
    assert run(env).stdout == "", "posted once"


def test_nothing_short_of_a_submit_reaches_the_owner(tmp_path):
    env, folder = make_env(tmp_path)
    for oid, steps in (("JOB-1-a-ready", ("ready",)), ("JOB-2-b-kit", ("ready", "manual_application")),
                       ("JOB-3-c-skip", ("delivered", "skipped")), ("JOB-4-d-watch", ("analyzed",))):
        status(opening(folder, oid, oid.split("-")[2]), *steps)
    assert run(env).stdout == ""


def test_two_sends_go_out_one_per_run_oldest_first(tmp_path):
    """The delivery attaches every MEDIA file after the text: two openings in one message would split CV from job."""
    env, folder = make_env(tmp_path)
    old = opening(folder, "JOB-20261024-beta-backend", "Beta")
    new = opening(folder, "JOB-20261024-alfa-backend", "Alfa")
    status(old, "applied")
    status(new, "applied")
    submitted(old)
    submitted(new)
    now = datetime.now()
    backdate(old, (now - timedelta(minutes=40)).strftime("%Y-%m-%dT%H:%M"))  # the applier runs minutes apart
    backdate(new, (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M"))
    first, second = run(env).stdout, run(env).stdout
    assert first.count("MEDIA:") == 1 and second.count("MEDIA:") == 1
    assert "Beta" in first.splitlines()[0] and "Alfa" in second.splitlines()[0]
    assert run(env).stdout == ""


def test_the_first_run_after_an_install_does_not_replay_old_applications(tmp_path):
    env, folder = make_env(tmp_path)
    old = opening(folder, "JOB-20260901-old-backend", "Old")
    status(old, "applied")
    submitted(old)
    backdate(old, "2026-09-01T10:00")
    fresh = opening(folder, "JOB-20261024-new-backend", "New")
    status(fresh, "applied")
    submitted(fresh)
    out = run(env).stdout
    assert out.startswith("Postulé: Senior Backend Engineer - New")
    assert run(env).stdout == "", "the September application was history, not news"


def test_a_missing_cv_is_said_not_attached(tmp_path):
    env, folder = make_env(tmp_path)
    d = opening(folder, "JOB-20261024-nocv-backend", "Nocv", cv=False)
    status(d, "applied")
    submitted(d)
    out = run(env).stdout
    assert "MEDIA:" not in out and "No encuentro el CV: cv_ats.pdf" in out
    # without a brief the company summary's first sentence says what the job is about
    assert "Nocv sells order automation to distributors." in out and "140 people" not in out


def test_an_application_the_owner_reported_is_not_announced_as_a_send(tmp_path):
    """"I applied" makes the manager append `applied` with no submission: no "Postulé" notice, no CV claim."""
    env, folder = make_env(tmp_path)
    d = opening(folder, "JOB-20261024-self-backend", "Self")
    status(d, "delivered", "applied")
    assert run(env).stdout == ""


def test_unknown_placeholders_never_reach_the_phone(tmp_path):
    env, folder = make_env(tmp_path)
    d = opening(folder, "JOB-20261024-vague-backend", "Vague")
    text = (d / "opening.md").read_text().replace("posted_at: 2026-10-20", "posted_at: unknown")
    (d / "opening.md").write_text(text.replace("work_mode: remote_country:co", "work_mode: unknown"))
    status(d, "applied")
    submitted(d)
    facts = run(env).stdout.splitlines()[1]
    assert "unknown" not in facts and facts.startswith("81/100 · enviada ")


def test_a_corrupt_state_file_is_a_first_run_not_a_replay_of_history(tmp_path):
    env, folder = make_env(tmp_path)
    old = opening(folder, "JOB-20260901-old-backend", "Old")
    status(old, "applied")
    submitted(old)
    backdate(old, "2026-09-01T10:00")
    state = Path(env["HERMES_HOME"]) / "local" / "state" / "application_notices.json"
    state.parent.mkdir(parents=True)
    state.write_text("{not json")
    assert run(env).stdout == ""


def test_a_hermes_failure_is_said_once_an_hour_not_every_five_minutes(tmp_path):
    env, _ = make_env(tmp_path)
    broken = tmp_path / "bin" / "hermes"
    broken.write_text("#!/bin/sh\necho 'gateway down' >&2\nexit 3\n")
    first = run(env, "--now", "2026-10-24T10:00")
    assert first.returncode == 1 and "jobs-notices:" in first.stdout
    assert run(env, "--now", "2026-10-24T10:05").stdout == ""
    assert "jobs-notices:" in run(env, "--now", "2026-10-24T11:10").stdout
