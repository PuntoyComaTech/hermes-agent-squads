#!/usr/bin/env python3
"""In-process config writer for ONE Hermes profile. Run only by squadctl.py, under the Hermes runtime interpreter
with HERMES_HOME pointing at the profile. Uses Hermes's own writers (set_config_value, the Desktop ui_meta merge), so
validation and file locking are exactly those of `hermes config set`, at one process per bot instead of one per key.

stdin:  {"set": [[key, value, force], ...], "ui_meta_bots": {...} | null}
stdout: one `set <key>` line per changed key; `unchanged` when nothing changed. Exit 1 on the first failed write.

The pure helpers (current, same, changed_keys, merge_ui_meta) are also imported by squadctl.py for dry-run diffs.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path


def current(cfg: dict, key: str):
    node = cfg
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def as_cli(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


def same(cur, wanted) -> bool:
    if wanted == "" and cur is None:  # an unset key already means "inherit"
        return True
    if isinstance(wanted, list) and isinstance(cur, str) and cur.strip().startswith("["):
        with contextlib.suppress(ValueError):
            cur = json.loads(cur)
    return cur == wanted


def changed_keys(cfg: dict, sets: list) -> list[tuple]:
    """[(key, old, new, force)] for every wanted key whose live value differs."""
    return [(k, current(cfg, k), v, bool(f)) for k, v, f in sets if not same(current(cfg, k), v)]


def merge_ui_meta(data: dict | None, meta: dict) -> dict | None:
    """Same on-disk shape the Desktop Bots pane writes (tui_gateway/methods_profiles._configure_ui_meta):
    ui_meta.hermes-bots merged key-wise plus a bumped _ui_meta_revisions counter so open clients refetch.
    Returns the new profile.yaml mapping, or None when nothing changes."""
    data = dict(data or {})
    ui = data.get("ui_meta") if isinstance(data.get("ui_meta"), dict) else {}
    cur = ui.get("hermes-bots") if isinstance(ui.get("hermes-bots"), dict) else {}
    merged = {**cur, **meta}
    if merged == cur:
        return None
    data["ui_meta"] = {**ui, "hermes-bots": merged}
    revs = data.get("_ui_meta_revisions") if isinstance(data.get("_ui_meta_revisions"), dict) else {}
    data["_ui_meta_revisions"] = {**revs, "hermes-bots": int(revs.get("hermes-bots", 0)) + 1}
    return data


def main() -> int:
    import hermes_yaml as yaml  # the Hermes runtime's YAML module (PyYAML is not installed there)
    from hermes_cli.config import get_config_path, set_config_value

    plan = json.load(sys.stdin)
    path = get_config_path()
    cfg = (yaml.safe_load(path.read_text()) if path.is_file() else None) or {}
    changed = []
    for key, _old, value, force in changed_keys(cfg, plan.get("set", [])):
        sink = io.StringIO()
        try:
            with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
                set_config_value(key, as_cli(value), force=force)
        except SystemExit as exc:
            print(f"FAILED {key}: {sink.getvalue().strip() or exc}")
            return 1
        changed.append(key)

    meta = plan.get("ui_meta_bots")
    if meta is not None:
        from utils import atomic_yaml_write

        profile_yaml = Path(os.environ["HERMES_HOME"]) / "profile.yaml"
        data = (yaml.safe_load(profile_yaml.read_text()) if profile_yaml.is_file() else None) or {}
        merged = merge_ui_meta(data, meta)
        if merged is not None:
            atomic_yaml_write(profile_yaml, merged, sort_keys=False)
            changed.append("ui_meta.hermes-bots")

    print("\n".join(f"set {k}" for k in changed) if changed else "unchanged")
    return 0


if __name__ == "__main__":
    if {"-h", "--help"} & set(sys.argv[1:]):
        print((__doc__ or "").strip())
        sys.exit(0)
    sys.exit(main())
