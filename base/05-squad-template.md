# Template for designing a squad

> Base prompt. Use it to write the plan for **any** new squad (jobs, finance, studying, health, content…).
> Every squad plan in `squads/<key>/` must have these files and sections. That way any AI can install and personalize it the same way.

## Required files

```text
squads/<key>/
├── README.md                    # purpose, levels, bots, flows (one-page summary)
├── 01-personalization.md        # squad questionnaire + resulting profile
├── 02-architecture.md           # bots, flows, folders, data contracts, AGENTS.md
├── 03-bots.md                   # SOUL of each bot + skills + orchestration skill
├── 04-installation.md           # master prompt for Hermes to install it
├── 05-scripts.md                # script specifications (the installer AI writes them)
├── 06-testing-and-operations.md # acceptance tests, operations, metrics, moving up a level
└── reference/                   # optional: third-party material used as a source (with licenses)
```

**Squad key.** Each squad has one short lowercase English word (`jobs`, `marketing`) that is reused everywhere: plan folder `squads/<key>/`, folder on the user's computer `projects/<key>/`, profiles `<key>-<role>`, orchestration skill `orchestration-<key>` and profile file `<key>-profile.yaml`. The rest of the naming rules are in `CONTRIBUTING.md` ("Naming conventions").

## Design checklist

### README
- [ ] Purpose in 2 lines: what concrete result the user gets.
- [ ] Level ladder: Level 1 works end to end, automatically, with the minimum; each next level says what it adds and which metric justifies it.
- [ ] Table of bots with each one's **reason to exist** (independence, permissions, model or context; see `01-principles.md` §1.3). At most 5 specialists.

### Personalization
- [ ] Only questions specific to the squad. The general ones (name, country, languages, channel) are already in `user/profile.md`: read them, don't ask again.
- [ ] Required questions kept separate from optional ones.
- [ ] For each answer, what changes in the system ("answer → effect" table). If a question changes nothing, delete it.
- [ ] A `<squad>-profile.yaml` file with all the variables the bots use.
- [ ] A complete example of a filled-in profile.

### Architecture
- [ ] The `{{ROOT}}/projects/<squad>/` folder with its tree.
- [ ] Output contract for each bot (file and required fields).
- [ ] Automatic chain: who triggers it, who hands off to whom and under what condition, what reaches the user.
- [ ] On-demand flows and user replies, with the points where their confirmation is needed.
- [ ] What is a script and what is a bot.
- [ ] The squad's `AGENTS.md` (its own rules, without repeating the base ones).
- [ ] Tools: the best on the market for the task, justified in `00-evaluation/`, installable on Mac, Windows and Linux, and lightweight. No Docker or always-on services, and heavy jobs use the shared lock (`01-principles.md` §1.8).

### Bots
- [ ] Each bot's SOUL built with the template below, using variables from the profile.
- [ ] Minimal toolsets, and the ones they must not have listed in `agent.disabled_toolsets`. Model: the user's main model; another one only if a capability is needed that it lacks and that no Hermes auxiliary model covers (vision is covered by `auxiliary.vision`).
- [ ] An `orchestration-<squad>` skill that follows the contract in `04-orchestrator.md` §5.

### Installation
- [ ] Step 0: personalization (questionnaire). Nothing is created before it.
- [ ] Verifiable steps, each with its command and expected output.
- [ ] Updates `orchestrator/registry.md` and the orchestrator's `skills.external_dirs`.
- [ ] Creates the automations (cron) and the delivery script; tests that a message reaches the user's channel.
- [ ] End-to-end test at the end.

### Testing and operations
- [ ] Acceptance tests with input and expected result.
- [ ] Weekly metrics and the threshold for moving up a level.

## SOUL.md template for a specialist

At most 25 lines. The `{{...}}` variables are replaced with the profile data during installation.

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

Never: {{3 to 5 specific prohibitions}}.
When in doubt between pleasing and being accurate, be accurate.
Quality criterion: {{what a good result looks like, in 2 lines}}.
Handoff: {{if your result justifies it, create the task for <next bot> with kanban_create,
with workspace, idempotency-key and a complete body; if not, create nothing}}.
Always finish with kanban_complete (with the file path in artifacts) or kanban_block,
explaining exactly what is missing.
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
