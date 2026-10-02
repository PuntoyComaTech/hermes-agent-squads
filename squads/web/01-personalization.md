# Personalization: web development squad

> Two moments:
> - **Squad profile**: once, in step 1 of the installation. Produces `{{ROOT}}/projects/web/web-profile.yaml`.
> - **Site onboarding**: every time the user starts a site, during the installation or later by chat. Produces `sites/<slug>/settings.yaml`; the architect then writes `spec.md`.
>
> Do not repeat what `user/profile.md` already has (name, country, timezone, languages, channel, schedule, tone, autonomy, `main_model`).

## Part 1 · How to run the interview

1. Read `user/profile.md` and `web-profile.yaml` if it exists. Show a draft with what you infer; mark unconfirmed values with `(?)`.
2. At most 5 questions per round, with options. Required first.
3. **No technical questions to a non-technical user.** Ask about their business, their visitors and what they want the site to do. Stack, provider, languages of code, database: decided with defaults and explained in one line.
4. Vague answer ("something modern"): ask for a concrete example ("Send me one or two sites you like").
5. Never a silent default: propose a value, say its effect in one line, confirm.
6. Show the final YAML in plain words (not the raw file for `technical_level: none`) and wait for "ok".

## Part 2 · Squad profile

### Required

| Field | Question | Why it matters |
| --- | --- | --- |
| `works_for` | Who are the sites for? my own business · clients · the company I work for · several | With `clients`, each site's messages include a text to forward and data never crosses sites |
| `technical_level` | How comfortable are you with tech? I don't program · I get by · I'm a developer | How much the bots explain; default for each site |
| `github_account` | Do you have a GitHub account? yes (username) · no | With no: the builder guides creating one (free); the user creates it |
| `cloudflare_account` | Do you have a Cloudflare account? yes · no | With no: guided creation (free). Needed before the first preview |
| `default_provider` | Do you already host sites on Vercel? no (Cloudflare, recommended) · yes, keep Vercel | `deploy-cloudflare` or `deploy-vercel` pinned by default |
| `initial_sites` | Which site do you want first? One line about it | Onboarded at the end of the installation |
| `notify_window` | When can the squad message you? (suggestion: the schedule in your profile) | When `deliver.py` sends |

### Technical (the builder detects them; ask only what it cannot see)

| Field | How it is decided | Effect |
| --- | --- | --- |
| `github_owner` | The user's username, or an organization if they have one | Owner of every site repo |
| `repo_mode` | Installation step 7a: web-deployer checks with `gh` what the token can do, then the builder explains both options in plain words and the user picks one. No default | `bot_creates`: the token sees all repositories and has Administration write, so the deployer creates each site's repo. `user_creates`: the user creates each empty private repo and adds it to the token, which sees nothing else |
| `cloudflare_plan` | "Do you pay Cloudflare Workers Paid (USD 5/month)?" Default `free` | Whether SSR sites need a plan warning before production |
| `machine` | OS, RAM, free disk | `max_in_progress` (2 with 8 GB) and whether Lighthouse runs on every round or only on the last |
| `topic_per_site` | Telegram or Discord: one topic or channel per site? (recommended with 2+ sites) | `destination` in each `settings.yaml` |

### Optional

| Field | Question |
| --- | --- |
| `weekly_summary` | Summary every Monday of what was built and published? |
| `quiet_until` | Hold messages until a date ("quiet until Monday") |

### Automation (suggested values)

| Field | Suggested | What it controls |
| --- | --- | --- |
| `reviewer_rounds` | 2 | FIX rounds before escalating to the user |
| `auto_advance` | true | After an approved preview, the next milestone starts on its own |
| `thresholds` | see YAML | Minimum Lighthouse and accessibility scores |

## Part 3 · What each answer changes

