"""Fake hermes_cli.config: set_config_value writes a dotted key into $HERMES_HOME/config.yaml with CLI coercion."""
import json
import os
from pathlib import Path

import yaml


def get_config_path() -> Path:
    return Path(os.environ["HERMES_HOME"]) / "config.yaml"


def _coerce(value: str):
    if value in ("true", "false"):
        return value == "true"
    try:
        return int(value)
    except ValueError:
        pass
    if value.strip().startswith(("[", "{")):
        return json.loads(value)
    return value


def set_config_value(key: str, value: str, force: bool = False):
    path = get_config_path()
    if not key.strip() or "" in key.split("."):
        raise SystemExit(f"✗ Invalid config key: {key!r} (empty or empty path segment)")
    cfg = (yaml.safe_load(path.read_text()) if path.is_file() else None) or {}
    node = cfg
    *parents, leaf = key.split(".")
    for part in parents:
        child = node.setdefault(part, {})
        if not isinstance(child, dict):
            raise SystemExit(f"✗ Invalid config key: {key!r} ({part} is not a mapping)")
        node = child
    cur = node.get(leaf)
    if isinstance(cur, dict) and not force and not str(value).strip().startswith(("{", "[")):
        raise SystemExit(f"✗ {key} is a mapping section; pass force to replace it with a scalar")
    node[leaf] = _coerce(value)
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
