"""A data root that borrows the installed Hermes (a temp root, a release gate's root) must not pay a cold dependency
sync: squadctl asked the runtime from such a root, Hermes synced ~350 MB into it from an empty uv cache, and the
120 s probe timed out on a loaded machine (red release gates for code that was fine)."""
import argparse
import sys
import time
from pathlib import Path

import pytest

from _real import needs_hermes, temp_root

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import hermes_home as hh  # noqa: E402


def test_a_root_outside_the_owner_borrows_and_one_inside_does_not(tmp_path):
    owner = tmp_path / "owner"
    (owner / "profiles" / "web").mkdir(parents=True)
    assert hh.borrows(tmp_path / "elsewhere", owner)
    assert not hh.borrows(owner, owner) and not hh.borrows(owner / "profiles" / "web", owner)
    assert not hh.borrows(tmp_path / "elsewhere", None)


def test_a_borrowing_root_gets_a_link_to_the_owner_cache_and_deleting_it_keeps_the_cache(tmp_path):
    owner = tmp_path / "owner"
    (owner / "cache" / "uv").mkdir(parents=True)
    (owner / "cache" / "uv" / "wheel").write_text("x")
    root = tmp_path / "temp-root"
    root.mkdir()
    assert hh.share_uv_cache(root, owner)
    assert (root / "cache" / "uv").is_symlink() and (root / "cache" / "uv" / "wheel").read_text() == "x"
    assert not hh.share_uv_cache(root, owner)  # idempotent
    import shutil
    shutil.rmtree(root)
    assert (owner / "cache" / "uv" / "wheel").read_text() == "x"


def test_no_link_inside_the_owner_or_over_an_existing_cache(tmp_path):
    owner = tmp_path / "owner"
    (owner / "cache" / "uv").mkdir(parents=True)
    assert not hh.share_uv_cache(owner / "profiles" / "web", owner)
    root = tmp_path / "temp-root"
    (root / "cache" / "uv").mkdir(parents=True)
    assert not hh.share_uv_cache(root, owner) and not (root / "cache" / "uv").is_symlink()


@needs_hermes
def test_squadctl_reads_the_runtime_from_a_temp_root_without_a_dependency_sync(tmp_path):
    """The exact call that timed out: default toolsets and identity from a fresh root outside ~/.hermes."""
    import squadctl
    if hh.installed_owner() is None:
        pytest.skip("the installed Hermes does not report an owning root")
    root = temp_root(tmp_path)
    ctx = squadctl.Ctx(argparse.Namespace(hermes_root=str(root), src=None, local="/nonexistent",
                                         builder="builder", json=True))
    started = time.monotonic()
    tools = ctx.default_toolsets()
    identity = ctx.default_identity()
    elapsed = time.monotonic() - started
    assert {"terminal", "file", "web"} <= tools and identity
    assert not (root / "installs").exists(), "Hermes synced a dependency environment into the temp root"
    assert elapsed < 60, f"runtime probe took {elapsed:.0f}s"
    probe = ctx.runtime_home()
    assert probe.parent == hh.installed_owner() / "cache" / "scratch"
