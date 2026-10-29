# Platform adapters

LinkedIn is one profile among several. For any other platform (a national job board, a sector board, a freelance site)
the writer maps the same material onto that platform's fields, using only what the platform is known to ask for.

## Contents

- The common model
- Mapping to a platform
- Paste-kit mode
- Upwork
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

## Paste-kit mode

A supported mode, not a fallback, for a platform the writer must not drive (Upwork) or has no form script for. The
writer drafts and checks the copy as usual and renders `<P>/profiles/<platform>.md`; the user pastes each field. After
the user approves, the manager writes `<P>/profiles/approved-<platform>.json` (`fields` rows only, no `structure`).
To verify, the user opens their own profile, expands every "more", selects all, copies, and pastes the text into the
chat; the manager saves it as `<P>/profiles/<platform>-page-<YYYY-MM-DD>.txt` and the writer runs
`profile_diff.py verify-paste <approved> <page.txt>`. A field that fails is reported with its reason; nothing is
pasted for the user.

## Upwork

Paste-kit only. Upwork's terms ban any script that acts on an account without an API key, with warnings and bans
(https://support.upwork.com/hc/en-us/articles/43342677368467), and its bot check refuses a headless browser: the
writer never opens upwork.com, visible window or not, and never tries to get past the check.

Limits are built into `check_profile_copy.py` for `"platform": "upwork"` (sources: support articles 360016252373 and
360016144974, resources/freelancer-profile-tips): `headline` (title) 70, `about` (overview) 5,000 of which ~250 show
in search, `skills_count` 20, `portfolio_title` 70, `portfolio` (description) 600. The employment description limit
is not stated: keep it at the concise 600 like `experience`. Sections: `headline`, `about`, `experience` (one per
employment entry), `portfolio` (label = project title). Hourly rate, categories, photo and video are the user's.

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
