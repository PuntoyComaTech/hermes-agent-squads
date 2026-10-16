#!/usr/bin/env python3
"""squadctl: plan, apply, inspect and remove Hermes squads. Idempotent: read state, diff, write only the difference.

Reads squads/<key>/squad.yaml (builder.yaml for --self), the overlay local/squads/<key>/squad.yaml and the models
in local/installed.yaml (bots: and lanes: maps of provider/model/reasoning). --models <file> merges the same shape
or `scripts/hpy model_advisor.py --json` output, and a real apply saves it. Licence or disclosure items stay pending
until `--confirm <id>`. Output is TOON, JSON with --json. Config writes go through Hermes's own writer, one process
per profile (_profile_apply.py). Never prints secret values: `apply --yes` copies a provider key into the bot's env
file (mode 600, name+value, value never shown; C-14) and passthrough shows names and set/missing only.
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
PLUGIN_MANIFESTS = ("plugin.yaml", "plugin.yml")


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
            raise Fail("no YAML module: run scripts/hpy squadctl.py or scripts/squadctl (Hermes runtime) or install PyYAML") from None
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


ENV_FILE = ".env"  # the per-profile env file `apply --yes` writes (C-14); values never reach output


def env_pairs(path: Path) -> dict[str, str]:
    """`KEY -> value` of one env file's own assignments (`export KEY=value`, optional quotes).

    Values exist only inside the credential helpers (env_pairs, env_set, Applier.key_value): every output path
    names keys, never values (C-14)."""
    out: dict[str, str] = {}
    for line in _read(path).splitlines():
        bare = line.strip()
        if not bare or bare.startswith("#") or "=" not in bare:
            continue
        if bare.startswith("export "):
            bare = bare[len("export "):]
        key, _, value = bare.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            out[key] = value
    return out


def env_names(path: Path) -> set[str]:
    return set(env_pairs(path))


def env_set(path: Path, key: str, value: str) -> None:
    """Set KEY=value in an env file (mode 600), keeping every other line exactly as it is."""
    lines = _read(path).splitlines() if path.is_file() else []
    row = f"{key}={value}"
    out: list[str] = []
    hit = False
    for line in lines:
        bare = line.strip().removeprefix("export ").split("=", 1)[0].strip()
        if bare == key and not line.strip().startswith("#"):
            out.append(row)
            hit = True
        else:
            out.append(line)
    if not hit:
        out.append(row)
    write_text(path, "\n".join(out) + "\n", 0o600)


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
        self._vision: dict[tuple[str, str], bool] = {}
        self._env_keys: dict[str, list[str]] = {}
        self.confirmed = set(getattr(a, "confirm", None) or [])
        self.yes = bool(getattr(a, "yes", False))  # `apply --yes`: the owner's OK for the credential copy (C-14)

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

    def sees_images(self, provider: str, model: str) -> bool:
        """True when Hermes routes images to this model natively (agent.image_routing, `auto` mode, no
        auxiliary.vision). False when it is text-only or the runtime cannot tell."""
        key = (provider, model)
        if key not in self._vision:
            py, hroot = self.runtime()
            code = ("import json, sys; sys.path.insert(0, %r); sys._hermes_pin_default_home = True; "
                    "import hermes_bootstrap; from agent.image_routing import decide_image_input_mode as d; "
                    "print(json.dumps(d(sys.argv[1], sys.argv[2], {}) == 'native'))") % hroot
            try:
                p = subprocess.run([py, "-I", "-c", code, provider, model], capture_output=True, text=True,
                                   timeout=120, stdin=subprocess.DEVNULL, env={**os.environ, "HERMES_HOME": str(self.root)})
                self._vision[key] = p.returncode == 0 and p.stdout.strip().splitlines()[-1:] == ["true"]
            except (OSError, subprocess.SubprocessError):
                self._vision[key] = False
        return self._vision[key]

    def provider_env_keys(self, provider: str) -> list[str]:
        """Env var names this provider reads its API key from, in priority order (PROVIDER_REGISTRY).

        The registry is the only authority: a plugin provider declares its own names (ANTHROPIC_API_KEY,
        CLAUDE_CODE_OAUTH_TOKEN, ...). An empty list means the provider needs no API key (OAuth or an external
        process); `<PROVIDER>_API_KEY` is guessed only when the registry does not know the provider.
        """
        if provider not in self._env_keys:
            keys: list[str] | None = None
            try:
                py, hroot = self.runtime()
                code = ("import json, sys; sys.path.insert(0, %r); sys._hermes_pin_default_home = True; "
                        "import hermes_bootstrap; from hermes_cli.auth import PROVIDER_REGISTRY as R; "
                        "p = R.get(sys.argv[1]); "
                        "print(json.dumps(list(getattr(p, 'api_key_env_vars', ()) or []) if p else None))") % hroot
                p = subprocess.run([py, "-I", "-c", code, provider], capture_output=True, text=True, timeout=60,
                                   stdin=subprocess.DEVNULL, env={**os.environ, "HERMES_HOME": str(self.root)})
                keys = json.loads(p.stdout.strip().splitlines()[-1]) if p.returncode == 0 and p.stdout.strip() else None
            except (OSError, ValueError, Fail, subprocess.SubprocessError):
                keys = None
            names = [k for k in keys if isinstance(k, str) and k] if isinstance(keys, list) else []
            if keys is None:  # provider unknown to the registry: the conventional name is the only hint
                names = [f"{re.sub(r'[^A-Za-z0-9]', '_', provider).upper()}_API_KEY"]
            self._env_keys[provider] = names
        return self._env_keys[provider]

    def apply_config(self, home: Path, payload: dict) -> None:
        """One write pass per home through Hermes's own config writer (_profile_apply.py)."""
        py, hroot = self.runtime()
        boot = ("import sys,runpy; sys.path.insert(0, %r); sys._hermes_pin_default_home=True; "
                "import hermes_bootstrap; runpy.run_path(%r, run_name='__main__')") % (
            hroot, str(HERE / "_profile_apply.py"))
        p = subprocess.run([py, "-I", "-c", boot], input=json.dumps(payload),
                           capture_output=True, text=True, timeout=300,
                           env={**os.environ, "HERMES_HOME": str(home)})
        if p.returncode != 0:
            raise Fail(f"{home.name}: config failed: {(p.stdout + p.stderr).strip()[-600:]}")


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


