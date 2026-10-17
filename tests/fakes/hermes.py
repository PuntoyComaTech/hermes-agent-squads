#!/usr/bin/env python3
"""Fake `hermes` CLI for squadctl tests. State lives under $HERMES_HOME (profiles/<name>/...), calls are appended to
$FAKE_HERMES_LOG as JSON lines. Implements only the commands squadctl uses."""
import json
import os
import shutil
import sys
import tarfile
import time
import uuid
from pathlib import Path

import yaml

FAKE_ROOT = Path(os.environ.get("FAKE_HERMES_SRC") or Path(__file__).resolve().parent / "root")
ROOT = Path(os.environ.get("HERMES_HOME", "/nonexistent"))
# CONFIGURABLE_TOOLSETS keys of hermes_cli/tools_config.py (v0.22), the set `tools enable` accepts besides plugin
# toolsets and `server:tool` targets (hermes_cli/tools_config_mcp.tools_disable_enable_command). Anything else is
# printed as "✗ Unknown toolset" and skipped, and the command still exits 0.
KNOWN_TOOLSETS = frozenset("""
web browser terminal file code_execution vision video image_gen video_gen x_search tts stt skills todo kanban memory
context_engine session_search connections clarify delegation cronjob discord discord_admin yuanbao computer_use
""".split())
# Kanban mutations refused inside a delegate/kanban-worker child (hermes_cli/kanban._is_delegated_child_cli_mutation).
FENCED = bool(os.environ.get("HERMES_DELEGATED_CHILD_CONTEXT"))
argv = sys.argv[1:]
profile = None
if argv[:1] == ["-p"]:
    profile, argv = argv[1], argv[2:]
HOME = ROOT / "profiles" / profile if profile else ROOT
log = os.environ.get("FAKE_HERMES_LOG")
if log:
    with open(log, "a") as f:
        f.write(json.dumps({"profile": profile, "args": argv}) + "\n")


