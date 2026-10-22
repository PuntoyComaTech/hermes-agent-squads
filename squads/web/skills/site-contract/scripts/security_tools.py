#!/usr/bin/env python3
"""The web squad's security scanners, installed at pinned versions with verified downloads.

`status` lists each tool: installed, and at the pinned version. `ensure <tool>...` installs what is missing:
osv-scanner, gitleaks and nuclei are single binaries fetched over https from the project's GitHub release and checked
against the SHA-256 this repo pins in stacks.json (copied from the release's checksum file when the pin was set, so a
swapped release or mirror cannot also swap the digest); a mismatch installs nothing. The installed binary's digest is
recorded and rechecked, so a replaced or half-written file is reinstalled. semgrep installs through uv at its pin. Everything lands under one user folder (no sudo, no global package manager, no PATH edits): the bots'
scripts find it through toolpath.augment_path. `nuclei` also needs its template set (pinned, checksum-verified), fetched once into that folder.

Pins live in stacks.json (security_tools); a bump needs a decisions.md line and a release at least 14 days old.
HERMES_WEB_TOOLS_MIRROR points the downloads at a local folder (file://) for tests; plain http is refused.
Exit 0 every requested tool is ready, 1 one could not be installed (its JSON row says why), 2 usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from toolpath import tools_dir  # noqa: E402

PINS = json.loads((HERE / "stacks.json").read_text(encoding="utf-8")).get("security_tools", {})
MIRROR = "HERMES_WEB_TOOLS_MIRROR"  # tests point this at a local folder or server holding the same release layout
GITHUB = "https://github.com"
TOOLS = ("osv-scanner", "gitleaks", "nuclei", "semgrep")

# tool -> (release asset name template, checksum file template, archive kind); {v}, {os}, {arch} filled per host
LAYOUT = {
    "osv-scanner": ("osv-scanner_{os}_{arch}", "osv-scanner_SHA256SUMS", "raw"),
    "gitleaks": ("gitleaks_{v}_{os}_{arch}.tar.gz", "gitleaks_{v}_checksums.txt", "tar"),
    "nuclei": ("nuclei_{v}_{os}_{arch}.zip", "nuclei_{v}_checksums.txt", "zip"),
}
PLATFORM_NAMES = {
    "osv-scanner": {"os": {"darwin": "darwin", "linux": "linux"}, "arch": {"arm64": "arm64", "x86_64": "amd64",
                                                                            "aarch64": "arm64", "amd64": "amd64"}},
    "gitleaks": {"os": {"darwin": "darwin", "linux": "linux"}, "arch": {"arm64": "arm64", "x86_64": "x64",
                                                                         "aarch64": "arm64", "amd64": "x64"}},
    "nuclei": {"os": {"darwin": "macOS", "linux": "linux"}, "arch": {"arm64": "arm64", "x86_64": "amd64",
                                                                      "aarch64": "arm64", "amd64": "amd64"}},
}
REPOS = {"osv-scanner": "google/osv-scanner", "gitleaks": "gitleaks/gitleaks", "nuclei": "projectdiscovery/nuclei"}
TAGS = {"osv-scanner": "v{v}", "gitleaks": "v{v}", "nuclei": "v{v}"}


def bin_dir() -> Path:
    return tools_dir() / "bin"


def base_url(tool: str, pin: str) -> str:
    mirror = os.environ.get(MIRROR)
    if mirror:
        return f"{mirror.rstrip('/')}/{tool}/{pin}"
    return f"{GITHUB}/{REPOS[tool]}/releases/download/{TAGS[tool].format(v=pin)}"


class HttpsOnly(urllib.request.HTTPRedirectHandler):
    """GitHub answers release downloads with a redirect to its CDN; a redirect away from https is refused."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001 - urllib's signature
        if not newurl.startswith("https://"):
            raise ValueError(f"refused a redirect to a non-https URL: {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


OPENER = urllib.request.build_opener(HttpsOnly)


def fetch(url: str) -> bytes:
    if url.startswith("file://"):
        return Path(url[7:]).read_bytes()
    if not url.startswith("https://"):
        raise ValueError(f"refused a non-https download: {url}")
    with OPENER.open(url, timeout=600) as resp:
        return resp.read()


def asset_for(tool: str, pin: str) -> tuple[str, str, str]:
    names = PLATFORM_NAMES[tool]
    os_key = "darwin" if sys.platform == "darwin" else "linux" if sys.platform.startswith("linux") else sys.platform
    os_name = names["os"].get(os_key)
    arch = names["arch"].get(platform.machine().lower())
    if not os_name or not arch:
        raise RuntimeError(f"{tool}: no release for {sys.platform}/{platform.machine()}")
    asset, sums, kind = LAYOUT[tool]
    fill = {"v": pin, "os": os_name, "arch": arch}
    return asset.format(**fill), sums.format(**fill), kind


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def install_binary(tool: str, pin: str) -> dict:
    asset, _, kind = asset_for(tool, pin)
    want = ((PINS.get(tool) or {}).get("sha256") or {}).get(asset)
    if not want:
        return {"ok": False, "detail": f"{asset}: no pinned SHA-256 in stacks.json; not installed"}
    data = fetch(f"{base_url(tool, pin)}/{asset}")
    if sha256(data) != want:
        return {"ok": False, "detail": f"{asset}: SHA-256 does not match the pinned digest; not installed"}
    bin_dir().mkdir(parents=True, exist_ok=True)
    target = bin_dir() / tool
    if kind == "raw":
        blob = data
    elif kind == "tar":
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            member = next(m for m in tf.getmembers() if m.isfile() and Path(m.name).name == tool)
            blob = (tf.extractfile(member) or io.BytesIO()).read()
    else:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            blob = zf.read(next(n for n in zf.namelist() if Path(n).name == tool))
    tmp = target.with_suffix(".part")
    tmp.write_bytes(blob)
    tmp.chmod(0o755)
    tmp.replace(target)
    (bin_dir() / f"{tool}.version").write_text(f"{pin} {sha256(blob)}", encoding="utf-8")
    return {"ok": True, "detail": f"installed {tool} {pin}"}


def install_semgrep(pin: str) -> dict:
    uv = shutil.which("uv")
    if not uv:
        return {"ok": False, "detail": "semgrep installs through uv, which is not on PATH"}
    env = {**os.environ, "UV_TOOL_DIR": str(tools_dir() / "uv"), "UV_TOOL_BIN_DIR": str(bin_dir())}
    done = subprocess.run([uv, "tool", "install", "--quiet", f"semgrep=={pin}"], capture_output=True, text=True,
                          env=env, timeout=900, stdin=subprocess.DEVNULL)
    if done.returncode:
        return {"ok": False, "detail": (done.stdout + done.stderr)[-400:]}
    (bin_dir() / "semgrep.version").write_text(pin, encoding="utf-8")
    return {"ok": True, "detail": f"installed semgrep {pin}"}


def installed_version(tool: str) -> str | None:
    """The pin a tool was installed at, or None. A binary whose bytes changed since install (replaced, half-written)
    counts as not installed; semgrep is a uv launcher and carries no digest."""
    marker, binary = bin_dir() / f"{tool}.version", bin_dir() / tool
    if not (binary.is_file() and marker.is_file()):
        return None
    pin, _, digest = marker.read_text(encoding="utf-8").strip().partition(" ")
    if tool != "semgrep" and digest != sha256(binary.read_bytes()):
        return None
    return pin


def ensure(tool: str) -> dict:
    pin = (PINS.get(tool) or {}).get("version")
    if not pin:
        return {"tool": tool, "ready": False, "detail": f"no pin for {tool} in stacks.json"}
    if installed_version(tool) == pin:
        row = {"tool": tool, "ready": True, "version": pin, "detail": "already installed"}
    else:
        try:
            got = install_semgrep(pin) if tool == "semgrep" else install_binary(tool, pin)
        except (OSError, RuntimeError, StopIteration, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
            got = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}
        row = {"tool": tool, "ready": got["ok"], "version": pin, "detail": got["detail"]}
    if row["ready"] and tool == "nuclei":
        row = {**row, **ensure_templates()}
        row["version"] = pin
    return row


def templates_ready() -> bool:
    pin = (PINS.get("nuclei") or {}).get("templates")
    marker = tools_dir() / "nuclei-templates" / ".ready"
    return bool(pin) and marker.is_file() and marker.read_text(encoding="utf-8").strip() == pin


def ensure_templates() -> dict:
    """nuclei refuses to scan without templates, and its own downloader gives up after 60 s, which a slow link never
    meets (19 MB). So the pinned release is fetched here, checked against the SHA-256 pinned in stacks.json, and only the
    `http/` templates are kept: they are what the audit runs, and no template with a code or file protocol lands on
    disk. Members are written only inside the folder."""
    if templates_ready():
        return {}
    pin = (PINS.get("nuclei") or {}).get("templates")
    if not pin:
        return {"ready": False, "detail": "no nuclei templates pin in stacks.json"}
    asset = f"nuclei-templates-{pin}.zip"
    mirror = os.environ.get(MIRROR)
    archive = (f"{mirror.rstrip('/')}/nuclei-templates/{pin}/{asset}" if mirror
               else f"{GITHUB}/projectdiscovery/nuclei-templates/archive/refs/tags/v{pin}.zip")
    try:
        data = fetch(archive)
        if sha256(data) != (PINS.get("nuclei") or {}).get("templates_sha256"):
            return {"ready": False, "detail": f"{asset}: SHA-256 does not match the pinned digest; not installed"}
        folder = tools_dir() / "nuclei-templates"
        shutil.rmtree(folder, ignore_errors=True)
        kept = 0
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for member in zf.infolist():
                parts = Path(member.filename).parts[1:]  # drop the archive's top folder
                if member.is_dir() or len(parts) < 2 or parts[0] != "http" or not parts[-1].endswith((".yaml", ".yml")):
                    continue
                target = folder.joinpath(*parts)
                if folder.resolve() not in target.resolve().parents:
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))
                kept += 1
        if not kept:
            return {"ready": False, "detail": "the templates archive held no http templates"}
    except (OSError, ValueError, zipfile.BadZipFile) as exc:
        return {"ready": False, "detail": f"nuclei templates could not be fetched: {type(exc).__name__}: {exc}"}
    (folder / ".ready").write_text(pin, encoding="utf-8")
    return {"detail": f"installed nuclei {(PINS.get('nuclei') or {}).get('version')} and {kept} templates {pin}"}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0],
                                epilog="Exit 0 ready, 1 an install failed, 2 usage error.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="installed and pinned versions")
    en = sub.add_parser("ensure", help="install what is missing")
    en.add_argument("tools", nargs="+", help="osv-scanner gitleaks nuclei semgrep")
    args = p.parse_args(argv)
    if args.cmd == "status":
        rows = [{"tool": t, "pin": (PINS.get(t) or {}).get("version"), "installed": installed_version(t),
                 "ready": installed_version(t) == (PINS.get(t) or {}).get("version")
                 and (t != "nuclei" or templates_ready())} for t in TOOLS]
        print(json.dumps({"dir": str(tools_dir()), "tools": rows}, indent=2))
        return 0 if all(r["ready"] for r in rows) else 1
    unknown = [t for t in args.tools if t not in TOOLS]
    if unknown:
        print(f"error: unknown tool(s) {', '.join(unknown)}; known: {', '.join(TOOLS)}", file=sys.stderr)
        return 2
    rows = [ensure(t) for t in args.tools]
    print(json.dumps({"tools": rows}, indent=2))
    return 0 if all(r["ready"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
