---
name: rendering-3d
description: "Renders Blender scenes, turntables and glTF assets. Use when a piece needs a 3D render, a product turntable or a glTF model for a WebGL demo."
---

# Rendering 3D

Blender work runs through the `blender` MCP plugin (official). Its Blender workflow skill covers scene, tool and export details; this one covers the squad's conventions.

## When to Use

- A `3d` stage card: scene prep, materials, lighting, stills, a turntable or a glTF export.
- A WebGL demo needs a `.glb`/`.gltf` asset produced from a Blender scene.
- A 3D render came back wrong: framing, lighting, engine artifacts.

## Procedure

1. `python3 "$HERMES_HOME/skills/squad-studio/studio-contract/scripts/studio_project.py" check <folder>`; read `brief.md` and `storyboard.md`; the shots this stage owns are its rows.
2. Work on copies: scenes live in `assets/blender/`; never edit a `.blend` outside the piece folder.
3. Build or open the scene through the plugin's tools; set camera, materials and lighting from the storyboard. Follow `references/blender-workflow.md` for the stage conventions.
4. Draft first: EEVEE or low samples for the review pass, the final engine and the storyboard's `Samples` count for delivery. Render stills and turntables into `renders/`.
5. Export glTF (`.glb`) for the demos with materials applied, and validate it with `npx -y @gltf-transform/cli validate <file>` before handoff; an export with validation errors is not done. The demo-page load is studio-motion's step.
6. Check animated output with `python3 "$HERMES_HOME/skills/squad-studio/studio-contract/scripts/render_check.py" <file> --brief <folder>/brief.md --contact-sheet auto --json`; stills go through vision against the storyboard row.

## Pitfalls

- The plugin runs arbitrary Python in Blender: only read and run scripts from the piece folder, and never point it at files outside it.
- Plugin server discovery does not prove the scene is ready: open the scene and render one still first.
- 4K drafts and huge sample counts waste hours; review at draft quality, deliver at brief quality.
- A glTF without materials, or with textures left as absolute paths, breaks the demo.

## Verification

- Every deliverable sits in `renders/` under the studio-contract naming.
- Animated output passes `render_check.py`; a turntable loops cleanly, stills match their storyboard row.
- The glTF passes `npx -y @gltf-transform/cli validate <file>` without errors, with materials.
- `assets/sources.md` lists every external asset with its licence.
