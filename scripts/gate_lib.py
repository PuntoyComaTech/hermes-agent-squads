#!/usr/bin/env python3
"""Cron wake-gate helpers: zero LLM cost when there is nothing to do.

Hermes runs a cron --script BEFORE the agent (cron/scheduler_prompt.py):
  empty stdout                            the agent is skipped
  last non-empty line {"wakeAgent": false} the agent is skipped
  anything else                           the agent runs, with the full stdout prepended as `## Script Output`
A gate prints exactly one JSON line, which is also the wake decision.

Import it from a gate script (`from gate_lib import changed, emit, guarded, fingerprint`), or pipe JSON into
`gate_lib.py changed <gate>` / `gate_lib.py fingerprint` from the shell.

State lives in $HERMES_HOME/local/state/gate_<gate>.json (override with --state-dir or GATE_STATE_DIR).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path


def default_home() -> Path:
    return Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes" / "profiles" / "builder")


def state_dir(override: str | Path | None = None) -> Path:
    return Path(override or os.environ.get("GATE_STATE_DIR") or default_home() / "local" / "state")


def fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def load_state(name: str, directory: str | Path | None = None) -> dict:
    path = state_dir(directory) / f"{name}.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(name: str, data: dict, directory: str | Path | None = None) -> None:
    """Atomic write: a crash between truncate and write must not lose the last fingerprint."""
    path = state_dir(directory) / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def changed(gate: str, fp: str, *, save: bool = True, directory: str | Path | None = None) -> bool:
    """True when fp differs from the last stored fingerprint of this gate. Stores fp unless save=False."""
    name = f"gate_{gate}"
    old = load_state(name, directory).get("fp")
    if save and old != fp:
        save_state(name, {"fp": fp}, directory)
    return old != fp


def gate_line(wake: bool, context: dict | None = None, **extra) -> str:
    payload = {"wakeAgent": bool(wake), **({"context": context} if wake and context else {}), **extra}
    return json.dumps(payload, ensure_ascii=False, separators=(", ", ": "))


def emit(wake: bool, context: dict | None = None, *, out=None, **extra) -> int:
    print(gate_line(wake, context, **extra), file=out or sys.stdout)
    return 0


def parse_gate(stdout: str) -> bool:
    """Mirror of the Hermes rule: False only when the last non-empty line is JSON with wakeAgent false."""
    lines = [ln for ln in (stdout or "").splitlines() if ln.strip()]
    if not lines:
        return True
    try:
        gate = json.loads(lines[-1].strip())
    except ValueError:
        return True
    return not isinstance(gate, dict) or gate.get("wakeAgent", True) is not False


def run_json(argv: list[str], *, timeout: int = 60, env: dict | None = None) -> list | dict:
    """Run a command that prints JSON; raise RuntimeError with a short reason on failure."""
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(argv[:3])} failed: {proc.stderr.strip()[:300]}")
    return json.loads(proc.stdout or "[]")


def guarded(gate: str, fn: Callable[[], int]) -> int:
    """Run a gate body. An exception wakes the agent once with the error, so failures are never silent."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - a gate must never crash the cron job
        return emit(True, {"gate": gate, "gate_error": f"{type(exc).__name__}: {exc}"[:400]})


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=__doc__.split("\n\n", 1)[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state-dir", help="state directory (default $HERMES_HOME/local/state)")
    ap.add_argument("--json", action="store_true", help="accepted for uniformity; output is always JSON")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fingerprint", help="print the fingerprint of the JSON on stdin")
    ch = sub.add_parser("changed", help="wake only when the JSON on stdin differs from the last run")
    ch.add_argument("gate", help="gate name (state file gate_<gate>.json)")
    ch.add_argument("--no-save", action="store_true", help="do not store the new fingerprint")
    em = sub.add_parser("emit", help="print a gate line")
    mode = em.add_mutually_exclusive_group(required=True)
    mode.add_argument("--wake", action="store_true", help="wake the agent")
    mode.add_argument("--no-wake", action="store_true", help="skip the agent")
    em.add_argument("--context", help="JSON object (with --wake)")
    a = ap.parse_args(argv)

    if a.cmd == "emit":
        return emit(a.wake, json.loads(a.context) if a.context else None)
    try:
        data = json.load(sys.stdin)
    except ValueError as exc:
        return emit(True, {"gate_error": f"stdin is not JSON: {exc}"[:400]})
    fp = fingerprint(data)
    if a.cmd == "fingerprint":
        print(json.dumps({"fingerprint": fp}))
        return 0
    empty = data in ([], {}, None, "")
    is_new = changed(a.gate, fp, save=not a.no_save, directory=a.state_dir)
    return emit(is_new and not empty, {"gate": a.gate, "fingerprint": fp})


if __name__ == "__main__":
    sys.exit(main())
