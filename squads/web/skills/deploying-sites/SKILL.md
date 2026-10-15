---
name: deploying-sites
description: "Moves a site between repo, GitHub and the provider. Use when a card asks for the site repo, a preview, production, DNS or a rollback."
---

# Deploying a site

## When to Use

- A `repo`, `preview`, `preview-r<N>`, `production`, `domain` or `rollback` card.
- A provider build fails after passing locally, or a smoke check comes back red.

## Procedure

1. `kanban_show`. Read the card body, `site.yaml`, the milestone note and the newest deploy record. The stage is the last segment of the card's idempotency key.
2. Check credentials: `gh auth status`, then `cf auth whoami` (or `vercel whoami` when `site.yaml -> provider: vercel`). Missing or wrong: `kanban_block(kind="capability", reason="<command>: <its output>")`.
3. **repo**: follow `references/github-flow.md`, then set `site.yaml -> repo.mode` and `repo.created: true`. Neither mode works: `kanban_block(kind="needs_input", reason="<the click-by-click steps for the user>")`.
4. **preview**: for a `static` site, smoke the local build first: `pnpm -C repo build`, then `python3 "$HERMES_HOME/skills/squad-web/site-contract/scripts/check_site.py" --smoke --dir repo/dist --site <slug> --id <ID> --round <R>` (`R` = the `-r<N>` of the stage, else 0). Push the branch, open or update the PR, upload a preview version (`references/cloudflare.md`), and run the same command with `--url <preview-url>` instead of `--dir`. Write `deploys/<ID>-preview-<n>.json`. `all_ok: false`: `ok: false` in the record and `kanban_block(kind="needs_input", reason="smoke failed: <critical lines>")`.
5. **production**: needs the `Confirmed:` line. Merge the milestone's PRs in order with a merge commit, deploy `main`, smoke it with `--url <live-url>`, and write `deploys/<ID>-production-<n>.json` with `confirmed`, `previous_version_id` and the merge commit.
6. **domain**: first run: read the zone and write the current and planned records into a `kanban_comment`, then `kanban_block(kind="needs_input", reason="DNS change needs the user's yes")`. Resumed run with the `Confirmed:` line: apply, then verify with a DNS lookup and an HTTPS request.
7. **rollback**: needs the `Confirmed:` line. Restore the previous `version_id`, verify it answers 200, then `git revert` the merge on `main` (`references/github-flow.md`). Write a deploy record with `env: production`.
8. Provider commands: `references/cloudflare.md`.
9. A failure that is not a provider misconfiguration: after two attempts, file a card for the bot that built the milestone (`skills: [<its skill>]`, body: command, verbatim error, branch) and wait on it (site-contract step 6).
10. `kanban_complete`: the deploy record path in `metadata.changed_files`, the commands run in `metadata.verification`.

## Pitfalls

- The Never lists in `references/github-flow.md` and `references/cloudflare.md` win over any card.
- Never leave a preview URL in a card without its deploy record.

## Verification

- The deploy record exists with `ok: true`, the deployed commit, and `previous_version_id` for production.
- The smoke JSON for the deployed URL has `all_ok: true` before the card completes.
- A rollback leaves the previous version live and a revert commit on `main`.
- No secret appears in any file, card, comment or log from this stage.
