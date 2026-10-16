# Brand onboarding

Ask only what research and the brand files leave open.

## Procedure

1. Get the brand name and what exists: website, social profiles, Google Maps listing, product documents, files the user sent (note their paths).
2. File one `research` card (marketing-research, `skills: [researching-markets]`, key per `brand-contract` step 5). Ask for: website facts, colors (HEX) and typefaces as seen, active social accounts, review themes with verbatim quotes, and three competitors with what they run today. Every claim comes back with a URL and a date; a claim without both is not used.
3. Draft `brand.md` from `templates/brand.md` with `product-marketing`: Facts, Audience, Competitors and Voice from the research; every proof point `Verified: no` until the user confirms it; `status: draft`.
4. Ask the Required questions below, five per message at most. Write each answer into `brand.md` as it arrives and show the change.
5. When the user approves `brand.md` (and `DESIGN.md` once the producer has written it): set `status: active`, add the `Changes` line `v<N> <date> approved`, and offer the 90-day plan.

## Required (10)

1. Name and what it does, in one sentence. -> Facts.
2. What it sells, and at what price. -> Facts.
3. Who it is for, and who it is not for. -> Audience.
4. Country, city and markets; language, form of address (informal or formal), currency and timezone. -> frontmatter.
5. Website and social profiles. -> Facts.
6. The main goal for the next 90 days, and the number that shows it was reached. -> Facts.
7. Two or three competitors or alternatives, and where each falls short. -> Competitors.
8. How the brand speaks: three adjectives, banned words, emoji use and call-to-action rules. -> Voice.
9. Logo, colors and typefaces (files), or permission to propose them. -> `DESIGN.md`.
10. Monthly budget for ads and tools; "zero" is a valid answer. -> Facts.

## Recommended

- Channels used today, what works, and posts per week per channel. -> frontmatter `channels`, `weekly_quota`.
- Past work worth keeping.
- Customers' literal phrases; testimonials with permission. -> Audience, Proof points (`Permission to use: yes`).
- Objections heard and the answers. -> Audience.
- Legal or industry restrictions (health, finance, alcohol, minors). -> Restrictions.
- Who approves, when the brand is a client. -> frontmatter `approver`.
- What to ignore this quarter. -> Restrictions.
- Key dates: seasons, launches, local holidays. -> Restrictions.
- Creative risk: conservative, balanced or bold. -> Restrictions.
- Available assets: photos, videos, products to photograph, licensed music. -> `identity/`.

## Only for B2B, SaaS or e-commerce with data

- Buyer personas and decision roles.
- Funnel numbers: sessions, managers, orders, CAC, repeat purchase rate.
- Connected tools: Google Analytics, Search Console, CRM, email provider.
