# Tool search and connectors

## Contents

- [Tool search](#tool-search)
- [Connectors](#connectors)
- [Squad usage](#squad-usage)

## Tool search

- Tool search defers rarely used tools out of the always-on prompt and loads
  them on demand, cutting prompt cost without removing capability
  (`website/docs/user-guide/features/tool-search.md`).

## Connectors

- Connectors are hosted app accounts Hermes reaches through the Nous tool
  gateway: `hermes connectors list|accounts|connect|rename|disconnect`
  (`website/docs/reference/cli-commands.md#hermes-connectors`).
- A connected account exposes that app to bots; `tools.connectors.enabled`
  turns the surface on or off for a profile
  (`website/docs/user-guide/features/tool-search.md`).
- Architecture: `website/docs/user-guide/features/tool-gateway.md`.

## Squad usage

- Squad manifests declare `connectors: {enabled: false, suggest: [...]}`; the
  suggest list is a note in the apply output, and the user connects apps in the
  browser with `hermes connectors connect <app>` (`scripts/squadctl.py`;
  `squads/_schema/squad.schema.json`).
- Give a connector to exactly the bot that calls that app; web-reading bots hold
  no credentials (`docs/decisions.md` D-030).
