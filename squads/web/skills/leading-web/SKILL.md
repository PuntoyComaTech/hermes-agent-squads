---
name: leading-web
description: "Runs the web squad: interview, spec, milestones, launch. Use when a request adds a site, changes one, or asks for status or publish."
---

# Leading the web squad

## When to Use

- The user starts a site, approves a spec, or asks for a change, a bug fix, a domain, a rollback or status.
- An `accept` card reaches you, or a card is blocked and needs a user decision.
- The `web-watch` cron reports a card in your Bot Chat, or in your messaging channel when one is connected.

## Procedure

1. **New site.** The site is the project this chat runs in; `<site>` is its primary folder (`desktop_project` `list` -> the active row; outside Desktop the `*` row of `hermes -p web project list`, or the folder the channel prompt names). No project: ask the user to create one with "+" in Sessions (pick web in the bottom selector), choosing its folder, and to open the chat inside it; when they name a folder instead, `tool_call` `desktop_project` `{"action": "create", "name": "<name>", "path": "<their folder>"}` (outside Desktop `hermes -p web project create "<name>" <folder>`). Never pick the folder yourself. Then run `python3 $HERMES_HOME/scripts/project_sync.py` so the workers get it. Set `site.yaml -> repo.path` (site-contract step 2), run the interview in `references/onboarding.md`, then write `<site>/site.yaml` and `<site>/decisions.md`.
2. **Strict base and access, before any card.** Run site-contract `references/project-base.md` yourself, in this order and without asking: the base (`site_base.py --site <site folder>`, one command that reads `site.yaml`: the stack's official create CLI, packages through `pnpm add` with no version, strict TypeScript, the full quality gate, git hooks, first commit; it must end with `pnpm quality` green; when the JSON has `next`, fix the template code it names and run it again), then the access check (`web_access.py`): a login the user already has is reused; a missing CLI is installed; a missing login is started for them and opened as a tab. Then file the `onboarding` chain (`squad.yaml -> chains.onboarding`) per site-contract step 4, without `parents`, key `web:onboarding:<project>:init:repo`.
3. **Spec.** Research with `delegate_task` subagents (they run the cheap delegation model of this profile; never research on your own model): `inputs/`, the current site if any, and 2-3 reference sites with URL and date. Write `spec.md` in the format of site-contract `references/file-formats.md` section 2, milestones per `references/onboarding.md` section 3. Run `official:software-development/grill-me` on it before the user sees it.
4. **Approve.** Send the plan message of `references/onboarding.md` section 4. Only the user's "ok" sets `status: approved` in `spec.md` and `active: true` in `site.yaml`.
5. **Milestone chain.** First put `<repo>` on the work item's branch (site-contract step 7). A TanStack site's first `api` card is its response headers in the Start server middleware (site-contract `references/project-base.md`). One card per stage of `squad.yaml -> chains.milestone`, in order, each with the previous card as `parents`, fields per site-contract step 4; skip `api` unless `site.yaml -> backend: true`. `run-id` = `m<n>-<scope-slug>`, or the work item id for a change or bug.
6. **Route models and specialists.** `web-backend` runs the `code-routine` lane by default. For architecture, auth, data-model or migration cards, pin the `code-complex` lane's model on the card at creation: the kanban card fields are `model` and `provider` (`hermes kanban create --model <model> --provider <provider>`; `provider` requires `model`), values from `local/installed.yaml -> lanes.code-complex`. File 3D, WebGL or complex-motion UI on `web-frontend-pro` (`skills: [building-3d-motion]`) only when the brief needs it; it is optional (`squadctl apply web --with web-frontend-pro`) and `web-frontend` owns ordinary UI.
7. **Triage.** "change: ..." or "bug: ..." becomes a work item `<slug>-<YYYYMMDD>-<kind>-<nn>` in `spec.md -> Changes`, then a milestone chain with that id as `run-id`. A change to stack, provider or monthly cost needs a new spec approval first.
8. **Accept.** On your `accept` card: read the newest `reviews/<ID>-r<R>.json`, set the milestone note's `status: approved`, and `kanban_block(kind="needs_input", reason=<message>)` with the preview URL, the review's three `summary` lines and the reply options `publish`, `change: ...`, `bug: ...`, `rollback`; a board run cannot message the user, the block reaches your Bot Chat or messaging channel. On the reply, run step 7 or 9, then `kanban_complete(board: "web", task_id: <accept card>, summary: "<the reply>")`.
9. **Publish, rollback.** Ask one Yes/No question with `clarify`: what goes live, where, and the monthly cost. On a yes, put the `Confirmed:` line (site-contract Pitfalls) in the body and file one web-deployer card, `skills: [deploying-sites]`, stage `production` (chain `deploy-production`) or `rollback`, key `web:deploy-production:<project>:<run-id>:<stage>`. After the merge, `git -C <repo> switch main && git -C <repo> pull --ff-only` (site-contract step 7). Then copy `url`, `version_id` and the deploy time from the new `deploys/*-production-*.json` into `site.yaml -> production`.
10. **Domain.** File the same card with stage `domain` and no `Confirmed:` line. When the deployer blocks with the planned DNS records, show them to the user and ask Yes/No; post the yes as a `kanban_comment` with the `Confirmed:` line, then unblock (step 12).
11. **Status.** 3-5 lines per site from `site.yaml`, the milestone notes, the newest lines of `milestones/<ID>.progress.log` (what the builder saved and when) and `deploys/`: current milestone and status, last saved piece, last preview, live URL, what waits for the user.
12. **Live view, always on.** As soon as the base exists, and when the user asks for the site or says the tab is gone: `python3 "$HERMES_HOME/skills/squad-web/site-contract/scripts/live_view.py" start --repo <repo>` (reuses a running server), then `tool_call` `desktop_preview` with `{"action": "open", "url": "<its url>", "label": "<site name>"}`. Do not reopen it on your own when the user comes back to the chat: the Desktop keeps a chat's tab, and the squad-hub plugin puts a lost one back; a reopen from you reloads the page. The site lives in that tab beside the chat and reloads on every file a builder saves; never show the site inline in the message or as a screenshot instead of the tab. Outside the Desktop app, send the URL and say it opens as a tab in the Desktop chat. `live_view.py stop` only when the user asks.
13. **Unblock.** For a card `web-watch` reports: `kanban_show` it, ask the user its question, post the literal answer with `kanban_comment`, then `kanban_unblock`. If the answer changes the spec, patch `spec.md` and show the change first.

## Pitfalls

- Never ask a non-technical user a technical question: decide with the defaults in `references/onboarding.md`.
- Never tell the user to install or log in to a tool, and never announce that you will "check how Cloudflare works": `web_access.py` checks, installs and starts the login; the user only approves the provider's page in the tab.
- Never pay, create accounts, buy domains, or delete repositories, zones or data.
- Never file a `ui` card before `spec.md` is approved. One work item per site at a time: no new chain while a card of the previous one is open.
- Never route an ordinary UI card to `web-frontend-pro`: it exists only for 3D, WebGL or complex motion. Pin the `code-complex` model on a `web-backend` card only for architecture, auth, data-model or migration work.

## Verification

- `spec.md` is `approved` and `site.yaml -> active: true` before the first milestone card exists.
- Before the first card: `pnpm -C <repo> quality` exits 0 and `web_access.py status` shows `gh` and the provider CLI logged in.
- Every card matches site-contract steps 4 and 5.
- User messages carry the preview URL and the reply options, never raw logs or file paths.
- `site.yaml -> production` matches the newest `deploys/*-production-*.json` with `ok: true`.
