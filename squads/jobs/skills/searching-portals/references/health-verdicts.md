# Health verdicts

`portals.py health` answers one question per portal: does its CLI still return what the portal returns? It spends a
bounded number of requests to find out.

## Steps

1. Sentinel probe: `search` with `example_query`, `--limit 3` and the portal's own flags, plus `example_location` when
   the portal needs a place.
2. Empty answer: one retry with `retry_query`. Still empty: `broken`.
3. Degraded scan, applied to the rows returned (at most three):
   - company null or empty on every row;
   - an empty title on any row;
   - HTML tags or entities (`&amp;`, `<b>`) in any title;
   - any `url` not on `url_hosts`. An empty `url_hosts` only requires an http(s) address.
4. With `--detail`: one `detail` on the first row. Degraded when it fails, has no description, or its description
   still contains HTML tags or entities.

## Verdicts

| Verdict | When | What to do |
|---|---|---|
| healthy | Rows came back, the scan is clean and the detail (if asked) is readable. | Nothing. |
| degraded | Rows came back but the scan or detail found junk. The parser is half-working. | Tell the user with the reasons. Disable only on their word. |
| broken | A CLI error that is not a block, unreadable output, or zero rows for both queries. | Tell the user. Disable only on their word. |
| inconclusive | Rate limit (429), block page, 5xx after retries, timeout, no network, missing bun or CLI. | Back off, report it, do not retry in a loop. |
| blocked | The portal's host is on `JOBS_BLOCKLIST`. No probe is sent. | Nothing. The user set the list. |

Rules that hold for every verdict:

- A 429, a block page or an outage is never evidence of breakage.
- Per portal per run: one probe, at most one retry, at most one detail.
- Health never edits a manifest. `enabled` changes only with the user's confirmation.
- A portal with no yield history cannot be judged from one empty run. Compare with earlier runs (the `portal` field in
  the seen state) before calling a portal that used to produce rows broken.

## Output

`meta.today`, `meta.checked`, `meta.problems` (manifests that failed validation), and `portals[]` with `status`,
`reasons`, `notes` (for example the retry) and `probes`.

```json
{"portal": "linkedin", "status": "degraded", "reasons": ["company null or empty on all 3 results"], "probes": 1}
```