def rename_builder_bot(spec: dict, name: str) -> dict:
    """The builder's profile is whatever `--builder` names (`hermes profile install --name X`); builder.yaml names
    the bot `builder`, so the bot key and the manager follow the profile name. The squad key stays `builder`."""
    manager = spec.get("manager")
    bots = spec.get("bots") or {}
    if manager and manager in bots and manager != name:
        return {**spec, "manager": name, "bots": {name if b == manager else b: v for b, v in bots.items()}}
    return spec


def dist_version(ctx: Ctx) -> str:
    """The distribution version (distribution.yaml -> version): the single source of truth of the release.

    The builder manifest carries no version of its own (C-13); squad manifests keep theirs for drift detection
    against local/installed.yaml."""
    v = str((read_yaml(ctx.src / "distribution.yaml") or {}).get("version") or "")
    if not re.fullmatch(r"\d+\.\d+\.\d+", v):
        raise Fail("distribution.yaml has no x.y.z version")
    return v


def load_spec(ctx: Ctx, key: str) -> dict:
    repo = ctx.src / ("builder.yaml" if key == "builder" else f"squads/{key}/squad.yaml")
    base = read_yaml(repo)
    over = read_yaml(ctx.local / "squads" / key / "squad.yaml")
    if base is None and over is None:
        raise Fail(f"unknown squad {key!r}; available: {', '.join(available_squads(ctx)) or 'none'}")
    spec = deep_merge(base, over) if base is not None and over is not None else (base or over)
    if key == "builder":
        spec = rename_builder_bot(spec, ctx.builder)
        # One version for the distribution (C-13): injected here so status, plan and installed.yaml all read it.
        spec["version"] = dist_version(ctx)
    problems = validate_spec(ctx, spec, key)
    if problems:
        raise Fail(f"invalid squad {key}: " + "; ".join(p[:160] for p in problems[:6])
                   + (f"; and {len(problems) - 6} more" if len(problems) > 6 else ""))
    return spec


def validate_spec(ctx: Ctx, spec: dict, key: str) -> list[str]:
    """Cross-field rules of the schema (docs/decisions.md C-01); the full JSON schema runs when jsonschema exists."""
    if "lead" in spec and "manager" not in spec:
        return ["field 'lead' was renamed to 'manager' (C-11): update the manifest and the bot roles"]
    out: list[str] = []
    try:
        import jsonschema
        schema = json.loads((ctx.src / "squads" / "_schema" / "squad.schema.json").read_text())
        out += [f"{'/'.join(map(str, e.absolute_path)) or '.'}: {e.message}"
                for e in jsonschema.Draft202012Validator(schema).iter_errors(spec)]
    except (ImportError, OSError):
        for field in ("schema", "key", "name", "manager", "bots"):
            if field not in spec:
                out.append(f"missing {field}")
    if out:
        return out
    if key != "builder" and not re.fullmatch(r"\d+\.\d+\.\d+", str(spec.get("version") or "")):
        # only the builder manifest is versionless: its version is injected from distribution.yaml (C-13)
        out.append("missing version (x.y.z)")
    bots, lanes, always = spec["bots"], load_roles(ctx), set(load_always_disabled())
    if spec["key"] != key:
        out.append(f"key {spec['key']!r} does not match {key!r}")
    if spec["manager"] not in bots or bots[spec["manager"]].get("role") != "manager":
        out.append(f"manager {spec['manager']!r} is not a bot with role manager")
    if [b for b, s in bots.items() if s.get("role") == "manager"] != [spec["manager"]]:
        out.append("exactly one bot must have role manager")
    if len([b for b, s in bots.items() if not s.get("optional")]) > 5:
        out.append("at most 5 required bots; extra bots must set optional: true")
    if key != "builder":
        # manager naming (C-11): the manager's profile name is the squad key, its title '<Name> manager'
        if spec["manager"] != spec["key"]:
            out.append(f"manager {spec['manager']!r} must be named {spec['key']!r}")
        want = f"{spec.get('name') or key} manager"
        if (bots.get(spec["manager"]) or {}).get("title") != want:
            out.append(f"manager title must be {want!r}")
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


def live_bots(ctx: Ctx, spec: dict) -> list[str]:
    """Bots a live-state command (status, doctor, uninstall, project add) reports on: every required bot,
    plus an optional bot once its profile exists (optional bots install only via `apply --with`)."""
    return [b for b, s in spec["bots"].items() if not s.get("optional") or ctx.home(b).is_dir()]


def asset(ctx: Ctx, key: str, *parts: str) -> Path | None:
    return next((d.joinpath(*parts) for d in squad_dirs(ctx, key) if d.joinpath(*parts).exists()), None)


def load_installed(ctx: Ctx) -> dict:
    d = read_yaml(ctx.local / "installed.yaml") or {}
    return {"schema": 1, **{k: d.get(k) or {} for k in ("bots", "lanes", "squads", "projects")}}


def models_from(doc: dict) -> dict:
    """{bots: {name: m}, lanes: {lane: m}} from the installed.yaml shape or model_advisor --json output."""
    def pick(row: dict) -> dict:
        return {k: row[k] for k in ("provider", "model", "reasoning") if row.get(k)}
    if isinstance(doc.get("squads"), list):  # model_advisor --json: {squads: [{key, bots, shared}], lanes: [...]}
        doc = {"bots": [b for s in doc["squads"] for b in s.get("bots") or []],
               "shared": [x for s in doc["squads"] for x in s.get("shared") or []], "lanes": doc.get("lanes")}
    if isinstance(doc.get("bots"), list) or isinstance(doc.get("lanes"), list):
        rows = doc.get("bots") or []
        bots = {r["bot"]: pick(r) for r in rows}
        lanes: dict = {}
        for row in [*rows, {"extras": [*(doc.get("shared") or []), *(doc.get("lanes") or [])]}]:
            if row.get("lane"):
                lanes.setdefault(row["lane"], pick(row))
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


