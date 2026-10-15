# Brand onboarding

The lead runs onboarding once per brand. Research first, ask second: only ask what the research could not settle and no brand file already answers. Questions go to the user in rounds of five at most.

## Procedure

1. Get the name and whatever exists: website, social profiles, Google Maps, product documents, files the user sent (note their paths).
2. File a research chain first (stage `research`): public sources only, and hand it a short brief. Ask it for: website facts, colors and typefaces as seen (HEX), active social accounts, review themes with verbatim quotes, and three competitors with what they run today.
3. Draft `brand.md` from `templates/brand.md`: Facts, Audience, Competitors and Voice filled from the research; Proof points marked `unverified` until the user confirms each; `status: draft`.
4. Ask the required questions below in rounds of five; write each answer into `brand.md` as it arrives and show the change.
5. On the user's explicit approval of `brand.md` (and `DESIGN.md` once the producer exists): set `status: active`, set `Changes` to a new line, and offer the 90-day plan.

The research stage returns files under `research/` with a URL and a date per claim. Anything without a source is not used.

## Required (10)

1. Name and what it does, in one sentence. → Facts.
2. What it sells, and at what price. → Facts.
3. Who it is for, and who it is not for. → Audience.
4. Country, city and markets; language, variant and form of address (`tú`, `usted` or `vos`); currency and timezone. → frontmatter.
5. Website and social profiles, if any. → Facts.
6. The main goal for the next 90 days, and how the user will know it was achieved. → Facts.
7. Two or three competitors or alternatives, and how each falls short. → Competitors.
8. How the brand speaks: three adjectives, banned words, emojis and call-to-action rules. → Voice.
9. Logo, colors and typefaces (files), or permission to propose them. → `DESIGN.md`.
10. Monthly budget for ads and tools; "zero" is a valid answer. → Facts.

## Recommended

- Channels used today, what works, and how often the user wants to post on each. → frontmatter `channels` + `weekly_quota`.
- What was already done that is worth keeping.
- Customers' literal phrases; testimonials with permission. → Audience + Proof points (`Permission to use: yes`).
- Objections heard and the answers. → Audience.
- Legal or industry restrictions (health, finance, alcohol, minors). → Restrictions.
- Who approves, when the brand is a client. → frontmatter `approver`.
- What to ignore this quarter. → Restrictions.
- Key dates: seasons, launches, local holidays. → Restrictions.
- How bold the brand can be: conservative, balanced or bold. → Restrictions.
- Available assets: photos, videos, products to photograph, licensed music.

## Only if applicable

B2B, SaaS or e-commerce with data:

- Buyer personas and decision roles.
- Funnel numbers (visits, leads, orders, cost per customer, repeat purchases).
- Connected tools: Google Analytics, Search Console, CRM, email provider.

## Rules

- One round of at most five questions; never dump the whole list.
- A question the research settled is not asked again.
- Proof points enter the table only with type, source and permission; the rest stay `unverified` and no piece may use them.
- `publishing` stays `manual`: the squad hands over a ready-to-post package and never publishes.
- The brand stays `draft` until the approval; a draft brand gets no calendar and no report.
