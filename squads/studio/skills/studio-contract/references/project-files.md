# Piece files

Formats used by every studio bot. A piece folder is `<project>/studio/<piece-id>/`; the scripts in
`studio-contract/scripts/` read and write these files.

```text
<piece-id>/
  brief.md            the requester's specs; written by the lead (studio_project.py init --overwrite rewrites it)
  storyboard.md       shots and timing; written by the lead
  assets/             inputs: fonts, audio, images, models, .blend files
    sources.md        one row per external asset
  renders/            outputs and their checks
    <piece-id>-<shot>-<NN>.mp4          a rendered deliverable
    <piece-id>-<shot>-<NN>.check.json   render_check.py report
    <piece-id>-<shot>-<NN>.contact.png  contact sheet
```

## brief.md

YAML front matter at line 1, flat `key: value` lines (no nesting), then free notes. `render_check.py`
and `studio_project.py check` read the keys; never rename them.

```yaml
---
piece: 20261015-hero-loop
title: Hero loop for the site
requester: web
format: mp4
duration: 5.00
fps: 30
resolution: 1920x1080
audio: stereo
loudness: -23.0
---

## Objective

One paragraph: where the piece is used and what it must communicate.

## Acceptance

- [ ] The loop reads as one gesture: the camera settles in the last second.
- [ ] Text stays legible at 320 px wide.
```

`duration`, `fps` and `resolution` must be positive numbers; `-` counts as unset. `loudness` is checked
with a 0.5 LU tolerance by `render_check.py` unless a flag overrides it.

## storyboard.md

One row per shot. `Start` and `Duration` are seconds from 0; the sum must match `duration`. `Tool` is
one of HyperFrames, Remotion, three.js/R3F, GSAP, Manim, p5.js, Blender. `Assets` names files that exist
in `assets/`, so the producing stage never invents an input. `Samples` is the delivery sample count for a
Blender shot (`-` when it does not apply).

| # | Shot | Start | Duration | Tool | Assets | Samples | Acceptance |
|---|---|---|---|---|---|---|---|
| 1 | Wide establishing | 0.0 | 2.0 | HyperFrames | assets/brand-mark.png | - | Logo legible, enters by 0.4 s |
| 2 | Product orbit | 2.0 | 3.0 | Blender | assets/blender/watch.glb | 256 | One constant-speed revolution |

## assets/sources.md

Append one row per external asset before it is used. `Licence` is a concrete identifier
(`CC0-1.0`, `CC-BY-4.0`, `owned`, vendor name); an empty or unknown licence means the asset is unusable.

| File | Source | Licence | Cost | Added by |
|---|---|---|---|---|
| assets/fonts/Example-Display.woff2 | example.com/fonts | owned | - | studio-motion |

## renders/ and the check report

- Deliverables: `<piece-id>-<shot>-<NN>.<ext>`, `NN` counting from `01`; a new version is a new `NN`.
- `render_check.py FILE --brief brief.md --contact-sheet auto --json` writes `<name>.check.json` next to
  the render and exit 0 means the spec, the EBU R128 loudness and the contact sheet all passed.
- The report holds `duration`, `fps`, `resolution`, `loudness.integrated_lufs` and `violations`; hand the
  path to the lead in `metadata.paths`.
- Interactive deliverables with `format: html` live in `renders/<piece-id>-<shot>-<NN>/` and are verified
  in the browser, not with `render_check.py`.
