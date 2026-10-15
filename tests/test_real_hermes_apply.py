"""Real-hermes apply smoke test: `squadctl apply web` against the real `hermes` in a temp root.

Skipped by default. Run it with a real `hermes` on PATH and HERMES_REAL_SMOKE=1 (CI: the manually
triggered `real-hermes-smoke` job). Everything lands in a temp HERMES_HOME; the real ~/.hermes is
never written. It also proves the B2 fix: worker scripts ship inside their skill dirs, so web-qa can
run check_site.py and web-frontend can run scaffold_site.py from $HERMES_HOME.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.real_hermes, pytest.mark.skipif(
    os.environ.get("HERMES_REAL_SMOKE") != "1" or not shutil.which("hermes"),
    reason="skipped by default: set HERMES_REAL_SMOKE=1 with a real `hermes` on PATH to run it")]

MODELS = {"provider": "smoke", "model": "smoke-model"}
WEB_BOTS = ["web", "web-frontend", "web-backend", "web-qa", "web-deployer"]
LANES = ["design", "lead", "code", "advisor", "review", "copy", "research", "digest", "aux", "vision"]


def models_file(tmp_path: Path) -> Path:
    """A models file (installed.yaml shape) that assigns every bot and lane of the web squad."""
    doc = {"bots": {name: dict(MODELS) for name in WEB_BOTS},
           "lanes": {lane: dict(MODELS) for lane in LANES}}
    p = tmp_path / "models.json"  # JSON is a YAML subset: read_yaml accepts it
    p.write_text(json.dumps(doc))
    return p


def squadctl(*args: str, root: Path, models: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "HERMES_HOME": str(root)}
    return subprocess.run([str(REPO / "scripts" / "squadctl"), *args, "--models", str(models), "--json"],
                          env=env, capture_output=True, text=True, timeout=900)


def test_apply_web_against_real_hermes(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    models = models_file(tmp_path)

    plan = squadctl("plan", "web", root=root, models=models)
    assert plan.returncode == 0, (plan.stdout + plan.stderr)[-600:]
    assert json.loads(plan.stdout)["summary"] == {"would-create": 5}

    out = squadctl("apply", "web", "--yes", root=root, models=models)
    assert out.returncode == 0, (out.stdout + out.stderr)[-600:]

    # worker scripts ship inside their skills (site-contract carries the QA script, building-frontend the scaffolder)
    qa = root / "profiles" / "web-qa" / "skills" / "squad-web" / "site-contract" / "scripts" / "check_site.py"
    fe = root / "profiles" / "web-frontend" / "skills" / "squad-web" / "building-frontend" / "scripts" / "scaffold_site.py"
    assert qa.is_file(), f"check_site.py not installed at {qa}"
    assert fe.is_file(), f"scaffold_site.py not installed at {fe}"
    for script in (qa, fe):
        # the system python has no PyYAML: --help must still work (the B1 blocker)
        h = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=120)
        assert h.returncode == 0 and h.stdout.strip(), h.stderr[-300:]
