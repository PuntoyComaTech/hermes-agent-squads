---
name: producing-assets
description: "Produces statics, carousels, landings, emails and PDFs. Use when an asset stage asks for the rendered files at the channel's exact sizes, with sources and previews."
---

# Producing assets

HTML and CSS with the brand's tokens, rendered at exact sizes and checked before review. Long video, complex motion and 3D belong to the studio squad. Conventions: `brand-contract`.

## When to Use

- An `asset` stage card names `copy.md` and asks for the piece's files.
- An `asset-r<N>` or `asset-c<N>` card asks for a visual, size or rendering change.
- A document or an email needs the brand's identity.

## Procedure

1. Read the card, `concept.md`, `copy.md`, `DESIGN.md` and `preferences.md`. Missing `DESIGN.md` or copy: block per `brand-contract` step 7. Never invent a palette or rewrite a line.
2. Compose with the `DESIGN.md` tokens and the `brand-contract -> Formats` layout. Write source files under `source/` so the piece renders again.
3. Render each type at its `brand-contract -> Formats` spec and the brief's sizes; check each file's real dimensions.
4. Images, in this order: the brand's own from `identity/`; stock with a commercial licence; generated images up to `brand.md -> generated_images` per month. Never generate the final logo. Never present a generated face or voice as a real customer.
5. Copy every external asset into `assets/` as `<piece-id>-<channel>-<NN>.<ext>` and log origin, licence and cost in `sources.md`.
6. Check every output with `vision_analyze`: legibility at 390 px width, contrast, crop, safe zones. Fix and re-render at most three times; then `kanban_block(kind="needs_input", reason="<what still fails>")`.
7. Short clip: load `hyperframes` and keep it within the brief's length. Long video, complex motion or 3D: state in the handoff that the studio squad owns it.
8. Hand off per `brand-contract` step 6, with the checks you ran in `metadata.checks`.

## Pitfalls

- A size that is almost right: crop or letterbox to the exact canvas.
- An AI image used at its native aspect ratio instead of recomposed for the canvas.
- Changing the meaning, price or call to action of the copy to fit a layout: adjust the layout or block.

## Verification

- Every output file exists, opens, and has the exact requested size.
- `sources.md` lists every external asset with origin, licence and cost; generated images are labeled.
- Landings and emails have a mobile preview at 390 px.
- Every written file is inside the piece folder.
