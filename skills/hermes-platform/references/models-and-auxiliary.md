# Models and auxiliary slots

## Contents

- [Per-profile model](#per-profile-model)
- [Providers and the models cache](#providers-and-the-models-cache)
- [Auxiliary slots](#auxiliary-slots)
- [Vision](#vision)

## Per-profile model

- Each profile has `model.provider` and `model.default`, plus
  `agent.reasoning_effort` (`website/docs/user-guide/configuration.md`;
  `website/docs/user-guide/configuring-models.md`).
- A kanban card's `--model`/`--provider` override changes only the model; the
  profile's reasoning effort still applies, so a lane needing another effort
  gets its own profile (`website/docs/user-guide/features/kanban.md`,
  "Per-task model override"; `docs/decisions.md` V-07).
- Model switching and the picker: `hermes model` (`website/docs/user-guide/configuring-models.md`).

## Providers and the models cache

- Authenticated providers and their model catalogs are resolved by the runtime
  provider system (`website/docs/integrations/providers.md`).
- `$HERMES_HOME/provider_models_cache.json` caches each authed provider's model
  list (`hermes_cli/models.py`, `_provider_models_cache_path`).
- `scripts/model_advisor.py` reads that cache and `scripts/data/model-roles.yaml`
  (lanes → family regex candidates → provider preference) to suggest one model
  per bot; model ids live only in that data file and `local/installed.yaml`
  (`scripts/model_advisor.py`; `docs/decisions.md` V-08).
- Fallback and routing: `website/docs/user-guide/features/fallback-providers.md`
  and `website/docs/user-guide/features/provider-routing.md`.

## Auxiliary slots

- Background tasks (title generation, compression, curator, goal judge, kanban
  decomposer, triage specifier and more) have their own
  `auxiliary.<task>.provider/model` keys and default to the main model when
  unset (`website/docs/user-guide/configuration.md`; `scripts/squadctl.py`,
  `AUX_TASKS`).
- Squad tooling points every auxiliary slot at the cheap `aux` lane so heavy
  sessions do not burn the main model (`scripts/squadctl.py`;
  `scripts/data/model-roles.yaml`).

## Vision

- A text-only main model keeps its profile and gets `auxiliary.vision` instead
  of a model change (`docs/decisions.md` D-021;
  `website/docs/user-guide/features/vision.md`).
- The `vision` lane must be a model that accepts images
  (`scripts/data/model-roles.yaml`).
