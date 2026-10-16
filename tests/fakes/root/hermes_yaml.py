"""Fake hermes_yaml: the Hermes runtime ships ruamel; the test venv has PyYAML."""
from yaml import YAMLError, safe_dump, safe_load  # noqa: F401  (the real module re-exports ruamel's YAMLError)
