# GSAP ScrollTrigger and Lenis

Scroll choreography rules for site work. The `official:web-development/scrollcraft` keep in your profile
covers narrative scroll patterns; this file covers mechanics and teardown.

## Contents

- Contexts
- ScrollTrigger
- Lenis

## Contexts

- Every animation is created inside `gsap.context(...)` with `revert()` on teardown; one context per
  component, scoped with a ref (`scope: rootRef`), never per element.
- Timelines, not chained tweens: one `gsap.timeline({ scrollTrigger: ... })` per section.

## ScrollTrigger

- Animate `transform` and `opacity` only; `top/left/width/height/box-shadow` force layout or paint.
- `ScrollTrigger.batch` for many small elements; one trigger per element is a frame-rate tax.
- Pin sparingly: pinned sections break `Ctrl+F`, screen readers and mobile URL bars. If pinned, the
  unpinned layout must still make sense.
- Always create triggers after layout settles and call `ScrollTrigger.refresh()` on font load or
  route change.

## Lenis

- One Lenis instance per page, driven by `requestAnimationFrame`, with `lenis.on('scroll',
  ScrollTrigger.update)` wired into the GSAP ticker.
- Respect `prefers-reduced-motion` before starting Lenis: no smooth scroll, no scroll hijack.
- Destroy the instance on unmount; a surviving instance keeps hijacking scroll after navigation.
