# Bot-to-bot messaging

## Direct messages

- Every canonical Bot Chat carries the `message_agent` tool: a bot messages a
  teammate by profile name or title and the message arrives attributed in the
  teammate's Bot Chat (`website/docs/user-guide/bot-mode.md`).
- Delivery is fire-and-forget: the sender gets a queued acknowledgement, and the
  reply or a typed failure reason arrives as a completion notification
  (`website/docs/user-guide/bot-mode.md`).
- The tool exists only in canonical Bot Chat sessions on Bot-Mode-managed
  installs (`bot-mode-and-desktop.md` -> Bot Mode); regular chats, room member
  sessions and CLI sessions never see it.
- The teammate roster (names and roles from each profile's title and
  description) is part of every Bot Chat's system prompt
  (`website/docs/user-guide/bot-mode.md`).
- `kanban_comment` wakes nobody; bot chat is the channel for questions and
  hand-offs that must wake a bot (`docs/decisions.md` D-025).
- Silence tokens: `gateways-and-messaging.md` -> Messaging platforms.

## Group chats

- A group chat room (2-6 bots) is one visible conversation where your message
  triggers up to three serial rounds of member turns; @-mentions scope the round
  (`website/docs/user-guide/bot-mode.md`).
- Bots pull each other in with `@name` and escalate to the human with `@user`;
  hard caps (10 messages per send, 3 rounds) keep rooms from spinning.
- Each member keeps its own room session; group settings can compress one
  member's history at a time.

## Across machines

- Gateways registered under Settings > Connections are relay lines: rosters
  propagate and `message_agent` reaches remote bots while a Desktop that knows
  both connections runs (`website/docs/user-guide/bot-mode.md`).
- Without a Desktop, register a peer gateway: `hermes peer add <name> --url
  <api-server-url> --key <API_SERVER_KEY>`; the peer must run the `api_server`
  platform (`hermes peer --help`).
- Failed deliveries carry reason codes such as `provider_rate_limit`,
  `target_busy` and `delivery_timeout` (`website/docs/user-guide/bot-mode.md`).
