"""Fake hermes utils."""
import os

import yaml


def atomic_yaml_write(path, data, *, sort_keys=False, **_):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=sort_keys)
    os.replace(tmp, path)
