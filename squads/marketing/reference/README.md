# Reference: third-party skills for the marketing agency

> Reference material, not for direct installation. These are copies of third-party marketing skills, with their references, examples, scripts and licenses.
> The installer AI uses them in step 4 of `../04-installation.md`: it reads them as a source and uses them to write the squad's own skills (`../03-bots.md` §3.1), adapted to this plan. That way each bot gets skills tailored to it instead of generic copies.

## How they are used

1. The installer AI takes each own skill from the table in `03-bots.md` §3.1 and opens the skills in this folder that are listed as its source.
2. It extracts the concrete content (lists, rubrics, templates, thresholds, questions) and rewrites it for this plan:
   - paths in each brand's folder;
   - contracts from the `piece-contract` skill;
   - each brand's language and market;
   - rules from the squad's `AGENTS.md`.
3. It leaves out whatever clashes with the plan ("Caveats" column).
4. It writes each skill with the Hermes skills tool, following the format of the bundled skill `hermes-agent-skill-authoring` (frontmatter and structure). If it wants to test and measure the skills before keeping them, it can also use `skill-creator` from `anthropics/skills`.
5. The skills that are also installed as-is in some bot (`03-bots.md` §3.2) are installed from their original source, so they get updates, and not from this copy.

The scripts and tools that some skills include (for example, the A/B test calculators in `marketing-mindset`) serve as models for the scripts in `05-scripts.md` and for the testing limits of the report and the reviewer. They are not run from here.

## Included skills

| Skill | Source · license | What it includes | What it's used for | Bot · own skill it feeds | Caveats |
| --- | --- | --- | --- | --- | --- |
| `product-marketing` | coreyhaines31/marketingskills · MIT | 12 sections of product context, with versions and a changelog; interview technique | Structure of `context.md` and `brand.md`, and the onboarding questions | Orchestrator and strategist · `brand-onboarding` | Designed for a single software product: it has no visual identity, channels, country or budget |
| `marketing-plan` | same · MIT | A 13-section plan by funnel stage, in init, review and finalize phases; 17-point rubric; budget; measurement; 11 references and a complete sample plan | The 90-day plan and the diagnosis rubric | Strategist · `plan-90-days`, `brand-onboarding`. Reviewer: verification pass | SaaS and venture capital bias: funding stages are replaced by budget tiers |
| `marketing-ideas` | same · MIT | 139 tactics in 17 categories, by stage, budget and timeframe; a guerrilla marketing guide | Idea bank for plans, calendars and ideas | Strategist · `weekly-calendar`, `plan-90-days` | Local tactics are missing: maps and reviews, WhatsApp, marketplaces |
| `marketing-loops` | same · MIT | A catalog of 45 recurring loops with a 9-part anatomy, state, spend and publishing guards, and cases that always escalate to the user | Level 3 loops | Strategist (Level 3) | Many loops assume connected data; their scheduling is designed for other agents |
| `marketing-psychology` | same · MIT | About 70 mental models and biases, with their use in marketing | The 20 compact principles and the ethics check | Creative and reviewer · `persuasion-psychology` | Some uses border on dark patterns: the reviewer vetoes them |
| `marketing-council` | same · MIT | A simulated council of 12 advisors with profiles, a disagreement map and rules against invented quotes | COUNCIL mode (optional) | Strategist · `council-mode` | Only for big decisions; never for producing pieces |
| `co-marketing` | same · MIT | Partner search and scoring, joint campaigns, an 8-point agreement | Partnerships service | Strategist | The local case is missing: cross-promotions with neighboring businesses |
| `community-marketing` | same · MIT | Community strategy, ambassadors, metrics and health alerts | Community service | Strategist | WhatsApp groups and Telegram channels are missing |
| `influencer-marketing` | same · MIT | Creators: tiers, vetting, reference rates, brief, disclosure, user-generated content program | Influencers service and the disclosure rule | Strategist. Reviewer: disclosure | Rates in dollars and a US framework: the rules of the brand's country apply |
| `marketing-mindset` | axelfreeman/marketing-mindset · MIT | An experienced marketer's judgment: 90-day horizon, testing limits, UTM, visual rule. A short variant (`SKILL.lite.md`) and one for small models (`SKILL.deepseek-flash.md`), a sample script (`scripts/first-client-gate.py`) and HTML calculators (`docs/tools/`: A/B verdict, sample size, kill rule, UTM) | The mindset rule in `AGENTS.md` and the testing limits of the report and the reviewer | Strategist (optional) and reviewer · `results-report`, `marketing-review` | It takes aggressive stances ("borderline or hacky tactics", "embellishing is allowed, but no more than 2x") that the squad's rules rein in |

`skills/skills-lock.json` records the source and hash of each copy.

## Not included here

- **The rest of coreyhaines31/marketingskills** (50 skills in total): `copywriting`, `social`, `ad-creative`, `emails`, `cro`, `analytics`, `customer-research`, `competitor-profiling`, `content-strategy`, `launch`, `offers`, `seo-audit`, `ai-seo` and others. They are installed or consulted at their source (`03-bots.md` §3.2).
- **Hermes skills:** `hyperframes`, `claude-design`, `design-md`, `humanizer`, `creative-ideation`, `social-media-content-calendar`, `competitor-news-monitor` and others. They are installed from the Skills Hub.
- **anthropics/skills:** `frontend-design`, `canvas-design`, `theme-factory` and `skill-creator`.
- **`extension-email-marketing`** (caffeinelabs/skills): discarded. It is the backend of another platform; its consent principles are already in the email rule of the `AGENTS.md`.

## Licenses

All copies keep their MIT license. The copyright notices are in [LICENSES.md](LICENSES.md) and, when the skill includes one, in its own folder.
