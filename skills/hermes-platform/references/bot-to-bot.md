# Bot-to-bot messaging

## Direct messages

- Every canonical Bot Chat carries the `message_agent` tool: a bot messages a
  teammate by profile name or title and the message arrives attributed in the
  teammate's Bot Chat.
- Delivery is fire-and-forget: the sender gets a queued acknowledgement, and the
  reply or a typed failure reason arrives as a completion notification.
- The tool exists only in canonical Bot Chat sessions on Bot-Mode-managed
  installs (`bot-mode-and-desktop.md` -> Bot Mode), including a Bot Chat opened
  with `hermes -p <bot> chat`; regular chats and room member sessions never see
  it.
- The teammate roster (names and roles from each profile's title and
  description) is part of every Bot Chat's system prompt.
- `kanban_comment` wakes nobody; bot chat is the channel for questions and
  hand-offs that must wake a bot.
- Silence tokens: `gateways-and-messaging.md` -> Messaging platforms.

## Group chats

- A group chat room (2-6 bots) is one visible conversation where your message
  triggers up to three serial rounds of member turns; @-mentions scope the round.
- Bots pull each other in with `@name` and escalate to the human with `@user`;
  hard caps (10 messages per send, 3 rounds) keep rooms from spinning.
- Each member keeps its own room session; group settings can compress one
  member's history at a time.

## Across machines

- Gateways registered under Settings > Connections are relay lines: rosters
  propagate and `message_agent` reaches remote bots while a Desktop that knows
  both connections runs.
- Without a Desktop, register a peer gateway: `hermes peer add <name> --url
  <api-server-url> --key <API_SERVER_KEY>`; the peer must run the `api_server`
  platform.
- Failed deliveries carry reason codes such as `provider_rate_limit`,
  `target_busy` and `delivery_timeout`.
