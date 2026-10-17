"""Public docs: diagrams render vertically on GitHub, install commands exist, agents install the builder only."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DOCS = [REPO / "README.md", *sorted((REPO / "squads").glob("*/README.md"))]


@pytest.mark.parametrize("doc", DOCS, ids=lambda p: str(p.relative_to(REPO)))
def test_mermaid_diagrams_are_vertical(doc):
    heads = re.findall(r"```mermaid\s*\n\s*(\S+ ?\S*)", doc.read_text())
    assert all(h in ("flowchart TD", "flowchart TB", "graph TD", "graph TB") for h in heads), heads


def test_readme_squads_match_the_repo():
    text = (REPO / "README.md").read_text()
    shipped = sorted(p.parent.name for p in (REPO / "squads").glob("*/squad.yaml"))
    for key in shipped:
        assert f"(squads/{key}/README.md)" in text, key
    linked = set(re.findall(r"\(squads/([a-z0-9-]+)/README\.md\)", text))
    assert linked <= set(shipped), linked - set(shipped)


def test_readme_install_command_uses_real_flags():
    text = (REPO / "README.md").read_text()
    line = next(l for l in text.splitlines() if l.startswith("hermes profile install "))
    flags = set(re.findall(r"(--[a-z-]+)", line))
    if not shutil.which("hermes"):
        pytest.skip("hermes not on PATH")
    hermes = subprocess.run(["hermes", "profile", "install", "--help"], capture_output=True, text=True)
    assert hermes.returncode == 0, hermes.stderr
    assert flags <= set(re.findall(r"(--[a-z-]+)", hermes.stdout)), flags


def test_agents_install_only_the_builder():
    agents = (REPO / "AGENTS.md").read_text()
    assert "## Installing for a user" in agents and "never installs squads or picks models" in agents
    assert "install only the builder" in (REPO / "llms.txt").read_text()


def test_scripts_named_in_readme_and_agents_exist():
    names = set()
    for doc in ("README.md", "AGENTS.md"):
        names |= set(re.findall(r"(?<![\w/<>.-])([a-z][a-z0-9_]*\.py)\b", (REPO / doc).read_text()))
    assert names, "no script named"
    missing = sorted(n for n in names if not (REPO / "scripts" / n).is_file())
    assert not missing, missing


BOT_READ = [REPO / "SOUL.md", REPO / "AGENTS.md", REPO / "llms.txt", REPO / "CONTRIBUTING.md", *DOCS,
            *(p for d in ("skills", "squads") for p in sorted((REPO / d).rglob("*"))
              if p.is_file() and p.suffix in (".md", ".yaml", ".json", ".py") and "__pycache__" not in p.parts)]


@pytest.mark.parametrize("stale", ["migrate_v1", "squadctl project add", "squadctl.py project add"])
def test_no_retired_commands_in_bot_read_files_or_readmes(stale):
    hits = [str(p.relative_to(REPO)) for p in BOT_READ if stale in p.read_text(errors="ignore")]
    assert not hits, hits
