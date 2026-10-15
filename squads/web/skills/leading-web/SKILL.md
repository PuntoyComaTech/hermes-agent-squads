---
name: leading-web
description: "Leads the web squad: interview, spec, milestones, launch. Use when a request adds a site, changes one, or asks for status or publish."
---

# Leading the web squad

## When to Use

- The user starts a site, approves a spec, or asks for a change, a bug fix, a domain, a rollback or status.
- An `accept` card reaches you, or a card is blocked and needs a user decision.
- The `web-watch` cron reports a card in your Bot Chat.

## Procedure

1. **New site.** The site needs a project. When none exists, ask the user to have the builder run `squadctl project add web <name> <absolute folder>`; that folder is `<site>`. Run the interview in `references/onboarding.md`, then write `<site>/site.yaml` and `<site>/decisions.md`.
2. **Repo first.** File the `onboarding` chain (`squad.yaml -> chains.onboarding`) per site-contract step 4, without `parents`, key `web:onboarding:<project>:init:repo`.
3. **Spec.** Research with `delegate_task` subagents: `inputs/`, the current site if any, and 2-3 reference sites with URL and date. Write `spec.md` in the format of site-contract `references/file-formats.md` section 2, milestones per `references/onboarding.md` section 3. Run `official:software-development/grill-me` on it before the user sees it.
4. **Approve.** Send the plan message of `references/onboarding.md` section 4. Only the user's "ok" sets `status: approved` in `spec.md` and `active: true` in `site.yaml`.
5. **Milestone chain.** One card per stage of `squad.yaml -> chains.milestone`, in order, each with the previous card as `parents`, fields per site-contract step 4; skip `api` unless `site.yaml -> backend: true`. `run-id` = `m<n>-<scope-slug>`, or the work item id for a change or bug.
6. **Triage.** "change: ..." or "bug: ..." becomes a work item `<slug>-<YYYYMMDD>-<kind>-<nn>` in `spec.md -> Changes`, then a milestone chain with that id as `run-id`. A change to stack, provider or monthly cost needs a new spec approval first.
7. **Accept.** On your `accept` card: read the newest `reviews/<ID>-r<R>.json`, set the milestone note's `status: approved`, and `kanban_block(kind="needs_input", reason=<message>)` with the preview URL, the review's three `summary` lines and the reply options `publish`, `change: ...`, `bug: ...`, `rollback`; a board run cannot message the user, the block reaches your Bot Chat. On the reply, run step 6 or 8, then `kanban_complete(board: "web", task_id: <accept card>, summary: "<the reply>")`.
8. **Publish, rollback.** Ask one Yes/No question with `clarify`: what goes live, where, and the monthly cost. On a yes, put the `Confirmed:` line (site-contract Pitfalls) in the body and file one web-deployer card, `skills: [deploying-sites]`, stage `production` (chain `deploy-production`) or `rollback`, key `web:deploy-production:<project>:<run-id>:<stage>`. Then copy `url`, `version_id` and the deploy time from the new `deploys/*-production-*.json` into `site.yaml -> production`.
9. **Domain.** File the same card with stage `domain` and no `Confirmed:` line. When the deployer blocks with the planned DNS records, show them to the user and ask Yes/No; post the yes as a `kanban_comment` with the `Confirmed:` line, then unblock (step 11).
10. **Status.** 3-5 lines per site from `site.yaml`, the milestone notes and `deploys/`: current milestone and status, last preview, live URL, what waits for the user.
11. **Unblock.** For a card `web-watch` reports: `kanban_show` it, ask the user its question, post the literal answer with `kanban_comment`, then `kanban_unblock`. If the answer changes the spec, patch `spec.md` and show the change first.

## Pitfalls

- Never ask a non-technical user a technical question: decide with the defaults in `references/onboarding.md`.
- Never pay, create accounts, buy domains, or delete repositories, zones or data.
- Never file a `ui` card before `spec.md` is approved. One work item per site at a time: no new chain while a card of the previous one is open.

## Verification

- `spec.md` is `approved` and `site.yaml -> active: true` before the first milestone card exists.
- Every card matches site-contract steps 4 and 5.
- User messages carry the preview URL and the reply options, never raw logs or file paths.
- `site.yaml -> production` matches the newest `deploys/*-production-*.json` with `ok: true`.
