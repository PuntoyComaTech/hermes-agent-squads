#!/usr/bin/env python3
"""Evidence for the QA code lens: the quality gate step by step, a SAST pass, a DAST pass and the diff's shape.

Runs from the site folder, like check_site.py, and writes `reviews/<ID>-r<R>/code-checks.json`:
  steps    each `pnpm quality` step (types, lint, sonar, arch, dupes, unused, typecov, secrets, licenses, deps,
           test) with ok, seconds and the last error lines, so the verdict names the step that failed;
  sast     Semgrep over src/ (rule packs listed in stacks.json); an ERROR finding is critical, the rest are notes;
  dast     with --url, nuclei against the preview's origin (exposures, misconfigurations, missing response headers);
  diff     files and lines changed on web/<ID> against main, tests touched, the largest changed file.
A scanner that cannot run, a step that times out and a diff that cannot be read are critical findings: "nothing
found" and "nothing ran" must never look alike. The whole run has a 40-minute budget; a step past it is not run and
is reported. The repo must be on web/<ID>; this script never switches branches. The report lands in the site folder:
--root, or the current directory when it holds the repo, else the repo's parent.

Exit 0 evidence written (read `critical`; a missing scanner is a critical there, not an exit code), 1 repo on the
wrong branch or --root not holding the repo, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from site_base import GATE  # noqa: E402
import security_tools  # noqa: E402
from toolpath import augment_path  # noqa: E402

TAIL_LINES = 14
BUDGET = 40 * 60  # seconds for the whole run
STEP_TIMEOUT = {"test": 900, "types": 600}  # other gate steps: 300 s
# required response headers: a missing one is critical (HSTS only on https); the other nuclei header notes stay notes
REQUIRED_HEADERS = {"content-security-policy", "x-frame-options", "x-content-type-options", "referrer-policy",
                    "permissions-policy", "strict-transport-security"}


def run(argv: list[str], cwd: Path, timeout: int = 900) -> tuple[int, str, float]:
    start = time.time()
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, str(exc), time.time() - start
    return done.returncode, done.stdout + done.stderr, time.time() - start


def tail(text: str) -> list[str]:
    lines = [ln for ln in text.splitlines() if ln.strip() and "ELIFECYCLE" not in ln]
    return lines[-TAIL_LINES:]


class Budget:
    def __init__(self, seconds: int) -> None:
        self.end = time.time() + seconds

    def left(self, want: int) -> int:
        return max(0, min(want, int(self.end - time.time())))


def gate_steps(repo: Path, budget: Budget) -> dict:
    out = {}
    for step in GATE:
        limit = budget.left(STEP_TIMEOUT.get(step, 300))
        if not limit:
            out[step] = {"ok": False, "seconds": 0, "exit": None, "tail": ["not run: the audit's time budget ran out"]}
            continue
        code, text, secs = run(["pnpm", "run", "-s", f"quality:{step}"], repo, timeout=limit)
        out[step] = {"ok": code == 0, "seconds": round(secs, 1), "exit": code, "tail": [] if code == 0 else tail(text)}
    return out


def sast(repo: Path, budget: Budget) -> dict:
    got = security_tools.ensure("semgrep")
    if not got["ready"]:
        return {"ran": False, "reason": got["detail"]}
    limit = budget.left(600)
    if not limit:
        return {"ran": False, "reason": "the audit's time budget ran out"}
    rules = [arg for rule in security_tools.CONFIG["semgrep"]["rules"] for arg in ("--config", rule)]
    code, text, secs = run([security_tools.which("semgrep") or "semgrep", "scan", "--metrics=off", "--quiet", "--json",
                            *rules, "src"], repo, timeout=limit)
    try:
        doc = json.loads(text[text.index("{"):])
    except ValueError:
        return {"ran": False, "reason": f"semgrep exit {code}, no JSON: " + " ".join(tail(text)[-3:])}
    # semgrep exits 0 with findings; anything else, or an `errors` entry, means part of the code was not scanned
    # level "warn" is a partial parse (one construct skipped, the file still scanned); "error" lost a file or a rule
    errors = [str(e.get("message") or e.get("type") or e)[:200] for e in doc.get("errors") or []
              if e.get("level") != "warn"]
    if code != 0 or errors:
        return {"ran": False, "reason": f"semgrep exit {code}: " + ("; ".join(errors[:3]) or " ".join(tail(text)[-3:]))}
    rows = [{"rule": r["check_id"].split(".")[-1], "file": r["path"], "line": r["start"]["line"],
             "severity": r["extra"]["severity"]} for r in doc.get("results", [])]
    return {"ran": True, "seconds": round(secs, 1), "findings": rows,
            "critical": [f"{r['file']}:{r['line']} {r['rule']}" for r in rows if r["severity"] == "ERROR"]}


def dast(url: str, repo: Path, budget: Budget) -> dict:
    got = security_tools.ensure("nuclei")
    if not got["ready"]:
        return {"ran": False, "reason": got["detail"]}
    limit = budget.left(600)
    if not limit:
        return {"ran": False, "reason": "the audit's time budget ran out"}
    argv = [security_tools.which("nuclei") or "nuclei", "-u", url, "-silent", "-jsonl", "-disable-update-check",
            "-ud", str(security_tools.templates_dir()), "-tags", "exposure,misconfig,headers,config,token",
            "-etags", "intrusive,dos,fuzz", "-rl", "300", "-c", "50"]
    code, text, secs = run(argv, repo, timeout=limit)
    if code != 0:  # nuclei reports findings in its JSON lines; a non-zero exit is an error, never a clean scan
        return {"ran": False, "reason": f"nuclei exit {code}: " + " ".join(tail(text)[-3:])}
    rows = []
    for line in text.splitlines():
        if line.startswith("{"):
            try:
                doc = json.loads(line)
            except ValueError:
                continue
            # the missing-header template reports one row per header, the header in `matcher-name`
            name = doc.get("template-id", "")
            if doc.get("matcher-name"):
                name += ":" + doc["matcher-name"]
            rows.append({"template": name, "severity": (doc.get("info") or {}).get("severity"),
                         "at": doc.get("matched-at", "")})
    https = url.startswith("https://")

    def critical(row: dict) -> bool:
        header = row["template"].split(":")[-1] if row["template"].startswith("http-missing-security-headers") else ""
        if header:
            return header in REQUIRED_HEADERS and (https or header != "strict-transport-security")
        return row["severity"] in ("medium", "high", "critical")

    return {"ran": True, "seconds": round(secs, 1), "url": url, "findings": rows,
            "critical": [f"{r['template']} at {r['at']}" for r in rows if critical(r)]}


def diff_shape(repo: Path) -> dict:
    code, text, _ = run(["git", "diff", "--numstat", "main...HEAD"], repo)
    if code:
        return {"error": "git diff main...HEAD failed: " + " ".join(tail(text)[-2:])}
    rows = [ln.split("\t") for ln in text.splitlines() if ln.count("\t") == 2]
    changed = [(a, d, name) for a, d, name in rows if a.isdigit() and d.isdigit()]
    tests = [name for _, _, name in changed if ".test." in name or ".spec." in name or name.startswith("e2e/")]
    biggest = max(changed, key=lambda r: int(r[0]) + int(r[1]), default=None)
    return {"files": len(changed), "added": sum(int(a) for a, _, _ in changed),
            "removed": sum(int(d) for _, d, _ in changed), "tests_touched": len(tests),
            "largest": {"file": biggest[2], "added": int(biggest[0]), "removed": int(biggest[1])} if biggest else None}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0],
                                epilog="Exit 0 evidence written (read critical), 1 wrong branch or a --root not holding "
                                       "the repo, 2 usage error.")
    p.add_argument("--id", required=True, help="work item id (<slug>-<YYYYMMDD>-<kind>-<nn>)")
    p.add_argument("--round", type=int, default=0, help="review round")
    p.add_argument("--repo", required=True, help="the site repo, on branch web/<ID>")
    p.add_argument("--url", help="deployed preview URL: adds the DAST pass")
    p.add_argument("--root", help="site project folder (default: the current directory when it holds the repo, "
                                  "else the repo's parent)")
    args = p.parse_args(argv)
    augment_path()
    repo = Path(args.repo).expanduser().resolve()
    here = Path.cwd().resolve()
    root = Path(args.root).expanduser().resolve() if args.root else (
        here if here == repo or here in repo.parents else repo.parent)
    if root != repo and root not in repo.parents:
        print(json.dumps({"ok": False, "error": f"--root {root} does not hold the repo {repo}"}))
        return 1
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo)[1].strip()
    if branch != f"web/{args.id}":
        print(json.dumps({"ok": False, "error": f"repo is on {branch!r}, expected web/{args.id} (never switch it here)"}))
        return 1
    budget = Budget(BUDGET)
    steps = gate_steps(repo, budget)
    report = {"id": args.id, "round": args.round, "branch": branch, "steps": steps, "sast": sast(repo, budget),
              "dast": dast(args.url, repo, budget) if args.url else {"ran": False, "reason": "no --url given"},
              "diff": diff_shape(repo)}
    critical = [f"gate step {name} failed: {' | '.join(row['tail'][-3:])}" for name, row in steps.items() if not row["ok"]]
    for name in ("sast", "dast"):
        section = report[name]
        if name == "dast" and not args.url:
            continue
        critical += [f"{name} did not run: {section['reason']}"] if not section["ran"] else (
            [f"{name}: {c}" for c in section["critical"]])
    if "error" in report["diff"]:
        critical.append(f"diff could not be read, so the code lens has nothing to judge: {report['diff']['error']}")
    report["critical"] = critical
    folder = root / "reviews" / f"{args.id}-r{args.round}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "code-checks.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "critical": critical, "out": str(folder / "code-checks.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
