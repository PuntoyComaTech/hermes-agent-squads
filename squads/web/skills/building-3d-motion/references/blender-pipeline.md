# Blender pipeline

What to model offline and how it reaches the site. This file is the bridge only; the Blender workflow
itself (scenes, materials, lighting, Cycles/EEVEE, turntables) lives in the studio squad's
`rendering-3d` skill (`references/blender-workflow.md` there) — read it instead of duplicating it,
and order heavy renders as cards on the `studio` board.

## Contents

- Split of work
- Export
- In-site Blender use

## Split of work

- Model and bake in Blender when the asset is sculpted, lit or textured beyond what code does cheaply;
  keep procedural or parametric geometry in code (three.js/R3F) when it must react to the user.
- Static hero renders can be delivered as WebM/MP4 or AVIF stills by the studio squad: often cheaper
  than shipping a live scene.

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
