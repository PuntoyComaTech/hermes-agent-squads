# Animation libraries

Which library to reach for, and what each one costs. Read with `perf-budgets.md` (measured caps) and
`fallbacks.md` (the reduced-motion and no-JS branches).

## Contents

- Choosing
- GSAP and ScrollTrigger
- Lenis
- Motion (motion.dev)
- three.js and react-three-fiber
- Theatre.js
- Lottie and Rive
- Reduced motion

## Choosing

| The brief needs | Use | Budget |
| --- | --- | --- |
| Timeline choreography, scroll-linked sections, precise sequencing | GSAP + ScrollTrigger (`gsap.md`) | ~24 kB gz core + ScrollTrigger |
| Smoother wheel/touch scrolling under an existing animation layer | Lenis | ~3 kB gz |
| Small UI transitions, layout and gesture animation, React state-driven motion | Motion (`motion/react`) | ~18 kB gz, tree-shaken |
| A live 3D scene the user rotates, explores or drives with scroll | three.js or react-three-fiber + drei (`threejs.md`) | 150-600 kB gz: lazy-load it |
| Designer-authored, keyframe-ed 3D stage motion, iterated without a rebuild | Theatre.js | bundle only the exported project state |
| Vector icons, loaders, a short illustrated loop, art that must scale | Lottie (JSON) or Rive | Lottie 60-250 kB gz; Rive runtime ~120 kB gz |
| A pre-rendered video as the hero | none of these: ship MP4/WebM behind a poster | see `perf-budgets.md` |

One animation system per page. Two libraries driving the same element fight over `transform` and
double the JS cost; reach for the second only for a separate, isolated component.

## GSAP and ScrollTrigger

- Timelines inside `gsap.context`, `revert()` on teardown; one context per component (`gsap.md`).
- Animate `transform` and `opacity` only; `ScrollTrigger.batch` for repeated elements.
- GSAP is now free under its standard licence; still pin the version and vendor it rather than
  loading a CDN copy the site cannot control.

## Lenis

- One instance per page, driven by `requestAnimationFrame`, wired into the GSAP ticker.
- Never start it under `prefers-reduced-motion: reduce`; destroy it on unmount or it keeps hijacking
  scroll after navigation.

## Motion (motion.dev)

- The successor of Framer Motion: `motion/react` for components, `motion` for vanilla, a subset of
  Motion One for tiny transitions.
- Prefer its transforms/layout animations for UI affordances; it is not a scroll-timeline engine, so
  a scroll-driven story stays on GSAP + ScrollTrigger.
- Import per feature (`motion/react`, `motion/react-client`); the full bundle drags in ordering and
  gesture code a static hero never uses.

## three.js and react-three-fiber

- Structure, asset lifecycle and disposal: `threejs.md`; drei helpers cover cameras, controls,
  environments and loaders, and `<Environment preset="studio">` is a preset name, not a product.
- Always a poster or CSS fallback plus a context-loss branch; lazy-load the canvas behind the poster.
- Cut DPR first, then shadows, then geometry, when a mid-range phone drops below 60 fps.

## Theatre.js

- Designer-owned keyframes exported to a project state JSON that the site loads; good for a staged
  camera move or a product turntable that marketing wants to retime without a code change.
- Keep the editor a dev dependency; ship only the state and the small runtime.

## Lottie and Rive

- Lottie: After Effects vectors as JSON, `lottie-web` or `@lottiefiles/dotlottie-web`. Use for icons,
  loaders and short loops; keep one file under ~250 kB gz and never an unbounded auto-play loop.
- Rive: interactive state machines with runtime input, useful when the same art reacts to hover,
  scroll progress or a form state.
- Both are decorative unless they carry information: the information must also exist as text or an
  image.

## Reduced motion

- Every library here has an off switch: skip GSAP timelines, don't start Lenis, disable Motion
  transitions, freeze the Theatre.js sequence at its first frame, show the Lottie/Rive first frame as
  a static image.
- The `prefers-reduced-motion: reduce` branch is a complete static version of the same content, not a
  shortened animation, and it is part of the deliverable (`fallbacks.md`).
- Pause anything that keeps running when the tab or the canvas leaves the viewport.
