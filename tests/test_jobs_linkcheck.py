"""link_check.py: one offline verdict per job link (verified, official_ats, unverified), and the finding-jobs and
submitting-applications mapping that depends on it.

Real-use scenarios come first: a recruiter's WhatsApp message with a look-alike board, a real-shaped Lever link, a
Workday link, a scam Google Form, a bit.ly short link. Nothing here touches the network: the classifier is pure, and
one test blocks the socket layer to prove it.
"""
import ast
import json
import random
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
JOBS = REPO / "squads" / "jobs"
SCRIPTS = JOBS / "skills" / "jobs-contract" / "scripts"
LINK = SCRIPTS / "link_check.py"
DATA = SCRIPTS / "official_hosts.json"
FINDING = JOBS / "skills" / "finding-jobs"
SUBMIT = JOBS / "skills" / "submitting-applications"
JOB_KEY = SCRIPTS / "job_key.py"
SEEN = SCRIPTS / "seen_state.py"
STATUS = SCRIPTS / "status.py"
CHECK = SUBMIT / "scripts" / "check_submission.py"

sys.path.insert(0, str(SCRIPTS))
import jobs_common  # noqa: E402
import link_check as lc  # noqa: E402

SHIPPED = lc.load_data(DATA)
ACME_LEVER = "https://jobs.lever.co/acme/8f2c1d7e-1111-2222-3333-444455556666"
ACME_WORKDAY = "https://acme.wd5.myworkdayjobs.com/en-US/External/job/Lima/Data-Analyst_R123"
ACME_GREENHOUSE = "https://boards.greenhouse.io/acme/jobs/4012345"
WHATSAPP_LOOKALIKE = "https://boards-greenhouse.io/acme/jobs/123"
SCAM_FORM = "https://docs.google.com/forms/d/e/1FAIpQLScExampleApplicantForm/viewform"
BITLY = "https://bit.ly/3xYzAcme"


def run(*args, script=LINK, stdin=None):
    return subprocess.run([sys.executable, str(script), *args], input=stdin, capture_output=True, text=True,
                          encoding="utf-8", timeout=60)


def classify(url, company=None, data=None):
    return lc.classify(url, data or SHIPPED, company=company)


@pytest.fixture
def reviewed(tmp_path):
    """The shipped list plus two boards a reviewer confirmed on the employer's careers page."""
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    doc["reviewed_boards"] = [
        {"url": "https://boards.greenhouse.io/acme", "company": "Acme", "reviewed_on": "2026-10-20"},
        {"url": "https://acme.wd5.myworkdayjobs.com/External", "company": "Acme", "reviewed_on": "2026-10-20"},
    ]
    path = tmp_path / "official_hosts.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return lc.load_data(path)


# --- real-use scenarios ---------------------------------------------------------------------------------------------

def test_recruiter_whatsapp_lookalike_board_for_acme_is_unverified():
    result = classify(WHATSAPP_LOOKALIKE, company="Acme")
    assert result["verdict"] == "unverified"
    assert "lookalike_host" in result["flags"]
    assert result["board_url"] is None and result["manual_checks"] == []
    assert any(g.startswith("Do not open, fill in, log in to or send documents") for g in result["guidance"]), \
        result["guidance"]
    assert any("open its own careers page" in g for g in result["guidance"]), result["guidance"]


def test_recruiter_lookalike_stays_unverified_even_with_a_reviewed_list(reviewed):
    assert classify(WHATSAPP_LOOKALIKE, company="Acme", data=reviewed)["verdict"] == "unverified"


def test_real_shaped_lever_link_is_official_ats_with_manual_checks():
    result = classify(ACME_LEVER, company="Acme")
    assert result["verdict"] == "official_ats"
    assert (result["ats"], result["owner"], result["board_url"]) == ("lever", "acme", "https://jobs.lever.co/acme")
    assert result["flags"] == []
    assert len(result["manual_checks"]) == 3
    assert "same role" in result["manual_checks"][0]


