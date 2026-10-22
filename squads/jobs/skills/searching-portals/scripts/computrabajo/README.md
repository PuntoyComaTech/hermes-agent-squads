# computrabajo

Computrabajo's Colombian public listing, read with one HTTP GET per page. Standard library only.

## Addresses

- Search: `https://co.computrabajo.com/trabajo-de-<keywords>-en-<place>`; `?pubdate=N` narrows the server to the
  last N days (`?pubdate=1` is the last 24 hours), `&p=N` is the page (checked live: page 2 returns other rows).
  Keywords and place are lowercased, accent-free slugs. Omitting the place drops the `-en-<place>` part.
- Detail: the offer page under `/ofertas-de-trabajo/`, whose cards carry `data-id`.

## Flags

| Flag | Meaning |
|---|---|
| `--query` / `-q` | keywords, required (the address is built from them) |
| `--location` / `-l` | place, e.g. `Bogotá, D.C.` becomes `bogota-dc` |
| `--jobage N` | last N days through `pubdate=N` |
| `--limit N` | rows printed (default 20; one page holds at most 100, so a larger value is clamped) |
| `--page N` | 1-indexed page through `&p=N` |
| `--country xx` | market subdomain (default `co`) |
| `--today YYYY-MM-DD` | day that relative ages are counted back from |
| `--fixture-dir DIR` | read captured HTML instead of the network (or `COMPUTRABAJO_FIXTURE_DIR`) |

`--remote` is not mapped: the listing states no workplace type, and inventing one would mislabel rows.

## Notes

- `id` is the offer URL. `https://co.computrabajo.com/ofertas-de-trabajo/<id>` alone answers 404, so the board
  offers no id-only address; the listing's `data-id` is not enough to reopen an offer. A detail page whose JSON-LD
  `url` is not https on a computrabajo.com host (an employer, a `javascript:` href) falls back to the offer that was
  asked for, and a listing card whose link is off-host or not https is dropped. `datePosted` is normalised to
  YYYY-MM-DD.
- Ages arrive as `Hace  2  horas` (double spaces), `Ayer`, `Hace  3  días`. Hours and minutes count as today.
  A floor such as `Hace más de 30 días` yields no date.
- Listings sometimes show no company; that row keeps `company: null` rather than a placeholder.
- Robots: `co.computrabajo.com/robots.txt` disallows `/ofertas-de-trabajo/*<param>=` and account paths. Listing
  and offer pages without those parameters are allowed.

## Offline

`--fixture-dir` (or `COMPUTRABAJO_FIXTURE_DIR`) points at a directory holding `listing.html`,
`listing-p<N>.html` and `detail.html`. Nothing opens a socket in that mode.
