# three.js and React Three Fiber

## Budget

- Bundle: the core plus one loader helper, under ~180 kB gzipped before assets. Add a library only when it removes more code than it adds.
- Assets: glTF/GLB compressed with Draco or Meshopt; textures as KTX2/basis when heavy, never a 4K PNG.
- One canvas per page, loaded after the first render and never on the server: Astro `client:only="react"`, Next.js and TanStack Start a dynamic import in a client component.

## three.js baseline

```js
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));   // never above 2
renderer.setSize(width, height, false);                   // false: CSS owns the size
renderer.outputColorSpace = THREE.SRGBColorSpace;
```

- Resize with a `ResizeObserver` on the container, not `window`.
- Shadows: one directional light with a small shadow map, or none. No `PCFSoftShadowMap` unless it is visible.
- Many repeated objects: `InstancedMesh`, not a mesh per object.
- Reuse vectors and quaternions in the loop (`const v = new THREE.Vector3()` outside `animate`); no allocation per frame.
- Stop the loop when the canvas is off-screen or the tab is hidden.
- Dispose on teardown: geometries, materials, textures, render targets, `renderer.dispose()`.

## React Three Fiber

- `<Canvas dpr={[1, 2]} gl={{ antialias: true }} frameloop="demand">` when nothing animates continuously; switch to `frameloop="always"` only for a live loop.
- Assets through `useLoader`/`useGLTF` inside `<Suspense fallback={...}>` with a real placeholder, never a blank box.
- `useFrame` for per-frame work; keep the callback trivial (a few property writes) and read scroll progress from a shared ref, not from React state.
- drei helpers (`Environment`, `useTexture`, `ScrollControls`, `OrbitControls`, `AdaptiveDpr`) are preferred over hand-written equivalents.
- Dispose: drei handles loaded assets; a geometry or material a component creates (the React Compiler memoizes it, never `useMemo`) is disposed in `useEffect` cleanup.

## Scroll-driven scenes

- Prefer driving the scene from DOM scroll: read a normalized progress in `useFrame` from a GSAP `ScrollTrigger` (`trigger.scroll()`) or a scroll progress ref, and map it to camera position, uniforms or a clip's `mixer.setTime`. Keep the DOM the source of truth for accessibility and pinning.
- `ScrollControls` (drei) only for a page that is one canvas; it brings its own scroller.
- Camera move: interpolate with `damp`/`lerp` (frame-rate independent), never set the camera from a raw scroll listener.
- Reduced motion: replace scroll-driven camera moves with a single static framing.

## Quality and fallback

- Lighting: drei `<Environment preset="studio" />` or three lights; never a single point light on a dark scene.
- Color: `renderer.toneMapping = THREE.ACESFilmicToneMapping`, color textures with `colorSpace = THREE.SRGBColorSpace`. On a phone below 60 fps, cut DPR, then shadows, then geometry.
- Always ship a fallback: a static rendered image (poster) shown while loading, for reduced motion, when WebGL is unavailable, or when the device reports a low tier.
- Canvas needs an accessible name and role, and any information it carries must exist as text or an image elsewhere.

## Verification

- First render never waits on the 3D bundle: the poster covers the canvas area.
- `renderer.info.render` shows no growth over time; triangles and draw calls match the design's budget.
- Off-screen canvas stops its loop; returning to it resumes without a hitch.
- The fallback path is exercised once (blocked WebGL or reduced motion).
- Teardown leaves no canvas, no animation frame and no listener behind.
