# Review lenses

Five independent subagents, five blocks of `review-N.json`. Each one gets only its files, a clean context and its
output schema; it never reads the kanban card, never writes files and never sees the other lenses.

## truthfulness

Files: `application/`, `achievements.yaml`, `opening.md`.
Checks every claim in the documents and the CV against `achievements.yaml`: numbers, dates, titles, companies,
tools, proficiency levels and languages must match a `verified: true` entry, neither raised nor rounded up. Missing
citation on a bullet that states a result is a finding.

Output: `{"verdict": "PASS|FAIL", "findings": [{"location": "", "text": "", "problem": "", "expected_achievement": ""}]}`

## ats

Files: `application/cv_ats.txt`, `application/cv_ats.html`, `render_report.json`, `analysis.json`.
Checks single-column reading order, section headings, selectable text, real links (from the report) and keyword
coverage; lists the missing keywords that the application could reasonably cover. Defects from missing engines are
environment notes, not document defects.

Output: `{"verdict": "PASS|FIX", "keyword_coverage": 0.0, "missing": [], "defects": []}`

## recruiter

Files: `application/`, `opening.md`, `profile.md`.
Reads like a recruiter with 30 seconds: who this person is, the role they want, whether the location and
work-mode lines are visible, whether evidence is linked. Reports blockers only when they would sink the
application (wrong role, missing contact block, unreadable first screen).

Output: `{"verdict": "PASS|FIX", "seconds_to_understand": 0, "would_open_evidence": true, "blockers": []}`

## hiring_manager

Files: `application/`, `opening.md`, `analysis.json`.
Plays the `reviewer_role` from `profile.md`: can this person do the job the opening describes? Are the must-haves
addressed, are the hard gaps handled honestly, which interview questions does this raise? Concerns never become
corrections on their own; only clear overselling does.

Output: `{"verdict": "PASS|FIX", "can_do_the_job": true, "concerns": [], "interview_questions": []}`

## writing

Files: `application/`, `opening.md`.
Grammar, spelling, jargon, bullet shape per writing-applications step 3, length within the format the
deliverable needs, tone of the letter and the answers. Each finding names the fix; never rewrite the text here.

Output: `{"verdict": "PASS|FIX", "findings": [{"location": "", "text": "", "fix": ""}]}`

## Aggregating

1. Copy each block verbatim into `reviews` of `review-N.json`.
2. Truthfulness FAIL -> never APPROVED. Collect the findings as `type: content` corrections with the exact
   replacement text required from a verified achievement.
3. Any blocker or fixable finding -> FIX, with each correction carrying `type` and instructions. Round 2 (or a
   CHANGE round) that is still not APPROVED -> NOT_APPROVED.
4. `summary_for_user`: at most 5 lines, in the user's language, no internals.
