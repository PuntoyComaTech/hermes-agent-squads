---
name: marketing-council
description: "Runs a simulated council of documented marketers. Use when a big decision benefits from conflicting lenses, a disagreement map and a chaired recommendation."
---

# Marketing council

A simulated board of marketing advisors: each seat applies the documented frameworks and positions of a well-known marketer to the brand's specific question. Every take is grounded in what the advisor actually wrote (see Grounding rules) and labeled as simulation.

## When to Use

- A decision with real stakes needs conflicting lenses: positioning, offer, pricing, a channel shift, a launch.
- The user asks "what would <advisor> say", "get multiple perspectives" or "run it by the council".
- A plan or report has two defensible directions and the lead must argue both before recommending.
- Not for execution work: the council decides direction, then the normal chain produces.

## The Bench

| Advisor | Lens |
| --- | --- |
| Seth Godin | Remarkability, permission, smallest viable audience |
| David Ogilvy | Research-driven brand advertising with direct-response discipline |
| Eugene Schwartz | Channel existing mass desire; awareness and sophistication stages |
| Claude Hopkins | Scientific advertising, test everything, reason-why copy |
| Gary Halbert | The starving crowd, market and list before product and copy |
| Russell Brunson | Funnels, value ladders, hook-story-offer |
| Alex Hormozi | Offer construction and the value equation; volume and leverage |
| April Dunford | Positioning against real competitive alternatives |
| Rory Sutherland | Behavioral science; the opposite of a good idea can also be good |
| Byron Sharp | Mental and physical availability; reach over loyalty |
| Ann Handley | Content and writing craft; slower, braver marketing |
| Gary Vaynerchuk | Attention arbitrage; be native to underpriced channels at volume |

Dossiers: [godin](references/seth-godin.md), [ogilvy](references/david-ogilvy.md), [schwartz](references/eugene-schwartz.md), [hopkins](references/claude-hopkins.md), [halbert](references/gary-halbert.md), [brunson](references/russell-brunson.md), [hormozi](references/alex-hormozi.md), [dunford](references/april-dunford.md), [sutherland](references/rory-sutherland.md), [sharp](references/byron-sharp.md), [handley](references/ann-handley.md), [vaynerchuk](references/gary-vaynerchuk.md).

## Procedure

1. Read `brand.md` first; the council decides for this brand, not in general.
2. Restate the question and the stakes in two lines. Quick take: one advisor. Council session (default): three to five. Full council: all twelve, only for major decisions.
3. Seat by question type:

| Question type | Seats |
| --- | --- |
| positioning | dunford, godin, schwartz |
| offers | hormozi, halbert, brunson |
| brand | sharp, ogilvy, sutherland |
| copy | ogilvy, schwartz, halbert, handley |
| funnels | brunson, hormozi, hopkins |
| content | handley, godin, vaynerchuk |
| paid | hopkins, sharp, vaynerchuk |
| growth | hormozi, vaynerchuk, sharp |
| channels | vaynerchuk, sharp, halbert |
| launch | brunson, godin, halbert |

   Honor explicit requests, and always seat at least one designated dissenter whose documented position conflicts with where the question leans. A custom advisor is written from `references/advisor-template.md` into the brand's `research/council/` and seats like the built-ins.
4. Load only the seated advisors' dossiers, then research if the question is recent or the user wants citations: prefer primary sources (books, essays, interviews, talks) over roundups; a finding that contradicts a dossier wins and the dossier is corrected with one line, `dossier corrected: <source>`.
5. Each take, 2-4 paragraphs: apply the advisor's signature questions and frameworks to the specifics, no generic advice with a name attached, no strawmen, the strongest version of their view.
6. Disagreement map: two to four genuine conflicts; for each, the underlying trade-off and what evidence would settle it.
7. Synthesis: the recommendation that fits this brand's stage and constraints, the tripwire to watch, and the skill handoffs.

## Grounding rules

- Label the session as simulation once, at the top.
- Quote only what is verifiable in the dossier or the research pass, with the source named; otherwise paraphrase. No invented endorsements, and no simulating a living advisor commenting on a named competitor.
- If the dossier and the question do not overlap, say so and reason by explicit analogy.

## Output

```
> Simulated council, each take is built from the advisor's published
> frameworks and positions, not their actual review.

## The question before the council
## Seated: <advisors> (<mode>), one line on the bench and the dissenter
### <Advisor>, <lens>
<take>
**Bottom line:** <one sentence>
## Where the council disagrees
## Chair's synthesis
- Do: <2-4 concrete next steps>
- Tripwire: <warning + signal>
- Execute with: <skill handoffs>
```

## Pitfalls

- The agreeing council: five takes that bless the existing plan, re-seat with a real dissenter.
- Quote soup: famous one-liners instead of the method behind them.
- Running the council for execution work or for a headline; match the bench to the stakes.
- Presenting the simulation as if the real people reviewed the brand.

## Verification

- Every take cites its dossier source or research source; nothing quotes an unverifiable line.
- The disagreement map contains real conflicts, each with the evidence that would settle it.
- The synthesis names the seat it follows and the tripwire it keeps watching.
- The output is labeled simulation and proposes only moves the brand can execute.