def test_reviewed_greenhouse_board_is_verified_and_only_that_board(reviewed):
    result = classify(ACME_GREENHOUSE, company="Acme", data=reviewed)
    assert result["verdict"] == "verified" and result["reviewed"] is True
    assert result["flags"] == [] and result["manual_checks"] == []
    assert result["board_url"] == "https://boards.greenhouse.io/acme"
    # Another board on the same host is not blessed by the reviewed entry.
    assert classify("https://boards.greenhouse.io/otherco/jobs/9", data=reviewed)["verdict"] == "official_ats"


def test_an_agency_posting_on_a_manatal_career_page_is_an_employer_ats_link():
    """Recruitment agencies publish on Manatal's careers-page.com. Unknown, it blocked every automatic apply there."""
    posting = classify("https://www.careers-page.com/mineo/job/L4W9WY75", company="Mineo")
    assert (posting["verdict"], posting["board"]) == ("official_ats", "mineo")
    assert classify("https://www.careers-page.com/apply")["verdict"] == "unverified"  # Manatal's own form, no board
    assert classify("https://careers-page.com.jobs-offer.example/mineo/job/1")["verdict"] == "unverified"


def test_workday_link_gives_the_tenant_site_and_board_url():
    result = classify(ACME_WORKDAY, company="Acme")
    assert result["verdict"] == "official_ats"
    assert (result["ats"], result["owner"], result["board"]) == ("workday", "acme", "external")
    assert result["board_url"] == "https://acme.wd5.myworkdayjobs.com/External"


def test_workday_link_is_verified_only_for_the_reviewed_site(reviewed):
    assert classify(ACME_WORKDAY, company="Acme", data=reviewed)["verdict"] == "verified"
    other = "https://acme.wd5.myworkdayjobs.com/Careers/job/Lima/Analyst_R9"
    assert classify(other, company="Acme", data=reviewed)["verdict"] == "official_ats"


def test_scam_google_form_is_unverified_with_form_guidance():
    result = classify(SCAM_FORM, company="Acme")
    assert result["verdict"] == "unverified" and result["kind"] == "form"
    assert "form" in result["flags"]
    assert any("not a job posting" in g for g in result["guidance"])


def test_bitly_short_link_is_unverified_and_says_expand_it_yourself():
    result = classify(BITLY, company="Acme")
    assert result["verdict"] == "unverified" and result["flags"] == ["shortener"]
    assert any("Expand it yourself in a browser" in g for g in result["guidance"]), result["guidance"]


def test_whatsapp_chat_link_is_unverified():
    result = classify("https://wa.me/15550100")
    assert result["verdict"] == "unverified" and result["flags"] == ["messaging"]


def test_cli_prints_one_verdict_line_and_exits_zero_for_every_class():
    lines = {}
    for url in (ACME_LEVER, WHATSAPP_LOOKALIKE, BITLY):
        proc = run(url, "--company", "Acme")
        assert proc.returncode == 0, proc.stderr
        lines[url] = proc.stdout.splitlines()[0]
        assert lines[url].startswith("verdict: "), proc.stdout
    assert lines[ACME_LEVER].startswith("verdict: official_ats")
    assert lines[WHATSAPP_LOOKALIKE].startswith("verdict: unverified")
    assert lines[BITLY].startswith("verdict: unverified")


def test_cli_json_has_the_fields_the_skills_read():
    proc = run(ACME_LEVER, "--company", "Acme", "--json")
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    for field in ("verdict", "flags", "reasons", "manual_checks", "guidance", "board_url", "host", "kind", "ats"):
        assert field in doc, field


# --- the look-alike and malformed-link rules ------------------------------------------------------------------------

