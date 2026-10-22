# Platform research

How to find the platforms that matter in one market without trusting one page.

## Contents

- Query patterns
- Source quality
- Classifying a platform
- What goes in the file

## Query patterns

Run each in the country's main language and in English, for the user's field (`occupation`):

- `best job sites <country> <field>`; `portales de empleo <país> <sector>`; `sites de emprego <país> <área>`
- `<country> public employment service jobs portal` (the state service is often free and large)
- `<field> job board <country>` for sector boards; `remote jobs board <field>` for remote work
- `<country> job scams fee to apply` to remove sites that charge applicants

## Source quality

Independent evidence is a page the platform does not own and that is not the platform's paid placement: a news or
labour-ministry page, a university career centre, a professional association, a community thread with named users, a
comparison written by someone with no referral link. Count hosts, not pages: two articles on one site are one host.
Mark an article as weak when it carries referral links to the sites it ranks.

## Classifying a platform

| Field | How to decide |
|---|---|
| scope | `global`, `country` (one market), `region` (several), `sector` (one field), `remote` (location-free) |
| tier | `recommended`: two independent hosts and the user's field appears on it; `optional`: one source or a thin fit; `skip`: fees, scams, dead or off-field |
| login_required | what the public page shows without an account: the search form and results visible = false |
| search.method | `portal_cli` if `portals.py list` shows it (LinkedIn's public listings are that portal); `browser_url` only for a site a squad skill already reads, such as LinkedIn's hiring posts through browsing-linkedin; otherwise `manual` |

## What goes in the file

One object per platform with `why` in one sentence that names the fit (field, country, level) and each evidence page
with a note of what it says. Never copy a source's statistics without its URL. Dates are the day the page was read.
