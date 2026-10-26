# Clearing a discarded direction and handing off to a fresh session

Use when the user says a previous direction (a character, a stack, a whole concept) is dead, asks to clean the repo, or asks for a clean prompt to continue in a new session.

The goal: after this, a brand-new session with no history can read one file and build the right thing, and the repo carries no line that reads as current direction but is not.

## Procedure

1. **Name the base first**, in one line, before any tool: the folder and the branch the newest direction lives on. Everything below happens on that branch only.
2. **Inventory the leftovers before deleting anything.** In one batch:
   - `git branch`, `git worktree list`, `git log --oneline -12`, `git status -sb`;
   - stale tool dirs and one-off scripts for the discarded direction: `scripts/`, `tools/`, `.agents/`, `.claude/`;
   - the brief, `AGENTS.md`, and any session-start hook output that mentions the discarded direction: `grep -rn -i '<name>' docs AGENTS.md`;
   - `du -sh` the runtime/evidence dirs, so the report can say what was freed.
3. **Collect the evidence that is still worth having, before deleting.** For a reference site, that is screenshots per chapter, the source bundle, and its audio, kept for study and never shipped. Save it under one runtime dir the repo does not commit (`<repo>/.hermes-live/evidence/<topic>/`, excluded like the rest of `.hermes-live/`), and list those paths in the handoff prompt. A direction being killed does not kill what was learned from it.
4. **Archive, do not orphan, the superseded briefs.** Move old briefs and concept docs out of the repo tree instead of leaving them next to the current one: a repo with two briefs reads as two directions.
5. **Rewrite the brief in place.** Patch the same file, never append: the base branch in its recovery step, the new direction in its direction section, the repository-state section (which branch, what the frontend actually is today, where the previous attempt's code and notes live), and its "where we are / what is next" section. Delete the discarded direction's rules (character sheets, model pipelines) with it.
6. **Commit with the repo's own gate, then re-check `git status`.** See the pitfall below: a rejected commit is not a no-op.
7. **Delete branches only when they are provably redundant**: merged into the work branch AND either absent from the remote or explicitly approved for a forced delete. Report the ones left behind and why, in one line each; ask before deleting a branch that is published or holds an unmerged change.
8. **Never delete another project's folder** as part of this cleanup, and say so: it is a separate repo the user may still want.
9. **Write the handoff prompt as a file** (`<runtime>/next-session-prompt.md`) and paste it in the reply. Rules for it:
   - self-contained: project path, branch, which files to read first, what the user wants, what already exists and where, which tools are installed, what the new session must show the user;
   - it names the evidence paths, not the evidence content;
   - it states the decisions are the new session's to make, so it does not re-litigate the plan;
   - no AI attribution, no reference to "the previous chat" as a source of truth;
   - it ends with where to show the result (the preview tab), not with questions.
10. **Name the profile the new session must open in** when a plugin or tool only exists there (a Blender MCP add-on, for instance); the prompt alone cannot supply it.
11. **Verify zero mentions** of the discarded direction in the brief, `AGENTS.md` and the new prompt (`grep -rc -i`), and that `git status` is clean.

## Pitfalls

- A **pre-commit gate that fails on quality counts or on unresolved imports is usually the checkout, not the change**: the working tree's `node_modules` still belongs to the branch that was there before. Install the branch's lockfile (`bun install --frozen-lockfile`, `pnpm install --frozen-lockfile`) and commit again — do not edit the code until the install has been tried.
- A **rejected commit is not a no-op**: hooks that format or restage leave files staged-but-uncommitted after they fail, so the next `git commit` lands a half commit. After any hook failure, run `git status --short` and commit what is left before moving on.
- **Do not delete a local branch because it is "old"**: `git branch -d` refuses one the remote still tracks or that holds a commit you did not otherwise keep. Read the refusal, then decide: force-delete, or report it.
- **Never open the modelling app (Blender and the like) during a cleanup pass**: the user sees a window they did not ask for and reads it as work against a base they never confirmed. Announce it in one line before it opens, or do not open it.
- **The handoff prompt cannot point at chat history**: a new session has none. Every fact it needs goes in the file, including the branch and the runtime paths.
- **Deleting the evidence along with the direction** costs a rebuild you cannot re-derive (a stalled-WebGL capture, a bundle that no longer servers the same build). Archive first, then delete.