LOOKALIKES = [
    ("https://evil-greenhouse.io/acme/jobs/1", "lookalike_host"),          # prefix
    ("https://job-boards.greenhouse.io.evil.com/acme/jobs/1", "lookalike_host"),  # suffix
    ("https://boards.greenhouse.io@evil.example/x", "userinfo"),          # userinfo
    ("https://user:pw@boards.greenhouse.io/acme/jobs/1", "userinfo"),
    ("https://xn--boards-greenhouse-5ub.io/acme", "punycode_host"),      # punycode
    ("https://b\u043eards.greenhouse.io/acme/jobs/1", "non_ascii_host"),  # Cyrillic o homoglyph
    ("https://192.168.10.5/acme", "ip_literal"),                          # IPv4 literal
    ("https://[2001:db8::1]/acme", "ip_literal"),                         # IPv6 literal
    ("javascript:alert(1)", "scheme_not_http"),
    ("ftp://boards.greenhouse.io/acme", "scheme_not_http"),
    ("https://greenhouse.io/careers", "bare_apex"),
    ("https://boards.greenhouse.io", "no_board_path"),
    ("https://boards.greenhouse.io/embed/job_board?for=acme", "reserved_board"),
    ("https://boards.greenhouse.io:8443/acme", "unusual_port"),
    ("https://boards.greenhouse.io\\@evil.example/acme", "backslash"),
    ("https://boards.greenhouse.io/acme\u200b/jobs/1", "invisible_char"),
    ("https://unknown-company.example/careers/1", "unknown_host"),
    ("https://linkedin.com/feed/", "not_a_posting"),
    ("https://acme.bamboohr.com/", "no_board_path"),
    ("", "empty"),
    ("boards.greenhouse.io/acme/jobs/1", "no_scheme"),
]


@pytest.mark.parametrize("url,flag", LOOKALIKES, ids=[f for _, f in LOOKALIKES])
def test_lookalike_and_malformed_links_are_unverified(url, flag):
    result = classify(url, company="Acme")
    assert result["verdict"] == "unverified", result
    assert flag in result["flags"], result["flags"]
    assert result["board_url"] is None and result["manual_checks"] == []
    assert result["guidance"], "unverified links carry anti-scam guidance"


def test_bamboohr_careers_board_is_official_ats():
    result = classify("https://acme.bamboohr.com/careers/12")
    assert result["verdict"] == "official_ats" and result["board_url"] == "https://acme.bamboohr.com/careers"


def test_linkedin_posting_page_is_official_ats_not_verified():
    assert classify("https://linkedin.com/jobs/view/4012345678/")["verdict"] == "official_ats"


def test_http_downgrade_is_flagged_and_never_verified(reviewed):
    result = classify("http://boards.greenhouse.io/acme/jobs/4012345", company="Acme", data=reviewed)
    assert result["verdict"] == "official_ats"
    assert result["flags"] == ["http_not_https"]
    assert any("plain http" in r for r in result["reasons"])


def test_unknown_company_domain_is_unverified_with_employer_guidance():
    result = classify("https://careers.acme-example.com/job/123", company="Acme")
    assert result["verdict"] == "unverified"
    assert any("employer's own careers page" in g for g in result["guidance"])


# --- board_company_mismatch -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("company,mismatch", [
    ("Globex Industries", True),
    ("Acme", False),
    ("Acme Corp", False),
    ("\u00c1cme", False),      # accent-folded
    (None, False),              # no company given: nothing to compare
    ("\u042f\u043d\u0434\u0435\u043a\u0441", False),  # no Latin letters: never flagged
])
def test_verified_board_company_mismatch(reviewed, company, mismatch):
    result = lc.classify(ACME_GREENHOUSE, reviewed, company=company)
    assert result["verdict"] == "verified", result
    assert ("board_company_mismatch" in result["flags"]) is mismatch, (company, result["flags"])
    if mismatch:
        assert result["manual_checks"], "a mismatch carries the manual checks"
        assert "does not match company 'Globex Industries'" in result["reasons"][0]


# --- the reviewed list ----------------------------------------------------------------------------------------------

def test_shipped_list_verifies_nothing_until_a_reviewer_adds_a_board():
    assert SHIPPED["reviewed"] == set()
    for url in (ACME_GREENHOUSE, ACME_LEVER, ACME_WORKDAY, "https://jobs.ashbyhq.com/acme"):
        assert classify(url, company="Acme")["verdict"] != "verified"


