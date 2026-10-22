# Reading the own LinkedIn profile

Selectors and snippets measured on a real signed-in profile (2026-10-22, headless Chromium 145). Everything here is
read-only: no click that saves, no field typed into, no tab closed. LinkedIn ships hashed class names that change
between builds, so every selector below uses a stable attribute (`componentkey`, `id`, `aria-label`, element order) or
the page's own text.

## Contents

- The browser in one tab
- The own-profile guard
- The profile card: name, headline, location, About
- The details pages: experience, education, skills
- The edit forms and their language tabs
- Measured against unverified

## The browser in one tab

`browser_exec` runs with `shared_browser: true`: one signed-in headless Chromium on `127.0.0.1:9333`. A plugin gives
each run one tab and closes it at the end, so `new_tab()` navigates that tab. Navigate in place with `goto_url()`,
never close a tab, never open a window, never type a credential. A sign-in page, a checkpoint, a CAPTCHA or a
restriction notice ends the run: `kanban_block(kind="needs_input", reason="LinkedIn is not signed in for jobs-writer:
see the jobs README, LinkedIn session")`.

Cards below the fold mount only while they are near the viewport, and unmount when they leave it. The page scrolls
`main` (`main#workspace`), not the window: `window.scrollTo` does nothing and `document.scrollHeight` stays ~457.
Scroll `main` in ~600 px steps and extract immediately after the step that mounted the card, with no scroll back to
the top.

## The own-profile guard

Run `own_profile.py check <url> --own <slug|me>` before every navigation; it exits 0 only for `/in/me/`, the recorded
own `/in/<slug>/`, its `/details/<section>/` pages and its `/edit/` forms, and only for an `https` address on
`www.linkedin.com` or a two-letter locale subdomain (`es.linkedin.com`). The path is percent-decoded and its dot
segments resolved before the match, so `/in/<slug>/edit/../../../in/other/` is judged as `/in/other/`; a `contact-info`
form or an `overlay` under `/edit/` is refused. `own_profile.py record <url> --project <P>` stores the slug `/in/me/`
redirected to, and only accepts an https LinkedIn URL LinkedIn marked `isSelfProfile=true` or one that repeats the
stored slug.

## The profile card: name, headline, location, About

`https://www.linkedin.com/in/me/` redirects to `https://www.linkedin.com/in/<slug>/?isSelfProfile=true`. Card names
are `com.linkedin.sdui.profile.card.ref<memberRef><CardName>`; the `memberRef` differs per person, so match the
suffix: `[componentkey$="Topcard"]`, `[componentkey$="About"]`, `[componentkey$="Skills"]`.

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
# /in/<slug>/details/experience/  -> groups of roles, one group per company
js("""(() => {
  const lines = (el) => (el.innerText || '').split('\\n').map(t => t.trim()).filter(Boolean);
  const sec = document.querySelector('[componentkey$="ExperienceDetailsSection"]');
  if (!sec) return {found: false, groups: []};
  return {found: true, groups: [...sec.querySelectorAll('[componentkey^="entity-collection-item-"]')].map(g => ({
    all: lines(g),
    company: ([...g.querySelectorAll('a[href*="/company/"]')].map(a => (a.innerText || '').trim())
              .find(Boolean) || '').split('\\n')[0],
    roles: [...g.querySelectorAll('ul > li')].map(li => lines(li))}))};
})()""")
```

Each role's lines are `title`, `dates` (`Jun 2026 - Present · 5 mos`), then one location line or a `Skills: …` line.
The group's lines are the company, `Full-time · 1 yr 7 mos`, and a company location.

```python
# /in/<slug>/details/education/
js("""(() => {
  const lines = (el) => (el.innerText || '').split('\\n').map(t => t.trim()).filter(Boolean);
  const sec = document.querySelector('[componentkey$="EducationDetailsSection"]');
  if (!sec) return {found: false, items: []};
  return {found: true, items: [...sec.querySelectorAll('[componentkey^="entity-collection-item-"]')].map(lines)};
})()""")

# /in/<slug>/details/skills/
js("""(() => {
  const items = [...document.querySelectorAll('[componentkey^="entity-collection-item-"]')]
    .map(g => (g.innerText || '').split('\\n').map(t => t.trim()).filter(Boolean));
  return {found: items.length > 0, count: items.length, items: items.map(a => a[0] || '')};
})()""")
```

Per-skill edit links sit on the same page: `a[aria-label="Edit <skill> skill"]`, href
`/in/<slug>/details/skills/edit/forms/<id>/`; the add link is `/in/<slug>/skills/edit/forms/new/`.

## The edit forms and their language tabs

| Field | Where | The control |
|---|---|---|
| Headline | `/in/<slug>/edit/intro/` | `div[contenteditable="true"][role="textbox"]` (a TipTap editor), one `<p>` inside |
| About | `/in/<slug>/edit/forms/summary/new/` | `div[contenteditable="true"][role="textbox"]`, counter `1,353/2,600` beside it |
| Experience | `/in/<slug>/details/experience/edit/forms/<id>/` | `div[contenteditable="true"][aria-label="Description, maximum 2,000 characters"]`, counter `0/2,000` |

Save is a `button` whose text is `Save`. A form opens in the primary language; `nav a` holds one link per language
(`?language=en&country=US`) and clicking it swaps the field's text: the intro form gave 163 characters in Spanish and
163 in English, the About form 1,379 in Spanish and 1,500 in English. So a field's text depends on the tab: read the
tab before typing, and type only into the tab whose text equals the captured text.

The About counter is the only counter the profile shows; the headline field shows none, so its 220-character limit is
enforced by `check_profile_copy.py`, not read from the page.

## Measured against unverified

Measured: the `/in/me/` redirect and its `isSelfProfile=true` marker; the four card suffixes and the three details
sections; name, headline, location and About across a two-paragraph About with `… more`; 3 experience groups and 6
roles with company, employment, dates, location and a `Skills: …` line; 3 education items; 36 skills after scrolling;
the three edit forms, their controls, the `Save` button, the About counter and the language-tab URLs.

Unverified:

- A role description on the *displayed* page: no role on the measured profile has one, so `parse_profile.py` treats
  the lines after the location and the `Skills: …` line as the description.
- The experience edit form prefilled: `/details/experience/edit/forms/<id>/` opened with `Job title*` empty on the
  measured profile, so the writer checks the prefill and stops instead of typing into a blank form.
- A `Featured` card: absent on the measured profile. `parse_profile.py` keeps `featured` empty.
- A public-profile URL edit, Open to Work visibility and any setting: never changed by this skill.
