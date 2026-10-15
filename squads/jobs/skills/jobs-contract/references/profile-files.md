# Profile files

Written by the lead during the interview, in the project folder `<P>`: `profile.md`, `achievements.yaml`,
`contact.yaml` and `application-data.yaml`.

## Contents

- profile.md
- achievements.yaml
- contact.yaml
- application-data.yaml

## profile.md

YAML front matter (read by every bot and by `start_search.py`), then free notes.

```yaml
---
updated: 2026-09-25
search: active                      # active | paused; start_search.py reads it
occupation: "Data analyst, business reporting and automation"
target_roles: ["Data analyst", "BI analyst"]       # by preference
acceptable_roles: ["Operations analyst, data focus"]
seniority: mid-level
years_experience: {total: 4, in_role: 3}
seniority_margin: 2                 # years above in_role that only flag
key_skills: [SQL, Python, Power BI]
search_keywords: {en: ["data analyst", "BI analyst"], es: ["analista de datos"]}
search_days: 7                      # maximum age of an opening
max_required_language: {english: B2}    # CEFR, one per foreign language
application_languages: [es, en]
work_mode: [remote_region, hybrid]  # remote_global | remote_region | remote_country | hybrid | onsite
cities: [Lima]
timezone_max_diff_h: 3
contract: [employee, contractor]
min_salary: {amount: 6000, currency: PEN, period: month, type: gross}
avoid_sectors: []
avoid_companies: []
target_companies: []
evidence: {links: ["https://github.com/example"], pieces_per_application: 2}
reviewer_role: "Data Lead"          # hiring-manager lens, derived from occupation
deliverables: [cv_ats.pdf, cv.docx, cover_letter.md, answers.md]
apply_threshold: 70                 # minimum fit score for the writer
max_analyses_per_day: 5
max_company_searches: 12            # page reads allowed for one company profile
analyze_flagged: true
auto_apply: try                     # try | never
review_before_submit: false
confidential_search: false
---
```

Missing optional keys mean no constraint. Required: occupation, target_roles, seniority, years_experience, max_required_language, work_mode, search_keywords.

## achievements.yaml

The only source of claims. Nothing enters a document unless it is here with `verified: true`.

```yaml
experiences:
  - {id: EXP-001, title: "Data analyst", company: "Example Co", from: 2022-03, to: current}
achievements:
  - id: ACH-007
    experience: EXP-001
    proficiency: led              # led | did | participated | familiar
    en: "Automated the weekly sales report with Python and Power BI, from 6 hours to 20 minutes."
    es: "Automatice el reporte semanal de ventas con Python y Power BI, de 6 horas a 20 minutos."
    metric: {name: report_time, from: 360, to: 20, unit: min}
    evidence: evidence/report-before-after.png
    tags: [automation, python]
    verified: true                # true only after the user confirms this exact text
skills:
  - {name: SQL, proficiency: did, years: 4, achievements: [ACH-007]}
education:
  - {id: EDU-001, degree: "Industrial Engineering", institution: "Example U", year: 2021, verified: true}
languages:
  - {language: english, level: B2, verified: true}
public_evidence:
  - {id: PIECE-003, url: "https://github.com/example/repo", type: repository, achievements: [ACH-007]}
```

Store text in every language the user applies in; the user confirms each.

## contact.yaml

Read only by jobs-writer (CV header) and jobs-applier (forms). Sensitive; keep it out of git.

```yaml
name: "Ana Example"
email: "ana@example.com"
phone: "+51 900 000 000"
location: "Lima, Peru"
links: ["https://github.com/example"]
```

## application-data.yaml

Only when `auto_apply: try`. Read only by jobs-applier. Sensitive; keep it out of git.

```yaml
work_authorization: [{country: PE, authorized: true, needs_sponsorship: false}]
salary_expectation: [{currency: PEN, amount: 7000, period: month}]
start_availability: "2 weeks"
willing_to_relocate: false
voluntary_questions: "prefer not to answer"
authorize_consents: true            # tick the data-processing boxes a form requires
saved_answers: []                   # {question, answer}; added only with the user's OK
```