def load(path, default):
    return yaml.safe_load(path.read_text()) if path.is_file() and path.read_text().strip() else default


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def opt(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def opts(name):
    return [argv[i + 1] for i, a in enumerate(argv) if a == name]


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def need_profile():
    if not HOME.is_dir():
        die(f"profile {profile} does not exist")


def jobs_path():
    return HOME / "cron" / "jobs.json"


def jobs():
    p = jobs_path()
    return json.loads(p.read_text()) if p.is_file() else {"jobs": []}


def save_jobs(d):
    jobs_path().parent.mkdir(parents=True, exist_ok=True)
    jobs_path().write_text(json.dumps(d))


def config_add(path, section, key, value):
    cfg = load(HOME / "config.yaml", {})
    cfg.setdefault(section, {}).setdefault(key, [] if key == "enabled" else {})
    if key == "enabled":
        if value not in cfg[section][key]:
            cfg[section][key].append(value)
    else:
        cfg[section][key] = value
    save(HOME / "config.yaml", cfg)


def main():
    if argv == ["--version"]:
        # one line, with the +build suffix a git install reports
        print("Hermes Agent v0.22.0+2.gd97007c (fake)")
        return
    if argv == ["--print-runtime-command"]:
        boot = (f"import sys; sys.path.insert(0, '{FAKE_ROOT}'); sys._hermes_pin_default_home = True; "
                "import hermes_cli.main")
        print(json.dumps([sys.executable, "-I", "-c", boot]))
        return
    cmd, rest = argv[0], argv[1:]
    if cmd == "profile":
        sub, args = rest[0], rest[1:]
        if sub == "create":
            name = args[0]
            home = ROOT / "profiles" / name
            if home.exists():
                die(f"profile {name} exists")
            (home / "skills").mkdir(parents=True)
            # Real create copies the launching home's `model` block (profiles.launch_model_seed) and writes no
            # config.yaml at all when that home has none.
            launch = load(ROOT / "config.yaml", {}).get("model")
            if launch:
                save(home / "config.yaml", {"model": launch})
            save(home / "profile.yaml", {"description": opt("--description", "")})
            if "--no-skills" in args:
                (home / ".no-bundled-skills").write_text("")
            else:
                (home / "skills" / "bundled-demo").mkdir()
                (home / "skills" / "bundled-demo" / "SKILL.md").write_text("---\nname: bundled-demo\n---\n")
                (home / "skills" / ".bundled_manifest").write_text("bundled-demo:abc\n")
            print(f"created {name}")
        elif sub == "describe":
            data = load(ROOT / "profiles" / args[0] / "profile.yaml", {})
            data["description"] = opt("--text")
            save(ROOT / "profiles" / args[0] / "profile.yaml", data)
        elif sub == "show":
            data = load(ROOT / "profiles" / args[0] / "profile.yaml", {})
            print(f"Profile: {args[0]}")
            print(f"Description: {data.get('description', '')}")
            print(f"Gateway:        {'running' if args[0] == 'default' else 'stopped'}")
        elif sub == "export":
            home = ROOT / "profiles" / args[0]
            if not home.is_dir():
                die("no such profile")
            out = Path(opt("-o"))
            out.parent.mkdir(parents=True, exist_ok=True)
            with tarfile.open(out, "w:gz") as tf:
                tf.add(home, arcname=args[0], filter=lambda ti: None if Path(ti.name).name in (".env", "auth.json") else ti)
        elif sub == "delete":
            if "--yes" not in args:
                die("refusing to delete without --yes")
            shutil.rmtree(ROOT / "profiles" / args[0])
        elif sub == "list":
            print(" Profile    Model    Gateway    Alias")
            print(" ◆default   x        running    -")
            for p in sorted((ROOT / "profiles").glob("*")):
                print(f"  {p.name}   x   stopped   -")
        else:
            die(f"fake: profile {sub}")
    elif cmd == "skills":
        need_profile()
        sub, args = rest[0], rest[1:]
        if sub == "opt-out":
            if "--yes" not in args:
                die("refusing to remove bundled skills without --yes")
            (HOME / ".no-bundled-skills").write_text("")
            if "--remove" in args:
                manifest = HOME / "skills" / ".bundled_manifest"
                for line in (manifest.read_text().splitlines() if manifest.is_file() else []):
                    shutil.rmtree(HOME / "skills" / line.split(":")[0], ignore_errors=True)
        elif sub == "install":
            ident = args[0]
            name = ident.rsplit("/", 1)[-1]
            lock = HOME / "skills" / ".hub" / "lock.json"
            lock.parent.mkdir(parents=True, exist_ok=True)
            data = json.loads(lock.read_text()) if lock.is_file() else {"installed": {}}
            data["installed"][name] = {"identifier": ident}
            lock.write_text(json.dumps(data))
            (HOME / "skills" / "hub" / name).mkdir(parents=True, exist_ok=True)
            (HOME / "skills" / "hub" / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n")
        elif sub == "uninstall":  # tools/skills_hub_install.py uninstall_skill: lock entries only
            name = args[0]
            lock = HOME / "skills" / ".hub" / "lock.json"
            data = json.loads(lock.read_text()) if lock.is_file() else {"installed": {}}
            if name not in data["installed"]:
                die(f"'{name}' is not a hub-installed skill (may be a builtin)")
            del data["installed"][name]
            lock.write_text(json.dumps(data))
            shutil.rmtree(HOME / "skills" / "hub" / name, ignore_errors=True)
        else:
            die(f"fake: skills {sub}")
    elif cmd == "cron":
        need_profile()
        sub, args = rest[0], rest[1:]
        data = jobs()
        if sub == "create":
            sched = args[0]
            value_flags = {"--name", "--deliver", "--failure-deliver", "--repeat", "--skill", "--script", "--model",
                           "--provider", "--reasoning-effort", "--interpreter", "--monitor-script", "--monitor-url",
                           "--workdir", "--paused-reason"}
            bare, skip = [], False
            for a in args[1:]:
                if skip:
                    skip = False
                elif a in value_flags:
                    skip = True
                elif not a.startswith("--"):
                    bare.append(a)
            script = opt("--script")
            if not script and "--skill" not in args and not bare:
                die("cron create needs a prompt, --skill or --script")
            # Real create_job stores the script string without checking that it exists (cron/jobs.py); a missing
            # script surfaces only at run time or in `hermes cron doctor`.
            data["jobs"].append({
                "id": uuid.uuid4().hex[:12], "name": opt("--name"), "script": opt("--script"),
                "no_agent": "--no-agent" in args, "deliver": opt("--deliver", "local"),
                "skills": opts("--skill"), "model": opt("--model"), "provider": opt("--provider"),
                "reasoning_effort": opt("--reasoning-effort"),
                "schedule": {"kind": "cron", "expr": sched, "display": sched}, "schedule_display": sched})
        elif sub == "edit":
            job = next(j for j in data["jobs"] if j["id"] == args[0])
            for flag, key in (("--script", "script"), ("--deliver", "deliver"), ("--model", "model"),
                              ("--provider", "provider"), ("--reasoning-effort", "reasoning_effort")):
                if flag in args:
                    job[key] = opt(flag)
            if "--schedule" in args:
                job["schedule"] = {"kind": "cron", "expr": opt("--schedule"), "display": opt("--schedule")}
            if "--skill" in args:
                job["skills"] = opts("--skill")
            if "--no-agent" in args:
                job["no_agent"] = True
            elif "--agent" in args:
                job["no_agent"] = False  # an absent flag leaves the value alone
        elif sub == "remove":
            data["jobs"] = [j for j in data["jobs"] if j["id"] != args[0]]
        else:
            die(f"fake: cron {sub}")
        save_jobs(data)
    elif cmd == "kanban":
        mutating = (rest[2:3] == ["create"] if rest[:1] == ["--board"]
                    else rest[:1] == ["boards"] and rest[1:2] not in (["list"], ["show"]))
        if FENCED and mutating:
            die("kanban: delegate_task child contexts cannot mutate Kanban tasks via the CLI")
        if rest[:1] == ["--board"]:
            sub, args = rest[2], rest[3:]
            boards = json.loads((ROOT / "boards.json").read_text()) if (ROOT / "boards.json").is_file() else []
            if rest[1] != "default" and rest[1] not in {b["slug"] for b in boards if not b.get("archived")}:
                die(f"kanban: board {rest[1]!r} does not exist. Create it with `hermes kanban boards create {rest[1]}`.")
            store = ROOT / f"cards-{rest[1]}.json"
            cards = json.loads(store.read_text()) if store.is_file() else {}
            if sub == "create":
                key = opt("--idempotency-key")
                if key not in cards:
                    cards[key] = {"id": f"t_{len(cards) + 1:04d}", "title": args[0], "assignee": opt("--assignee"),
                                  "parent": opt("--parent"), "project": opt("--project"),
                                  "status": "todo", "created_at": int(time.time())}  # epoch int, as kanban list --json
                    store.write_text(json.dumps(cards))
                print(json.dumps({"id": cards[key]["id"]}))
            else:
                status = opt("--status")
                print(json.dumps([c for c in cards.values() if not status or c.get("status") == status]))
            return
        assert rest[0] == "boards", rest
        sub, args = rest[1], rest[2:]
        store = ROOT / "boards.json"
        boards = json.loads(store.read_text()) if store.is_file() else []
        if sub == "list":
            print(json.dumps([b for b in boards if not b.get("archived")]))
        elif sub == "create":
            boards.append({"slug": args[0], "name": opt("--name"), "archived": False})
        elif sub == "rm":
            for b in boards:
                if b["slug"] == args[0]:
                    b["archived"] = True
        if sub != "list":
            store.write_text(json.dumps(boards))
    elif cmd == "auth":
        need_profile()
        assert rest[:1] == ["list"], rest
        # real shape (hermes_cli/auth_commands): provider header lines only; the indented credential rows below
        # them are never parsed by squadctl, which reads names, never values.
        names = HOME / "auth-names.json"
        for slug in (json.loads(names.read_text()) if names.is_file() else []):
            print(f"{slug} (1 credentials):")
            print("  #1  key-name  api_key id=1 priority=0 env:X <-")
    elif cmd == "project":
        need_profile()
        sub, args = rest[0], rest[1:]
        # one tab-separated row per project: slug, name, board=<slug|None>, path=<primary>, folders=<a|b>
        store = HOME / "projects.txt"
        rows = [dict(zip(("slug", "name", "board", "path", "folders"), ln.split("\t")))
                for ln in (store.read_text().splitlines() if store.is_file() else []) if ln.strip()]
        for r in rows:
            r["board"] = r.get("board", "board=None").split("=", 1)[1]
            r["path"] = r.get("path", "path=").split("=", 1)[1]
            r["folders"] = [f for f in r.get("folders", "folders=").split("=", 1)[1].split("|") if f] or [r["path"]]

        def write():
            store.write_text("".join(f"{r['slug']}\t{r['name']}\tboard={r['board']}\tpath={r['path']}\t"
                                     f"folders={'|'.join(r['folders'])}\n" for r in rows))

        def find(ident):
            row = next((r for r in rows if r["slug"] == ident), None)
            if row is None:
                die(f"project: no such project: {ident}")
            return row

        active = (HOME / "projects.active").read_text().strip() if (HOME / "projects.active").is_file() else ""
        if sub in ("list", "ls"):
            # real shape (projects_cmd._cmd_list): "<*| > <slug:<24> <name>  [N folder(s)]"
            print("\n".join(f"{'*' if r['slug'] == active else ' '} {r['slug']:<24} {r['name']}  "
                            f"[{len(r['folders'])} folder(s)]" for r in rows)
                  or "No projects yet. Create one with `hermes project create <name>`.")
        elif sub == "show":
            # real shape (projects_cmd._print_project)
            r = find(args[0])
            print(f"{r['slug']}  [p_{r['slug']}]")
            print(f"  name:    {r['name']}")
            if r["board"] != "None":
                print(f"  board:   {r['board']}")
            if r["path"]:
                print(f"  primary: {r['path']}")
            print("  folders:")
            for f in r["folders"]:
                print(f"   {' *' if f == r['path'] else '  '} {f}")
        elif sub == "create":
            bare, skip = [], False
            for a in args:
                if skip:
                    skip = False
                elif a in ("--slug", "--primary", "--board", "--description", "--icon", "--color"):
                    skip = True
                elif not a.startswith("--"):
                    bare.append(a)
            folders = [str(Path(f).expanduser().absolute()) for f in bare[1:]]
            slug = opt("--slug") or bare[0].lower().replace(" ", "-")
            if any(r["slug"] == slug for r in rows):
                die(f"project: slug already exists: {slug}")
            primary = opt("--primary") or (folders[0] if folders else "")
            rows.append({"slug": slug, "name": bare[0], "board": opt("--board") or "None", "path": primary,
                         "folders": folders or [primary]})
            write()
            if "--use" in args:
                (HOME / "projects.active").write_text(slug)
            print(f"Created project {slug} (p_{slug})")
        elif sub == "bind-board":
            r = find(args[0])
            r["board"] = args[1] if len(args) > 1 and args[1] else "None"
            write()
            print(f"Bound {r['slug']} -> board {args[1]}" if r["board"] != "None" else f"Unbound board from {r['slug']}")
        elif sub == "use":
            if args:
                find(args[0])
            (HOME / "projects.active").write_text(args[0] if args else "")
            print(f"Active project: {args[0]}" if args else "Cleared active project")
        else:
            die(f"fake: project {sub}")
    elif cmd == "mcp":
        need_profile()
        assert rest[0] == "add"
        args = rest[1:]
        cfg = load(HOME / "config.yaml", {})
        name_arg = args[0]
        url = opt("--url")
        failing = name_arg in set(filter(None, (os.environ.get("FAKE_MCP_PROBE_FAIL") or "").split(",")))
        # Real prompt order and defaults (hermes_cli/mcp_config.cmd_mcp_add): only an HTTP server asks "Does this
        # server require authentication?" (_configure_http_auth), then the tool picker's "Enable all N tools?"
        # (_choose_tools) or a "Save config anyway?" confirm. A blank line takes the prompt's default and an
        # exhausted stdin is EOF — the picker then prints "Cancelled." and exits 0 without writing anything, the
        # silent failure a wrong answer sequence hides.
        answers = sys.stdin.read().splitlines()

        def ask(default: bool) -> bool:
            val = answers.pop(0).strip().lower() if answers else ""
            return val in {"y", "yes"} if val else default

        if url and ask(True):
            die("fake: the auth prompt was answered 'yes' (a bearer key would be asked for next)")
        enabled = False
        if failing:
            if not ask(False):  # "Save config anyway (you can test later)?": yes saves it disabled
                return
        elif ask(True):  # "Enable all N tools?"
            enabled = True
        else:
            print("Cancelled.")
            return
        cfg.setdefault("mcp_servers", {})[name_arg] = {"command": opt("--command"), "url": url, "enabled": enabled}
        save(HOME / "config.yaml", cfg)
    elif cmd == "plugins":
        need_profile()
        sub, args = rest[0], rest[1:]
        if sub == "enable":
            config_add(None, "plugins", "enabled", args[0])
        elif sub == "install":
            # real behavior: without --yes-deps the dependency consent fails closed, so the plugin lands in
            # <home>/plugins but stays disabled; enabling needs --enable together with --yes-deps.
            plugdir = HOME / "plugins" / args[0]
            plugdir.mkdir(parents=True, exist_ok=True)
            (plugdir / "plugin.json").write_text("{}")
            if "--enable" in args and "--yes-deps" in args:
                config_add(None, "plugins", "enabled", args[0])
        elif sub == "disable":
            cfg = load(HOME / "config.yaml", {})
            cfg.setdefault("plugins", {}).setdefault("enabled", [])
            cfg["plugins"]["enabled"] = [p for p in cfg["plugins"]["enabled"] if p != args[0]]
            save(HOME / "config.yaml", cfg)
    elif cmd == "tools" and rest[:2] == ["post-setup", "agent_browser"]:
        print("✓ Post-setup 'agent_browser' complete")
    elif cmd == "tools":
        need_profile()
        # Mirror hermes_cli.tools_config._save_platform_tools: platform_toolsets.cli becomes sorted(union).
        if rest[:1] == ["enable"]:
            unknown = [n for n in rest[1:] if n not in KNOWN_TOOLSETS and ":" not in n]
            for n in unknown:  # real: an error line per bad name, the rest applied, exit 0
                print(f"✗ Unknown toolset '{n}'")
            cfg = load(HOME / "config.yaml", {})
            have = set((cfg.get("platform_toolsets") or {}).get("cli") or [])
            cfg.setdefault("platform_toolsets", {})["cli"] = sorted(have | (set(rest[1:]) - set(unknown)))
            save(HOME / "config.yaml", cfg)
    else:
        die(f"fake hermes: unsupported command {argv}")


main()
