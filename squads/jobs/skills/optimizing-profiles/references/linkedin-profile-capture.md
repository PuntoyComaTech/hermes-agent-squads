# Reading the own LinkedIn profile

Selectors and snippets measured on a real signed-in profile (reads 2026-10-22, form writes 2026-10-25, headless
Chromium). The capture snippets only read; every write is a `profile_form.py` step (Writing, below). LinkedIn ships
hashed class names that change between builds, so every selector uses a stable attribute (`componentkey`, `id`,
`aria-label`, placeholder, element order) or the page's own text.

## Contents

- The browser in one tab
- The own-profile guard
- The profile card: name, headline, location, About
- The details pages: experience, education, skills
- The edit forms and their language tabs
- Profile languages and one capture per language
- Dialog forms: add skill, add language
- Writing: profile_form.py
- Measured against unverified

## The browser in one tab

`browser_exec` runs with `shared_browser: true` (one signed-in headless Chromium on `127.0.0.1:9333`, one tab per run,
closed at the end): navigate in place with `goto_url()`, never close a tab or open a window, never type a credential. A
sign-in page, checkpoint, CAPTCHA or restriction notice ends the run: `kanban_block(kind="needs_input",
reason="LinkedIn is not signed in for jobs-writer: see the jobs README, LinkedIn session")`.

Cards below the fold mount only near the viewport. The page scrolls `main` (`main#workspace`), not the window: scroll
`main` in ~600 px steps and extract right after the step that mounted the card, with no scroll back to the top.

## The own-profile guard

Run `own_profile.py check <url> --own <slug|me>` before every navigation; it exits 0 only for `/in/me/`, the recorded
own `/in/<slug>/`, its `/details/<section>/` pages, the experience, education and skills forms under them, and the
intro, summary and position forms under `/edit/`, on `https` `www.linkedin.com` or a two-letter locale subdomain. The
path is percent-decoded and its dot segments resolved first, so `/in/<slug>/edit/../../../in/other/` is judged as
`/in/other/`. The languages forms pass too. Contact info, overlays, the photo, banner and public-URL forms, Featured,
and every `next-action` prompt LinkedIn opens after a Save are refused. `own_profile.py record <url> --project <P>` stores the slug `/in/me/`
redirected to, and only accepts a URL LinkedIn marked `isSelfProfile=true` or one that repeats the stored slug.

## The profile card: name, headline, location, About

`/in/me/` redirects to `/in/<slug>/?isSelfProfile=true`. Card keys end in the card name (the `memberRef` before it
differs per person): `[componentkey$="Topcard"]`, `[componentkey$="About"]`, `[componentkey$="Skills"]`.

| Field | Selector |
|---|---|
| Name | `[componentkey$="Topcard"] h2` |
| Headline | the first `p` inside the Topcard |
| Location | the `p` before the `Contact info` paragraph, skipping the `·` separator |
| About | the `p` elements of `[componentkey$="About"]`, after clicking the `… more` button in that card |
| Skills count | the `Skills (36)` heading of `[componentkey$="Skills"]`, or the item count on `/details/skills/` |

Scroll, then extract (two calls: the lazy cards need the turn to settle):

```python
js("""(() => { const m = document.querySelector('main'); m.scrollTop += 600;
  const a = document.querySelector('[componentkey$="About"]');
  return !!(a && (a.innerText || '').length > 60); })()""")          # repeat until true, 2 s apart, 14 tries
js("""(() => { const a = document.querySelector('[componentkey$="About"]');
  const b = [...a.querySelectorAll('button')].find(x => /more/i.test(x.innerText || ''));
  if (b) b.click(); return b ? 'clicked' : 'no more'; })()""")
```

```python
# name, headline, location, about
js("""(() => {
  const card = (s) => document.querySelector('[componentkey$="' + s + '"]');
  const txt = (el) => el ? (el.innerText || '').trim() : '';
  const top = card('Topcard');
  let name = '', headline = '', place = '';
  if (top) {
    name = txt(top.querySelector('h2'));
    const ps = [...top.querySelectorAll('p')].filter(p => (p.innerText || '').trim());
    headline = ps.length ? txt(ps[0]) : '';
    const i = ps.findIndex(p => /^(contact info|informaci[oó]n de contacto)$/i.test(txt(p)));
    if (i > 0) for (let k = i - 1; k >= 0; k--) { const t = txt(ps[k]); if (t && t !== '·') { place = t; break; } }
  }
  const about = card('About') ? [...card('About').querySelectorAll('p')]
      .map(p => (p.innerText || '').trim()).filter(t => t && !/^(…|\.\.\.)\s*more$/i.test(t)).join('\\n\\n') : '';
  return {url: window.location.href, name, headline, location: place, about};
})()""")
```

