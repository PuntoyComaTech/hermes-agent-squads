# Blender workflow

Squad conventions for the `3d` stage. The blender plugin (official) is the interface: it ships a Blender
workflow skill with the tool names and scene recipes — read it first, then apply the conventions below.

## Stage setup

- Blender 5.1+, the plugin's MCP add-on and `uv` are prerequisites; the plugin refuses to install without
  Blender and its discovery step does not prove the scene is ready. Check the plugin doctor output before
  the first render of a piece.
- Every scene is a copy: work in `assets/blender/<piece-id>/`. Never edit a `.blend` file that lives
  outside the piece folder, and never run a script you have not read — the plugin executes arbitrary
  Python with the user's privileges.
- Keep the working scene (`*.blend`) and the exported assets in `assets/`; only finished files go to
  `renders/`.

## Scene conventions

- Camera and lighting follow the storyboard row, with the composition readable at the brief's
  resolution; check framing with one still before rendering the whole shot.
- Materials need real roughness and normal detail; flat shader colors read as placeholder and fail review.
- Product stills: neutral background, one key light, one fill, soft contact shadow.
- Turntables: one constant-speed 360-degree orbit (camera or object driven), no cuts, total length equal
  to the shot's `Duration` at the brief's fps, so the loop joins seamlessly.
- Draft pass: EEVEE or low samples, review quality. Delivery pass: Cycles (or EEVEE when the brief wants
  its look) at the sample count the storyboard records. Never change camera or timing between passes.

## Outputs

- Stills: PNG at the brief's resolution into `renders/<piece-id>-<shot>-<NN>.png`.
- Animation: write a clip into `renders/` at the brief's fps and resolution, then run
  `$HERMES_HOME/skills/squad-studio/studio-contract/scripts/render_check.py <file> --brief <folder>/brief.md --contact-sheet auto --json`; a PNG sequence
  is stitched with FFmpeg before the check.
- glTF for the demos: export `.glb` with materials and textures embedded, into `assets/` (or the demo
  folder when the brief delivers it), then validate it with `npx gltf-validator <file>` (the demo-page
  load is studio-motion's step). Absolute texture
  paths and missing materials are the usual causes of a broken export.
- Contact sheets for stills: run `render_check.py` on the animation, or build a grid with FFmpeg for a
  still set; the lead reviews from the sheet.

## Assets and licences

- Every external model, HDRI, texture or brush set gets a row in `assets/sources.md` with source, licence
  and cost before it is used (CC0 or a recorded licence only).
- Record the Blender version and the plugin version in the handoff summary when a render is the first in
  a piece; a later stage may need to reproduce it.