| Field | Effect |
| --- | --- |
| `works_for: clients` | Each site gets `approver: client`; preview messages include a forwardable paragraph |
| `technical_level` | `none`: one-line explanations, no jargon, no code in messages. `some`: names the stack and plan. `developer`: shows branch, PR and commit links, accepts technical requests literally |
| `github_account`, `cloudflare_account` | Installation step 7 guides account creation or only the token |
| `repo_mode` | What deployer REPO does at each site's onboarding: create the repo, or check the user's empty repo and, if missing, send the user the steps |
| `default_provider` | Provider skill pinned on deployer tasks; `vercel` also asks `commercial` per site (Hobby is non-commercial) |
| `cloudflare_plan` | `free` + SSR site: the architect's spec and the publish confirmation state the USD 5/month plan |
| `notify_window`, `quiet_until` | When `deliver.py` writes |
| `topic_per_site` | One topic or channel per site; `site-<slug>` skill |
| `reviewer_rounds`, `thresholds` | When the reviewer approves, fixes or escalates |
| `auto_advance` | Whether milestones chain on their own or wait for "continue" |

## Part 4 · `web-profile.yaml`

```yaml
# {{ROOT}}/projects/web/web-profile.yaml
version: 1
works_for: own_business          # own_business | clients | employer | mixed
technical_level: none            # none | some | developer
github_account: true
github_owner: "{{github_owner}}"
repo_mode: null                  # bot_creates | user_creates: the user's choice at install step 7a, no default
repo_mode_checked_at: null       # date of web-deployer's last gh check of the token
cloudflare_account: true
cloudflare_plan: free            # free | paid (Workers Paid)
default_provider: cloudflare     # cloudflare | vercel
notify_window: {days: [mon, tue, wed, thu, fri, sat], from: "08:00", to: "20:00"}
quiet_until: null
topic_per_site: true
weekly_summary: false

automation:
  reviewer_rounds: 2
  auto_advance: true
  thresholds:
    lighthouse_mobile: {performance: 90, accessibility: 95, best_practices: 90, seo: 95}
    lighthouse_mobile_ssr: {performance: 80}   # overrides performance for dynamic_seo and saas
    axe_max: {critical: 0, serious: 0}
    broken_internal_links: 0

technical:
  max_in_progress: 3             # 2 with 8 GB of RAM
level: 1
```

## Part 5 · Site onboarding

The orchestrator runs it (`orchestration-web`, "New site"). It asks only what the user can answer; the architect researches the rest.

### Required

| # | Question (plain language) | Field or file | Effect |
| --- | --- | --- | --- |
| 1 | What is the site for? Tell me in one or two lines | `spec.md` Goal; `type` | The architect maps it to `static`, `dynamic_seo` or `saas` |
| 2 | Who will visit it, and what should they do there? | `spec.md` Audience | Pages, calls to action, tone |
| 3 | Which pages do you imagine? (or "you propose") | `spec.md` Pages | Milestones |
| 4 | Where does the content come from? I write it · you draft it from my info · an existing site or document | `spec.md` Content sources | What the developer uses; drafted copy is marked for the user's approval |
| 5 | In which languages? | `languages` | i18n routes and content |
| 6 | Do you have a look already? my marketing brand · a logo and colors · sites I like · you propose | `design` | `source: marketing` reads that brand's `DESIGN.md` read-only; otherwise the architect writes the site's own `DESIGN.md` |
| 7 | Does the site sell, take bookings, collect forms or have user accounts? | `integrations`; may change `type` | Forms in Level 1; accounts and payments are Level 2 |
| 8 | Do you have a domain? yes (which, bought where) · I will buy one · not yet | `domain` | `workers.dev` address until then; DOMAIN flow when ready |
| 9 | Is it for a business (earns money)? | `commercial` | Blocks Vercel Hobby for commercial sites |

### Only if applicable

| Question | When |
| --- | --- |
| Is there a current site we replace? Its address | Existing site: the architect inventories its pages and redirects |
| Any legal page you must show? (privacy, cookies, terms) | Forms, analytics or sales |
| A date it must be live by | The user mentions a launch |