## The details pages: experience, education, skills

Section containers: `[componentkey$="ExperienceDetailsSection"]`, `[componentkey$="EducationDetailsSection"]`;
skills use no section container. Items are `[componentkey^="entity-collection-item-"]` (the hash may be negative:
`entity-collection-item--4e58e422`). Scroll each page until the item count stops growing: experience showed 3 groups
over 6 roles, education 3 items, skills 10 items at load and all 36 after scrolling.

```python
# /in/<slug>/details/experience/  -> groups of roles, one group per company; each keeps its edit-form URL
js("""(() => {
  const lines = (el) => (el.innerText || '').split('\\n').map(t => t.trim()).filter(Boolean);
  const edit = (el) => ([...el.querySelectorAll('a')].map(a => a.href).find(h => /\\/edit\\/forms\\/\\d+/.test(h)) || '');
  const sec = document.querySelector('[componentkey$="ExperienceDetailsSection"]');
  if (!sec) return {found: false, groups: []};
  return {found: true, groups: [...sec.querySelectorAll('[componentkey^="entity-collection-item-"]')].map(g => ({
    all: lines(g), edit: edit(g),
    company: ([...g.querySelectorAll('a[href*="/company/"]')].map(a => (a.innerText || '').trim())
              .find(Boolean) || '').split('\\n')[0],
    roles: [...g.querySelectorAll('ul > li')].map(li => ({lines: lines(li), edit: edit(li)}))}))};
})()""")
```

A role's lines: `title`, `dates`, then a location or a skills line; a group's: company, `Full-time · 1 yr 7 mos`, a
location. A one-role company has no `ul > li` (`title`, `Company · Employment`, `dates`): `parse_profile.py` reads
it as one role, so pass the groups unchanged. The skills line (`Skills: A, B, +3 skills`, or `A, B and +1 skill`)
hides all but two: pass each position form's `page.ticked_skills()` as `parse_profile.py --role-skills`.

```python
# /in/<slug>/details/education/
js("""(() => {
  const lines = (el) => (el.innerText || '').split('\\n').map(t => t.trim()).filter(Boolean);
  const edit = (el) => ([...el.querySelectorAll('a')].map(a => a.href).find(h => /\\/edit\\/forms\\/\\d+/.test(h)) || '');
  const sec = document.querySelector('[componentkey$="EducationDetailsSection"]');
  if (!sec) return {found: false, items: []};
  return {found: true, items: [...sec.querySelectorAll('[componentkey^="entity-collection-item-"]')]
    .map(i => ({lines: lines(i), edit: edit(i)}))};
})()""")

# /in/<slug>/details/skills/
js("""(() => {
  const items = [...document.querySelectorAll('[componentkey^="entity-collection-item-"]')]
    .map(g => (g.innerText || '').split('\\n').map(t => t.trim()).filter(Boolean));
  return {found: items.length > 0, count: items.length, items: items.map(a => a[0] || '')};
})()""")
```
Per-skill edit links: `a[aria-label="Edit <skill> skill"]` (`/details/skills/edit/forms/<id>/`); add: `.../forms/new/`.
## The edit forms and their language tabs

| Field | Where | The control |
|---|---|---|
| Headline | `/in/<slug>/edit/intro/` | `div[contenteditable="true"][role="textbox"]` (a TipTap editor), one `<p>` inside |
| About | `/in/<slug>/edit/forms/summary/new/` | `div[contenteditable="true"][role="textbox"]`, counter `1,353/2,600` beside it |
| Experience | `/in/<slug>/details/experience/edit/forms/<id>/` | `div[contenteditable="true"][aria-label="Description, maximum 2,000 characters"]`, counter `0/2,000` |

