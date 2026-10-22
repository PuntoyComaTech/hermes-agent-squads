"""Find the user's CLIs when the bot's PATH is a bare one (launchd, cron, a gateway): Homebrew, nvm, pnpm, Volta and
the user's local bin are searched too, so a tool that is installed is never reported missing."""
from __future__ import annotations

import os
from pathlib import Path


def _node_dirs(home: Path) -> list[str]:
    nvm = home / ".nvm" / "versions" / "node"
    found = sorted(nvm.glob("v*/bin"), key=lambda p: [int(x) for x in p.parent.name[1:].split(".") if x.isdigit()])
    return [str(p) for p in reversed(found)]


def tools_dir() -> Path:
    """The squad's scanner data (nuclei's template set); the scanners themselves come from Homebrew."""
    home = Path(os.environ.get("HERMES_REAL_HOME") or Path.home())
    return Path(os.environ.get("HERMES_WEB_TOOLS_DIR") or home / ".local" / "share" / "hermes-web-tools")


def augment_path() -> str:
    """Append the usual install folders that exist and are missing from PATH (the caller's PATH keeps priority);
    returns the new PATH (also set)."""
    home = Path(os.environ.get("HERMES_REAL_HOME") or Path.home())
    prefix = os.environ.get("HOMEBREW_PREFIX")  # what `brew shellenv` exports; else Homebrew's default prefixes
    brew = [str(Path(prefix) / "bin")] if prefix else ["/opt/homebrew/bin", "/home/linuxbrew/.linuxbrew/bin",
                                                          "/usr/local/bin"]
    extra = [*brew, str(home / ".local" / "bin"), str(home / ".volta" / "bin"),
             str(home / "Library" / "pnpm"), str(home / ".local" / "share" / "pnpm"), *_node_dirs(home)]
    have = os.environ.get("PATH", "").split(os.pathsep)
    add = [d for d in extra if d not in have and Path(d).is_dir()]
    os.environ["PATH"] = os.pathsep.join([*have, *add]) if have != [""] else os.pathsep.join(add)
    return os.environ["PATH"]


if __name__ == "__main__":
    import sys
    if sys.argv[1:2] in (["-h"], ["--help"]):
        print("usage: toolpath.py [--help]\n\n" + (__doc__ or "").strip() + "\n\nPrints the augmented PATH. Exit 0.")
    else:
        print(augment_path())
