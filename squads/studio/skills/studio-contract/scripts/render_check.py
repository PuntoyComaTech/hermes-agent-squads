#!/usr/bin/env python3
"""Check a rendered deliverable against the brief: spec, EBU R128 loudness, contact sheet (plan section 4.4).

  render_check.py FILE [FILE ...] [--brief BRIEF.md] [--duration S] [--fps N] [--resolution WxH]
                  [--target-lufs LUFS] [--tolerance-seconds S] [--tolerance-fps F]
                  [--contact-sheet PATH|auto] [--samples N] [--json]

Reads the expectations from the brief front matter (duration, fps, resolution, format, loudness) and lets
each flag override one of them. Uses ffprobe for the spec, `ffmpeg -af ebur128` for loudness and ffmpeg
`fps,scale,tile` for the contact sheet. Writes the contact sheet only when asked. Every file gets a
`<name>.check.json` report next to it (studio-contract); `--json` prints the whole run to stdout.

Exit codes: 0 pass, 1 a deliverable violates the brief, 2 ffprobe/ffmpeg missing or bad usage.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path

FORMAT_EXT = {"mp4": {"mp4", "m4v", "mov"}, "webm": {"webm"}, "gif": {"gif"}}
IMAGE_CODECS = {"png", "jpeg", "jpg", "mjpeg", "bmp", "tiff", "webp", "apng"}


def run(argv: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)


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


def as_float(value, default: float | None = None) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_rate(value: str | None) -> float | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d+)/(\d+)", value.strip())
    if match:
        num, den = int(match.group(1)), int(match.group(2))
        return num / den if den else None
    return as_float(value)


def probe(ffprobe: str, path: Path) -> dict:
    done = run([ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    if done.returncode != 0:
        raise ValueError((done.stderr or done.stdout).strip()[:300] or "ffprobe failed")
    return json.loads(done.stdout or "{}")


def measure_loudness(ffmpeg: str, path: Path) -> dict | None:
    done = run([ffmpeg, "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0",
                "-af", "ebur128=peak=true", "-f", "null", "-"])
    text = done.stderr or ""
    if done.returncode != 0:
        raise ValueError("ffmpeg ebur128 failed: " + (text.strip().splitlines() or [""])[-1][:200])
    integrated = re.findall(r"I:\s+(-?\d+(?:\.\d+)?)\s+LUFS", text)
    lra = re.findall(r"LRA:\s+(-?\d+(?:\.\d+)?)\s+LU", text)
    peak = re.findall(r"Peak:\s+(-?\d+(?:\.\d+)?)\s+dBFS", text)
    if not integrated:
        return None
    return {"integrated_lufs": float(integrated[-1]), "lra_lu": as_float(lra[-1] if lra else None),
            "true_peak_dbfs": as_float(peak[-1] if peak else None)}


def contact_sheet(ffmpeg: str, path: Path, out: Path, duration: float | None, samples: int) -> None:
    span = duration if duration and duration > 0 else float(samples)
    rate = max(samples / span, 0.1)
    columns = 4
    rows = max(1, math.ceil(samples / columns))
    out.parent.mkdir(parents=True, exist_ok=True)
    done = run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
                "-vf", f"fps={rate:.6f},scale=320:-2,tile={columns}x{rows}", "-frames:v", "1", str(out)])
    if done.returncode != 0 or not out.is_file():
        raise ValueError("contact sheet failed: " + (done.stderr or "").strip()[-200:])


def check_file(ffprobe: str, ffmpeg: str | None, path: Path, expect: dict, args: argparse.Namespace) -> dict:
    details = probe(ffprobe, path)
    streams = details.get("streams") or []
    fmt = details.get("format") or {}
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    kind = "image" if video and (video.get("codec_name") in IMAGE_CODECS or
                                 "image" in str(fmt.get("format_name", ""))) else "media"
    duration = as_float(video.get("duration") if video else None) or as_float(fmt.get("duration"))
    fps = parse_rate(video.get("avg_frame_rate") if video else None) or parse_rate(
        video.get("r_frame_rate") if video else None)
    resolution = f"{video.get('width')}x{video.get('height')}" if video else None
    violations: list[str] = []

    if kind == "media":
        want_duration = as_float(expect.get("duration"))
        if want_duration and duration is not None and abs(duration - want_duration) > args.tolerance_seconds:
            violations.append(f"duration {duration:.3f}s differs from {want_duration:.3f}s "
                              f"(tolerance {args.tolerance_seconds}s)")
        want_fps = as_float(expect.get("fps"))
        if want_fps and fps is not None and abs(fps - want_fps) > args.tolerance_fps:
            violations.append(f"fps {fps:.3f} differs from {want_fps:g} (tolerance {args.tolerance_fps})")
    want_res = (expect.get("resolution") or "").lower().replace(" ", "")
    if want_res and want_res != "-" and resolution and resolution.lower() != want_res:
        violations.append(f"resolution {resolution} differs from {want_res}")
    want_format = (expect.get("format") or "").lower()
    if want_format in FORMAT_EXT and path.suffix.lstrip(".").lower() not in FORMAT_EXT[want_format]:
        violations.append(f"format {path.suffix.lstrip('.').lower()} differs from brief {want_format}")

    loudness = None
    want_lufs = as_float(expect.get("loudness")) if args.target_lufs is None else args.target_lufs
    if audio and ffmpeg:
        loudness = measure_loudness(ffmpeg, path)
        if loudness and want_lufs is not None:
            measured = loudness["integrated_lufs"]
            loudness["target_lufs"], loudness["ok"] = want_lufs, abs(measured - want_lufs) <= args.tolerance_lufs
            if not loudness["ok"]:
                violations.append(f"loudness {measured:.1f} LUFS differs from {want_lufs:.1f} LUFS "
                                  f"(EBU R128, tolerance {args.tolerance_lufs})")

    sheet = None
    if args.contact_sheet and kind == "media" and video:
        assert ffmpeg is not None  # main refuses to start without ffmpeg when a contact sheet is asked for
        sheet = Path(args.contact_sheet)
        if str(sheet) == "auto":
            sheet = path.with_suffix(".contact.png")
        contact_sheet(ffmpeg, path, sheet, duration, args.samples)

    return {"file": str(path), "kind": kind, "codec": video.get("codec_name") if video else None,
            "duration": duration, "fps": fps, "resolution": resolution,
            "audio": {"codec": audio.get("codec_name"), "sample_rate": audio.get("sample_rate"),
                      "channels": audio.get("channels")} if audio else None,
            "loudness": loudness, "contact_sheet": str(sheet) if sheet else None, "violations": violations}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="render_check.py",
        description="Check rendered deliverables against the brief: spec, EBU R128 loudness, contact sheet.",
        epilog="Exit 0 pass, 1 violation, 2 ffprobe/ffmpeg missing or bad usage.",
    )
    parser.add_argument("files", nargs="+", type=Path, help="rendered files to check")
    parser.add_argument("--brief", type=Path, help="brief.md to read duration, fps, resolution, format, loudness from")
    parser.add_argument("--duration", type=float, help="expected duration in seconds")
    parser.add_argument("--fps", type=float, help="expected frames per second")
    parser.add_argument("--resolution", help="expected resolution, WxH")
    parser.add_argument("--target-lufs", type=float, help="EBU R128 integrated loudness target in LUFS")
    parser.add_argument("--tolerance-seconds", type=float, default=0.2, help="duration tolerance (default 0.2)")
    parser.add_argument("--tolerance-fps", type=float, default=0.02, help="fps tolerance (default 0.02)")
    parser.add_argument("--tolerance-lufs", type=float, default=0.5, help="loudness tolerance (default 0.5 LU)")
    parser.add_argument("--contact-sheet", metavar="PATH", help="write a 320px contact sheet to PATH (or 'auto')")
    parser.add_argument("--samples", type=int, default=12, help="frames in the contact sheet (default 12)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ffprobe, ffmpeg = shutil.which("ffprobe"), shutil.which("ffmpeg")
    if not ffprobe:
        print("error: ffprobe not found on PATH (install ffmpeg)", file=sys.stderr)
        return 2
    need_ffmpeg = args.contact_sheet or args.target_lufs is not None
    if need_ffmpeg and not ffmpeg:
        print("error: ffmpeg not found on PATH (needed for loudness and contact sheets)", file=sys.stderr)
        return 2
    expect = front_matter(args.brief) if args.brief else {}
    for key, value in (("duration", args.duration), ("fps", args.fps), ("resolution", args.resolution),
                       ("loudness", args.target_lufs)):
        if value is not None:
            expect[key] = value
    missing = [str(p) for p in args.files if not p.is_file()]
    if missing:
        print("error: no such file: " + ", ".join(missing), file=sys.stderr)
        return 2
    results, errors = [], []
    for path in args.files:
        try:
            results.append(check_file(ffprobe, ffmpeg, path, expect, args))
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            errors.append({"file": str(path), "error": str(exc)})
    ok = not errors and all(not entry["violations"] for entry in results)
    result = {"ok": ok, "brief": str(args.brief) if args.brief else None, "files": results, "errors": errors}
    for entry in results:
        report = Path(entry["file"]).with_suffix(".check.json")
        report.write_text(json.dumps({**entry, "ok": not entry["violations"]}, indent=2) + "\n", encoding="utf-8")
    for entry in errors:
        report = Path(entry["file"]).with_suffix(".check.json")
        report.write_text(json.dumps({"file": entry["file"], "ok": False, "error": entry["error"]}, indent=2) + "\n",
                          encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for entry in results:
            line = f"{entry['file']}: {entry['kind']} {entry['duration'] or '-'}s {entry['fps'] or '-'} fps {entry['resolution'] or '-'}"
            if entry["loudness"]:
                line += f" {entry['loudness']['integrated_lufs']:.1f} LUFS"
            print(("ok   " if not entry["violations"] else "fail ") + line)
            for violation in entry["violations"]:
                print(f"     - {violation}")
            if entry["contact_sheet"]:
                print(f"     contact sheet: {entry['contact_sheet']}")
        for entry in errors:
            print(f"error {entry['file']}: {entry['error']}")
        print("ok" if ok else "fail")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
