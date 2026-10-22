# talent

talent.com's Colombian public listing, read with one HTTP GET per page. Standard library only.

## Addresses

- Search: `https://co.talent.com/jobs?k=<keywords>&l=<place>&date=N&radius=25`. `date=N` is the last N days
  (`date=1` is the last 24 hours; `date=3` and `date=7` were each checked against the live listing). `p=2`
  returned no cards, so there is no page flag.
- Detail: `https://co.talent.com/view?id=<id>`, whose JSON-LD carries the posting.

## Flags

| Flag | Meaning |
|---|---|
| `--query` / `-q` | keywords, required |
| `--location` / `-l` | place, free text |
| `--jobage N` | last N days through `date=N` |
| `--limit N` | rows printed (default 20; one page holds at most 100, so a larger value is clamped) |
| `--country xx` | market subdomain (default `co`) |
| `--today YYYY-MM-DD` | day that relative ages are counted back from |
| `--fixture-dir DIR` | read captured HTML instead of the network (or `TALENT_FIXTURE_DIR`) |

`--remote` is not mapped: the search cards state no workplace type.

## Notes

- The cards are server-rendered. Each card's `<time datetime="...">` is the board's own timestamp; the visible
  text reads `Última actualización: hace 4 horas`, so the parsed date is the day the board last touched the
  posting, which is the closest thing this listing gives to a posted date. The detail page carries the true
  `datePosted`.
- Rows come back newest first, so a small `--limit` is not spent on stale cards.
- Some old offers keep their page but lose the JSON-LD `JobPosting`. Their visible heading and body are still
  read, and `details.structured_data` is `false` on those rows; a normal posting carries `true`.
- Result `url` is the talent.com view page. The board aggregates other sites and the employer's own page is not
  followed, so `url_hosts` stays `talent.com`: a JSON-LD `url` off that host is dropped and the view page is printed.
- `id` is numeric and reopens the offer with `view?id=`.
- Search returns 14 to 20 cards depending on the market and window; the CLI prints what the page holds.
- Robots: `co.talent.com/robots.txt` disallows `/search-jobs/*`, `/services/api-new/search` and redirect paths;
  the `jobs` and `view` pages used here are allowed.

## Offline

`--fixture-dir` (or `TALENT_FIXTURE_DIR`) points at a directory holding `listing.html` and `detail.html`.
Nothing opens a socket in that mode.
