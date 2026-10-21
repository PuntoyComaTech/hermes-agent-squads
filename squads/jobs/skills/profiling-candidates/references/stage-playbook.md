# Stage playbook

What each career stage leads with, how gaps are handled, and the neutral wording used in every document. Set
`candidate.stage` once and revisit it when the user changes goals.

## Contents

- Stages at a glance
- Gap handling
- Age-neutral wording
- Stage per message

## Stages at a glance

| Stage | CV leads with | Strongest evidence | Watch for |
|---|---|---|---|
| first_job | education, projects, coursework, part-time work | projects with a measured result | a long list of tools with no outcome |
| junior | recent projects and one employer | results of the first role | responsibilities written as a job description |
| mid | the last two roles, the results | metrics per role, ownership | a career history with no pattern |
| senior | scope: team, budget, systems, decisions | outcomes across teams | detail on early roles |
| lead | people and direction, then delivery | hiring, growth, delivery across teams | individual tasks only |
| career_change | the transferable skills, then the new field | a project in the new field | a list of unrelated titles without a bridge |
| returning | the last role, then the reason for the gap in one line | recent learning, certificates | an unexplained gap |

## Gap handling

- A missing required skill is named as a gap. It is never covered by a loose synonym.
- A transferable skill is shown with the situation it came from, in the user's words.
- A gap in a language level is flagged, not hidden: state the declared level; do not raise it.
- A career gap is given one neutral line of fact (study, caring work, a project, a break); the user chooses the words.
- A long history of short roles is described by what was delivered in each, not by the number of roles.

## Age-neutral wording

- Use years of experience, not dates of birth. Show the first and last year of a role only.
- Do not state an age, a generation or a graduation year older than the user's own choice.
- Use present-day tools and results. Drop early-career details that no longer support the goal, when the user agrees.
- Keep the writing direct and about results, which does not depend on age.
- Age appears in a CV only when `candidate.include_age_in_cv` is true and the user chose to show it.

## Stage per message

When the stage is unclear, ask one question with options: "first job, junior, mid, senior, lead, career change, or
returning after a break?" Do not guess from the job title alone.
