---
name: directing-studio
description: "Directs a studio piece from brief to delivery. Use when a requester's card orders a rendered asset, when the piece chain must be filed, or when a produced render needs the lead's review before delivery."
---

# Directing a studio piece

The lead turns the order into `brief.md`, `storyboard.md` and the `piece` chain, reviews what comes back, and delivers it. A piece renders nothing by itself: studio-motion and studio-3d do the producing.

## When to Use

- A card on the studio board orders a rendered asset.
- The brief or the storyboard must be written, or the `piece` chain filed.
- A render is ready for review, or came back wrong once.

## Procedure

1. Read the ordering card: project, what the piece is for, where it will be used, deadline. The piece folder is `<project>/studio/<piece-id>/` (id: studio-contract step 1).
2. Write `brief.md` with measurable specs: format, resolution, fps, duration, audio and loudness target, plus one acceptance line per deliverable. Format in studio-contract `references/project-files.md`.
3. Write `storyboard.md`: one row per shot with start, duration, tool and the assets the shot needs.
4. A missing spec only the requester has: `kanban_block(kind=needs_input)` with the exact question. Never invent format, deadline, font or licence.
5. File the `piece` chain with `kanban_create` on `board: "studio"`, one card per stage (`squad.yaml` -> `chains.piece`):
   - `motion` (studio-motion, `skills: [producing-motion]`);
   - `3d` (studio-3d, `skills: [rendering-3d]`) only with `when: needs_3d`, and then `motion` waits for it;
   - `review` (studio, `skills: [directing-studio]`) waits for the last producing stage.
   - `parents` chains the stages. The idempotency key is `studio:piece:<project>:<piece-id>:<stage>`, the same key a builder-filed chain derives, so a rerun creates nothing.
   - Body: piece folder path, deliverable list, specs, acceptance lines, and the shots this stage owns.
6. Review: read the handoff (render paths, `render_check.py` report, contact sheet) and look at the contact sheet with vision. Green means deliver. A problem means one fix round: comment the exact fixes on the producing card, file `fix` with key `...:motion-r2` (or `...:3d-r2`) plus a second `review-r2` card, and review again. A second failure blocks the card to the requester with what is wrong.
7. Deliver: `kanban_comment` on the requesting card (`board: "studio"`) with the deliverable paths, the render check result, and one line on what the piece shows. The requester's lead talks to the user; the studio lead does not.

## Pitfalls

- Never accept a render you have not looked at: the contact sheet and a passing `render_check.py` report are both required.
- One fix round per review; a further round is a new card only after the requester agrees.
- A brief with no measurable acceptance line goes back to step 2.

## Verification

- `brief.md` and `storyboard.md` exist, follow studio-contract, and every spec carries a number and a unit.
- Each chain card exists once under its stage key, and parents chain in order.
- The review names the `render_check.py` result and what the contact sheet shows.
- The delivery comment sits on the requester's card and lists only paths that exist.
