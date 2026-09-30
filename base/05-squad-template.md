# Template for designing a squad

> Base prompt. Use it to write the plan for **any** squad, official (`plans/squads/<key>/`) or the user's own (`{{ROOT}}/squads/<key>/`, created with the builder's `squad-design` skill).
> Every squad plan has these files and sections, so any AI installs and personalizes it the same way.

## Required files

```text
squads/<key>/
├── README.md                    # purpose, levels, bots, flows (one-page summary)
├── squad.yaml                   # manifest (schema below)
├── 01-personalization.md        # squad questionnaire + resulting profile
├── 02-architecture.md           # bots, flows, folders, data contracts, AGENTS.md
├── 03-bots.md                   # SOUL of each bot + skills + orchestration skill
├── 04-installation.md           # master prompt the builder follows to install it
├── 05-scripts.md                # script specifications (the builder writes them)
├── 06-testing-and-operations.md # acceptance tests, operations, metrics, moving up a level
└── reference/                   # optional: third-party material used as a source (with licenses)
```

**Squad key.** One short lowercase English word (`jobs`, `marketing`, `web`) reused everywhere: plan folder `squads/<key>/`, data folder `projects/<key>/`, profiles `<key>-<role>`, orchestration skill `orchestration-<key>`, profile file `<key>-profile.yaml`. Other naming rules: `CONTRIBUTING.md` ("Naming conventions").

## Manifest `squad.yaml`

The plan ships the template; at install time the builder writes the filled-in copy to `{{ROOT}}/projects/<key>/squad.yaml`, which `scripts/registry.py` reads (`02-architecture.md` §3.1).

```yaml
key: web
name: Web development agency
source: official            # official (plans/squads) | own (~/Hermes/squads)
plan_version: 1              # bump when the squad's contracts change
level: 1
multi_project: true
projects_dir: sites          # projects/<key>/<projects_dir>/<slug>/ ; null if single project
orchestration_skills: skills/orchestration   # relative to projects/<key>/; orchestrator skills only, never a specialist's folder
bots:
  - profile: web-architect
    does: "one line"
    modes: [SPEC, CHANGE, CONSULT]
    toolsets: [web, browser, file, skills, delegation]
    disabled_toolsets: [terminal, code_execution]
    skills_dirs: [skills/architect, skills/common]
    model: null              # plan: null + "# recommended: ..."; filled by the builder (07-builder.md §5)
    reasoning_effort: null
consult:                     # allowed direct consultations (02-architecture.md §5.1)
  - {from: web-developer, to: web-architect, about: "spec or acceptance criteria"}
crons:
  - {name: deliver, profile: orchestrator, script: deliver.py, schedule: "every 15m", no_agent: true}   # name kebab-case; script null for agent crons
asks:                        # registry column "Ask it things like..."
  - "new site: <idea>"
```

## Design checklist

### README
- [ ] Purpose in 2 lines: what concrete result the user gets.
- [ ] Level ladder: Level 1 works end to end, automatically, with the minimum; each next level says what it adds and which metric justifies it.
- [ ] Bot table with each one's **reason to exist** (`01-principles.md` §1.3). At most 5 specialists.

### Personalization
- [ ] Only squad-specific questions. The general ones are in `user/profile.md`: read them, don't ask again.
- [ ] Required questions separate from optional ones.
- [ ] An "answer → effect" table. A question that changes nothing is deleted.
- [ ] A `<key>-profile.yaml` with every variable the bots use, and a complete filled-in example.

