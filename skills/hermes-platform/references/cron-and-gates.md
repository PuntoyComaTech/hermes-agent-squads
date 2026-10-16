# Cron and gates

## Creating jobs

- `hermes cron create <schedule> [prompt]` accepts `30m`, `every 2h` or a cron
  expression like `0 9 * * *` (`hermes cron create --help`).
- `--script <file>`: a relative path resolves under `<HERMES_HOME>/scripts/` of
  the profile; `.sh`/`.bash` run via bash, everything else via Python
  (`hermes cron create --help`; `cron/scheduler_script.py`).
- `--no-agent` skips the LLM: the script is the job, its stdout is delivered
  verbatim, and empty stdout is silent (`website/docs/guides/cron-script-only.md`).
- Agent jobs can pin `--model`, `--provider`, `--reasoning-effort` and attach
  `--skill` (repeatable) (`hermes cron create --help`).
- `--monitor-script` runs a cheap script before the agent and skips the run when
  its output is unchanged (exact-bytes hash); incompatible with `--no-agent`
  (`hermes cron create --help`).
- Agent cron runs get the toolsets in `platform_toolsets.cron`
  (`website/docs/user-guide/features/cron.md`).

## Gates and wakeAgent

- With `--script` and an agent, the full stdout is prepended to the prompt as
  `## Script Output`; empty stdout skips the agent
  (`cron/scheduler_prompt.py`).
- A last stdout line of `{"wakeAgent": false}` skips the agent for that tick;
  any other last line wakes it (`website/docs/user-guide/features/cron.md`,
  "Skipping the agent entirely: wakeAgent").
- Every agent cron in a squad gets a gate script so quiet ticks spend no tokens
  (`scripts/gate_lib.py`).

## Delivery and silence

- `--deliver` targets: `origin`, `local`, a platform name, `platform:chat_id` or
  `bot-chat[:profile]` (inject output into a profile's canonical Bot Chat)
  (`hermes cron create --help`). Squad crons deliver to `bot-chat:<manager>`
  (`scripts/squadctl.py`; `docs/decisions.md` V-05).
- `--failure-deliver` overrides the target for failure notices only; `local`
  suppresses them (`hermes cron create --help`).
- `[SILENT]` in a successful agent response suppresses delivery; the output is
  still saved under `~/.hermes/cron/output/`. Failed jobs always deliver
  (`website/docs/user-guide/features/cron.md`).
- Troubleshooting: `website/docs/guides/cron-troubleshooting.md`; internals:
  `website/docs/developer-guide/cron-internals.md`.
