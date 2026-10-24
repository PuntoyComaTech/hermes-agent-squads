# Application form answers

Some applications ask for free text typed into a portal: a self-introduction, project entries, a short pitch under a
character limit, a motivation question, a competency question with a word cap. This file governs that text. It is
pasted into the form, never compiled.

## Contents

- The governing rule
- Field types
- Counting
- Output file
- Checklist

## The governing rule

Every claim in a form answer is supported by a verified achievement in `achievements.yaml`, or by a fact in
`profile.md`. A form is the place to select from what is already true and arrange it for the question. It is not a
place for new claims, bigger scope or filler. The interviewer reads the form next to the CV, so an answer that disagrees
with the CV is a defect.

**Related tools play for the candidate.** "Have you used GitLab CLI?" when the candidate uses GitHub and `gh`
daily is a yes: `Yes. I work daily with GitHub and its CLI (gh); GitLab and glab follow the same model.` Any tool in
the same family as a held one (`skill_families.json`) is answered yes with the held tool named. Never "not
familiar", never a refusal to answer. Only a tool with no held member in its family is answered honestly as new,
with the closest experience and how fast the candidate picks tools up.

## Field types

### Self-introduction (100 to 200 words, one paragraph, no formatting)

1. Current status: what the candidate is doing or completing now.
2. The strongest evidence, with its number and scale.
3. One line of trajectory, if a pivot or specialisation helps the reader.
4. What the candidate wants next, connected to this employer's work.

Lead with the strongest evidence, not with chronology. Write one version per role type when the history supports two
framings, and say which goes where. Tie the last sentence to the employer. State the word count, and name the sentence
to cut first, because portals truncate silently.

### Project entries

Fields: project name, role, start date, end date, description.

- Name the project by what it is ("Warehouse inventory forecasting platform"), not by the employer's name. Name a client
  only when the relationship is true (worked on-site with, delivered to).
- Role: the candidate's role on that project, which may be narrower than the job title. Never upgrade it.
- Dates: the dates on that project. Narrow them only when the candidate can say when the project started.
- Description: 100 to 150 words. What the system did and who used it; the hardest technical problem and how it was
  solved; the outcome with its number. Add a 60-word short version for portals with tighter limits.
- Contributory work says so inside the description. A project entry with the candidate's name attached reads as
  ownership of the whole project.

### Character-limited pitches

These reward a specific situation over an adjective.

1. Pick the single most distinctive true thing: a number, an unusual combination of backgrounds, or a problem shape that
   matches the employer's own work.
2. Draft four to six candidates at different angles.
3. Count characters with a script. Do not estimate. Over-limit text is cut mid-word by the portal.
4. Present all candidates with their counts, recommend one and say why. Prefer the version that maps the candidate's
   problem onto the employer's problem, where that mapping is true.

## Counting

Count with a script, not by eye. Save each field to its own temporary file, then:

    python3 -c "import sys; t=open(sys.argv[1], encoding='utf-8').read(); print(len(t), len(t.split()))" field.txt

Report characters and words for every field, against its limit.

## Output file

One file per opening: `application/answers.md`, with:

- A header naming the employer and the roles it covers.
- Each field, labelled, with its word or character count and its limit.
- A citation comment after each field: `<!-- achievements: ACH-... -->`.
- Short variants where a limit may be tighter than expected.
- `NOTE TO SELF` blocks for scope reminders and prepared answers to questions the content invites. Mark them as not
  for pasting. Never put one inside a field's text.
- A dates quick-reference, so date fields match the CV.

## Checklist

- Every factual claim traces to a verified achievement id or to `profile.md`, and the claim is cited.
- No answer contradicts the CV or the cover letter submitted for the same opening.
- Contributory work is scoped correctly.
- Counts were measured with the script above.
- An in-progress qualification is described as in progress.
- `NOTE TO SELF` blocks are marked and sit outside every field.
