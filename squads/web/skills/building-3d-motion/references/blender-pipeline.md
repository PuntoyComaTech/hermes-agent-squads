# Blender pipeline

What to model offline and how it reaches the site. The Blender work itself (scenes, materials, lighting,
Cycles/EEVEE, turntables) happens outside the site repo, with the confirm-gated plugin below; what
arrives here is a glTF/GLB or a static render you wire into the scene.

## Contents

- Split of work
- Export
- In-site Blender use

## Split of work

- Model and bake in Blender when the asset is sculpted, lit or textured beyond what code does cheaply;
  keep procedural or parametric geometry in code (three.js/R3F) when it must react to the user.
- Static hero renders delivered as WebM/MP4 or AVIF stills are often cheaper than shipping a live
  scene: ask for a static export when the scene never reacts to the user.

## Export

- glTF/GLB is the interchange format; apply transforms, one unit scale, +Y up.
- Compress: Draco or Meshopt for geometry, KTX2/Basis for textures; bake lighting only when the scene
  is static.
- Keep a hero asset under ~2 MB compressed or lazy-load it behind the poster (see `perf-budgets.md`).

## In-site Blender use

- The `blender` plugin (blender MCP/scripts) is confirm-gated in the manifest: it runs arbitrary Python
  inside Blender with the user's privileges and needs Blender 5.1+, its MCP add-on and uv. It installs
  only after the user's OK, and only when a card really needs scripted Blender work.
- Scripted Blender runs are build-time tools, never part of the shipped site bundle.
