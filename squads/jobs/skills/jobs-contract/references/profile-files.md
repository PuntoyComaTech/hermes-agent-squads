# Profile files

Written by the manager (skill profiling-candidates), in the project folder `<P>`. One project per person.

## Contents

- profile.md: search keys, personalisation keys and consent
- Years of experience
- achievements.yaml, contact.yaml and application-data.yaml
- Check the files: validate_profile.py

## profile.md: search keys

YAML front matter (read by every bot and by the cron gates), then free notes.

```yaml
---
updated: 2026-09-25
search: active                      # active | paused; the cron gates read it: write it unquoted
user_language: es                   # ISO 639-1: the language of every message to the user
timezone: America/Lima              # IANA zone: the search slot and "today" use it
occupation: "Data analyst, business reporting and automation"
target_roles: ["Data analyst", "BI analyst"]       # by preference
acceptable_roles: ["Operations analyst, data focus"]
seniority: mid-level
years_experience: {total: 4, in_role: 3}   # informational: the gates compute years from the dates
seniority_margin: 1                 # a shortfall up to this many years is a soft note; more fails the gate
seniority_basis: total              # total: years of the profession for every requirement | role: lead years count only lead titles
reject_on_skill_gaps: false         # true: a skill, tool or method the profile does not prove rejects the opening
reject_on_missing_credentials: false  # true: a degree, licence or certification the profile lacks rejects it
plans_to_relocate: false            # true: "must reside in <country>" is a question (FLAG), not a FAIL
key_skills: [SQL, Python, Power BI]
search_keywords: {en: ["data analyst", "BI analyst"], es: ["analista de datos"]}   # the user's own terms plus approved suggestions
search_times: ["12:00"]             # weekday checks, local time; each reads postings since the previous check
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
apply_threshold: 70                 # 0-100: minimum fit score for the writer, and for an automatic submit
max_analyses_per_day: 5
max_company_searches: 12            # page reads allowed for one company profile
analyze_flagged: true
auto_apply: try                     # never | ask | try | auto: see "Consent to submit"
apply_consent: per_opening          # per_opening (try, ask) | standing (auto)
auto_apply_since: 2026-10-01        # the day the user agreed to auto; required with auto
daily_apply_cap: 10                 # auto: submissions a day, every method
daily_easy_apply_cap: 5             # auto: LinkedIn Easy Apply submissions a day; easy_apply_gap_minutes: 1 between two
review_before_submit: false         # true: the user checks the screenshot before any submit (ask)
linkedin_browse: true               # the scout may read LinkedIn posts and the applier may use Easy Apply
confidential_search: false
confidential_terms: []              # never in any outward text; keep_off_public_profile: CV yes, LinkedIn no
```

## profile.md: personalisation keys

Same front matter. Every key is optional; a missing key takes the default shown.

```yaml
candidate:
  stage: mid                        # first_job | junior | mid | senior | lead | career_change | returning
  situation: employed               # employed | unemployed | student | freelance
  age: null                         # only when the user offers it; never inferred
  include_age_in_cv: false
  photo_in_cv: false
market:
  country: "PE"                     # ISO-3166 alpha-2 of the target market, quoted
  cv_page_limit: 2                  # 1 | 2
  conventions: {photo: false, age: false, marital_status: false, references_line: false}
eligibility:                        # one row per country applied in
  - {country: "PE", status: citizen}  # citizen | resident | permit | needs_sponsorship
  - {country: "US", status: needs_sponsorship, notes: ""}   # quote every code: unquoted NO reads as false
languages_policy: {flag_gap_steps: 1, discard_gap_steps: 2}   # CEFR steps above the declared level
scoring:
  weights: {technical: 30, experience: 25, behavioral: 15, career: 30}   # sum 100; location is pass/fail
  bands: {strong: 75, good: 60, moderate: 45, weak: 30}
deal_breakers: ["on-call weekends"] # duties or conditions the user refuses; never a work mode
career_goals: []
energizers: []                      # tasks that energise
drains: []                          # tasks that drain
behavioral: {thrives_in: [], avoid: [], work_style: ""}
writing_style: {tone: warm_direct, formality: medium, avoid_phrases: []}
cv_template: classic                # classic | compact | modern | a registered <P>/templates name
salary_data: null                   # path, relative to <P>, of the user's own benchmark file
follow_up_days: 10                  # quiet days before a follow-up draft
stale_days: 60
---
```

Language levels live in `achievements.yaml -> languages`. A required language not declared there is a DISCARD; a gap of `discard_gap_steps` CEFR steps or more is a DISCARD; a gap of `flag_gap_steps` or more is a FLAG; an unknown required level is a FLAG; at or below the declared level is a PASS.

Required for a search: occupation, target_roles, seniority, years_experience, work_mode, search_keywords, and at least one language in `achievements.yaml`. Missing optional keys mean no constraint.

