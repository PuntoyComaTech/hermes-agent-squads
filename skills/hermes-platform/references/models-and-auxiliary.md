# Models and auxiliary slots

## Contents

Per-profile model; Providers and the models cache; Credential pools; Prompt cache; Auxiliary slots;
Vision.

## Per-profile model

- Each profile has `model.provider`, `model.default` and `agent.reasoning_effort`.
- Effort levels: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`, `ultra`; empty means
  `medium`. Other strings are rejected.
- Default effort is per profile. `agent.reasoning_overrides` maps a model id to an effort; set it with
  `hermes config set 'agent.reasoning_overrides.<model id with dots escaped as \.>' <level>` or in
  `config.yaml`. Cron jobs take `--reasoning-effort`. `kanban create` has no effort flag: per-card
  depth is writable only through the kanban dashboard's `reasoning_effort` field, so from the CLI a
  lane that needs another effort gets its own profile.
- `hermes model` picks provider, model and effort; `hermes model --refresh` re-fetches every
  provider's model list. In a session, `/model <name> --reasoning <level>` switches, `--global`
  persists it.

## Providers and the models cache

- `$HERMES_HOME/provider_models_cache.json` caches each authed provider's model list.
- `scripts/model_advisor.py` reads that cache and `scripts/data/model-roles.yaml` to suggest one model
  per bot; model ids live only in that data file and the builder profile's `local/installed.yaml`.
- Credentials per profile: `.env` is read only from the profile's own `HERMES_HOME`. A profile with no
  `auth.json` entry for a provider reads the root `auth.json`; a token refresh done in any profile is
  written back to the root, and a profile's own `auth add` takes precedence.
- Provider plugins: bundled ones (`plugins/model-providers/`, for example `opencode-zen`, which
  registers `opencode-go`) load in every profile; a user-installed one under `$HERMES_HOME/plugins/`
  loads only in that profile. Squad tooling copies the builder's provider plugin into each bot that
  uses it.
- Fallback chain: top-level `fallback_providers: [{provider, model}]`, tried in order when the primary
  fails (rate limit, quota, auth, connection) and restored on the next turn. On a switch Hermes
  re-resolves the effort from `agent.reasoning_overrides`, else `agent.reasoning_effort`. Pinned cron
  jobs never use it (`cron-and-gates.md`); children use `delegation.fallback_providers` when declared
  (`delegation.md`). Squad tooling writes the chain from the models file's top-level `fallback:` list,
  the same chain for every bot; no `fallback:` key keeps the saved chain, `fallback: []` clears it.
- Providers: `website/docs/integrations/providers.md`; fallback and routing:
  `website/docs/user-guide/features/fallback-providers.md`,
  `website/docs/user-guide/features/provider-routing.md`.

## Credential pools

- A pool holds several keys or OAuth logins for one provider:
  `hermes -p <bot> auth add <provider> [--type api-key|oauth] [--priority 0]`,
  `hermes auth list [<provider>]`, `hermes auth remove|reset|priority|status|refresh|logout`.
  Numbered env siblings (`<NAME>_API_KEY_2`, `_3`, ...) join the pool with no command; a custom
  endpoint's pool is keyed `custom:<name>`.
- On 429 (second in a row), 402, or a failed OAuth refresh Hermes rotates to the next pool entry. The
  fallback chain runs only after every entry is exhausted.
- `credential_pool_strategies: {<provider>: fill_first|round_robin|least_used|random}` in
  `config.yaml`; default `fill_first` (by `priority`).
- Children of `delegate_task` on the parent's provider share its pool; on another provider they load
  that provider's pool.
- A rotation starts on a key with no prompt cache: the next request pays full input price.
- Two logins of the same OpenAI account add no quota; pool different accounts.
- `scripts/model_advisor.py` counts a provider listed by `hermes auth list` as available, pool-only
  ones included.

## Prompt cache

- `prompt_caching.cache_ttl`: `5m` (default), `1h` or `auto`; applies to Claude via Anthropic,
  OpenRouter and Nous Portal.
- `auto` = `1h` for sessions a person types into, `5m` for machine-paced ones (kanban workers, cron,
  subagents, one-shots, webhooks, API server).
- `1h` writes cost 2x base input (`5m`: 1.25x) and pay off only when turns are more than 5 minutes
  apart. Squad workers and cron bots keep `5m`; a manager the user chats with through the day can use
  `auto`.
- Delegated children always use `5m`.

## Auxiliary slots

- Background tasks have their own `auxiliary.<task>.provider` / `.model` / `.reasoning_effort` keys.
  `provider: auto` tries the main model, then the slot's `fallback_chain`, then `fallback_providers`;
  it never borrows another logged-in provider while a main provider is set.
- `auxiliary.background_review.reasoning_effort` applies only when the review is routed to another
  model; a same-model review inherits the parent's effort.
- squadctl routes each slot one way:
  - `aux` lane: `title_generation`, `goal_judge`, `curator`, `compression`, `kanban_decomposer`,
    `triage_specifier`, `background_review`, `profile_describer`, `memory_query_rewrite`, `approval`,
    `review`, `skills_hub`, `monitor`.
  - `vision` lane: `vision` (text-only main models only; see Vision).
  - Main model: `mcp`, `tts_audio_tags`, `voice_chat`, `moa_reference`, `moa_aggregator`.
- Read a profile's live slots with `hermes -p <bot> config get auxiliary`.

## Vision

- A text-only main model keeps its profile and gets `auxiliary.vision` instead of a model change. The
  `vision` lane must accept images (`scripts/data/model-roles.yaml`).
- An explicit `auxiliary.vision` provider or model also sends images from a vision-capable main model
  through the description path under `agent.image_input_mode: auto`. `image_input_mode: text` keeps
  pixels out of the main model entirely; `model.supports_vision: true` marks a custom endpoint as
  vision-capable.
