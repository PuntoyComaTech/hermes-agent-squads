# Personalization: job search

> Runs in STEP 1 of the installation and every time the user changes their goal.
> Produces three files: `jobs-profile.yaml` (what they are looking for), `achievements.yaml` (what they can prove) and `application-data.yaml` (what to answer in forms), in `{{ROOT}}/projects/jobs/`.
> **Do not repeat** what is already in `user/profile.md` (name, country, time zone, languages, channel, autonomy): read it and use it.

## Part 1 · How to run the interview (instructions for the AI)

1. Read `user/profile.md`, your memory and the current CV if the user provides it. **Ask for the CV first**: it answers half of the questions.
2. Build a draft of `jobs-profile.yaml` with what you can infer and show it. Mark anything not confirmed with `(?)`.
3. Ask what is missing, required fields first, at most 5 questions per batch, with options when there are any.
4. When an answer is vague ("something remote", "good pay"), ask for the concrete value the filter needs.
5. Do not set default values silently. If the user does not know, propose a value, explain its effect and ask for confirmation.
6. Show the complete final YAML and ask for an "ok".

## Part 2 · Questions

### Required

| Field | Question | Why it matters |
| --- | --- | --- |
| `occupation` | What do you do? How would you describe your profession in one line? | Defines everything else |
| `target_roles` | Which positions are you looking for? Rank them by preference. Which ones would you accept even if they are not ideal? | Role filter and search keywords |
| `seniority` | What level are you aiming for? (junior, mid-level, senior, lead, management) | Seniority filter |
| `years_experience` | How many years of experience do you have in total, and in the role you are looking for? | Seniority filter and CV credibility |
| `key_skills` | What are your 5-10 strongest skills or tools? In which ones do you have real, provable experience, and which ones do you only know? | Avoids overselling |
| `max_required_language` | Based on your language levels (from the profile), what is the highest level you would accept an opening requiring? Would you feel comfortable with an interview in that language? | Hard language filter |
| `work_mode` | Which work modes do you accept? global remote · remote in your region · remote only in your country · hybrid · onsite. For hybrid and onsite, in which cities? Would you relocate? | Geographic filter |
| `timezones` | If remote, how many hours of difference from your time zone do you accept? | Geographic filter |
| `contract` | Which contract types do you accept? employee · contractor · freelance · internship | Filter |
| `min_salary` | What is your minimum acceptable pay? With currency, period (month/year) and whether it is gross or net | Filter and negotiation |
| `evidence` | How do you show your work? visual portfolio · code repositories · publications · case studies with business metrics · certifications · references · nothing formal. Share the links | Which links and pieces go with each application |
| `weekly_volume` | How many applications do you want to send per week? | Spending limit and the scout's pace |

### Optional

| Field | Question |
| --- | --- |
| `preferred_sectors` / `avoid_sectors` | Are there sectors or types of company you prefer or rule out? |
| `target_companies` / `avoid_companies` | Are there specific companies where you would like to work, or where you would not? |
| `confidential_search` | Do you currently have a job, and does the search need to be discreet? |
| `availability` | When could you start? |
| `extra_requirements` | Is there anything you absolutely need? (visa, sponsorship, provided equipment, schedule) |
| `known_sources` | Which job boards do you use, or know that work in your country and occupation? |
| `cv_template` | Do you have a CV with your own design that you want to keep for direct submissions? |
| `cover_letter` | Do you want a cover letter with every application, only when they ask for one, or never? |
| `delivery_mode` | Only the tailored CV, or also answers to typical questions and a message for the recruiter? |

### Automation and applying

| Field | Question | Proposed value |
| --- | --- | --- |
| `search_times` | At what times do you want openings to be searched? | 08:00 and 15:00 |
| `apply_threshold` | From what fit score (0-100) do you want me to prepare the CV? Higher = fewer messages, but better targeted | 70 |
| `max_deliveries_per_day` | What is the maximum number of ready openings you want to receive per day? | `weekly_volume / 5`, rounded up |
| `analyze_flagged` | Doubtful openings (for example, in English with no stated level): should I analyze them anyway or discard them? | analyze |
| `auto_apply` | When you reply "apply", do you want me to try to apply myself if the form is simple, or do you always prefer to apply yourself? | try |
| `review_before_submit` | If I apply, do you want to see a screenshot of the filled-in form before I submit it? (safer, one more step) | no |
| `weekly_summary` | Do you want a summary every Monday of how the search is going? | yes |

## Part 3 · What each answer changes

The installer AI uses this table to substitute variables in the SOULs and in the rules.

