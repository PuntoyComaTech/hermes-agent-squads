# Filter rules

Applied in this order; the first rule that discards, discards. Record `filter` and one short `filter_reasons`
phrase per rule used.

1. **Scam or closed**: asks for payments or bank details, no identifiable company, 404 or "position closed" ->
   DISCARD, with a label (`scam`, `closed`).
2. **Language**: normalize what the opening requires with the table below. Above `max_required_language` ->
   DISCARD. In that language with no stated level -> FLAG, warning "interview probably in <language>".
3. **Geography**: residence or onsite presence outside `work_mode` and `cities`, remote restricted to another
   country, or a time-zone difference above `timezone_max_diff_h` -> DISCARD.
4. **Role**: does not match `target_roles` or `acceptable_roles` -> DISCARD.
5. **Seniority**: requires more than `years_experience.in_role + seniority_margin` years -> DISCARD; between `+0`
   and `+margin` -> FLAG.
6. **Contract and salary**, only when the opening states them: outside `contract` or below `min_salary` ->
   DISCARD. When they are not stated, they never discard.
7. **Avoid lists**: a company in `avoid_companies` or a sector in `avoid_sectors` -> DISCARD.

Nothing discards -> PASS. Never soften a requirement so that an opening passes; an unstated datum is `unknown`,
never a guess.

## Language to CEFR

| Text in the opening | Assumed CEFR |
|---|---|
| native, bilingual, nativo, bilingue | C2 |
| fluent, advanced, proficient, C1, C2 | C1 |
| upper-intermediate, B2, business, professional working proficiency, "daily meetings with clients" | B2 |
| intermediate, conversational, B1, "reading documentation" | B1 |
| basic, elementary, A1, A2, "nice to have" | A2 |
| the opening is in that language with no stated level | unknown -> FLAG |
| the opening is in the user's native language with no mention | not required |

`required_language` in `opening.md` carries the normalized value per language, e.g. `{english: B2}`.

## Labels

Short snake_case tags that travel to the analysis: `language_not_stated`, `possible_repost`, `salary_missing`,
`contract_missing`, `scam`, `closed`. Add one only when it is visible in `opening.md`.
