#!/usr/bin/env python3
"""Where the installed Hermes keeps its dependency state, and how another data root reuses it.

Hermes scopes dependency state per data root (`<root>/installs/<key>`). A process whose HERMES_HOME lies outside
the root that owns the checkout (a test's temporary root, a release gate's root, a second data root) borrows the
checkout: before it imports anything it syncs a dependency environment of its own (about 350 MB), and its uv cache
(`<root>/cache/uv`) starts empty, so that sync downloads every wheel again. Minutes, network- and load-dependent.

- `owner_root(python, source)`: the data root that owns the install, from Hermes itself
  (`owning_home_root(...) or get_default_hermes_root()`, the rule behind its store root).
- `probe_home(owner)`: an empty HERMES_HOME inside the owner root for questions about the installed code (default
  identity, default toolsets). Hermes resolves it to the owner's dependency state and never syncs.
- `share_uv_cache(root, owner)`: links a borrowing root's uv cache to the owner's, the machine cache Hermes shares
  across profiles by design, so the borrowing root's one sync runs from cache in seconds. Deleting the borrowing
  root removes only the link.

Stdlib only. `--json` prints the owner root and whether a given root borrows.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

OWNER_CODE = ("import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); "
              "from pm.environments import owning_home_root; from hermes_constants import get_default_hermes_root; "
              "print(owning_home_root(Path(sys.argv[1]).resolve()) or get_default_hermes_root())")


def runtime_command() -> tuple[str, str] | None:
    """(python, Hermes source root) from `hermes --print-runtime-command`, or None."""
    env = {k: v for k, v in os.environ.items() if k != "HERMES_HOME"}
    try:
        p = subprocess.run(["hermes", "--print-runtime-command"], capture_output=True, text=True, env=env,
                           timeout=60, stdin=subprocess.DEVNULL)
        argv = json.loads(p.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    src = re.search(r"sys\.path\.insert\(0, '([^']+)'\)", argv[-1]) if isinstance(argv, list) and argv else None
    return (argv[0], src.group(1)) if src else None


def owner_root(python: str, source: str) -> Path | None:
    """The data root that owns the install at `source`, asked of Hermes with no HERMES_HOME; None when this Hermes
    cannot answer (a runtime without PM, a fake)."""
    env = {k: v for k, v in os.environ.items() if k != "HERMES_HOME"}
    try:
        p = subprocess.run([python, "-I", "-c", OWNER_CODE, source], capture_output=True, text=True, env=env,
                           timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    lines = p.stdout.strip().splitlines()
    return Path(lines[-1]) if p.returncode == 0 and lines else None


def installed_owner() -> Path | None:
    rt = runtime_command()
    return owner_root(*rt) if rt else None


def borrows(root: Path, owner: Path | None) -> bool:
    """True when Hermes run with HERMES_HOME under `root` keeps dependency state apart from the owner's."""
    if owner is None:
        return False
    r, o = Path(root).expanduser().absolute(), Path(owner).expanduser().absolute()
    r = r.resolve() if r.exists() else r
    o = o.resolve() if o.exists() else o
    return r != o and o not in r.parents


def probe_home(owner: Path) -> Path:
    """A new, empty HERMES_HOME under `<owner>/cache/scratch`; the caller removes it."""
    scratch = Path(owner) / "cache" / "scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix="squadctl-probe-", dir=scratch))


def share_uv_cache(root: Path, owner: Path | None) -> bool:
    """Link `<root>/cache/uv` to the owner's uv cache when `root` borrows and has no cache of its own yet.
    True when the link was made."""
    if owner is None or not borrows(root, owner):
        return False
    src, dest = owner / "cache" / "uv", Path(root) / "cache" / "uv"
    if not src.is_dir() or dest.exists() or dest.is_symlink():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(src.resolve(), target_is_directory=True)
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Report the data root that owns the installed Hermes and whether a root "
                                            "borrows it (its own dependency sync).",
                                epilog="Exit 0 answered, 1 the installed Hermes could not tell.")
    p.add_argument("--root", type=Path, help="data root to check (default: none)")
    p.add_argument("--share-cache", action="store_true", help="link --root's uv cache to the owner's when it borrows")
    p.add_argument("--json", action="store_true", help="print JSON")
    a = p.parse_args(argv)
    owner = installed_owner()
    out: dict[str, object] = {"owner": str(owner) if owner else None}
    if a.root:
        out["borrows"] = borrows(a.root, owner)
        if a.share_cache:
            out["shared_cache"] = share_uv_cache(a.root, owner)
    print(json.dumps(out) if a.json else "\n".join(f"{k}: {v}" for k, v in out.items()))
    return 0 if owner else 1


if __name__ == "__main__":
    sys.exit(main())
