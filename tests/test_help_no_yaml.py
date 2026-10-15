"""Every shipped Python script must answer `--help` under a bare `python3 -I` with no YAML module.

The Hermes runtime provides `hermes_yaml` (see scripts/hpy); a stock system python3 has neither that nor
PyYAML, so `--help` must never import YAML at module level. The blocker below raises ModuleNotFoundError
for yaml/ruamel/hermes_yaml before the script runs, which is stricter and hermetic (no site-packages
trickery): a script that imports YAML anywhere on the --help path fails this test.
"""
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

BLOCKER = r"""
import runpy, sys

class _BlockYAML:
    BLOCKED = {"yaml", "ruamel", "hermes_yaml"}

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in self.BLOCKED:
            raise ModuleNotFoundError(f"no YAML in this test: {name}", name=name)
        return None

sys.meta_path.insert(0, _BlockYAML())
script = sys.argv[1]
sys.argv = [script, "--help"]
runpy.run_path(script, run_name="__main__")
"""


def shipped_scripts() -> list[Path]:
    out = sorted((REPO / "scripts").glob("*.py"))
    out += sorted((REPO / "squads").glob("*/scripts/*.py"))
    out += sorted((REPO / "squads").glob("*/skills/*/scripts/*.py"))
    assert out, "no scripts found"
    return out


@pytest.mark.parametrize("script", shipped_scripts(), ids=lambda p: str(p.relative_to(REPO)))
def test_help_works_without_pyyaml(script: Path):
    proc = subprocess.run([sys.executable, "-I", "-c", BLOCKER, str(script)], capture_output=True, text=True,
                          timeout=60)
    assert proc.returncode == 0, f"{script} --help failed without a YAML module: {proc.stderr[-400:]}"
    assert proc.stdout.strip(), f"{script} --help printed nothing"


def test_blocker_actually_blocks_yaml():
    """The harness must fail a script that imports yaml at import time (guards the test itself)."""
    bad = REPO / "scripts" / "gate_lib.py"  # any stdlib-only script proves runpy works
    ok = subprocess.run([sys.executable, "-I", "-c", BLOCKER, str(bad)], capture_output=True, text=True, timeout=60)
    assert ok.returncode == 0
    probe = Path(subprocess.run([sys.executable, "-I", "-c", "import tempfile; print(tempfile.mkdtemp())"],
                                capture_output=True, text=True).stdout.strip()) / "probe.py"
    probe.write_text("import yaml\nprint('unreachable')\n")
    bad_run = subprocess.run([sys.executable, "-I", "-c", BLOCKER, str(probe)], capture_output=True, text=True,
                             timeout=60)
    assert bad_run.returncode != 0 and "no YAML in this test" in bad_run.stderr
