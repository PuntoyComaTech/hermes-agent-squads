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
# Core toolset names of toolsets.py (v0.22): `tools enable` rejects anything else, as the real CLI does.
KNOWN_TOOLSETS = frozenset("""
bot_room browser catalog clarify code_execution coding computer_use connections context_engine cronjob debugging
delegation desktop_ui discord discord_admin feishu_doc feishu_drive file image_gen kanban memory onboarding project
safe search session_search skills terminal todo tts video video_gen vision web x_search yuanbao
""".split())
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
            save(home / "config.yaml", {"model": {"default": "seed"}})
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
            if script and not (HOME / "scripts" / script).is_file():
                die(f"script not found: {script}")
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
        if rest[:1] == ["--board"]:
            sub, args = rest[2], rest[3:]
            store = ROOT / f"cards-{rest[1]}.json"
            cards = json.loads(store.read_text()) if store.is_file() else {}
            if sub == "create":
                key = opt("--idempotency-key")
                if key not in cards:
                    cards[key] = {"id": f"t_{len(cards) + 1:04d}", "title": args[0], "assignee": opt("--assignee"),
                                  "parent": opt("--parent"), "project": opt("--project"),
                                  "status": "todo", "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                    store.write_text(json.dumps(cards))
                print(json.dumps({"id": cards[key]["id"]}))
            else:
                print(json.dumps(list(cards.values())))
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
    elif cmd == "project":
        need_profile()
        sub, args = rest[0], rest[1:]
        store = HOME / "projects.txt"
        lines = store.read_text().splitlines() if store.is_file() else []
        if sub == "list":
            print("\n".join(f"  {ln}" for ln in lines) or "No projects yet.")
        elif sub == "show":
            row = next((ln for ln in lines if ln.split()[:1] == [args[0]]), None)
            if row is None:
                die(f"no such project: {args[0]}")
            path = row.split("path=", 1)[1].split()[0] if "path=" in row else ""
            print(f"Project: {row.split()[1] if len(row.split()) > 1 else args[0]}")
            print(f"   primary: {path}")
            print(f"   * {path}")
        elif sub == "create":
            slug = opt("--slug")
            lines.append(f"{slug}  {args[0]}  board={opt('--board')}  path={args[1]}")
            store.write_text("\n".join(lines) + "\n")
        else:
            die(f"fake: project {sub}")
    elif cmd == "mcp":
        need_profile()
        assert rest[0] == "add"
        cfg = load(HOME / "config.yaml", {})
        failing = set(filter(None, (os.environ.get("FAKE_MCP_PROBE_FAIL") or "").split(",")))
        cfg.setdefault("mcp_servers", {})[rest[1]] = {"command": opt("--command"), "url": opt("--url"),
                                                      "enabled": rest[1] not in failing}
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
    elif cmd == "tools":
        need_profile()
        # Mirror hermes_cli.tools_config._save_platform_tools: platform_toolsets.cli becomes sorted(union),
        # and unknown toolset names are refused.
        if rest[:1] == ["enable"]:
            unknown = [n for n in rest[1:] if n not in KNOWN_TOOLSETS and ":" not in n]
            if unknown:
                die(f"unknown toolset: {', '.join(unknown)}")
            cfg = load(HOME / "config.yaml", {})
            have = set((cfg.get("platform_toolsets") or {}).get("cli") or [])
            cfg.setdefault("platform_toolsets", {})["cli"] = sorted(have | set(rest[1:]))
            save(HOME / "config.yaml", cfg)
    else:
        die(f"fake hermes: unsupported command {argv}")


main()
