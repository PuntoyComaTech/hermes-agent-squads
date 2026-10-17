"""Fake of hermes_cli/tools_config.py: the toolsets a profile with no platform_toolsets gets on `cli`.

A copy of the real `_get_platform_tools({}, "cli")` (Hermes v0.22); tests/test_contracts.py checks it against the
installed Hermes when one is on PATH.
"""

DEFAULT_CLI = frozenset("""
browser clarify code_execution computer_use connections cronjob delegation file image_gen memory session_search
skills terminal todo tts vision web
""".split())


def _get_platform_tools(config, platform, *, include_default_mcp_servers=True):
    assert platform == "cli" and not config
    return set(DEFAULT_CLI)
