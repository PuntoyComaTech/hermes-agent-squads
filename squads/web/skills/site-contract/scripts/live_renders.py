#!/usr/bin/env python3
"""Keep a renders viewer for one work item: every modeller's newest render, full size, zoomable, live.

A modeller (Blender, an offline bake, a capture) overwrites its own image under `<site>/milestones/<ID>/live/`,
named after what it shows (`hero-neuron.png`, `ground.png`), after every render pass, then runs this script. The
script rewrites `live/renders.js` (the images and their modification times) and writes `live/index.html` only when
the viewer itself changed, so the tab is never reloaded and the user's zoom is never reset.

The viewer, opened once by the manager with `desktop_preview`: one render fills the tab, thumbnails of the others
in a strip below. Wheel or pinch zooms at the pointer, drag pans, double-click toggles fit / 100 %, `0` fits, `1` is
100 %, arrow keys or a thumbnail switch, `F` follows the newest render. Every 2 s it re-reads `renders.js` and
reloads only an image whose time changed, decoded off screen first, so an update never flickers and keeps the view.
Watching it costs no model tokens: it is a local page, no bot reads it.

`--add <image>` copies an image in first (under `--name`, default its file name), for a render written elsewhere.
Prints `{"path": <index.html>, "images": N}`. Exit 0 written, 1 no such site folder or image, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

IMAGES = (".png", ".jpg", ".jpeg", ".webp", ".gif")
ID_RE = re.compile(r"\A[a-z0-9][a-z0-9-]*-\d{8}-(?:build|change|bug|domain|rollback)-\d{2}\Z")
NAME_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,80}\Z")

VIEWER = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Renders - __ID__</title>
<style>
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:#0d0d0f;color:#ccc;font:12px system-ui,sans-serif;overflow:hidden}
#stage{position:absolute;inset:0 0 96px 0;overflow:hidden;cursor:grab;touch-action:none;background:
  repeating-conic-gradient(#151518 0 25%,#111114 0 50%) 0 0/24px 24px}
#stage.drag{cursor:grabbing}
#img{position:absolute;left:0;top:0;transform-origin:0 0;user-select:none;-webkit-user-drag:none}
#hud,#help{position:absolute;top:8px;padding:4px 8px;border-radius:6px;background:#000a;pointer-events:none}
#hud{left:10px}#help{right:10px;color:#888}
#strip{position:absolute;left:0;right:0;bottom:0;height:96px;display:flex;gap:6px;padding:6px;overflow-x:auto;
  background:#08080a;border-top:1px solid #222}
.th{flex:0 0 auto;height:84px;border:2px solid transparent;border-radius:6px;overflow:hidden;position:relative;
  cursor:pointer;background:#111}
.th.on{border-color:#7aa2ff}
.th.new::after{content:"";position:absolute;right:4px;top:4px;width:8px;height:8px;border-radius:50%;background:#7aff9a}
.th img{height:64px;display:block}.th span{display:block;padding:1px 4px;color:#999;white-space:nowrap}
#empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:#777}
</style></head><body>
<div id="stage"><img id="img" alt=""><div id="hud"></div>
<div id="help">wheel zoom · drag pan · double-click fit/100% · 0 fit · 1 100% · ←→ switch · F follow newest</div></div>
<div id="strip"></div>
<div id="empty" hidden>No renders yet: the first one shows here as soon as a modeller saves it.</div>
<script>
const stage = document.getElementById('stage'), img = document.getElementById('img'),
      hud = document.getElementById('hud'), strip = document.getElementById('strip'),
      empty = document.getElementById('empty');
let list = [], seen = {}, cur = null, follow = true, fitted = true, v = {s: 1, x: 0, y: 0}, drag = null;
const url = r => encodeURIComponent(r.name) + '?v=' + r.mtime;
function apply() { img.style.transform = `translate(${v.x}px,${v.y}px) scale(${v.s})`; label(); }
function label() {
  const r = list.find(r => r.name === cur);
  if (!r) return;
  hud.textContent = `${r.name} · ${img.naturalWidth}×${img.naturalHeight} · ${Math.round(v.s * 100)}% · ` +
    new Date(r.mtime * 1000).toLocaleTimeString() + (follow ? ' · following newest' : '');
}
function fit() {
  const w = stage.clientWidth, h = stage.clientHeight, iw = img.naturalWidth || 1, ih = img.naturalHeight || 1;
  v.s = Math.min(w / iw, h / ih); v.x = (w - iw * v.s) / 2; v.y = (h - ih * v.s) / 2; fitted = true; apply();
}
function zoomAt(cx, cy, f) {
  const s = Math.min(32, Math.max(0.05, v.s * f)); f = s / v.s;
  v.x = cx - (cx - v.x) * f; v.y = cy - (cy - v.y) * f; v.s = s; fitted = false; apply();
}
function actual(cx = stage.clientWidth / 2, cy = stage.clientHeight / 2) { zoomAt(cx, cy, 1 / v.s); }
function show(name, keepView) {
  const r = list.find(r => r.name === name);
  if (!r) return;
  const pre = new Image();  // decoded off screen: the visible image swaps in one frame, no flicker
  pre.onload = () => {
    const other = cur !== name;
    cur = name; img.src = pre.src;
    if (other || !keepView || fitted) fit(); else apply();
    seen[name] = r.mtime; thumbs();
  };
  pre.src = url(r);
}
function thumbs() {  // DOM nodes and textContent only: a file name is data, never markup
  strip.replaceChildren(...list.map(r => {
    const d = document.createElement('div'), t = document.createElement('img'), s = document.createElement('span');
    d.className = 'th' + (r.name === cur ? ' on' : '') + (seen[r.name] !== r.mtime ? ' new' : '');
    t.src = url(r); s.textContent = r.name; d.append(t, s);
    d.onclick = () => { follow = false; show(r.name, false); };
    return d;
  }));
}
function load() {
  const s = document.createElement('script');
  s.src = 'renders.js?t=' + Date.now();
  s.onload = s.onerror = () => {
    s.remove();
    const next = (window.RENDERS || []).slice().sort((a, b) => b.mtime - a.mtime);
    if (JSON.stringify(next) === JSON.stringify(list)) return;
    list = next; empty.hidden = list.length > 0;
    const newest = list[0] && list[0].name, r = list.find(r => r.name === cur);
    if (!r || (follow && newest !== cur)) show(newest, false);
    else if (seen[cur] !== r.mtime) show(cur, true);
    else thumbs();
  };
  document.head.appendChild(s);
}
stage.addEventListener('wheel', e => {
  e.preventDefault();
  const b = stage.getBoundingClientRect();
  zoomAt(e.clientX - b.left, e.clientY - b.top, Math.exp(-e.deltaY * (e.ctrlKey ? 0.01 : 0.002)));
}, {passive: false});
stage.addEventListener('pointerdown', e => {
  drag = {x: e.clientX - v.x, y: e.clientY - v.y}; stage.classList.add('drag'); stage.setPointerCapture(e.pointerId);
});
stage.addEventListener('pointermove', e => {
  if (!drag) return;
  v.x = e.clientX - drag.x; v.y = e.clientY - drag.y; fitted = false; apply();
});
stage.addEventListener('pointerup', () => { drag = null; stage.classList.remove('drag'); });
stage.addEventListener('dblclick', e => {
  const b = stage.getBoundingClientRect();
  if (fitted) actual(e.clientX - b.left, e.clientY - b.top); else fit();
});
addEventListener('keydown', e => {
  const i = list.findIndex(r => r.name === cur);
  if (e.key === '0') fit();
  else if (e.key === '1') actual();
  else if (e.key === 'f' || e.key === 'F') { follow = !follow; if (follow && list[0]) show(list[0].name, false); label(); }
  else if (e.key === 'ArrowRight' && list[i + 1]) { follow = false; show(list[i + 1].name, false); }
  else if (e.key === 'ArrowLeft' && i > 0) { follow = false; show(list[i - 1].name, false); }
});
addEventListener('resize', () => { if (fitted) fit(); });
load();
setInterval(load, 2000);
</script>
</body></html>
"""


def tiles(live: Path) -> list[Path]:
    return sorted((p for p in live.iterdir() if p.suffix.lower() in IMAGES and p.is_file()),
                  key=lambda p: p.stat().st_mtime, reverse=True)


def atomic(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def render(live: Path, work_id: str) -> tuple[Path, int]:
    images = tiles(live)
    manifest = [{"name": p.name, "mtime": round(p.stat().st_mtime, 3)} for p in images]
    atomic(live / "renders.js", "window.RENDERS = " + json.dumps(manifest) + ";\n")
    page = live / "index.html"
    viewer = VIEWER.replace("__ID__", work_id)
    if not page.is_file() or page.read_text(encoding="utf-8") != viewer:
        atomic(page, viewer)  # only when the viewer changed: a rewrite reloads the tab and resets the zoom
    return page, len(images)


def main(argv: list[str] | None = None) -> int:
    doc = __doc__ or ""
    p = argparse.ArgumentParser(description=doc.split("\n\n")[0], epilog=doc.split("\n\n", 1)[1],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--site", required=True, help="the site folder (holds site.yaml and milestones/)")
    p.add_argument("--id", required=True, help="work item id, e.g. acme-20261022-build-01")
    p.add_argument("--add", help="copy this image onto the viewer before updating it")
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