| Answer | Effect on the system |
| --- | --- |
| `occupation`, `target_roles` | Search keywords in Spanish and English (and the local language if it is a different one) · role families for the filter · **profile of the "hiring manager" reviewer** (e.g., Design Lead, Engineering Manager, Head Nurse, Construction Manager) · suitable CV template |
| `seniority`, `years_experience` | Filter rule: if the opening asks for more than `years_experience + seniority_margin` years → discard; between `+0` and `+margin` → flag. Proposed default margin: 2 |
| `max_required_language` | Hard filter rule (CEFR table in `02-architecture.md`) · level stated in the CV and in forms · warning "interview probably in <language>" when no level is stated |
| `work_mode`, `timezones`, `country` (from the base profile) | Geographic filter rule · suggested sources for that region |
| `contract`, `min_salary` | Filter rules when the opening states them; if it does not state them, it does not discard |
| `evidence` | Which links go in the CV header · whether the writer picks 3-5 pieces per opening · whether the reviewer checks links |
| `weekly_volume` | Maximum number of openings the scout returns per search, and of analyses per day |
| `confidential_search` | The scout does not use the user's name in searches; the orchestrator does not mention the current employer outside the documents |
| `cover_letter`, `delivery_mode` | Which files the writer produces |
| `cv_template` | `cv_custom.pdf` is produced in addition to `cv_ats.pdf` |
| `search_times` | Cron for `start_search.sh` |
| `apply_threshold`, `max_deliveries_per_day`, `analyze_flagged` | When the analyst passes the opening to the writer, and how many openings are prepared per day (spend control) |
| `auto_apply`, `review_before_submit` | Whether the `jobs-applier` bot exists, and whether it asks for a screenshot before submitting |
| `weekly_summary` | Orchestrator agent cron on Mondays |

## Part 4 · Achievements record (`achievements.yaml`)

It is the squad's most important asset: **nothing goes into a CV unless it is here.** It is built during installation and grows over time.

How to build it (instructions for the AI):

1. Extract from the current CV every experience, project, achievement, tool, education item and language. One achievement per entry.
2. For each achievement, ask what makes it credible: what exactly did you do? Is there a number (before/after, volume, time, money)? Is there evidence (link, screenshot, document)?
3. Mark `verified: true` **only** when the user confirms the final text. Anything unconfirmed stays `false`, and no bot uses it.
4. Distinguish proficiency levels: `led`, `did`, `participated`, `familiar`. The writer cannot raise the level.
5. If the user applies in more than one language, store the text in each language and ask them to confirm both.
6. Do it in batches (one job experience per batch). If it is long, it can be finished in another session: the system works with whatever is verified.

```yaml
# {{ROOT}}/projects/jobs/achievements.yaml
experiences:
  - id: EXP-001
    title: "Data analyst"
    company: "Example Company"
    from: 2022-03
    to: current
    work_mode: hybrid
achievements:
  - id: ACH-007
    experience: EXP-001
    proficiency: led           # led | did | participated | familiar
    es: "Automaticé el reporte semanal de ventas con Python y Power BI; pasó de 6 horas a 20 minutos."
    en: "Automated the weekly sales report with Python and Power BI, cutting it from 6 hours to 20 minutes."
    metric: {name: report_time, from: 360, to: 20, unit: "min", months: 3}
    evidence: evidence/report-before-after.png
    tags: [automation, python, power-bi]
    verified: true
skills:
  - {name: SQL, proficiency: did, years: 4, achievements: [ACH-007, ACH-009]}
education:
  - {id: EDU-001, degree: "Industrial Engineering", institution: "...", year: 2021, verified: true}
languages:
  - {language: english, level: B2, verified: true}
public_evidence:                 # portfolio, repositories, publications
  - {id: PIECE-003, url: "https://github.com/...", type: repository, year: 2024, achievements: [ACH-007]}
```

## Part 5 · Application data (`application-data.yaml`)

Only if `auto_apply` is `try`. These are the answers that almost every form asks for. The applier **only** uses what is here, in `user/contact.yaml`, in `achievements.yaml` or in the answers for each application; if a form asks for something else, it asks. Ask for each item explaining what it is for, and accept "prefer not to answer" (it is recorded as is).

```yaml
# {{ROOT}}/projects/jobs/application-data.yaml   (sensitive, in .gitignore)
work_authorization:              # per country or region where they apply
  - {country: "{{...}}", authorized: {{true|false}}, needs_sponsorship: {{true|false}}}
salary_expectation:              # what goes in forms (can differ from the minimum)
  - {currency: "{{XXX}}", amount: {{n}}, period: "{{month|year}}"}
start_availability: "{{immediate | 2 weeks | ...}}"
willing_to_relocate: {{true|false}}
how_did_you_hear: "{{job board}}"
gender_and_diversity: "{{answer or 'prefer not to answer'}}"   # forms with voluntary questions
authorize_consents: {{true|false}}   # tick the data-processing checkboxes required to apply
saved_answers: []                # the orchestrator adds here, with permission, new answers the user gave
```

