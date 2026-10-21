# Bot-to-bot messaging

## Direct messages

- Every canonical Bot Chat carries the `message_agent` tool: a bot messages a teammate and the message
  arrives attributed in the teammate's Bot Chat. The gate (title `Bot Chat` plus a Bot-Mode-managed
  install) is in `bot-mode-and-desktop.md` -> Bot Mode; regular chats and room member sessions never
  see the tool.
- Targets resolve by profile name, then friendly name, then `@tag`; `@hermes` is the primary bot, and
  a friendly name two bots share is refused with the roster. Remote targets are `name@connection` or
  `peer/profile`.
- Delivery is fire-and-forget: the sender gets a queued acknowledgement (durable admission, not a
  reply), and the reply or a typed failure reason arrives as a completion notification. Where
  notifications cannot arrive (API server, one-shot runs) the ack says `reply_delivery: poll` and the
  sender calls `process_manage(action="wait", session_id=...)`.
- Messages and replies are capped at 16,000 characters (a longer reply arrives as its tail). The target
  turn is capped at 10 minutes. A failed delivery retries at most once, only for transient failures
  and context overflow; never resend a delivery whose outcome is unknown.
- The teammate roster (names and roles from each profile's title and description) is part of every Bot
  Chat's system prompt.
- `kanban_comment` wakes nobody; bot chat is the channel for questions and hand-offs that must wake a
  bot.
- Silence tokens: `gateways-and-messaging.md` -> Messaging platforms.

## Group chats

- A group chat room (2-6 bots) is one visible conversation where your message triggers up to three
  serial rounds of member turns; @-mentions scope the round.
- Bots pull each other in with `@name` and escalate to the human with `@user`; hard caps (10 messages
  per send, 3 rounds) keep rooms from spinning. `@all` / `@everyone` address the whole room; "stop"
  next to a member's @mention holds that member.
- Each member keeps its own room session; group settings can compress one member's history at a time.

## Across machines

- Gateways registered under Settings > Connections are relay lines: rosters propagate and
  `message_agent` reaches remote bots while a Desktop that knows both connections runs.
- Without a Desktop, register a peer gateway: `hermes peer add <name> --url <api-server-url> --key
  <API_SERVER_KEY>`; the peer must run the `api_server` platform. `hermes peer
  list|set|remove|dm|run|status|stop` manage peers; links are direct, so a laptop can dial a VPS but
  not the reverse.
- Failed deliveries carry `[reason: <code>]`: `provider_auth_or_access`, `provider_quota_limit`,
  `provider_rate_limit`, `provider_server_error`, `context_overflow`, `missing_config`,
  `model_unavailable`, `runtime_offline`, `queued_expired`, `delivery_timeout`, `target_busy`,
  `unknown`.