### Architecture
- [ ] The `{{ROOT}}/projects/<key>/` tree.
- [ ] Output contract per bot (file and required fields).
- [ ] Automatic chain: trigger, who hands off to whom and under what condition, what reaches the user.
- [ ] On-demand flows and user replies, with the points needing confirmation.
- [ ] What is a script and what is a bot.
- [ ] The squad's `AGENTS.md` (its own rules, not the base ones). It lists the allowed consult pairs; the procedure itself is already in the base `AGENTS.md` (`01-principles.md` §2.3, design in `02-architecture.md` §5.1).
- [ ] Consult pairs: which bot may consult which, and about what. Listed in `consult` of `squad.yaml` and copied into the squad's `AGENTS.md`. The answering bot has a `CONSULT` mode.
- [ ] Tools: best in market, justified in `00-evaluation/`, installable on Mac, Windows and Linux, lightweight. Heavy jobs use the shared lock (`01-principles.md` §1.8).

### Multi-project squads
When the user runs several independent projects (brands, sites, clients):
- [ ] One folder per project: `projects/<key>/<projects_dir>/<slug>/`, and `multi_project: true` in `squad.yaml`.
- [ ] One Kanban tenant per project (`--tenant <slug>`), workspace inside the project folder, and one Telegram topic or Discord channel per project.
- [ ] Per-project settings file (for example `settings.yaml`) with everything that varies per project. Bots stay generic.
- [ ] Per-task skills: the task creator pins the project's stack or provider skill with `kanban_create(skills=[...])`. Those skills must already be installed on the assignee profile.

### Bots
- [ ] Each SOUL built with the template below, using profile variables.
- [ ] Minimal toolsets; the forbidden ones in `agent.disabled_toolsets`. Vision through `auxiliary.vision`, not a separate model.
- [ ] Model and reasoning effort per bot: the user's choice, asked by the builder, stored in `squad.yaml` `bots[]`.
- [ ] An `orchestration-<key>` skill following `04-orchestrator.md` §5, in `skills/orchestration/`, apart from every specialist's skills folder.

### Installation
- [ ] Step 0: personalization. Nothing is created before it.
- [ ] A models step: one table with bot, recommended model, recommended effort, the user's choice (`07-builder.md` §5).
- [ ] Verifiable steps, each with its command and expected output.
- [ ] Writes `projects/<key>/squad.yaml`, runs `scripts/registry.py`, and applies the orchestrator's `skills.external_dirs`.
- [ ] Creates the automations (cron) and the delivery script; tests that a message reaches the user's channel.
- [ ] Records the squad in `builder/installed.yaml` (`08-updates.md`).
- [ ] End-to-end test.

### Testing and operations
- [ ] Acceptance tests with input and expected result, including one consultation.
- [ ] Weekly metrics and the threshold for moving up a level.

## SOUL.md template for a specialist

At most 25 lines. `{{...}}` variables are replaced at install time.

```markdown
You are {{role in one sentence, with the level of experience you simulate}}.
You work for {{name}} within the {{squad}} squad.

Your only task: {{what you produce}}.
Input: {{files you read, with paths relative to the task folder}}.
Output: {{file}} with the fields {{required fields}}.

Guard (before working): {{condition under which you close the task without working, e.g. "if
analysis.json says REJECT, complete with 'skipped: REJECT' and finish"}}.

Procedure:
1. ...
2. ...

Missing datum: follow the consultation rule in AGENTS.md (assume if low impact; else consult
{{allowed bots}}; block for {{name}} only for human decisions).
Never: {{3 to 5 specific prohibitions}}.
When in doubt between pleasing and being accurate, be accurate.
Quality criterion: {{what a good result looks like, in 2 lines}}.
Handoff: {{if your result justifies it, create the task for <next bot> with kanban_create,
with workspace, idempotency-key and a complete body; if not, create nothing}}.
Always finish with kanban_complete (file path in artifacts) or kanban_block, saying exactly
what is missing.
```

## Skill template

```markdown
---
name: <kebab-case-name>
description: <what it does and when to use it, in one sentence>
version: 1.0.0
metadata:
  hermes:
    tags: [<Squad>, <Topic>]
    requires_toolsets: [<toolsets>]
---

# <Title>

## When to use it
## Procedure
1. ...
## Verification
How the bot knows it finished correctly.
## Common mistakes
```
