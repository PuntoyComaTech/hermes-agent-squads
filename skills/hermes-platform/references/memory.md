# Memory

## Built-in memory

- Two files per profile under `<HERMES_HOME>/memories/`: `MEMORY.md` (the bot's notes: environment
  facts, conventions, lessons) and `USER.md` (the user's preferences). The bot writes them with the
  `memory` tool (`add`, `patch`, `remove`, or one `operations` batch).
- Every call names a top-level `target` (`memory` or `user`). There is no `replace` action; `patch`
  replaces one span and its `old_text` must occur exactly once in the entry. Writes are scanned for
  injection and exfiltration and blocked on a match; an exact duplicate is a no-op.
- Both load into the system prompt as a snapshot frozen at session start. A write lands on disk at
  once and reaches the prompt in the next session.
- Limits: `memory.memory_char_limit` (2200) and `memory.user_char_limit` (1375). Memory never
  auto-compacts: a write over the limit fails and the bot must remove or shorten entries in the same
  batch.
- Memory is per profile; `profile create --clone` copies both files. Two processes on one
  `HERMES_HOME` write into each other's memory; bots that must share memory use an external provider.
- A fact needed on every run of one job belongs in a skill, not in memory.

## Background review

- A background review writes memory after turns, every `memory.nudge_interval` turns (default 10). It
  runs on the main model unless `auxiliary.background_review` routes it elsewhere; that block also
  takes `enabled`, `max_input_tokens` and `defer`.

## Keys

| Key | Default | Effect |
|---|---|---|
| `memory.memory_enabled` | `true` | `false` rejects `MEMORY.md` writes |
| `memory.user_profile_enabled` | `true` | `false` rejects `USER.md` writes |
| `memory.write_approval` | `false` | `true` stages writes outside the interactive CLI; review with `/memory pending`, `/memory approve <id>\|all`, `/memory reject <id>\|all` |
| `memory.nudge_interval` | `10` | Turns between background reviews |
| `memory.provider` | unset | The one active external provider |
| `memory.prefetch_spill_enabled` | `false` | `true` replaces oversized external recall with a preview and a file path |

- `memory_enabled: false` alone keeps the tool, scoped to `user`. Both `*_enabled: false` removes the
  `memory` tool and its prompt block; an external provider keeps its own tools. `memory` in
  `agent.disabled_toolsets` also hides the provider's tools.
- Squad manifests: `memory: false` on a bot sets both `*_enabled` keys to `false`; otherwise squad
  tooling sets them `true` and adds the `memory` toolset.

## External providers

- One external provider is active at a time, always alongside the built-in files. Bundled:
  `retaindb`, `byterover`. Catalog plugins: `honcho`, `hindsight`, `mem0`, `supermemory`,
  `openviking`, `holographic`.
- Install a catalog provider per profile, then select it: `hermes -p <bot> plugins install <name>`
  and `hermes -p <bot> memory setup` (or `hermes -p <bot> config set memory.provider <name>`).
  `hermes plugins enable <name>` does not select a memory provider.
- `hermes memory status` shows the active provider; `hermes memory off` returns to built-in only;
  `hermes memory reset` erases `MEMORY.md` and `USER.md`.
- Provider settings live in the plugin's own files (for example `$HERMES_HOME/hindsight/config.json`)
  and keys in `.env`, never in squad manifests.
- Details per provider: `website/docs/user-guide/features/memory-providers.md`.
