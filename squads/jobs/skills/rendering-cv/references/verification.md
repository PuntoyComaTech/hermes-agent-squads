# Verification

Two scripts check the PDF after rendering. Neither needs a network. Each skips cleanly when its tool is missing: exit 2
with `skipped:` on stderr. A skip is not a pass. The card says which check was skipped and why.

## Contents

- verify_pdf.py
- verify_layout.py
- Date ranges
- When a check fails

## verify_pdf.py

Reads the text layer the way an applicant tracking system does.

    python3 verify_pdf.py <pdf> --pages 2 --ascii-dates --contains "Ana Example" --contains "Power BI" \
      --dump-text <dir>/cv_ats.txt

- Extractor: pypdf first (`pip install pypdf`), then Poppler `pdftotext -raw -enc UTF-8`. Neither is required. With
  neither, the check exits 2 as skipped.
- `--pages N`: an exact page count. pdfinfo or pypdf must be able to count pages, otherwise the check is skipped.
- `--min-chars N`: a text layer with fewer characters fails. An image-only PDF has none.
- `--contains TEXT` (repeatable): the text must appear in the text layer. Both sides are folded: whitespace, Unicode NFC
  and typographic punctuation (curly quotes, en and em dashes), so "Master's" matches its typeset form.
- `--ascii-dates`: fails when a year is joined to a non-ASCII dash in the raw layer. This check never folds.
- `--dump-text FILE`: writes the raw layer as UTF-8 before any check, so a failed check still leaves the dump.
- Exit 0 pass; 1 a check failed (each failure printed to stderr as `fail: ...`); 2 usage error or skipped.

Read the dump for: every experience entry with a start and an end date; the email address as printed text (not only as
a link or an icon); no replacement characters and no `(cid:` markers; one linear reading order.

## verify_layout.py

Measures word boxes (`pdftotext -bbox`), so it needs Poppler. It reports layout faults that a page count does not show:

| Check | Fails when |
|---|---|
| hole | A gap above 100pt between two body lines: an entry pushed to the next page leaves one |
| page ends early | A page that is not the last stops more than 25% above the bottom |
| thin last page | The last page is more than 35% empty: it reads as unfinished |
| stranded heading | A section heading is the last line of a page |
| orphaned entry | A page ends on a job or project title while its bullets resume on the next page |
| footer collision | Body text sits in the bottom 90pt band reserved for the footer |
| empty page | A page has no text |

Page count is `verify_pdf.py --pages`'s job; this script does not check it.

    python3 verify_layout.py <pdf>

Exit 0 clean; 1 layout problems (listed); 2 usage error or skipped (no Poppler with `-bbox`).

## Date ranges

Many applicant tracking systems split a date range on the ASCII hyphen. An en dash (U+2013) makes the range unreadable,
and the date is dropped. `--ascii-dates` finds these in the raw layer. Quantity ranges are left alone: "EUR 1500-2000"
and "2000-5000 requests/s". Ranges of two years, of a year and a two-digit year (2019-20), and numeric dates
(03/2016-07/2024) are caught.

The renderer already writes hyphens in date fields. The check protects the rest of the document (headers, notes,
letters) and the case where a hand edit brings a dash back.

## When a check fails

1. Read the message. Fix the cause in the content or the template, never by changing a fact.
2. Re-render with `render_cv.py` and re-run the failed check. Three attempts in total at most.
3. If a fault remains, report it in the card with the check name and the message. Do not ship it silently.
4. If a tool is missing, put the install line in the card: `pip install pypdf`, `brew install poppler` on macOS,
   `apt install poppler-utils` on Debian and Ubuntu. The agent never installs packages itself.
