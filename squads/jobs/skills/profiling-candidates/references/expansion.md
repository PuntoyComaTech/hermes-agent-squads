# Expansion (Mode: EXPAND)

Finds competencies the user has not declared: skills, projects and certificates that the documents or public pages
show and `achievements.yaml` does not. Additive only: nothing is removed or changed, and nothing is written until the
user approves each group. The manager's rules are in `../SKILL.md`.

## Contents

- Inputs
- Steps
- Writing the approved groups

## Inputs

- `<P>/achievements.yaml`: the declared skills, certifications and public evidence. This is the baseline.
- `<P>/documents/**`: the material the user dropped in. `expand_candidates.py` reads text files; the manager reads PDF
  and DOCX files in chat.
- Public pages (the GitHub profile and repositories, a portfolio, a course syllabus): the manager has no web tool, so
  the jobs-scout fetches them in step 2.

## Steps

1. **Baseline.** Read `profile.md` (occupation, target_roles, `evidence.links`) and `achievements.yaml`.
2. **Public pages, only when the profile lists links.** File a support card for jobs-scout (`kanban_create` with no
   parent): `assignee: jobs-scout`, `skills: [finding-jobs]`, body `Mode: EVIDENCE`, the project path, and the URLs from
   `profile.md` `evidence.links` and `achievements.yaml` `public_evidence`. URLs only; never the links in
   `contact.yaml`. `workspace_kind: dir`, `workspace_path: <P>`, `idempotency_key: jobs:evidence:<project>:<YYYY-MM-DD>`.
   Do not use `analyzing-jobs`: that skill scores openings. Tell the user: "Reading your public pages; the list
   follows." Wait for `reports/evidence-YYYY-MM-DD.json`. If the user declines the web, skip this step and say so.
3. **Merge.** Run `python3 "$HERMES_HOME/skills/squad-jobs/jobs-contract/scripts/expand_candidates.py" --project <P>`,
   adding `--evidence <P>/reports/evidence-YYYY-MM-DD.json` when step 2 ran. The output lists candidates (skills,
   projects, certifications), skipped items with the reason, and the groups by source. The script decides what is new
   and what is a duplicate; the LLM does not.
4. **Judge.** Keep a candidate when the user could explain it in an interview; drop vague words a README uses in
   passing. Read each PDF and DOCX in `documents/` and add any competency it names that the list lacks, with that file as
   its source. Tag each item `stated` when a source names it, and `inferred` when only a project summary or a vocabulary
   term implies it. Never claim a skill that no source names, and never raise a level.
5. **Present, grouped by source.** One block per source, never one flat list:

   ```
   1. Source: documents/cv/cv-2026.txt
      + pandas (stated)
      + Power BI (stated)
   2. Source: https://github.com/ana-example/sales-etl (fetched)
      + project sales-etl: Python and pandas ETL (inferred from its summary)
   ```

   Then ask: "Reply with the group numbers to add (for example 1 and 2), or `skip`." Wait for the answer.

## Writing the approved groups

- Show the exact YAML of each approved addition. Write a group only after the user's "ok" for that group.
- Skill: a `skills:` entry `{name, proficiency: familiar, achievements: []}`. A higher level only when the user states it.
- Project: an `achievements` entry with `en` (and `es` when `application_languages` includes es), written from the
  summary, with `source: <URL>` and `verified: false`; and a `public_evidence` entry
  `{id, url, type: repository, achievements: [<ID>]}`.
- Certificate: a `certifications` entry `{id, name, issuer: null, year: null, source: <path>, verified: false}`. Issuer
  and year stay null unless the user states them.
- Every addition has `source:` set and `verified: false` until the user confirms that exact text.
- Recheck: run the script again. Written items now appear under `skipped` as already declared. Items the user declined
  appear again; that is expected.
- Report: the items written, the items the user declined, and the sources skipped (empty copies, unfetched pages) with
  the script's reason.
