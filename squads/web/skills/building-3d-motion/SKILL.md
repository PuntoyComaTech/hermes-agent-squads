---
name: building-3d-motion
description: "Builds 3D, WebGL and complex-motion frontends. Use when a brief needs three.js, react-three-fiber, shaders, a motion library (GSAP/ScrollTrigger, Lenis, Motion, Theatre.js, Lottie/Rive) or Blender-derived assets."
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
2. Reuse before building. Your profile keeps the motion, design and scroll skills
   (`official:web-development/scrollcraft`, `official:creative/impeccable`,
   `bundled:claude-design`, `bundled:design-md`, `bundled:popular-web-designs`), and
   `references/animation-libraries.md` says which library fits which brief. Offline assets
   (Blender glTF, video, audio) are supplied by whoever ordered the card: ask for them on the
   card; never render them inside the site repo.
3. Pick the library before writing motion code: `references/animation-libraries.md` (when to use each
   one, its bundle cost and its off switch).
4. Scene work: `references/threejs.md` (three.js and react-three-fiber structure, assets, disposal).
5. Scroll and timeline work: `references/gsap.md` (ScrollTrigger + Lenis, contexts, teardown).
6. Blender pipeline: `references/blender-pipeline.md` (what to model offline, glTF export, compression).
7. Budgets: `references/perf-budgets.md` (LCP/INP caps measured, not assumed).
8. Fallbacks are part of the deliverable: `references/fallbacks.md` (GPU fallback, `prefers-reduced-motion`).
9. Verify in the browser at 390 and 1440 px before completing: no console errors, the fallback path works,
   reduced motion renders the static branch.
10. `kanban_complete`: files in `metadata.changed_files`, what you verified in `metadata.verification`.

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
