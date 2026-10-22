"""Contract with reality: squadctl against the real `hermes` binary in a temp root (never `~/.hermes`).

- `plan` runs whenever `hermes` is on PATH: it reads real profiles and boards through the real CLI.
- `apply` writes five profiles and takes a minute or more, so it also needs HERMES_REAL_SMOKE=1 (CI: the
  manually triggered `real-hermes-smoke` job). It checks what the fake cannot: the toolsets real `tools enable`
  accepted, the MCP servers real `mcp add` saved enabled, and the worker scripts shipped inside their skills.
Lanes come from scripts/data/model-roles.yaml, so a lane rename cannot leave this file assigning dead lanes.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from _real import env_for, needs_hermes, temp_root

REPO = Path(__file__).resolve().parents[1]
pytestmark = [pytest.mark.real_hermes, needs_hermes]

MODELS = {"provider": "smoke", "model": "smoke-model"}
WEB_BOTS = ["web", "web-frontend", "web-backend", "web-qa", "web-deployer"]
LANES = sorted(yaml.safe_load((REPO / "scripts" / "data" / "model-roles.yaml").read_text())["lanes"])


def models_file(tmp_path: Path) -> Path:
    """A models file (installed.yaml shape) that assigns every lane model-roles.yaml defines."""
    p = tmp_path / "models.json"  # JSON is a YAML subset: read_yaml accepts it
    p.write_text(json.dumps({"bots": {}, "lanes": {lane: dict(MODELS) for lane in LANES}}))
    return p


def squadctl(*args: str, root: Path, models: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(REPO / "scripts" / "squadctl"), *args, "--models", str(models), "--json"],
                          env=env_for(root), capture_output=True, text=True, timeout=900)


def test_plan_web_against_real_hermes(tmp_path):
    root = temp_root(tmp_path)
    plan = squadctl("plan", "web", root=root, models=models_file(tmp_path))
    assert plan.returncode == 0, (plan.stdout + plan.stderr)[-600:]
    out = json.loads(plan.stdout)
    assert out["summary"] == {"would-create": 5} and out["board"] == "would-create"
    notes = [n for b in out["bots"] for n in b.get("notes", [])]
    assert not [n for n in notes if n.startswith("no model assigned")], notes
    assert not any((root / "profiles").glob("web*")), "plan must not create profiles"


@pytest.mark.skipif(os.environ.get("HERMES_REAL_SMOKE") != "1",
                    reason="slow (writes 5 real profiles): set HERMES_REAL_SMOKE=1")
def test_apply_web_against_real_hermes(tmp_path):
    root = temp_root(tmp_path)
    models = models_file(tmp_path)
    out = squadctl("apply", "web", "--yes", root=root, models=models)
    assert out.returncode == 0, (out.stdout + out.stderr)[-600:]
    spec = yaml.safe_load((REPO / "squads" / "web" / "squad.yaml").read_text())

    for bot in WEB_BOTS:
        cfg = yaml.safe_load((root / "profiles" / bot / "config.yaml").read_text())
        landed = set(cfg["platform_toolsets"]["cli"])
        # real `tools enable` drops an unknown name and exits 0: every manifest toolset must have landed
        assert set(spec["bots"][bot]["toolsets"]) <= landed, (bot, sorted(set(spec["bots"][bot]["toolsets"]) - landed))
        # real `mcp add` can print "Cancelled." and exit 0: every declared server must be saved and enabled
        for server in spec["bots"][bot].get("mcp") or {}:
            assert cfg["mcp_servers"][server]["enabled"] is True, (bot, server)

    # worker scripts ship inside site-contract, which every web bot carries: the QA script, the strict base, the
    # logins and the live tab for the manager, the progress saves for the builders
    def contract(bot: str, script: str) -> Path:
        return root / "profiles" / bot / "skills" / "squad-web" / "site-contract" / "scripts" / script

    scripts = [contract("web-qa", "check_site.py"), contract("web", "site_base.py"), contract("web", "web_access.py"),
               contract("web", "live_view.py"), contract("web-frontend", "save_progress.py"),
               contract("web-backend", "save_progress.py"), contract("web-deployer", "web_access.py")]
    for script in scripts:
        assert script.is_file(), f"not installed: {script}"
        # the system python has no PyYAML: --help must still work
        h = subprocess.run([sys.executable, str(script), "--help"], capture_output=True, text=True, timeout=120)
        assert h.returncode == 0 and h.stdout.strip(), h.stderr[-300:]

    again = squadctl("apply", "web", "--yes", root=root, models=models)
    assert again.returncode == 0, again.stdout[-600:]
    assert json.loads(again.stdout)["summary"] == {"unchanged": 5}, again.stdout[-600:]
