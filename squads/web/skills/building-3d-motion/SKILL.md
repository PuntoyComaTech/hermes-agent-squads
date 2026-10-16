---
name: building-3d-motion
description: "Builds 3D, WebGL and complex-motion frontends. Use when a brief needs three.js, react-three-fiber, shaders, GSAP scroll choreography or Blender assets."
---

# Building 3D and complex motion

## When to Use

- The manager routes a `ui` card here because the brief needs 3D (three.js / react-three-fiber), WebGL
  shaders, GSAP ScrollTrigger/Lenis choreography or Blender-made assets.
- A preview fix touches an existing 3D scene, shader or scroll timeline.

Ordinary UI, styling and simple transitions belong to `web-frontend`: never take those cards.

## Procedure

1. `kanban_show`. Read the card body, `spec.md`, the milestone note and `site.yaml`. The scene serves the
   milestone; if the brief is ambiguous about what the scene must communicate, block with that question.
2. Reuse before building. The studio squad owns Blender scenes and rendered clips (`rendering-3d`,
   `producing-motion` skills there), and your profile keeps the motion skills (`official:creative/hyperframes`,
   `official:web-development/scrollcraft`, `official:creative/auteur`). Do not duplicate their material here;
   order rendered assets by card on the `studio` board instead of rendering inside the site repo.
3. Scene work: `references/threejs.md` (three.js and react-three-fiber structure, assets, disposal).
4. Scroll and timeline work: `references/gsap.md` (ScrollTrigger + Lenis, contexts, teardown).
5. Blender pipeline: `references/blender-pipeline.md` (what to model offline, glTF export, compression).
6. Budgets: `references/perf-budgets.md` (LCP/INP caps measured, not assumed).
7. Fallbacks are part of the deliverable: `references/fallbacks.md` (GPU fallback, `prefers-reduced-motion`).
8. Verify in the browser at 390 and 1440 px before completing: no console errors, the fallback path works,
   reduced motion renders the static branch.
9. `kanban_complete`: files in `metadata.changed_files`, what you verified in `metadata.verification`.

## Pitfalls

- Blocking first paint with the 3D bundle: lazy-load the canvas behind a poster (LCP).
- Animations that never stop: pause on `visibilitychange` and when the canvas leaves the viewport.
- WebGL with no fallback: a context-loss and no-WebGL branch ships with every scene.
- Editing the brief or spec to make a scene easier: ask the manager instead.

## Verification

- LCP and INP stay inside `site.yaml -> thresholds` while the scene animates (measure, do not guess).
- `prefers-reduced-motion: reduce` renders the static branch with no scroll hijack.
- With WebGL unavailable the poster or CSS fallback renders; never a blank canvas.
- Unmount disposes geometries, materials, textures and render targets.
