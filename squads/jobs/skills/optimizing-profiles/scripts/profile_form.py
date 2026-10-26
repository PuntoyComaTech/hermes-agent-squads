#!/usr/bin/env python3
"""Plans and performs the writes of an approved LinkedIn profile change, one form at a time.

Two halves. `plan` is pure: it reads the approved file and the captures and prints the ordered steps (which form, which
language tab, what the form must show before anything is typed, what to write). The `Page` class does the browser
part inside `browser_exec`, with the harness's own `js` and `cdp`; every method reads the form first, refuses on any
mismatch, and returns what it did, so the writer never improvises a selector, a click or a Save.

Usage:
  profile_form.py plan APPROVED.json --current current.json [current.en.json ...] --phase structure|text [--json]

  # inside browser_exec (the harness defines js and cdp):
  import importlib.util, os
  spec = importlib.util.spec_from_file_location("profile_form", os.path.expandvars(
      "$HERMES_HOME/skills/squad-jobs/optimizing-profiles/scripts/profile_form.py"))
  pf = importlib.util.module_from_spec(spec); spec.loader.exec_module(pf)
  page = pf.Page(js, cdp, own="<slug>")
  steps = json.load(open("<plan.json>"))      # the output of `plan ... --json`
  out = pf.apply_all(page, steps, "<project>/profiles/apply-state.json")   # paced, resumable

`apply_all` runs the steps with a person's rhythm: 25-70 s between saves, a 3-6 min break every 6 saves, words typed
a few at a time, at most 40 saves a day. It returns `continue` before the 30-minute browser_exec limit (call it again
with the same state file), `paused` at the daily cap, and `stopped` the moment LinkedIn shows a sign-in, checkpoint,
CAPTCHA or restriction page: nothing more is opened. It never hides automation (no fingerprint or user-agent trick).
`page.run(step)` performs one step alone; returns {"result": "applied" | "refused" | "failed", ...}.

Phases: `structure` first (titles, dates, a new position or school, deletions), then re-capture the profile in every
language, then `text` (headline, About, descriptions, role skills, skills, then the top-skill pins). A text step for a role that only exists
after the structure phase cannot be planned from the old capture: that is why the phases are separate.

`plan` exits 0 with the steps, 1 when a structure step is refused (an entry the capture lacks or holds twice, a date
the form cannot take; the step is listed with `"result": "refused"` and its reason; text-phase refusals are listed the
same way but exit 0), 2 on a usage error. `Page.run` never presses Save after a mismatch, never confirms a delete
unless the open form shows the entry the row names, and never saves a form whose "notify network" switch is on or
whose "end current position" box is ticked.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

MONTH_NAMES = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
               "november", "december"]
SHARED = ("skills", "top_skills")
MAX_REMOVALS = 10
MAX_PINS = 5
# LinkedIn's language proficiency options, as the form lists them (measured 2026-10-26), lower-case
PROFICIENCY = {"elementary proficiency", "limited working proficiency", "professional working proficiency",
               "full professional proficiency", "native or bilingual proficiency"}


class UsageError(ValueError):
    pass


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def date_parts(token) -> tuple[str, str] | None:
    """'Oct 2023' -> ('10', '2023'); '2023' -> ('', '2023'); 'Present' -> None (the current-role box)."""
    import profile_diff  # noqa: E402 - the sibling script holds the one date grammar
    parsed = profile_diff.date_token(token)
    if parsed is None:
        raise UsageError(f"{token!r} is not a date: use 'Oct 2023', '2023' or 'Present'")
    if parsed == ("present",):
        return None
    year, month = parsed
    return (str(month) if month else "", str(year))


# --- plan -------------------------------------------------------------------------------------------------------------

def matches(rows, **want) -> list[dict]:
    return [row for row in rows or []
            if isinstance(row, dict) and all(norm(row.get(k)).lower() == norm(v).lower() for k, v in want.items())]


def find(rows, **want):
    found = matches(rows, **want)
    return found[0] if found else None


def one(found: list[dict], what: str) -> tuple[dict | None, str]:
    """The single entry a row names. Two entries with the same name (a rehire, two degrees at one school) cannot be
    told apart by the form either, so the step is refused instead of editing or deleting the first one."""
    if not found:
        return None, f"the capture holds no {what}"
    if len(found) > 1:
        return None, (f"the profile holds {len(found)} entries for {what}: the form cannot prove which one the row "
                      "means, so the user edits it by hand")
    if not found[0].get("edit"):
        return None, f"the capture holds no edit form for {what}"
    return found[0], ""


def date_problem(row: dict, experience: bool) -> str:
    """A date the form cannot take exactly: an unparseable token, 'Present' as a start, or a year without a month on a
    position (its month select would keep the old month and save a date nobody approved)."""
    import profile_diff  # noqa: E402
    for key in ("from", "to"):
        token = row.get(key)
        if not token:
            continue
        parsed = profile_diff.date_token(token)
        if parsed is None:
            return f"`{key}` {token!r} is not a date: use 'Oct 2023', '2023' or 'Present'"
        if parsed == ("present",):
            if key == "from":
                return "`from` cannot be 'Present'"
            continue
        if experience and parsed[1] is None:
            return f"`{key}` {token!r} has no month: a position needs 'Oct 2023', not a year alone"
    return ""


def degree_of(entry: dict) -> str:
    import profile_diff  # noqa: E402
    return profile_diff.degree_of(entry)


def date_parts_safe(token):
    try:
        return date_parts(token)
    except UsageError:
        return None


def own_base(capture: dict) -> str:
    slug = norm(capture.get("own_profile"))
    if not slug:
        raise UsageError("the capture has no own_profile slug: run parse_profile.py on a capture of /in/me/")
    return f"https://www.linkedin.com/in/{slug}/"


def structure_steps(rows, current: dict, texts: dict | None = None) -> list[dict]:
    """One step per form: rows that edit the same entry (a new title and its dates) share one open and one Save.

    A row may name an entry by the title an earlier row gives it (`experience_title` with `was`), so renames are
    resolved first. A created position takes its primary-language description from the approved text rows, and its
    end date is always set before Save: a position saved without one is saved as the current job, and LinkedIn then
    replaces the headline with "<title> at <company>".
    """
    import profile_diff  # noqa: E402
    base, steps, texts = own_base(current), {}, texts or {}
    primary = current.get("primary_language") or current.get("language") or ""
    rows = list(rows or [])
    if not all(isinstance(r, dict) for r in rows):
        raise UsageError("every structure row must be a JSON object")
    renamed = {(norm(r.get("company")).lower(), norm(r.get("title")).lower()): norm(r.get("was"))
               for r in rows if r.get("kind") == "experience_title" and r.get("was")}
    headline_approved = any(field == "headline" and lang in ("", primary[:2]) for field, lang in texts)

    def group(entry, fallback):
        # rows that edit one entry share one form and one Save, whatever name each row used for it
        key = ("form", entry["edit"]) if entry else fallback
        step = steps.setdefault(key, {"phase": "structure", "kinds": [], "rows": [], "language": primary})
        step["kinds"].append(kind)
        step["rows"].append(row)
        return step

    for row in rows:
        kind = str(row.get("kind") or "")
        company, title, school = norm(row.get("company")), norm(row.get("title")), norm(row.get("institution"))
        bad_date = date_problem(row, kind.startswith("experience_"))
        if kind in ("experience_title", "experience_dates", "experience_delete"):
            old = renamed.get((company.lower(), title.lower()), title)
            entry, why = one(matches(current.get("experience"), company=company, title=old), f"{old!r} at {company!r}")
            step = group(entry, ("experience", company.lower(), old.lower()))
            why = why or bad_date
            if not why and kind == "experience_title" and not title:
                why = "the rename names no new title"
            if not why and kind == "experience_dates" and not (row.get("from") or row.get("to")):
                why = "the dates row names no date"
            if why or entry is None or step.get("result") == "refused":
                step.update(result="refused", reason=step.get("reason") or why)
                continue
            step.update(url=entry["edit"], expect={"title": entry["title"], "company": company})
            if kind == "experience_delete":
                step["action"] = "delete"
                continue
            step.setdefault("action", "position")
            step.setdefault("set", {})
            if kind == "experience_title":
                step["set"]["title"] = title
            else:
                step["set"].update({k: row[k] for k in ("from", "to") if row.get(k)})
        elif kind == "experience_create":
            desc = texts.get((f"experience:{company}:{title}", primary))
            step = steps[("create", company.lower(), title.lower())] = {
                "phase": "structure", "kinds": [kind], "rows": [row], "language": primary, "action": "position",
                "url": base + "details/experience/edit/forms/new/", "expect": {"new": True},
                "set": {**{k: row[k] for k in ("title", "company", "from", "to", "employment", "location")
                           if row.get(k)}, **({"description": desc} if desc else {})}}
            why = bad_date or ("" if title and company else "a new position needs a title and a company")
            if not why and not row.get("to"):
                why = ("a new position needs `to` (an end date or 'Present'): saved without one it becomes the "
                       "current job and LinkedIn rewrites the headline")
            if not why and profile_diff.date_token(row["to"]) == ("present",) and not headline_approved:
                why = ("a new current position makes LinkedIn rewrite the headline to '<title> at <company>': "
                       "approve the headline in the same file, or give the position an end date")
            if not why and matches(current.get("experience"), company=company, title=title):
                why = "the profile already holds this position: approve a title or dates row for it instead"
            if why:
                step.update(result="refused", reason=why)
        elif kind in ("education_title", "education_dates", "education_delete"):
            # two degrees at one school: the row's `was` (a rename) or `degree` names which one
            which = norm(row.get("was") if kind == "education_title" else row.get("degree"))
            found = matches(current.get("education"), institution=school)
            if which:
                found = [e for e in found if degree_of(e).lower() == which.lower()]
            entry, why = one(found, repr(school) + (f" ({which})" if which else ""))
            step = group(entry, ("education", school.lower(), which.lower()))
            why = why or bad_date
            if not why and kind == "education_title" and not title:
                why = "the rename names no new degree"
            if not why and kind == "education_dates" and not (row.get("from") or row.get("to")):
                why = "the dates row names no date"
            if why or entry is None or step.get("result") == "refused":
                step.update(result="refused", reason=step.get("reason") or why)
                continue
            step.update(url=entry["edit"], expect={"school": entry["institution"]})
            if kind == "education_delete":
                step["action"] = "delete"
                continue
            step.setdefault("action", "education")
            step.setdefault("set", {})
            if kind == "education_title":
                step["set"]["degree"] = title
            else:
                step["set"].update({k: row[k] for k in ("from", "to") if row.get(k)})
        elif kind == "language_create":
            name, level = norm(row.get("language")), norm(row.get("proficiency"))
            step = steps[("create-language", name.lower())] = {
                "phase": "structure", "kinds": [kind], "rows": [row], "language": primary, "action": "language",
                "url": base + "details/languages/edit/forms/new/", "expect": {"new": True},
                "set": {"language": name, **({"proficiency": level} if level else {})}}
            why = "" if name else "a new language needs its `language`"
            if not why and level and level.lower() not in PROFICIENCY:
                why = f"{level!r} is not a LinkedIn proficiency: use one of {', '.join(sorted(PROFICIENCY))}"
            if not why and any(norm(x.get("language")).lower() == name.lower() for x in current.get("languages") or []):
                why = "the profile already lists this language"
            if why:
                step.update(result="refused", reason=why)
        elif kind == "education_create":
            step = steps[("create-school", school.lower(), title.lower())] = {
                "phase": "structure", "kinds": [kind], "rows": [row], "language": primary, "action": "education",
                "url": base + "details/education/edit/forms/new/", "expect": {"new": True},
                "set": {"school": school, **{k: row[k] for k in ("from", "to") if row.get(k)},
                        **({"degree": title} if title else {}), **({"field": row["field"]} if row.get("field") else {})}}
            why = bad_date or ("" if school else "a new school needs its `institution`")
            if why:
                step.update(result="refused", reason=why)
        else:
            raise UsageError(f"unknown structure kind {kind!r}")
    out = []
    for step in steps.values():
        if step.get("action") == "delete" and len(step["kinds"]) > 1:
            step.update(result="refused", reason="the same entry is edited and deleted: approve one of the two")
        step["kind"] = "+".join(step["kinds"])
        out.append(step)
    return out


def text_value(capture: dict, field: str):
    import profile_diff  # noqa: E402
    return profile_diff.value_of(capture, field)


def text_steps(rows, captures: list[dict]) -> list[dict]:
    primary = captures[0]
    base = own_base(primary)
    lang_primary = primary.get("primary_language") or primary.get("language") or ""
    by_lang = {str(c.get("language") or "")[:2]: c for c in captures}
    approved = {(r["field"], str(r.get("language") or "")[:2]): r.get("after") for r in rows}
    steps = []
    for row in rows:
        field, lang = row["field"], str(row.get("language") or "")[:2] or lang_primary
        if field in ("skills", "top_skills") and row.get("language") and lang != lang_primary:
            continue  # skills and their pins are one list for every language: one step
        capture = primary if field in SHARED or field.startswith("role_skills:") else by_lang.get(lang)
        step = {"phase": "text", "field": field, "language": lang, "want": row.get("after")}
        if capture is None:
            steps.append({**step, "result": "refused", "reason": f"no capture in {lang}: re-read that tab first"})
            continue
        if field == "top_skills":
            steps.append(top_skills_step(step, row, rows, capture, base, lang_primary))
            continue
        if field == "skills":
            have = [norm(s) for s in capture.get("skills") or []]
            want = [norm(s) for s in row.get("after") or []]
            low, keep = {s.lower() for s in have}, {w.lower() for w in want}
            # one skill per form and per Save, like a person: new ones first, so the list never shrinks to nothing
            for name in [s for s in want if s.lower() not in low]:
                steps.append({**step, "field": f"skill:{name}", "action": "skill_add", "control": "skills",
                              "language": lang_primary, "skill": name,
                              "url": base + "details/skills/edit/forms/new/"})
            gone = [s for s in have if s.lower() not in keep]
            # a removal deletes the skill's endorsements: only the names the row lists under `remove` go, or, when it
            # lists none, at most MAX_REMOVALS; a longer silent cut (a short `after` against a long profile) is refused
            listed = {norm(s).lower() for s in row.get("remove") or []}
            if listed:
                gone = [s for s in gone if s.lower() in listed]
            for name in gone:
                out = {**step, "field": f"skill:{name}", "action": "skill_remove", "control": "skills",
                       "language": lang_primary, "skill": name, "url": base + "details/skills/"}
                if not want:
                    out.update(result="refused", reason="the approved skills list is empty: nothing is removed")
                elif not listed and len(gone) > MAX_REMOVALS:
                    out.update(result="refused", reason=f"{len(gone)} skills would be removed with their endorsements:"
                                                        " list the ones to remove under the row's `remove`")
                steps.append(out)
            continue
        entry_expect = {}
        if field in ("headline", "about"):
            url = base + ("edit/intro/" if field == "headline" else "edit/forms/summary/new/")
            control = field
        else:
            kind, _, rest = field.partition(":")
            if kind == "education":
                entry, why = one(matches(primary.get("education"), institution=rest), repr(rest))
                control = "education"
                entry_expect = {"school": rest}
            else:
                company, _, title = rest.rpartition(":")
                entry, why = one(matches(primary.get("experience"), company=company, title=title),
                                 f"{title!r} at {company!r}")
                control = "role_skills" if kind == "role_skills" else "description"
                entry_expect = {"title": title, "company": company}
            if entry is None:
                steps.append({**step, "result": "refused", "reason": why + ": re-capture after the structure phase"})
                continue
            url = entry["edit"]
            if control == "role_skills":
                steps.append({**step, "action": "role_skills", "url": url, "language": lang_primary,
                              "expect": entry_expect, "have": [norm(s) for s in entry.get("skills") or []]})
                continue
        before = text_value(capture, field) or ""
        expect = [before]
        if lang != lang_primary and norm(before) == norm(text_value(primary, field)):
            # an empty secondary tab shows the primary text; once the primary is written it shows the new one
            expect.append(approved.get((field, lang_primary)) or "")
        out = {**step, "action": "text", "control": control, "url": url, "expect": expect}
        if entry_expect and lang == lang_primary:   # the secondary tab holds only the description: no names to read
            out["entry"] = entry_expect
        steps.append(out)
    order = {"headline": 0, "about": 1, "description": 2, "education": 3, "role_skills": 4, "skills": 5,
             "top_skills": 6}
    return sorted(steps, key=lambda s: (order.get(s.get("control") or s.get("action") or "", 9),
                                        s["language"] != lang_primary))


def top_skills_step(step: dict, row: dict, rows: list, capture: dict, base: str, primary: str) -> dict:
    """The pins on the About card, in order. They live in the About form's "Show your top skills" section (measured
    2026-10-25; the top-skills overlay only displays them). A pin must be a skill the profile lists after this apply,
    so the pins always agree with the approved skills list: a pin the skills row removes, or one it never had, is
    refused rather than pinned on its own."""
    want = [norm(s) for s in row.get("after") or [] if norm(s)]
    out = {**step, "field": "top_skills", "action": "top_skills", "control": "top_skills", "language": primary,
           "url": base + "edit/forms/summary/new/", "want": want,
           "have": [norm(s) for s in capture.get("top_skills") or []]}
    approved_skills = next((r.get("after") for r in rows if r.get("field") == "skills"), None)
    listed = {norm(s).lower() for s in (approved_skills if approved_skills is not None else capture.get("skills") or [])}
    why = ""
    if not want:
        why = "no top skills approved: the pins are left as they are"
    elif len(want) > MAX_PINS:
        why = f"{len(want)} top skills: LinkedIn pins at most {MAX_PINS}"
    elif len({w.lower() for w in want}) != len(want):
        why = "a top skill is listed twice"
    else:
        missing = [w for w in want if w.lower() not in listed]
        if missing:
            why = (f"{', '.join(missing)} would be pinned but is not in the approved skills list: add it to `skills` "
                   "so the pins and the list agree")
    if why:
        out.update(result="refused", reason=why)
    return out


def plan(approved: dict, captures: list[dict], phase: str) -> list[dict]:
    rows = [r for r in approved.get("fields") or [] if isinstance(r, dict) and r.get("field")]
    if phase == "structure":
        texts = {(r["field"], str(r.get("language") or "")[:2]): r.get("after") for r in rows}
        steps = structure_steps(approved.get("structure") or [], captures[0], texts)
    else:
        steps = text_steps(rows, captures)
    primary = captures[0].get("primary_language") or captures[0].get("language") or ""
    for step in steps:
        step.setdefault("primary", primary)
    return steps


# --- the browser half -------------------------------------------------------------------------------------------------

FORM_JS = r"""
(() => {
  // LinkedIn's add-skill and language forms render Save and one <input> with no type attribute inside an open <dialog>;
  // a field selector that needs type="text" climbs past that dialog and finds no form (measured 2026-10-26)
  const FIELD = 'input[type="text"], input:not([type]), textarea, select, [contenteditable="true"]';
  const saves = [...document.querySelectorAll('button')].filter(b => (b.innerText || '').trim() === 'Save');
  const save = saves.find(b => { const d = b.closest('dialog'); return d && d.open; }) || saves[0];
  if (!save) return null;
  let root = save.parentElement;
  while (root && !root.querySelector(FIELD)) root = root.parentElement;
  return root;
})()
"""

READ_JS = r"""
(() => {
  const root = %s;
  if (!root) return {found: false};
  const label = (el) => {
    const l = el.id ? document.querySelector('label[for="' + el.id + '"]') : null;
    let t = l ? l.innerText : (el.getAttribute('aria-label') || '');
    for (let p = el.parentElement, k = 0; !t && p && k < 4; p = p.parentElement, k++) {
      const s = (p.innerText || '').trim(); if (s && s.length < 90) t = s; }
    return (t || '').trim();
  };
  const texts = [...root.querySelectorAll('input[type="text"], input:not([type])')].map(e => ({
    ph: e.placeholder || '', aria: e.getAttribute('aria-label') || '', value: e.value}));
  const selects = [...root.querySelectorAll('select')].map(s => ({
    value: s.value, kind: [...s.options].some(o => /^january$/i.test((o.text || '').trim())) ? 'month'
      : [...s.options].some(o => /^(19|20)\d\d$/.test((o.text || '').trim())) ? 'year' : 'other'}));
  const boxes = [...root.querySelectorAll('input[type="checkbox"]')].map(c => ({
    label: label(c), checked: c.checked, sw: c.getAttribute('role') === 'switch'}));
  const desc = root.querySelector('[aria-label^="Description, maximum"], textarea[placeholder^="Description"]');
  const head = root.querySelector('div[contenteditable="true"][role="textbox"]');
  return {found: true, texts, selects, boxes,
    description: desc ? (desc.tagName === 'TEXTAREA' ? desc.value : desc.innerText) : null,
    textbox: head ? head.innerText : null,
    buttons: [...root.querySelectorAll('button')].map(b => (b.innerText || '').trim()).filter(Boolean)};
})()
"""

MARK_JS = r"""
(() => {
  const root = %s;
  if (!root) { document.querySelectorAll('[data-pf]').forEach(e => e.removeAttribute('data-pf')); return null; }
  const want = %s;
  let el = null;
  if (want.kind === 'input') {
    el = [...root.querySelectorAll('input[type="text"], input:not([type])')].find(e =>
      new RegExp(want.match, 'i').test((e.placeholder || '') + ' ' + (e.getAttribute('aria-label') || '')));
  } else if (want.kind === 'select') {
    el = [...root.querySelectorAll('select')].filter(s => [...s.options].some(o =>
      new RegExp(want.match, 'i').test((o.text || '').trim())))[want.index || 0];
  } else if (want.kind === 'box') {
    el = [...root.querySelectorAll('input[type="checkbox"]')].find(c => {
      const l = c.id ? document.querySelector('label[for="' + c.id + '"]') : null;
      let t = l ? l.innerText : (c.getAttribute('aria-label') || '');
      for (let p = c.parentElement, k = 0; !t && p && k < 4; p = p.parentElement, k++) {
        const s = (p.innerText || '').trim(); if (s && s.length < 90) t = s; }
      return new RegExp(want.match, 'i').test(t || ''); });
  } else if (want.kind === 'aria') {
    el = [...(root.closest('[role="dialog"]') || root).querySelectorAll('button[aria-label], [role="button"][aria-label]')].find(b =>
      (b.getAttribute('aria-label') || '').trim().toLowerCase() === want.match.toLowerCase());
  } else if (want.kind === 'text') {
    el = root.querySelector(want.match);
  } else if (want.kind === 'button') {
    const scope = want.dialog ? [...document.querySelectorAll('[role="dialog"], [role="alertdialog"]')]
      .filter(d => /delete/i.test(d.innerText || '')).pop() : root;
    el = scope ? [...scope.querySelectorAll('button, [role="button"]')].filter(b =>
      new RegExp(want.match, 'i').test((b.innerText || '').trim())).pop() : null;
  }
  // the old mark goes first: a later click on "the marked element" never lands on the previous one
  document.querySelectorAll('[data-pf]').forEach(e => e.removeAttribute('data-pf'));
  if (!el) return null;
  el.setAttribute('data-pf', '1');
  el.scrollIntoView({block: 'center'});
  return '[data-pf="1"]';
})()
"""

SET_JS = r"""
(() => {
  const e = document.querySelector('[data-pf="1"]');
  if (!e) return null;
  const proto = e.tagName === 'SELECT' ? HTMLSelectElement.prototype
    : e.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  let value = %s;
  if (e.tagName === 'SELECT') {
    const o = [...e.options].find(o => o.value === value || (o.text || '').trim().toLowerCase() === value.toLowerCase());
    if (!o) return {error: 'no option ' + value};
    value = o.value;
  }
  Object.getOwnPropertyDescriptor(proto, 'value').set.call(e, value);
  e.dispatchEvent(new Event('input', {bubbles: true}));
  e.dispatchEvent(new Event('change', {bubbles: true}));
  e.dispatchEvent(new Event('blur', {bubbles: true}));
  return {value: e.value};
})()
"""

DESC_SEL = '[aria-label^="Description, maximum"], textarea[placeholder^="Description"]'
HEAD_SEL = 'div[contenteditable="true"][role="textbox"]'
POSITION = {"title": r"role title|senior product manager|job title|cargo",
            "company": r"organization|microsoft|company|empresa", "location": r"city|region|ciudad|ubicaci"}
SCHOOL = {"school": r"boston university|school|universidad|escuela", "degree": r"bachelor|degree|t[ií]tulo",
          "field": r"business|field of study|disciplina"}
CURRENT_BOX = r"^\s*(?:i am currently working in this role|actualmente trabajo en este cargo)\s*$"
EMPLOYMENT = {"full-time": "Full-time", "part-time": "Part-time", "self-employed": "Self-employed",
              "freelance": "Freelance", "contract": "Contract", "internship": "Internship"}


CHALLENGE_URL = re.compile(r"/(?:checkpoint|authwall|uas/login|login|captcha)\b|/challenge/", re.I)
CHALLENGE_TEXT = re.compile(r"unusual activity|verify (?:that )?you(?:'re| are) (?:a )?human|security verification|"
                            r"your account (?:has been|is) (?:temporarily )?restricted|let'?s do a quick security check|"
                            r"actividad inusual|verificaci[oó]n de seguridad|cuenta (?:ha sido )?restringida", re.I)


class Pacer:
    """The rhythm of a person editing their own profile: one Save, then a pause; a longer break every few saves.

    It spaces the writes out and caps them per day so the run never looks like a burst. It does not hide automation:
    there is no fingerprint, user-agent or webdriver trick anywhere in this skill, and nothing guarantees LinkedIn will
    not notice. A checkpoint or restriction page stops the whole run (`apply_all`).
    """

    def __init__(self, gap=(25.0, 70.0), burst: int = 6, burst_break=(180.0, 360.0), daily_cap: int = 40,
                 sleep=time.sleep, rng=None, clock=time.time):
        import random
        self.gap, self.burst, self.burst_break, self.daily_cap = gap, burst, burst_break, daily_cap
        self.sleep, self.rng, self.clock = sleep, rng or random.Random(), clock

    def between(self, saves_in_session: int) -> float:
        """Seconds to wait after the n-th save of this session."""
        low, high = self.burst_break if self.burst and saves_in_session % self.burst == 0 else self.gap
        seconds = self.rng.uniform(low, high)
        self.sleep(seconds)
        return seconds


class Page:
    """The writer's hands on one LinkedIn form. `js` and `cdp` are the browser_exec helpers.

    `typing` is the per-chunk delay range (seconds) when a rich-text field is typed: words arrive a few at a time, as
    from a keyboard, instead of one paste. Tests pass `pause=0`, which also turns typing delays off.
    """

    def __init__(self, js, cdp, own: str, pause: float = 1.2, typing=(0.04, 0.16), rng=None):
        import random
        self.js, self.cdp, self.own, self.pause = js, cdp, own, pause
        self.typing = typing if pause else None
        self.rng = rng or random.Random()

    # -- primitives
    def wait(self, factor: float = 1.0):
        if self.pause:
            time.sleep(self.pause * factor * self.rng.uniform(0.7, 1.4))

    def type_text(self, text: str):
        """Insert text a few words at a time with short irregular gaps (no gap when typing is off)."""
        if not self.typing:
            self.cdp("Input.insertText", text=text)
            return
        words = re.findall(r"\S+\s*|\s+", text)
        i = 0
        while i < len(words):
            n = self.rng.randint(1, 3)
            self.cdp("Input.insertText", text="".join(words[i:i + n]))
            i += n
            time.sleep(self.rng.uniform(*self.typing))

    def challenge(self) -> str:
        """A sign-in, checkpoint, CAPTCHA or restriction page: the reason, or '' when the page is a normal one."""
        url = self.js("location.href") or ""
        if CHALLENGE_URL.search(url.split("?")[0]):
            return f"LinkedIn showed {url.split('?')[0]}"
        text = self.js("(document.body && document.body.innerText || '').slice(0, 4000)") or ""
        match = CHALLENGE_TEXT.search(text)
        return f"LinkedIn showed '{match.group(0)}'" if match else ""

    def read(self) -> dict:
        return self.js(READ_JS % FORM_JS) or {"found": False}

    def mark(self, **want):
        return self.js(MARK_JS % (FORM_JS, json.dumps(want)))

    def set_value(self, value) -> dict:
        return self.js(SET_JS % json.dumps(str(value))) or {"error": "the control is gone"}

    def click_marked(self) -> bool:
        # a styled checkbox is often a zero-size input under its label: click what the user would click
        box = self.js("""(() => { let e = document.querySelector('[data-pf="1"]'); if (!e) return null;
            let r = e.getBoundingClientRect();
            if (r.width < 2 || r.height < 2) {
              const l = (e.id && document.querySelector('label[for="' + e.id + '"]')) || e.closest('label') || e.parentElement;
              if (l) { l.scrollIntoView({block: 'center'}); r = l.getBoundingClientRect(); }
            }
            return {x: r.x + Math.min(r.width / 2, 12), y: r.y + r.height / 2}; })()""")
        if not box:
            return False
        for kind in ("mousePressed", "mouseReleased"):
            self.cdp("Input.dispatchMouseEvent", type=kind, x=box["x"], y=box["y"], button="left", clickCount=1)
        return True

    def open(self, url: str, language: str = "", primary: str = "", form: bool = True) -> dict:
        """Navigate to a guarded address, then prove where the browser landed: the landing page passes the guard
        too, and (for a form) the form is on it. A redirect elsewhere, an error page or a missing form is refused."""
        import own_profile  # noqa: E402 - the guard runs before every navigation
        verdict = own_profile.check(url, self.own)
        if not verdict.get("allow"):
            return {"result": "refused", "reason": verdict.get("reason"), "url": url}
        before = self.js("location.href")
        self.js("document.querySelectorAll('[data-pf]').forEach(e => e.removeAttribute('data-pf'))")
        self.cdp("Page.navigate", url=verdict.get("url") or url)
        ready = False
        for _ in range(60):
            time.sleep(0.25)
            here = self.js("location.href") or ""
            if here == before and not ready:     # the old page is still up: never read its form as the new one
                ready = self.js("document.readyState") == "complete" and here == verdict.get("url")
                if not ready:
                    continue
            if self.js("document.readyState") != "complete":
                continue
            if not form or self.read().get("found"):
                ready = True
                break
        here = self.js("location.href") or ""
        landed = own_profile.check(here, self.own)
        if not landed.get("allow"):
            return {"result": "refused", "reason": f"the page went to {here.split('?')[0]}: {landed.get('reason')}",
                    "url": url}
        if form and not self.read().get("found"):
            return {"result": "refused", "reason": "the form did not appear: nothing was touched", "url": here}
        if language and primary and language != primary:
            href = self.js("""(() => { const a = [...document.querySelectorAll('nav a')].find(a =>
                /[?&]language=%s(&|$)/.test(a.getAttribute('href') || '')); return a ? a.href : null; })()"""
                           % re.escape(language))
            if not href:
                return {"result": "refused", "reason": f"the form has no {language} tab", "url": url}
            return self.open(href, form=form)
        return {"result": "open", "url": here}

    def guard_switches(self, current_box: bool) -> str:
        """Fail closed: a switch that is on, or any ticked box this form is not meant to carry, blocks the Save.
        `current_box` says whether the current-role box may be ticked (a role the user still holds)."""
        for box in self.read().get("boxes") or []:
            if not box.get("checked"):
                continue
            label = box.get("label") or ""
            if box.get("sw"):
                return "the notify-network switch is on"
            if re.search(r"end current position", label, re.I):
                return "the box that ends the current position is ticked"
            if current_box and self.is_current_box(label):
                continue
            if self.allowed_ticks is not None and norm(label).lower() in self.allowed_ticks:
                continue
            return f"the box {label[:60]!r} is ticked and this step did not set it"
        return ""

    @staticmethod
    def is_current_box(label: str) -> bool:
        return bool(re.match(CURRENT_BOX, label or "", re.I))

    allowed_ticks: set | None = None

    def save(self, current_box: bool = False) -> dict:
        problem = self.guard_switches(current_box)
        if problem:
            return {"result": "refused", "reason": problem + ": nothing was saved"}
        if not self.mark(kind="button", match="^save$"):
            return {"result": "failed", "reason": "no Save button"}
        self.wait()
        self.click_marked()
        closed = False
        for _ in range(48):
            time.sleep(0.25)
            if not self.mark(kind="button", match="^save$"):
                closed = True
                break
        landed = self.js("location.href") or ""
        alerts = self.js("""(() => [...document.querySelectorAll('[role=alert],[aria-live]')]
            .map(x => (x.innerText || '').trim()).filter(t => t && t.length < 200).slice(0, 3))()""") or []
        errors = [a for a in alerts if re.search(r"error|required|invalid|couldn|no se pudo", a, re.I)]
        if errors:
            return {"result": "failed", "reason": "; ".join(errors), "landed": landed}
        if not closed:
            # the form is still open: LinkedIn kept it for a validation message the page does not mark as an alert
            return {"result": "failed", "reason": "the form stayed open after Save: nothing was confirmed saved",
                    "landed": landed}
        # a follow-up prompt (share, people you may know, Premium) is never read or answered
        return {"result": "saved", "landed": landed, "follow_up": "/next-action/" in landed}

    # -- a text control (headline, About, a description)
    def replace_text(self, selector: str, want: str) -> str:
        if not self.mark(kind="text", match=selector):
            return "the control is not on the form"
        tag = self.js("document.querySelector('[data-pf=\"1\"]').tagName")
        if tag in ("TEXTAREA", "INPUT"):
            self.set_value(want)
        else:
            self.click_marked()
            # measured: a Range over the editor's nodes was ignored once and the text was appended; the editor's own
            # selectAll command selects what it holds. Typing starts only once the whole old text is selected.
            # An empty editor has nothing to select: selectAll would then grab the whole page, so it is skipped.
            selected = self.js("""(() => { const e = document.querySelector('[data-pf="1"]'); e.focus();
                const old = e.innerText.replace(/\\s+/g, '');
                if (!old) {   // put the caret inside the empty editor, or the typed text lands nowhere
                  const r = document.createRange(); r.selectNodeContents(e.querySelector('p') || e); r.collapse(true);
                  const s = getSelection(); s.removeAllRanges(); s.addRange(r); return ['', '']; }
                document.execCommand('selectAll');
                const s = getSelection();
                if (!e.contains(s.anchorNode) || s.toString().replace(/\\s+/g, '') !== old) {
                  const r = document.createRange(); r.selectNodeContents(e); s.removeAllRanges(); s.addRange(r); }
                return [s.toString().replace(/\\s+/g, ''), old]; })()""")
            if not selected or selected[0] != selected[1]:
                return "the old text could not be selected whole"
            for i, para in enumerate(str(want).split("\n")):
                if i:
                    for kind in ("keyDown", "keyUp"):
                        self.cdp("Input.dispatchKeyEvent", type=kind, key="Enter", code="Enter",
                                 windowsVirtualKeyCode=13, **({"text": "\r"} if kind == "keyDown" else {}))
                if para:
                    self.type_text(para)
        self.wait(0.5)
        got = self.js("""(() => { const e = document.querySelector('[data-pf="1"]');
            return e ? (e.tagName === 'TEXTAREA' || e.tagName === 'INPUT' ? e.value : e.innerText) : null; })()""")
        return "match" if norm(got) == norm(want) else f"typed text differs: {norm(got)[:120]!r}"

    def text(self, step: dict) -> dict:
        selector = HEAD_SEL if step["control"] in ("headline", "about") else DESC_SEL
        if step.get("entry"):
            problem = self.form_matches(step["entry"])
            if problem:
                return {"result": "refused", "reason": problem}
        form = self.read()
        shown = form.get("textbox") if selector == HEAD_SEL else form.get("description")
        if shown is None:
            return {"result": "refused", "reason": "the control is not on the form"}
        if norm(shown) == norm(step["want"]):
            return {"result": "applied", "note": "the form already holds the approved text"}
        if norm(shown) not in {norm(x) for x in step.get("expect") or [""]}:
            return {"result": "refused", "reason": "the form text is not the captured text: re-capture first",
                    "shown": norm(shown)[:120]}
        typed = self.replace_text(selector, step["want"])
        if typed != "match":
            return {"result": "failed", "reason": typed + ": nothing was saved"}
        return self.finish(self.save(current_box=self.current_ticked()))

    # -- structure forms
    def form_values(self) -> dict:
        values = {t["ph"] + " " + t["aria"]: norm(t["value"]) for t in self.read().get("texts") or []}
        out = {}
        for name, pattern in {**POSITION, **SCHOOL}.items():
            out[name] = next((v for k, v in values.items() if re.search(pattern, k, re.I)), None)
        return out

    def form_matches(self, expect: dict) -> str:
        form = self.read()
        if not form.get("found"):
            return "the form is not on the page"
        got = self.form_values()
        if expect.get("new"):
            # an empty new form has its name fields, all blank; a page without them is not the new form
            names = [got["title"], got["school"]]
            if all(v is None for v in names):
                return "the page shows no title or school field: it is not the new form"
            return "" if not any(names) else "the new form is not empty"
        if "title" in expect:
            if (got["title"] or "").lower() != norm(expect["title"]).lower():
                return f"the form shows the title {got['title']!r}, not {expect['title']!r}"
            if (got["company"] or "").lower() != norm(expect["company"]).lower():
                return f"the form shows the company {got['company']!r}, not {expect['company']!r}"
        if "school" in expect and (got["school"] or "").lower() != norm(expect["school"]).lower():
            return f"the form shows the school {got['school']!r}, not {expect['school']!r}"
        return ""

    def readback(self, values: dict, names: tuple) -> str:
        """After every value is set and before Save: the form must show exactly what the step set."""
        got = self.form_values()
        for key in names:
            if values.get(key) and norm(got.get(key)).lower() != norm(values[key]).lower():
                return f"the {key} field reads {got.get(key)!r} after it was set to {values[key]!r}"
        return ""

    def current_ticked(self) -> bool:
        return any(b.get("checked") and self.is_current_box(b.get("label") or "")
                   for b in self.read().get("boxes") or [])

    def year_selects(self) -> int:
        return sum(1 for s in self.read().get("selects") or [] if s.get("kind") == "year")

    def date_selects(self) -> list:
        """The (month, year) select values in form order: start first, then end."""
        sel = self.read().get("selects") or []
        months = [s["value"] for s in sel if s.get("kind") == "month"]
        years = [s["value"] for s in sel if s.get("kind") == "year"]
        return list(zip(months + [""] * (len(years) - len(months)), years))

    def set_dates(self, start, end) -> str:
        """Start and end selects; an end date first clears the current-role box, which hides the end selects."""
        if end is not None:
            want_current = end == "Present"
            if self.year_selects() < 2 and not want_current:
                if not self.mark(kind="box", match=CURRENT_BOX):
                    return "the end-date selects are hidden and there is no current-role box"
                self.click_marked()
                self.wait(0.6)
                if self.year_selects() < 2:
                    return "the end-date selects did not appear after clearing the current-role box"
            elif want_current and self.year_selects() >= 2:
                if not self.mark(kind="box", match=CURRENT_BOX):
                    return "there is no current-role box to mark the role as present"
                self.click_marked()
                self.wait(0.6)
        wanted = {}
        for index, token in ((0, start), (1, end)):
            if token is None or token == "Present":
                continue
            try:
                parts = date_parts(token)
            except UsageError as exc:
                return str(exc)
            if parts is None:
                continue
            month, year = parts
            if month and not (self.mark(kind="select", match="^january$", index=index)
                              and "error" not in self.set_value(month)):
                return f"no month select for {token}"
            if not (self.mark(kind="select", match="^(19|20)\\d\\d$", index=index)
                    and "error" not in self.set_value(year)):
                return f"no year select for {token}"
            wanted[index] = (month, year)
            self.wait(0.3)
        shown = self.date_selects()
        for index, (month, year) in wanted.items():
            if index >= len(shown) or shown[index][1] != year or (month and shown[index][0] != month):
                return f"the date selects read {shown} after they were set"
        return ""

    def position(self, step: dict) -> dict:
        problem = self.form_matches(step.get("expect") or {})
        if problem:
            return {"result": "refused", "reason": problem}
        values = step.get("set") or {}
        for key in ("title", "company", "location"):
            if values.get(key):
                if not self.mark(kind="input", match=POSITION[key]):
                    return {"result": "failed", "reason": f"no {key} field: open the primary-language tab"}
                if "error" in self.set_value(values[key]):
                    return {"result": "failed", "reason": f"the {key} field took no value: nothing was saved"}
                self.wait(0.4)
        if values.get("employment"):
            label = EMPLOYMENT.get(norm(values["employment"]).lower(), values["employment"])
            if not (self.mark(kind="select", match="^full-time$") and "error" not in self.set_value(label)):
                return {"result": "failed", "reason": f"no employment option {label!r}"}
        if values.get("from") or values.get("to"):
            end = values.get("to")
            try:
                end = "Present" if end and date_parts(end) is None else end
            except UsageError as exc:
                return {"result": "refused", "reason": str(exc)}
            problem = self.set_dates(values.get("from"), end)
            if problem:
                return {"result": "failed", "reason": problem + ": nothing was saved"}
        if values.get("description"):
            typed = self.replace_text(DESC_SEL, values["description"])
            if typed != "match":
                return {"result": "failed", "reason": typed + ": nothing was saved"}
        problem = self.readback(values, ("title", "company", "location"))
        if problem:
            return {"result": "failed", "reason": problem + ": nothing was saved"}
        # the current-role box may stay ticked only on a role that is current and was not given an end date
        keep_current = self.current_ticked() and not (values.get("to") and values.get("to") != "Present"
                                                       and date_parts_safe(values.get("to")) is not None)
        return self.finish(self.save(current_box=keep_current))

    def education(self, step: dict) -> dict:
        problem = self.form_matches(step.get("expect") or {})
        if problem:
            return {"result": "refused", "reason": problem}
        values = step.get("set") or {}
        for key in ("school", "degree", "field"):
            if values.get(key):
                if not self.mark(kind="input", match=SCHOOL[key]):
                    return {"result": "failed", "reason": f"no {key} field: open the primary-language tab"}
                if "error" in self.set_value(values[key]):
                    return {"result": "failed", "reason": f"the {key} field took no value: nothing was saved"}
                self.wait(0.4)
        problem = self.set_dates(values.get("from"), values.get("to")) if (values.get("from") or values.get("to")) \
            else ""
        if problem:
            return {"result": "failed", "reason": problem + ": nothing was saved"}
        problem = self.readback(values, ("school", "degree", "field"))
        if problem:
            return {"result": "failed", "reason": problem + ": nothing was saved"}
        return self.finish(self.save())

    def language(self, step: dict) -> dict:
        """The add-language form: the language name (LinkedIn's suggestion when it offers one) and the proficiency
        select, by its label. Only a new, empty form is filled."""
        values = step.get("set") or {}
        if not self.mark(kind="input", match=r"(^|\s)language\*?$"):
            return {"result": "refused", "reason": "the page has no Language field: it is not the language form"}
        if norm(self.js("(document.querySelector('[data-pf=\"1\"]') || {}).value || ''")):
            return {"result": "refused", "reason": "the language form is not empty"}
        self.set_value(values["language"])
        self.wait(1.2)
        self.pick(values["language"])           # a suggestion with exactly this name, when the field offers one
        self.wait(0.5)
        if values.get("proficiency"):
            if not self.mark(kind="select", match=r"proficiency$"):
                return {"result": "failed", "reason": "no proficiency select: nothing was saved"}
            if "error" in self.set_value(values["proficiency"]):
                return {"result": "failed", "reason": f"the proficiency {values['proficiency']!r} is not an option: "
                                                      "nothing was saved"}
        got = self.js("""(() => { const d = [...document.querySelectorAll('dialog')].find(x => x.open) || document;
            const i = [...d.querySelectorAll('input')].find(e => /^language/i.test(e.getAttribute('aria-label') || ''));
            const s = [...d.querySelectorAll('select')].find(e => [...e.options].some(o => /proficiency$/i.test(o.text)));
            return {language: i ? i.value : null, proficiency: s ? (s.options[s.selectedIndex] || {}).text : null}; })()""")
        if norm((got or {}).get("language")).lower() != norm(values["language"]).lower():
            return {"result": "failed", "reason": f"the form holds the language {(got or {}).get('language')!r}: "
                                                  "nothing was saved"}
        if values.get("proficiency") and norm((got or {}).get("proficiency")).lower() != norm(values["proficiency"]).lower():
            return {"result": "failed", "reason": "the proficiency did not take: nothing was saved"}
        return self.finish(self.save())

    def delete(self, step: dict) -> dict:
        problem = self.form_matches(step.get("expect") or {})
        if problem:
            return {"result": "refused", "reason": problem + ": the entry was not deleted"}
        if not self.mark(kind="button", match="^delete$"):
            return {"result": "failed", "reason": "the form has no Delete button"}
        self.click_marked()
        self.wait()
        # LinkedIn's dialog is generic ("Are you sure you want to delete this role?"); the form above proved the entry
        if not self.mark(kind="button", match="^delete$", dialog=True):
            return {"result": "failed", "reason": "no confirmation dialog appeared"}
        self.click_marked()
        for _ in range(40):
            time.sleep(0.25)
            if not self.mark(kind="button", match="^delete$", dialog=True):
                return {"result": "applied", "landed": self.js("location.href")}
        return {"result": "failed", "reason": "the confirmation dialog stayed open"}

    def role_skills(self, step: dict) -> dict:
        """Tick the approved skills under one role. Only a box whose label is a skill the capture listed under this
        role (or an approved one) is ever unticked; any other ticked box (the current-role box in any language, a
        box this script does not know) is left alone, and Save refuses if one it did not expect is ticked."""
        if step.get("expect"):
            problem = self.form_matches(step["expect"])
            if problem:
                return {"result": "refused", "reason": problem}
        want = [norm(s) for s in step.get("want") or []]
        known = {s.lower() for s in want} | {norm(s).lower() for s in step.get("have") or []}
        boxes = {norm(b["label"]).lower(): b["checked"] for b in self.read().get("boxes") or []
                 if b["label"] and not b.get("sw")}
        current = self.current_ticked()
        changed = []
        for name, checked in boxes.items():
            if checked and name in known and name not in {w.lower() for w in want}:
                if not self.mark(kind="box", match="^" + re.escape(name) + "$"):
                    return {"result": "failed", "reason": f"the box {name!r} could not be found again",
                            "changed": changed}
                self.click_marked()
                changed.append("-" + name)
                self.wait(0.4)
        for skill in want:
            if boxes.get(skill.lower()):
                continue
            if skill.lower() in boxes:
                if not self.mark(kind="box", match="^" + re.escape(skill) + "$"):
                    return {"result": "failed", "reason": f"the box {skill!r} could not be found again",
                            "changed": changed}
                self.click_marked()
            else:
                if not self.mark(kind="input", match=r"^skill \(ex"):
                    if not self.mark(kind="button", match="^add skill$"):
                        return {"result": "failed", "reason": "no Add skill control on the form"}
                    self.click_marked()
                    self.wait()
                    if not self.mark(kind="input", match=r"^skill \(ex"):
                        return {"result": "failed", "reason": "the skill picker did not open"}
                self.set_value(skill)
                self.wait(1.5)
                if not self.pick(skill):
                    return {"result": "failed", "reason": f"LinkedIn offered no skill named {skill!r}",
                            "changed": changed}
            changed.append("+" + skill)
            self.wait(0.6)
        now = {norm(b["label"]).lower() for b in self.read().get("boxes") or [] if b.get("checked")}
        missing = [s for s in want if s.lower() not in now]
        if missing:
            return {"result": "failed", "reason": f"not ticked after the clicks: {missing}", "changed": changed}
        if current != self.current_ticked():
            return {"result": "failed", "reason": "the current-role box changed: nothing was saved", "changed": changed}
        if not changed:
            return {"result": "applied", "note": "the role already shows these skills"}
        before = self.allowed_ticks
        self.allowed_ticks = {s.lower() for s in want} | {n for n, c in boxes.items() if c and n not in known}
        try:
            return self.finish(self.save(current_box=current), changed=changed)
        finally:
            self.allowed_ticks = before

    def pins(self) -> list | None:
        """The pinned top skills in the open About form, in order (each pin has a 'Remove <skill> from list' button);
        None when the form shows no top-skills section."""
        return self.js("""(() => { let root = %s; if (!root) return null;
            root = root.closest('[role="dialog"]') || root;   // measured: the About form is a dialog
            if (!/show your top skills|top skills|aptitudes principales/i.test(root.innerText || '')) return null;
            return [...root.querySelectorAll('button[aria-label], [role="button"][aria-label]')]
              .map(b => /^remove (.+) from list$/i.exec((b.getAttribute('aria-label') || '').trim()))
              .filter(Boolean).map(m => m[1].trim()); })()""" % FORM_JS)

    def pick_option(self, skill: str) -> bool:
        """Click the typeahead option named exactly `skill` (measured: `[role=option]`); nothing else is clicked."""
        return bool(self.js("""(() => { const want = %s.toLowerCase();
            const c = [...document.querySelectorAll('[role="option"]')]
              .filter(x => (x.innerText || '').trim().split('\\n')[0].trim().toLowerCase() === want);
            if (!c.length) return false; c[0].click(); return true; })()""" % json.dumps(skill)))

    def top_skills(self, step: dict) -> dict:
        """Set the About form's pins to `want`, in order, with one Save. The pins that already lead in the right order
        stay; from the first one out of place, every pin is removed and the rest are added in order (LinkedIn keeps
        the order they were added in). The About text is read before and after and must not change."""
        want = [norm(s) for s in step.get("want") or []]
        if not want or len(want) > MAX_PINS:
            return {"result": "refused", "reason": f"the pins must be 1 to {MAX_PINS} skills"}
        have = self.pins()
        if have is None:
            return {"result": "refused", "reason": "the form shows no top-skills section: it is not the About form"}
        if [h.lower() for h in have] == [w.lower() for w in want]:
            return {"result": "applied", "note": "the pins already read in the approved order"}
        about = norm(self.read().get("textbox"))
        keep = 0
        while keep < min(len(have), len(want)) and have[keep].lower() == want[keep].lower():
            keep += 1
        changed = []
        for name in have[keep:]:
            if not self.mark(kind="aria", match=f"remove {name} from list"):
                return {"result": "failed", "reason": f"no remove button for the pin {name!r}: nothing was saved",
                        "changed": changed}
            self.click_marked()
            changed.append("-" + name)
            self.wait(0.6)
        for name in want[keep:]:
            # measured: the typeahead input appears only after "Add skill"; a leftover one is reused
            if self.mark(kind="button", match="^add skill$"):
                self.click_marked()
                self.wait()
            if not self.mark(kind="input", match=r"^skill \(ex"):
                return {"result": "failed", "reason": "no Add skill picker in the top-skills section: nothing was "
                                                      "saved", "changed": changed}
            self.set_value(name)
            self.wait(1.5)
            if not self.pick_option(name):
                return {"result": "failed", "reason": f"LinkedIn offered no skill named {name!r}: nothing was saved",
                        "changed": changed}
            changed.append("+" + name)
            self.wait(0.8)
        now = self.pins() or []
        if [n.lower() for n in now] != [w.lower() for w in want]:
            return {"result": "failed", "reason": f"the pins read {now} after the clicks: nothing was saved",
                    "changed": changed}
        if norm(self.read().get("textbox")) != about:
            return {"result": "failed", "reason": "the About text changed while pinning: nothing was saved",
                    "changed": changed}
        return self.finish(self.save(current_box=False), changed=changed)

    def pick(self, skill: str) -> bool:
        """Click LinkedIn's own suggestion named exactly `skill`; a name the picker does not offer is never typed in."""
        return bool(self.js("""(() => { const want = %s.toLowerCase();
            const c = [...document.querySelectorAll('[role="option"], [role="button"], li')]
              .filter(x => (x.innerText || '').trim().toLowerCase() === want);
            if (!c.length) return false; c[c.length - 1].click(); return true; })()""" % json.dumps(skill)))

    def skill_add(self, step: dict) -> dict:
        """The new-skill form: one text input, LinkedIn's suggestion list, Save. Only a name LinkedIn offers is added:
        a free-typed one is refused by the picker (measured: "Workers", "AI")."""
        if not self.mark(kind="input", match=r"^skill \(ex"):
            return {"result": "refused", "reason": "the add-skill form has no skill field"}
        self.set_value(step["skill"])
        self.wait(1.5)
        if not self.pick(step["skill"]):
            return {"result": "failed", "reason": f"LinkedIn offered no skill named {step['skill']!r}: use a name its "
                                                  "picker offers"}
        self.wait(0.6)
        return self.finish(self.save(current_box=False))

    def skill_remove(self, step: dict) -> dict:
        """Find the skill's own edit link on the skills page (scrolling, as LinkedIn renders ~10 at a time), open its
        form, check the heading names the skill, then 'Delete skill' and confirm in a dialog that names it."""
        name = norm(step["skill"]).lower()
        href = None
        for _ in range(30):
            href = self.js("""(() => { const want = %s;
                const a = [...document.querySelectorAll('a[aria-label]')].find(a =>
                  (a.getAttribute('aria-label') || '').trim().toLowerCase() === ('edit ' + want + ' skill'));
                return a ? a.href : null; })()""" % json.dumps(name))
            if href:
                break
            grew = self.js("""(() => { const m = document.querySelector('main#workspace') || document.scrollingElement;
                const before = m.scrollTop; m.scrollTop = m.scrollHeight; window.scrollTo(0, document.body.scrollHeight);
                return m.scrollTop !== before; })()""")
            self.wait(0.8)
            if not grew:
                break
        if not href:
            return {"result": "refused", "reason": f"the skills page shows no {step['skill']!r} after scrolling"}
        opened = self.open(href, form=False)
        if opened["result"] != "open":
            return opened
        heading = self.js("""(() => { const h = [...document.querySelectorAll('h1, h2')].map(x =>
            (x.innerText || '').trim()).find(t => /^edit /i.test(t)); return h || ''; })()""")
        if norm(heading).lower() != ("edit " + name):
            return {"result": "refused", "reason": f"the form is {heading!r}, not the skill {step['skill']!r}"}
        if not self.mark(kind="button", match="^delete skill$"):
            return {"result": "failed", "reason": "the skill form has no 'Delete skill' button"}
        self.click_marked()
        self.wait()
        dialog = self.js("""(() => { const d = [...document.querySelectorAll('[role="dialog"], [role="alertdialog"]')]
            .filter(d => /delete/i.test(d.innerText || '')).pop(); return d ? d.innerText : ''; })()""") or ""
        if name not in norm(dialog).lower():
            return {"result": "refused", "reason": "the confirmation dialog does not name the skill: not deleted"}
        if not self.mark(kind="button", match="^delete$", dialog=True):
            return {"result": "failed", "reason": "no confirmation dialog appeared"}
        self.click_marked()
        for _ in range(40):
            time.sleep(0.25)
            if not self.mark(kind="button", match="^delete$", dialog=True):
                return {"result": "applied", "landed": self.js("location.href")}
        return {"result": "failed", "reason": "the confirmation dialog stayed open"}

    def finish(self, saved: dict, **extra) -> dict:
        if saved.get("result") != "saved":
            return {**saved, **extra}
        return {"result": "applied", **{k: v for k, v in saved.items() if k != "result"}, **extra}

    def run(self, step: dict) -> dict:
        """One `plan` step, guarded, from opening its form to its Save. A refused step is never opened."""
        if step.get("result") == "refused":
            return step
        action = str(step.get("action") or "")
        handler = {"text": self.text, "position": self.position, "education": self.education,
                   "language": self.language,
                   "delete": self.delete, "role_skills": self.role_skills, "skill_add": self.skill_add,
                   "skill_remove": self.skill_remove, "top_skills": self.top_skills}.get(action)
        if handler is None:
            raise UsageError(f"unknown step action {action!r}")
        # the skills page is a list, not a form: skill_remove opens the skill's own form itself
        opened = self.open(step["url"], step.get("language", ""), step.get("primary", ""),
                           form=action != "skill_remove")
        if opened["result"] != "open":
            return opened
        # boxes ticked when the form opened (a role's skills, a current role) may stay ticked; a new form starts from
        # none, so a box LinkedIn pre-ticks there ("end current position", in any language) blocks the Save
        pre = {norm(b["label"]).lower() for b in self.read().get("boxes") or [] if b.get("checked") and not b.get("sw")}
        expect = step.get("expect")
        self.allowed_ticks = set() if isinstance(expect, dict) and expect.get("new") else pre
        try:
            out = handler(step)
        finally:
            self.allowed_ticks = None
        self.wait(2)
        return {"field": step.get("field") or step.get("kind"), "language": step.get("language"), **out}


def step_key(step: dict) -> str:
    """A stable id for a plan step: the same approved change planned again maps to the same key."""
    import hashlib
    body = {k: v for k, v in step.items() if k not in ("result", "reason", "note")}
    return hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def apply_all(page: Page, steps: list, state_path: str, pacer: Pacer | None = None, budget_s: float = 1200,
              today: str | None = None) -> dict:
    """Run every step of one `plan`, paced, resumable across browser_exec calls.

    A browser_exec call lives at most 30 minutes, and a paced apply takes longer, so progress lives in `state_path`
    (JSON): a step already `applied`, `refused` or `failed` is skipped on the next call (a failed field is not retried
    on the same card), and saves are counted per day against the pacer's daily cap. The default budget leaves room
    for the longest break and one more form inside the 30 minutes. Returns {"status": "done" | "continue" |
    "paused" | "stopped", "results": [...], "remaining": n}: `continue` means call again with the same state file,
    `paused` means today's cap is reached, `stopped` means LinkedIn showed a checkpoint, sign-in or restriction page;
    once stopped, the state file refuses every later call until the user deletes its `stopped` entry.

    The state is keyed by the plan: a new plan (another approved file, or a re-capture) starts a new record, so a
    change approved later is never skipped as already done. A step is recorded as `started` before its form opens:
    if the call dies between the Save and the record, the next call reports it as `unknown` and never repeats it
    (a repeated "Add position" would create the position twice).
    """
    import hashlib
    from datetime import date
    pacer = pacer or Pacer()
    path = Path(state_path)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    if not isinstance(state, dict):
        state = {}
    if state.get("stopped"):
        return {"status": "stopped", "reason": f"an earlier call stopped: {state['stopped']}. Nothing was opened; the "
                                               "user clears LinkedIn's check and removes `stopped` from the state file",
                "results": [], "remaining": len(steps)}
    plan_id = hashlib.sha1(json.dumps([step_key(s) for s in steps]).encode()).hexdigest()[:16]
    plans = state.setdefault("plans", {})
    done = plans.setdefault(plan_id, {})
    day = today or date.today().isoformat()
    saves = state.setdefault("saves", {})
    saves.setdefault(day, 0)
    started, session_saves, results = pacer.clock(), 0, []

    def save_state():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        tmp.replace(path)

    for key, rec in list(done.items()):
        if rec.get("result") == "started":   # the last call died inside this step: its Save may have landed
            done[key] = {"result": "unknown", "reason": "the call ended inside this step: re-capture and verify; "
                                                        "it is not repeated"}
    pending = [s for s in steps if step_key(s) not in done]
    for index, step in enumerate(pending):
        if saves[day] >= pacer.daily_cap:
            save_state()
            return {"status": "paused", "reason": f"{pacer.daily_cap} saves today: the rest waits for tomorrow",
                    "results": results, "remaining": len(pending) - index}
        if pacer.clock() - started > budget_s:
            save_state()
            return {"status": "continue", "results": results, "remaining": len(pending) - index}
        key = step_key(step)
        if step.get("result") != "refused":
            done[key] = {"result": "started"}
            save_state()
        try:
            out = page.run(step)
        except Exception as exc:  # noqa: BLE001 - one broken step never takes the rest of the run with it
            out = {"field": step.get("field") or step.get("kind"), "result": "failed",
                   "reason": f"{type(exc).__name__}: {exc}"}
        blocked = page.challenge()
        if blocked:
            results.append({**out, "result": "stopped", "reason": blocked})
            done[key] = {"result": out.get("result"), "reason": out.get("reason")}
            state["stopped"] = blocked
            save_state()
            return {"status": "stopped", "reason": blocked + ": the run stops; the user signs in or clears it",
                    "results": results, "remaining": len(pending) - index - 1}
        results.append(out)
        done[key] = {"result": out.get("result") or "failed", "reason": out.get("reason")}
        if out.get("result") == "applied" and " already " not in str(out.get("note") or ""):
            saves[day] += 1
            session_saves += 1
            save_state()
            if index < len(pending) - 1:
                pacer.between(session_saves)
        else:
            save_state()
    return {"status": "done", "results": results, "remaining": 0}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan", help="the ordered form steps for one phase")
    pl.add_argument("approved")
    pl.add_argument("--current", nargs="+", required=True, help="one capture per profile language, primary first")
    pl.add_argument("--phase", choices=("structure", "text"), required=True)
    pl.add_argument("--json", action="store_true")
    ns = p.parse_args(argv)
    try:
        try:
            approved = json.loads(Path(ns.approved).read_text(encoding="utf-8"))
            captures = [json.loads(Path(c).read_text(encoding="utf-8")) for c in ns.current]
        except (OSError, ValueError) as exc:
            raise UsageError(f"cannot read input: {exc}") from exc
        if not isinstance(approved, dict) or not all(isinstance(c, dict) for c in captures):
            raise UsageError("APPROVED.json and every capture must be JSON objects")
        steps = plan(approved, captures, ns.phase)
    except UsageError as exc:
        sys.stderr.write(json.dumps({"error": str(exc), "code": "BAD_INPUT"}) + "\n")
        return 2
    if ns.json:
        print(json.dumps(steps, ensure_ascii=False, indent=1))
    else:
        for s in steps:
            what = s.get("field") or s.get("kind")
            print(f"{s.get('result', s.get('action', '?')):9} {what} [{s.get('language') or '-'}] "
                  f"{s.get('url') or s.get('reason', '')}")
    return 1 if any(s.get("result") == "refused" and s.get("phase") == "structure" for s in steps) else 0


if __name__ == "__main__":
    sys.exit(main())
