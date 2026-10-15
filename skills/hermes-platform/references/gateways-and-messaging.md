# Gateways and messaging

## Contents

- [The gateway](#the-gateway)
- [Messaging platforms](#messaging-platforms)
- [Multiple profiles and machines](#multiple-profiles-and-machines)
- [Delivery targets](#delivery-targets)

## The gateway

- The gateway is the only always-on service of a Hermes install; it serves the
  scheduled jobs, the kanban dispatcher and the messaging platforms
  (`website/docs/developer-guide/gateway-internals.md`; `docs/decisions.md` D-020).
- Gateway supervision limits: a bot cannot stop or restart the gateway that
  supervises it (`website/docs/user-guide/security.md`).

## Messaging platforms

- One gateway connects Telegram, Discord, Slack, WhatsApp, email and more; the
  catalog of platform pages is `website/docs/user-guide/messaging/index.md`.
- Intentional silence tokens (`[SILENT]`, `NO_REPLY`, ...) suppress a reply on
  messaging surfaces (`website/docs/user-guide/messaging/index.md`).
- Platform adapters and their quirks: `website/docs/user-guide/messaging/<platform>.md`.

## Multiple profiles and machines

- One gateway can serve many profiles (multiplexing), each with its own
  channels and Bot Chat (`website/docs/user-guide/multi-profile-gateways.md`;
  `website/docs/developer-guide/multiplexing-gateway.md`).
- Bots on different machines message each other through the Desktop relay or a
  registered peer gateway (`website/docs/user-guide/bot-mode.md`).

## Delivery targets

- Cron and kanban output deliver to `origin`, `local`, a platform chat or
  `bot-chat[:profile]`, which injects the output into a profile's canonical Bot
  Chat as a message the bot responds to (`hermes cron create --help`).
- Squads deliver to `bot-chat:<lead>`; leads are the only bots the user talks
  to (`scripts/squadctl.py`; `docs/decisions.md` V-02).
- Messaging internals: `website/docs/developer-guide/gateway-session-lifecycle.md`.
