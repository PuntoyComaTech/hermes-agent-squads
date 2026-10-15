---
name: producing-assets
description: "Produces statics, carousels, landings and documents. Use when an asset stage asks for the rendered files at the channel's exact sizes, with sources and previews."
---

# Producing assets

You build with code what the creative imagined: HTML and CSS with the brand's tokens, rendered at exact sizes, checked before the reviewer sees them. Complex motion, video and 3D belong to the studio squad — say so in the handoff instead of forcing a clip out.

## When to Use

- An `asset` stage card names `copy.md` and asks for the piece's production files.
- A fix card asks for a visual, size or rendering change.
- A document or an email needs the brand's identity applied.

## Procedure

1. Read the card, `concept.md`, `copy.md`, `DESIGN.md` and `preferences.md`. Missing `DESIGN.md` or missing copy means `kanban_block(kind=needs_input)`, not an invented palette or a rewritten line.
2. Compose with the brand's tokens (`DESIGN.md`), the piece templates and the layout rule: background and scene, one hero, movement. Write source files under `source/` so the piece can be rendered again.
3. Work per type at the exact size, and verify each file's real dimensions before calling it done:
   - post and carousel: 1080×1350 or 1080×1080, one file per slide;
   - story and reel cover: 1080×1920 with safe zones;
   - ad: each placement's size (1080×1080, 1080×1350, 1080×1920, 1200×628);
   - email: 600 px wide HTML from the MJML-style template, plain-text version, unsubscribe placeholder;
   - landing: responsive static page, meta and OG tags, the form wired to a provider or service, UTM on links;
   - document: `document.md` to a branded PDF (A4 or letter per the brand's country), tables inside the margins.
4. Images, in order: the brand's own from `identity/`; stock with a commercial licence, downloaded and logged; then generated images within the monthly cap. AI never produces the final logo, and generated faces or voices are never presented as real customers.
5. Copy every external asset into `assets/`, named `<piece-id>-<channel>-<NN>.<ext>`, and log origin, licence and cost in `sources.md` with the piece's claims. Unlicensed or unknown means unusable.
6. Render with the local tools, then look at every output with vision: legibility on a phone width (about 390 px), contrast, crop, safe zones. Fix and re-render within three attempts; if it still fails, block explaining exactly what fails.
7. For a short HyperFrames clip: load the `hyperframes` skill, keep it under the length the brief asks for, and keep heavy 3D, long video or complex motion for the studio squad — note it in the handoff.
8. Hand off with `kanban_complete`, every file in `metadata.paths`, and the checks you ran.

## Pitfalls

- Shipping a size that is almost right: crop or letterbox before the reviewer sees it.
- Text baked at untested sizes; check at 390 px, not only at full width.
- An AI image's general aspect ratio used as-is instead of recomposed for the exact canvas.
- Changing the meaning, the price or the call to action of the copy to make a layout fit — adjust the minimum or block.
- Publishing anything: you produce, the user decides, the lead delivers.

## Verification

- Every output file exists, is at the exact requested size and opens without error.
- `sources.md` lists every external asset with licence, origin and cost; generated images are labeled.
- A mobile preview exists for landings and emails; contrast and safe zones checked.
- The handoff names the checks that ran; nothing went out of the piece folder except its own files.
