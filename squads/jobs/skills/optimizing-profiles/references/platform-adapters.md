# Platform adapters

LinkedIn is one profile among several. For any other platform (a national job board, a sector board, a freelance site)
the writer maps the same material onto that platform's fields, using only what the platform is known to ask for.

## Contents

- The common model
- Mapping to a platform
- Unknown limits
- Typical platform shapes

## The common model

Every public profile is some of: a headline or desired title, a summary, experience entries, a skills list, education
and certifications, links, and settings for who can see it. `check_profile_copy.py` treats each as a `section` of
blocks: `headline`, `about`, `experience`, `skills`, plus any section name the platform uses. The same achievements
feed all of them.

## Mapping to a platform

1. Take the section names from the platform's own form as the user pastes them, or from the newest platforms file.
2. Put a block per field. Use the section name the platform uses, so the audit reads like the form.
3. Limits: only `profile_fields` from `reports/platforms-*.json` (each has a source page) go into the copy file's
   `limits` (`headline_max` becomes `headline`, `summary_max` becomes `about`, `skills_max` becomes `skills_count`,
   `title_max` becomes `experience_title`). The checker does not know any other platform's limits.
4. Keywords: the same market terms apply; a national board often searches in the local language, so use the terms of
   that language from `search_keywords` and the market file's matching titles.

## Unknown limits

When the platform states none, say so in the audit ("limit not stated; check the field's counter when pasting") and
keep each block no longer than the user's current text in that field. Do not invent a limit.

## Typical platform shapes

- **Job board with a CV upload and a short profile:** the CV (rendering-cv) is the main asset; the profile is a headline
  and a summary of one paragraph.
- **Freelance or project marketplace:** a title, an overview aimed at a client's problem, and a portfolio of
  `public_evidence`. Rates and availability are the user's to enter.
- **Government or public employment service:** structured forms (occupation codes, education levels). Fill what the
  user's documents prove; do not guess a code.
