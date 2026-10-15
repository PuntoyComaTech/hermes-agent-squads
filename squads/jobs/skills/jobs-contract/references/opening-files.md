# Opening files

Per opening, under `<P>/openings/<ID>/`: `opening.md`, `analysis.json`, `status.json`, `application/`, `review-N.json`, `submission.json` and `interview.md`. Searches write `<P>/searches/YYYY-MM-DD-HH.md`.

## opening.md (scout)

```markdown
---
id: JOB-20260925-acme-data-analyst
company: Acme
role: Data analyst
url: https://...
apply_url: https://...
source: company site
posted_at: 2026-09-24            # or unknown
work_mode: remote_region:latam   # remote_global | remote_region:<r> | remote_country:<iso> | hybrid:<city> | onsite:<city> | unknown
opening_language: en
required_language: {english: B2} # B2 | unknown | not_required
filter: PASS                     # PASS | FLAG | DISCARD
filter_reasons: ["verifiable short phrases"]
labels: [language_not_stated]
---
<full text of the opening, as published>
```

## searches/YYYY-MM-DD-HH.md (scout)

Table, one row per opening found: `id | company | role | work mode | required language | filter | reason | url`; PASS first, then FLAG, then DISCARD grouped by reason.

## analysis.json (scout)

```json
{
  "id": "JOB-...",
  "requirements": {"must_have": [], "nice_to_have": [], "responsibilities": [], "tools": [],
                   "keywords": [], "disqualifiers": [], "priorities": []},
  "company": {"summary": "", "product": "", "sector": "", "brand_tone": "", "team_signals": [], "news": [], "sources": []},
  "evidence": [{"requirement": "", "achievements": ["ACH-007"], "confidence": 0.8, "note": ""}],
  "fit": {"score": 0, "decision": "PURSUE", "strengths": [], "gaps": [], "hard_gaps": [],
          "transferable": [], "overselling_risk": "low", "reason": ""}
}
```

`decision`: PURSUE, WATCH or REJECT. `confidence`: 0 to 1. `keywords` feed the CV keyword check.

## companies/<company>.md (scout)

Dated profile: summary, product, sector, brand tone, team signals, news, sources. Reused while under 30 days old.

## application/ (writer)

| File | Content |
|---|---|
| `strategy.md` | headline, narrative, order of experiences, keywords to cover, evidence pieces and why, CV language |
| `cv_content.json` | input of `render_cv.py`, see skill rendering-cv |
| `cover_letter.md`, `answers.md` | per `deliverables`; each paragraph ends with `<!-- achievements: ACH-... -->` |
| `cv_ats.pdf`, `cv.docx`, `cv_ats.txt`, `render_report.json` | output of `render_cv.py` |

`interview.md` lives beside `application/`: it is the writer's interview-preparation output for that opening.

## review-N.json (reviewer)

```json
{
  "id": "JOB-...", "round": 1, "verdict": "APPROVED",
  "reviews": {
    "truthfulness": {"verdict": "PASS", "findings": [{"location": "", "text": "", "problem": "", "expected_achievement": ""}]},
    "ats": {"verdict": "PASS", "keyword_coverage": 0.0, "missing": [], "defects": []},
    "recruiter": {"verdict": "PASS", "seconds_to_understand": 0, "would_open_evidence": true, "blockers": []},
    "hiring_manager": {"verdict": "PASS", "can_do_the_job": true, "concerns": [], "interview_questions": []},
    "writing": {"verdict": "PASS", "findings": [{"location": "", "text": "", "fix": ""}]}
  },
  "corrections": [{"type": "content", "instructions": ""}],
  "summary_for_user": "5 lines at most"
}
```

`verdict`: APPROVED, FIX or NOT_APPROVED. `type`: content, format or strategy.

## status.json (whoever acts)

```json
{"id": "JOB-...", "status": "analyzed",
 "history": [{"date": "2026-09-25T08:14", "status": "found", "by": "jobs-scout", "note": ""}]}
```

Statuses, lowercase snake_case: found, discarded, analyzed, in_preparation, in_review, not_approved, ready, delivered,
applying, applied, manual_application, skipped, screening, interview, offer, rejected, closed. Append, never rewrite.

## submission.json (applier)

```json
{"id": "JOB-...", "result": "SUBMITTED", "method": "no_login_form",
 "filled_fields": [{"field": "", "source": "contact.yaml"}],
 "pending_questions": [], "screenshots": ["/abs/before.png", "/abs/confirmation.png"],
 "reason": "", "manual_kit": "application/kit.md"}
```

`result`: SUBMITTED, NEEDS_DATA or NOT_POSSIBLE. `method`: no_login_form, requires_account, email, linkedin,
captcha or other. `source`: contact.yaml, application-data.yaml, answers.md, cv or `consult:<card id>`.
