---
name: directing-studio
description: "Directs a studio piece from brief to delivery. Use when a requester's card orders a rendered asset, when the piece chain must be filed, or when a produced render needs the lead's review before delivery."
---

# Directing a studio piece

You run on two kinds of card: the ordering card (steps 1-5, then 7) and the `review` card of the chain (step 6).

## When to Use

- A card on the studio board orders a rendered asset.
- The brief or the storyboard must be written, or the `piece` chain filed.
- A render is ready for review, or came back wrong once.

## Procedure

1. Read the ordering card: project, what the piece is for, where it will be used, deadline. The piece folder is `<project>/studio/<piece-id>/` (id: studio-contract step 1).
2. Write `brief.md` with measurable specs: format, resolution, fps, duration, audio and loudness target, plus one acceptance line per deliverable. Format in studio-contract `references/project-files.md`.
3. Write `storyboard.md`: one row per shot with start, duration, tool, the assets the shot needs and `Samples` for a Blender shot.
4. A missing spec only the requester has: `kanban_block(kind="needs_input", reason="<exact question>")`. Never invent format, deadline, font or licence. The requester's chat gets the block; when no chat filed the order, the `studio-watch` cron posts it to your Bot Chat: ask the user, `kanban_comment` the answer, then `kanban_unblock`.
5. File the `piece` chain with `kanban_create`, one card per stage of `squad.yaml` -> `chains.piece`:
   - `3d` (studio-3d, `skills: [rendering-3d]`) only when the piece `needs_3d` (a Blender shot in the storyboard);
   - `motion` (studio-motion, `skills: [producing-motion]`), `parents: [<3d card>]` when `3d` exists;
   - `review` (studio, `skills: [directing-studio]`), `parents: [<motion card>]`.
   - Every card: `board: "studio"`, the project of the ordering card, `workspace_kind: dir`, `workspace_path: <piece folder>`, idempotency key `studio:piece:<project>:<piece-id>:<stage>`.
   - Body: piece folder path, deliverable list, specs, acceptance lines, and the shots this stage owns.
   - Then `kanban_link(parent_id=<review card>, child_id=<ordering card>)` and `kanban_block(kind="dependency", reason="piece chain filed")`: the ordering card resumes when the review is done.
6. Review (on the `review` card): read the handoff (render paths, `.check.json` reports, contact sheets) and look at each contact sheet with vision. Pass: `kanban_complete` with "accepted" and the deliverable paths. Fail in round 1: file a fix card for the same producer with no parents (key `...:motion-r2` or `...:3d-r2`, body listing each exact fix) and a `review` card (key `...:review-r2`, `parents: [<fix card>]`), `kanban_link(parent_id=<review-r2 card>, child_id=<ordering card>)`, then `kanban_complete` with "fix round filed". Fail in round 2: `kanban_complete` with "rejected" and what is wrong.
7. Deliver (on the ordering card, when it resumes): accepted -> `kanban_complete` with the deliverable paths in `artifacts`, the render check result and one line on what the piece shows; rejected -> `kanban_block(kind="needs_input", reason="<what is wrong>")`. Completing or blocking the ordering card notifies the requester; a comment notifies nobody.

## Pitfalls

- Never accept a render you have not looked at: the contact sheet and a passing `render_check.py` report are both required.
- One fix round per piece; a further round is a new order from the requester.
- A brief with no measurable acceptance line goes back to step 2.

## Verification

- `brief.md` and `storyboard.md` exist, follow studio-contract, and every spec carries a number and a unit.
- Each chain card exists once under its stage key, and parents chain in order.
- The review names the `render_check.py` result and what the contact sheet shows.
- The ordering card ends completed with deliverable paths that exist, or blocked with the reason.
