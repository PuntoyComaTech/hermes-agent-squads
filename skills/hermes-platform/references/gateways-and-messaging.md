# Gateways and messaging

## Contents

- [The gateway](#the-gateway)
- [Messaging platforms](#messaging-platforms)
- [Multiple profiles and machines](#multiple-profiles-and-machines)
- [Delivery targets](#delivery-targets)

## The gateway

- Squad choice: the gateway is the only always-on service; it serves the
  scheduled jobs, the kanban dispatcher and the messaging platforms
  (`docs/decisions.md` D-020; `website/docs/developer-guide/gateway-internals.md`).

## Messaging platforms

- One gateway connects Telegram, Discord, Slack, WhatsApp, email and more; the
  catalog of platform pages is `website/docs/user-guide/messaging/index.md`.
- Silence tokens (`[SILENT]`, `NO_REPLY`, ...) stay silent only on machinery
  turns or when no reply is expected; a human turn gets a notice
  (`website/docs/user-guide/messaging/index.md`).
- Platform adapters and their quirks: `website/docs/user-guide/messaging/<platform>.md`.

## Multiple profiles and machines

- One gateway can serve many profiles (multiplexing), each with its own
  channels and Bot Chat (`website/docs/user-guide/multi-profile-gateways.md`;
  `website/docs/developer-guide/multiplexing-gateway.md`).

## Delivery targets

- Delivery targets: `cron-and-gates.md`.
- Squads deliver to `bot-chat:<lead>`; leads are the only bots the user talks
  to (`scripts/squadctl.py`; `docs/decisions.md` V-02).
- Messaging internals: `website/docs/developer-guide/gateway-session-lifecycle.md`.
