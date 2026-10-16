# three.js and react-three-fiber

Scene structure and lifecycle for site work. Offline renders (Blender, MP4/WebM) are supplied by
whoever ordered the card; this skill covers live scenes inside the site bundle.

## Contents

- Structure
- Assets
- Disposal

## Structure

- One `<Canvas>` per page region, never one per component; mount it lazily (`next/dynamic` or
  `React.lazy`, `ssr: false`) behind a poster image.
- Clamp DPR (`dpr={[1, 2]}` or lower on mobile); uncapped device pixel ratio is the most common
  mobile GPU killer.
- Keep the render loop imperative: `useFrame` for animation, React state only for user-visible state.
- Off-screen or hidden tab: stop the loop (`visibilitychange`, IntersectionObserver on the canvas).

## Assets

- Load with `useGLTF`/`useTexture` + `Suspense`; show the poster until the first frame renders.
- Compress meshes (Draco or Meshopt) and textures (KTX2/Basis); a hero GLB over ~2 MB needs a reason.
- Prefer one atlas/texture set over many small textures; each texture is a GPU upload.

## Disposal

- On unmount dispose geometries, materials, textures and render targets; react-three-fiber does not
  do it for objects you created manually.
- `useEffect` cleanup returns a function that calls `dispose()` and removes event listeners.
- Never re-create geometry or material inside `useFrame`; hoist or memoize them.