def test_reviewed_entry_with_a_posting_path_is_refused(tmp_path):
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    doc["reviewed_boards"] = [{"url": "https://boards.greenhouse.io/acme/jobs/4012345"}]
    path = tmp_path / "official_hosts.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    data = lc.load_data(path)
    assert data["reviewed"] == set()
    assert any("ignored" in w for w in data["warnings"])
    assert classify(ACME_GREENHOUSE, data=data)["verdict"] == "official_ats"


def test_unreadable_list_fails_safe_and_the_cli_still_exits_zero(tmp_path):
    folder = tmp_path / "scripts"
    folder.mkdir()
    shutil.copy(LINK, folder / "link_check.py")
    shutil.copy(SCRIPTS / "jobs_common.py", folder / "jobs_common.py")
    (folder / "official_hosts.json").write_text("{not json", encoding="utf-8")
    proc = run(ACME_LEVER, script=folder / "link_check.py")
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.startswith("verdict: unverified")
    assert "official_hosts_unreadable" in proc.stdout


def test_wrong_shape_list_is_refused(tmp_path):
    path = tmp_path / "official_hosts.json"
    path.write_text(json.dumps({"ats": "nope"}), encoding="utf-8")
    with pytest.raises(lc.DataError):
        lc.load_data(path)


# --- regional LinkedIn hosts and reviewed job boards -----------------------------------------------------------------
# Country hosts (mx, br, co, cl, uk, de) serve the same portal as www.linkedin.com: a posting there is official_ats
# and is read through the portal's detail command.

REGIONAL_LINKEDIN = [
    "https://mx.linkedin.com/jobs/view/senior-data-analyst-at-acme-4444395323",
    "https://br.linkedin.com/jobs/view/analista-de-dados-senior-presencial-ciudad-ejemplo-at-acme-4478906767",
    "https://co.linkedin.com/jobs/view/analista-de-datos-y-bi-at-acme-4480537356",
    "https://cl.linkedin.com/jobs/view/analista-de-datos-at-acme-4475249000",
    "https://uk.linkedin.com/jobs/view/data-analyst-at-acme-4475249001",
    "https://de.linkedin.com/jobs/view/data-analyst-at-acme-4475249002",
    "https://www.linkedin.com/jobs/view/4012345678/",
]


@pytest.mark.parametrize("url", REGIONAL_LINKEDIN)
def test_regional_linkedin_posting_is_official_ats_like_www(url):
    result = classify(url, company="Acme")
    assert result["verdict"] == "official_ats", result
    assert result["kind"] == "portal" and result["ats"] == "linkedin"
    assert "lookalike_host" not in result["flags"] and "not_a_posting" not in result["flags"], result["flags"]


def test_a_country_host_and_www_give_the_same_verdict_for_the_same_posting():
    regional = classify(REGIONAL_LINKEDIN[1], company="Acme")["verdict"]
    www = classify("https://www.linkedin.com/jobs/view/4478906767/", company="Acme")["verdict"]
    assert regional == www == "official_ats"


@pytest.mark.parametrize("url", [
    "https://linkedin.com.evil.example/jobs/view/4012345678/",
    "https://mx.linkedin.com.evil.example/jobs/view/4012345678/",
    "https://linkedin-jobs.example/jobs/view/4012345678/",
    "https://www.linkedin.co/jobs/view/4012345678/",
])
def test_linkedin_look_alikes_stay_unverified(url):
    result = classify(url, company="Acme")
    assert result["verdict"] == "unverified", result
    assert "lookalike_host" in result["flags"] or "unknown_host" in result["flags"], result["flags"]


def test_a_regional_linkedin_non_posting_page_is_unverified_like_the_www_host():
    # not_a_posting is a hard flag: a regional feed page is no posting, exactly as linkedin.com/feed/ is.
    regional = classify("https://mx.linkedin.com/feed/", company="Acme")
    www = classify("https://www.linkedin.com/feed/", company="Acme")
    assert regional["verdict"] == www["verdict"] == "unverified"
    assert "not_a_posting" in regional["flags"]


