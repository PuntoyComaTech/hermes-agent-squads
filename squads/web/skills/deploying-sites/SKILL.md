---
name: deploying-sites
description: "Moves a site between repo, GitHub and the provider. Use when a card asks for the site repo, a preview, production, DNS or a rollback."
---

# Deploying a site

GitHub steps are in `references/github-flow.md`, provider steps in `references/cloudflare.md`. You hold the only credentials.

## When to Use

- A `repo` card (site onboarding), a `preview` card, or a `deploy-production` card.
- The user asks to connect a domain, or to roll back.
- A provider build fails after passing locally, or a smoke check comes back red.

## Procedure

1. `kanban_show`. Read the card body, `site.yaml`, the milestone note and the newest deploy record. Identify the stage: `repo`, `preview`, `production`, `domain` or `rollback`.
2. Confirm the credentials before acting: `gh auth status` shows the token user, and the platform CLI answers one read command (`cf auth whoami`, or the Vercel equivalent). Missing or wrong token -> block with the exact command and what it returned.
3. **repo**: follow `references/github-flow.md`. Create the private repo, or verify the user's empty repo is reachable; push `main`; then set `site.yaml -> repo.created: true` and record what the token can do. If neither path works, block with the click-by-click steps for the user.
4. **preview**: run the smoke pass first against a local build, then push the branch, open or update the PR, upload a preview version, and run `python3 "$HERMES_HOME/skills/squad-web/site-contract/scripts/check_site.py" --smoke --url <preview-url> --site <slug> --id <ID>`. Write `deploys/<ID>-preview-<n>.json` with commit, PR, version id, URL and `ok`. Red smoke -> block naming the failing check; no PR merge, no preview message.
5. **production**: require a `Confirmed:` line with the user's literal answer in the card body. Merge the open PRs for the milestone in order with a **merge commit** (never squash), deploy `main`, smoke it, write `deploys/<ID>-production-<n>.json` with `confirmed`, `previous_version_id` and the merge commit. Then hand the live URL to the lead.
6. **domain**: the DOMAIN CHECK phase collects the current records and the planned ones, writes them into the card, and blocks for the user's yes. The APPLY phase runs only with the `Confirmed:` line; verify with a DNS lookup and HTTPS before completing.
7. **rollback**: require the `Confirmed:` line. Bring the previous `version_id` back on the provider, verify it answers, then `git revert` the merge on `main`. Record the new state in the deploy record.
8. Provider commands: never guess. Find them with `cf cli search "<task>"` (or the provider's own help) and use the form `references/cloudflare.md` records. Wrangler only for the two documented exceptions.
9. Any failure that is not a provider misconfiguration gets a support card to the builder with the command, the verbatim error and the branch. Do not retry in a loop; two attempts, then block.
10. Complete with `kanban_complete`: the deploy record path in `metadata.changed_files`, the commands run in `metadata.verification`.

## Pitfalls

- Secrets, force-push, repository deletion, zone or record deletion, account or payment changes, named-login commands: the Never lists in `references/github-flow.md` and `references/cloudflare.md`; they win.
- Never leave a preview URL in a card without its deploy record; the reviewer needs both.
- Never squash-merge stacked milestone branches: the order of the merges is the release order.

## Verification

- The deploy record exists with `ok: true`, the commit it deployed, and `previous_version_id` for production.
- The live URL answers 200 and the smoke pass is green before the lead tells the user anything.
- `site.yaml -> production` matches the newest production deploy record.
- A rollback restores the previous version and leaves a revert commit on `main`.
- No secret appears in any file, card, comment or log produced by this stage.
