"""Fake hermes_cli.auth: the provider registry squadctl reads the API-key env var names from.

One provider per lane of the test fleet (`prov-design-pro` -> `PROV_DESIGN_PRO_API_KEY`), the shape the real
`ProviderConfig.api_key_env_vars` exposes for both built-in and plugin-registered providers.
"""
from types import SimpleNamespace

LANES = ("manager", "frontend", "design-pro", "code-complex", "code-routine", "review", "deploy", "research", "digest",
         "aux", "vision")

PROVIDER_REGISTRY = {
    f"prov-{lane}": SimpleNamespace(id=f"prov-{lane}", api_key_env_vars=(f"PROV_{lane.upper().replace('-', '_')}_API_KEY",))
    for lane in LANES
}
# An external-process / OAuth provider declares no API-key env var (claude-subscription shape).
PROVIDER_REGISTRY["prov-keyless"] = SimpleNamespace(id="prov-keyless", api_key_env_vars=())