def plugin_manifest(plugin_dir: Path) -> dict:
    for fname in PLUGIN_MANIFESTS:
        data = read_yaml(plugin_dir / fname)
        if isinstance(data, dict):
            return data
    return {}


def plugin_key(plugin_dir: Path, plugins_root: Path) -> str:
    """Canonical `plugins.enabled` key of one plugin dir (mirrors hermes_cli.plugins_cmd._read_manifest_info):
    a nested dir keys by its path (`model-providers/<name>`), a flat one by its manifest name."""
    rel = plugin_dir.relative_to(plugins_root)
    if len(rel.parts) > 1:
        return "/".join(rel.parts)
    return str(plugin_manifest(plugin_dir).get("name") or plugin_dir.name)


def provider_plugins(plugins_root: Path) -> dict[str, Path]:
    """Provider plugins installed in ONE profile home: provider directory name -> dir.

    Both layouts `providers/__init__._scan_home_layer` loads: `<plugins>/model-providers/<name>/`, and a flat
    `<plugins>/<name>/` declaring `kind: model-provider` (where `hermes plugins install` clones).
    """
    out: dict[str, Path] = {}
    nested = plugins_root / "model-providers"
    if nested.is_dir():
        out |= {d.name: d for d in sorted(nested.iterdir()) if d.is_dir() and not d.name.startswith(("_", "."))}
    if plugins_root.is_dir():
        for d in sorted(plugins_root.iterdir()):
            if (d.is_dir() and d.name != "model-providers" and not d.name.startswith(("_", "."))
                    and plugin_manifest(d).get("kind") == "model-provider"):
                out.setdefault(d.name, d)
    return out


def provider_source(ctx: "Ctx", provider: str) -> tuple[Path, Path] | None:
    """(plugin dir, home that holds it) for a user-installed provider plugin: the builder profile first, then
    the root home. Bundled providers (`<hermes>/plugins/model-providers/`) load everywhere and return None."""
    for owner in (ctx.home(ctx.builder), ctx.root):
        src = provider_plugins(owner / "plugins").get(provider)
        if src is not None:
            return src, owner
    return None


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


# App locations `shutil.which` misses (GUI apps on macOS).
APP_MAC_PATHS = {"blender": "/Applications/Blender.app/Contents/MacOS/Blender"}

# npm-packaged CLIs: when one is not on PATH, `npx --no-install` runs the project-local or cached copy and
# never downloads anything, so a hit there proves the CLI is reachable from this machine.
APP_NPX = frozenset({"wrangler"})

# Stored logins `doctor` reports on: app -> (arguments, what the user runs once to log in). Only these apps are
# probed, and only their exit status is read: a probe's output carries accounts and, with the wrong flag, tokens.
APP_LOGINS = {"cf": (["auth", "whoami"], "cf auth login"),
              "wrangler": (["whoami"], "wrangler login"),
              "gh": (["auth", "status"], "gh auth login"),
              "vercel": (["whoami"], "vercel login")}