def test_a_domain_that_only_begins_with_linkedin_is_not_a_regional_host():
    # The wildcard covers subdomains of linkedin.com only; a domain that merely contains the name is a look-alike.
    assert classify("https://linkedin.com.example/jobs/view/4012345678/")["verdict"] == "unverified"


JOB_BOARD_POSTINGS = [
    "https://www.getonbrd.com/jobs/programming/gtm-engineer-acme-remote",
    "https://himalayas.app/companies/acme/jobs/data-analyst",
    "https://torre.ai/post/NrJOVmJW-acme-ai-technical-lead-engineer-4",
    "https://www.whatjobs.com/job/sample-job-example-url",
    "https://uk.whatjobs.com/job/sample-job-example-url",
    "https://remoteok.com/remote-jobs/remote-account-manager-acme-1137528",
    "https://weworkremotely.com/remote-jobs/acme-data-analyst",
    "https://www.wellfound.com/company/acme/jobs/4690673-software-engineer",
    "https://www.bumeran.com.ar/empleos/operario-a-de-mantenimiento-acme-1118482032.html",
    "https://www.bumeran.com.pe/empleos/docente-de-derecho-acme-1118353433.html",
    "https://cl.computrabajo.com/ofertas-de-trabajo/oferta-de-trabajo-de-digitadora-en-santiago-C2DA875214A5C67961373E686DCF3405",
    "https://www.glassdoor.com.mx/job-listing/data-analyst-acme-JV_IC1132277_KO0,11_KE12,16.htm?jl=1010264134454",
]


@pytest.mark.parametrize("url", JOB_BOARD_POSTINGS)
def test_reviewed_job_board_posting_is_job_board_not_unverified(url):
    result = classify(url, company="Acme")
    assert result["verdict"] == "job_board", result
    assert result["kind"] == "job_board"
    assert result["manual_checks"], "a board is not the employer: the manual checks are carried"
    assert not [f for f in result["flags"] if f not in lc.SOFT_FLAGS], result["flags"]


@pytest.mark.parametrize("url", [
    "https://remoteok.com/",
    "https://www.getonbrd.com/jobs/",
    "https://torre.ai/sub/us-software-development/jobs/13",
])
def test_a_job_board_listing_page_is_not_a_posting(url):
    result = classify(url, company="Acme")
    assert result["verdict"] == "unverified" and "not_a_posting" in result["flags"], result


def test_a_look_alike_of_a_job_board_is_unverified():
    for url in ("https://remoteok.com.evil.example/remote-jobs/x-1", "https://getonbrd-jobs.example/jobs/programming/x"):
        assert classify(url, company="Acme")["verdict"] == "unverified", url


def test_job_board_verdict_has_a_render_and_a_json_shape():
    proc = run("https://www.getonbrd.com/jobs/programming/gtm-engineer-acme-remote", "--company", "Acme")
    assert proc.returncode == 0 and proc.stdout.startswith("verdict: job_board"), proc.stdout


def test_the_job_board_list_names_the_reviewed_boards_and_every_pattern_compiles():
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    assert doc["schema"] == 2 and doc["job_boards"], "the reviewed boards are in the list"
    brands = {b["brand"] for b in doc["job_boards"]}
    assert {"getonbrd", "himalayas", "torre", "whatjobs", "remoteok", "weworkremotely", "wellfound",
            "computrabajo", "bumeran", "indeed", "glassdoor"} <= brands
    loaded = lc.load_data(DATA)["job_boards"]
    assert len(loaded) == len(doc["job_boards"])
    assert all(row["path_re"].pattern and row["hosts"] for row in loaded)


def test_a_bad_job_board_pattern_is_refused_not_silently_skipped(tmp_path):
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    doc["job_boards"].append({"id": "broken", "brand": "broken", "hosts": ["broken.example"], "path": "^/x(["})
    path = tmp_path / "official_hosts.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(lc.DataError):
        lc.load_data(path)


# --- offline, stdlib, Python 3.9 -------------------------------------------------------------------------------------

