# Investigation checklist

Work through these in order and record each answer before scaffolding. A stop condition ends the work and goes to the
user.

| # | Check | Record | Stop condition |
|---|---|---|---|
| 1 | robots.txt for the search and detail paths | Allowed or disallowed, per path | A path the CLI needs is disallowed. |
| 2 | Terms of use | Whether automated access is allowed for personal use | The terms forbid automated access. |
| 3 | Login | Whether results and details are public | Results or details need an account. |
| 4 | Data source | A JSON endpoint behind the site's search (prefer it), or HTML results | Neither is stable enough to parse. |
| 5 | Search parameters | Query, place, recency, workplace type, page and page size | No recency filter: note it, the wrapper filters by date. |
| 6 | Result fields | id, title, company, location, date and url per result, with the field path or CSS anchor | No id or url on each result. |
| 7 | Detail fields | Description, employment type, closed status | No detail endpoint: search rows only, which must be said. |
| 8 | Bot protection | Whether a plain request returns the content | Only a paid unlocker returns content: tell the user the cost per query first. |
| 9 | Dates and language | Date format and the posting language | Relative dates only ("3 days ago"): date stays null, say so. |

## Mapping to the squad's result shape

| Field | Source on the board |
|---|---|
| id | The posting id in the URL or the API. |
| title | The title with entities decoded. |
| company | The employer name. Null when absent; never guessed. |
| location | The place text as the board prints it. |
| date | The posting date as YYYY-MM-DD. Null when absent. |
| url | The posting's own page, or the employer's link when the board aggregates. |
| work_mode | Optional: remote, hybrid or onsite when the board shows it. |

## Health gate

After scaffolding, run the health check with `--detail`. The verdict decides `enabled`: `healthy` only.