def run_quiet(argv: list[str], timeout: int = 60) -> subprocess.CompletedProcess | None:
    """The finished command, or None when it cannot run here (missing binary, timeout). No output is used."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None


def app_launcher(name: str) -> list[str] | None:
    """argv that runs a required app here: its PATH location or the macOS app path, else `npx --no-install`
    for an npm-packaged CLI (proved with `--version`, so the launcher really resolves). None when missing."""
    if shutil.which(name):
        return [name]
    mac = APP_MAC_PATHS.get(name)
    if mac and Path(mac).is_file():
        return [mac]
    if name in APP_NPX and shutil.which("npx"):
        argv = ["npx", "--no-install", name]
        if run_quiet([*argv, "--version"]):
            return argv
    return None


def find_app(spec: str) -> tuple[str | None, str | None]:
    """(how it runs, version) of a `requires.apps` entry like `blender>=5.1`. The version is read with
    `--version` only when the entry pins one; an unparsable version is reported, never guessed."""
    name = re.split(r"[<>=~]", spec)[0].strip()
    want = spec[len(name):].strip()
    argv = app_launcher(name)
    version = None
    if argv and want:
        done = run_quiet([*argv, "--version"], 60)
        hit = re.search(r"(\d+(?:\.\d+){1,2})", ((done.stdout or "") + (done.stderr or "")) if done else "")
        version = hit.group(1) if hit else None
    return (" ".join(argv) if argv else None, version)


def app_problem(spec: str) -> str | None:
    """One note when a required app is missing or does not satisfy its version pin; None when fine."""
    name = re.split(r"[<>=~]", spec)[0].strip()
    want = spec[len(name):].strip()
    how, version = find_app(spec)
    if not how:
        where = "PATH, the macOS app path or npx" if name in APP_NPX else "PATH or the macOS app path"
        return f"app {spec} not found ({where})"
    if want and version is None:
        return f"app {name} runs as `{how}` but `--version` gave no parsable version (need {want})"
    if want and version and not version_ok(want, version):
        return f"app {name} {version} (as `{how}`) does not satisfy {spec}"
    return None


def login_probe(name: str) -> tuple[str, str]:
    """(status, detail) for a required CLI's stored login: ok, warn when it is not logged in, info when the
    probe cannot run here. Only the exit status is read, never the output (`gh auth status` prints the account
    and a masked token; cf and wrangler print account identifiers). Deploys use these logins (D-036)."""
    probe = APP_LOGINS.get(name)
    argv = app_launcher(name) if probe else None
    if not probe or not argv:
        return "info", f"{name}: no login check (no probe for this app, or it is not installed)"
    hint = probe[1]
    done = run_quiet([*argv, *probe[0]], 45)
    if done is None:
        return "info", f"{name} login not verified here: run `{hint}` once"
    if done.returncode == 0:
        return "ok", "logged in"
    return "warn", f"not logged in: run `{hint}` once (no credentials stored, or no network)"


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

    def config_plan(self, name: str, bot: dict, extra_dirs: list[str], notes: list[str],
                    live: dict | None = None) -> list:
        d, home = self.defaults, self.ctx.home(name)
        toolsets = list(bot["toolsets"])
        plan: list = []
        m = self.bot_model(name, bot)
        if m:
            plan += [["model.provider", m["provider"], False], ["model.default", m["model"], False]]
            if m.get("reasoning"):
                plan.append(["agent.reasoning_effort", m["reasoning"], True])
            if live is not None and (live.get("model") or {}).get("provider") != m["provider"]:
                # A provider switch re-points `model:`; base_url/api_mode are route state of the OLD provider and
                # the runtime honours them for whatever provider the block now names, so a stale route (a
                # `process://` base_url inherited from the gateway root config) posts the new provider's key to
                # the old endpoint. "" = no route here, which is what the runtime resolver reads as "unset".
                plan += [["model.base_url", "", False], ["model.api_mode", "", False]]
        else:
            notes.append(f"no model assigned for {name} (lane {bot['lane']})")
        deleg = (bot.get("delegation") or {}).get("lane")
        dm = self.lane_model(deleg) if deleg else None
        if deleg and not dm:
            notes.append(f"no model assigned for lane {deleg} (delegation of {name})")
        plan += [["delegation.provider", dm["provider"] if dm else "", False],
                 ["delegation.model", dm["model"] if dm else "", False],
                 ["delegation.reasoning_effort", (dm or {}).get("reasoning") or "", False]]
        plan += [["platform_toolsets.cli", sorted(toolsets), False],  # hermes tools enable stores sorted(union)
                 ["platform_toolsets.cron", d.get("cron_toolsets") or CRON_TOOLSETS, False],
                 ["agent.disabled_toolsets", sorted(set(self.always) | (MANAGED - set(toolsets))), False]]
        for use, lane in (("aux", d.get("aux_lane", "aux")), ("vision", d.get("vision_lane", "vision"))):
            if use == "vision" and m and self.ctx.sees_images(m["provider"], m["model"]):
                # An explicit auxiliary.vision would turn native images into text descriptions
                # (agent/image_routing.py decide_image_input_mode): only text-only models get one (D-021).
                plan += [["auxiliary.vision.provider", "", False], ["auxiliary.vision.model", "", False]]
                continue
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
                 ["curator.enabled", True, False], ["curator.consolidate", False, False]]
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
        # All bots are visible (V-12). Section membership is one section per bot, stamped as
        # sectionId/sectionName on ui_meta.hermes-bots: the Desktop rebuilds the section records from these
        # stamps (apps/desktop/src/plugins/hermes-bots/user-sections.ts, adoptBotSectionsFromMeta), so this
        # is idempotent and travels with the profile. Managers share the `Managers` section; workers go to
        # the squad's own section.
        if bot.get("role") == "manager":
            section = {"id": "managers", "name": "Managers"}
        else:
            section = self.spec.get("section") or {"id": self.key, "name": self.spec.get("name") or self.key}
        return {"title": bot["title"], "hidden": False,
                "sectionId": section["id"], "sectionName": section["name"]}

    def cron_plan(self, name: str, bot: dict, notes: list[str]) -> dict:
        jobs = {}
        for job_key, j in (bot.get("cron") or {}).items():
            full = job_key if job_key.startswith(f"{self.key}-") else f"{self.key}-{job_key}"
            args = j.get("args") or []
            args = shlex.split(args) if isinstance(args, str) else list(args)
            agent = j.get("agent")
            want = {"schedule": j["schedule"], "src": j["script"], "args": args, "no_agent": not agent,
                    "script": f"{full}.sh" if args else j["script"], "deliver": f"bot-chat:{self.spec['manager']}"}
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
        sets = self.config_plan(name, bot, extra_dirs, notes, live=cfg)
        diff = pa.changed_keys(cfg, sets)
        meta = self.ui_meta(bot)
        profile_yaml = read_yaml(home / "profile.yaml") if exists else None
        meta_changed = pa.merge_ui_meta(profile_yaml, meta) is not None
        if diff or meta_changed or created:
            if not dry:
                ctx.apply_config(home, {"set": sets, "ui_meta_bots": meta})
                if any(k == "platform_toolsets.cli" for k, *_ in diff) or created:
                    ctx.hermes("tools", "enable", *bot["toolsets"], profile=name)
        acts += self.describe(diff, created)
        if created:
            # bundled keeps are external skill dirs: one visible line each, never folded into the key count
            acts += [f"skill dir + {Path(v).name} (bundled)" for _ident, k, v in keeps if k == "dir"]
        if meta_changed:
            acts.append(f"ui_meta.hermes-bots {meta}")
        if not dry and not (home / "workspace").is_dir() and not self.self_mode:
            (home / "workspace").mkdir(parents=True, exist_ok=True)

        # skills
        if not self.skip_skills:
            acts += self.skills(name, bot, keeps, existed)

        # plugins, mcp
        acts += self.plugins(name, bot, cfg, pending)
        acts += self.mcp(name, bot, cfg, pending)

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
        cred_acts, cred_notes = self.credentials(name, bot)
        acts += cred_acts
        notes += cred_notes
        conn = (bot.get("connectors") or {}).get("suggest") or []
        if conn:
            notes.append(f"connectors suggested: {', '.join(conn)}")
        for app in (bot.get("requires") or {}).get("apps") or []:
            problem = app_problem(app)
            if problem:
                notes.append(problem)
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
                    # --yes-deps: consent comes from `apply --confirm`, not from this non-interactive call;
                    # without it dependency consent fails closed and the plugin stays installed but disabled.
                    ctx.hermes("plugins", "install", pname, "--enable", "--yes-deps", profile=name)
        for pname in spec.get("disable") or []:
            if pname in enabled:
                acts.append(f"plugins disable {pname}")
                if not self.dry:
                    ctx.hermes("plugins", "disable", pname, profile=name)
        acts += self.provider_plugin(name, bot)
        return acts

    def provider_plugin(self, name: str, bot: dict) -> list[str]:
        """A provider that is a user plugin (of the builder profile or the root home): copy it into this bot's home.

        `providers/__init__._scan_home_layer` only loads the profile's own `<home>/plugins/model-providers/<name>/`
        (or a flat `<home>/plugins/<name>/` declaring `kind: model-provider`), so a provider installed elsewhere
        is `Unknown provider` in this bot until it is copied and listed.
        """
        m = self.bot_model(name, bot)
        if not m:
            return []
        found = provider_source(self.ctx, m["provider"])
        if found is None:
            return []
        src, owner = found
        home = self.ctx.home(name)
        key = plugin_key(src, owner / "plugins")
        dest = home / src.relative_to(owner)
        in_sync = dest.is_dir() and tree_sha(dest) == tree_sha(src)
        # Read the live list, never the config scanned at the start of the run: the `plugins.enable` items above
        # have been written since, and merging with a stale copy would drop them.
        enabled = list((((read_yaml(home / "config.yaml") or {}).get("plugins") or {}).get("enabled")) or [])
        if in_sync and key in enabled:
            return []
        acts = [f"provider plugin {'enable' if in_sync else '+' if not dest.is_dir() else '~'} {m['provider']}"]
        if not self.dry:
            if not in_sync:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.is_dir():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)
            if key not in enabled:
                self.ctx.apply_config(home, {"set": [["plugins.enabled", sorted({*enabled, key}), False]],
                                             "ui_meta_bots": None})
        return acts

    def key_value(self, key: str) -> str | None:
        """The value of one provider key from the only homes squadctl may take it from: the root env file and the
        process environment. Used only by the copy step; never printed or logged (C-14)."""
        return env_pairs(self.ctx.root / ENV_FILE).get(key) or os.environ.get(key) or None

    def auth_slugs(self, name: str) -> set[str]:
        """Provider slugs the profile auth store holds (`hermes -p <name> auth list`, header names only)."""
        out = self.ctx.hermes("auth", "list", profile=name, check=False)
        return set(re.findall(r"^([a-z0-9][a-z0-9._-]*)(?: \([^)]*\))?:", out, re.M))

    def _credential(self, name: str, bot: dict) -> dict:
        """One provider credential as facts: which key name, where it already lives, where a value could come from.

        A profile never inherits the gateway root environment, so the bot's own homes are its env file and its
        auth store; a key held only by the root is the copy case (C-14)."""
        m = self.bot_model(name, bot)
        if not m:
            return {"skip": True, "where": "no model assigned"}
        keys = self.ctx.provider_env_keys(m["provider"])
        if not keys:  # OAuth or an external process: there is no API key to hold
            return {"skip": True, "where": f"provider {m['provider']} needs no API key"}
        have = env_names(self.ctx.home(name) / ENV_FILE)
        if any(k in have for k in keys):
            return {"skip": True, "where": "profile env file"}
        if m["provider"] in self.auth_slugs(name):
            return {"skip": True, "where": "profile auth store"}
        key = next((k for k in keys if self.key_value(k) is not None), None)
        return {"key": key or keys[0], "copy_from": key, "provider": m["provider"]}

    def credentials(self, name: str, bot: dict) -> tuple[list[str], list[str]]:
        """Apply-time credential handling (C-14): a key that exists only in the root env file or the process
        environment is copied (name+value) into the bot's env file (mode 600) on `apply --yes`; the value is
        never printed. Without `--yes` (and in plan) it stays an owner item; a key no home holds is named."""
        c = self._credential(name, bot)
        if c.get("skip"):
            return [], []
        if not c.get("copy_from"):
            return [], [f"credentials {c['key']}: not in this environment; put it in the {name} profile "
                        f"(mode 600) for provider {c['provider']} before the first run"]
        if not self.ctx.yes:
            return [], [f"credentials {c['key']}: held by the root only; `apply --yes` copies it into the "
                        f"{name} profile (mode 600)"]
        if not self.dry:
            value = self.key_value(c["key"])
            if value is not None:
                env_set(self.ctx.home(name) / ENV_FILE, c["key"], value)
        return [f"credentials {c['key']}: copied into {name} (mode 600)"], []

    def credential_status(self, name: str, bot: dict) -> tuple[bool, str]:
        """Doctor's provider-credential check per bot: the key is in the profile env file or the auth store."""
        c = self._credential(name, bot)
        if c.get("skip"):
            return True, c["where"]
        hint = (f"`apply --yes` copies {c['copy_from']} there" if c.get("copy_from")
                else f"put {c['key']} in the {name} profile (mode 600)")
        return False, f"{c['key']} not in the {name} profile: {hint}"

    def mcp(self, name: str, bot: dict, cfg: dict, pending: list[str]) -> list[str]:
        have = cfg.get("mcp_servers") or {}
        acts = []
        for sname, srv in (bot.get("mcp") or {}).items():
            if sname in have:
                if not (have.get(sname) or {}).get("enabled", True):
                    pending.append(f"mcp {sname}: saved disabled, the probe failed; run `hermes -p {name} mcp test {sname}`")
                continue
            acts.append(f"mcp add {sname}")
            if not self.dry:
                tail = ["--url", srv["url"]] if "url" in srv else ["--command", srv["command"], "--args",
                                                                     *srv.get("args", [])]
                # The prompt order of `hermes mcp add` (hermes_cli/mcp_config.py) decides the answers: an HTTP
                # server asks "Does this server require authentication?" first (_configure_http_auth, only for
                # --url), then the tool picker's "Enable all N tools?" (_choose_tools); a stdio server only sees
                # the picker. One lone `y` landed on the auth question, the picker read EOF and printed
                # "Cancelled." with exit 0 — a server that was never written and never reported.
                stdin = ("n\n" if "url" in srv else "") + "y\n"
                self.ctx.hermes("mcp", "add", sname, *tail, profile=name, stdin=stdin)
                live = (read_yaml(self.ctx.home(name) / "config.yaml") or {}).get("mcp_servers") or {}
                if not (live.get(sname) or {}).get("enabled", True):
                    raise Fail(f"{name}: mcp add {sname} did not land enabled — the server probe failed. "
                               f"Fix it, then run `hermes -p {name} mcp add {sname} {' '.join(tail)}` "
                               f"(or `hermes -p {name} mcp test {sname}`)")
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
            if "gate_lib" in files[w["src"]]:
                # squad gates import gate_lib from their own directory: ship it beside them
                files["gate_lib.py"] = (HERE / "gate_lib.py").read_text(encoding="utf-8")
            if body:
                files[w["script"]] = body
            for fname, text in files.items():
                dest = home / "scripts" / fname
                if dest.is_file() and dest.resolve() in (src.resolve(), (HERE / fname).resolve()):
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

