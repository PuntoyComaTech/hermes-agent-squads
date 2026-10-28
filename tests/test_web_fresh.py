"""The versions gate (fresh.mjs) reads the lockfile of every pnpm release a site may be installed with.

pnpm 9 writes a scoped dependency name with single quotes ('@types/node':) and pnpm 12 with double quotes
("@types/node":). A gate that only knew the first form reported every scoped package of a fresh pnpm 12 base as
"the lockfile nothing", so `pnpm quality` failed on a base nobody had touched. Each test runs the real script with
node; `pnpm` is a stub on PATH that answers `outdated` with nothing, so no network is used.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FRESH = REPO / "squads" / "web" / "skills" / "site-contract" / "templates" / "quality" / "tools" / "quality" / "fresh.mjs"
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

PACKAGE = {"name": "demo", "devDependencies": {"@types/node": "^26.6.5", "vitest": "^5.0.5"}}


def lockfile(quote: str) -> str:
    q = quote
    return (
        'lockfileVersion: "9.0"\n\nimporters:\n'
        f"  {q}.{q}:\n"
        "    devDependencies:\n"
        f"      {q}@types/node{q}:\n        specifier: ^26.6.5\n        version: 26.6.5\n"
        "      vitest:\n        specifier: ^5.0.5\n        version: 5.0.5\n"
    )


def run_gate(tmp_path: Path, lock: str) -> tuple[int, list]:
    site = tmp_path / "site"
    (site / "tools" / "quality").mkdir(parents=True)
    for name in ("fresh.mjs", "toolkit.mjs"):  # fresh.mjs imports the shared helpers beside it
        shutil.copy(FRESH.with_name(name), site / "tools" / "quality" / name)
    (site / "package.json").write_text(json.dumps(PACKAGE))
    (site / "pnpm-lock.yaml").write_text(lock)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "pnpm"
    stub.write_text("#!/bin/sh\necho '{}'\n")
    stub.chmod(0o755)
    env = {"PATH": f"{bin_dir}:{Path(shutil.which('node')).parent}"}
    p = subprocess.run(["node", "tools/quality/fresh.mjs", "--json"], cwd=site, env=env, capture_output=True,
                       text=True, timeout=60)
    return p.returncode, json.loads(p.stdout or "[]")


@needs_node
@pytest.mark.parametrize("quote", ["'", '"'], ids=["pnpm9-single-quotes", "pnpm12-double-quotes"])
def test_a_scoped_package_resolved_by_pnpm_add_passes_the_gate(tmp_path, quote):
    code, findings = run_gate(tmp_path, lockfile(quote))
    assert findings == [] and code == 0


@needs_node
def test_a_package_json_line_pnpm_never_resolved_is_still_caught(tmp_path):
    lock = lockfile('"').replace('      "@types/node":\n        specifier: ^26.6.5\n        version: 26.6.5\n', "")
    code, findings = run_gate(tmp_path, lock)
    assert code == 1 and [f["name"] for f in findings] == ["@types/node"]
    assert findings[0]["kind"] == "not-resolved"
