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
    cfg = (yaml.safe_load(path.read_text()) if path.is_file() else None) or {}
    node = cfg
    *parents, leaf = key.split(".")
    for part in parents:
        node = node.setdefault(part, {})
    node[leaf] = _coerce(value)
    path.write_text(yaml.safe_dump(cfg, sort_keys=False))
