# elempleo

elempleo's Colombian public listing, read with one HTTP GET per search. Standard library only.

## Addresses

- Search: `https://www.elempleo.com/co/ofertas-empleo/[<city>/]trabajo-<keywords>`, keywords and city as
  lowercased, accent-free slugs.
- Detail: the offer page under `/co/ofertas-trabajo/`, whose cards carry `data-url`.

## Flags

| Flag | Meaning |
|---|---|
| `--query` / `-q` | keywords, required |
| `--location` / `-l` | city, e.g. `Bogotá` becomes `/bogota/` |
| `--remote remote\|hybrid\|onsite` | keeps rows of that workplace type, and rows that state none |
| `--limit N` | rows printed (default 20; one page holds at most 100, so a larger value is clamped) |
| `--today YYYY-MM-DD` | day that relative ages are counted back from |
| `--fixture-dir DIR` | read captured HTML instead of the network (or `ELEMPLEO_FIXTURE_DIR`) |

## Notes

- No `--jobage`. The board's own date control (`PublishDatesInfo1=1`, "Hoy y ayer") and its recent sort
  (`orderFilter=PublishDate_Desc`) were both tried against the live listing and neither narrowed nor reordered
  the results, so this CLI does not claim a server-side date window. The caller's window is applied to the
  parsed dates instead.
- No `--page`: the listing's paging control is client-side and no page parameter was proven. The flag is refused with
  `BAD_ARG`, never ignored.
- `remote` comes from the card's own label (`- Hibrido`, `- Remoto`, `- Presencial`), so the flag is mapped and
  filtered here. A row that states no workplace type is kept.
- Ages: `Hace 1 semana` is 7 days, `Hace 3 semanas` 21, `Hace 1 mes` 30. The board also ships a client-side
  template row (`{{title}}`) at the end of the list; it is skipped.
- `id` is the offer URL: `/co/ofertas-trabajo/<id>` alone answers 404, so the numeric id cannot reopen an offer.
- `Empresa confidencial` is the board's own label for a hidden employer and is kept as the company text.
- Detail dates arrive as `2026-9-4` and are normalised to `2026-09-04`. `jobLocationType: TELECOMMUTE` adds
  `work_mode: remote`.
- Robots: `www.elempleo.com/robots.txt` disallows admin, account and form paths; the listing and offer pages
  used here are allowed.

## Offline

`--fixture-dir` (or `ELEMPLEO_FIXTURE_DIR`) points at a directory holding `listing.html` and `detail.html`.
Nothing opens a socket in that mode.
