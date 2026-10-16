# Models and auxiliary slots

## Per-profile model

- Each profile has `model.provider`, `model.default` and
  `agent.reasoning_effort` (`website/docs/user-guide/configuration.md`;
  `website/docs/user-guide/configuring-models.md`).
- Default effort is per profile. `agent.reasoning_overrides` maps a model name
  to an effort (config.yaml only, no CLI) and cron jobs take
  `--reasoning-effort` (`hermes_cli/config_defaults.py`; `hermes cron create
  --help`). `kanban create` has no effort flag, so a lane that needs another
  effort gets its own profile (`docs/decisions.md` V-07).
- `hermes model` picks provider and model; `hermes model --refresh` re-fetches
  every provider's model list (`hermes model --help`).

## Providers and the models cache

- `$HERMES_HOME/provider_models_cache.json` caches each authed provider's model
  list (`hermes_cli/models.py`, `_provider_models_cache_path`).
- `scripts/model_advisor.py` reads that cache and `scripts/data/model-roles.yaml`
  to suggest one model per bot; model ids live only in that data file and the
  builder profile's `local/installed.yaml` (`docs/decisions.md` V-08).
- Credentials per profile: `.env` is read only from the profile's own
  `HERMES_HOME` (`hermes_cli/env_loader.py`, `load_hermes_dotenv`); the root
  `auth.json` is a read-only fallback per provider while the profile has no
  entry for it (`hermes_cli/auth.py`, `_load_provider_state`,
  `read_credential_pool`).
- Provider plugins: bundled ones (`plugins/model-providers/`, for example
  `opencode-go`) load in every profile; a user-installed one under
  `$HERMES_HOME/plugins/` loads only in that profile
  (`website/docs/developer-guide/model-provider-plugin.md`;
  `providers/__init__.py`, `_scan_home_layer`). Squad tooling copies the
  builder's provider plugin into each bot that uses it (`scripts/squadctl.py`,
  `provider_plugin`).
- Providers: `website/docs/integrations/providers.md`; fallback and routing:
  `website/docs/user-guide/features/fallback-providers.md`,
  `website/docs/user-guide/features/provider-routing.md`.

## Auxiliary slots

- Background tasks have their own `auxiliary.<task>.provider` / `.model` keys;
  `provider: auto` inherits the main model (`hermes_cli/config_defaults.py`,
  `auxiliary`).
- Squad tooling points its `AUX_TASKS` set (13 slots) at the `aux` lane and
  `auxiliary.vision` at the `vision` lane; `mcp`, `tts_audio_tags`,
  `voice_chat`, `moa_reference` and `moa_aggregator` keep the main model
  (`scripts/squadctl.py`).

## Vision

- A text-only main model keeps its profile and gets `auxiliary.vision` instead
  of a model change (`docs/decisions.md` D-021). The `vision` lane must accept
  images (`scripts/data/model-roles.yaml`).
- An explicit `auxiliary.vision` provider or model also sends images from a
  vision-capable main model through the description path under
  `agent.image_input_mode: auto` (`website/docs/user-guide/features/vision.md`).
