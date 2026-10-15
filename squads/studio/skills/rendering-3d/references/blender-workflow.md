# Blender workflow

Squad conventions for the `3d` stage.

## Stage setup

- Keep the working scene (`*.blend`) and the exported assets in `assets/blender/`; only finished files go to
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
- Animation: write a clip into `renders/` at the brief's fps and resolution, then run the check of
  rendering-3d step 6; a PNG sequence is stitched with FFmpeg before the check.
- glTF for the demos: export `.glb` with materials and textures embedded, into `assets/blender/` (or the
  demo folder when the brief delivers it), then validate it (rendering-3d step 5).
- Contact sheets for stills: run `render_check.py` on the animation, or build a grid with FFmpeg for a
  still set; the lead reviews from the sheet.

## Versions

- Record the Blender version and the plugin version in the handoff summary when a render is the first in
  a piece.
