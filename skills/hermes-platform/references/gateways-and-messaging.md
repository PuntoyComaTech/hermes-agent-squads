# Gateways and messaging

## The gateway

- The gateway runs scheduled jobs, the kanban dispatcher
  (`kanban.dispatch_in_gateway`) and the messaging platforms.
  In squads it is the only
  always-on service.
- One gateway can serve many profiles (multiplexing), each with its own
  channels and Bot Chat.

## Messaging platforms

- One gateway connects Telegram, Discord, Slack, WhatsApp, email and more; the
  platform index is `website/docs/user-guide/messaging/index.md`, one page per
  platform beside it.
- Silence tokens (`[SILENT]`, `SILENT`, `NO_REPLY`, `NO REPLY`) must be the whole
  final response. They stay silent only on machinery turns or when no reply is
  expected; a human turn gets a short notice.
  Cron delivery has its own `[SILENT]` rule: `cron-and-gates.md`.
- Session internals: `website/docs/developer-guide/gateway-session-lifecycle.md`.

## Delivery targets

- `--deliver` grammar and squad delivery: `cron-and-gates.md` -> Delivery and
  silence. Kanban notifications use `hermes kanban notify-subscribe` instead.
- Managers are the only bots the user talks to.
