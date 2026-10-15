# Motion and scroll animation

One idea per page, a few seconds long.

## Principles

- Animate `transform` and `opacity` only: both stay on the compositor. Never `width`, `height`, `top`, `left` or `margin`.
- Durations: 150-250 ms for state changes, 400-800 ms for entrance; scrubbed scroll progress uses `scrub: 0.5`.
- Easing: `ease-out` for entrances, `ease-in-out` for loops, a soft spring for touch surfaces. No linear except scrubbed progress.
- Never block content on animation: the page must be complete and readable with JavaScript disabled and with `prefers-reduced-motion: reduce`.
- Budget: at most one hero motion, one reveal pattern, one hover idiom. Everything else is instant.

## Reduced motion

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
```

The same branch in JavaScript: `gsap.matchMedia()` with a `(prefers-reduced-motion: reduce)` block that sets final states instead of animating them.

## CSS first

- `transition` for hover, focus, open/close; `@keyframes` for entrance and loading states.
- Scroll-driven CSS (`animation-timeline: view()`/`scroll()`) for simple reveals, wrapped in `@supports (animation-timeline: view())` with a static fallback.
- `IntersectionObserver` for one-shot reveals when a whole animation library is not justified: observe, add a class, unobserve.

## GSAP ScrollTrigger

- Register once per page: `gsap.registerPlugin(ScrollTrigger)`. Never twice for the same plugin.
- One timeline per section, created inside a `gsap.context()` (or the framework-aware equivalent) so teardown reverts everything:

```js
const ctx = gsap.context(() => {
  gsap.timeline({ scrollTrigger: { trigger: section, start: "top 80%", end: "top 30%", scrub: 0.5 } })
      .from(".card", { y: 24, opacity: 0, stagger: 0.08 });
}, section);
// teardown
ctx.revert();
```

- React: `useGSAP(() => { ... }, { scope })` from `@gsap/react`; it reverts on unmount. Vanilla: `ctx.revert()` in the cleanup path.
- Scrubbed values: `scrub: true` ties the timeline to the scrollbar; `scrub: 0.5` adds smoothing. Use `scrub` only when the user is meant to control the pace.
- Pinning: pin a wrapper, never a node inside a flex/grid that reflows, and check `pinSpacing` before changing margins. A pinned section needs an explicit height budget on mobile.
- `markers: true` only while developing; it must never ship.
- `ScrollTrigger.refresh()` after fonts load, images load, a route change or a resize of dynamic content; otherwise triggers fire at the wrong offsets.
- Destroy on teardown: `ScrollTrigger.getAll().forEach((t) => t.kill())` only as a last resort; prefer `ctx.revert()`.
- Skeleton page with several sections: one `ScrollTrigger` per section, `start: "top 80%"`, no global scroll listener anywhere else.

## Framework notes

- Astro islands: mount the animation in a `client:visible` island so it never runs before the section exists.
- React/Next: animation code lives in a client component; never touch `document` during server render.
- Per-frame work belongs to the render loop (`useFrame`/`requestAnimationFrame`), not to a scroll listener; see `three.md` for scroll-driven 3D.

## Verification

- With reduced motion, the page shows every element in its final state, nothing animates, and no content is missing.
- With JavaScript disabled, every section is visible.
- No horizontal scrollbar on a 390 px viewport after any pinned or scrubbed section.
- The performance profile shows no layout or paint on scroll: only composite.
- Every timeline, trigger and observer is destroyed when the component or page unmounts.
