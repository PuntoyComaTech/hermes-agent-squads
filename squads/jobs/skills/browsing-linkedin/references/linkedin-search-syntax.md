# Posts search syntax

LinkedIn publishes none of this. What follows was measured on the shared signed-in browser on 2026-10-22;
`market_urls.py` writes the URL so no card types one by hand.

## The URL

```
https://www.linkedin.com/search/results/content/?keywords=<boolean>&origin=FACETED_SEARCH&sortBy="date_posted"&datePosted="past-24h"
```

| Parameter | Meaning |
|---|---|
| `keywords` | the Boolean string, percent-encoded |
| `origin` | `FACETED_SEARCH`, as the search box writes it |
| `sortBy` | `"date_posted"` newest first; the quotes are part of the value; leave it out for relevance |
| `datePosted` | `"past-24h"` or `"past-week"`; the quotes are part of the value |

Measured: one 24 h search with `("estamos contratando" OR "we're hiring") AND "data analyst"` returned posts aged
31 minutes to 3 hours, first page newest first. A second search in Spanish returned the same shape, and no card in
either was older than 3 hours, so the window held for these queries. Still read each card's age text: the parser
drops what is older than the card's window.

## Boolean strings

- `AND`, `OR`, `NOT` in capitals; lowercase words are searched as text.
- A quoted phrase is exact; parentheses group: `("data analyst" OR "BI analyst") AND "SQL" NOT ("intern")`.
- Under 256 characters; split by language or by title family instead of nesting further.
- One search per language: the words are matched as written, not translated. The Spanish search with
  `("estamos contratando" OR "vacante") AND "analista de datos"` matched posts the English one never showed.

## What the search does not do

Measured, on 9 English and 9 Spanish cards: the Boolean match does not make a post a hiring post. Five of the nine
Spanish results were people announcing they were looking for work (`#OpenToWork`), and one English card was a
learning diary that mentions the role. Read each snippet and drop what is not an employer or a recruiter hiring.

There is no place filter on this search: the cards came from several countries for one query. When the user's market
matters, read the post for its city and drop what is out of reach — the card text is the only location evidence.

## Building a query from a profile

- `--any`: the phrases people write where the user works, one group per language — "estamos contratando",
  "estamos buscando", "buscamos", "vacante", "we're hiring", "join our team".
- `--all`: one role title from `search_keywords` or `target_roles`.
- `--not`: only the words the user's own `avoid_*` and `seniority` exclude; a guess removes real posts.
- Two queries per card at most. A third language is a second card's question, not this card's.
