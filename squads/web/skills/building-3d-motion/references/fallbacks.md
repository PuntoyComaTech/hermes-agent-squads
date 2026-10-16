# GPU fallback and prefers-reduced-motion

Every scene ships with both. They are part of the deliverable, not polish.

## Contents

- GPU fallback
- prefers-reduced-motion

## GPU fallback

- Feature-detect WebGL at boot (`WebGL.isWebGLAvailable()` or a try/catch context creation) and show
  the poster or a CSS layout when it fails; never a blank canvas or a spinner that never resolves.
- Handle `webglcontextlost` / `webglcontextrestored`: pause the loop on loss, rebuild or fall back on
  failed restore.
- Low-power devices: a static branch (AVIF/WebP still or baked render) is an acceptable answer; a
  throttled 3 FPS scene is not.

## prefers-reduced-motion

- `prefers-reduced-motion: reduce` renders the static branch: no smooth scroll (no Lenis), no scroll
  hijack, no entrance animation, autoplay media paused or replaced by stills.
- Detect with `matchMedia('(prefers-reduced-motion: reduce)')` and subscribe to changes; do not sniff
  the OS setting.
- The reduced-motion branch must still tell the same story as the animated one: same content, same
  order, no removed information.
