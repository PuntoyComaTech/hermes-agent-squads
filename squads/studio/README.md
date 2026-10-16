# Squad: Studio

Rendered and standalone assets for the other squads: motion graphics, MP4/WebM clips, 3D renders, glTF
assets and WebGL hero demos. The web and marketing managers order a piece by card on the `studio` board;
the studio manager writes the brief and storyboard, files the `piece` chain, reviews the renders and
completes the ordering card with the deliverables.

The split with the web squad: `web-frontend` owns interactive code inside a site; studio owns files that
render or ship as standalone assets. Complex motion, video and 3D never run inside the marketing
producer profile.

## Bots

| Bot | Lane | Does |
|---|---|---|
| `studio` (manager) | design | Brief to `brief.md` and `storyboard.md`, files the chain, reviews renders (contact sheets plus the check report), delivers; no terminal |
| `studio-motion` | design | HyperFrames, Remotion, GSAP/ScrollTrigger, three.js/R3F, Manim, p5.js; runs `render_check.py` |
| `studio-3d` | design | Blender scenes, materials, lighting, Cycles/EEVEE renders, turntables, glTF, through the blender MCP plugin |

## Chain `piece`

Stages: `squad.yaml` -> `chains.piece`; the manager files them (skill `directing-studio` step 5). No cron.

## Piece folder

`<project>/studio/<piece-id>/`; layout and formats in `skills/studio-contract/references/project-files.md`.

## Scripts

| Script | Where | Does |
|---|---|---|
| `studio_project.py` | `skills/studio-contract/scripts/` | `init` creates or completes the layout; `check` verifies it and the brief front matter (`--json`) |
| `render_check.py` | `skills/studio-contract/scripts/` | ffprobe spec, EBU R128 loudness via `ffmpeg ebur128`, contact sheet, duration/fps/resolution vs the brief (`--json`); writes `<name>.check.json` per file |

Both are Python 3 with `--help`; `render_check.py` needs `ffprobe`/`ffmpeg` on PATH.

## Skills, keeps and plugins

`squad.yaml` -> `bots.*.skills` and `bots.*.plugins`.

## Install notes

Licence and disclosure asks are the `confirm` items in `squad.yaml`; the builder quotes them and installs
only after the user's explicit OK.

`scripts/squadctl plan studio` lists what an install or change would do.
