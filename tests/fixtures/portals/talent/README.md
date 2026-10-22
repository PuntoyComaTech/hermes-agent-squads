# talent fixtures

Captured 2026-10-22 from the public talent.com Colombia site. Public job listings only; no account, CV or
personal data is included.

## listing.html

Source: `https://co.talent.com/jobs?k=analista+de+datos&l=Bogot%C3%A1` — the default listing for the query
`analista de datos` in Bogotá. This is the unsorted page, so it carries older postings (the newest rows read
`hace 1 día`, the oldest `hace más de 30 días`). 20 server-rendered cards.

## detail.html

Source: `https://co.talent.com/view?id=642670062979261969` — a posting from that search. Carries a JSON-LD
`JobPosting` with `datePosted`, `hiringOrganization` and `jobLocation`.

## detail-no-ld.html

Source: `https://co.talent.com/view?id=571861773647417250` — an old card from the same listing whose page no
longer carries the JSON-LD `JobPosting` but still shows the heading and description. Used to test that fallback.

