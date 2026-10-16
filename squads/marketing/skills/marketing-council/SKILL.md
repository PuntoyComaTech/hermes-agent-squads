---
name: marketing-council
description: "Runs a simulated council of documented marketers. Use when a big decision benefits from conflicting lenses, a disagreement map and a chaired recommendation."
---

# Marketing council

A simulated board: each seat applies one marketer's documented frameworks and positions to the brand's question, per the Grounding rules.

## When to Use

- A decision with real stakes needs conflicting lenses: positioning, offer, pricing, a channel shift, a launch.
- The user asks "what would <advisor> say", "get multiple perspectives" or "run it by the council".
- A plan or report has two defensible directions and the manager must argue both before recommending.

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

1. Read `brand.md`.
2. Restate the question and the stakes in two lines. Pick the mode: quick take (one advisor), session (three to five, the default) or full council (all twelve, for decisions that change the plan).
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

   Seat any advisor the user names. Seat at least one dissenter whose documented position conflicts with where the question leans. A custom advisor is written from [advisor-template.md](references/advisor-template.md) into the brand's `research/council/` and is seated like the built-ins.
4. Load only the seated advisors' dossiers. Research when the question is recent or the user wants citations: primary sources (books, essays, interviews, talks) over roundups. A finding that contradicts a dossier wins; note `dossier corrected: <source>` in the output.
5. Each take, 2-4 paragraphs: apply the advisor's signature questions and frameworks to the brand's specifics, in the strongest version of their view.
6. Disagreement map: two to four genuine conflicts; for each, the underlying trade-off and what evidence would settle it.
7. Synthesis: the recommendation for this brand's stage and constraints, the tripwire to watch, and the skill handoffs. Write the session to `research/<YYYY-MM-DD>-council-<topic>.md`.

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

- Five takes that agree with the current plan: re-seat with a dissenter.
- Quote soup: famous one-liners instead of the method behind them.
- A council for execution work or a single headline: use a quick take or none.
- Presenting the simulation as if the real people reviewed the brand.

## Verification

- Every take cites its dossier source or research source; nothing quotes an unverifiable line.
- The disagreement map contains real conflicts, each with the evidence that would settle it.
- The synthesis names the seat it follows and the tripwire it keeps watching.
- The output is labeled simulation and proposes only moves the brand can execute.