## Consent to submit

Four values, in plain words:

- `auto_apply: never`: the squad never submits. The applier writes a manual kit (`kit.md`) with the link.
- `auto_apply: ask`: the applier fills the form and stops before the submit, with a screenshot. The user approves it in
  chat; only then it submits. Requires `review_before_submit: true`.
- `auto_apply: try`: the applier submits once, for simple forms, after the user's `apply` for that opening. Any other
  form gets the kit.
- `auto_apply: auto`: the user said yes once. The applier submits on its own, every day, with no per-opening apply:
  only an APPROVED review, a PURSUE analysis with no gate FAIL and `fit.score` at or above `apply_threshold`, an employer ATS link
  (or a LinkedIn `/jobs/view` page for Easy Apply) and room under `daily_apply_cap` (default 10) and
  `daily_easy_apply_cap` (default 5). Needs `apply_consent: standing`, `auto_apply_since` (the day the user said yes)
  and `review_before_submit: false`; it never submits a form that asks for payment, a paid test or data the files lack.

`apply_consent` follows the mode: `per_opening` for try and ask (each submit needs its own `consent.json`), `standing`
for auto (profile.md is the consent). A cap reached means the opening waits for tomorrow, never a kit.

## Years of experience

Gates compute years from the dated `experiences` in `achievements.yaml` (overlaps counted once); `years_experience` is
used only when no experience has dates. With `seniority_basis: total` every "N years" requirement compares with the
total; with `role`, "N years as <role>" compares with matching titles (validate_profile.py checks).

## achievements.yaml

The only source of claims (jobs-contract -> Pitfalls). Store text in every language the user applies in; the user confirms each.

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
    evidence: documents/projects/report-before-after.png
    tags: [automation, python]
    source: "documents/cv/cv-2026.pdf"   # a document path or "interview"
    verified: true                # true only after the user confirms this exact text
skills:
  - {name: SQL, proficiency: did, years: 4, achievements: [ACH-007]}
education:
  - {id: EDU-001, degree: "Industrial Engineering", institution: "Example U", year: 2021, verified: true}
certifications:
  - {id: CERT-001, name: "Data Analysis Certificate", issuer: "Example Academy", year: 2024, verified: true}
languages:
  - {language: spanish, level: C2, verified: true}
  - {language: english, level: B2, verified: true}
public_evidence:
  - {id: PIECE-003, url: "https://github.com/example/repo", type: repository, achievements: [ACH-007]}
star_stories:                     # interview stories; drafted with the user, never invented
  - {id: STAR-001, achievements: [ACH-007], situation: "", task: "", action: "", result: "", verified: false}
```

## contact.yaml

Sensitive; keep it out of git. Readers: jobs-contract step 2.

```yaml
name: "Ana Example"                # short_name (optional) sets the CV file name: CV_Ana_Example.pdf
email: "ana@example.com"
phone: "+51 900 000 000"
location: "Lima, Peru"
links: ["https://github.com/example"]
```

## application-data.yaml

Only when `auto_apply` is `try`, `ask` or `auto`. Sensitive; keep it out of git. Every country in `eligibility` needs a row in `work_authorization`.
```yaml
work_authorization:
  - {country: PE, authorized: true, needs_sponsorship: false}
salary_expectation: [{currency: PEN, amount: 7000, period: month}]   # floors; form_answer.py types the answers:
salary_answer: {amount: 7500, currency: PEN, period: month}         # typed when a posting gives no range
start_availability: "2 weeks"                                       # notice_period_days: 14 overrides it in a dropdown
willing_to_relocate: false
voluntary_questions: "prefer not to answer"
authorize_consents: true            # tick the data-processing boxes a form requires
saved_answers: []                   # {question, answer}; added only with the user's OK
```

## Check the files: validate_profile.py

Run it after the writes and before telling the user the files are saved:

```bash
python3 -I "$HERMES_HOME/skills/squad-jobs/jobs-contract/scripts/validate_profile.py" --project <P> --json
```

Exit 0: no findings. Exit 1: each finding names its file, key and message; fix every one, asking the user for any fact. Exit 2: usage error. The script only reads, and it never prints contact values.

It checks: required keys; enum values (`search`, `auto_apply`, `apply_consent`, `candidate.stage`, `work_mode`,
`proficiency`, CEFR levels); `apply_consent` matching the mode and `auto_apply_since` dated with `auto`; the daily caps
whole numbers; `review_before_submit` true for `ask` and false for `auto`; `scoring.weights` sums to 100; quoted country
codes; `user_language` (ISO 639-1); `timezone` (IANA); work-mode words in `deal_breakers`; ids referenced from
achievements exist; dates parse and end after they start; computed years against `years_experience`;
`application-data.yaml` covers every eligibility country.