def board_args(board: dict) -> list[str]:
    return [board["slug"], "--name", board["name"],
            *[f"--{k}={board[k]}" for k in ("icon", "color", "description") if board.get(k)]]


def ensure_board(ctx: Ctx, spec: dict, dry: bool) -> str:
    board = spec.get("board")
    if not board:
        return "none"
    # The read is allowed inside a Kanban worker (HERMES_DELEGATED_CHILD_CONTEXT): only creation is fenced.
    # Check first; the owner errand is reported only when the board is actually missing.
    out = ctx.hermes("kanban", "boards", "list", "--json", check=False)
    try:
        live = {b["slug"] for b in json.loads(out) if not b.get("archived")}
    except ValueError:
        live = set()
    if board["slug"] in live:
        return "exists"
    if os.environ.get("HERMES_DELEGATED_CHILD_CONTEXT"):
        # Hermes refuses board creation from inside a Kanban worker (the card's board scope is fenced to the
        # board it runs on), and the refusal must not cost the whole apply: the board becomes the owner's errand.
        return "pending owner action: hermes kanban boards create " + shlex.join(board_args(board))
    if not dry:
        ctx.hermes("kanban", "boards", "create", *board_args(board))
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
    names = [spec["manager"], *[b for b in spec["bots"] if b != spec["manager"]]]
    optional = [b for b, s in spec["bots"].items() if s.get("optional")]
    with_bots = {x for w in (a.with_bots or []) for x in w.split(",") if x}
    unknown = with_bots - set(spec["bots"])
    if unknown:
        raise Fail(f"not in {key}: {sorted(unknown)}")
    if with_bots - set(optional):
        raise Fail(f"--with names only optional bots: {sorted(with_bots - set(optional))}")
    selected = [b for b in names if b not in optional or b in with_bots]
    if a.bots:
        wanted = [b for b in a.bots.split(",") if b]
        missing = set(wanted) - set(selected)
        if missing:
            hint = sorted(missing & set(optional))
            raise Fail(f"not in {key}: {sorted(missing)}"
                       + (f" (optional bots install only with --with: {', '.join(hint)})" if hint else ""))
        selected = [b for b in selected if b in wanted]
    names = selected
    ap = Applier(ctx, spec, models, dry, a.skip_skills, a.self_mode)
    unassigned = sorted({n for name in names for n in ap.missing_models(name)})
    if unassigned and not dry:
        raise Fail("; ".join(unassigned) + ". Run scripts/hpy model_advisor.py, then pass --models <file>.", 2)
    board = "none" if a.self_mode else ensure_board(ctx, spec, dry)
    root_acts = root_kanban(ctx, dry, bool(getattr(a, "set_root_kanban_cap", False)))
    bots = [ap.bot(n) for n in names]
    counts: dict[str, int] = {}
    for b in bots:
        counts[b["status"]] = counts.get(b["status"], 0) + 1
    if not dry:
        old = installed["squads"].get(key) or {}
        rec = {"version": spec["version"],
               "bots": [b for b in spec["bots"] if b in names or ctx.home(b).is_dir()],
               "board": (spec.get("board") or {}).get("slug"), "applied": old.get("applied")}
        if any(b["actions"] for b in bots) or old.get("version") != spec["version"]:
            rec["applied"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        new = {**installed, "squads": {**installed["squads"], key: rec}}
        new["bots"], new["lanes"] = models["bots"], models["lanes"]
        if new != load_installed(ctx):
            write_yaml(ctx.local / "installed.yaml", new)
    rows = [{k: v for k, v in b.items() if v or k in ("bot", "status")} for b in bots]
    out = {"squad": key, "dry_run": dry, "board": board, "root": root_acts, "summary": counts, "bots": rows}
    skipped = [b for b in optional if b not in names]
    if skipped:
        out["optional_skipped"] = skipped
    return out


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
        for name in live_bots(ctx, spec):
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


def profile_inventory(ctx: Ctx, name: str, owners: dict[str, str]) -> dict:
    """One profile as documentation: identity, model, toolsets, skills, plugins, MCP and cron names.

    Reads only `config.yaml`, `profile.yaml`, `cron/jobs.json` and the `skills/` tree, never a credential file;
    MCP servers and passthrough are reported by name only."""
    home = ctx.home(name) if name != "default" else ctx.root
    cfg = read_yaml(home / "config.yaml") or {}
    meta = read_yaml(home / "profile.yaml") or {}
    bots = ((meta.get("ui_meta") or {}).get("hermes-bots") or {}) if isinstance(meta, dict) else {}
    model = cfg.get("model") if isinstance(cfg.get("model"), dict) else {}
    skills = sorted({p.parent.name for p in (home / "skills").rglob("SKILL.md")}) if (home / "skills").is_dir() else []
    raw = json.loads(_read(home / "cron" / "jobs.json") or "[]")
    jobs = raw.get("jobs", []) if isinstance(raw, dict) else raw

    def when(job: dict) -> str | None:
        s = job.get("schedule")
        return (s.get("display") or s.get("expr")) if isinstance(s, dict) else (s or job.get("schedule_display"))
    return {
        "profile": name, "squad": owners.get(name, "unmanaged"),
        "description": meta.get("description") if isinstance(meta, dict) else None,
        "title": bots.get("title"), "section": bots.get("sectionName"), "hidden": bool(bots.get("hidden")),
        "model": {"provider": model.get("provider"), "default": model.get("default"),
                  "reasoning": pa.current(cfg, "agent.reasoning_effort")},
        "toolsets": sorted(pa.current(cfg, "platform_toolsets.cli") or []),
        "disabled_toolsets": sorted(pa.current(cfg, "agent.disabled_toolsets") or []),
        "skills": skills, "plugins": sorted(pa.current(cfg, "plugins.enabled") or []),
        "mcp": sorted(cfg.get("mcp_servers") or {}),
        "passthrough": list(pa.current(cfg, "terminal.env_passthrough") or []),
        "cron": [{"name": j.get("name"), "schedule": when(j)} for j in jobs],
    }


def cmd_inventory(ctx: Ctx, a: argparse.Namespace) -> int:
    """Document the local fleet without touching it: every profile (or --profiles), read-only."""
    installed = load_installed(ctx)
    owners = {b: key for key, rec in installed["squads"].items() for b in rec.get("bots") or []}
    names = [n for n in (a.profiles or "").split(",") if n]
    if not names:
        names = ["default"] + (sorted(p.name for p in ctx.profiles.iterdir() if (p / "config.yaml").is_file())
                               if ctx.profiles.is_dir() else [])
    missing = [n for n in names if n != "default" and not ctx.home(n).is_dir()]
    if missing:
        raise Fail(f"no such profile: {', '.join(missing)}")
    doc = {"root": str(ctx.root), "profiles": [profile_inventory(ctx, n, owners) for n in names]}
    if a.out:
        out = Path(a.out).expanduser().absolute()
        if ctx.local not in out.parents:
            raise Fail(f"--out must live under {ctx.local} (local data, never shipped)")
        write_yaml(out, doc)
        doc = {"written": str(out), "profiles": len(doc["profiles"])}
    emit(ctx, doc)
    return 0


def check(name: str, status: str, detail: str) -> dict:
    return {"check": name, "status": status, "detail": detail}


ROOT_KANBAN_KEY = "kanban.max_in_progress_per_profile"


def root_kanban(ctx: Ctx, dry: bool, set_cap: bool = False) -> list[str]:
    """`kanban.*` is machine-wide (the gateway holds the dispatcher lock), so squadctl never writes the cap on its
    own: `plan` reports it as an owner item and only `apply --set-root-kanban-cap` sets it (V-12)."""
    cfg = read_yaml(ctx.root / "config.yaml") or {}
    cur = pa.current(cfg, ROOT_KANBAN_KEY)
    if cur == 1:
        return []
    act = f"set root {ROOT_KANBAN_KEY}: {pa.as_cli(cur) if cur is not None else 'unset'} -> 1"
    if dry or not set_cap:
        return [f"{act} (owner confirm: apply --set-root-kanban-cap)"]
    ctx.apply_config(ctx.root, {"set": [[ROOT_KANBAN_KEY, 1, False]], "ui_meta_bots": None})
    return [act]


def cmd_doctor(ctx: Ctx, a: argparse.Namespace) -> int:
    out = []
    ver = hermes_version(ctx) if shutil.which("hermes") else None
    out.append(check("hermes", "ok" if ver else "fail", f"v{ver}" if ver else "not found on PATH"))
    out.append(check("builder", "ok" if ctx.home(ctx.builder).is_dir() else "warn",
                     str(ctx.home(ctx.builder)) if ctx.home(ctx.builder).is_dir() else "profile missing"))
    out.append(check("desktop-kanban", "info", "enable Capabilities > Plugins > Kanban to see the boards; "
                     "the dispatcher runs in the gateway regardless (not readable from the CLI)"))
    if ver:
        shown = ctx.hermes("profile", "show", "default", check=False)
        running = bool(re.search(r"^Gateway:\s+running", shown, re.M))
        out.append(check("gateway", "ok" if running else "warn", "default profile gateway "
                         + ("running" if running else "not running: kanban cards will not be dispatched")))
    for act in root_kanban(ctx, True):
        out.append(check("root:kanban", "warn", act))
    if not any(c["check"] == "root:kanban" for c in out):
        out.append(check("root:kanban", "ok", f"{ROOT_KANBAN_KEY} = 1"))
    installed = load_installed(ctx)
    _i, models = effective_models(ctx, None)
    keys = sorted(installed["squads"])
    if getattr(a, "squad", None):
        if a.squad not in installed["squads"]:
            raise Fail(f"squad {a.squad!r} is not installed; installed: {', '.join(keys) or 'none'}")
        keys = [a.squad]
    now = time.time()
    for key in keys:
        try:
            spec = load_spec(ctx, key)
        except Fail as e:
            out.append(check(f"{key}:spec", "fail", str(e)))
            continue
        ap = Applier(ctx, spec, models, True, False, key == "builder")
        for name in live_bots(ctx, spec):
            bot = spec["bots"][name]
            miss = ap.missing_models(name)
            authed, cred = ap.credential_status(name, bot)
            out.append(check(f"{name}:credentials", "ok" if authed else "warn", cred))
            # `models ok` never passes when the bot cannot authenticate (C-14)
            out.append(check(f"{name}:models", "ok" if not miss and authed else "warn",
                             "; ".join(miss) or ("assigned" if authed else f"assigned, but {cred}")))
            m = ap.bot_model(name, bot)
            found = provider_source(ctx, m["provider"]) if m else None
            if found and not (ctx.home(name) / found[0].relative_to(found[1])).is_dir():
                out.append(check(f"{name}:provider-plugin", "warn",
                                 f"provider {m['provider']} is a user plugin of {found[1].name}: "
                                 f"apply copies {found[0]} into this profile"))
            for env in bot.get("passthrough") or []:
                out.append(check(f"{name}:{env}", "ok" if os.environ.get(env) else "warn",
                                 "set" if os.environ.get(env) else "missing in this environment"))
            for app in (bot.get("requires") or {}).get("apps") or []:
                problem = app_problem(app)
                how, version = find_app(app)
                out.append(check(f"{name}:app:{app}", "warn" if problem else "ok",
                                 problem or f"{how} {version or ''}".strip()))
                status, detail = login_probe(re.split(r"[<>=~]", app)[0].strip())
                out.append(check(f"{name}:login:{app}", status, detail))
        if key == "jobs":
            # start_search.py stays silent without a project or profile.md; doctor is where the gap shows
            projs = [p for p in installed["projects"].values() if key in (p.get("squads") or [])]
            out.append(check("jobs:project", "ok" if projs else "warn", ", ".join(p["path"] for p in projs)
                             or "none: scripts/squadctl project add jobs <name> <path>"))
            for p in projs:
                ok = (Path(p["path"]) / "profile.md").is_file()
                out.append(check("jobs:profile.md", "ok" if ok else "warn",
                                 p["path"] if ok else f"missing in {p['path']}: the search stays off"))
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
    for name in live_bots(ctx, spec):
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
    for name in live_bots(ctx, spec):
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
        sp.add_argument("--with", dest="with_bots", action="append", metavar="BOT",
                        help="also install this optional bot (repeatable or comma-separated)")
        sp.add_argument("--models", metavar="FILE", help="models file (installed.yaml shape or model_advisor --json)")
        sp.add_argument("--skip-skills", action="store_true", help="config only; leave the skills dirs alone")
        sp.add_argument("--confirm", action="append", metavar="ID",
                        help="install this keep or plugin that needs the user's OK (repeatable)")
        sp.add_argument("--yes", action="store_true",
                        help="non-interactive run (squadctl never prompts; confirm items still need --confirm)")
        sp.add_argument("--set-root-kanban-cap", action="store_true",
                        help="also write the machine-wide kanban.max_in_progress_per_profile=1 into the gateway "
                             "root config (never set silently)")
    sp = sub.add_parser("plan", parents=[common], help="show what apply would change (reads only)")
    apply_args(sp)
    sp.set_defaults(fn=lambda c, a: cmd_apply(c, a, True), dry_run=True)
    sp = sub.add_parser("apply", parents=[common], help="create or update the squad's profiles")
    apply_args(sp)
    sp.add_argument("--dry-run", action="store_true", help="same as plan")
    sp.set_defaults(fn=cmd_apply)
    sp = sub.add_parser("status", parents=[common], help="installed squads against the live profiles")
    sp.add_argument("squad", nargs="?", help="squad key (default: every installed squad)")
    sp.set_defaults(fn=cmd_status)
    sp = sub.add_parser("inventory", parents=[common], help="document every profile of this machine (reads only)")
    sp.add_argument("--profiles", help="comma-separated profiles (default: default + every profile)")
    sp.add_argument("--out", metavar="FILE", help="also write the inventory as YAML (must be under local/)")
    sp.set_defaults(fn=cmd_inventory)
    sp = sub.add_parser("doctor", parents=[common],
                        help="check hermes, gateway, apps and their logins, models, passthrough, stale cards")
    sp.add_argument("squad", nargs="?", help="squad key (default: every installed squad)")
    sp.set_defaults(fn=cmd_doctor)
    sp = sub.add_parser("uninstall", parents=[common], help="export, remove cron, delete profiles, archive the board")
    sp.add_argument("squad", help="squad key")
    sp.add_argument("--keep-profiles", action="store_true", help="export and remove cron only; keep the profiles")
    sp.add_argument("--dry-run", action="store_true", help="show what would be removed; change nothing")
    sp.add_argument("--yes", action="store_true", help="non-interactive run (uninstall never prompts)")
    sp.set_defaults(fn=cmd_uninstall)
    sp = sub.add_parser("project", parents=[common], help="project commands")
    psub = sp.add_subparsers(dest="pcmd", required=True, metavar="action")
    pp = psub.add_parser("add", parents=[common], help="create the project in the manager and every worker")
    pp.add_argument("squad", help="squad key")
    pp.add_argument("name", help="project name (the slug is derived from it)")
    pp.add_argument("path", help="existing project folder")
    pp.add_argument("--dry-run", action="store_true", help="show which profiles would get it; create nothing")
    pp.set_defaults(fn=cmd_project_add)
    sp = sub.add_parser("chain", parents=[common], help="file the dependent cards of a squad chain")
    sp.add_argument("squad", help="squad key")
    sp.add_argument("chain", help="chain name in squad.yaml -> chains")
    sp.add_argument("--project", required=True, help="project slug")
    sp.add_argument("--title", required=True, help="title prefix of every card")
    sp.add_argument("--when", default="", help="comma list of conditions that enable `when:` stages")
    sp.add_argument("--body", default="", help="text appended to every card body")
    sp.add_argument("--run-id", help="idempotency run id (default: slug of the title)")
    sp.add_argument("--workspace", help="card workspace (default: dir:<project primary path>)")
    sp.add_argument("--dry-run", action="store_true", help="print the cards, create nothing")
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
