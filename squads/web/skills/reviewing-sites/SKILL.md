---
name: reviewing-sites
description: "Reviews a deployed site preview with six lenses. Use when a qa card reaches web-qa, before anything reaches the user or production."
---

# Reviewing a site

## When to Use

- A `qa` card of a milestone chain: a preview URL and a deploy record exist.
- Your `qa` card resumes after a fix round.
- The manager asks whether a change already in production broke something: same procedure against the live URL.

## Procedure

1. `kanban_show`. Read the card body, `spec.md`, the milestone note, `site.yaml` and the newest `deploys/<ID>-preview-*.json`. No deploy record, or `ok: false`: `kanban_block(kind="needs_input", reason="no deployed preview for <ID>")`.
2. Round `R` = the number of `reviews/<ID>-r*.json` files that exist (0 on the first run).
3. From the site folder run:
   `python3 "$HERMES_HOME/skills/squad-web/site-contract/scripts/check_site.py" --site <slug> --id <ID> --round <R> --url <preview-url> --browser --lighthouse --lighthouse-runs 3 --repo <repo>` (`<repo>`: site-contract step 2)
   It writes `reviews/<ID>-r<R>/checks.json` and `screenshots/`. Then, from the site folder: `python3 "$HERMES_HOME/skills/squad-web/site-contract/scripts/code_audit.py" --id <ID> --round <R> --repo <repo> --url <preview-url>`. It checks the repo is on `web/<ID>` (never switch it yourself: site-contract step 7), runs every quality-gate step, Semgrep and nuclei against the preview, and writes `reviews/<ID>-r<R>/code-checks.json` with a `critical` list; it installs a missing scanner itself (the first run takes a few minutes). Exit 1 on the wrong branch: `kanban_block(kind="needs_input", reason="repo is on <branch>, expected web/<ID>")`. A scanner that could not run is already a `critical` entry, not an exit code. Never re-run to chase a pass. For check_site.py, exit 2 (Chrome, Node or a repo devDependency missing): `kanban_block(kind="capability", reason="<the error line>")`, never a finding.
4. Look at the screenshots, mobile first, then desktop. Then open the preview in the browser (that origin only) and walk the acceptance criteria. On a resumed card, verify each requested change first, then the whole site.
5. Run six `delegate_task` subagents, one per lens in `references/lenses.md`, each with the URL, the criteria, the paths of `checks.json`, `code-checks.json` and the screenshots, and its lens section. The code-review subagent also gets `<repo>` read-only and `site-contract/references/engineering-rules.md`.
6. Write `reviews/<ID>-r<R>.json` in the format of site-contract `references/file-formats.md` section 4.
7. Verdict:
   - `APPROVED`, no critical finding: `kanban_complete`. The `accept` card, a child of yours, then promotes.
   - `FIX`, every finding fixable and `R < site.yaml -> automation.reviewer_rounds`, with N = R + 1:
     1. `kanban_create` the fix card: assignee = the bot that built the finding (web-frontend, or web-backend for a backend finding), `skills: [<its skill>]`, no `parents`, key `web:milestone:<project>:<run-id>:fix-r<N>`, body = your `critical` findings verbatim and round N.
     2. `kanban_create` the re-preview card: web-deployer, `skills: [deploying-sites]`, `parents: [<fix card id>]`, key `web:milestone:<project>:<run-id>:preview-r<N>`.
     3. `kanban_link(parent_id=<re-preview card id>, child_id=<this card id>)`.
     4. `kanban_block(kind="dependency", reason="waiting for preview-r<N>")`. This card resumes when the re-preview completes.
   - `ESCALATE`, a human decision is needed or the rounds are spent: `kanban_block(kind="needs_input", reason="<one plain question>; open: <surviving critical findings>")`.

## Pitfalls

- Your only outputs are the review JSON, `checks.json` and cards: no code edit, commit or deploy.
- Never approve with a critical finding, and never downgrade one to a note.
- Review the whole site on every round: a fix can break a page you approved.
- Browse only the preview's origin.
- Judge Lighthouse numbers from `checks.json` (median of `--lighthouse-runs`); never re-run to chase a pass.

## Verification

- `reviews/<ID>-r<R>.json` has exactly six lens objects, a verdict and three summary lines; every `code-checks.json -> critical` entry appears in a lens.
- Every critical finding names the page, what is wrong and the fix, one line each.
- Every lens cites evidence in `reviews/<ID>-r<R>/`.
- `FIX`: one `fix-r<N>` card, one `preview-r<N>` card linked as this card's parent, and this card in `todo` (dependency block). `ESCALATE`: one `needs_input` block with one question.
