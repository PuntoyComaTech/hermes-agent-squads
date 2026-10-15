# Onboarding: interview script

## Contents

1. How to run the interview
2. Site questions
3. Mapping the answers
4. What the user sees

## 1. How to run the interview

- Read `USER.md` (the user profile memory) and any existing site folder first; show a draft with what you inferred and mark unconfirmed values `(?)`.
- At most 5 questions per round, numbered, with options. Ask what you cannot infer before anything else.
- No technical questions unless the user is one: ask about their business, visitors and what the site must do. Stack, provider and database are decided with the defaults below and explained in one line.
- A vague answer ("something modern") gets one concrete request: "Send me one or two sites you like."
- Never a silent default: propose the value, say the effect in one line, then confirm.
- Files the user sends (logo, texts, photos, screenshots) go to `<site>/inputs/`; list the paths in `spec.md -> Content sources`.
- Show the result in plain words and wait for "ok". Then write `site.yaml` with `active: false`, and only set `active: true` when the spec is approved.

## 2. Site questions

| # | Question (plain language) | Lands in |
|---|---|---|
| 1 | What is the site for? One or two lines | `spec.md -> Goal`, `type` |
| 2 | Who will visit it, and what should they do there? | `spec.md -> Audience`, pages and calls to action |
| 3 | Which pages do you imagine? (or "you propose") | `spec.md -> Pages` |
| 4 | Where does the content come from: I write it, you draft it from my info, or an existing site or document | `spec.md -> Content sources` |
| 5 | In which languages? | `site.yaml -> languages` |
| 6 | Do you have a look already: a logo and colors, sites you like, or you propose | `design.source` (`own` here, or a marketing brand slug) |
| 7 | Does it take bookings, collect forms or have user accounts? | `integrations`; may change `type` |
| 8 | Do you have a domain? (which, bought where, or not yet) | `domain` |
| 9 | Is it for a business (it earns money)? | blocks commercial use on Vercel Hobby |

Only if applicable: the current site being replaced (address, so its pages and redirects can be inventoried); a legal page the site must show (privacy, cookies, terms); a date it must be live by.

## 3. Mapping the answers

Type, pages and stack: `stacks.json` (`type` per stack; the stack follows the type).

- Hosting default is `cloudflare`; `vercel` only when the user already uses it.
- Data only if the spec needs it, and never in this milestone unless the site cannot work without it.
- A server-rendered site in production needs the paid Workers plan once it passes the free tier: state the condition and the current price in the spec and again in the publish question.
- Milestones: at most one day of work each, ordered so the first one produces something visible. Every acceptance criterion is testable (page, action, expected result).
- The first milestone never carries accounts, payments or a database.

## 4. What the user sees

```text
🥐 Panadería Sol · your site plan
What it is: a page with your menu, hours and a contact form, in Spanish and English.
Stack: Astro, in plain words: an extremely fast site, no server, USD 0/month.
Plan: M1 home and menu · M2 contact form and legal pages · M3 English version.
Still open: do you have the menu as a PDF or should I write it from your dishes?
Reply "ok" to start, or tell me what to change.
```

Rules for the message: no file paths, no jargon, no model or tool names, at most one screen. The reply options are always quoted literally so the user can copy them.
