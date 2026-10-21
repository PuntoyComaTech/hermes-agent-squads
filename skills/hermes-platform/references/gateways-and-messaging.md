# Gateways and messaging

## The gateway

- The gateway runs scheduled jobs, the kanban dispatcher (`kanban.dispatch_in_gateway`) and the
  messaging platforms. In squads it is the only always-on service.
- One gateway serves many profiles: `gateway.multiplex_profiles` defaults to true, and
  `hermes -p <name> gateway run` attaches the profile to the host gateway instead of starting another.
- `hermes gateway run|start|stop|restart|status|install|uninstall|list|setup`; `list` shows every
  profile's gateway state.

## Messaging platforms

- One gateway connects Telegram, Discord, Slack, WhatsApp, email and more; the platform index is
  `website/docs/user-guide/messaging/index.md`, one page per platform beside it.
- The gateway denies every user who is not in an allowlist (`<PLATFORM>_ALLOWED_USERS`,
  `GATEWAY_ALLOWED_USERS`) or paired by DM (`hermes pairing approve|list|revoke <platform>`).
  `GATEWAY_ALLOW_ALL_USERS=true` is unsafe on a bot with terminal access.
- Silence tokens (`[SILENT]`, `SILENT`, `NO_REPLY`, `NO REPLY`) must be the whole final response. They
  stay silent on internal wakes, heartbeat turns and messages not addressed to the bot; a human turn
  addressed to the bot gets a short notice instead. Cron delivery has its own `[SILENT]` rule:
  `cron-and-gates.md`.
- Session internals: `website/docs/developer-guide/gateway-session-lifecycle.md`.

## Delivery targets

- `--deliver` grammar and squad delivery: `cron-and-gates.md` -> Delivery and silence. Kanban
  notifications use `hermes kanban notify-subscribe` instead.
- A gateway chat can create cards only when `kanban` is in that platform's
  `platform_toolsets.<platform>` (`toolsets.md`).
- Managers are the only bots the user talks to.
