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

`storyboard` (lead) → `3d` (only with `--when needs_3d`) → `motion` → `review` (lead, one fix round).
Delivery is a comment on the requester's card. Stage keys are `studio:piece:<project>:<piece-id>:<stage>`,
so a rerun or a builder-filed chain (`squadctl chain studio piece --project <slug> --title <piece-id>
[--when needs_3d]`) creates nothing twice. No cron.

## Piece folder

`<project>/studio/<piece-id>/` with `brief.md`, `storyboard.md`, `assets/` and `renders/`; formats in
`skills/studio-contract/references/project-files.md`. Renders are checked before handoff.

## Scripts

| Script | Where | Does |
|---|---|---|
| `studio_project.py` | `skills/studio-contract/scripts/` | `init` creates or completes the layout; `check` verifies it and the brief front matter (`--json`) |
| `render_check.py` | `skills/producing-motion/scripts/` | ffprobe spec, EBU R128 loudness via `ffmpeg ebur128`, contact sheet, duration/fps/resolution vs the brief (`--json`) |

Both are Python 3 with `--help`; `render_check.py` needs `ffprobe`/`ffmpeg` on PATH.

## Skills

| Skill | Used by | Covers |
|---|---|---|
| `directing-studio` | `studio` (lead) | Brief, storyboard, chain, review, delivery |
| `studio-contract` | all three | Piece layout, formats, handoffs |
| `producing-motion` | `studio-motion` | Tool choice and the render check loop |
| `rendering-3d` | `studio-3d` | Blender conventions per shot |

Kept from Hermes: `official:creative/creative-ideation` (lead); `hub:skills-sh/remotion-dev/skills/
remotion-best-practices`, `official:creative/hyperframes`, `official:creative/auteur`,
`official:creative/dream-loop`, `bundled:manim-video`, `bundled:p5js` (motion). The blender plugin ships
its own workflow skill.

## Install notes (licence and disclosure asks)

The builder quotes these at install and installs only after the user's explicit OK:

- **Remotion** (hub skill keep): free for individuals and companies up to 3 employees; a paid company
  licence is required from 4 employees.
- **hermes-video-editor** plugin: PolyForm Noncommercial 1.0.0; commercial use needs a separate licence
  from the author.
- **blender** plugin: runs arbitrary Python inside Blender with the user's privileges; needs Blender 5.1+,
  its MCP add-on and `uv` (`requires.apps: [blender>=5.1, uv]`).
- **GSAP / three.js community skills**: none pinned yet. Until their author and licence are reviewed, the
  auteur, hyperframes and dream-loop skills cover both; a new pin is a builder change to this squad.

## Operations

- Workers are hidden, have no memory and run one card at a time; the lead is visible with board
  notifications.
- Weights: `studio-motion` and `studio-3d` run on the `design` lane; per-card `--model` pins are only used
  by the builder at install.
- A piece never edits the requester's project files; it writes only inside its own folder.