## Part 6 · Resulting file: `jobs-profile.yaml`

```yaml
# {{ROOT}}/projects/jobs/jobs-profile.yaml
updated: {{date}}
squad_level: 1

occupation: "{{occupation}}"
target_roles: ["{{role 1}}", "{{role 2}}"]            # in order of preference
acceptable_roles: ["{{...}}"]
seniority: "{{seniority}}"
years_experience: {total: {{n}}, in_role: {{n}}}
seniority_margin: 2
key_skills: ["{{...}}"]

search_keywords:                                      # generated by the AI and approved by the user
  es: ["{{...}}"]
  en: ["{{...}}"]

max_required_language: {english: "{{CEFR}}"}          # one per relevant foreign language
work_mode: ["{{remote_global | remote_region | remote_country | hybrid | onsite}}"]
cities: ["{{...}}"]
would_relocate: {{true | false}}
timezone_max_diff_h: {{n}}
contract: ["{{...}}"]
min_salary: {amount: {{n}}, currency: "{{XXX}}", period: "{{month | year}}", type: "{{gross | net}}"}

evidence:
  type: ["{{portfolio | repositories | publications | case_studies | certifications}}"]
  main_links: ["{{url}}"]
  pieces_per_application: {{3-5 | 0}}

reviewer_role: "{{e.g., Design Lead / Creative Director}}"   # derived from occupation
templates: ["cv-ats"{{, "cv-custom"}}]
deliverables: ["cv_ats.pdf", "cv.docx"{{, "cover_letter.md", "answers.md", "recruiter_message.md"}}]

weekly_volume: {{n}}
max_analyses_per_day: {{n}}

# Derived values and settings (the AI proposes them, the user can change them)
application_languages: ["es"{{, "en"}}]               # languages they can apply in, based on max_required_language
text_deliverables: "{{cover_letter.md, answers.md…}}" # the deliverables that are not the CV
search_days: 7                                        # maximum age of openings when searching

# Automation
search_times: ["08:00", "15:00"]
apply_threshold: 70
max_deliveries_per_day: {{n}}
analyze_flagged: true
auto_apply: try                                       # try | never
review_before_submit: false
weekly_summary: true
max_company_searches: 5                               # the analyst's web searches per company

preferred_sectors: []
avoid_sectors: []
target_companies: []
avoid_companies: []
confidential_search: {{true | false}}
availability: "{{...}}"
extra_requirements: []

sources:                                              # the AI proposes them by country and occupation; verify
  - {name: "{{...}}", via: "{{api | web | indexed_search | manual}}", level: {{1 | 2}}}
```

## Part 7 · Full example

Data analyst in Peru, English B2, working from a laptop (fictional person).

```yaml
occupation: "Data analyst, focused on business reporting and automation"
target_roles: ["Data analyst", "BI analyst", "Junior analytics engineer"]
acceptable_roles: ["Operations analyst with a data focus", "Sales analyst"]
seniority: "mid-level"
years_experience: {total: 4, in_role: 3}
seniority_margin: 2
key_skills: ["SQL", "Python", "Power BI", "Advanced Excel", "dbt (familiar)"]
search_keywords:
  es: ["analista de datos", "analista BI", "analista de inteligencia de negocios", "data analyst"]
  en: ["data analyst", "BI analyst", "business intelligence analyst", "analytics engineer"]
max_required_language: {english: B2}
work_mode: ["remote_region", "hybrid"]
cities: ["Lima"]
timezone_max_diff_h: 3
contract: ["employee", "contractor"]
min_salary: {amount: 6000, currency: PEN, period: month, type: gross}
evidence:
  type: ["repositories", "case_studies"]
  main_links: ["https://github.com/example"]
  pieces_per_application: 2
reviewer_role: "Data Lead or Analytics Manager, depending on the role"
templates: ["cv-ats"]
deliverables: ["cv_ats.pdf", "cv.docx", "cover_letter.md"]
weekly_volume: 8
max_analyses_per_day: 5
sources:
  - {name: "Get on Board", via: api, level: 2}
  - {name: "Company ATS job boards (Greenhouse, Lever, Ashby)", via: api, level: 2}
  - {name: "Bumeran / Computrabajo", via: web, level: 1}
  - {name: "LinkedIn", via: manual, level: 1}
```

### How it would change for other cases

| Case | Main differences |
| --- | --- |
| Backend developer in Spain, English C1 | Evidence = repositories; reviewer = Engineering Manager; language filters out almost nothing; sources: InfoJobs, company ATS job boards, remote job boards |
| Nurse in Chile, onsite | No portfolio; evidence = certifications and references; filter by city and shift; reviewer = Head Nurse; local and hospital sources |
| Mid-level accountant in Mexico, hybrid | Evidence = case studies with metrics; reviewer = Finance Manager; filter by city and required certifications |