def test_classification_never_touches_the_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("network access during link_check")

    class NoSocket:
        def __init__(self, *args, **kwargs):
            refuse()

    monkeypatch.setattr(socket, "socket", NoSocket)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    for url in (ACME_LEVER, ACME_WORKDAY, WHATSAPP_LOOKALIKE, BITLY, SCAM_FORM):
        classify(url, company="Acme")


def test_script_imports_only_offline_modules():
    banned = ("socket", "http", "ssl", "requests", "subprocess", "ftplib", "smtplib", "urllib.request")
    tree = ast.parse(LINK.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            assert not name.startswith(banned), f"link_check imports {name}"


def test_script_parses_as_python_39():
    ast.parse(LINK.read_text(encoding="utf-8"), feature_version=(3, 9))


def test_every_flag_the_classifier_can_raise_has_a_reason():
    rng = random.Random(7)
    alphabet = "abcxyz-./:@[]\\%#?\u200b\u043e0123 "
    corpus = [WHATSAPP_LOOKALIKE, ACME_WORKDAY, BITLY, SCAM_FORM, "", "https://", "https://a@b:x/",
              "https://xn--a.io/x", "https://[::1]/x"]
    corpus += ["https://boards.greenhouse.io/" + "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 25)))
               for _ in range(300)]
    seen_flags = set()
    for url in corpus:
        result = lc.classify(url, SHIPPED, company="Acme")
        assert result["verdict"] in ("verified", "official_ats", "unverified")
        assert len(result["reasons"]) == len(result["flags"])
        seen_flags.update(result["flags"])
    assert seen_flags <= set(lc.REASONS), seen_flags - set(lc.REASONS)


def test_help_exits_zero_and_a_missing_url_is_a_usage_error():
    assert run("--help").returncode == 0
    proc = run()
    assert proc.returncode == 2 and "usage" in proc.stderr


# --- finding-jobs: the documented mapping, end to end on a tmp project ------------------------------------------------

def _section(text, heading):
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start:] if end < 0 else text[start:end]


