"""The writer fills LinkedIn's forms with a script, not with prose it improvises per run.

The run that prompted these tests (a real apply on a real profile, replayed here with fictitious data) wrote every
form by hand-made JavaScript: a new position was saved without its end date and became the current job, LinkedIn then
replaced the headline with "<title> at <company>", the headline fix appended the text instead of replacing it, and a
delete was held because nobody had written down that the dialog never names the entry. `profile_form.py` holds those
lessons. The browser tests drive a real headless Chrome over a pipe (no debugging port) against a fixture built from
the measured form, and each asserts what LinkedIn would have stored after Save.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "squads" / "jobs" / "skills" / "optimizing-profiles" / "scripts"
FORM = SCRIPTS / "profile_form.py"
FIXTURE = REPO / "tests" / "fixtures" / "linkedin" / "position_form.html"
ABOUT_FIXTURE = REPO / "tests" / "fixtures" / "linkedin" / "about_form.html"
CHROME = next((c for c in (shutil.which("chromium"), shutil.which("google-chrome"), shutil.which("chromium-browser"),
                           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome") if c and Path(c).is_file()),
              None)
needs_chrome = pytest.mark.skipif(CHROME is None or os.name == "nt", reason="no Chrome binary")


def load_form():
    spec = importlib.util.spec_from_file_location("profile_form_under_test", FORM)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pf = load_form()


def run(*args):
    return subprocess.run([sys.executable, "-B", str(FORM), *map(str, args)], capture_output=True, text=True,
                          timeout=60)


# --- plan: what the writer is told to do, form by form ---------------------------------------------------------------

BASE = "https://www.linkedin.com/in/ana-example/"


def role(company, title, dates, form, description=""):
    return {"company": company, "title": title, "dates": dates, "description": description, "skills": [],
            "edit": f"{BASE}details/experience/edit/forms/{form}/"}


CURRENT = {"own_profile": "ana-example", "language": "es", "primary_language": "es", "profile_languages": ["es", "en"],
           "headline": "Analista de datos", "about": "Sobre mí.", "skills": ["SQL", "Excel"], "top_skills": [],
           "experience": [role("Sample Labs", "Software Developer", "Oct 2023 - Apr 2024 · 7 mos", 2),
                          role("Contoso Retail", "Frontend Developer Trainee", "Apr 2022 - Oct 2022 · 7 mos", 3)],
           "education": [{"institution": "Example Institute", "degree": "Web Developer, Software",
                          "dates": "Feb 2021 – Dec 2021", "description": "",
                          "edit": f"{BASE}details/education/edit/forms/9/"}]}
CURRENT_EN = dict(CURRENT, language="en", headline="Analista de datos", about="About me.")

APPROVED = {"fields": [
    {"field": "headline", "language": "es", "after": "Analista de datos | SQL"},
    {"field": "headline", "language": "en", "after": "Data analyst | SQL"},
    {"field": "experience:Independent:Freelance Developer", "language": "es", "after": "• Construí un bot."},
    {"field": "skills", "language": "es", "after": ["SQL", "Power BI"]}],
    "structure": [
    {"kind": "experience_title", "company": "Sample Labs", "title": "Senior Software Developer", "was": "Software Developer"},
    {"kind": "experience_dates", "company": "Sample Labs", "title": "Senior Software Developer", "from": "Oct 2024",
     "to": "Feb 2025"},
    {"kind": "experience_delete", "company": "Contoso Retail", "title": "Frontend Developer Trainee"},
    {"kind": "experience_create", "company": "Independent", "title": "Freelance Developer", "from": "Jan 2024",
     "to": "Dec 2024", "employment": "Self-employed"}]}


def test_a_rename_and_its_new_dates_are_one_form_and_one_save():
    steps = pf.plan(APPROVED, [CURRENT], "structure")
    rename = next(s for s in steps if "experience_title" in s["kind"])
    assert rename["kind"] == "experience_title+experience_dates"
    assert rename["url"].endswith("/details/experience/edit/forms/2/")            # the form of the old title
    assert rename["expect"] == {"title": "Software Developer", "company": "Sample Labs"}
    assert rename["set"] == {"title": "Senior Software Developer", "from": "Oct 2024", "to": "Feb 2025"}
    assert [s for s in steps if s["kind"] == "experience_delete"][0]["url"].endswith("/forms/3/")


def test_a_new_position_carries_its_end_date_and_its_approved_description():
    create = next(s for s in pf.plan(APPROVED, [CURRENT], "structure") if s["kind"] == "experience_create")
    assert create["set"]["to"] == "Dec 2024" and create["set"]["description"] == "• Construí un bot."
    assert create["expect"] == {"new": True}
    without_end = json.loads(json.dumps(APPROVED))
    del without_end["structure"][3]["to"]
    create = next(s for s in pf.plan(without_end, [CURRENT], "structure") if s["kind"] == "experience_create")
    assert create["result"] == "refused" and "headline" in create["reason"]


def test_a_row_for_an_entry_the_capture_lacks_is_refused_and_plan_exits_1(tmp_path):
    approved = {"structure": [{"kind": "experience_dates", "company": "Globex", "title": "Engineer",
                               "from": "Jan 2020", "to": "Jan 2021"}]}
    a, c = tmp_path / "a.json", tmp_path / "c.json"
    a.write_text(json.dumps(approved)), c.write_text(json.dumps(CURRENT))
    p = run("plan", a, "--current", c, "--phase", "structure", "--json")
    assert p.returncode == 1 and json.loads(p.stdout)[0]["result"] == "refused"


def test_text_steps_expect_the_captured_text_and_skills_go_one_per_form():
    steps = pf.plan(APPROVED, [CURRENT, CURRENT_EN], "text")
    head_en = next(s for s in steps if s["field"] == "headline" and s["language"] == "en")
    # the empty English tab shows the Spanish text; once Spanish is written it shows the new Spanish text
    assert head_en["expect"] == ["Analista de datos", "Analista de datos | SQL"]
    assert [s["field"] for s in steps if s.get("action") in ("skill_add", "skill_remove")] == ["skill:Power BI",
                                                                                               "skill:Excel"]
    assert next(s for s in steps if s["field"].startswith("experience:Independent"))["result"] == "refused"


# --- the browser half, on a real Chrome ------------------------------------------------------------------------------

class Browser:
    """A minimal CDP client over --remote-debugging-pipe: the same js()/cdp() surface browser_exec gives the bot."""

    def __init__(self):
        self.profile = tempfile.mkdtemp(prefix="pf-chrome-")
        r1, self.w1 = os.pipe()
        self.r2, w2 = os.pipe()

        def fds():
            os.dup2(r1, 3)
            os.dup2(w2, 4)

        self.proc = subprocess.Popen([CHROME, "--headless=new", "--remote-debugging-pipe", "--no-first-run",
                                      "--no-default-browser-check", f"--user-data-dir={self.profile}",
                                      "--window-size=1200,1600", "about:blank"],
                                     pass_fds=(3, 4), preexec_fn=fds, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)
        os.close(r1)
        os.close(w2)
        self.buf, self.n, self.sid = b"", 0, None
        target = self.call("Target.createTarget", url="about:blank")["targetId"]
        self.sid = self.call("Target.attachToTarget", targetId=target, flatten=True)["sessionId"]

    def call(self, method, **params):
        self.n += 1
        msg = {"id": self.n, "method": method, "params": params}
        if self.sid:
            msg["sessionId"] = self.sid
        os.write(self.w1, json.dumps(msg).encode() + b"\0")
        while True:
            while b"\0" not in self.buf:
                chunk = os.read(self.r2, 1 << 16)
                if not chunk:
                    raise RuntimeError("Chrome closed the pipe")
                self.buf += chunk
            raw, self.buf = self.buf.split(b"\0", 1)
            reply = json.loads(raw)
            if reply.get("id") == self.n:
                if "error" in reply:
                    raise RuntimeError(reply["error"])
                return reply.get("result", {})

    def cdp(self, method, **params):
        return self.call(method, **params)

    def js(self, expression):
        res = self.call("Runtime.evaluate", expression=expression, returnByValue=True, awaitPromise=True)
        if res.get("exceptionDetails"):
            raise RuntimeError(res["exceptionDetails"])
        return res.get("result", {}).get("value")

    def open(self, state: dict, fixture: Path = FIXTURE):
        url = fixture.as_uri() + "#" + urllib.parse.quote(json.dumps(state))
        self.call("Page.navigate", url="about:blank")
        self.call("Page.navigate", url=url)
        for _ in range(40):
            time.sleep(0.05)
            if self.js("document.readyState") == "complete" and self.js("!!document.getElementById('save')"):
                return
        raise RuntimeError("the fixture did not load")

    def close(self):
        self.proc.kill()
        self.proc.wait(timeout=10)
        shutil.rmtree(self.profile, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    b = Browser()
    yield b
    b.close()


def page(browser):
    return pf.Page(browser.js, browser.cdp, own="ana-example", pause=0)


def saved(browser):
    return browser.js("window.__saved || null")


@needs_chrome
def test_renaming_and_re_dating_a_position_saves_exactly_the_approved_values(browser):
    browser.open({"title": "Software Developer", "org": "Sample Labs", "sm": "10", "sy": "2023", "em": "4",
                  "ey": "2024"})
    step = next(s for s in pf.plan(APPROVED, [CURRENT], "structure") if "experience_title" in s["kind"])
    out = page(browser).position(step)
    assert out["result"] == "applied", out
    got = saved(browser)
    assert (got["title"], got["org"], got["sm"], got["sy"], got["em"], got["ey"]) == (
        "Senior Software Developer", "Sample Labs", "10", "2024", "2", "2025")
    assert got["current"] is False and got["notify"] is False


@needs_chrome
def test_a_new_past_position_is_saved_with_its_end_date_not_as_the_current_job(browser):
    # LinkedIn opens "Add position" with "I am currently working in this role" ticked and the end selects hidden;
    # saving it like that made the new role the current job and rewrote the headline.
    browser.open({"current": True, "offer_end": True})
    step = next(s for s in pf.plan(APPROVED, [CURRENT], "structure") if s["kind"] == "experience_create")
    out = page(browser).position(step)
    assert out["result"] == "applied", out
    got = saved(browser)
    assert got["current"] is False and (got["em"], got["ey"]) == ("12", "2024")
    assert (got["sm"], got["sy"]) == ("1", "2024") and got["emp"] == "3"
    assert got["end_now"] is False                       # the user's real current job was not ended
    assert got["desc"].strip() == "• Construí un bot."


@needs_chrome
def test_a_delete_runs_only_on_the_form_of_the_entry_the_row_names(browser):
    step = next(s for s in pf.plan(APPROVED, [CURRENT], "structure") if s["kind"] == "experience_delete")
    browser.open({"title": "Frontend Developer", "org": "Contoso Retail"})          # a sibling entry's form
    out = page(browser).delete(step)
    assert out["result"] == "refused" and browser.js("window.__deleted || false") is False
    browser.open({"title": "Frontend Developer Trainee", "org": "Contoso Retail"})
    out = page(browser).delete(step)
    assert out["result"] == "applied", out
    assert browser.js("window.__deleted || false") is True


@needs_chrome
def test_a_description_is_replaced_whole_and_only_when_the_form_shows_the_captured_text(browser):
    step = {"control": "description", "want": "• Built the sales report.\n• Cut the weekly load.",
            "expect": ["• Old line one.\n• Old line two."]}
    browser.open({"title": "Analyst", "org": "Northwind", "desc": "• Somebody else's edit."})
    assert page(browser).text(step)["result"] == "refused" and saved(browser) is None
    browser.open({"title": "Analyst", "org": "Northwind", "desc": "• Old line one.\n• Old line two."})
    out = page(browser).text(step)
    assert out["result"] == "applied", out
    assert pf.norm(saved(browser)["desc"]) == pf.norm(step["want"])                # replaced, not appended


@needs_chrome
def test_typed_a_few_words_at_a_time_the_old_text_is_still_replaced_whole(browser):
    # human typing sends many small inserts; only the first replaces the selection, the rest must follow the caret
    sent = []

    def cdp(method, **params):
        if method == "Input.insertText":
            sent.append(params["text"])
        return browser.cdp(method, **params)

    want = "• Built the monthly sales report for four regions.\n• Cut the weekly load from six hours to one."
    step = {"control": "description", "want": want, "expect": ["• Old line one.\n• Old line two."]}
    browser.open({"title": "Analyst", "org": "Northwind", "desc": "• Old line one.\n• Old line two."})
    import random
    slow = pf.Page(browser.js, cdp, own="ana-example", pause=0.001, typing=(0.0, 0.002), rng=random.Random(7))
    out = slow.text(step)
    assert out["result"] == "applied", out
    assert len(sent) >= 6                                                          # chunks, not one paste
    assert pf.norm(saved(browser)["desc"]) == pf.norm(want)


class FakePage:
    """Stands in for Page in apply_all: records each step and can show a checkpoint after the n-th one."""

    def __init__(self, results=None, challenge_after=None):
        self.ran, self.results, self.challenge_after = [], results or {}, challenge_after

    def run(self, step):
        self.ran.append(step["n"])
        return {"field": step["n"], "result": self.results.get(step["n"], "applied")}

    def challenge(self):
        return "LinkedIn showed /checkpoint/challenge/" if self.challenge_after == len(self.ran) else ""


def pacer(sleeps, clock=None, **kw):
    import random
    return pf.Pacer(sleep=sleeps.append, rng=random.Random(1), clock=clock or (lambda: 0.0), **kw)


def test_saves_are_spaced_like_a_person_with_a_longer_break_every_few(tmp_path):
    sleeps = []
    steps = [{"n": i} for i in range(8)]
    out = pf.apply_all(FakePage(), steps, str(tmp_path / "s.json"), pacer(sleeps, burst=3))
    assert out["status"] == "done" and len(sleeps) == 7                           # between saves, none after the last
    breaks = [s for i, s in enumerate(sleeps, 1) if i % 3 == 0]
    gaps = [s for i, s in enumerate(sleeps, 1) if i % 3]
    assert all(25 <= s <= 70 for s in gaps) and all(180 <= s <= 360 for s in breaks)
    assert len(set(round(s, 3) for s in gaps)) == len(gaps)                       # never a fixed beat


def test_a_checkpoint_page_stops_the_run_and_nothing_more_is_opened(tmp_path):
    fake = FakePage(challenge_after=2)
    out = pf.apply_all(fake, [{"n": i} for i in range(5)], str(tmp_path / "s.json"), pacer([]))
    assert out["status"] == "stopped" and "checkpoint" in out["reason"]
    assert fake.ran == [0, 1] and out["remaining"] == 3                            # the stopped step is recorded
    again = FakePage()
    out = pf.apply_all(again, [{"n": i} for i in range(5)], str(tmp_path / "s.json"), pacer([]))
    assert out["status"] == "stopped" and again.ran == []                         # a later call opens nothing


def test_the_daily_cap_pauses_and_the_next_day_resumes_where_it_stopped(tmp_path):
    state = str(tmp_path / "s.json")
    steps = [{"n": i} for i in range(5)]
    first = FakePage()
    out = pf.apply_all(first, steps, state, pacer([], daily_cap=3), today="2026-10-25")
    assert out["status"] == "paused" and first.ran == [0, 1, 2] and out["remaining"] == 2
    again = FakePage()
    assert pf.apply_all(again, steps, state, pacer([], daily_cap=3), today="2026-10-25")["status"] == "paused"
    assert again.ran == []                                                         # same day: nothing more
    nextday = FakePage()
    out = pf.apply_all(nextday, steps, state, pacer([], daily_cap=3), today="2026-10-26")
    assert out["status"] == "done" and nextday.ran == [3, 4]                       # no step saved twice


def test_a_step_that_crashes_is_failed_and_the_rest_still_runs(tmp_path):
    class Crashing(FakePage):
        def run(self, step):
            if step["n"] == 1:
                self.ran.append(1)
                raise RuntimeError("Chrome closed the pipe")
            return super().run(step)

    fake = Crashing()
    out = pf.apply_all(fake, [{"n": i} for i in range(3)], str(tmp_path / "s.json"), pacer([]))
    assert out["status"] == "done" and fake.ran == [0, 1, 2]
    assert out["results"][1]["result"] == "failed" and "pipe" in out["results"][1]["reason"]


def test_a_call_that_died_inside_a_save_never_repeats_that_step(tmp_path):
    # "Add position" twice would create the position twice: a step left `started` is reported, not re-run
    state = tmp_path / "s.json"
    steps = [{"n": i} for i in range(3)]

    class Dies(FakePage):
        def run(self, step):
            if step["n"] == 1:
                raise KeyboardInterrupt   # the browser_exec call is killed mid-step
            return super().run(step)

    with pytest.raises(KeyboardInterrupt):
        pf.apply_all(Dies(), steps, str(state), pacer([]))
    again = FakePage()
    out = pf.apply_all(again, steps, str(state), pacer([]))
    assert out["status"] == "done" and again.ran == [2]
    plan = next(iter(json.loads(state.read_text())["plans"].values()))
    assert plan[pf.step_key(steps[1])]["result"] == "unknown"


def test_a_change_approved_later_is_a_new_plan_and_is_applied(tmp_path):
    state = str(tmp_path / "s.json")
    head = {"n": 0, "field": "headline", "want": "A"}
    pf.apply_all(FakePage(), [head], state, pacer([]))
    later = FakePage()
    out = pf.apply_all(later, [head, {"n": 1, "field": "about", "want": "B"}], state, pacer([]))
    assert out["status"] == "done" and later.ran == [0, 1]


def test_a_run_longer_than_one_browser_call_continues_without_repeating_a_step(tmp_path):
    ticks = iter(range(0, 10_000, 400))
    state = str(tmp_path / "s.json")
    steps = [{"n": i} for i in range(6)]
    first = FakePage(results={1: "failed"})
    out = pf.apply_all(first, steps, state, pacer([], clock=lambda: next(ticks)), budget_s=1000)
    assert out["status"] == "continue" and first.ran == [0, 1]                    # clock: 400, 800, then 1200 > budget
    second = FakePage()
    out = pf.apply_all(second, steps, state, pacer([]))
    assert out["status"] == "done" and second.ran == [2, 3, 4, 5]                 # the failed one is not retried


@needs_chrome
def test_nothing_is_saved_while_the_notify_network_switch_is_on(browser):
    browser.open({"title": "Software Developer", "org": "Sample Labs", "sm": "10", "sy": "2023", "em": "4",
                  "ey": "2024"})
    browser.js("document.getElementById('notify').checked = true")
    step = next(s for s in pf.plan(APPROVED, [CURRENT], "structure") if "experience_title" in s["kind"])
    out = page(browser).position(step)
    assert out["result"] == "refused" and "notify" in out["reason"] and saved(browser) is None


def test_the_only_buttons_a_saved_position_can_lead_to_are_never_opened():
    # After Save LinkedIn redirects to follow-up prompts: share the new position, people you may know, Premium. The
    # run that prompted this landed on all three. The guard refuses them, and the photo, banner and URL settings.
    own = SCRIPTS / "own_profile.py"
    for tail in ("edit/forms/next-action/shareable-trigger-new-position/",
                 "edit/forms/next-action/people-you-may-know/123/?formType=TOP_LEVEL_POSITION_FORM",
                 "edit/forms/next-action/premium-upsell-about-card/", "edit/photo/", "edit/forms/background-photo/",
                 "edit/forms/public-profile-settings/", "edit/forms/content-collections-star-pill/new/",
                 "details/featured/edit/forms/1/", "details/skills/edit/forms/next-action/add-another-skill/"):
        p = subprocess.run([sys.executable, "-B", str(own), "check", BASE + tail, "--own", "ana-example", "--json"],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 1 and json.loads(p.stdout)["allow"] is False, tail
    for tail in ("edit/intro/", "edit/forms/summary/new/", "edit/forms/position/123", "details/experience/edit/forms/new/",
                 "details/education/edit/forms/9/", "details/skills/edit/forms/new/", "details/skills/"):
        p = subprocess.run([sys.executable, "-B", str(own), "check", BASE + tail, "--own", "ana-example", "--json"],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, tail


# --- verify: a structure row is "ok" only when the page shows exactly that -------------------------------------------

DIFF = SCRIPTS / "profile_diff.py"


def verify_rows(tmp_path, rows, current):
    a, c = tmp_path / "approved.json", tmp_path / "current.json"
    a.write_text(json.dumps({"structure": rows})), c.write_text(json.dumps(current))
    p = subprocess.run([sys.executable, "-B", str(DIFF), "verify", a, c, "--json"], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode in (0, 1), p.stderr
    return p.returncode, json.loads(p.stdout)


ON_PAGE = {"experience": [role("Northwind", "Analyst", "Jan 2020 - Oct 2023 · 3 yrs 10 mos", 1)],
           "education": [{"institution": "Example Institute", "degree": "Web Developer, Software Engineering",
                          "dates": "Feb 2021 – Dec 2021", "description": ""}]}


def test_dates_are_compared_as_dates_start_against_start_and_end_against_end(tmp_path):
    row = {"kind": "experience_dates", "company": "Northwind", "title": "Analyst"}
    assert verify_rows(tmp_path, [dict(row, **{"from": "Jan 2020", "to": "Oct 2023"})], ON_PAGE)[0] == 0
    assert verify_rows(tmp_path, [dict(row, **{"from": "Oct 2023", "to": "Jan 2020"})], ON_PAGE)[0] == 1   # swapped
    assert verify_rows(tmp_path, [dict(row, **{"from": "2020", "to": "2023"})], ON_PAGE)[0] == 1           # no month
    assert verify_rows(tmp_path, [dict(row, **{"from": "Jan 2020", "to": "Present"})], ON_PAGE)[0] == 1
    school = {"kind": "education_dates", "institution": "Example Institute"}
    assert verify_rows(tmp_path, [dict(school, **{"from": "Feb 2021", "to": "Dec 2021"})], ON_PAGE)[0] == 0


def test_a_degree_rename_is_ok_only_when_the_page_shows_the_new_degree(tmp_path):
    row = {"kind": "education_title", "institution": "Example Institute", "title": "Full Stack Web Development"}
    code, out = verify_rows(tmp_path, [row], ON_PAGE)
    assert code == 1 and "Web Developer" in out["failures"][0]["reason"]
    renamed = json.loads(json.dumps(ON_PAGE))
    renamed["education"][0]["degree"] = "Full Stack Web Development, Software Engineering"
    assert verify_rows(tmp_path, [row], renamed)[0] == 0


def test_a_new_school_is_a_row_verify_knows(tmp_path):
    row = {"kind": "education_create", "institution": "Sample University", "from": "2024", "to": "2025"}
    assert verify_rows(tmp_path, [row], ON_PAGE)[0] == 1
    added = json.loads(json.dumps(ON_PAGE))
    added["education"].append({"institution": "Sample University", "degree": "", "dates": "2024 – 2025"})
    assert verify_rows(tmp_path, [row], added)[0] == 0


def test_a_degree_rename_keeps_the_school_covered_in_the_copy_check(tmp_path):
    folder = tmp_path / "ana"
    folder.mkdir()
    (folder / "profile.md").write_text("---\ntarget_roles: [Analyst]\n---\n")
    (folder / "achievements.yaml").write_text("achievements: []\n")
    copy = {"platform": "linkedin", "language": "es", "skills": [],
            "blocks": [{"section": "headline", "text": "Analyst", "no_claim": True},
                       {"section": "experience", "company": "Northwind", "title": "Analyst", "text": "Did it.",
                        "no_claim": True},
                       {"section": "education", "institution": "Example Institute", "text": "Web.", "no_claim": True}]}
    files = {name: tmp_path / f"{name}.json" for name in ("copy", "current", "structure")}
    files["copy"].write_text(json.dumps(copy))
    files["current"].write_text(json.dumps(dict(ON_PAGE, language="es", profile_languages=["es"])))
    files["structure"].write_text(json.dumps({"structure": [{"kind": "education_title", "institution":
                                                             "Example Institute", "title": "Full Stack Web"}]}))
    p = subprocess.run([sys.executable, "-B", str(SCRIPTS / "check_profile_copy.py"), files["copy"], "--project", folder,
                        "--current", files["current"], "--structure", files["structure"], "--json"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stdout


def test_a_company_with_one_role_keeps_its_role_and_its_edit_form(tmp_path):
    # LinkedIn renders a company with a single role as one item (title, "Company · Employment", dates) with no role
    # list: the parser dropped it, so a position the bot had just created never reached current.json.
    capture = {"url": BASE, "name": "Ana", "headline": "Analyst", "about": "x", "profile_languages": ["English"],
               "experience": {"found": True, "groups": [
                   {"company": "", "all": ["Freelance Developer", "Independent · Self-employed",
                                           "Jan 2024 - Dec 2024 · 1 yr", "• Built a bot."], "roles": [],
                    "edit": BASE + "details/experience/edit/forms/22/"}]},
               "education": {"found": True, "items": []}, "skills": {"items": ["SQL"]}}
    src, out = tmp_path / "capture.json", tmp_path / "current.json"
    src.write_text(json.dumps(capture))
    p = subprocess.run([sys.executable, "-B", str(SCRIPTS / "parse_profile.py"), src, "--output", out],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    rows = json.loads(out.read_text())["experience"]
    assert [(r["company"], r["title"], r["employment"], r["dates"], r["edit"]) for r in rows] == [
        ("Independent", "Freelance Developer", "Self-employed", "Jan 2024 - Dec 2024 · 1 yr",
         BASE + "details/experience/edit/forms/22/")]


@needs_chrome
def test_role_skills_tick_what_was_approved_and_untick_the_rest(browser):
    browser.open({"title": "Analyst", "org": "Northwind", "catalog": ["Power BI", "Power Apps"],
                  "skills": [{"name": "SQL", "checked": True}, {"name": "Mean Stack", "checked": True}]})
    out = page(browser).role_skills({"want": ["SQL", "Power BI"], "have": ["SQL", "Mean Stack"]})
    assert out["result"] == "applied", out
    assert sorted(saved(browser)["skills"]) == ["Power BI", "SQL"]


def opened_page(browser):
    """A Page whose navigation is already done (the fixture is loaded): run() then exercises everything after open."""
    p = page(browser)
    p.open = lambda *a, **k: {"result": "open"}
    return p


@needs_chrome
def test_a_box_in_another_language_is_never_unticked_and_the_current_role_survives(browser):
    # the account's interface may be Portuguese: the current-role box is then a label no English or Spanish pattern
    # names. Only skills the capture listed under this role are unticked; everything else is left as it was.
    browser.open({"title": "Analyst", "org": "Northwind", "current": True, "cur_label": "Atualmente trabalho neste cargo",
                  "skills": [{"name": "SQL", "checked": True}, {"name": "Excel", "checked": True}]})
    step = {"action": "role_skills", "url": BASE + "details/experience/edit/forms/1/", "want": ["SQL"],
            "have": ["SQL", "Excel"], "expect": {"title": "Analyst", "company": "Northwind"}}
    out = opened_page(browser).run(step)
    assert out["result"] == "applied", out
    got = saved(browser)
    assert got["current"] is True and got["skills"] == ["SQL"]


@needs_chrome
def test_a_new_form_with_any_unexpected_ticked_box_is_never_saved(browser):
    # "End current position as of now" in Portuguese, pre-ticked: saving would end the user's real current job
    browser.open({"current": True, "offer_end": True, "end_now": True,
                  "end_label": "Encerrar o cargo atual a partir de agora - Lead"})
    step = next(s for s in pf.plan(APPROVED, [CURRENT], "structure") if s["kind"] == "experience_create")
    out = opened_page(browser).run(step)
    assert out["result"] == "refused" and "ticked" in out["reason"] and saved(browser) is None


@needs_chrome
def test_a_save_that_leaves_the_form_open_is_failed_not_applied(browser):
    browser.open({"title": "Software Developer", "org": "Sample Labs", "sm": "10", "sy": "2023", "em": "4", "ey": "2024",
                  "reject": "End date can't be before start date"})
    step = next(s for s in pf.plan(APPROVED, [CURRENT], "structure") if "experience_title" in s["kind"])
    out = page(browser).position(step)
    assert out["result"] == "failed" and "stayed open" in out["reason"], out
    assert saved(browser) is None


@needs_chrome
def test_a_field_that_does_not_keep_the_typed_value_is_never_saved(browser):
    browser.open({"title": "Software Developer", "org": "Sample Labs", "sm": "10", "sy": "2023", "em": "4", "ey": "2024"})
    # a field that snaps back to its old value (a widget that ignores programmatic input)
    browser.js("""(() => { const t = document.getElementById('title'); const keep = t.value;
        const d = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value');
        Object.defineProperty(t, 'value', {get() { return keep; }, set(v) { d.set.call(this, keep); }}); })()""")
    step = next(s for s in pf.plan(APPROVED, [CURRENT], "structure") if "experience_title" in s["kind"])
    out = page(browser).position(step)
    assert out["result"] == "failed" and "title" in out["reason"] and saved(browser) is None


@needs_chrome
def test_a_click_after_a_failed_mark_never_lands_on_the_previous_element(browser):
    browser.open({"title": "Analyst", "org": "Northwind", "skills": [{"name": "SQL", "checked": True}]})
    p = page(browser)
    assert p.mark(kind="box", match="^SQL$")
    assert not p.mark(kind="box", match="^Kubernetes$")
    assert p.click_marked() is False
    assert browser.js("[...document.querySelectorAll('#skills input')].every(c => c.checked)") is True


class Landing:
    """js/cdp fakes for Page.open: the page is `start` until navigate, then `land`."""

    def __init__(self, land, form=True):
        self.href, self.land, self.form = "https://www.linkedin.com/in/ana-example/", land, form

    def cdp(self, method, **params):
        if method == "Page.navigate":
            self.href = self.land

    def js(self, expression):
        if expression == "location.href":
            return self.href
        if expression == "document.readyState":
            return "complete"
        if "found: true" in expression:
            return {"found": self.form, "boxes": []}
        return None


def test_open_proves_where_the_browser_landed():
    url = BASE + "details/experience/edit/forms/2/"
    for land, form, result in ((BASE + "edit/forms/position/2", True, "open"),
                               (BASE + "edit/forms/next-action/people-you-may-know/7/", True, "refused"),
                               ("chrome-error://chromewebdata/", True, "refused"),
                               ("https://www.linkedin.com/checkpoint/challenge/x", True, "refused"),
                               (BASE + "edit/forms/position/2", False, "refused")):
        fake = Landing(land, form)
        out = pf.Page(fake.js, fake.cdp, own="ana-example", pause=0).open(url)
        assert out["result"] == result, (land, form, out)
    fake = Landing(BASE)
    assert pf.Page(fake.js, fake.cdp, own="ana-example", pause=0).open(
        BASE + "details/experience/edit/forms/2/?redirect=https://evil.example/")["result"] == "refused"


# --- plan refuses what the form could not do exactly ----------------------------------------------------------------

def refused(approved, current=CURRENT, phase="structure"):
    return [s for s in pf.plan(approved, [current], phase) if s.get("result") == "refused"]


def test_two_entries_with_the_same_name_are_never_guessed():
    rehire = json.loads(json.dumps(CURRENT))
    rehire["experience"].append(role("Sample Labs", "Software Developer", "Jan 2019 - Dec 2019 · 1 yr", 7))
    rehire["education"].append(dict(rehire["education"][0], degree="Master, Data", edit=BASE + "details/education/edit/forms/8/"))
    out = refused({"structure": [{"kind": "experience_delete", "company": "Sample Labs", "title": "Software Developer"},
                                 {"kind": "education_delete", "institution": "Example Institute"}]}, rehire)
    assert len(out) == 2 and all("2 entries" in s["reason"] for s in out)
    # naming the degree tells the two schools apart
    steps = pf.plan({"structure": [{"kind": "education_delete", "institution": "Example Institute",
                                    "degree": "Master"}]}, [rehire], "structure")
    assert steps[0]["url"].endswith("/forms/8/") and "result" not in steps[0]


def test_dates_the_form_cannot_take_exactly_are_refused_before_any_browser_work():
    base = {"kind": "experience_dates", "company": "Sample Labs", "title": "Software Developer"}
    for row in (dict(base, to="Q4 2023"), dict(base, **{"from": "2018", "to": "Dec 2019"}),
                dict(base, **{"from": "Present"})):
        assert refused({"structure": [row]}), row
    assert not refused({"structure": [dict(base, **{"from": "Sep 2018", "to": "Dec 2019"})]})
    assert pf.date_parts("Sept 2023") == ("9", "2023") and pf.date_parts_safe("Maybe 2023") is None


def test_a_new_current_position_needs_the_headline_approved_with_it():
    row = {"kind": "experience_create", "company": "Globex", "title": "Lead", "from": "Jan 2025", "to": "Present"}
    out = refused({"structure": [row]})
    assert out and "headline" in out[0]["reason"]
    assert not refused({"fields": [{"field": "headline", "language": "es", "after": "Lead | Globex"}],
                        "structure": [row]})


def test_an_entry_renamed_and_deleted_in_one_file_is_refused():
    rows = [{"kind": "experience_title", "company": "Sample Labs", "title": "Senior Software Developer",
             "was": "Software Developer"},
            {"kind": "experience_delete", "company": "Sample Labs", "title": "Software Developer"}]
    out = refused({"structure": rows})
    assert len(out) == 1 and "edited and deleted" in out[0]["reason"]


def test_a_short_skills_list_never_deletes_the_rest_of_a_long_profile():
    many = dict(CURRENT, skills=[f"Skill {i}" for i in range(30)])
    steps = pf.plan({"fields": [{"field": "skills", "language": "es", "after": ["Skill 1"]}]}, [many], "text")
    removals = [s for s in steps if s.get("action") == "skill_remove"]
    assert len(removals) == 29 and all(s.get("result") == "refused" for s in removals)
    listed = {"field": "skills", "language": "es", "after": ["Skill 1"], "remove": ["Skill 2", "Skill 3"]}
    removals = [s for s in pf.plan({"fields": [listed]}, [many], "text") if s.get("action") == "skill_remove"]
    assert [s["skill"] for s in removals] == ["Skill 2", "Skill 3"] and not any(s.get("result") for s in removals)


def test_the_guard_allows_only_the_measured_form_addresses():
    own = SCRIPTS / "own_profile.py"
    refused_tails = ("edit/forms/position/next-action/", "edit/forms/position/photo", "edit/forms/intro/photo",
                     "edit/forms/intro/public-profile-settings", "edit/forms/position/ABC",
                     "edit/forms/position/" + "1" * 23, "edit/forms/position/１２", "edit/intro/?redirect=x",
                     "details/experience/edit/forms/2/?profileUrn=urn:li:fsd_profile:OTHER")
    for tail in refused_tails:
        p = subprocess.run([sys.executable, "-B", str(own), "check", BASE + tail, "--own", "ana-example", "--json"],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 1, tail
    for tail in ("edit/forms/position/123?language=en&country=US", "skills/edit/forms/new/",
                 "details/education/edit/forms/new/?profileFormEntryPoint=Detail"):
        p = subprocess.run([sys.executable, "-B", str(own), "check", BASE + tail, "--own", "ana-example", "--json"],
                           capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, tail


def test_verify_proves_the_degree_the_row_names_when_one_school_holds_two(tmp_path):
    two = json.loads(json.dumps(ON_PAGE))
    two["education"].append({"institution": "Example Institute", "degree": "Master, Data", "dates": "2023 – 2024"})
    rename = {"kind": "education_title", "institution": "Example Institute", "title": "MSc Data Science",
              "was": "Master"}
    assert verify_rows(tmp_path, [rename], two)[0] == 1                            # neither degree reads the new name
    two["education"][1]["degree"] = "MSc Data Science, Data"
    assert verify_rows(tmp_path, [rename], two)[0] == 0
    dates = {"kind": "education_dates", "institution": "Example Institute", "from": "2023", "to": "2024"}
    assert verify_rows(tmp_path, [dates], two)[0] == 1                             # which degree? none is proven
    assert verify_rows(tmp_path, [dict(dates, degree="MSc Data Science")], two)[0] == 0
    gone = {"kind": "education_delete", "institution": "Example Institute", "degree": "MSc Data Science"}
    assert verify_rows(tmp_path, [gone], two)[0] == 1
    two["education"].pop()
    assert verify_rows(tmp_path, [gone], two)[0] == 0                              # the other degree stays


def test_verify_fails_one_row_with_a_bad_date_instead_of_aborting(tmp_path):
    row = {"kind": "experience_dates", "company": "Northwind", "title": "Analyst", "from": "Q1 2020"}
    good = {"kind": "experience_title", "company": "Northwind", "title": "Analyst"}
    code, out = verify_rows(tmp_path, [row, good], ON_PAGE)
    assert code == 1 and len(out["failures"]) == 1 and "not a date" in out["failures"][0]["reason"]


# --- top skills: the pins follow the approved skills list ------------------------------------------------------------

PINNED = dict(CURRENT, skills=["SQL", "Excel", "Python", "Power BI", "Team leadership"],
              top_skills=["Team leadership", "SQL", "Excel"])


def pin_plan(after, skills=None, current=PINNED):
    rows = [{"field": "top_skills", "language": "es", "after": after},
            {"field": "top_skills", "language": "en", "after": after}]
    if skills is not None:
        rows.append({"field": "skills", "language": "es", "after": skills})
    return [s for s in pf.plan({"fields": rows}, [current, dict(current, language="en")], "text")
            if s.get("field") == "top_skills"]


def test_the_pins_are_one_step_on_the_about_form_and_only_skills_the_list_keeps():
    steps = pin_plan(["SQL", "Python", "Power BI"])
    assert len(steps) == 1 and "result" not in steps[0]                           # one list for both languages
    assert steps[0]["url"] == BASE + "edit/forms/summary/new/" and steps[0]["want"] == ["SQL", "Python", "Power BI"]
    # a pin the approved skills list drops, or never had, would leave the pins out of step with the list
    assert pin_plan(["SQL", "Excel"], skills=["SQL", "Python"])[0]["result"] == "refused"
    assert pin_plan(["Looker"])[0]["result"] == "refused"
    assert "result" not in pin_plan(["Looker", "SQL"], skills=["SQL", "Looker", "Python"])[0]
    assert pin_plan(["SQL", "Python", "Excel", "Power BI", "Team leadership", "SQL"])[0]["result"] == "refused"
    six = dict(PINNED, skills=PINNED["skills"] + ["Looker"])
    assert pin_plan(["SQL", "Python", "Excel", "Power BI", "Team leadership", "Looker"], current=six)[0][
        "result"] == "refused"                                                     # LinkedIn pins at most 5
    # the pins go after every skills step, so a pin the same apply adds to the list already exists
    steps = pf.plan({"fields": [{"field": "top_skills", "after": ["Looker"]},
                                {"field": "skills", "after": ["SQL", "Excel", "Python", "Power BI", "Team leadership",
                                                              "Looker"]}]}, [PINNED], "text")
    assert [s["action"] for s in steps][-1] == "top_skills" and steps[0]["action"] == "skill_add"


def about_page(browser, pins, catalog, about="Soy analista.\nTrabajo con datos.", **hooks):
    browser.open({"pins": pins, "catalog": catalog, "about": about, **hooks}, ABOUT_FIXTURE)
    return opened_page(browser)


@needs_chrome
def test_the_pins_are_replaced_in_the_approved_order_and_the_about_text_is_untouched(browser):
    p = about_page(browser, ["Team leadership", "SQL", "Excel", "Docker", "Git"],
                   ["SQL", "Python", "Power BI", "Excel", "Team leadership"])
    step = pin_plan(["SQL", "Python", "Power BI"])[0]
    out = p.run(step)
    assert out["result"] == "applied", out
    got = saved(browser)
    assert got["pins"] == ["SQL", "Python", "Power BI"]                            # order kept, extras gone
    assert pf.norm(got["about"]) == pf.norm("Soy analista.\nTrabajo con datos.")


@needs_chrome
def test_pins_already_in_place_are_kept_and_nothing_is_saved_when_they_match(browser):
    p = about_page(browser, ["SQL", "Python", "Excel"], ["SQL", "Python", "Power BI", "Excel"])
    out = p.run(pin_plan(["SQL", "Python", "Power BI"])[0])
    assert out["result"] == "applied" and out["changed"] == ["-Excel", "+Power BI"], out
    p = about_page(browser, ["SQL", "Python", "Power BI"], ["SQL"])
    out = p.run(pin_plan(["SQL", "Python", "Power BI"])[0])
    assert out["result"] == "applied" and "already" in out["note"] and saved(browser) is None


@needs_chrome
def test_a_pin_linkedin_does_not_offer_leaves_the_form_unsaved(browser):
    p = about_page(browser, ["Team leadership"], ["SQL"])                          # "Python" is not in the taxonomy
    out = p.run(pin_plan(["SQL", "Python"])[0])
    assert out["result"] == "failed" and "Python" in out["reason"] and saved(browser) is None


def test_verify_holds_the_pins_to_their_order(tmp_path):
    a, c = tmp_path / "approved.json", tmp_path / "current.json"
    a.write_text(json.dumps({"fields": [{"field": "top_skills", "after": ["SQL", "Python"]}]}))
    for pins, code in ((["SQL", "Python"], 0), (["Python", "SQL"], 1)):
        c.write_text(json.dumps(dict(PINNED, top_skills=pins)))
        p = subprocess.run([sys.executable, "-B", str(DIFF), "verify", a, c, "--json"], capture_output=True,
                           text=True, timeout=60)
        assert p.returncode == code, (pins, p.stdout)


@needs_chrome
def test_pins_that_land_out_of_order_or_touch_the_about_text_are_never_saved(browser):
    catalog = ["SQL", "Python", "Power BI"]
    p = about_page(browser, [], catalog, sort=True)                                # LinkedIn re-sorted the pins
    out = p.run(pin_plan(["SQL", "Python", "Power BI"])[0])
    assert out["result"] == "failed" and "pins read" in out["reason"] and saved(browser) is None
    p = about_page(browser, [], catalog, leak=True)                                # a click typed into the About
    out = p.run(pin_plan(["SQL", "Python", "Power BI"])[0])
    assert out["result"] == "failed" and "About text" in out["reason"] and saved(browser) is None


# --- v5: the add-skill and add-language dialogs, year-only school dates, the languages section ---------------------
# The v5 run (2026-10-25) could not add "pgvector" or "PostgreSQL": those forms render Save and an <input> with no type
# attribute inside an open <dialog>, and the form finder only looked for input[type="text"], so it climbed past the
# dialog and found no form. `run()` also crashed on text steps, whose `expect` is a list. The languages section had no
# allowed form at all, and a school saved with only its end year ("2025") failed verify. Fictitious data throughout.

DIALOG = REPO / "tests" / "fixtures" / "linkedin" / "dialog_form.html"


@needs_chrome
def test_a_skill_in_the_add_skill_dialog_is_picked_from_linkedins_list_and_saved(browser):
    browser.open({"kind": "skill"}, fixture=DIALOG)
    out = page(browser).skill_add({"skill": "PostgreSQL"})
    assert out["result"] == "applied", out
    assert saved(browser) == {"value": "PostgreSQL", "picked": "PostgreSQL", "level": None}


@needs_chrome
def test_a_skill_the_picker_does_not_offer_is_never_saved(browser):
    browser.open({"kind": "skill"}, fixture=DIALOG)
    out = page(browser).skill_add({"skill": "Workers"})
    assert out["result"] == "failed" and saved(browser) is None


def lang_approved(name="English", level="Professional working proficiency"):
    return {"structure": [{"kind": "language_create", "language": name, "proficiency": level}]}


@needs_chrome
def test_a_new_language_is_saved_with_its_proficiency(browser):
    step = pf.plan(lang_approved(), [CURRENT], "structure")[0]
    assert step["url"].endswith("/details/languages/edit/forms/new/") and "result" not in step
    browser.open({"kind": "language"}, fixture=DIALOG)
    out = page(browser).language(step)
    assert out["result"] == "applied", out
    assert saved(browser) == {"value": "English", "picked": "English", "level": "Professional working proficiency"}


@needs_chrome
def test_a_language_form_that_is_not_empty_is_left_alone(browser):
    step = pf.plan(lang_approved(), [CURRENT], "structure")[0]
    browser.open({"kind": "language", "prefill": "Spanish"}, fixture=DIALOG)
    out = page(browser).language(step)
    assert out["result"] == "refused" and "not empty" in out["reason"] and saved(browser) is None


def test_a_language_row_with_a_level_linkedin_does_not_offer_or_already_listed_is_refused():
    step = pf.plan(lang_approved(level="B2"), [CURRENT], "structure")[0]
    assert step["result"] == "refused" and "proficiency" in step["reason"]
    listed = dict(CURRENT, languages=[{"language": "English", "proficiency": "Limited working proficiency"}])
    step = pf.plan(lang_approved(), [listed], "structure")[0]
    assert step["result"] == "refused" and "already" in step["reason"]


def test_a_text_step_runs_with_its_list_of_expected_texts():
    # run() read step["expect"].get(...) and crashed on every text step: their expect is the list of accepted texts
    class Stub(pf.Page):
        def open(self, *a, **k):
            return {"result": "open"}

        def read(self):
            return {"found": True, "boxes": []}

        def text(self, step):
            return {"result": "applied"}

    stub = Stub(lambda e: None, lambda *a, **k: None, own="ana-example", pause=0)
    out = stub.run({"action": "text", "control": "about", "url": BASE + "edit/forms/summary/new/",
                    "expect": ["Sobre mí."], "want": "Nuevo."})
    assert out["result"] == "applied"


def test_the_guard_opens_the_language_forms_and_still_refuses_other_sections():
    own = SCRIPTS / "own_profile.py"
    for tail, allow in (("details/languages/edit/forms/new/", True), ("details/languages/edit/forms/123/", True),
                        ("details/certifications/edit/forms/new/", False), ("details/languages/edit/x/", False)):
        p = subprocess.run([sys.executable, "-B", str(own), "check", BASE + tail, "--own", "ana-example", "--json"],
                           capture_output=True, text=True, timeout=60)
        assert json.loads(p.stdout)["allow"] is allow, tail


def test_verify_reads_a_school_saved_with_one_year_and_a_language_entry(tmp_path):
    diff = SCRIPTS / "profile_diff.py"
    current = dict(CURRENT, education=CURRENT["education"] + [
        {"institution": "Sample Language Center", "degree": "Advanced English Program", "dates": "2025",
         "description": ""}],
        languages=[{"language": "English", "proficiency": "Professional working proficiency"}])
    approved = {"fields": [], "structure": [
        {"kind": "education_create", "institution": "Sample Language Center", "title": "Advanced English Program",
         "to": "2025"},
        {"kind": "language_create", "language": "English", "proficiency": "Professional working proficiency"}]}
    a, c = tmp_path / "a.json", tmp_path / "c.json"
    a.write_text(json.dumps(approved)), c.write_text(json.dumps(current))
    p = subprocess.run([sys.executable, "-B", str(diff), "verify", a, c, "--json"], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 0, p.stdout
    current["languages"][0]["proficiency"] = "Limited working proficiency"
    c.write_text(json.dumps(current))
    p = subprocess.run([sys.executable, "-B", str(diff), "verify", a, c, "--json"], capture_output=True, text=True,
                       timeout=60)
    assert p.returncode == 1 and json.loads(p.stdout)["failures"][0]["field"] == "structure:language_create:English"


def test_the_languages_section_is_parsed_into_the_capture(tmp_path):
    parse = SCRIPTS / "parse_profile.py"
    capture = {"url": BASE, "name": "Ana Example", "headline": "Analyst", "about": "x",
               "experience": {"found": True, "groups": []}, "education": {"found": True, "items": []},
               "skills": {"count": 1, "items": ["SQL"]}, "profile_languages": ["Español"],
               "languages": {"found": True, "items": [["Spanish", "Native or bilingual proficiency"],
                                                      ["English", "Professional working proficiency"]]}}
    src, out = tmp_path / "cap.json", tmp_path / "current.json"
    src.write_text(json.dumps(capture))
    p = subprocess.run([sys.executable, "-B", str(parse), src, "--output", out, "--today", "2026-10-26"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    langs = json.loads(out.read_text())["languages"]
    assert [(x["language"], x["proficiency"]) for x in langs] == [("Spanish", "Native or bilingual proficiency"),
                                                                   ("English", "Professional working proficiency")]
