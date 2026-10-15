# Bot-to-bot messaging

## Contents

- [Direct messages](#direct-messages)
- [Silence](#silence)
- [Group chats](#group-chats)
- [Across machines](#across-machines)

## Direct messages

- Every canonical Bot Chat carries the `message_agent` tool: a bot messages a
  teammate by profile name or title and the message arrives attributed in the
  teammate's Bot Chat (`website/docs/user-guide/bot-mode.md`).
- Delivery is fire-and-forget: the sender gets a queued acknowledgement and the
  outcome (reply or typed failure reason) arrives as a completion notification
  (`website/docs/user-guide/bot-mode.md`).
- The tool exists only in canonical Bot Chat sessions on Bot-Mode-managed
  installs; regular chats, room member sessions and CLI sessions never see it
  (`website/docs/user-guide/bot-mode.md`).
- The teammate roster (names and roles from each profile's title/description) is
  part of every Bot Chat's system prompt
  (`website/docs/user-guide/bot-mode.md`).
- `kanban_comment` wakes nobody; bot chat is the channel for questions and
  hand-offs that must wake a bot (`docs/decisions.md`, D-025).

## Silence

- A bot with nothing to add may end a turn with an intentional silence token
  (`[SILENT]`, `NO_REPLY`, ...); the transcript keeps the turn but renders
  nothing (`website/docs/user-guide/bot-mode.md`;
  `website/docs/user-guide/messaging/index.md`).

## Group chats

- A group chat room (2-6 bots) is one visible conversation where your message
  triggers up to three serial rounds of member turns; @-mentions scope the round
  (`website/docs/user-guide/bot-mode.md`).
- Bots pull each other in with `@name` and escalate to the human with `@user`;
  hard caps (10 messages per send, 3 rounds) keep rooms from spinning
  (`website/docs/user-guide/bot-mode.md`).
- Each member keeps its own persistent room session; group settings can compress
  one member's history at a time (`website/docs/user-guide/bot-mode.md`).

## Across machines

- Registered gateways under Settings → Connections are relay lines; rosters
  propagate automatically and `message_agent` reaches remote bots
  (`website/docs/user-guide/bot-mode.md`).
- For always-on machine-to-machine messaging with no Desktop in the loop,
  register a peer gateway with `hermes peer add` (`website/docs/user-guide/bot-mode.md`).
- Failed deliveries carry machine-readable reason codes (for example
  `provider_rate_limit`, `target_busy`, `delivery_timeout`)
  (`website/docs/user-guide/bot-mode.md`).
