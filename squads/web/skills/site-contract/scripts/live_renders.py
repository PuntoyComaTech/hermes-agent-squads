#!/usr/bin/env python3
"""Keep a renders board for one work item: every modeller's newest render on one page the user watches in a tab.

A modeller (Blender, an offline bake, a capture) overwrites its own image under `<site>/milestones/<ID>/live/`,
named after what it shows (`hero-neuron.png`, `ground.png`), after every render pass, then runs this script. The
script rewrites `<site>/milestones/<ID>/live/index.html`: one tile per image, newest first, with its name and time.
The manager opens that file once with `desktop_preview`; Hermes Desktop reloads a file tab when the file changes,
and the page itself re-reads each image every few seconds, so an overwritten render shows up without a new run.

`--add <image>` copies an image in first (under `--name`, default its file name), for a render written elsewhere.
Prints `{"path": <index.html>, "images": N}`. Exit 0 written, 1 no such site folder or image, 2 usage error.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

IMAGES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
ID_RE = re.compile(r"\A[a-z0-9][a-z0-9-]*-\d{8}-(?:build|change|bug|domain|rollback)-\d{2}\Z")
NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,80}\Z")
REFRESH_MS = 3000

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<style>
body{{margin:0;padding:16px;background:#111;color:#ddd;font:13px system-ui,sans-serif}}
h1{{font-size:14px;font-weight:600;margin:0 0 12px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}}
figure{{margin:0;background:#1b1b1b;border-radius:8px;overflow:hidden}}
img{{display:block;width:100%;height:auto}}
figcaption{{padding:6px 10px;display:flex;justify-content:space-between;color:#aaa}}
.empty{{color:#888}}
</style></head><body>
<h1>{title}</h1>
{body}
<script>
setInterval(() => {{
  const t = Date.now();
  for (const img of document.querySelectorAll('img[data-src]')) img.src = img.dataset.src + '?t=' + t;
}}, {refresh});
</script>
</body></html>
"""


def tiles(live: Path) -> list[Path]:
    return sorted((p for p in live.iterdir() if p.suffix.lower() in IMAGES and p.is_file()),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def render(live: Path, work_id: str) -> tuple[Path, int]:
    images = tiles(live)
    if images:
        body = '<div class="grid">\n' + "\n".join(
            f'<figure><img data-src="{html.escape(p.name)}" src="{html.escape(p.name)}" alt="{html.escape(p.stem)}">'
            f'<figcaption><span>{html.escape(p.stem)}</span>'
            f'<span>{datetime.fromtimestamp(p.stat().st_mtime).strftime("%H:%M:%S")}</span></figcaption></figure>'
            for p in images) + "\n</div>"
    else:
        body = '<p class="empty">No renders yet: the first one shows here as soon as a modeller saves it.</p>'
    page = live / "index.html"
    tmp = live / ".index.html.tmp"
    tmp.write_text(PAGE.format(title=html.escape(f"Renders - {work_id}"), body=body, refresh=REFRESH_MS),
                   encoding="utf-8")
    tmp.replace(page)  # one atomic change: the tab reloads once, never on a half-written file
    return page, len(images)


def main(argv: list[str] | None = None) -> int:
    doc = __doc__ or ""
    p = argparse.ArgumentParser(description=doc.split("\n\n")[0], epilog=doc.split("\n\n", 1)[1],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--site", required=True, help="the site folder (holds site.yaml and milestones/)")
    p.add_argument("--id", required=True, help="work item id, e.g. acme-20261022-build-01")
    p.add_argument("--add", help="copy this image onto the board before rewriting it")
    p.add_argument("--name", help="file name for --add (default: the image's own name)")
    a = p.parse_args(argv)
    if not ID_RE.match(a.id) or (a.name and not NAME_RE.match(a.name)):
        print("error: --id must be a work item id and --name a plain file name", file=sys.stderr)
        return 2
    site = Path(a.site).expanduser().resolve()
    if not site.is_dir():
        print(json.dumps({"error": f"no site folder {site}"}))
        return 1
    live = site / "milestones" / a.id / "live"
    live.mkdir(parents=True, exist_ok=True)
    if a.add:
        src = Path(a.add).expanduser()
        if not src.is_file() or src.suffix.lower() not in IMAGES:
            print(json.dumps({"error": f"not an image: {src}"}))
            return 1
        name = a.name or src.name
        if Path(name).suffix.lower() not in IMAGES:
            name += src.suffix.lower()
        tmp = live / f".{name}.tmp"
        shutil.copyfile(src, tmp)
        tmp.replace(live / name)
    page, count = render(live, a.id)
    print(json.dumps({"path": str(page), "images": count}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