The position form (`/details/experience/edit/forms/<id>/` redirects to `/edit/forms/position/<id>`) shows, in the
primary tab only, inputs by placeholder (`Role title`, `Organization name`, `City, region, or Remote`), the location
type and employment type selects, the box `I am currently working in this role` (ticked hides the end selects), the
month/year selects, the description and the role's skill checkboxes with `Add skill` (input `Skill (ex: Project
Management)`, suggestions as `role="button"`). A secondary tab holds only the description, as a `textarea`. "Add
position" (`/details/experience/edit/forms/new/`) opens with the current-role box ticked and a box `End current position
as of now - <role>`. The education form holds `School*`, `Degree`, `Field of study`, the date selects and a
`Description, maximum 1,000 characters` textarea. Each form has a `Notify network` switch (off) and `Delete`; the
position dialog reads only "Are you sure you want to delete this role?" (no entry name: the form is the proof), the
skill dialog names the skill. The pinned top skills are edited in the About form (`/edit/forms/summary/new/`,
section "Show your top skills": one `button[aria-label="Remove <skill> from list"]` per pin, "Add skill" opens the
`Skill (ex: Project Management)` typeahead with `[role=option]` items, 5 at most, kept in the order added); the
top-skills overlay only displays them. A skill is picked from LinkedIn's taxonomy: a name the picker lacks ("Workers", "AI") cannot be
added, so draft skills with names it offers ("Cloudflare", "Generative AI").

Save is a `button` whose text is `Save`. A form opens in the primary language; `nav a` holds one link per language
(`?language=en&country=US`) and clicking it swaps the field's text: the intro form gave 163 characters in Spanish and
163 in English, the About form 1,379 in Spanish and 1,500 in English. So a field's text depends on the tab: read the
tab before typing, and type only into the tab whose text equals the captured text. The headline shows no counter:
its 220-character limit is enforced by `check_profile_copy.py`.

## Profile languages and one capture per language

`details/education/` (and the other details pages) carry a card whose `componentkey` ends in `SupportedLocales`: its
lines are `Profile language`, then one line per language, the primary first (`Español`, `English`). Add them to the
capture as `profile_languages`. Every edit form shows the same tabs: `Spanish (Primary profile)` and `English`
(`?language=en&country=US`).

The displayed page mixes languages: with the browser in English, the headline and About showed the English version
while the role descriptions showed the Spanish one. So the page is the structure (roles, schools, skills, edit ids)
and the forms are the text: for each language, open each field's form in that tab and read its control (Headline,
About, each role's Description, each school's Degree, Field of study and Description). Write the capture with
`"language": "<code>"` and parse it into `current.<code>.json`. Reading a form is not editing it: close it with
`Escape`, never with `Save`. An empty secondary tab shows the primary text until it is written. The About card's
last lines (`Top skills`, then the pins) are not About text: `parse_profile.py` moves them to `top_skills`.

## Dialog forms: add skill, add language

Measured 2026-10-26: `/in/<slug>/skills/edit/forms/new/` and `/details/languages/edit/forms/new/` open an HTML
`<dialog>` holding `Skill*` or `Language*` (an `<input>` with no `type`), for languages a proficiency select
(Elementary / Limited working / Professional working / Full professional / Native or bilingual), and Save in its
footer; selects outside it (a video player's captions) are not the form. `/details/languages/` lists name, then level.

## Writing: profile_form.py

Inside `browser_exec`, load it from `$T` (`profile_form.py --help`), make `page = pf.Page(js, cdp, own=<slug>)` and
run the whole plan with `pf.apply_all(page, steps, <state file>)`: it paces the saves and stops on a checkpoint. Each
step navigates to the address the guard rebuilt, checks where it landed (guard again, and the form is there), proves
the form shows the entry the row names, sets only the step's values, reads them back, and saves; a Save counts only
when the form closes. It returns `applied`, `refused` (nothing typed or saved) or `failed`. Measured 2026-10-25:

- A new position saved with the current-role box ticked became the current job, and LinkedIn replaced the headline
  with "<title> at <company>". The step clears the box and sets the end selects before Save.
- Typing after a Range selection appended to the old headline; the step selects with the editor's own selectAll and
  types only after the whole old text is selected, then compares the field with the approved text before Save.
- After Save LinkedIn lands on `/edit/forms/next-action/...` (share, people you may know, Premium): refused by the
  guard. A Save is refused while `Notify network` is on or a box the step did not set is ticked, in any language.
- A skill is added and removed one per Save; the pins are set last on the About form, its text unchanged.

## Measured against unverified

Measured: the `/in/me/` redirect, card suffixes, details sections, 71 skills, and the intro, summary (with its pins),
position, education, skill and language forms. Unverified: a `Featured` card and every account setting (never opened).