def test_finding_jobs_mapping_matches_what_link_check_returns(tmp_path):
    intake = (FINDING / "references" / "intake-safety.md").read_text(encoding="utf-8")
    skill = (FINDING / "SKILL.md").read_text(encoding="utf-8")
    table = _section(intake, "## Link check")
    # The reference names each verdict, the label and the flag, and the JSON fields it reads.
    for verdict in ("`verified`", "`official_ats`", "`unverified`"):
        assert verdict in table
    assert "`unverified_link`" in table and "FLAG" in table and "link_verdict:" in table
    for field in ("verdict", "flags", "reasons", "manual_checks", "guidance", "board_url"):
        assert f"`{field}`" in table, field
    assert "link_check.py" in skill and "--company" in skill and "--json" in skill
    assert "`unverified_link`" in (FINDING / "references" / "filter-rules.md").read_text(encoding="utf-8")
    assert "`unverified_link`" in (JOBS / "skills" / "jobs-contract" / "references" / "opening-files.md").read_text(
        encoding="utf-8")

    # A search card with three candidates: the scout runs the check, then saves every row (never discards one).
    project = tmp_path / "project"
    project.mkdir()
    (project / "profile.md").write_text("---\nsearch: active\n---\n", encoding="utf-8")
    candidates = [
        {"title": "Data analyst", "url": WHATSAPP_LOOKALIKE},
        {"title": "Data analyst (Lima)", "url": ACME_LEVER},
        {"title": "Data Analyst R123", "url": ACME_WORKDAY},
    ]
    entries, verdicts = [], {}
    for item in candidates:
        proc = run(item["url"], "--company", "Acme", "--json")
        assert proc.returncode == 0, proc.stderr
        doc = json.loads(proc.stdout)
        verdicts[item["url"]] = doc
        key = subprocess.run([sys.executable, str(JOB_KEY), "--company", "Acme", "--title", item["title"],
                              "--url", item["url"]], capture_output=True, text=True, check=True).stdout.strip()
        # The procedure passes --url and --project: two candidates for one company can share a readable id, and the
        # project check gives the second one its own folder.
        opening = subprocess.run([sys.executable, str(JOB_KEY), "--company", "Acme", "--title", item["title"],
                                  "--url", item["url"], "--opening-id", "--date", "2026-10-20",
                                  "--project", str(project)], capture_output=True, text=True,
                                 check=True).stdout.strip()
        labels = ["unverified_link"] if doc["verdict"] == "unverified" else []
        filter_value = "FLAG" if labels else "PASS"
        folder = project / "openings" / opening
        folder.mkdir(parents=True)
        (folder / "opening.md").write_text(
            "---\n"
            f"id: {opening}\nkey: {key}\ncompany: Acme\nrole: {item['title']}\nurl: {item['url']}\n"
            f"link_verdict: {doc['verdict']}\nfilter: {filter_value}\n"
            f"filter_reasons: {json.dumps(doc['reasons'], ensure_ascii=False)}\n"
            f"labels: {json.dumps(labels)}\n---\nposting text\n",
            encoding="utf-8")
        entries.append({"key": key, "company": "Acme", "title": item["title"], "url": item["url"],
                        "portal": "user link", "opening_id": opening, "posted_at": "2026-10-19"})

    batch = project / "batch.json"
    batch.write_text(json.dumps(entries), encoding="utf-8")
    added = subprocess.run([sys.executable, str(SEEN), "add", "--project", str(project), "--file", str(batch),
                            "--today", "2026-10-20"], capture_output=True, text=True)
    assert added.returncode == 0, added.stderr
    assert len(json.loads(added.stdout)["added"]) == 3

    state = json.loads((project / "searches" / "seen.json").read_text(encoding="utf-8"))["seen"]
    assert all(state[e["key"]]["status"] == "new" for e in entries), "the unverified row is kept, not skipped"

    for e in entries:
        folder = project / "openings" / e["opening_id"]
        meta = jobs_common.read_front_matter(folder / "opening.md")
        verdict = verdicts[e["url"]]["verdict"]
        assert meta["link_verdict"] == verdict
        if verdict == "unverified":
            assert meta["labels"] == ["unverified_link"] and meta["filter"] == "FLAG"
            assert meta["filter_reasons"], "the reasons from link_check are recorded"
        else:
            assert meta["labels"] == [] and meta["filter"] == "PASS"
        status = subprocess.run([sys.executable, str(STATUS), "append", str(folder), "found", "--by", "jobs-scout"],
                                capture_output=True, text=True)
        assert status.returncode == 0, status.stderr


# --- submitting-applications: an unverified apply_url is kit only ---------------------------------------------------

def test_submitting_applications_never_submits_an_unverified_apply_url():
    skill = SUBMIT.joinpath("SKILL.md").read_text(encoding="utf-8")
    assert "link_check.py" in skill and "`unverified`" in skill
    assert "kit only" in skill and "NOT_POSSIBLE" in skill
    assert "Never auto-submit an `unverified` apply_url" in skill
    assert classify(BITLY)["verdict"] == "unverified"
    assert classify(WHATSAPP_LOOKALIKE)["verdict"] == "unverified"
    assert classify(ACME_LEVER)["verdict"] == "official_ats"


def test_kit_only_path_is_accepted_by_the_validator(tmp_path):
    """The NOT_POSSIBLE path an unverified apply_url takes is valid, with kit.md beside the file."""
    opening = "JOB-20261020-acme-data-analyst"
    app = tmp_path / "openings" / opening / "application"
    app.mkdir(parents=True)
    (app / "kit.md").write_text("Answers ready to copy.\n", encoding="utf-8")
    data = {"id": opening, "result": "NOT_POSSIBLE", "method": "other", "filled_fields": [],
            "pending_questions": [], "screenshots": [], "reason": "apply_url unverified: kit only",
            "manual_kit": "application/kit.md"}
    path = app / "submission.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(CHECK), str(path)], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "valid: NOT_POSSIBLE" in proc.stdout
