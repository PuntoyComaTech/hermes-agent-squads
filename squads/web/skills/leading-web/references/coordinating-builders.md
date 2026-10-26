# Coordinating several builders on one milestone

How the manager splits a milestone that holds more than one deliverable, so several builders work at once, each on
one thing, and the pieces fit when they meet.

## Contents

When to split; The contract card; Parallel cards; When one builder needs another; The integration card; Showing the
work; Limits of parallel work.

## When to split

- Split whenever a milestone holds more than one deliverable a fresh worker could finish alone: each 3D asset or
  asset family, each shared look module (palette, atmosphere, ground material), each chapter or page, sound, copy.
- One card = one deliverable a fresh worker finishes and saves within 2-3 hours. A card that bundles several chapters
  grows the worker's context past 300k tokens, each reply takes minutes and nothing gets saved.
- Never file a single card that "does M2" when M2 has chapters, assets and a shared kit: that is four to eight cards.

## The contract card

The first card of a split milestone writes `<site>/milestones/<ID>.contract.md` and nothing else. It is the one place
the parallel cards agree on, so they never guess each other's names:

- every asset: file path, format, scale and units, origin, budget in kB;
- shared tokens: palette (names and values), light rig, camera rules;
- module interfaces: the exported names and signatures each card provides or consumes;
- ownership: which paths each card writes (its `--paths` for `save_progress.py`); two cards never own one path.

Assign it to the builder who will integrate (`web-frontend-pro` for 3D, else `web-frontend`). Its body lists the
deliverables the manager plans, so the contract covers every one of them.

## Parallel cards

- One card per deliverable, each with the contract card as `parents`, all filed at once so the dispatcher runs them
  side by side. Body: the deliverable, the contract path, its `Writes:` paths, the spec sections it needs (not every
  doc), the user's literal words for this piece, and `--max-runtime 3h`.
- A lean shared footer instead of a reading list: read only the named spec sections, save every finished piece,
  contact sheets of 6 frames at most.
- The same profile may hold several running cards: the dispatcher has no per-profile cap unless the root config sets
  `kanban.max_in_progress_per_profile`.

## When one builder needs another

- A builder that needs something another card owns (a mesh, an export name, a token) never writes it itself: it
  files a support card for that owner, links it as the parent of its own card
  (`kanban_link(parent_id=<support>, child_id=<own card>)`) and blocks with `kind="dependency"`. It resumes when the
  support card completes.
- A builder that finds the contract wrong blocks `needs_input` with the exact change. The manager patches the
  contract, then `kanban_comment`s every running card the change touches. Comments wake nobody: builders re-read
  `kanban_show` after each saved piece (site-contract step 8), which is how a running card hears it.

## The integration card

- Parents: every parallel card. It wires the pieces into the page, checks them against the contract, runs the quality
  gate and captures the result on a real GPU. Then the milestone chain continues: `preview`, `qa`, `accept`.
- It fixes seams, never re-does a piece: a piece that does not meet the contract goes back as a `fix` card to its
  owner.

## Showing the work

- File cards with the `kanban_create` tool: its result says `subscribed: true`, and every completion then reaches
  this chat. A card filed from the terminal (`hermes kanban create`, `kanban_chain.py`) is subscribed by the
  squad-kanban plugin; `hermes kanban --board web notify-list <id>` confirms it.
- On every completion: open what the card made (its proof image as a `MEDIA:` line, the live tab refreshed, the
  live renders tab for 3D), say in one line what changed and which parts of the live tab are still old, then say what
  runs next. Never wait for the user to ask "how are we doing?".
- Before any status reply, read `git log` and the board for pieces finished since your last message and show them
  first: a user shown only stale states corrects work that has already changed.

## Limits of parallel work

- Blender: one interactive instance owns the MCP bridge (port 9876); every other modeller runs
  `Blender --background --python <script>` on its own `.blend` file. Two cards never open the same `.blend`.
- One working tree: builders save only their own paths with `save_progress.py`, which commits from a private index
  and waits for another save's lock, so parallel saves never block each other. Never `git add -A`, `stash` or
  `reset`.
- A card running over an hour with no saved piece: read its log; if it is lost in scope, reclaim it, keep its
  unsaved files and split what is left into smaller cards.
