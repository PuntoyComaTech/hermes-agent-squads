---
name: rendering-3d
description: "Renders Blender scenes, turntables and glTF assets. Use when a piece needs a 3D render, a product turntable or a glTF model for a WebGL demo."
---

# Rendering 3D

Blender work runs through the `blender` MCP plugin (official). The plugin executes arbitrary Python inside Blender with the user's privileges, and it ships its own Blender workflow skill: follow that skill for scene, tool and export details, and this one for the squad's conventions.

## When to Use

- A `3d` stage card: scene prep, materials, lighting, stills, a turntable or a glTF export.
- A WebGL demo needs a `.glb`/`.gltf` asset produced from a Blender scene.
- A 3D render came back wrong: framing, lighting, engine artifacts.

## Procedure

1. `scripts/studio_project.py check <folder>`; read `brief.md` and `storyboard.md`; the shots this stage owns are its rows.
2. Work on copies: put scenes under `assets/blender/`, never edit a `.blend` that lives outside the piece folder.
3. Build or open the scene through the plugin's tools; set camera, materials and lighting from the storyboard. Follow `references/blender-workflow.md` for the stage conventions.
4. Draft first: EEVEE or low samples for the review pass, the final engine and sample count for delivery. Render stills and turntables into `renders/`.
5. A turntable is one clean 360-degree orbit over the brief's duration at the brief's fps: constant speed, no cuts, loops seamlessly.
6. Export glTF (`.glb`) for the demos with materials applied, and validate it with `npx gltf-validator <file>` before handoff (studio-3d has no browser; the demo-page load is studio-motion's step); an export that does not validate is not done.
7. Check animated output with `$HERMES_HOME/skills/squad-studio/studio-contract/scripts/render_check.py <file> --brief <folder>/brief.md --contact-sheet auto --json`; stills go through vision against the storyboard row.
8. Log every external model, HDRI or texture in `assets/sources.md` with source, licence and cost before using it.

## Pitfalls

- The plugin runs arbitrary Python in Blender: only read and run scripts from the piece folder, and never point it at files outside it.
- Blender 5.1+, its MCP add-on and uv are prerequisites (`requires.apps`); plugin server discovery does not prove the scene is ready.
- HDRIs and models from marketplaces: CC0 or a recorded licence only; unknown licence means unusable.
- 4K drafts and huge sample counts waste hours; review at draft quality, deliver at brief quality.
- A glTF without materials, or with textures left as absolute paths, breaks the demo; check before exporting to the team.
- Blender version drift (add-on vs app) produces empty renders: check the plugin's doctor output first.

## Verification

- Every deliverable sits in `renders/` under the studio-contract naming.
- Animated output passes `$HERMES_HOME/skills/squad-studio/studio-contract/scripts/render_check.py`; a turntable loops cleanly, stills match their storyboard row.
- The glTF passes `npx gltf-validator <file>` without errors, with materials.
- `assets/sources.md` lists every external asset with its licence.
