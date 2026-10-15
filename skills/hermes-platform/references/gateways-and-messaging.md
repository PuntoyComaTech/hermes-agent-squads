# Gateways and messaging

## The gateway

- The gateway runs scheduled jobs, the kanban dispatcher
  (`kanban.dispatch_in_gateway`) and the messaging platforms
  (`website/docs/developer-guide/gateway-internals.md`;
  `website/docs/user-guide/features/kanban.md`). In squads it is the only
  always-on service (`docs/decisions.md` D-020).
- One gateway can serve many profiles (multiplexing), each with its own
  channels and Bot Chat (`website/docs/user-guide/multi-profile-gateways.md`;
  `website/docs/developer-guide/multiplexing-gateway.md`).

## Messaging platforms

- One gateway connects Telegram, Discord, Slack, WhatsApp, email and more; the
  platform index is `website/docs/user-guide/messaging/index.md`, one page per
  platform beside it.
- Silence tokens (`[SILENT]`, `SILENT`, `NO_REPLY`, `NO REPLY`) must be the whole
  final response. They stay silent only on machinery turns or when no reply is
  expected; a human turn gets a short notice
  (`website/docs/user-guide/messaging/index.md`, "Intentional Silence Tokens").
  Cron delivery has its own `[SILENT]` rule: `cron-and-gates.md`.
- Session internals: `website/docs/developer-guide/gateway-session-lifecycle.md`.

## Delivery targets

- `--deliver` grammar and squad delivery: `cron-and-gates.md` -> Delivery and
  silence. Kanban notifications use `hermes kanban notify-subscribe` instead.
- Leads are the only bots the user talks to (`docs/decisions.md` V-02).
