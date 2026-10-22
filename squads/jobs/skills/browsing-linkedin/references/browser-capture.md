# Browser capture

The capture file is `{"source_url": "<the posts search url>", "items": [{"componentkey": "...", "text": "...",
"anchors": ["..."]}]}`. `capture_rows.py` does the parsing; the browser only collects raw text and links.

## Collecting the cards

```python
items = js("""(() => {
  const hook = '[componentkey^="expanded"][componentkey$="FeedType_FLAGSHIP_SEARCH"]';
  return Array.from(document.querySelectorAll(hook)).map(c => ({
    componentkey: c.getAttribute('componentkey'),
    text: c.innerText,
    anchors: Array.from(c.querySelectorAll('a')).map(a => a.href).filter(Boolean)
  }));
})()""")
```

Only that one attribute is needed for the id. A post card carries no permalink, no URN and no `<time>` element, so
do not look for one: the id is the `componentkey`, and it read the same on two visits to the same search.

## What a card's text looks like

```
Feed post
Kamran Azad                      <- a person's name, or a page's name
• 2nd                            <- sometimes
Senior Recruiter (US, Canada & LATAM)   <- sometimes, the headline
35m                              <- relative age: 31m, 1h, 3h, 2d
Follow                           <- or Join, Request services
🚀 Were Hiring: Process Mining Consultant…
```

The body follows the button. A card may also hold a nested LinkedIn job card (`Data Analyst … | Company | City |
View job | 35K GBP/yr`); its link is a `/jobs/view/<id>` anchor, which `capture_rows.py` records as `job_ids` for
the portal tool's `detail`. Two of eighteen measured cards carried one; the rest were plain text.

## Paging

Measured: the results page shows 3 posts, and each press of the button whose text is `Load more` appends 3 more. The
page window does not scroll (window height equals document height) and scrolling the results panel loads nothing, so
paging is that button, not a scroll. Press it at most 4 times, 2 to 4 seconds apart, and stop when it is gone.

Posts that arrive from `Load more` are appended, so the list is no longer newest first: decide the window from each
card's age text, never from its position.

## When nothing matches

`js('document.querySelectorAll(\'[componentkey^="expanded"]\').length')` counts every card-shaped block on the page.
Zero of the hook while the page shows posts means the markup changed: read the page text, build `items` by hand from
what you see, and write `selector_drift` in the card result so the builder updates this file.

A page that says the search found nothing is an answer: record it with zero cards and say which Boolean was run.
