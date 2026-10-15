#!/usr/bin/env python3
"""Create or verify the folder layout of one studio piece.

A piece lives in <project>/studio/<piece-id>/ and holds brief.md, storyboard.md, assets/ and renders/
(formats: studio-contract references/project-files.md). init creates whatever is missing and rewrites an
existing brief.md or storyboard.md only with --overwrite. check verifies the layout and the brief front matter.

Exit codes: 0 ok, 1 incomplete (check), 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DIRS = ("assets", "renders")
REQUIRED_KEYS = ("piece", "title", "format")
FORMATS = ("mp4", "webm", "gif", "png", "png-sequence", "glb", "html")
TIMED = ("mp4", "webm", "gif", "png-sequence")  # need duration and fps
UNSIZED = ("glb", "html")  # need no resolution
DEFAULT_LUFS = -23.0

BRIEF = """---
piece: {piece}
title: {title}
requester: {requester}
format: {format}
duration: {duration}
fps: {fps}
resolution: {resolution}
audio: {audio}
{loudness}---

## Objective

One paragraph: where the piece is used and what it must communicate.

## Acceptance

- [ ] Measurable line the requester can check (order, legibility, timing, sound level).
"""

STORYBOARD = """# Storyboard - {title}

One row per shot; time is seconds from the start. Tools: HyperFrames, Remotion, three.js/R3F, GSAP,
Manim, p5.js or Blender (studio-motion and studio-3d skills).

| # | Shot | Start | Duration | Tool | Assets | Samples | Acceptance |
|---|---|---|---|---|---|---|---|
| 1 |  | 0.0 |  |  |  | - |  |

## Notes

- Total must match the brief ({duration} s at {fps} fps, {resolution}).
- Every asset named here must exist in `assets/` and be logged in `assets/sources.md`.
"""


def as_number(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---", text, re.S)
    if not match:
        return {}
    data = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, value = line.split(":", 1)
            value = value.split(" #", 1)[0].strip().strip('"')
            data[key.strip()] = value
    return data


def brief_text(a: argparse.Namespace) -> str:
    loudness = ""
    if a.loudness is not None:
        loudness = f"loudness: {a.loudness:.1f}\n"
    elif a.audio != "none":
        loudness = f"loudness: {DEFAULT_LUFS:.1f}\n"
    return BRIEF.format(piece=a.piece, title=a.title, requester=a.requester or "-", format=a.format,
                        duration=f"{a.duration:.2f}", fps=a.fps, resolution=a.resolution or "-",
                        audio=a.audio, loudness=loudness)


def cmd_init(a: argparse.Namespace) -> int:
    folder = Path(a.folder).expanduser()
    created, kept, rewritten = [], [], []
    folder.mkdir(parents=True, exist_ok=True)
    for directory in DIRS:
        target = folder / directory
        if target.is_dir():
            kept.append(f"{directory}/")
        else:
            target.mkdir()
            created.append(f"{directory}/")
    for name, body in (("brief.md", brief_text(a)), ("storyboard.md", STORYBOARD.format(
            title=a.title, duration=f"{a.duration:.2f}", fps=a.fps, resolution=a.resolution or "-"))):
        target = folder / name
        if target.is_file() and not a.overwrite:
            kept.append(name)
            continue
        existed = target.is_file()
        target.write_text(body, encoding="utf-8")
        (rewritten if existed else created).append(name)
    result = {"folder": str(folder), "ok": True, "created": created, "kept": kept, "rewritten": rewritten,
              "brief": str(folder / "brief.md")}
    if a.json:
        print(json.dumps(result, indent=2))
    else:
        for line in created:
            print(f"created {line}")
        for line in kept:
            print(f"kept {line}")
        for line in rewritten:
            print(f"rewritten {line}")
        print(f"ok: {folder}")
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    folder = Path(a.folder).expanduser()
    missing = []
    if not folder.is_dir():
        missing.append(str(folder))
    for name in ("brief.md", "storyboard.md"):
        if not (folder / name).is_file():
            missing.append(name)
    for directory in DIRS:
        if not (folder / directory).is_dir():
            missing.append(f"{directory}/")
    brief = front_matter(folder / "brief.md") if (folder / "brief.md").is_file() else {}
    missing_keys = [key for key in REQUIRED_KEYS if not brief.get(key)]
    fmt = brief.get("format")
    if fmt in TIMED:
        missing_keys += [key for key in ("duration", "fps") if (as_number(brief.get(key)) or 0) <= 0]
    if fmt not in UNSIZED and brief.get("resolution") in (None, "", "-"):
        missing_keys.append("resolution")
    ok = not missing and not missing_keys
    result = {"folder": str(folder), "ok": ok, "missing": missing, "missing_keys": missing_keys, "brief": brief}
    if a.json:
        print(json.dumps(result, indent=2))
    else:
        for entry in missing:
            print(f"missing {entry}")
        for key in missing_keys:
            print(f"missing brief key: {key}")
        print(f"{'ok' if ok else 'incomplete'}: {folder}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio_project.py",
        description="Create or verify the folder layout of one studio piece.",
        epilog="Exit 0 ok, 1 incomplete (check), 2 usage error.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init", help="create the pieces of the layout that are missing")
    init.add_argument("folder", help="piece folder, usually <project>/studio/<piece-id>")
    init.add_argument("--piece", help="piece id <YYYYMMDD>-<slug> (default: the folder name)")
    init.add_argument("--title", help="human title of the piece (default: the piece id)")
    init.add_argument("--requester", default="", help="bot or squad that ordered the piece (web, marketing, ...)")
    init.add_argument("--format", default="mp4", choices=FORMATS, help="deliverable format (default: mp4)")
    init.add_argument("--duration", type=float, default=0.0, help="target duration in seconds")
    init.add_argument("--fps", type=int, default=0, help="target frames per second")
    init.add_argument("--resolution", default="", help="target resolution, WxH (for example 1920x1080)")
    init.add_argument("--audio", default="none", choices=["none", "stereo"], help="audio tracks in the deliverable")
    init.add_argument("--loudness", type=float,
                      help=f"EBU R128 integrated target in LUFS (default with --audio stereo: {DEFAULT_LUFS})")
    init.add_argument("--overwrite", action="store_true", help="rewrite an existing brief.md and storyboard.md")
    init.add_argument("--json", action="store_true", help="machine-readable output")
    init.set_defaults(fn=cmd_init)
    check = sub.add_parser("check", help="verify the layout and the brief front matter")
    check.add_argument("folder", help="piece folder")
    check.add_argument("--json", action="store_true", help="machine-readable output")
    check.set_defaults(fn=cmd_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    if a.cmd == "init":
        a.piece = a.piece or Path(a.folder).name
        a.title = a.title or a.piece
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
