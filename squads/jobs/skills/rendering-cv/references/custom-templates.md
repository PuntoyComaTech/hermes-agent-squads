# Custom templates: the guided flow

## Contents

- Who does what
- Step 1: take the design in
- Step 2: gate it
- Step 3: render with it
- What the gate checks
- When a check fails

## Who does what

- The user drops a design: an HTML file, a description, or a screenshot.
- The writer turns a description or screenshot into HTML that uses the slots below, and saves it in the project.
- `template_check.py` decides. The writer never registers a template by its own judgement.
- `render_cv.py` uses a project template only with a passing gate record whose fingerprint still matches the file.

## Step 1: take the design in

Save the template in the project, never in the skill folder:

- `<P>/templates/<name>.html`: one HTML file. `<name>` is lowercase letters, digits and single hyphens, up to 40
  characters (`modern-serif`).
- `<P>/templates/<name>.json` (optional, recommended): `{"kind": "cv", "page_limit": 2, "notes": "..."}`. `kind` is
  `cv` or `letter`; `page_limit` is 1, 2 or 3 and is the design's own limit. The page budget is the tighter of this
  and the profile's `market.cv_page_limit`.

A description or screenshot becomes HTML in one pass. Use the same single column layout as the shipped templates:
one `h1` name, a contact paragraph with the email, phone and location as text, `h2` sections, `h3` entries,
`ul` bullets, body text 9pt or larger. Copy the shape of `templates/classic.html` (in the skill folder) and change
only the styles. A screenshot's layout is not a fact: keep one column even when the screenshot has two.

The slots the renderer fills, exactly once each: `{{LANG}}` (the document language), `{{TITLE}}` (the name and
headline), `{{PAGE_SIZE}}` (`Letter` or `A4`, in `@page`), and `{{CONTENT}}` (the whole document body). Any other
`{{...}}` is refused by the gate.

## Step 2: gate it

```bash
python3 "$HERMES_HOME/skills/squad-jobs/rendering-cv/scripts/template_check.py" <P>/templates/<name>.html \
  --kind cv --register --json
```

- It renders the template with a fictional candidate (Jordan Example), then runs `verify_pdf.py` and
  `verify_layout.py` on the PDF when a PDF engine exists.
- Exit 0: `pass`; with `--register` it writes `<name>.gate.json` beside the template.
- Exit 1: `fail [check] message` lines and a JSON report on `--json`; no record is written, and an old record is
  removed. Exit 2: usage error (no kind, file missing).
- `--no-smoke` runs only the static checks: useful while drafting, never enough to register.
- `--keep-smoke <dir>` keeps the fixture render to read the reading order yourself.

## Step 3: render with it

```bash
python3 "$HERMES_HOME/skills/squad-jobs/rendering-cv/scripts/render_cv.py" --content ... --output ... \
  --project <P> --template <name> --json
```

- Lookup order: `--templates-dir`, else `<P>/templates`, then the shipped set. A project template name that does not
  pass its gate is refused with exit 2, not silently replaced by a shipped template.
- The report carries `template_source` (`project` or `shipped`) and `template_gate`. Quote them in the card.
- A registered `pdf: skipped` template renders with a warning on every run until it is registered again with a PDF
  engine present.

## What the gate checks

| Check | Fails when |
|---|---|
| name, manifest | The name is not kebab-case; the manifest is not a JSON object, has a bad `kind` or `page_limit`, or disagrees with the kind being checked |
| placeholders | A required slot is missing or repeated, or an unknown `{{...}}` appears |
| no_tables | A `<table>` element, or CSS that lays out with `display: table` |
| images | `<img>`, `<svg>`, `<picture>`, `<canvas>`, `<object>`, `<embed>`, `<iframe>`, `<video>`, `<audio>` |
| scripts | A `<script>` element, an `on*` handler, or a `javascript:` URL |
| external_requests | A `http(s)://` or protocol-relative URL in `src`, `href`, `url()` or `@import` |
| local_references | A relative file reference: the output folder does not hold it |
| multi_column | Row flex, a grid with more than one column track, `column-count`, or a two-column `grid-template-areas` |
| float_layout | `float: left` or `right` |
| absolute_position | `position: absolute` or `fixed` |
| generated_text | A `content:` value that is not empty |
| background_images | A `url()` in a background, list style, border image or mask |
| contact_text | The contact or links line is hidden, or an icon stands alone with no text |
| body_font_size | Body text under 9pt, or metadata lines (contact, dates, links, references) under 7pt |
| render_smoke | `render_cv.py` refuses the template, crashes, or reports a defect other than a missing engine or python-docx |
| pdf_text | `verify_pdf.py` fails: the name, email and phone are not text in the PDF, or a date range breaks |
| layout | `verify_layout.py` finds a hole, an early page end, a thin last page, a stranded heading or an empty page |

Warnings do not fail the gate: no manifest, a name that shadows a shipped template, unknown manifest keys, and an
email address written into the template (personal details belong in `contact.yaml`).

## When a check fails

1. Read the message. The fix is in the HTML: restructure the layout, move the contact line out of an icon, or embed
   a font as a `data:` URL. Never change a fact in `cv_content.json` to get past a template check.
2. Re-run the gate. Three attempts in total; then report the reason in the card and stop. Do not register it.
3. A PDF gate that is skipped (no engine, or no Poppler) is not a pass. Write the install line in the card:
   `pip install weasyprint` or Google Chrome, and `brew install poppler` on macOS.
