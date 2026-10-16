# Cron and gates

## Creating jobs

- `hermes cron create <schedule> [prompt]` accepts `30m`, `every 2h` or a cron
  expression like `0 9 * * *`.
- `--script <file>`: a relative path resolves under `<HERMES_HOME>/scripts/` of
  the profile; `.sh`/`.bash` run via bash, everything else via Python.
- `--no-agent` skips the LLM: the script is the job, its stdout is delivered
  verbatim, and empty stdout is silent.
- Agent jobs can pin `--model`, `--provider`, `--reasoning-effort` and attach
  `--skill` (repeatable).
- An agent job without `--model` follows `cron.model`, then the main model, at
  fire time: a later `hermes model` change moves it. `--pin` locks the current
  main model; `hermes cron edit <id> --unpin` releases it. squadctl writes
  `--model/--provider` from the job's lane on every agent job, and `doctor`
  warns on a squad agent job with no pin.
- `--paused` (+ `--paused-reason`) creates the job disabled; `--interpreter`
  runs a `.py` script with another Python; `--continuity` injects the job's
  previous output into each run; `--workdir` loads that directory's
  `AGENTS.md` and uses it as cwd.
- Missed recurring fires inside the grace window run once on catch-up
  (`cron.catch_up_missed`, default true).
- `--monitor-script` runs a cheap script before the agent and skips the run when
  its output is unchanged (exact-bytes hash); incompatible with `--no-agent`.
- Agent cron runs get the toolsets in `platform_toolsets.cron`.

## Gates and wakeAgent

- With `--script` and an agent, the full stdout is prepended to the prompt as
  `## Script Output`; empty stdout skips the agent.
- A last stdout line of `{"wakeAgent": false}` skips the agent for that tick;
  any other last line wakes it.
- Every agent cron in a squad gets a gate script so quiet ticks spend no tokens
  (`scripts/gate_lib.py`).

## Delivery and silence

- `--deliver` targets: `origin`, `local`, a platform name, `platform:chat_id` or
  `bot-chat[:profile]` (inject output into a profile's canonical Bot Chat).
  Squad crons deliver to `bot-chat:<manager>`.
- `--failure-deliver` overrides the target for failure notices only; `local`
  suppresses them.
- `[SILENT]` in a successful agent response suppresses delivery; the output is
  still saved under `~/.hermes/cron/output/`. Failed jobs always deliver.
- `[CRON_FAILURE]` as the exact first line of an agent response marks the run
  failed; the following lines are the failure evidence. A cron skill uses it
  when its check finds a real failure, never to quote the token.
- The same error alerts once, then stays silent for
  `cron.failure_repeat_alert_hours` (default 6) before one reminder; a green
  run or a different error alerts at once. `hermes cron incidents` lists
  them; `hermes cron incidents ack` silences a signature.
- Troubleshooting: `website/docs/guides/cron-troubleshooting.md`; internals:
  `website/docs/developer-guide/cron-internals.md`.
