# Cron and gates

## Contents

- [Creating jobs](#creating-jobs)
- [Script mode and gates](#script-mode-and-gates)
- [wakeAgent](#wakeagent)
- [Delivery and silence](#delivery-and-silence)

## Creating jobs

- `hermes cron create <schedule> [prompt]` accepts `30m`, `every 2h` or a cron
  expression like `0 9 * * *` (`hermes cron create --help`).
- `--script <file>`: relative paths resolve under `<HERMES_HOME>/scripts/`
  (the profile home); `.sh`/`.bash` run via bash, everything else via Python
  (`hermes cron create --help`).
- `--no-agent` skips the LLM entirely: the script is the job and its stdout is
  delivered verbatim; empty stdout is silent
  (`hermes cron create --help`; `website/docs/guides/cron-script-only.md`).
- Agent jobs can pin `--model`, `--provider`, `--reasoning-effort` and attach
  `--skill` (`hermes cron create --help`).
- `--monitor-script` runs a cheap source script before the agent and suppresses
  the run when its output is unchanged by exact-bytes hash
  (`hermes cron create --help`).

## Script mode and gates

- With `--script` and an agent, script stdout is injected into the prompt each
  run (`hermes cron create --help`).
- Every agent cron in a squad gets a gate script so quiet ticks spend no tokens
  (`scripts/gate_lib.py`).

## wakeAgent

- A gate script prints `{"wakeAgent": false}` as its last line to skip the agent
  for that tick; omitting the key means wake as usual
  (`website/docs/user-guide/features/cron.md`, "Skipping the agent entirely:
  wakeAgent").
- Any other last line wakes the agent; the full stdout is prepended as
  `## Script Output`. Empty stdout skips the agent
  (`website/docs/user-guide/features/cron.md`).

## Delivery and silence

- `--deliver` targets: `origin`, `local`, a messaging platform, `platform:chat_id`
  or `bot-chat[:profile]` (inject output into a profile's canonical Bot Chat)
  (`hermes cron create --help`).
- `[SILENT]` in a successful agent response suppresses delivery; the output is
  still saved under `~/.hermes/cron/output/`. Failed jobs always deliver
  (`website/docs/user-guide/features/cron.md`).
- `--failure-deliver` overrides the target for failure notices only
  (`hermes cron create --help`).
- Troubleshooting: `website/docs/guides/cron-troubleshooting.md`;
  internals: `website/docs/developer-guide/cron-internals.md`.
