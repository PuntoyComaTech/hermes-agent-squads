# Test fixtures

- `search-cards.json`: two synthetic `<li>` job cards in the shape of LinkedIn's public guest search response.
  The companies, titles and IDs are invented; the markup mirrors the live page so the parser runs on realistic structure.
- `detail-closed-excerpt.html`: a synthetic guest detail page for a closed posting (closed banner in the top card,
  description markup, job-criteria list).

Tests serve these over loopback. No test sends a request to LinkedIn.
