---
name: producing-motion
description: "Produces rendered motion assets and graphics. Use when a piece needs an MP4/WebM clip, a scroll or WebGL demo, a generative sketch or an explainer video."
---

# Producing motion

Turn a storyboard into rendered files, one shot at a time. A shot is done when its render passes `render_check.py` (step 6) against the brief.

## When to Use

- A `motion` stage card on the studio board.
- A clip, overlay, demo or explainer must be produced from code.
- A rendered output failed the check and needs a fix.

## Procedure

1. `python3 "$HERMES_HOME/skills/squad-studio/studio-contract/scripts/studio_project.py" check <folder>`; read `brief.md` and `storyboard.md`; write down each shot's spec (format, resolution, fps, duration, audio, loudness target).
2. Pick the tool per shot with `references/tool-matrix.md`.
3. Inputs go to `assets/` (licences: studio-contract step 4); a demo delivered as files lands in `renders/<piece-id>-<shot>-<NN>/`.
4. Use Remotion only when the `remotion-best-practices` skill is installed (its licence is a `squad.yaml` confirm item); otherwise `kanban_block(kind="needs_input", reason="Remotion licence answer missing")`.
5. Render to `renders/<piece-id>-<shot>-<NN>.<ext>`; never overwrite a previous version.
6. Check: `python3 "$HERMES_HOME/skills/squad-studio/studio-contract/scripts/render_check.py" <file> --brief <folder>/brief.md --contact-sheet auto --json`, fix and rerun until it exits 0. For a `format: html` demo there is no render to probe: open it in the browser and confirm it loads without console errors before handoff.
7. Hand off: every render path, its `.check.json` report, the contact sheets, and the decisions taken (tool per shot, palette, timing changes and why).

## Pitfalls

- A preview server left running keeps a render worker busy forever: stop `hyperframes preview` and `remotion studio` before finishing.
- Draft quality and delivery quality use the same cut: never change timing between the two.
- Never make a render pass by editing the brief's numbers; fix the render or ask the lead.
- Heavy renders time out or fill the disk: keep intermediate frames in the piece folder and delete them after the check.

## Verification

- `render_check.py` exits 0 for every deliverable, with the brief's duration, fps, resolution and loudness.
- The contact sheet exists next to each render and shows the shots the storyboard names.
- `assets/sources.md` has a row for every external asset the shot used.
- The handoff lists no path that does not exist.
