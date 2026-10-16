# Perf budgets (LCP / INP)

Measured, never assumed. `site.yaml -> thresholds` holds the site's numbers; when it says nothing,
use these defaults and write the measured values into the deploy record.

## Contents

- Budgets
- Measuring
- Keeping inside the budget

## Budgets

- LCP <= 2.5 s on a mid-range mobile profile; the poster image (not the canvas) is the LCP element
  in almost every 3D hero.
- INP <= 200 ms while the scene animates: animation work stays on `requestAnimationFrame`, never in
  scroll or input handlers.
- JS added by the scene: keep the 3D chunk out of the first route; lazy-load it after first paint.

## Measuring

- Local: the site's own checks (`check_site.py --smoke`) plus a Lighthouse or DevTools performance
  trace at 390 px with CPU throttling.
- Preview: measure on the preview URL, not on localhost; a cold CDN tells the truth about LCP.
- Record the numbers in the card and the deploy record; "feels fast" is not evidence.

## Keeping inside the budget

- One draw-loop, DPR clamp, no per-frame allocations (see `threejs.md`).
- `transform`/`opacity` animation only, `ScrollTrigger.batch` (see `gsap.md`).
- Compressed assets behind a poster (see `blender-pipeline.md`).
- If the budget cannot be met, cut the scene complexity first; a smaller scene beats a heavy one
  with a warning.
