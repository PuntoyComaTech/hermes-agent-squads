# Site project file formats

## Contents

1. `site.yaml`
2. `spec.md`
3. `milestones/<ID>.md`
4. `reviews/<ID>-r<R>.json`
5. `deploys/<ID>-<env>-<n>.json`

## 1. `site.yaml`

Written by the lead at onboarding, updated as the site moves. Names only, never secret values.

```yaml
name: "Panadería Sol"
slug: panaderia-sol
emoji: "🥐"
active: false            # true after the user approves the spec
type: static             # static | dynamic_seo | saas
stack: astro             # astro | nextjs | tanstack
backend: false           # true when the site needs the api stage (milestone chain `when backend`)
provider: cloudflare     # cloudflare | vercel
languages: [es, en]
design:
  source: own            # own (DESIGN.md here) | marketing (read the brand, never write)
  brand: null
integrations: [contact_form]
domain:
  name: null
  status: none           # none | pending_user | pending_dns | active
repo:
  owner: "<github owner>"
  name: panaderia-sol
  visibility: private
  created: false         # true once the deployer created or verified it
production:
  url: null
  version_id: null       # live version id
  deployed_at: null
automation:
  reviewer_rounds: 2
  auto_advance: true
  thresholds:
    lighthouse_mobile: {performance: 90, accessibility: 95, best_practices: 90, seo: 95}
    lighthouse_mobile_ssr: {performance: 80}   # overrides performance for dynamic_seo and saas
    axe_max: {critical: 0, serious: 0}
    broken_internal_links: 0
    core_web_vitals: {lcp_ms: 2500, cls: 0.1, inp_ms: 200}
```

## 2. `spec.md`

```markdown
---
site: panaderia-sol
version: 1
status: draft            # draft | approved
approved_at: null
type: static
stack: astro
provider: cloudflare
---
## Goal
One or two lines.
## Audience and main action
## Pages
| Path | Purpose | Content source | Languages |
## Content sources
What the user provides; what is drafted and marked "draft, needs the user's ok".
## Design
`DESIGN.md` here, or the marketing brand slug; references with URL and date.
## Integrations
## Stack, in plain words
Three lines, no jargon.
## Hosting and monthly cost
## Milestones
| # | Scope | Acceptance criteria |
Each criterion is testable: page, action, expected result.
## Out of scope
## Open questions (at most 5)
## Changes
- v2 · 2026-10-12 · "add a gallery" -> M4
```

## 3. `milestones/<ID>.md`

```markdown
---
id: panaderia-sol-20261005-build-01
site: panaderia-sol
kind: build              # build | change | bug
milestone: M1
branch: web/panaderia-sol-20261005-build-01
base: main
status: building         # planned | building | built | previewed | in_review | approved | published
round: 0
commit: null
pr_url: null
preview_url: null
updated: 2026-10-05T10:12-05:00
---
## Scope
## Acceptance criteria (copied from spec.md)
## Done
## Tests run
Command and result, pass/fail counts.
## Assumptions
## Advisor
Question, advice, decision and why.
## Env vars and bindings
Names only. Secrets the user must provide.
## Migrations
File, destructive yes/no, what it changes.
## History
- 2026-10-05 10:12 · building (web-frontend)
```

Every stage appends one History line; the building bot is the only one that edits the other sections after `built`.

## 4. `reviews/<ID>-r<R>.json`

```json
{
  "id": "panaderia-sol-20261005-build-01",
  "round": 0,
  "url": "https://<preview-url>",
  "verdict": "APPROVED",
  "lenses": {
    "acceptance": {"ok": true, "critical": [], "notes": []},
    "visual": {"ok": true, "critical": [], "notes": ["menu images: alt text could name the dish"]},
    "wcag22": {"ok": true, "critical": [], "notes": []},
    "core_web_vitals": {"ok": true, "critical": [], "notes": []},
    "security_seo": {"ok": true, "critical": [], "notes": []}
  },
  "checks": "reviews/panaderia-sol-20261005-build-01-r0/checks.json",
  "critical": [],
  "summary": ["Home with hours and map", "Menu in Spanish and English", "Mobile load 1.2 s"]
}
```

`verdict`: `APPROVED`, `FIX` or `ESCALATE`. A critical finding is an unmet acceptance criterion, an axe `critical` or `serious` result, a score under `thresholds`, a broken internal link, a leaked secret, a missing security header, or invented content presented as fact. `summary` is three plain-language lines for the lead to reuse.

## 5. `deploys/<ID>-<env>-<n>.json`

```json
{
  "id": "panaderia-sol-20261005-build-01",
  "site": "panaderia-sol",
  "env": "preview",
  "provider": "cloudflare",
  "branch": "web/panaderia-sol-20261005-build-01",
  "commit": "3f2a9c1",
  "pr_url": "https://github.com/<owner>/panaderia-sol/pull/1",
  "version_id": "<provider version id>",
  "url": "https://<preview-url>",
  "previous_version_id": null,
  "confirmed": null,
  "ok": true,
  "smoke": {"status": 200, "checks": "reviews/.../smoke.json"},
  "notes": []
}
```

In production, `confirmed` holds the user's literal answer with its timestamp, and `previous_version_id` is the rollback target. Both are required before the deploy.
