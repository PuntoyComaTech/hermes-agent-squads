"""Fake hermes_yaml: the Hermes runtime ships ruamel; the test venv has PyYAML."""
from yaml import safe_dump, safe_load  # noqa: F401
