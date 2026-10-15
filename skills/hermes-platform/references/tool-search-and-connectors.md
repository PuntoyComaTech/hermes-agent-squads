# Tool search and connectors

## Contents

- [Tool search](#tool-search)
- [Connectors](#connectors)
- [Squad usage](#squad-usage)

## Tool search

- Tool search defers rarely used tools out of the always-on prompt and loads
  them on demand, cutting prompt cost without removing capability
  (`website/docs/user-guide/features/tool-search.md`).
- Deferred tools are discovered through the tool-search tool rather than being
  listed in full in every request (`website/docs/user-guide/features/tool-search.md`).

## Connectors

- Connectors are the app accounts Hermes uses through Nous Portal:
  `hermes connectors list|accounts|connect|rename|disconnect` (`hermes
  connectors --help`).
- A connected account exposes that app to bots through the connector tooling;
  `tools.connectors.enabled` turns the surface on or off for a profile
  (`scripts/squadctl.py`; `website/docs/user-guide/features/tool-search.md`).
- Connector plumbing for plugin authors:
  `website/docs/developer-guide/relay-connector-contract.md`.

## Squad usage

- Squad manifests declare `connectors: {enabled: false, suggest: [...]}`; the
  suggest list is shown to the user at apply time and connected only after
  their OK (`squads/_schema/squad.schema.json`; `scripts/squadctl.py`).
- Give a connector to exactly the bot that calls that app; web-reading bots hold
  no credentials (`docs/decisions.md`, D-006; plan guardrails).
- Account connections happen in the user's browser; bots never type passwords
  (`hermes connectors connect --help`; `README.md`).
