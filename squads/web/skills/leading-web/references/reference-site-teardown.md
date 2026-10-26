# Reference site teardown

How to dissect a site the user points at as inspiration, so `spec.md` carries its
method as measured facts instead of adjectives.

## Contents

What the teardown must produce; Procedure; Capturing WebGL scenes with a real GPU; Weigh the page; Contact sheets.

## What the teardown must produce

1. The stack: framework, renderer, and the animation, scroll and post-processing
   libraries with versions.
2. The scene list in play order, each row mapped to one of our milestones.
3. Motion timing and audio mix quoted as numbers.
4. A clear split of what we copy (method, timings, structure) and what we build
   ourselves (3D models, textures, audio, code).

Their models, textures, audio files and code are owned by someone else. Capture
how it moves and name our own assets in the spec, so no builder drops a
downloaded asset into the repo.

## Procedure

1. **Walk it in a real browser first.** `new_tab(url)`, then wait for the loader —
   a heavy hero page can keep `document.body.innerText` empty for 20-30 s. Read the
   text and shoot one frame per chapter.
2. **Capture scroll-driven chapters with wheel events.** Virtual-scroll sites
   (Lenis, Locomotive, pinned ScrollTrigger sections) hold `window.scrollY` at 0 and
   only advance on wheel deltas, so a flat `scrollY` is not a failed capture:

   ```python
   for _ in range(6):
       cdp('Input.dispatchMouseEvent', type='mouseWheel',
           x=640, y=300, deltaX=0, deltaY=120)
       time.sleep(0.08)
   time.sleep(2.2)
   capture_screenshot()
   ```

   Save each frame under the workspace and repeat until the chapter indicator stops
   changing.
3. **Prove every frame is real before writing anything.** `capture_screenshot()`
   returns a path even when the WebGL context has stalled and the frame is uniform
   dark. Compare hashes (`md5 -q s*.png | uniq -c`) and inspect the distinct ones;
   a run of identical hashes or all-black frames means the context died — reload and
   recapture that stretch instead of reporting a chapter you never saw.
4. **Read the bundle for the true stack.** Fetch the entry JS and count library
   markers rather than inferring from behaviour:

   ```bash
   python3 -I - <<'EOF'
   import re; s = open('entry.js').read()
   for kw in ['new Lenis', 'Lenis(', 'uProgress', 'uChromaticAberration',
              'uReveal', 'Bloom', 'theatre', 'gsap', 'postprocessing']:
       print(kw, s.count(kw))
   EOF
   ```

   Version literals sit in the bundle next to the library's own class definitions;
   shader uniform names (`uProgress`, `uReveal`, `uChromaticAberration`) are the
   cheapest evidence of which effects are real WebGL and which are CSS.
5. **Measure the audio, do not describe it.** Pull the audio URLs out of the bundle,
   download them, and read format and duration with `afinfo` (macOS) or `ffprobe`.
   Mix levels are in the bundle as call-site arguments (`playHover: () => l(wr.hover, .15)`)
   — quote duration and level per sound in the spec. Two measured facts carry further
   than any adjective: whether the whole set is one sprite (one file holding every
   sound, fetched once) and what each sound actually peaks at, which
   `ffmpeg -i <file> -af volumedetect -f null -` reports as mean and max dB whatever
   the bundle says. Carry both into our own sound spec as targets.
6. **Map chapters to our milestones.** A table of their scene -> our equivalent, plus
   the performance budget: these sites are heavy, so ask for a lighter scene set on
   mobile and treat a stalled capture as evidence of the cost, not as bad luck.

## Capturing WebGL scenes with a real GPU

A headless harness browser often has no GPU and falls back to `SwiftShader` (software
GL); a WebGL hero page then stalls, or returns uniform dark frames with no error at all.
Read the renderer before concluding the site is broken:

```python
js("(() => { const c = document.createElement('canvas'); const g = c.getContext('webgl2') || c.getContext('webgl'); const i = g && g.getExtension('WEBGL_debug_renderer_info'); return i ? g.getParameter(i.UNMASKED_RENDERER_WEBGL) : 'n/a'; })()")
```

Software GL there means: drive the machine's own browser for this capture. Playwright
with `channel="chrome"`, `headless=True` and `user_data_dir=tempfile.mkdtemp()` gives a
throwaway profile (no cookies, no logins, nothing of the user's) that still renders on
the real GPU — Metal on Apple silicon — so the matrix effects, the fluid under the
cursor and the shaders all come out intact. Then hash and open the frames as in step 3.

Capture the interactions, not only the scroll: wheel through every chapter, hover a
card, press and hold wherever the page invites it, open the menu, click into a project
to catch its transition. Shoot frames between actions, not only after them — the
transition between two scenes is usually the part worth copying.

If the runner has no video recorder, the PNG frames are the artifact; `ffmpeg` turns
them into a clip when the user needs to see the motion.

## Weigh the page

Capture the network log and sum transfer bytes per type before writing the spec:
total, JS, models and textures, audio, plus the time from navigation to ready. Quote
the reference's number beside our budget in the same sentence, because a 95 MB
reference is the argument for a 2.5 MB budget. Two patterns are worth naming when they
show up: the same audio requested twice, and one sprite file holding every sound.

## Contact sheets

Resize frames with `sips` (always present on macOS) instead of depending on PIL:

```bash
for f in s*.png; do sips -Z 640 "$f" --out "m$f" >/dev/null; done
```

Then open the frames with `vision_analyze`, or show the two or three that carry the
idea with `MEDIA:/absolute/path` in the reply — never paste a path the user cannot click.
