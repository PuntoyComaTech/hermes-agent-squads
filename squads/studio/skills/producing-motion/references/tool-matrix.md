# Tool matrix

Which tool produces which shot, and the commands each kept skill documents. The skills named here are
installed into the profile (keeps in squad.yaml).

## Contents

- Choosing a tool
- HyperFrames
- Remotion
- GSAP, three.js and R3F
- Manim
- p5.js
- Measuring

## Choosing a tool

| Shot | Tool |
|---|---|
| Title cards, overlays, captions, product tours, social cuts | HyperFrames |
| Data-driven, templated or long compositions; React codebase already exists | Remotion |
| Standalone scroll or gesture demo with pinned scenes | GSAP + ScrollTrigger |
| WebGL hero demo, 3D scene in the browser, `.glb` showcase | three.js / React Three Fiber |
| Math, algorithm or concept explainer with equations | Manim |
| Generative art, interactive sketch, canvas experiment | p5.js |

One shot, one tool. If a shot needs two (for example a Blender asset inside a three.js demo), the 3d
stage produces the asset first and the motion stage imports it from `assets/`.

## HyperFrames

- Prerequisites: Node.js 22+, FFmpeg. Its skill ships `scripts/setup.sh` for the one-time install.
- `npx hyperframes init <name> --non-interactive` scaffolds a project; `--example <template>` picks a
  template (blank, warm-grain, kinetic-type, product-promo, swiss-grid, ...).
- `npx hyperframes lint` before preview or render; `npx hyperframes doctor` for environment issues.
- `npx hyperframes preview` is a long-lived server (port 3002): stop it when the shot is done.
- `npx hyperframes render --output renders/<piece-id>-<shot>-<NN>.mp4` with `--quality draft|standard|high`,
  `--fps 24|30|60`, `--format mp4|webm`, `--strict`. Draft for review, high for delivery, same cut.

## Remotion

- React project; `npx remotion studio [--no-open]` for the interactive preview, `npx remotion render`
  to write the file (the remotion-best-practices skill routes to its render reference for flags).
- The keep is confirm-gated in squad.yaml: no licence answer, no Remotion renders.
- Keep the project in `assets/remotion/` (or `renders/<...>/src` for a delivered demo) and pin the
  Remotion version in `package.json`.

## GSAP, three.js and R3F

- The libraries come from npm (or a CDN for single-file demos). GSAP's ScrollTrigger and three.js have no
  pinned community skill yet; the kept skills (hyperframes, auteur, dream-loop) carry the techniques.
- A standalone demo is a small static page (plus its libraries) delivered under
  `renders/<piece-id>-<shot>-<NN>/`; verify it in the browser, at the brief's viewport.
- A three.js scene built as video output follows the HyperFrames path (capture the page) or renders
  headless, then goes through `render_check.py`.

## Manim

- Manim Community Edition, LaTeX and FFmpeg are the prerequisites (the manim-video skill documents setup).
- One Python file per piece with one class per scene; render draft with `manim -ql script.py <Scene>`,
  delivery with `manim -qh script.py <Scene>`, then stitch the scene clips with FFmpeg.
- Manim writes to `media/`; copy only the final files into `renders/`.

## p5.js

- One self-contained HTML file; p5.js from the CDN unless the brief pins a version.
- Export PNG with `saveCanvas()`, frames with `saveFrames()` + FFmpeg, or capture deterministically with
  CCapture.js; headless high-res runs use Puppeteer (all documented in the p5js skill).
- For an animation deliverable, capture at the brief's fps and then run `render_check.py`.

## Measuring

- `ffprobe` and `ffmpeg` are the measuring instruments; `$HERMES_HOME/skills/squad-studio/studio-contract/scripts/render_check.py` wraps them (spec,
  EBU R128 loudness, contact sheet). Never eyeball a number the check can measure.
- Every render gets `<name>.check.json` plus a contact sheet; both go into the handoff.
- Version drift (Node, FFmpeg, browsers) changes output: record what `npx hyperframes doctor` or the
  preview reports when a render is first in a piece.
