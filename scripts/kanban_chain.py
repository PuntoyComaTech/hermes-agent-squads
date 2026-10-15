#!/usr/bin/env python3
"""File one squad chain as dependent kanban cards in one command (zero LLM).

Reads squads/<squad>/squad.yaml (deep-merged with <home>/local/squads/<squad>/squad.yaml when present) and creates
one card per stage on the squad's board, through the lead's profile:
  hermes -p <lead> kanban --board <slug> create ... --assignee <bot> --skill <skill> --parent <previous card>
        --project <slug> --idempotency-key <squad>:<chain>:<project>:<run>:<stage> --workspace dir:<primary>
        [--model M --provider P]

- Each stage waits for the previous stage (--parent). A stage with `when: x` is skipped unless --when x is given.
- A stage with `lane: L` pins that lane's model on the card (--model/--provider). The model comes from
  <home>/local/installed.yaml: `lanes.L`, else the first bot of the squad on lane L (`bots.<bot>.provider/model`).
  With no model on record the card is created without the flags and a warning is reported.
- Idempotent: the key is derived from squad, chain, project, run id (default: slug of the title) and stage, so
  re-running prints the same card ids. Use --run-id to file a second chain with the same title.
- The board and the project (`hermes -p <lead> project create ...`) must already exist.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


class ChainError(Exception):
    pass


def _yaml():
    """YAML module on first use, never at import: `--help` must work without PyYAML (scripts/hpy provides
    hermes_yaml; a bare python3 falls back to PyYAML when a command actually reads YAML)."""
    try:
        import hermes_yaml as y  # the Hermes runtime's YAML module
    except ImportError:
        try:
            import yaml as y
        except ImportError:
            raise ChainError("no YAML module: run scripts/hpy kanban_chain.py (Hermes runtime) or install PyYAML") from None
    return y


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "run"


def hermes_root() -> Path:
    home = Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    return home.parent.parent if home.parent.name == "profiles" else home


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, val in over.items():
        out[key] = deep_merge(out[key], val) if isinstance(val, dict) and isinstance(out.get(key), dict) else val
    return out


def load_yaml(path: Path) -> dict:
    data = _yaml().safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def load_squad(squad: str, squads_dir: Path, home: Path) -> dict:
    repo, local = squads_dir / squad / "squad.yaml", home / "local" / "squads" / squad / "squad.yaml"
    if not repo.is_file() and not local.is_file():
        raise ChainError(f"squad {squad!r} not found in {squads_dir} or {local.parent}")
    doc = deep_merge(load_yaml(repo) if repo.is_file() else {}, load_yaml(local) if local.is_file() else {})
    for field in ("lead", "bots", "chains"):
        if not doc.get(field):
            raise ChainError(f"squad {squad!r} has no {field}")
    return doc


def lane_model(doc: dict, lane: str, installed: dict) -> tuple[str, str] | None:
    """(model, provider) recorded for a lane: installed.lanes.<lane>, else a bot of the squad on that lane."""
    candidates = [(installed.get("lanes") or {}).get(lane)]
    candidates += [(installed.get("bots") or {}).get(name) for name, bot in doc["bots"].items() if bot.get("lane") == lane]
    for entry in candidates:
        if isinstance(entry, dict) and entry.get("model"):
            return str(entry["model"]), str(entry.get("provider") or "")
    return None


def plan(doc: dict, squad: str, chain: str, project: str, title: str, body: str, when: set[str], run_id: str,
         installed: dict) -> dict:
    stages = (doc["chains"] or {}).get(chain)
    if not stages:
        raise ChainError(f"chain {chain!r} not in {squad}: {', '.join(doc['chains'])}")
    active = [s for s in stages if not s.get("when") or s["when"] in when]
    skipped = [{"stage": s["stage"], "when": s["when"]} for s in stages if s not in active]
    cards, warnings, parent = [], [], None
    for n, st in enumerate(active, 1):
        if st["assignee"] not in doc["bots"]:
            raise ChainError(f"stage {st['stage']!r}: assignee {st['assignee']!r} is not a bot of {squad}")
        card = {
            "stage": st["stage"], "title": f"{title} - {n} {st['stage']}", "assignee": st["assignee"],
            "skill": st.get("skill"), "parent": parent, "model": None, "provider": None,
            "key": f"{squad}:{chain}:{project}:{run_id}:{st['stage']}",
            "body": f"Squad {squad}, chain {chain}, stage {n}/{len(active)} ({st['stage']}), project {project}."
                    + (f"\n\n{body}" if body else ""),
        }
        if st.get("lane"):
            found = lane_model(doc, st["lane"], installed)
            if found:
                card["model"], card["provider"] = found[0], found[1] or None
            else:
                warnings.append(f"stage {st['stage']}: no model on record for lane {st['lane']!r}; card uses the profile model")
        cards.append(card)
        parent = f"<{st['stage']}>"
    return {"squad": squad, "chain": chain, "board": (doc.get("board") or {}).get("slug") or squad, "lead": doc["lead"],
            "project": project, "cards": cards, "skipped": skipped, "warnings": warnings}


def card_command(hermes_bin: str, result: dict, card: dict, parent_id: str | None, workspace: str | None) -> list[str]:
    cmd = [hermes_bin, "-p", result["lead"], "kanban", "--board", result["board"], "create", card["title"],
           "--assignee", card["assignee"], "--created-by", result["lead"], "--project", result["project"],
           "--idempotency-key", card["key"], "--body", card["body"]]
    for flag, value in (("--skill", card["skill"]), ("--parent", parent_id), ("--model", card["model"]),
                        ("--provider", card["provider"]), ("--workspace", workspace)):
        if value:
            cmd += [flag, value]
    return cmd + ["--json"]


def task_id(out: str) -> str:
    try:
        data = json.loads(out)
        return str(data.get("id") or data.get("task_id") or (data.get("task") or {}).get("id"))
    except ValueError:
        return out.split()[-1]


def project_primary(hermes_bin: str, root: Path, lead: str, project: str) -> str | None:
    """Primary folder of the project (`hermes project show` prints a `primary:` line). With a project and no
    explicit workspace, kanban_db turns a `scratch` card into a git worktree of that repo; a plain folder is
    not a repo, so cards default to `dir:<primary>` instead."""
    try:
        proc = subprocess.run([hermes_bin, "-p", lead, "project", "show", project], capture_output=True, text=True,
                              timeout=120, env={**os.environ, "HERMES_HOME": str(root)})
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    match = re.search(r"^\s*primary:\s*(\S.*?)\s*$", proc.stdout, re.M)
    return match.group(1) if match else None


def create(result: dict, hermes_bin: str, root: Path, workspace: str | None) -> None:
    env = {**os.environ, "HERMES_HOME": str(root)}
    if not workspace:
        primary = project_primary(hermes_bin, root, result["lead"], result["project"])
        if primary:
            workspace = f"dir:{primary}"
        else:
            result["warnings"].append(
                f"project {result['project']}: primary path unknown; pass --workspace dir:<folder> "
                "(the CLI default turns a project card into a git worktree)")
    prev = None
    for card in result["cards"]:
        proc = subprocess.run(card_command(hermes_bin, result, card, prev, workspace), capture_output=True, text=True,
                              timeout=180, env=env)
        if proc.returncode != 0:
            raise ChainError(f"stage {card['stage']} failed: {(proc.stderr or proc.stdout).strip()[:300]}")
        card["parent"] = prev
        card["id"] = prev = task_id(proc.stdout.strip())


def render(result: dict, dry_run: bool) -> str:
    lines = []
    for card in result["cards"]:
        after = f" (after {card['parent']})" if card["parent"] else ""
        model = f" [{card['model']}]" if card["model"] else ""
        lines.append(f"{'would create' if dry_run else 'card ' + str(card.get('id'))}: {card['title']} -> {card['assignee']}{model}{after}")
    lines += [f"skipped: {s['stage']} (when {s['when']})" for s in result["skipped"]]
    lines += [f"warning: {w}" for w in result["warnings"]]
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], epilog=__doc__.split("\n\n", 1)[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("squad", help="squad key")
    ap.add_argument("chain", help="chain name in squad.yaml -> chains")
    ap.add_argument("--project", required=True, help="project slug (exists in the lead's profile)")
    ap.add_argument("--title", required=True, help="title prefix of every card")
    ap.add_argument("--body", default="", help="text appended to every card body")
    ap.add_argument("--when", default="", help="comma list of conditions that enable `when:` stages")
    ap.add_argument("--run-id", help="idempotency run id (default: slug of the title)")
    ap.add_argument("--workspace", help="pin every card's workspace (default: dir:<project primary path>, so a "
                                       "project card is never created as a git worktree)")
    ap.add_argument("--squads-dir", type=Path, default=SCRIPTS.parent / "squads",
                    help="directory holding <squad>/squad.yaml (default: the squads/ beside scripts/)")
    ap.add_argument("--home", type=Path, default=Path(os.environ.get("HERMES_HOME") or Path.home() / ".hermes" / "profiles" / "builder"),
                    help="builder profile home holding local/ (default $HERMES_HOME)")
    ap.add_argument("--hermes-root", type=Path, help="Hermes root for `-p` (default: $HERMES_HOME without /profiles/<name>)")
    ap.add_argument("--hermes-bin", default=os.environ.get("HERMES_BIN", "hermes"),
                    help="hermes executable (default: $HERMES_BIN, else hermes)")
    ap.add_argument("--dry-run", action="store_true", help="print the cards, create nothing")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    return ap


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        doc = load_squad(a.squad, a.squads_dir, a.home)
        installed_path = a.home / "local" / "installed.yaml"
        installed = load_yaml(installed_path) if installed_path.is_file() else {}
        result = plan(doc, a.squad, a.chain, a.project, a.title, a.body,
                      {w for w in a.when.split(",") if w}, a.run_id or slugify(a.title), installed)
        if not a.dry_run:
            create(result, a.hermes_bin, a.hermes_root or hermes_root(), a.workspace)
    except (ChainError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc)}) if a.json else f"error: {exc}")
        return 2
    result["dry_run"] = a.dry_run
    print(json.dumps(result, indent=2) if a.json else render(result, a.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