### Procedure

1. Name and slug (lowercase, no accents); minimal `settings.yaml` with `active: false` and `live.port`, the lowest port from 4321 up not used by another site.
2. Deployer REPO task for the site (`02-architecture.md` §8, GitHub access). With `repo_mode: user_creates` and no reachable empty repo, the deployer blocks with `needs_input` and click-by-click steps (create an empty private repo named `<slug>`, add it to the token's repository access); `deliver.py` sends them and the user replies "done".
3. Questions above, at most 5 per round. Files the user sends go to `sites/<slug>/inputs/`.
4. Architect SPEC task. The spec arrives with open questions (at most 5).
5. Answers go into `spec.md`; with the user's "ok" on spec and stack, `active: true`, `spec.md` status `approved`, and the first milestone starts.

The builder writes this Part as `skills/orchestration/references/onboarding.md` (it is not bundled).

## Part 6 · `sites/<slug>/settings.yaml`

```yaml
name: "Panadería Sol"
slug: panaderia-sol
emoji: "🥐"
active: false                    # true after the user approves the spec
approver: self                   # self | client
type: static                     # static | dynamic_seo | saas
stack: astro                     # astro | nextjs | tanstack
provider: cloudflare             # cloudflare | vercel
plan_required: free              # free | workers_paid (set by the architect)
commercial: true
technical_level: none            # overrides web-profile.yaml for this site
languages: [es, en]
design:
  source: own                    # own (sites/<slug>/DESIGN.md) | marketing
  brand: null                    # marketing brand slug when source is marketing
integrations: [contact_form]     # contact_form | newsletter | booking | cms | analytics | auth | payments
domain:
  name: null                     # e.g. panaderiasol.example
  status: none                   # none | pending_user | pending_dns | active
repo:
  owner: "{{github_owner}}"
  name: panaderia-sol
  visibility: private
  created: false                 # true once deployer REPO created or verified it
cloudflare:
  worker_name: panaderia-sol
  profile: null                  # named cf login for a client's own account (D-034); null = deployer's .env token
  preview_url: null              # filled by the deployer
production:
  url: null
  version_id: null
  deployed_at: null
destination: topic               # topic | channel | main
live:                            # how the user watches a BUILD (D-035)
  port: 4321                     # unique per site, assigned at onboarding: 4321, 4322, ...
  watch: live                    # live (Desktop or console: localhost) | screenshots (messaging); set by the orchestrator
```

## Part 7 · Example (fictional)

**Lucía Paz**, owner of Panadería Sol, a bakery in Valencia. Does not program. Has GitHub (`lucia-paz-demo`) and created a Cloudflare account during the installation. Wants a page with the menu, hours and a contact form, in Spanish and English. Uses the marketing squad for social media but wants the site's own look. No domain yet.

Result: `works_for: own_business`, `technical_level: none`, `default_provider: cloudflare`, `cloudflare_plan: free`, `repo_mode: user_creates` (she prefers the key to see only her site's repo). Site: `type: static`, `stack: astro`, `plan_required: free`, `integrations: [contact_form]`, `domain.status: none`. The architect proposes 3 milestones: M1 home and menu, M2 contact form and legal pages, M3 English version. Monthly cost: USD 0 until she buys a domain.

### Other cases (what changes)

| Case | Change |
| --- | --- |
| Online shop with 300 products, SEO matters | `type: dynamic_seo`, `stack: nextjs`, `plan_required: workers_paid`; payments deferred to Level 2 |
| Booking app for a gym with a members area | `type: saas`, `stack: tanstack`; accounts need Level 2 (auth) |
| Freelancer building sites for clients | `works_for: clients`; one repo per client site in the user's GitHub; `approver: client` |
| Already on Vercel, personal portfolio | `provider: vercel`, `commercial: false` |
| Developer user | `technical_level: developer`: messages include PR links and commit hashes |
