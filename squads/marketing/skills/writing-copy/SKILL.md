---
name: writing-copy
description: "Writes concepts, copy and scripts in the brand's voice. Use when a copy stage asks for a concept, per-channel copy, a video script or art direction for the producer."
---

# Writing copy

The idea and the words, in the brand's voice, for one channel at a time. You have no web access: the brief, `brand.md` and the research files are the whole world. Finish, then the chain sends the piece to review.

## When to Use

- A `copy` stage card asks for `concept.md` and `copy.md` for a piece.
- The piece needs two or three campaign territories to choose from.
- A fix card quotes the user's change request for copy.

## Procedure

1. Read the card body, `brief.md`, `brand.md` and `preferences.md`. If the brief or a brand fact is unclear, block with one concrete question instead of guessing.
2. Diverge before choosing: list at least five ideas, discard the first three, keep the odd one.
3. `concept.md`: the idea in one sentence, why it works (the mechanism, in one line), and the art direction (`producing-assets` step 2). For video, a storyboard table: scene, seconds, visual, on-screen text, voice-over.
4. `copy.md`, per channel, one message and one call to action:
   - **Post / story**: first line carries the hook; lengths, hashtags and emojis follow `brand.md`.
   - **Carousel**: one idea per slide, 6-10 slides, the last one asks.
   - **Ad**: three hook variants and two calls to action in the channel's sizes.
   - **Email**: subject of 45 characters or less, preheader, one goal; plain-text version included.
   - **Landing**: promise, problem, mechanism, proof, offer, objections, FAQ, one action.
   - **Article**: search intent first, the direct answer at the top, clear H2s.
   - **Script**: hook in the first two seconds, beats timed at ~150 words per minute, six-word on-screen text, subtitles, the ask at the end.
5. Write alt text for the images and UTM on every outbound link (`utm_source`, `utm_medium`, `utm_campaign`, `utm_content` = piece id); never on internal links.
6. Run the copy through `bundled:humanizer` and strike the machine tells: "in today's fast-paced world", "it is worth noting", "unlock", "dive in", "not only... but also", stacked dashes, bold on every phrase. In other languages, the same class of clichés.
7. `sources.md`: name the `brand.md` proof point every claim rests on; facts and external phrases keep their source (`brand-contract`).
8. Hand off with `kanban_complete`, every written path in `metadata.changed_files` and the mechanism named in one line.

## Pitfalls

- Claims without a verified proof point; figures without a source and a date.
- The same copy pasted across networks.
- Manufactured urgency or scarcity; comparisons against a competitor that are not factual.
- Changing what the user asked to keep, or the call to action, to fit a line.
- Sounding like the category instead of the brand: check the voice samples before shipping.

## Verification

- One message and one call to action; the hook sits in the first line (video: first 2 s).
- Every claim maps to a `brand.md` row marked verified, with permission where a person is quoted.
- Copy respects the voice samples, vocabulary and form of address in `brand.md`.
- `concept.md`, `copy.md` and `sources.md` exist under the piece folder, and the handoff names the mechanism.
