#!/usr/bin/env python3
"""squadctl: plan, apply, inspect and remove Hermes squads. Idempotent: read state, diff, write only the difference.

  squadctl plan|apply <squad>|--self [--bots a,b] [--models f] [--dry-run] [--skip-skills] [--confirm id]
  squadctl status [squad]          installed.yaml and the live profiles
  squadctl doctor                  hermes, gateway, apps, models, passthrough, stale cards
  squadctl uninstall <squad> [--keep-profiles] [--dry-run]
  squadctl project add <squad> <name> <path>
  squadctl chain <squad> <chain> --project <slug> --title <t> [--when a,b] [--dry-run]

Reads squads/<key>/squad.yaml (builder.yaml for --self), the overlay local/squads/<key>/squad.yaml and the models
chosen in local/installed.yaml (bots: and lanes: maps of provider/model/reasoning, written by the builder after
scripts/model_advisor.py). --models <file> merges the same shape (or model_advisor --json output) and is saved on
a real apply. Output is TOON by default, JSON with --json. Config writes go through Hermes's own writer, one process
per profile (_profile_apply.py). Never reads or prints secrets: passthrough shows names and set/missing only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent
sys.path.insert(0, str(HERE))
import _profile_apply as pa  # noqa: E402  (stdlib-only helpers shared with the in-runtime writer)

AUX_TASKS = ("title_generation", "goal_judge", "curator", "compression", "kanban_decomposer", "triage_specifier",
             "background_review", "profile_describer", "memory_query_rewrite", "approval", "review", "skills_hub",
             "monitor")
# Toolsets this tool switches on or off. kanban, skills, terminal and file are never put in disabled_toolsets: it
# overrides everything, including the kanban tools the dispatcher gives workers.
MANAGED = {"web", "browser", "vision", "video", "image_gen", "video_gen", "delegation", "memory", "session_search",
           "clarify", "cronjob", "connections", "todo"}
CRON_TOOLSETS = ["terminal", "file", "skills", "kanban", "todo"]
SHA_MARK = ".squad-sha"
STALE_SECONDS = 24 * 3600


class Fail(Exception):
    def __init__(self, msg: str, code: int = 1):
        super().__init__(msg)
        self.code = code


# --- plumbing -------------------------------------------------------------------------------------------------------

def _yaml():
    try:
        import hermes_yaml as y  # the Hermes runtime's YAML module
    except ImportError:
        try:
            import yaml as y
        except ImportError:
            raise Fail("no YAML module: run scripts/squadctl (Hermes runtime) or install PyYAML") from None
    return y


def read_yaml(path: Path):
    return _yaml().safe_load(path.read_text(encoding="utf-8")) if path.is_file() else None


def write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(_yaml().safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    os.replace(tmp, path)


def write_text(path: Path, text: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def deep_merge(base, over):
    """Dicts merge key-wise, anything else is replaced; a None value deletes the key."""
    if not isinstance(base, dict) or not isinstance(over, dict):
        return over
    out = dict(base)
    for k, v in over.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = deep_merge(base[k], v) if k in base else v
    return out


def resolve_root(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser().absolute()
    home = os.environ.get("HERMES_HOME")
    if home:
        p = Path(home).expanduser().absolute()
        return p.parent.parent if p.parent.name == "profiles" else p
    return Path.home() / ".hermes"


class Ctx:
    def __init__(self, a: argparse.Namespace):
        self.root = resolve_root(a.hermes_root)
        self.profiles = self.root / "profiles"
        self.src = Path(a.src).expanduser().absolute() if a.src else SRC
        self.local = Path(a.local).expanduser().absolute() if a.local else self.profiles / a.builder / "local"
        self.builder = a.builder
        self.json = a.json
        self._runtime: tuple[str, str] | None = None
        self.confirmed = set(getattr(a, "confirm", None) or [])

    def home(self, bot: str) -> Path:
        return self.profiles / bot

    def hermes(self, *args: str, profile: str | None = None, check: bool = True, stdin: str | None = None) -> str:
        cmd = ["hermes", *(["-p", profile] if profile else []), *args]
        env = {**os.environ, "HERMES_HOME": str(self.root)}
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=600,
                               **({"input": stdin} if stdin is not None else {"stdin": subprocess.DEVNULL}))
        except FileNotFoundError:
            raise Fail("hermes not found on PATH") from None
        if check and p.returncode != 0:
            raise Fail(f"hermes {' '.join(args)} failed ({p.returncode}): {(p.stderr or p.stdout).strip()[:400]}")
        return p.stdout

    def runtime(self) -> tuple[str, str]:
        """(python, hermes source root) of the installed Hermes, from its own launcher."""
        if self._runtime is None:
            env = {k: v for k, v in os.environ.items() if k != "HERMES_HOME"}
            try:
                p = subprocess.run(["hermes", "--print-runtime-command"], capture_output=True, text=True, env=env,
                                   timeout=60, stdin=subprocess.DEVNULL)
                argv = json.loads(p.stdout)
            except (FileNotFoundError, ValueError):
                raise Fail("cannot read `hermes --print-runtime-command`: is Hermes installed and on PATH?") from None
            root = re.search(r"sys\.path\.insert\(0, '([^']+)'\)", argv[-1])
            if not root:
                raise Fail("cannot locate the Hermes source tree from `hermes --print-runtime-command`")
            self._runtime = (argv[0], root.group(1))
        return self._runtime


# --- output (TOON by default) ---------------------------------------------------------------------------------------

def _scalar(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    s = str(v)
    if s == "" or re.search(r'[,:\n"\[\]{}]|^\s|\s$|^(true|false|null|-?\d+(\.\d+)?)$', s):
        return json.dumps(s, ensure_ascii=False)
    return s


def _is_scalar(v) -> bool:
    return not isinstance(v, (dict, list))


def toon(obj: dict, ind: int = 0) -> list[str]:
    pad, out = "  " * ind, []
    for k, v in obj.items():
        if isinstance(v, dict):
            out += [f"{pad}{k}:" if v else f"{pad}{k}: {{}}"] + toon(v, ind + 1)
        elif isinstance(v, list):
            out += _toon_list(k, v, ind)
        else:
            out.append(f"{pad}{k}: {_scalar(v)}")
    return out


def _toon_list(k: str, v: list, ind: int) -> list[str]:
    pad = "  " * ind
    if not v:
        return [f"{pad}{k}[0]:"]
    if all(_is_scalar(x) for x in v):
        inline = ",".join(_scalar(x) for x in v)
        if len(v) <= 6 and len(inline) <= 100 and all(_scalar(x) == str(x) for x in v):
            return [f"{pad}{k}[{len(v)}]: {inline}"]
        return [f"{pad}{k}[{len(v)}]:", *[f"{pad}  - {x}" for x in v]]
    keys = list(v[0]) if isinstance(v[0], dict) else None
    if keys and all(isinstance(x, dict) and list(x) == keys and all(map(_is_scalar, x.values())) for x in v):
        rows = [f"{pad}  " + ",".join(_scalar(x[c]) for c in keys) for x in v]
        return [f"{pad}{k}[{len(v)}]{{{','.join(keys)}}}:", *rows]
    out = [f"{pad}{k}[{len(v)}]:"]
    for item in v:
        lines = toon(item) if isinstance(item, dict) else [_scalar(item)]
        out += [f"{pad}  - {lines[0]}", *[f"{pad}    {ln}" for ln in lines[1:]]]
    return out


def emit(ctx: Ctx, data: dict) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False) if ctx.json else "\n".join(toon(data)))


# --- spec, models ---------------------------------------------------------------------------------------------------

def load_roles(ctx: Ctx) -> dict:
    base = read_yaml(HERE / "data" / "model-roles.yaml") or {}
    local = read_yaml(ctx.local / "model-roles.yaml") or {}
    return deep_merge(base, local).get("lanes") or {}


def load_always_disabled() -> list[str]:
    return list((read_yaml(HERE / "data" / "always-disabled.yaml") or {}).get("always_disabled") or [])


def squad_dirs(ctx: Ctx, key: str) -> list[Path]:
    """Asset search order for one squad: the local overlay first, then the repo."""
    dirs = [ctx.local / "squads" / key, ctx.src / "squads" / key]
    return dirs + [ctx.src] if key == "builder" else dirs


def available_squads(ctx: Ctx) -> list[str]:
    keys = set()
    for base in (ctx.src / "squads", ctx.local / "squads"):
        if base.is_dir():
            keys |= {p.parent.name for p in base.glob("*/squad.yaml") if not p.parent.name.startswith("_")}
    return sorted(keys)


def load_spec(ctx: Ctx, key: str) -> dict:
    repo = ctx.src / ("builder.yaml" if key == "builder" else f"squads/{key}/squad.yaml")
    base = read_yaml(repo)
    over = read_yaml(ctx.local / "squads" / key / "squad.yaml")
    if base is None and over is None:
        raise Fail(f"unknown squad {key!r}; available: {', '.join(available_squads(ctx)) or 'none'}")
    spec = deep_merge(base, over) if base is not None and over is not None else (base or over)
    problems = validate_spec(ctx, spec, key)
    if problems:
        raise Fail(f"invalid squad {key}: " + "; ".join(p[:160] for p in problems[:6])
                   + (f"; and {len(problems) - 6} more" if len(problems) > 6 else ""))
    return spec


def validate_spec(ctx: Ctx, spec: dict, key: str) -> list[str]:
    """Cross-field rules of the schema (docs/decisions.md C-01); the full JSON schema runs when jsonschema exists."""
    out: list[str] = []
    try:
        import jsonschema
        schema = json.loads((ctx.src / "squads" / "_schema" / "squad.schema.json").read_text())
        out += [f"{'/'.join(map(str, e.absolute_path)) or '.'}: {e.message}"
                for e in jsonschema.Draft202012Validator(schema).iter_errors(spec)]
    except (ImportError, OSError):
        for field in ("schema", "key", "name", "version", "lead", "bots"):
            if field not in spec:
                out.append(f"missing {field}")
    if out:
        return out
    bots, lanes, always = spec["bots"], load_roles(ctx), set(load_always_disabled())
    if spec["key"] != key:
        out.append(f"key {spec['key']!r} does not match {key!r}")
    if spec["lead"] not in bots or bots[spec["lead"]].get("role") != "lead":
        out.append(f"lead {spec['lead']!r} is not a bot with role lead")
    if [b for b, s in bots.items() if s.get("role") == "lead"] != [spec["lead"]]:
        out.append("exactly one bot must have role lead")
    used = {v for k, v in (spec.get("defaults") or {}).items() if k.endswith("_lane")}
    for name, bot in bots.items():
        used.add(bot["lane"])
        used.add((bot.get("delegation") or {}).get("lane"))
        used |= {j["agent"]["lane"] for j in (bot.get("cron") or {}).values() if isinstance(j.get("agent"), dict)}
        if bot["role"] == "worker" and not name.startswith(f"{spec['key']}-"):
            out.append(f"worker {name} must be prefixed {spec['key']}-")
        if set(bot["toolsets"]) & always:
            out.append(f"{name} uses always-disabled toolsets {sorted(set(bot['toolsets']) & always)}")
    for stages in (spec.get("chains") or {}).values():
        used |= {s.get("lane") for s in stages}
        out += [f"chain stage {s['stage']} assignee {s['assignee']} is not a bot"
                for s in stages if s["assignee"] not in bots]
    out += [f"lane {lane!r} is not in model-roles.yaml" for lane in sorted(used - {None}) if lane not in lanes]
    return out


def asset(ctx: Ctx, key: str, *parts: str) -> Path | None:
    return next((d.joinpath(*parts) for d in squad_dirs(ctx, key) if d.joinpath(*parts).exists()), None)


def load_installed(ctx: Ctx) -> dict:
    d = read_yaml(ctx.local / "installed.yaml") or {}
    return {"schema": 1, **{k: d.get(k) or {} for k in ("bots", "lanes", "squads", "projects")}}


def models_from(doc: dict) -> dict:
    """{bots: {name: m}, lanes: {lane: m}} from the installed.yaml shape or model_advisor --json output."""
    def pick(row: dict) -> dict:
        return {k: row[k] for k in ("provider", "model", "reasoning") if row.get(k)}
    if isinstance(doc.get("bots"), list):
        bots = {r["bot"]: pick(r) for r in doc["bots"]}
        lanes: dict = {}
        for row in [*doc["bots"], {"extras": doc.get("shared") or []}]:
            for ex in row.get("extras") or []:
                lanes.setdefault(ex["lane"], pick(ex))
        return {"bots": bots, "lanes": lanes}
    return {"bots": doc.get("bots") or {}, "lanes": doc.get("lanes") or {}}


def model_for(models: dict, lane: str, bot: str | None = None) -> dict | None:
    m = (models["bots"].get(bot) if bot else None) or models["lanes"].get(lane)
    return m if m and m.get("provider") and m.get("model") else None


def tree_sha(path: Path) -> str:
    h = hashlib.sha256()
    for f in sorted(p for p in path.rglob("*") if p.is_file() and p.name != SHA_MARK):
        h.update(str(f.relative_to(path)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def version_ok(req: str, have: str) -> bool:
    m = re.match(r"(>=|>|==|<=|<|~=)\s*(\d+(?:\.\d+)*)", req or "")
    if not m:
        return True
    pad = lambda v: tuple(int(x) for x in v.split("."))  # noqa: E731
    op, want, cur = m.group(1), pad(m.group(2)), pad(have)
    n = max(len(want), len(cur))
    want, cur = want + (0,) * (n - len(want)), cur + (0,) * (n - len(cur))
    return {">=": cur >= want, "~=": cur >= want, ">": cur > want, "==": cur == want, "<=": cur <= want,
            "<": cur < want}[op]


def hermes_version(ctx: Ctx) -> str | None:
    m = re.search(r"v(\d+\.\d+\.\d+)", ctx.hermes("--version", check=False))
    return m.group(1) if m else None


# --- one bot ----------------------------------------------------------------------------------------------------------

def resolve_keep(ctx: Ctx, entry: str) -> tuple[str, str]:
    """(kind, value): dir = an external skills dir, hub = an install identifier, local = a name in the profile."""
    kind, _, name = entry.partition(":")
    hroot = Path(ctx.runtime()[1])
    if kind == "bundled":
        hits = sorted((hroot / "skills").glob(f"*/{name}/SKILL.md"))
        if not hits:
            raise Fail(f"bundled skill not found in {hroot}/skills: {name}")
        return "dir", str(hits[0].parent)
    if kind == "official":
        if not (hroot / "optional-skills" / name / "SKILL.md").is_file():
            raise Fail(f"official skill not found in {hroot}/optional-skills: {name}")
        return "hub", f"official/{name}"
    if kind in ("hub", "local"):
        return kind, name
    raise Fail(f"unknown keep kind: {entry}")


def prune_skills(home: Path, keep: set[str], dry: bool) -> list[str]:
    """Remove every skill dir in the profile except `keep` (names): essential, squad, declared and hub installs."""
    skills = home / "skills"
    if not skills.is_dir():
        return []
    lock = skills / ".hub" / "lock.json"
    keep = keep | (set((json.loads(lock.read_text()).get("installed") or {}) if lock.is_file() else ()))
    removed: list[str] = []
    for entry in sorted(skills.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_symlink():
            removed.append(entry.name)
            if not dry:
                entry.unlink()
            continue
        if not entry.is_dir():
            continue
        children = [entry] if (entry / "SKILL.md").is_file() else [c for c in entry.iterdir() if c.is_dir()]
        for child in children:
            if child.name in keep:
                continue
            removed.append(entry.name if child == entry else f"{entry.name}/{child.name}")
            if not dry:
                shutil.rmtree(child)
        if not dry and entry.is_dir() and not any(entry.rglob("SKILL.md")):
            shutil.rmtree(entry)
    return removed


def sched_matches(job: dict, wanted: str) -> bool:
    sched = job.get("schedule") or {}
    have = {str(sched.get("expr") or ""), str(sched.get("display") or ""), str(job.get("schedule_display") or "")}

    def mins(s: str) -> str:
        m = re.fullmatch(r"every\s+(\d+)\s*([mhd])", s.strip())
        return f"every {int(m.group(1)) * {'m': 1, 'h': 60, 'd': 1440}[m.group(2)]}m" if m else s.strip()
    return mins(wanted) in {mins(h) for h in have if h}


class Applier:
    """Reconciles the bots of one squad. With dry=True it only reads and reports."""

    def __init__(self, ctx: Ctx, spec: dict, models: dict, dry: bool, skip_skills: bool, self_mode: bool):
        self.ctx, self.spec, self.models, self.dry = ctx, spec, models, dry
        self.skip_skills, self.self_mode, self.key = skip_skills, self_mode, spec["key"]
        self.always = load_always_disabled()
        self.defaults = spec.get("defaults") or {}

    # desired state ---------------------------------------------------------------------------------------------

    def bot_model(self, name: str, bot: dict) -> dict | None:
        m = model_for(self.models, bot["lane"], name)
        if not m:
            return None
        entry = self.models["bots"].get(name) or {}
        return {**m, "reasoning": entry.get("reasoning") or bot.get("reasoning") or m.get("reasoning")}

    def lane_model(self, lane: str, reasoning: str | None = None) -> dict | None:
        m = model_for(self.models, lane)
        return {**m, "reasoning": reasoning or m.get("reasoning")} if m else None

    def config_plan(self, name: str, bot: dict, extra_dirs: list[str], notes: list[str]) -> list:
        d, home = self.defaults, self.ctx.home(name)
        toolsets = list(bot["toolsets"])
        plan: list = []
        m = self.bot_model(name, bot)
        if m:
            plan += [["model.provider", m["provider"], False], ["model.default", m["model"], False]]
            if m.get("reasoning"):
                plan.append(["agent.reasoning_effort", m["reasoning"], True])
        else:
            notes.append(f"no model assigned for {name} (lane {bot['lane']})")
        deleg = (bot.get("delegation") or {}).get("lane")
        dm = self.lane_model(deleg) if deleg else None
        if deleg and not dm:
            notes.append(f"no model assigned for lane {deleg} (delegation of {name})")
        plan += [["delegation.provider", dm["provider"] if dm else "", False],
                 ["delegation.model", dm["model"] if dm else "", False],
                 ["delegation.reasoning_effort", (dm or {}).get("reasoning") or "", False]]
        plan += [["platform_toolsets.cli", toolsets, False],
                 ["platform_toolsets.cron", d.get("cron_toolsets") or CRON_TOOLSETS, False],
                 ["agent.disabled_toolsets", sorted(set(self.always) | (MANAGED - set(toolsets))), False]]
        for use, lane in (("aux", d.get("aux_lane", "aux")), ("vision", d.get("vision_lane", "vision"))):
            lm = self.lane_model(lane)
            if not lm:
                notes.append(f"no model assigned for lane {lane} ({use})")
                continue
            for task in (AUX_TASKS if use == "aux" else ("vision",)):
                plan += [[f"auxiliary.{task}.provider", lm["provider"], False],
                         [f"auxiliary.{task}.model", lm["model"], False]]
        skills = bot.get("skills") or {}
        auto = skills.get("auto_load")
        cwd = home if self.self_mode else home / "workspace"
        conn = bot.get("connectors") or {}
        plan += [["skills.auto_load", [auto] if auto else [], False],
                 ["skills.external_dirs", extra_dirs, False],
                 ["terminal.cwd", str(cwd), False],
                 ["terminal.env_passthrough", list(bot.get("passthrough") or []), False],
                 ["tools.connectors.enabled", bool(conn.get("enabled")), False],
                 ["memory.memory_enabled", bool(bot.get("memory")), False],
                 ["memory.user_profile_enabled", bool(bot.get("memory")), False],
                 ["curator.enabled", True, False], ["curator.consolidate", False, False],
                 ["kanban.max_in_progress_per_profile", 1, False]]
        if bot.get("website_blocklist"):
            plan += [["security.website_blocklist.enabled", True, False],
                     ["security.website_blocklist.domains", list(bot["website_blocklist"]), False]]
        return plan

    def missing_models(self, name: str) -> list[str]:
        """Lanes without a model for this bot (its own, delegation, aux, vision, agent cron jobs)."""
        notes: list[str] = []
        self.config_plan(name, self.spec["bots"][name], [], notes)
        self.cron_plan(name, self.spec["bots"][name], notes)
        return [n for n in notes if n.startswith("no model assigned")]

    def ui_meta(self, bot: dict) -> dict:
        meta = {"title": bot["title"], "hidden": bool(bot.get("hidden", bot["role"] == "worker"))}
        if self.spec.get("section"):
            meta |= {"sectionId": self.spec["section"]["id"], "sectionName": self.spec["section"]["name"]}
        return meta

    def cron_plan(self, name: str, bot: dict, notes: list[str]) -> dict:
        jobs = {}
        for job_key, j in (bot.get("cron") or {}).items():
            full = job_key if job_key.startswith(f"{self.key}-") else f"{self.key}-{job_key}"
            args = j.get("args") or []
            args = shlex.split(args) if isinstance(args, str) else list(args)
            agent = j.get("agent")
            want = {"schedule": j["schedule"], "src": j["script"], "args": args, "no_agent": not agent,
                    "script": f"{full}.sh" if args else j["script"], "deliver": f"bot-chat:{self.spec['lead']}"}
            if agent:
                lm = self.lane_model(agent["lane"], agent.get("reasoning"))
                if not lm:
                    notes.append(f"no model assigned for lane {agent['lane']} (cron {full})")
                want |= {"skill": agent["skill"], "lm": lm}
            jobs[full] = want
        return jobs

    # reconcile -------------------------------------------------------------------------------------------------

    def bot(self, name: str) -> dict:
        ctx, bot, dry = self.ctx, self.spec["bots"][name], self.dry
        home = ctx.home(name)
        exists = home.is_dir()
        acts: list[str] = []
        pending: list[str] = []
        notes: list[str] = []
        created = False
        if not exists and self.self_mode:
            install = f"hermes profile install github.com/PuntoyComaTech/hermes-agent-squads --name {name} --alias"
            if not dry:
                raise Fail(f"profile {name} is missing: install it first with `{install}`")
            acts.append(f"profile install ({install})")
            created = True
        elif not exists:
            acts.append("profile create (--no-skills --no-alias)")
            if not dry:
                ctx.hermes("profile", "create", name, "--no-skills", "--no-alias", "--description",
                           bot["description"])
            created = True
        existed = exists
        cfg = (read_yaml(home / "config.yaml") or {}) if exists else {}

        keeps = []
        for entry in (bot.get("skills") or {}).get("keep") or []:
            ident, confirm = (entry, None) if isinstance(entry, str) else (entry["id"], entry["confirm"])
            if confirm and ident not in ctx.confirmed:
                pending.append(f"keep {ident}: {confirm}")
                continue
            keeps.append((ident, *resolve_keep(ctx, ident)))
        extra_dirs = [v for _, k, v in keeps if k == "dir"]

        # config + ui_meta
        sets = self.config_plan(name, bot, extra_dirs, notes)
        diff = pa.changed_keys(cfg, sets)
        meta = self.ui_meta(bot)
        profile_yaml = read_yaml(home / "profile.yaml") if exists else None
        meta_changed = pa.merge_ui_meta(profile_yaml, meta) is not None
        if diff or meta_changed or created:
            if not dry:
                py, hroot = ctx.runtime()
                boot = ("import sys,runpy; sys.path.insert(0, %r); sys._hermes_pin_default_home=True; "
                        "import hermes_bootstrap; runpy.run_path(%r, run_name='__main__')") % (
                            hroot, str(HERE / "_profile_apply.py"))
                p = subprocess.run([py, "-I", "-c", boot], input=json.dumps({"set": sets, "ui_meta_bots": meta}),
                                   capture_output=True, text=True, timeout=300,
                                   env={**os.environ, "HERMES_HOME": str(home)})
                if p.returncode != 0:
                    raise Fail(f"{name}: config failed: {(p.stdout + p.stderr).strip()[-600:]}")
                if any(k == "platform_toolsets.cli" for k, *_ in diff) or created:
                    ctx.hermes("tools", "enable", *bot["toolsets"], profile=name)
        acts += self.describe(diff, created)
        if meta_changed:
            acts.append(f"ui_meta.hermes-bots {meta}")
        if not dry and not (home / "workspace").is_dir() and not self.self_mode:
            (home / "workspace").mkdir(parents=True, exist_ok=True)

        # skills
        if not self.skip_skills:
            acts += self.skills(name, bot, keeps, existed)

        # plugins, mcp
        acts += self.plugins(name, bot, cfg, pending)
        acts += self.mcp(name, bot, cfg)

        # description, SOUL
        if not self.self_mode:
            desc = (profile_yaml or {}).get("description") if exists else None
            if exists and desc != bot["description"]:
                acts.append("profile describe")
                if not dry:
                    ctx.hermes("profile", "describe", name, "--text", bot["description"])
            soul = asset(ctx, self.key, "souls", f"{name}.md")
            if soul and soul.read_text(encoding="utf-8") != _read(home / "SOUL.md"):
                acts.append("SOUL.md updated")
                if not dry:
                    write_text(home / "SOUL.md", soul.read_text(encoding="utf-8"))
        acts += self.cron(name, bot, existed, notes)

        for env in bot.get("passthrough") or []:
            notes.append(f"passthrough {env}: {'set' if os.environ.get(env) else 'missing'}")
        conn = (bot.get("connectors") or {}).get("suggest") or []
        if conn:
            notes.append(f"connectors suggested: {', '.join(conn)}")
        for app in (bot.get("requires") or {}).get("apps") or []:
            if not shutil.which(re.split(r"[<>=~]", app)[0]):
                notes.append(f"app {app} not found on PATH")
        status = "unchanged" if not acts else ("created" if created else "changed")
        if dry and acts:
            status = "would-" + status.removesuffix("d")
        return {"bot": name, "status": status, "actions": acts, "pending": pending, "notes": notes}

    def describe(self, diff: list, created: bool) -> list[str]:
        """Key diff as action lines. A new profile gets one summary line; auxiliary.* keys sharing a change merge."""
        if created:
            got = {k: v for k, _o, v, _f in diff}
            model = f"{got.get('model.provider', '?')}/{got.get('model.default', '?')} {got.get('agent.reasoning_effort', '')}"
            return [f"set {len(diff)} config keys (model {model.strip()})"]
        out, groups = [], {}
        for k, old, new, _f in diff:
            parts = k.split(".")
            if parts[0] == "auxiliary" and len(parts) == 3 and parts[1] != "vision":
                groups.setdefault((parts[2], self._show(old), self._show(new)), []).append(k)
            else:
                out.append(f"set {k}: {self._show(old)} -> {self._show(new)}")
        out += [f"set auxiliary.*.{f}: {o} -> {n} ({len(ks)} keys)" for (f, o, n), ks in groups.items()]
        return out

    @staticmethod
    def _show(v) -> str:
        s = json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v
        return s if len(s) <= 80 else s[:77] + "..."

    def skills(self, name: str, bot: dict, keeps: list, existed: bool) -> list[str]:
        ctx, dry, home = self.ctx, self.dry, self.ctx.home(name)
        acts: list[str] = []
        squad = (bot.get("skills") or {}).get("squad") or []
        if existed and not (home / ".no-bundled-skills").exists():
            acts.append("skills opt-out --remove")
            if not dry:
                ctx.hermes("skills", "opt-out", "--remove", "--yes", profile=name)
        keep = {"hermes-agent", *squad} | {i.rsplit("/", 1)[-1] for _, k, i in keeps if k in ("hub", "local")}
        keep |= {Path(i).name for _, k, i in keeps if k == "dir"}
        if not self.self_mode and existed:
            removed = prune_skills(home, keep, True)
            if removed:
                acts.append(f"skills removed: {len(removed)} ({', '.join(removed[:6])}{'...' if len(removed) > 6 else ''})")
                if not dry:
                    self.backup(name)
                    prune_skills(home, keep, False)
        dest_root = home / "skills" if self.self_mode else home / "skills" / f"squad-{self.key}"
        for skill in squad:
            src = asset(ctx, self.key, "skills", skill)
            if src is None or not (src / "SKILL.md").is_file():
                raise Fail(f"{self.key}: squad skill {skill} has no SKILL.md in {[str(d / 'skills') for d in squad_dirs(ctx, self.key)]}")
            dest = dest_root / skill
            if dest.resolve() == src.resolve():
                continue
            sha = tree_sha(src)
            have = _read(dest / SHA_MARK).strip() if dest.is_dir() else None
            if have == sha:
                continue
            acts.append(f"skill {'~' if dest.is_dir() else '+'} {skill}")
            if not dry:
                if dest.is_dir():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
                write_text(dest / SHA_MARK, sha + "\n")
        lock = home / "skills" / ".hub" / "lock.json"
        installed = set((json.loads(lock.read_text()).get("installed") or {}) if lock.is_file() else ())
        for _ident, kind, value in keeps:
            if kind == "hub" and value.rsplit("/", 1)[-1] not in installed:
                acts.append(f"skills install {value}  [review first: hermes -p {name} skills inspect {value}]")
                if not dry:
                    ctx.hermes("skills", "install", value, "--yes", profile=name)
        return acts

    def backup(self, name: str) -> Path:
        out = self.ctx.local / "backups" / f"{name}-{time.strftime('%Y%m%d-%H%M%S')}.tar.gz"
        out.parent.mkdir(parents=True, exist_ok=True)
        self.ctx.hermes("profile", "export", name, "-o", str(out))
        return out

    def plugins(self, name: str, bot: dict, cfg: dict, pending: list[str]) -> list[str]:
        ctx, home = self.ctx, self.ctx.home(name)
        enabled = set(((cfg.get("plugins") or {}).get("enabled")) or [])
        acts: list[str] = []
        spec = bot.get("plugins") or {}
        for entry in spec.get("enable") or []:
            pname, confirm = (entry, None) if isinstance(entry, str) else (entry["name"], entry["confirm"])
            if pname in enabled:
                continue
            if confirm and pname not in ctx.confirmed:
                pending.append(f"plugin {pname}: {confirm}")
                continue
            bundled = (Path(ctx.runtime()[1]) / "plugins" / pname).is_dir() or (home / "plugins" / pname).is_dir()
            if not bundled and not confirm:
                raise Fail(f"{name}: plugin {pname} is neither bundled nor installed; declare it with a confirm text")
            acts.append(f"plugins {'enable' if bundled else 'install --enable'} {pname}")
            if not self.dry:
                if bundled:
                    ctx.hermes("plugins", "enable", pname, "--no-allow-tool-override", profile=name)
                else:
                    ctx.hermes("plugins", "install", pname, "--enable", profile=name)
        for pname in spec.get("disable") or []:
            if pname in enabled:
                acts.append(f"plugins disable {pname}")
                if not self.dry:
                    ctx.hermes("plugins", "disable", pname, profile=name)
        return acts

    def mcp(self, name: str, bot: dict, cfg: dict) -> list[str]:
        have = set((cfg.get("mcp_servers") or {}).keys())
        acts = []
        for sname, srv in (bot.get("mcp") or {}).items():
            if sname in have:
                continue
            acts.append(f"mcp add {sname}")
            if not self.dry:
                tail = ["--url", srv["url"]] if "url" in srv else ["--command", srv["command"], "--args",
                                                                     *srv.get("args", [])]
                self.ctx.hermes("mcp", "add", sname, *tail, profile=name, stdin="y\n")
        return acts

    def cron(self, name: str, bot: dict, existed: bool, notes: list[str]) -> list[str]:
        ctx, home = self.ctx, self.ctx.home(name)
        want = self.cron_plan(name, bot, notes)
        path = home / "cron" / "jobs.json"
        raw = json.loads(path.read_text()) if existed and path.is_file() else []
        current = {j["name"]: j for j in (raw.get("jobs", []) if isinstance(raw, dict) else raw)}
        acts: list[str] = []
        for jname, w in want.items():
            src = asset(ctx, self.key, "scripts", w["src"]) or ctx.src / "scripts" / w["src"]
            if not src.is_file():
                raise Fail(f"{self.key}: cron script {w['src']} not found in {[str(d / 'scripts') for d in squad_dirs(ctx, self.key)]}")
            body = (f'#!/usr/bin/env bash\nexec {"bash" if w["src"].endswith(".sh") else "python3"} '
                    f'"$(dirname "$0")/{w["src"]}" {shlex.join(w["args"])}\n').replace(" \n", "\n") if w["args"] else None
            files = {w["src"]: src.read_text(encoding="utf-8")}
            if body:
                files[w["script"]] = body
            for fname, text in files.items():
                dest = home / "scripts" / fname
                if dest.is_file() and dest.resolve() == src.resolve():
                    continue
                if _read(dest) != text:
                    acts.append(f"script {'~' if dest.is_file() else '+'} {fname}")
                    if not self.dry:
                        write_text(dest, text, 0o755)
            job, lm = current.get(jname), w.get("lm")
            agent_args = ["--skill", w["skill"], *(["--model", lm["model"], "--provider", lm["provider"],
                          *(["--reasoning-effort", lm["reasoning"]] if lm.get("reasoning") else [])] if lm else [])] \
                if not w["no_agent"] else []
            flags = ["--script", w["script"], "--deliver", w["deliver"], *(["--no-agent"] if w["no_agent"] else []),
                     *agent_args]
            if job is None:
                acts.append(f"cron + {jname}")
                if not self.dry:
                    ctx.hermes("cron", "create", w["schedule"], "--name", jname, *flags, profile=name)
            elif not self.job_matches(job, w, lm):
                acts.append(f"cron ~ {jname}")
                if not self.dry:
                    ctx.hermes("cron", "edit", job["id"], "--schedule", w["schedule"], *flags,
                               *([] if w["no_agent"] else ["--agent"]), profile=name)
        for jname, job in current.items():
            if jname.startswith(f"{self.key}-") and jname not in want:
                acts.append(f"cron - {jname}")
                if not self.dry:
                    ctx.hermes("cron", "remove", job["id"], profile=name)
        return acts

    @staticmethod
    def job_matches(job: dict, w: dict, lm: dict | None) -> bool:
        ok = (sched_matches(job, w["schedule"]) and job.get("script") == w["script"]
              and bool(job.get("no_agent")) == w["no_agent"] and job.get("deliver") == w["deliver"])
        if ok and not w["no_agent"] and lm:
            ok = (job.get("model") == lm["model"] and job.get("provider") == lm["provider"]
                  and (job.get("skills") or []) == [w["skill"]]
                  and (not lm.get("reasoning") or job.get("reasoning_effort") == lm["reasoning"]))
        return ok


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""


# --- commands ---------------------------------------------------------------------------------------------------------

def ensure_board(ctx: Ctx, spec: dict, dry: bool) -> str:
    board = spec.get("board")
    if not board:
        return "none"
    out = ctx.hermes("kanban", "boards", "list", "--json", check=False)
    try:
        live = {b["slug"] for b in json.loads(out) if not b.get("archived")}
    except ValueError:
        live = set()
    if board["slug"] in live:
        return "exists"
    if not dry:
        flags = [f"--{k}={board[k]}" for k in ("icon", "color", "description") if board.get(k)]
        ctx.hermes("kanban", "boards", "create", board["slug"], "--name", board["name"], *flags)
    return "would-create" if dry else "created"


def effective_models(ctx: Ctx, models_file: str | None) -> tuple[dict, dict]:
    installed = load_installed(ctx)
    models = models_from(installed)
    if models_file:
        extra = models_from(read_yaml(Path(models_file)) or {})
        models = {k: {**models[k], **extra[k]} for k in models}
    return installed, models


def run_apply(ctx: Ctx, a: argparse.Namespace, dry: bool) -> dict:
    if bool(a.squad) == bool(a.self_mode):
        raise Fail("give a squad key or --self")
    key = "builder" if a.self_mode else a.squad
    spec = load_spec(ctx, key)
    installed, models = effective_models(ctx, a.models)
    if not dry:
        ver = hermes_version(ctx)
        if ver and not version_ok(spec.get("hermes_requires", ""), ver):
            raise Fail(f"{key} needs Hermes {spec['hermes_requires']}, found {ver}")
    names = [spec["lead"], *[b for b in spec["bots"] if b != spec["lead"]]]
    if a.bots:
        wanted = [b for b in a.bots.split(",") if b]
        if set(wanted) - set(names):
            raise Fail(f"not in {key}: {sorted(set(wanted) - set(names))}")
        names = [b for b in names if b in wanted]
    ap = Applier(ctx, spec, models, dry, a.skip_skills, a.self_mode)
    unassigned = sorted({n for name in names for n in ap.missing_models(name)})
    if unassigned and not dry:
        raise Fail("; ".join(unassigned) + ". Run scripts/model_advisor.py, then pass --models <file>.", 2)
    board = "none" if a.self_mode else ensure_board(ctx, spec, dry)
    bots = [ap.bot(n) for n in names]
    counts: dict[str, int] = {}
    for b in bots:
        counts[b["status"]] = counts.get(b["status"], 0) + 1
    if not dry:
        old = installed["squads"].get(key) or {}
        rec = {"version": spec["version"], "bots": list(spec["bots"]), "board": (spec.get("board") or {}).get("slug"),
               "applied": old.get("applied")}
        if any(b["actions"] for b in bots) or old.get("version") != spec["version"]:
            rec["applied"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        new = {**installed, "squads": {**installed["squads"], key: rec}}
        new["bots"], new["lanes"] = models["bots"], models["lanes"]
        if new != load_installed(ctx):
            write_yaml(ctx.local / "installed.yaml", new)
    rows = [{k: v for k, v in b.items() if v or k in ("bot", "status")} for b in bots]
    return {"squad": key, "dry_run": dry, "board": board, "summary": counts, "bots": rows}


def cmd_apply(ctx: Ctx, a: argparse.Namespace, force_dry: bool = False) -> int:
    emit(ctx, run_apply(ctx, a, force_dry or a.dry_run))
    return 0


def cmd_status(ctx: Ctx, a: argparse.Namespace) -> int:
    installed, models = effective_models(ctx, None)
    keys = [a.squad] if a.squad else sorted(installed["squads"])
    out = []
    for key in keys:
        spec = load_spec(ctx, key)
        ap = Applier(ctx, spec, models, True, False, key == "builder")
        rows = []
        for name in spec["bots"]:
            home = ctx.home(name)
            if not home.is_dir():
                rows.append({"bot": name, "state": "missing", "model": "-", "drift": 0})
                continue
            r = ap.bot(name)
            cfg = read_yaml(home / "config.yaml") or {}
            rows.append({"bot": name, "state": "ok" if r["status"] == "unchanged" else "drift",
                         "model": (cfg.get("model") or {}).get("default") or "-", "drift": len(r["actions"])})
        rec = installed["squads"].get(key) or {}
        out.append({"squad": key, "installed": rec.get("version") or "no", "repo": spec["version"],
                    "board": ensure_board(ctx, spec, True) if spec.get("board") else "none", "bots": rows})
    emit(ctx, {"installed": len(installed["squads"]), "available": available_squads(ctx), "squads": out})
    return 0


def check(name: str, status: str, detail: str) -> dict:
    return {"check": name, "status": status, "detail": detail}


def cmd_doctor(ctx: Ctx, a: argparse.Namespace) -> int:
    out = []
    ver = hermes_version(ctx) if shutil.which("hermes") else None
    out.append(check("hermes", "ok" if ver else "fail", f"v{ver}" if ver else "not found on PATH"))
    out.append(check("builder", "ok" if ctx.home(ctx.builder).is_dir() else "warn",
                     str(ctx.home(ctx.builder)) if ctx.home(ctx.builder).is_dir() else "profile missing"))
    out.append(check("desktop-kanban", "info", "enable Capabilities > Plugins > Kanban to see the boards; "
                     "the dispatcher runs in the gateway regardless (not readable from the CLI)"))
    if ver:
        listing = ctx.hermes("profile", "list", check=False)
        running = any("running" in ln.split() for ln in listing.splitlines() if ln.strip().lstrip("\u25c6 ").startswith("default"))
        out.append(check("gateway", "ok" if running else "warn", "default profile gateway "
                         + ("running" if running else "not running: kanban cards will not be dispatched")))
    installed = load_installed(ctx)
    _i, models = effective_models(ctx, None)
    now = time.time()
    for key in sorted(installed["squads"]):
        try:
            spec = load_spec(ctx, key)
        except Fail as e:
            out.append(check(f"{key}:spec", "fail", str(e)))
            continue
        ap = Applier(ctx, spec, models, True, False, key == "builder")
        for name, bot in spec["bots"].items():
            miss = ap.missing_models(name)
            out.append(check(f"{name}:models", "warn" if miss else "ok", "; ".join(miss) or "assigned"))
            for env in bot.get("passthrough") or []:
                out.append(check(f"{name}:{env}", "ok" if os.environ.get(env) else "warn",
                                 "set" if os.environ.get(env) else "missing in this environment"))
            for app in (bot.get("requires") or {}).get("apps") or []:
                found = shutil.which(re.split(r"[<>=~]", app)[0])
                out.append(check(f"{name}:app:{app}", "ok" if found else "warn", found or "not found on PATH"))
        slug = (spec.get("board") or {}).get("slug")
        if slug and ver:
            try:
                cards = json.loads(ctx.hermes("kanban", "--board", slug, "list", "--json", check=False) or "[]")
            except ValueError:
                cards = []
            stale = [c["id"] for c in cards if c.get("status") in ("blocked", "running")
                     and now - float(c.get("started_at") or c.get("created_at") or now) > STALE_SECONDS]
            out.append(check(f"{key}:cards", "warn" if stale else "ok",
                             f"stale over 24h: {', '.join(stale)}" if stale else "no stale cards"))
    emit(ctx, {"ok": not any(c["status"] == "fail" for c in out), "checks": out})
    return 1 if any(c["status"] == "fail" for c in out) else 0


def cmd_uninstall(ctx: Ctx, a: argparse.Namespace) -> int:
    if a.squad == "builder":
        raise Fail("refusing to uninstall the builder: use `hermes profile delete builder`")
    spec = load_spec(ctx, a.squad)
    installed, models = effective_models(ctx, None)
    ap = Applier(ctx, spec, models, a.dry_run, False, False)
    rows = []
    for name in spec["bots"]:
        home = ctx.home(name)
        if not home.is_dir():
            rows.append({"bot": name, "actions": ["profile absent"]})
            continue
        acts = ["profile export"]
        if not a.dry_run:
            ap.backup(name)
        path = home / "cron" / "jobs.json"
        raw = json.loads(path.read_text()) if path.is_file() else []
        for job in (raw.get("jobs", []) if isinstance(raw, dict) else raw):
            if job["name"].startswith(f"{a.squad}-"):
                acts.append(f"cron - {job['name']}")
                if not a.dry_run:
                    ctx.hermes("cron", "remove", job["id"], profile=name)
        if not a.keep_profiles:
            acts.append("profile delete")
            if not a.dry_run:
                ctx.hermes("profile", "delete", name, "--yes")
        rows.append({"bot": name, "actions": acts})
    board = (spec.get("board") or {}).get("slug")
    if board:
        live = {b["slug"] for b in json.loads(ctx.hermes("kanban", "boards", "list", "--json", check=False) or "[]")}
        if board in live and not a.dry_run:
            ctx.hermes("kanban", "boards", "rm", board)
    if not a.dry_run:
        installed["squads"].pop(a.squad, None)
        for proj in installed["projects"].values():
            proj["squads"] = [s for s in proj.get("squads", []) if s != a.squad]
        installed["bots"], installed["lanes"] = models["bots"], models["lanes"]
        write_yaml(ctx.local / "installed.yaml", installed)
    emit(ctx, {"squad": a.squad, "dry_run": a.dry_run, "board": f"archive {board}" if board else "none",
               "backups": str(ctx.local / "backups"), "projects": "untouched", "bots": rows})
    return 0


def cmd_project_add(ctx: Ctx, a: argparse.Namespace) -> int:
    spec = load_spec(ctx, a.squad)
    path = Path(a.path).expanduser().absolute()
    if not path.is_dir():
        raise Fail(f"project path is not a directory: {path}")
    slug = slugify(a.name)
    board = (spec.get("board") or {}).get("slug")
    rows = []
    for name in spec["bots"]:
        if not ctx.home(name).is_dir():
            rows.append({"bot": name, "result": "profile missing"})
            continue
        listing = ctx.hermes("project", "list", "--all", check=False, profile=name)
        if any(ln.replace("*", " ", 1).split()[:1] == [slug] for ln in listing.splitlines()):
            rows.append({"bot": name, "result": "exists"})
            continue
        if not a.dry_run:
            ctx.hermes("project", "create", a.name, str(path), "--slug", slug, *(["--board", board] if board else []),
                       profile=name)
        rows.append({"bot": name, "result": "would-create" if a.dry_run else "created"})
    if not a.dry_run and any(r["result"] in ("created", "exists") for r in rows):
        installed, models = effective_models(ctx, None)
        proj = installed["projects"].get(slug) or {"name": a.name, "path": str(path), "squads": []}
        proj["squads"] = sorted({*proj.get("squads", []), a.squad})
        installed["projects"][slug] = proj
        installed["bots"], installed["lanes"] = models["bots"], models["lanes"]
        write_yaml(ctx.local / "installed.yaml", installed)
    emit(ctx, {"squad": a.squad, "project": slug, "path": str(path), "dry_run": a.dry_run, "bots": rows})
    return 1 if any(r["result"] == "profile missing" for r in rows) else 0


def cmd_chain(ctx: Ctx, a: argparse.Namespace) -> int:
    spec = load_spec(ctx, a.squad)
    stages = (spec.get("chains") or {}).get(a.chain)
    if stages is None:
        raise Fail(f"{a.squad} has no chain {a.chain!r}; chains: {', '.join(spec.get('chains') or {}) or 'none'}")
    try:
        import kanban_chain  # scripts/kanban_chain.py files the cards, idempotently
    except ImportError:
        kanban_chain = None
    if kanban_chain is not None:
        argv = [a.squad, a.chain, "--project", a.project, "--title", a.title, "--squads-dir", str(ctx.src / "squads"),
                "--home", str(ctx.local.parent), "--hermes-root", str(ctx.root)]
        for flag, val in (("--body", a.body), ("--when", a.when), ("--run-id", a.run_id), ("--workspace", a.workspace)):
            argv += [flag, val] if val else []
        return kanban_chain.main(argv + [x for x, on in (("--dry-run", a.dry_run), ("--json", ctx.json)) if on])
    if not a.dry_run:
        raise Fail("scripts/kanban_chain.py is missing from this checkout; `chain --dry-run` still shows the stages", 3)
    live = [s for s in stages if not s.get("when") or s["when"] in set(filter(None, (a.when or "").split(",")))]
    cards = [{"stage": s["stage"], "assignee": s["assignee"], "skill": s.get("skill") or "-",
              "parent": live[i - 1]["stage"] if i else "-"} for i, s in enumerate(live)]
    emit(ctx, {"squad": a.squad, "chain": a.chain, "dry_run": True, "executor": "stub", "title": a.title,
               "project": a.project, "cards": cards})
    return 0


# --- cli --------------------------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", help="JSON output instead of TOON")
    common.add_argument("--hermes-root", help="Hermes root (default: HERMES_HOME without /profiles/<name>, else ~/.hermes)")
    common.add_argument("--src", help="repo or distribution root holding squads/ and builder.yaml (default: this checkout)")
    common.add_argument("--local", help="builder local/ dir (default: <root>/profiles/<builder>/local)")
    common.add_argument("--builder", default="builder", help="builder profile name (default: builder)")
    p = argparse.ArgumentParser(prog="squadctl", description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__.split("\n\n", 1)[1])
    sub = p.add_subparsers(dest="cmd", required=True, metavar="command")

    def apply_args(sp):
        sp.add_argument("squad", nargs="?", help="squad key")
        sp.add_argument("--self", dest="self_mode", action="store_true", help="the builder itself (builder.yaml)")
        sp.add_argument("--bots", help="comma-separated subset of bots")
        sp.add_argument("--models", metavar="FILE", help="models file (installed.yaml shape or model_advisor --json)")
        sp.add_argument("--skip-skills", action="store_true", help="config only; leave the skills dirs alone")
        sp.add_argument("--confirm", action="append", metavar="ID",
                        help="install this keep or plugin that needs the user's OK (repeatable)")
    sp = sub.add_parser("plan", parents=[common], help="show what apply would change (reads only)")
    apply_args(sp)
    sp.set_defaults(fn=lambda c, a: cmd_apply(c, a, True), dry_run=True)
    sp = sub.add_parser("apply", parents=[common], help="create or update the squad's profiles")
    apply_args(sp)
    sp.add_argument("--dry-run", action="store_true", help="same as plan")
    sp.set_defaults(fn=cmd_apply)
    sp = sub.add_parser("status", parents=[common], help="installed squads against the live profiles")
    sp.add_argument("squad", nargs="?")
    sp.set_defaults(fn=cmd_status)
    sp = sub.add_parser("doctor", parents=[common], help="check hermes, gateway, apps, models, passthrough, stale cards")
    sp.set_defaults(fn=cmd_doctor)
    sp = sub.add_parser("uninstall", parents=[common], help="export, remove cron, delete profiles, archive the board")
    sp.add_argument("squad")
    sp.add_argument("--keep-profiles", action="store_true")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(fn=cmd_uninstall)
    sp = sub.add_parser("project", parents=[common], help="project commands")
    psub = sp.add_subparsers(dest="pcmd", required=True, metavar="action")
    pp = psub.add_parser("add", parents=[common], help="create the project in the lead and every worker")
    pp.add_argument("squad")
    pp.add_argument("name")
    pp.add_argument("path")
    pp.add_argument("--dry-run", action="store_true")
    pp.set_defaults(fn=cmd_project_add)
    sp = sub.add_parser("chain", parents=[common], help="file the dependent cards of a squad chain")
    sp.add_argument("squad")
    sp.add_argument("chain")
    sp.add_argument("--project", required=True, help="project slug")
    sp.add_argument("--title", required=True)
    sp.add_argument("--when", default="", help="comma list of conditions that enable `when:` stages")
    sp.add_argument("--body", default="")
    sp.add_argument("--run-id", help="idempotency run id (default: slug of the title)")
    sp.add_argument("--workspace")
    sp.add_argument("--dry-run", action="store_true")
    sp.set_defaults(fn=cmd_chain)
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    ctx = Ctx(a)
    try:
        return a.fn(ctx, a)
    except Fail as e:
        if ctx.json:
            print(json.dumps({"error": str(e), "code": e.code}))
        else:
            print(f"error: {e}", file=sys.stderr)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
