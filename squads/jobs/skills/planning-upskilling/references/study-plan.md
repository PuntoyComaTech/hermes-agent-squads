# Study plan rules

How the heatmap is ranked, how the plan entries read and how the study order is set. All counts come from
`skill_gaps.py`; the numbers in this file are thresholds, not findings.

## Contents

- Priority rules
- Plan entry format
- Study order rules
- Report layout and diff
- Worked example

## Priority rules

Let `N` be the number of analysed openings in the project (`openings_analysed`) and `M` the must-have count of a skill.

| Priority | Rule |
|---|---|
| Critical | M is at least half of N, or M is at least 3 |
| High | M is 1 or 2 (below the Critical rule), or a tool count of 2 or more |
| Medium | Nice-to-have only, in 2 or more openings |
| Low | one mention anywhere |

Within a priority, keep the script order (must-have first, then nice-to-have, then openings).

## Plan entry format

```text
### <Skill> [Type] - about 20 hours (estimate)
Start from: <skill the user already has, from achievements.yaml, if any>
Direction: <what to skip and where to start>
Search: "<skill> hands-on course <current year>"
```

Type is one of: hard (a named tool or technique), domain (the sector's context), soft (a way of working), credential
(a certificate a posting names). A `credential` entry names only the certificate the posting itself asks for.

## Study order rules

1. Dependencies first. If skill B needs skill A, A comes first and the entry says so.
2. Within a dependency tier: Critical, then High, then Medium.
3. A quick win (five hours or less) may move earlier when it unblocks an application.
4. Domain and soft skills run alongside a project, placed after the hard skills they support.

Give the total as a range when any entry is an estimate.

## Report layout and diff

```text
# Upskill report - YYYY-MM-DD
Mode: aggregate (N openings analysed) | targeted: <ID>

## Since last report (only when an earlier report exists)
Gaps closed: ...
New gaps: ...

## Gap heatmap
| Priority | Skill | Must | Nice | Tools | Keywords | Openings |

## Learning plan
(entries grouped by theme)

## Study order
| # | Topic | Type | Est. time | Note |

Total estimated time: about Nh
```

Gaps closed: a skill named in the earlier report's heatmap that is now in `achievements.yaml`. New gaps: a skill in
this heatmap that the earlier report did not list.

## Worked example

Fictional candidate Ana Example, four analysed openings, all with the same stack. The diff gives "Power BI" with
must-have 3 and tools 2; "dbt" with nice-to-have 2; "ETL" with keywords 4.

- Power BI: must-have 3 of 4 openings, so Critical.
- dbt: nice-to-have in 2 openings, so Medium.
- ETL: keywords only, in 4 openings: Medium by the openings count, shown with its keyword count so the user sees why.
- Study order: ETL concepts first (dependency of dbt), Power BI alongside a project, dbt last.
