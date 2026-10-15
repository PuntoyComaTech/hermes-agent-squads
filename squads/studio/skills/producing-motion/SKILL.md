---
name: producing-motion
description: "Produces rendered motion assets and graphics. Use when a piece needs an MP4/WebM clip, a scroll or WebGL demo, a generative sketch or an explainer video."
---

# Producing motion

Turn a storyboard into rendered files, one shot at a time. A shot is done when its render passes `$HERMES_HOME/skills/squad-studio/studio-contract/scripts/render_check.py` against the brief.

## When to Use

- A `motion` stage card on the studio board.
- A clip, overlay, demo or explainer must be produced from code.
- A rendered output failed the check and needs a fix.

## Procedure

1. `scripts/studio_project.py check <folder>`; read `brief.md` and `storyboard.md`; write down each shot's spec (format, resolution, fps, duration, audio, loudness target).
2. Pick the tool per shot with `references/tool-matrix.md`:
   - HyperFrames for HTML + GSAP compositions: titles, overlays, captions, product tours (skill hyperframes);
   - Remotion for data-driven, templated or long compositions in React (skill remotion-best-practices);
   - GSAP with ScrollTrigger for standalone scroll demos (technique covered by the auteur and hyperframes skills);
   - three.js or React Three Fiber for WebGL demos and 3D scenes (technique covered by auteur and dream-loop);
   - Manim for math, algorithm and concept explainers (skill manim-video);
   - p5.js for generative art and interactive sketches (skill p5js).
3. Work inside the piece folder only. Everything downloaded or generated as an input goes to `assets/` and is logged in `assets/sources.md`; a demo delivered as files lands in `renders/<piece-id>-<shot>-<NN>/`.
4. Remotion needs a paid company licence from 4 employees: if the licence answer is not on record, `kanban_block` instead of using it.
5. Render to `renders/<piece-id>-<shot>-<NN>.<ext>`; never overwrite a previous version.
6. Check: `$HERMES_HOME/skills/squad-studio/studio-contract/scripts/render_check.py <file> --brief <folder>/brief.md --contact-sheet auto --json`, fix and rerun until it exits 0. For a `format: html` demo there is no render to probe: open it in the browser and confirm it loads without console errors before handoff.
7. Hand off: every render path, its `.check.json` report, the contact sheets, and the decisions taken (tool per shot, palette, timing changes and why).

## Pitfalls

- A preview server left running keeps a render worker busy forever: stop `hyperframes preview` and `remotion studio` before finishing.
- Draft quality and delivery quality use the same cut: never change timing between the two.
- Never make a render pass by editing the brief's numbers; fix the render or ask the lead.
- No community skill is pinned for GSAP or three.js yet: use the libraries directly with the kept skills above, and propose a pinned skill through the builder only after its author and licence are reviewed.
- Placeholder fonts, stock audio and unlicensed models never ship.
- Heavy renders time out or fill the disk: keep intermediate frames in the piece folder and delete them after the check.

## Verification

- `$HERMES_HOME/skills/squad-studio/studio-contract/scripts/render_check.py` exits 0 for every deliverable, with the brief's duration, fps, resolution and loudness.
- The contact sheet exists next to each render and shows the shots the storyboard names.
- `assets/sources.md` has a row for every external asset the shot used.
- The handoff lists no path that does not exist.
