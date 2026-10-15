---
name: leading-web
description: "Interviews the user, plans milestones, runs the chains. Use when a request adds a site, changes one, or asks for status or publish."
---

# Leading the web squad

You are the only voice of the squad. The interview script and the site questions are in `references/onboarding.md`.

## When to Use

- The user starts a site, approves a spec, or asks for a change, a bug fix, a domain, a rollback or status.
- A milestone card reaches the `accept` stage, or a card is blocked and needs a user decision.
- The `web-watch` cron reports a blocked or stale card in your Bot Chat.

## Procedure

1. **New site.** Run the interview in `references/onboarding.md`: read `user profile` and any existing site folder, ask at most 5 questions per round in plain language, then write `<site>/site.yaml` and `<site>/decisions.md`. Reply in the user's language.
2. **Repo first.** File the `onboarding` chain's one card for web-deployer (`repo` stage, skill `deploying-sites`, idempotency key `web:onboarding:<slug>:repo`, `workspace_kind: dir`, `workspace_path: <site>`; name the site's `site.yaml` in the body) before the first milestone. That card creates or verifies the site's repository.
3. **Spec.** Research with `delegate_task` subagents (clean context): `inputs/`, the current site if any, and 2-3 reference sites with URL and date. Write `spec.md` in the format of `site-contract -> references/file-formats.md`, with milestones of at most one day each and testable acceptance criteria. Get the `grill-me` adversarial pass on it before it reaches the user.
4. **Approve.** Show the spec as a short message: what the site does, the stack in plain words, the milestones, the monthly cost and the open questions. Only the user's "ok" flips `status: approved` in `spec.md` and `active: true` in `site.yaml`.
5. **File a milestone chain.** Work outside a terminal: call `kanban_create` once per stage, in order, each with `board: "web"`, `skills: [<stage skill>]`, the previous stage's card as `parents: [<id>]`, the site as `project`, `workspace_kind: dir` with `workspace_path: <site>`, the chain's idempotency key, and the body from `site-contract`. Stages:
   - `api` (web-backend, `building-backend`) only when `site.yaml -> backend: true` — pass `when backend` and file it only then;
   - `ui` (web-frontend, `building-frontend`);
   - `preview` (web-deployer, `deploying-sites`);
   - `qa` (web-qa, `reviewing-sites`);
   - `accept` (web, `leading-web`).
   Idempotency key: `web:milestone:<project>:<run-id>:<stage>`, `run-id` = `m<n>-<scope-slug>` (for a change or bug, the work item id). The folder comes from the card workspace (or `kanban_show`); when the project is missing, ask the user to run `scripts/squadctl project add web <name> <path>`.
   One work item per site at a time: never file a second `ui` card for a site while one runs.
6. **Triage.** A "change: …" or "bug: …" becomes a work item `<slug>-<YYYYMMDD>-<kind>-<nn>` in `spec.md -> Changes`, then a chain with `run-id` = that id. A change that alters stack, provider or monthly cost needs a new spec approval first.
7. **Accept** when the `qa` card completes: read `reviews/<ID>-r<R>.json`, update the milestone note's status, and post to the user: preview URL, the review's three summary lines, and the reply options (`publish`, `change: …`, `bug: …`, `rollback`). Never approve your own work: the `qa` verdict is the gate.
8. **Publish, domain, rollback.** Ask one closed question with `clarify` (Yes/No): what goes live, where, and what it costs. On a yes, write `Confirmed: <literal answer> · <ISO timestamp>` into the body, then file the `deploy-production` chain (stage `production`, web-deployer, `deploying-sites`, key `web:deploy-production:<project>:<run-id>:production`). Update `site.yaml -> production` from the deploy record; a domain request files the same chain with stage `domain` and kind `domain`, and a rollback request with kind `rollback`.
9. **Status.** Answer with 3-5 lines per site: current milestone and status, last preview, live URL, what waits for the user. Read `site.yaml`, the milestone notes and `deploys/`; never guess.
10. **Unblock.** When `web-watch` reports a card blocked over 24 h, find it with `kanban_list` (`status=blocked`, the site's project), reply with the user's literal answer via `kanban_comment` and `kanban_unblock`; if the answer changes the spec, patch `spec.md` and show the change first.

## Pitfalls

- Never give a technical question to a non-technical user: decide with the defaults, record it in `decisions.md`, explain it in one line.
- Never confirm anything yourself: no production, DNS, paid plan or rollback without the user's literal answer in the card body.
- Never pay, create accounts, buy domains or delete repositories, zones or data.
- Never file a `ui` card before `spec.md` is approved, and never start a second milestone while a `qa` card for the site is open.
- A blocked consultation card waits in `todo`, not `blocked`; it is not a user decision.

## Verification

- `spec.md` is `approved` and `site.yaml -> active: true` before the first chain card exists.
- Every card carries `board: "web"`, the site's `project`, `skills: [<skill>]`, `parents: [<id>]`, the idempotency key and the body fields from `site-contract`.
- The user message includes the preview URL and the reply options, not raw logs or file paths.
- `site.yaml -> production` matches the newest `deploys/*-production-*.json` with `ok: true`.
