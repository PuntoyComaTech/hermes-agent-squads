# Squad: Studio

Rendered and standalone assets for the other squads: motion graphics, MP4/WebM clips, 3D renders, glTF
assets and WebGL hero demos. The web and marketing leads order a piece by card on the `studio` board;
the studio lead turns it into a brief and a storyboard, files the `piece` chain, reviews what comes back
and delivers it as a comment on the requester's card.

The split with the web squad: `web-frontend` owns interactive code inside a site; studio owns files that
render or ship as standalone assets. Complex motion, video and 3D never run inside the marketing
producer profile.

## Bots

| Bot | Lane | Does |
|---|---|---|
| `studio` (lead) | design | Brief to `brief.md` and `storyboard.md`, files the chain, reviews renders (contact sheets plus the check report), delivers; no terminal |
| `studio-motion` | design | HyperFrames, Remotion, GSAP/ScrollTrigger, three.js/R3F, Manim, p5.js; runs `render_check.py` |
| `studio-3d` | design | Blender scenes, materials, lighting, Cycles/EEVEE renders, turntables, glTF, through the blender MCP plugin |

## Chain `piece`

Stages: `squad.yaml` -> `chains.piece`. `squadctl chain studio piece --project <slug> --title <piece-id>
[--when needs_3d]` files them, and stage keys are `studio:piece:<project>:<piece-id>:<stage>`, so a rerun
creates nothing twice. No cron.

## Piece folder

`<project>/studio/<piece-id>/` with `brief.md`, `storyboard.md`, `assets/` and `renders/`; formats in
`skills/studio-contract/references/project-files.md`. Renders are checked before handoff.

## Scripts

| Script | Where | Does |
|---|---|---|
| `studio_project.py` | `skills/studio-contract/scripts/` | `init` creates or completes the layout; `check` verifies it and the brief front matter (`--json`) |
| `render_check.py` | `skills/studio-contract/scripts/` | ffprobe spec, EBU R128 loudness via `ffmpeg ebur128`, contact sheet, duration/fps/resolution vs the brief (`--json`); writes `<name>.check.json` per file |

Both are Python 3 with `--help`; `render_check.py` needs `ffprobe`/`ffmpeg` on PATH.

## Skills

| Skill | Used by | Covers |
|---|---|---|
| `directing-studio` | `studio` (lead) | Brief, storyboard, chain, review, delivery |
| `studio-contract` | all three | Piece layout, formats, handoffs |
| `producing-motion` | `studio-motion` | Tool choice and the render check loop |
| `rendering-3d` | `studio-3d` | Blender conventions per shot |

## Keeps and plugins

`squad.yaml` -> `bots.*.skills.keep` and `bots.*.plugins`.

## Install notes

Licence and disclosure asks are the `confirm` items in `squad.yaml`; the builder quotes them and installs
only after the user's explicit OK.

## Operations

Bot visibility, lanes and per-card pins come from `squad.yaml`; `scripts/squadctl plan studio` lists what
an install or change would do.
