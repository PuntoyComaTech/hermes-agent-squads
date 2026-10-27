#!/usr/bin/env python3
"""Personalised fit for one saved opening: gates, weighted score, band, decision, salary, employer-call advice.

The agent writes the judgment in analysis.json: requirements, evidence, the four dimension scores (each with a
one-line note), strengths, gaps. This script adds what the files decide: the eligibility, language, location and
seniority gates, deal-breaker and avoid-list hits, the weighted score and band from profile.md, the decision the
rules give, the salary benchmark, employer-call advice, and the guard verdict, dates and id from opening.md.

The opening text is untrusted. It is only searched for phrases, never run or followed.

Subcommands (JSON on stdout; errors on stderr, exit 1):
  rubric   --project P                         scoring rubric and candidate summary for batch triage
  years    --project P                         total and per-title years from the dated experiences
  screen   --project P --text FILE [--company C]   deal-breaker and eligibility-wording hits in cleaned text
  cache    --project P --company C             is companies/<slug>.md fresh enough to reuse?
  check    OPENING_DIR --project P             validate analysis.json; writes nothing
  finalize OPENING_DIR --project P             validate, compute the derived fields, write analysis.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jobs-contract" / "scripts"))
import jobs_common as jc  # noqa: E402
import salary_lookup as sl  # noqa: E402
import posting_guard as pg  # noqa: E402
import seen_state as ss  # noqa: E402

GATE_NAMES = jc.GATE_NAMES
REQUIRED_LISTS = ("must_have", "nice_to_have", "responsibilities", "tools", "keywords", "disqualifiers", "priorities")
DIMENSIONS = ("technical", "experience", "behavioral", "career")
DEFAULT_POLICY = {"flag_gap_steps": 1, "discard_gap_steps": 2}
DEFAULT_SENIORITY_MARGIN = 1
DEFAULT_SENIORITY_BASIS = "total"  # total: every years requirement compares with the total; role: lead years with lead titles
CACHE_DAYS = 30  # companies/<slug>.md is reused while younger than this
DEFAULT_OVERSELLING = "low"
CLIP = 160

DIMENSION_GUIDE = {
    "technical": "Required and preferred skills versus the candidate's skills. 80-100: core requirements are the "
                 "candidate's primary skills. 60-79: most match, 1-2 learnable gaps. 40-59: partial, real upskilling. "
                 "0-39: fundamental mismatch. A tool or method the candidate has not used, in a family they work in "
                 "(another database, cloud, framework or AI technique), is a learnable gap: it costs a few points, "
                 "never a band.",
    "experience": "Function and nature of past work versus the role, not the job title. 80-100: same domain and role "
                  "type. 60-79: related, transfer is clear. 40-59: adjacent, the case must be argued. 0-39: unrelated.",
    "behavioral": "Culture and working style versus behavioral.thrives_in and behavioral.avoid. 80-100: strong match. "
                  "60-79: mixed but compatible. 40-59: some friction. 0-39: significant mismatch.",
    "career": "Advances career_goals and holds energizers rather than drains; security, flexibility and growth "
              "included. 80-100: strongly aligned, clear path. 60-79: partly aligned. 40-59: decent but builds little. "
              "0-39: dead end or step backwards.",
}

# --- eligibility wording -------------------------------------------------------------------------------------------
# Patterns run on folded text: accents removed, lower case, punctuation as spaces ("H-1B" is "h 1b", "U.S." is
# "u s"). The posting is split into clauses first, so a refusal and the country it names can sit in two clauses.

# Sponsorship refused: no visa sponsorship, not able to provide sponsorship, sin patrocinio, keine Visa, ...
REFUSE_RE = re.compile(
    r"\bno (?:visa )?sponsor\w*|"
    r"\bwithout (?:visa )?sponsor\w*|"
    r"\bsponsorship (?:is )?(?:not|no|unavailable)\b|"
    r"\b(?:not|unable|cannot|can not|can t|won t|will not|do not|don t|does not|doesn t|never)\s+"
    r"(?:\w+\s+){0,5}?sponsor\w*|"
    r"\b(?:no|nao)\s+(?:\w+\s+){0,3}?(?:patrocin\w*|parrain\w*)|"
    r"\b(?:sin|sem|ohne|sans|kein|keine|keinen|pas de)\s+(?:\w+\s+){0,2}?"
    r"(?:patrocin\w*|sponsor\w*|parrain\w*|visa\w*|visum\w*|aufenthalt\w*)"
)
# A refusal worded as an inability to support visas or work permits, or as 'visa support is not provided'.
VISA_REFUSE_RE = re.compile(
    r"\b(?:unable|not able|cannot|can not|can t|won t|will not|do not|don t|does not|doesn t|never)\s+"
    r"(?:\w+\s+){0,2}?(?:support|provide|offer|give|accept)\w*\s+(?:\w+\s+)?(?:visas?|work permits?)\b|"
    r"\b(?:visa|work permit|immigration) (?:support|sponsorship|assistance)\s+(?:is\s+)?(?:not|no)\s+(?:\w+\s+)?"
    r"(?:provided|offered|available|possible|given)\b"
)
# Sponsorship offered: visa sponsorship is available, we sponsor visas.
OFFER_RE = re.compile(
    r"\b(?:offer|provide|support|sponsor|will sponsor|can sponsor)\w*\s+(?:\w+\s+){0,2}?(?:visa|sponsorship)\b|"
    r"\bsponsorship (?:is )?(?:available|provided|offered)\b|"
    r"\bwe sponsor\b|"
    r"\bvisa sponsorship (?:available|provided)\b"
)
# Authorisation the candidate must already hold: citizenship, nationality, residence, right or permit to work.
AUTH_RE = re.compile(
    r"\b(?:citizens?|citizenship|nationals? only|nationals? of|ressortissants?|staatsburger\w*|"
    r"staatsangehorig\w*|ciudadan\w*|cidadao\w*|cidadania|citoyen\w*|nacionales|"
    r"residents? only|permanent residents?|permanent residency|residency required|residents? of|"
    r"residentes?|residencia\w*|green card|"
    r"right to work|eligible to work|entitled to work|authori[sz]ed to work|legally (?:authori[sz]ed|eligible)|"
    r"authori[sz]ation to work|work authori[sz]ation|work permit|permiso de trabajo|permissao de trabalho|"
    r"permis de travail|autorizacion de trabajo|autorizacao de trabalho|autorisation de travail|"
    r"arbeitserlaubnis|aufenthaltserlaubnis|arbeitsberechtigung|direito de trabalhar|derecho a trabajar|"
    r"droit de travailler|security clearance|background clearance|clearance required|e ?verify|"
    r"ability to work legally|legally work)\b"
)
# H-1B is a US work visa. Without an offer it names a US authorisation, so it counts as authorisation for US.
H1B_RE = re.compile(r"\bh ?1 ?b\b")
# Wording about work status that no other pattern classified. For a sponsorship-dependent candidate it is a FLAG.
# Generic words such as "authorization" are left out: a server authorization or a visa card would flag every posting.
UNKNOWN_RE = re.compile(
    r"\b(?:visa (?:sponsor\w*|work\w*|status|process|support|requirements?|required|eligib\w*|holders?|"
    r"applications?|types?)|sponsor\w*|patrocin\w*|parrain\w*|visum|residenc\w*|residencia|immigrat\w*|"
    r"aufenthalt\w*|arbeitserlaub\w*|work (?:status|eligib\w*|visa)|legal(?:ly)? (?:to )?(?:work|live|reside|employ)\w*)\b"
)
# Country names as postings write them, matched against folded clauses.
COUNTRY_TERMS = (
    ("US", r"\busa\b|\bunited states\b|\bu s\b|\b(?:the|in) us\b|"
           r"\bus (?:citizens?|residents?|only|based|work\w*|authori\w*|law|persons?|sponsorship|passport|employers?)\b|"
           r"\bh ?1 ?b\b|\bus time ?zones?\b"),
    ("PE", r"\bperu\w*|\bperuvian\w*|\bperuan\w*"),
    ("ES", r"\bspain\b|\bespana\b|\bspanish (?:citizens?|residents?|nationals?)\b"),
    ("DE", r"\bgermany\b|\bdeutschland\b|\bgerman (?:citizens?|residents?|nationals?)\b"),
    ("FR", r"\bfrance\b|\bfrench (?:citizens?|residents?|nationals?)\b"),
    ("GB", r"\bunited kingdom\b|\buk\b|\bgreat britain\b|\bbritish (?:citizens?|residents?|nationals?)\b|\bengland\b"),
    ("CA", r"\bcanada\b|\bcanadian\w*"),
    ("MX", r"\bmexico\b|\bmexican\w*|\bmexicanos?\b"),
    ("BR", r"\bbrazil\w*|\bbrasil\b|\bbrasileir\w*"),
    ("CO", r"\bcolombia\w*|\bcolombian\w*"),
    ("CL", r"\bchile\b|\bchilen\w*"),
    ("AR", r"\bargentin\w*"),
    ("IE", r"\bireland\b|\birish (?:citizens?|residents?)\b"),
    ("CY", r"\bcyprus\b|\bcypriot\w*"),
)
COUNTRY_RES = [(code, re.compile(pattern)) for code, pattern in COUNTRY_TERMS]

# --- deal-breakers, location and skills -----------------------------------------------------------------------------

# Negation words: a deal-breaker phrase next to one of these in its clause does not match ("No travel required").
NEGATIONS = {"no", "not", "none", "never", "without", "zero", "don", "doesn", "won", "cannot", "cant", "unable",
             "unavailable", "t", "nie", "nicht", "kein", "keine", "keinen", "ohne", "sin", "sem", "nao", "nunca",
             "sans", "pas", "ni", "ningun", "ninguna"}
# Work mode belongs to the location gate. A phrase made only of these words never counts as a deal-breaker, so
# "remote or hybrid" cannot reject a posting whose work mode the user accepts.
WORK_MODE_WORDS = {"remote", "remoto", "remota", "hybrid", "hybrida", "hibrido", "hibrida", "onsite", "site",
                   "presencial", "presential", "office", "oficina"}
WORK_FILLER = {"or", "and", "only", "on", "in", "a", "an", "the", "fully", "work", "from", "home", "based", "of",
               "to", "with", "o", "y", "ou", "und", "oder"}

# Seniority: the years a posting asks for, and the words that say what kind of years.
# "5+ years", "5 years plus", "3-5 years" (the lower bound is what must be met) and "3 a 5 años".
YEARS_RE = re.compile(
    r"(?:(\d{1,2}(?:[.,]\d)?)\s*(?:-|to|a|bis|–)\s*)?(?<![\d.,])(\d{1,2}(?:[.,]\d)?)\s*(?:\+|plus\b)?\s*"
    r"(?:years?|yrs?|anos?|a[nñ]os|jahre?n?|ans)\b",
    re.I,
)
ROLE_WORDS = {"lead": "lead", "leader": "lead", "manager": "manager", "head": "head", "director": "director"}
ROLE_PREFIX = {"as", "a", "an", "in", "the", "of", "experience", "experiences", "background", "technical", "tech",
               "team", "engineering", "senior", "product", "people", "hands", "on", "current", "previous", "prior"}
EXPERIENCE_WORDS = {"experience", "experiences", "background"}
CORE_WORDS = {"software", "engineering", "development", "programming", "coding", "tech", "technology", "it"}
FILLER_WORDS = {"of", "in", "a", "an", "the", "relevant", "professional", "hands", "on", "industry", "total",
                "overall", "work", "working", "prior", "previous", "proven", "solid", "strong", "commercial",
                "related", "and", "or"}
LINK_WORDS = {"in", "with", "using", "on", "for"}

# Credentials (a degree, a licence, a certification, a clearance) are told apart from skills only so the profile can
# choose strictness for each kind; by default neither kind rejects.
CREDENTIAL_RE = re.compile(
    r"\b(?:degree|bachelor\w*|master\w*|msc|bsc|phd|doctora\w*|diploma\w*|licen[cs]\w*|certif\w*|accredit\w*|"
    r"clearance|chartered|titulo|titulacion|grado|licenciatura|ingenier[oa] titulad\w*|abschluss|studium|"
    r"zertifi\w*|diplome|formacion universitaria|university)\b"
)


# Language: a required level written as a phrase, such as "english B2".
LANGUAGE_PHRASE_RE = re.compile(r"^\s*([^\d]+?)\s+([ABC][12])\s*$", re.I)

# Invitations to ask questions, for the employer-call advice.
INVITE_RE = re.compile(
    r"\b(any questions|questions are welcome|reach out to|feel free to contact|call me|call us|contact me)\b"
)


class AnalysisError(Exception):
    """analysis.json cannot be read or is not a JSON object. Reported on stderr with exit 1."""


# --- files --------------------------------------------------------------------------------------------------------

def read_opening(folder: Path):
    """(front matter, body) of opening.md; raises when the file is missing."""
    path = folder / "opening.md"
    if not path.is_file():
        raise AnalysisError(f"{path} not found")
    return jc.split_front_matter(path.read_text(encoding="utf-8", errors="ignore"))


def read_achievements(project: Path) -> dict:
    data = jc.read_data(project / "achievements.yaml")
    return data if isinstance(data, dict) else {}


def read_profile(project: Path) -> dict:
    return jc.read_front_matter(project / "profile.md")


def eligibility_rows(profile: dict) -> list:
    rows = profile.get("eligibility") or []
    return [row for row in rows if isinstance(row, dict) and row.get("country")]


def profile_market(profile: dict):
    market = profile.get("market") or {}
    country = market.get("country") if isinstance(market, dict) else None
    return str(country).upper() if country else None


def market_country(profile: dict, opening_fm: dict):
    mode = str(opening_fm.get("work_mode") or "").strip()
    if mode.lower().startswith("remote_country:"):
        return mode.split(":", 1)[1].strip().upper() or None
    return profile_market(profile)


def _countries_in(folded: str) -> set:
    return {code for code, pattern in COUNTRY_RES if pattern.search(folded)}


def default_country(profile: dict, opening_fm: dict):
    """The country that wording without a country name refers to. None when the posting does not place it.

    A country-specific remote role names its country. An onsite or hybrid role names its country in the place,
    else it is in the candidate's market. A remote-region or remote-global role names no country, so wording
    without a country is unplaced, not guessed.
    """
    mode = str(opening_fm.get("work_mode") or "").strip()
    base, _, arg = mode.lower().partition(":")
    if base == "remote_country":
        return arg.strip().upper() or None
    if base in ("onsite", "hybrid"):
        named = _countries_in(ss.fold(arg))
        if len(named) == 1:
            return named.pop()
        return profile_market(profile)
    if base:
        return None
    return profile_market(profile)


# --- hiring scope -------------------------------------------------------------------------------------------------
# Where a remote role may be done, as a set of ISO-3166 alpha-2 codes. One helper answers it for the location and the
# eligibility gates. Sources, first that applies: opening.md `hiring_countries` (every country the posting names),
# `remote_country:<CC>`, `remote_region:<name>` through REGIONS. A region name REGIONS does not hold is unresolved:
# FLAG, never PASS. `remote_global` and the worldwide names are no restriction.

_EU = "AT BE BG HR CY CZ DK EE FI FR DE GR IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split()
_EEA = _EU + "IS LI NO".split()
_EUROPE = _EEA + "GB CH UA MD RS ME MK AL BA XK BY AD MC SM VA TR GE AM AZ".split()
_MIDDLE_EAST = "AE BH IL IQ JO KW LB OM PS QA SA EG".split()
_AFRICA = ("DZ AO BJ BW BF BI CV CM CF TD KM CG CD CI DJ GQ ER SZ ET GA GM GH GN GW KE LS LR LY MG MW ML MR MU "
           "MA MZ NA NE NG RW ST SN SC SL SO ZA SS SD TZ TG TN UG ZM ZW").split()
_LATAM = "AR BO BR CL CO CR CU DO EC SV GT HN HT MX NI PA PY PE PR UY VE".split()
_NORTH_AMERICA = "US CA MX".split()
REGIONS = {
    "eu": _EU, "eea": _EEA, "europe": _EUROPE, "emea": _EUROPE + _MIDDLE_EAST + _AFRICA, "latam": _LATAM,
    "north_america": _NORTH_AMERICA, "us_canada": ["US", "CA"],
    "americas": _LATAM + _NORTH_AMERICA + "BZ GY SR JM TT BS BB".split(),
    "apac": "AU NZ JP KR CN HK TW SG MY TH VN PH ID IN PK BD LK NP KH LA MM MN BN".split(),
}
REGION_ALIASES = {
    "eu": "eu", "european union": "eu", "eu27": "eu", "eea": "eea", "eu eea": "eea", "eu and eea": "eea",
    "european economic area": "eea", "europe": "europe", "europa": "europe", "emea": "emea", "latam": "latam",
    "latin america": "latam", "latinoamerica": "latam", "america latina": "latam", "lac": "latam",
    "north america": "north_america", "north_america": "north_america", "norteamerica": "north_america",
    "us canada": "us_canada", "us and canada": "us_canada", "us_canada": "us_canada", "americas": "americas",
    "apac": "apac", "asia pacific": "apac",
}
WORLDWIDE = {"global", "worldwide", "anywhere", "world", "international", "mundo", "cualquier lugar"}
ISO2_RE = re.compile(r"^[A-Z]{2}$")


def hiring_scope(opening_fm: dict):
    """(kind, countries, label) of a remote opening; None when the role is not remote (onsite, hybrid, unknown).

    kind: "global" (no restriction), "countries" (countries is a set of ISO codes), "unresolved" (a region name
    REGIONS does not hold, or a hiring_countries entry that is not an ISO code). label names the scope in a reason.
    An explicit `hiring_countries` list wins over the country or region in work_mode.
    """
    mode = str(opening_fm.get("work_mode") or "").strip()
    base, _, arg = mode.partition(":")
    base, arg = base.strip().lower(), arg.strip()
    if base not in ("remote_global", "remote_region", "remote_country"):
        return None
    listed = opening_fm.get("hiring_countries")
    if isinstance(listed, str):
        listed = [part for part in re.split(r"[,\s]+", listed) if part]
    if isinstance(listed, list) and listed:
        codes = list(dict.fromkeys(str(code).strip().upper() for code in listed))
        bad = [code for code in codes if not ISO2_RE.match(code)]
        if bad:
            return "unresolved", None, f"hiring_countries {', '.join(bad)} (not ISO country codes)"
        return "countries", set(codes), ", ".join(codes)
    if base == "remote_global":
        return "global", None, "anywhere"
    if base == "remote_country":
        code = arg.upper()
        return ("countries", {code}, code) if ISO2_RE.match(code) else ("unresolved", None, f"remote_country:{arg}")
    key = re.sub(r"[^a-z0-9_]+", " ", ss.fold(arg)).strip()
    if key in WORLDWIDE:
        return "global", None, "anywhere"
    region = REGION_ALIASES.get(key)
    if not region:
        return "unresolved", None, arg or "an unnamed region"
    return "countries", set(REGIONS[region]), region.replace("_", " ").upper()


def scope_check(profile: dict, opening_fm: dict):
    """(kind, verdict, note) of the hiring scope against the candidate's countries; None when the role is not remote.

    kind: "open" (global, or the scope holds a workable country), "sponsorship" (the scope's only listed countries
    the candidate has a row for need sponsorship), "outside" (no country of the scope is workable), "unresolved".
    Workable: an eligibility row with a status in WORKABLE_STATUSES, plus the market country unless its row needs
    sponsorship.
    """
    scope = hiring_scope(opening_fm)
    if scope is None:
        return None
    kind, countries, label = scope
    if kind == "global":
        return "open", "PASS", ""
    if kind == "unresolved":
        return "unresolved", "FLAG", f"remote in {label}: the gate cannot map it to countries; confirm it covers you"
    statuses = {row["country"].upper(): row.get("status") for row in eligibility_rows(profile)}
    workable = {code for code, status in statuses.items() if status in WORKABLE_STATUSES}
    market = profile_market(profile)
    if market and statuses.get(market) != "needs_sponsorship":
        workable.add(market)
    if countries & workable:
        return "open", "PASS", ""
    sponsored = sorted(code for code in countries if statuses.get(code) == "needs_sponsorship")
    if sponsored:
        # The candidate is not in those countries; the CV market does not change that. Relocation is the user's call.
        where = f"remote only in {label}, where you need sponsorship"
        if profile.get("plans_to_relocate") is True:
            return "sponsorship", "FLAG", f"{where}; you are willing to relocate"
        return "sponsorship", "FAIL", where
    return "outside", "FAIL", f"remote only in {label}, not in your countries ({', '.join(sorted(workable)) or 'none'})"


# --- gates --------------------------------------------------------------------------------------------------------

# Residence wording: the candidate must live in the country the posting names. A bare 'live' or 'reside' is not
# enough ('you live the values' is not residence wording): the sentence must say 'in', 'within' or 'en'.
RESIDENCY_RE = re.compile(
    r"\b(?:candidates?|applicants?|you|employees?|workers?|persons?|people)\s+(?:must\s+|should\s+|need to\s+|"
    r"have to\s+|will need to\s+)?(?:reside|live|be located|be based|be resident|be residing)\s+(?:in|within)\b|"
    r"\bmust (?:live|reside) (?:in|within)\b|"
    r"\b(?:based|resident|located|residing) (?:candidates?|applicants?|professionals|people|workers|employees|residents?)\b|"
    r"\bonly (?:candidates? |applicants? )?based\b|\bbased only\b|\bresidence (?:in|required|requirement)\b|"
    r"\b(?:debes|debe|deben|tienes que) (?:vivir|residir) en\b|\bresidir en\b|\bresidencia (?:en|requerida)\b"
)
# Hiring restricted to a place: only meaningful when the clause names the place (checked in _classify).
HIRE_RE = re.compile(r"\b(?:can |could )?only hire (?:in|from)\b|\bhire only (?:in|from)\b|\bsolo contratamos (?:en|de|desde)\b")
WORKABLE_STATUSES = ("citizen", "resident", "permit")


def _sentences(body: str):
    for raw in re.split(r"[.;!?\n]+", body or ""):
        if raw.strip():
            yield raw.strip()


def _clauses(body: str):
    """(clauses, instructions): each comma-separated clause as (text, addressed), and how many sentences are addressed.

    A sentence addressed to an AI, a screener or a reviewer is an instruction, not the employer's wording: an offer
    inside it does not count as an offer. Refusals and residence wording still count, which is the safe direction.
    """
    clauses, instructions = [], 0
    for sentence in _sentences(body):
        addressed = pg.addressed_to_model(sentence)
        instructions += 1 if addressed else 0
        clauses.extend((raw.strip(), addressed) for raw in sentence.split(",") if raw.strip())
    return clauses, instructions


def _restricted_country(opening_fm: dict):
    """The country the posting itself places the role in: a remote role for one country, or a place that names one.

    The market default does not count: a role in a city of the candidate's own market is not a restriction to a
    country.
    """
    scope = hiring_scope(opening_fm)
    if scope is not None:
        kind, countries, _ = scope
        return next(iter(countries)) if kind == "countries" and len(countries) == 1 else None
    mode = str(opening_fm.get("work_mode") or "").strip()
    base, _, arg = mode.lower().partition(":")
    if base in ("onsite", "hybrid"):
        named = _countries_in(ss.fold(arg))
        if len(named) == 1:
            return named.pop()
    return None


def _classify(folded: str, addressed: bool = False, names_country: bool = False) -> dict:
    """The kinds of eligibility wording in one folded clause: refuse, offer, auth, residency, unknown. Empty if none.

    An offer ("we offer H-1B sponsorship") is not an authorisation requirement, so H-1B there is not counted as one.
    An addressed clause is an instruction: its offer and unknown wording is not read as the employer's wording.
    """
    kinds = {}
    if REFUSE_RE.search(folded) or VISA_REFUSE_RE.search(folded):
        kinds["refuse"] = True
    elif OFFER_RE.search(folded) and not addressed:
        kinds["offer"] = True
    if AUTH_RE.search(folded) or (H1B_RE.search(folded) and not kinds.get("offer")):
        kinds["auth"] = True
    if RESIDENCY_RE.search(folded) or (names_country and HIRE_RE.search(folded)):
        kinds["residency"] = True
    if not kinds and not addressed and UNKNOWN_RE.search(folded):
        kinds["unknown"] = True
    return kinds


def _country_verdict(code: str, status, found: dict, market=None, relocate: bool = False):
    """(verdict, note) for the wording the posting puts on one country, against the candidate's status there.

    Residence wording ('must reside in X') is met only when the candidate is based in X: X is the profile market and
    the status there is workable. Any other candidate FAILs it, unless profile.md says plans_to_relocate: true, which
    makes it a FLAG: the user decides whether to move.
    Other wording is read against the status: a needs_sponsorship candidate FAILs a refusal or an authorisation
    requirement, and a candidate who holds the right to work there is not restricted by a refusal.
    """
    refuse, offer = found.get("refuse"), found.get("offer")
    auth, unknown, residency = found.get("auth"), found.get("unknown"), found.get("residency")
    if residency and not (code == market and status in WORKABLE_STATUSES):
        if not market:
            return "FLAG", f'"{residency}"; profile.md has no market country to check residence in {code}'
        if code != market:
            why = f"you are based in {market}, not {code}"
        else:
            why = f"your {code} row is {status or 'missing'}, not a workable status"
        if relocate:
            return "FLAG", f'"{residency}"; residence in {code} is required; {why}; you are willing to relocate'
        return "FAIL", f'"{residency}"; residence in {code} is required and {why}'
    if status is None:
        quote = refuse or offer or auth or unknown
        return "FLAG", f'"{quote}"; no eligibility row for {code}'
    if status == "needs_sponsorship":
        if refuse or auth:
            quote = refuse or auth
            return "FAIL", f'"{quote}"; you declared needs_sponsorship for {code}'
        if offer:
            return "PASS", f'"{offer}"; sponsorship offered in {code}'
        return "FLAG", f'"{unknown}"; you declared needs_sponsorship for {code}; check what the wording means'
    if status in WORKABLE_STATUSES:
        if refuse or offer:
            # A refusal of sponsorship costs a candidate who holds the right to work nothing.
            return "PASS", f'"{refuse or offer}"; declared {status} for {code}'
        if auth:
            # Restriction to citizens or residents may refer to another country: check it, never pass it silently.
            return "FLAG", f'"{auth}"; declared {status} for {code}; check which country this wording refers to'
        return "PASS", f"declared {status} for {code}; the wording does not restrict you"
    return "FLAG", f"eligibility status {status!r} for {code} is not recognised; check the wording"


def eligibility_gate(profile: dict, opening_fm: dict, body: str):
    """(verdict, note). Silence in the posting is PASS with an eligibility_unverified label, never a guess.

    Each clause of wording is checked against the country it names. A clause that names no country takes the
    countries named elsewhere in the posting, else the default country of the work mode, else no country. A refusal
    that names no country does not restrict a candidate who holds the right to work in some country. Residence
    wording FAILs a candidate who is not based in the named country. Silence FLAGs only when the posting places the
    role in a country where the candidate needs sponsorship. Unrecognised wording FLAGs that candidate, which blocks
    PURSUE.
    """
    scoped = scope_check(profile, opening_fm)
    if scoped and scoped[0] == "outside":
        # The posting hires only where the candidate may not work: no wording makes that eligible.
        return "FAIL", f"{scoped[2]}; the posting hires only there"
    worst, notes = eligibility_wording(profile, opening_fm, body)
    if scoped and worst == "PASS" and (scoped[0] == "unresolved" or (
            scoped[0] == "sponsorship" and notes.startswith("eligibility_unverified"))):
        # A scope the gate cannot map, or a silent posting that hires only where the candidate needs sponsorship, is
        # never a silent PASS.
        return "FLAG", f"{scoped[2]}; {notes}"
    return worst, notes


def eligibility_wording(profile: dict, opening_fm: dict, body: str):
    """eligibility_gate without the hiring scope: the posting's wording against the eligibility table."""
    raw_clauses, instructions = _clauses(body)
    clauses = []
    for raw, addressed in raw_clauses:
        folded = ss.fold(raw)
        countries = _countries_in(folded) | ({"US"} if H1B_RE.search(folded) else set())
        kinds = _classify(folded, addressed, bool(countries)) if folded else {}
        if kinds:
            clauses.append((ss.clip(raw, CLIP), kinds, countries))
    statuses = {row["country"].upper(): row.get("status") for row in eligibility_rows(profile)}
    skipped = ("; instruction-like sentence(s) in the posting: offer wording in them is not read as an offer"
               if instructions else "")
    if not clauses:
        restricted = _restricted_country(opening_fm)
        if restricted and statuses.get(restricted) == "needs_sponsorship":
            return "FLAG", (f"eligibility_unverified: the posting places the role in {restricted} and says nothing "
                            f"about sponsorship; you need sponsorship there{skipped}")
        return "PASS", ("eligibility_unverified: the posting says nothing about citizenship or work authorisation"
                        + skipped)
    named = set().union(*(countries for _, _, countries in clauses))
    fallback = default_country(profile, opening_fm)
    found = {}
    for quote, kinds, countries in clauses:
        targets = countries or named or ({fallback} if fallback else {None})
        for code in targets:
            bucket = found.setdefault(code, {})
            for kind in kinds:
                bucket.setdefault(kind, quote)
    market = profile_market(profile)
    relocate = profile.get("plans_to_relocate") is True
    workable = sorted(code for code, status in statuses.items() if status in WORKABLE_STATUSES)
    worst, notes = "PASS", []
    for code in sorted(found, key=lambda c: c or ""):
        bucket = found[code]
        if code is None:
            quote = bucket.get("auth") or bucket.get("unknown") or bucket.get("residency")
            if quote or not market:
                quote = quote or bucket.get("refuse") or bucket.get("offer")
                verdict, note = "FLAG", f'"{quote}"; the wording names no country; check which country it means'
            elif (bucket.get("refuse") or bucket.get("offer")) and workable:
                quote = bucket.get("refuse") or bucket.get("offer")
                verdict, note = "PASS", (f'"{quote}"; names no country, and you hold the right to work in '
                                         f'{", ".join(workable)}, so it does not restrict you')
            else:
                verdict, note = _country_verdict(market, statuses.get(market), bucket, market, relocate)
                note = f"no country named; checked against your market {market}: {note}"
        else:
            verdict, note = _country_verdict(code, statuses.get(code), bucket, market, relocate)
        notes.append(note)
        if _rank(verdict) > _rank(worst):
            worst = verdict
    return worst, "; ".join(notes) + skipped


def language_gate(opening_fm: dict, achievements: dict, policy):
    """(verdict, note). Gap rules from profile.md languages_policy; an undeclared language is a FAIL.

    Language names are normalised to ISO 639-1 on both sides, so 'Inglés', 'English' and 'en' are one language.
    """
    required = opening_fm.get("required_language")
    if required in (None, ""):
        return "PASS", ""
    if isinstance(required, str):
        if required.strip().lower() == "not_required":
            return "PASS", ""
        match = LANGUAGE_PHRASE_RE.match(required)
        if not match:
            return "FLAG", f"required language is '{required}' in the opening; level not stated"
        required = {match.group(1).strip(): match.group(2).upper()}
    if not isinstance(required, dict):
        return "FLAG", "required language could not be read from the opening"
    policy = policy or DEFAULT_POLICY
    declared = {}
    for item in achievements.get("languages") or []:
        if isinstance(item, dict) and item.get("language"):
            declared[jc.normalize_language(item["language"])] = item.get("level")
    flag_steps = int(policy.get("flag_gap_steps", DEFAULT_POLICY["flag_gap_steps"]))
    discard_steps = int(policy.get("discard_gap_steps", DEFAULT_POLICY["discard_gap_steps"]))
    worst, notes = "PASS", []
    for language, level in required.items():
        asked = str(level or "").strip()
        if asked.lower() == "not_required":
            continue
        need = jc.cefr_index(asked)
        key = jc.normalize_language(language)
        if key not in declared:
            # Order matters: an undeclared language discards before any level is compared.
            verdict, note = "FAIL", f"{language}: the opening asks {asked or 'a level'}; not in your declared languages"
        elif need is None:
            verdict, note = "FLAG", f"{language}: the opening states '{asked or 'no level'}', not a CEFR level"
        else:
            have_level = declared[key]
            have = jc.cefr_index(have_level)
            if have is None:
                verdict, note = "FLAG", f"{language}: the opening asks {asked}; your level is not a CEFR level"
            else:
                gap = need - have
                if gap >= discard_steps:
                    verdict = "FAIL"
                elif gap >= flag_steps:
                    verdict = "FLAG"
                else:
                    verdict = "PASS"
                note = f"{language}: the opening asks {asked}; you declare {have_level}"
        if verdict != "PASS":
            notes.append(note)
        if _rank(verdict) > _rank(worst):
            worst = verdict
    return worst, "; ".join(notes)


def _rank(verdict: str) -> int:
    return {"PASS": 0, "FLAG": 1, "FAIL": 2}[verdict]


def _place_verdict(profile: dict, base: str, arg: str):
    """An onsite or hybrid place: 'Lima', 'Lima, Peru', 'San Isidro, Lima, Peru' or 'Miraflores, Lima'.

    One part must name a city of yours (whole word); the parts after it may name the country. A place with no part
    that names one of your cities FAILs. A city with nothing after it is yours. A country named after it must be
    your market; a country that cannot be read is a FLAG.
    """
    parts = [part.strip() for part in arg.split(",") if part.strip()]
    cities = [ss.fold(city) for city in (profile.get("cities") or []) if str(city).strip()]
    index = 0
    if cities:
        index = next((i for i, part in enumerate(parts) if any(jc.word_in(city, part) for city in cities)), None)
        if index is None:
            return "FAIL", f"{base} in {arg}, outside your cities"
    rest = parts[index + 1:]
    if not rest:
        return "PASS", ""
    market = profile_market(profile)
    if not market:
        return "FLAG", f"{base} in {arg}: profile.md has no market country to check the place against"
    named = _countries_in(ss.fold(", ".join(rest)))
    if named == {market}:
        return "PASS", ""
    if named:
        return "FAIL", f"{base} in {arg}, in {', '.join(sorted(named))}, outside your country"
    return "FLAG", f"{base} in {arg}: the place names no country you can check; confirm the country"


def location_gate(profile: dict, opening_fm: dict):
    mode = str(opening_fm.get("work_mode") or "").strip().lower()
    if not mode or mode == "unknown":
        return "FLAG", "work mode is not stated in the opening"
    base, _, arg = mode.partition(":")
    arg = arg.strip()
    accepted = profile.get("work_mode")
    if isinstance(accepted, list) and accepted and base not in accepted:
        return "FAIL", f"work mode {base} is not in your work_mode list"
    if base in ("onsite", "hybrid"):
        if not arg:
            return "FLAG", f"{base} without a city in the opening"
        return _place_verdict(profile, base, arg)
    if base == "remote_country" and not arg:
        return "FLAG", "remote for a country not named in the opening"
    scoped = scope_check(profile, opening_fm)
    if scoped is None:
        return "FLAG", f"work mode {base} is not one the gate knows; confirm where the role is done"
    return scoped[1], scoped[2]


# --- seniority ----------------------------------------------------------------------------------------------------

def _margin(profile: dict) -> float:
    try:
        return float(profile.get("seniority_margin", DEFAULT_SENIORITY_MARGIN))
    except (TypeError, ValueError):
        return float(DEFAULT_SENIORITY_MARGIN)


def _basis(profile: dict) -> str:
    value = str(profile.get("seniority_basis") or DEFAULT_SENIORITY_BASIS).strip().lower()
    return value if value in ("total", "role") else DEFAULT_SENIORITY_BASIS


def _profile_total(profile: dict):
    years = profile.get("years_experience")
    total = years.get("total") if isinstance(years, dict) else None
    if isinstance(total, bool) or not isinstance(total, (int, float)):
        return None
    return float(total)


def years_profile(achievements: dict, profile: dict, on) -> dict:
    """Total and per-title years. Dated experiences are the source. profile.years_experience.total is used only
    when no experience has dates. years_experience.in_role is never used for a gate."""
    dated = jc.experience_years(achievements.get("experiences") or [], on=on)
    if dated["total"] > 0:
        return {"total": dated["total"], "by_title": dated["by_title"], "source": "dated experiences"}
    return {"total": _profile_total(profile), "by_title": {}, "source": "years_experience in profile.md"}


def years_requirement(window: str):
    """What the words after an 'N years' phrase ask for.

    ('generic', None) for software, engineering or development experience, and for activity ('of experience building
    distributed systems'); ('role', word) for time in a role such as lead or manager; ('skill', None) for a tool or
    method ('of experience with React'), which is never a seniority test; None for anything else the dated
    experiences cannot settle.
    """
    tokens = ss.fold(window).split()
    general = CORE_WORDS | FILLER_WORDS
    for index, token in enumerate(tokens[:8]):
        if token in ROLE_WORDS:
            if all(t in general or t in ROLE_PREFIX or t in EXPERIENCE_WORDS for t in tokens[:index]):
                return "role", ROLE_WORDS[token]
            break
    for index, token in enumerate(tokens):
        if token in EXPERIENCE_WORDS:
            rest = tokens[index + 1:]
            if not rest or all(t in general or t in LINK_WORDS for t in rest[:3]):
                return "generic", None
            if rest[0].endswith("ing") or any(t in CORE_WORDS for t in rest[:5]):
                return "generic", None
            if rest[0] in LINK_WORDS:
                return "skill", None
            return None
        if token not in general:
            return None
    return ("generic", None) if any(t in CORE_WORDS for t in tokens) else None


def seniority_gate(profile: dict, achievements: dict, body: str, today):
    """(verdict, note). A years requirement compares with the years the dated experiences cover.

    Generic years ('N years of software engineering experience') compare with the total, overlaps counted once.
    'N years as tech lead' compares with the total too under seniority_basis: total (the default: most markets ask
    for years of the profession, not of a rank), and with the time in titles holding that role word under
    seniority_basis: role. A shortfall up to seniority_margin is a soft note and never a FLAG. A larger shortfall
    FAILs the gate (REJECT). Skill years are noted and never compared. A years number is never reported as 'no
    years requirement'.
    """
    years = years_profile(achievements, profile, today)
    margin = _margin(profile)
    basis = _basis(profile)
    verdict, notes = "PASS", []
    for raw in re.split(r"[.;!?\n]+", body or ""):
        for match in YEARS_RE.finditer(raw):
            quote = ss.clip(raw.strip(), CLIP)
            requirement = years_requirement(raw[match.end():])
            if requirement is None:
                notes.append(f'"{quote}"; years wording not compared: not a software-experience or role requirement')
                continue
            kind, role = requirement
            if kind == "skill":
                notes.append(f'"{quote}"; skill years: not a seniority test, never a reason to reject')
                continue
            need = float((match.group(1) or match.group(2)).replace(",", "."))
            if kind == "generic" or basis == "total":
                have, label = years["total"], "professional experience"
            else:
                have = None
                if years["source"] == "dated experiences":
                    have = sum(value for title, value in years["by_title"].items() if jc.word_in(role, title))
                label = f"time as {role}"
            if have is None:
                notes.append(f'"{quote}"; not checked: no dated experience to compare')
                continue
            gap = need - have
            if gap <= 0:
                notes.append(f'"{quote}"; met: {have:g} years of {label} against {need:g} asked')
                continue
            if gap <= margin:
                notes.append(f'"{quote}"; soft: {have:g} years of {label} against {need:g}, within seniority_margin '
                             f"{margin:g}")
                continue
            verdict = "FAIL"
            notes.append(f'"{quote}"; {have:g} years of {label} from {years["source"]}, {need:g} asked: more than '
                         f"seniority_margin {margin:g} short")
    if not notes:
        return "PASS", "no years requirement in the posting"
    return verdict, "; ".join(notes)


# --- deal-breakers ------------------------------------------------------------------------------------------------

def _stem(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") and not token.endswith("ss") else token


def _phrase_in_clause(wanted: list, clause: list) -> bool:
    """True when every stemmed phrase word is in the clause and no negation word sits next to the match."""
    stems = [_stem(token) for token in clause]
    positions = []
    for word in wanted:
        if word not in stems:
            return False
        positions.append(stems.index(word))
    low, high = min(positions), max(positions)
    around = clause[max(0, low - 3):low] + clause[high + 1:high + 4]
    return not any(token in NEGATIONS for token in around)


# Words that mean the same in a deal-breaker and in a posting. Reviewed; extend with care.
DEAL_ALIASES = (
    (r"\bfin(?:es)? de semanas?\b|\bfinde\b", "weekend"),
    (r"\bon call\b|\boncall\b|\bguardias?\b|\bretenes?\b|\bstandby\b", "oncall"),
    (r"\b(?:todos|todas|cada)\b", "every"),
)
# Articles say nothing about the deal: 'los fines de semana' is 'fines de semana'.
DEAL_DROP = frozenset({"los", "las", "el", "la", "de", "del", "the", "a", "an"})
# 'every' in a deal-breaker ('on-call every weekend') is a frequency. A posting that says how often in another way
# ('rotativas los fines de semana' for 'guardias todos los fines de semana') still means the deal. So the frequency
# word is not required, but a limiting word in the same clause ('one weekend per month') stops the match.
DEAL_FREQUENCY = frozenset({"every", "all", "each"})
DEAL_LIMITS = frozenset({"one", "once", "occasional", "occasionally", "monthly", "month", "months", "quarter",
                         "quarterly", "some", "per", "una", "vez", "mes", "meses", "mensual", "mensuales", "algunos"})
# Sector words that name the same industry. Reviewed.
SECTOR_GROUPS = (frozenset({"gambling", "betting", "casino", "igaming", "wagering", "bookmaker", "apuesta"}),)
AVOID_SPLIT = re.compile(r"\s*(?:/|,|;|\||&|\band\b)\s*", re.I)


def _deal_tokens(text) -> list:
    """Folded tokens of one phrase or clause, with the aliases applied and the articles left out."""
    folded = ss.fold(text)
    for pattern, replacement in DEAL_ALIASES:
        folded = re.sub(pattern, replacement, folded)
    return [token for token in folded.split() if token not in DEAL_DROP]


def _sector_term_hit(term: str, sector: str) -> bool:
    """True when every word of an avoid term is in the sector; a word of the same group counts as the same word."""
    words = [_stem(word) for word in ss.fold(term).split()]
    if not words:
        return False
    tokens = {_stem(token) for token in ss.fold(sector).split()}
    for word in words:
        group = next((members for members in SECTOR_GROUPS if word in members), {word})
        if not tokens & set(group):
            return False
    return True


def deal_breaker_hits(profile: dict, body: str, analysis: dict) -> list:
    """Deal-breaker phrases found in the opening, avoid-list hits, and nothing else.

    A phrase matches when all its words appear in one clause, in any order, after the aliases are applied ('on-call
    weekends' matches 'weekend on-call rotation' and 'guardias ... fines de semana'). A clause that negates the
    phrase ('No travel required') does not match. A phrase that starts with a negation ('no on-call') is a wish: it
    matches only a positive mention of what it negates. A phrase made only of work-mode words never matches: the
    location gate decides work mode.
    """
    hits = []
    clauses = [_deal_tokens(part) for part in re.split(r"[.;!?\n,]+", body or "")]
    for phrase in profile.get("deal_breakers") or []:
        if not isinstance(phrase, str):
            continue
        tokens = _deal_tokens(phrase)
        while tokens and tokens[0] in NEGATIONS:
            tokens.pop(0)
        if not tokens or all(token in WORK_MODE_WORDS or token in WORK_FILLER for token in tokens):
            continue
        core = [token for token in tokens if token not in DEAL_FREQUENCY]
        framed = len(core) != len(tokens)
        wanted = [_stem(token) for token in core]
        for clause in clauses:
            if clause and _phrase_in_clause(wanted, clause) and not (framed and DEAL_LIMITS & set(clause)):
                hits.append(phrase)
                break
    company = ss.norm((analysis.get("company") or {}).get("name") or "")
    for name in profile.get("avoid_companies") or []:
        if isinstance(name, str) and company and ss.norm(name) == company:
            hits.append(f"avoid_companies: {name}")
    sector = ss.fold((analysis.get("company") or {}).get("sector"))
    for name in profile.get("avoid_sectors") or []:
        if not isinstance(name, str) or not sector or not ss.fold(name):
            continue
        terms = [term for term in AVOID_SPLIT.split(name) if ss.fold(term)]
        if ss.fold(name) in sector or any(_sector_term_hit(term, sector) for term in terms):
            hits.append(f"avoid_sectors: {name}")
    return hits


# --- skill coverage -----------------------------------------------------------------------------------------------

# Skill spellings that name one skill. Reviewed; extend with care. Applied to the lower-cased text, before folding.
SKILL_ALIASES = (
    (r"\bc\+\+", " cplusplus "), (r"\bc#", " csharp "), (r"\bnode\.?\s?js\b", " nodejs "), (r"^node$", " nodejs "),
    (r"\breact native\b", " reactnative "), (r"\bk8s\b", " kubernetes "), (r"\bpostgres\b", " postgresql "),
    (r"\bjs\b", " javascript "), (r"\bpowerbi\b", " power bi "), (r"\bamazon web services\b", " aws "),
    (r"\bgcp\b", " google cloud "), (r"\bsklearn\b", " scikit learn "),
)
# A compound must-have is split into parts; each part needs its own verified evidence.
PART_SPLIT = re.compile(r"\s*(?:,|;|/|&|\band\b)\s*", re.I)
# Words that may stand next to a skill without making it a different skill: 'Python data analysis', 'Docker in
# production'. Any other extra word makes it a different skill ('React Native' is not 'React').
MODIFIER_WORDS = frozenset({
    "data", "analysis", "analytics", "development", "developer", "developers", "engineering", "engineer", "engineers",
    "programming", "applications", "application", "apps", "systems", "system", "framework", "frameworks", "language",
    "languages", "skills", "skill", "experience", "tools", "tool", "basics", "fundamentals", "knowledge", "in", "with",
    "using", "for", "of", "the", "a", "an", "production", "based", "design", "techniques", "technique", "libraries",
    "library", "services", "service",
})


def _skill_tokens(text) -> list:
    """Tokens of one skill text after the alias table: 'K8s' is 'kubernetes', 'C++' is 'cplusplus'."""
    folded = str(text or "").lower()
    for pattern, replacement in SKILL_ALIASES:
        folded = re.sub(pattern, replacement, folded)
    return ss.fold(folded).split()


def _parts(text) -> list:
    """The non-empty token lists of a requirement, split on 'and', commas, slashes and ampersands."""
    parts = []
    for piece in PART_SPLIT.split(str(text or "")):
        tokens = _skill_tokens(piece)
        if tokens:
            parts.append(tokens)
    return parts


def _covers(evidence: list, must: list) -> bool:
    """True when evidence covers one part of a must-have: equal tokens, or a shorter run of tokens inside the longer
    one with only generic modifier words around it."""
    if not evidence or not must:
        return False
    if evidence == must:
        return True
    short, long_ = (evidence, must) if len(evidence) < len(must) else (must, evidence)
    if not short or len(short) >= len(long_) or len(" ".join(short)) < 3:
        return False
    for start in range(len(long_) - len(short) + 1):
        if long_[start:start + len(short)] == short:
            extra = long_[:start] + long_[start + len(short):]
            return all(token in MODIFIER_WORDS for token in extra)
    return False


# --- decision and advice ------------------------------------------------------------------------------------------

def is_credential(text) -> bool:
    return CREDENTIAL_RE.search(ss.fold(text)) is not None


def split_gaps(hard_gaps: list, profile: dict):
    """(blocking, learnable). By default nothing blocks: a missing skill, tool, method, degree or certification lowers
    the score and is named so the user can prepare it or argue it. The profile opts in to strictness:
    reject_on_missing_credentials: true blocks a missing degree, licence, certification or clearance;
    reject_on_skill_gaps: true blocks a missing skill, tool or method."""
    credentials = profile.get("reject_on_missing_credentials") is True
    skills = profile.get("reject_on_skill_gaps") is True
    blocking = [gap for gap in hard_gaps if (credentials if is_credential(gap) else skills)]
    return blocking, [gap for gap in hard_gaps if gap not in blocking]


def core_must_haves(requirements: dict) -> list:
    """The core must-haves: requirements.priorities when the scout set them, else every must-have. A hard gap in a
    core must-have rejects; a hard gap elsewhere only lowers the score through the dimensions."""
    priorities = [str(item) for item in requirements.get("priorities") or [] if str(item).strip()]
    return priorities or [str(item) for item in requirements.get("must_have") or []]


def decide(gates: dict, deal_hits: list, hard_gaps: list, core: list, score: int, threshold: int):
    failed = [name for name in GATE_NAMES if gates.get(name) == "FAIL"]
    if failed:
        return "REJECT", f"gate FAIL: {', '.join(failed)}"
    if deal_hits:
        return "REJECT", f"deal-breaker: {deal_hits[0]}"
    core_keys = {ss.fold(item) for item in core}
    core_gaps = [gap for gap in hard_gaps if ss.fold(gap) in core_keys]
    if core_gaps:
        return "REJECT", f"hard gap in a core must-have: {core_gaps[0]}"
    # A FLAG on eligibility or location is a question the posting leaves open (which country, which city). The user
    # answers it before an application starts, so the opening is WATCH, never PURSUE.
    flagged = [name for name in ("eligibility", "location") if gates.get(name) == "FLAG"]
    if flagged:
        return "WATCH", f"gate FLAG: {', '.join(flagged)}; resolve it before a PURSUE"
    if score < threshold:
        return "WATCH", f"score {score} is below apply_threshold {threshold}"
    return "PURSUE", f"score {score} is at or above apply_threshold {threshold}"


CALL_QUESTIONS = [
    "What are the primary challenges in this role?",
    "How is time divided across the listed responsibilities?",
    "Which requirements are essential, and which are nice to have?",
    "What does success look like in the first six to twelve months?",
]


def employer_call(analysis: dict, body: str, decision: str) -> dict:
    """Advice only when a call has substantive questions: vague tasks, unclear must-haves, or a named contact who
    invites questions. Never 'to be remembered'. The questions are for gathering facts, not for a pitch."""
    if decision == "REJECT":
        return {"advised": False, "why": "rejected; no call", "questions": []}
    requirements = analysis.get("requirements") or {}
    reasons = []
    if not requirements.get("must_have"):
        reasons.append("no must-haves are clear")
    if len(requirements.get("responsibilities") or []) < 2:
        reasons.append("the day-to-day tasks are vague")
    if requirements.get("must_have") and requirements.get("nice_to_have") and not requirements.get("priorities"):
        reasons.append("essential and nice-to-have requirements are not separated")
    if INVITE_RE.search(ss.fold(body)):
        reasons.append("the posting invites questions")
    if reasons:
        return {"advised": True, "why": "; ".join(reasons), "questions": list(CALL_QUESTIONS)}
    return {"advised": False, "why": "requirements and tasks are clear enough to write from the posting",
            "questions": []}


def salary_for(project: Path, company: str, opening_fm: dict, warnings: list):
    mode = str(opening_fm.get("work_mode") or "")
    city = mode.partition(":")[2].strip() if mode.lower().startswith(("onsite:", "hybrid:")) else None
    try:
        return sl.project_benchmark(project, company, city or None)
    except sl.SalaryError as exc:
        warnings.append(f"salary benchmark skipped: {exc}")
        return None


# --- the analysis document ----------------------------------------------------------------------------------------

def verified_ids(achievements: dict) -> set:
    """Ids of every verified claim: achievements, education and certifications all count as evidence."""
    ids = set()
    for key in ("achievements", "education", "certifications"):
        for item in achievements.get(key) or []:
            if isinstance(item, dict) and item.get("verified") is True:
                ids.add(str(item.get("id")))
    return ids


def build(folder: Path, project: Path, today=None):
    """(document, problems, warnings). Problems block a write; warnings are reported and written."""
    today = today or date.today()
    problems, warnings = [], []
    path = folder / "analysis.json"
    if not path.is_file():
        raise AnalysisError(f"{path} not found; the scout writes it before finalize")
    try:
        analysis = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise AnalysisError(f"{path} is not valid JSON: {exc}")
    if not isinstance(analysis, dict):
        raise AnalysisError(f"{path} must hold a JSON object")

    opening_fm, body = read_opening(folder)
    profile = read_profile(project)
    policy = profile.get("languages_policy") if isinstance(profile.get("languages_policy"), dict) else None
    cfg = ss.scoring_config(profile)  # raises ValueError on bad weights or bands

    requirements = analysis.get("requirements")
    if not isinstance(requirements, dict):
        problems.append("requirements must be an object")
        requirements = {}
    for name in REQUIRED_LISTS:
        if requirements.get(name) is None:
            requirements[name] = []  # an absent list is empty, so the rules still run
        elif not isinstance(requirements.get(name), list):
            problems.append(f"requirements.{name} must be a list")
    if not isinstance(analysis.get("company"), dict):
        problems.append("company must be an object (summary, product, sector, ...)")
    elif not analysis["company"].get("summary"):
        warnings.append("company.summary is empty: no company profile was written")

    fit = analysis.get("fit")
    if not isinstance(fit, dict):
        problems.append("fit must be an object")
        fit = {}
    dims = fit.get("dimensions") or {}
    scores = {}
    for dim in DIMENSIONS:
        block = dims.get(dim) if isinstance(dims, dict) else None
        if not isinstance(block, dict):
            problems.append(f"fit.dimensions.{dim} must be an object with score and note")
            continue
        try:
            scores[dim] = ss.check_number(block.get("score"), f"fit.dimensions.{dim}.score")
        except ValueError as exc:
            problems.append(str(exc))
            continue
        if not isinstance(block.get("note"), str):
            block["note"] = ""
        block["score"] = ss.tidy(scores[dim])
    if problems:
        return analysis, problems, warnings

    score = ss.overall_score(scores, cfg["weights"])
    band = ss.band_for(score, cfg["bands"])
    fit["dimensions"] = {dim: dims[dim] for dim in DIMENSIONS}
    fit["score"] = score

    evidence = analysis.get("evidence") or []
    if not isinstance(evidence, list):
        problems.append("evidence must be a list")
        evidence = []
    achievements = read_achievements(project)
    verified = verified_ids(achievements)
    covered = []  # token lists of the requirement parts that have verified evidence
    for item in evidence:
        if not isinstance(item, dict):
            problems.append("each evidence entry must be an object")
            continue
        ids = item.get("achievements") or []
        if not isinstance(ids, list):
            problems.append(f"evidence {item.get('requirement')!r}: achievements must be a list")
            continue
        supported = [a for a in ids if a in verified]
        for missing in [a for a in ids if a not in verified]:
            warnings.append(f"{missing} is not verified in achievements.yaml; it is not evidence")
        confidence = item.get("confidence")
        if confidence is not None and (isinstance(confidence, bool) or not isinstance(confidence, (int, float))
                                       or not 0 <= confidence <= 1):
            problems.append(f"evidence {item.get('requirement')!r}: confidence must be 0 to 1")
            continue
        if supported and item.get("requirement"):
            covered.extend(_parts(item["requirement"]))
    if problems:
        return analysis, problems, warnings

    held_text = json.dumps(achievements, ensure_ascii=False)

    def is_covered(must: str) -> bool:
        """Every part of a must-have needs verified evidence of its own. 'Python' covers 'Python data analysis'.
        'Java' never covers 'JavaScript', 'React' never covers 'React Native', 'C' never covers 'C++'. A part whose
        tool family the candidate holds (PostgreSQL next to SQL, GitLab next to GitHub) is covered as related."""
        parts = _parts(must)
        return bool(parts) and all(any(_covers(ev, part) for ev in covered)
                                   or jc.related_held(" ".join(part), held_text) for part in parts)

    hard_gaps = [str(item) for item in (fit.get("hard_gaps") or [])]
    hard_keys = {ss.fold(item) for item in hard_gaps}
    for must in requirements["must_have"]:
        if not is_covered(str(must)) and ss.fold(must) not in hard_keys:
            hard_gaps.append(str(must))
            hard_keys.add(ss.fold(must))
            warnings.append(f"no verified evidence: {must}; sorted into learnable or hard gaps by the profile opt-ins")
    blocking_gaps, learnable_gaps = split_gaps(hard_gaps, profile)
    fit["hard_gaps"] = blocking_gaps
    fit["learnable_gaps"] = learnable_gaps
    if learnable_gaps:
        warnings.append("learnable, not a reason to reject (prepare them for the interview, or tell the manager if "
                        f"you have used them): {', '.join(learnable_gaps)}")

    gate_eligibility, eligibility_note = eligibility_gate(profile, opening_fm, body)
    gate_language, language_note = language_gate(opening_fm, achievements, policy)
    gate_location, location_note = location_gate(profile, opening_fm)
    gate_seniority, seniority_note = seniority_gate(profile, achievements, body, today)
    gates = {
        "eligibility": gate_eligibility,
        "language": gate_language,
        "location": gate_location,
        "seniority": gate_seniority,
        "language_note": language_note,
        "eligibility_note": eligibility_note,
        "location_note": location_note,
        "seniority_note": seniority_note,
    }
    raw_company = analysis.get("company")
    company_block = raw_company if isinstance(raw_company, dict) else {}
    company = str(company_block.get("name") or opening_fm.get("company") or "")
    deal_hits = deal_breaker_hits(profile, body, {"company": {"name": company,
                                                              "sector": company_block.get("sector")}})
    # Disqualifiers the scout judged from the posting reject exactly like a profile deal-breaker.
    deal_hits += [f"disqualifier: {item}" for item in requirements["disqualifiers"] if str(item).strip()]
    fit["deal_breakers_hit"] = deal_hits

    decision, basis = decide(
        {name: gates[name] for name in GATE_NAMES}, deal_hits, blocking_gaps,
        core_must_haves(requirements), score, cfg["apply_threshold"],
    )
    # A hard gap, a failed gate or a deal-breaker shows as band "gap", so a rejected opening never reads "strong".
    failed_gate = any(gates[name] == "FAIL" for name in GATE_NAMES)
    fit["band"] = "gap" if (blocking_gaps or deal_hits or failed_gate) else band
    if fit.get("decision") and fit.get("decision") != decision:
        warnings.append(f"decision set by the rules: {decision} (the scout wrote {fit.get('decision')})")
    fit["decision"] = decision
    scout_reason = str(fit.get("reason") or "").strip()
    fit["reason"] = f"{decision}: {basis}"  # the deciding rule, always; the scout's wording is kept beside it
    if scout_reason and scout_reason != fit["reason"]:
        fit["scout_reason"] = ss.clip(scout_reason, 300)
    fit.setdefault("overselling_risk", DEFAULT_OVERSELLING)
    fit["apply_threshold"] = cfg["apply_threshold"]

    if company and company_block.get("summary"):
        try:
            cached = company_cache(project, company, today)
        except AnalysisError:
            cached = {"reuse": False, "path": "", "note": ""}
        if not cached["reuse"]:
            warnings.append(
                f"companies/<slug>.md is missing or older than {CACHE_DAYS} days: save the profile to "
                f"{cached['path']} with fetched: {today.isoformat()}"
            )
    posted = ss.optional_iso(opening_fm.get("posted_at"))
    deadline = ss.optional_iso(opening_fm.get("deadline"))
    if posted is False:
        warnings.append(f"posted_at {opening_fm.get('posted_at')!r} is not YYYY-MM-DD; stored as null")
    if deadline is False:
        warnings.append(f"deadline {opening_fm.get('deadline')!r} is not YYYY-MM-DD; stored as null")

    document = dict(analysis)
    document["id"] = str(opening_fm.get("id") or analysis.get("id") or folder.name)
    document["requirements"] = requirements
    document["fit"] = fit
    document["gates"] = gates
    document["salary_benchmark"] = salary_for(project, company, opening_fm, warnings) if company else None
    document["employer_call_advised"] = employer_call(document, body, decision)
    # posting_guard verdict recorded at intake: "clean", the warning line, or "not_checked" when no run is on file.
    # "not_checked" is never read as clean.
    # The intake verdict in opening.md wins; an earlier "not_checked" in analysis.json never masks a later check.
    previous = analysis.get("guard") if analysis.get("guard") != "not_checked" else None
    document["guard"] = ss.normal_guard(opening_fm.get("guard") or previous) or "not_checked"
    document["posted_at"] = None if posted is False else posted
    document["deadline"] = None if deadline is False else deadline
    return document, problems, warnings


def summary(document: dict) -> dict:
    fit = document["fit"]
    return {
        "id": document["id"],
        "score": fit["score"],
        "band": fit["band"],
        "decision": fit["decision"],
        "reason": fit["reason"],
        "gates": {name: document["gates"][name] for name in GATE_NAMES},
        "employer_call_advised": document["employer_call_advised"],
        "guard": document["guard"],
    }


# --- commands -----------------------------------------------------------------------------------------------------

def cmd_rubric(args) -> dict:
    """The scoring rubric and the profile facts a triage scorer needs. It never reads achievements.yaml: the
    requirements are written before the evidence is looked at, in the deep analysis and in triage alike."""
    project = jc.project_dir(args.project)
    profile = read_profile(project)
    cfg = ss.scoring_config(profile)
    keep = ("target_roles", "acceptable_roles", "key_skills", "years_experience", "seniority", "work_mode",
            "cities", "career_goals", "energizers", "drains", "behavioral", "deal_breakers", "avoid_sectors",
            "avoid_companies")
    return {
        "weights": cfg["weights"],
        "bands": cfg["bands"],
        "apply_threshold": cfg["apply_threshold"],
        "dimension_guide": DIMENSION_GUIDE,
        "candidate": {key: profile.get(key) for key in keep if profile.get(key) is not None},
    }


def cmd_years(args) -> dict:
    project = jc.project_dir(args.project)
    years = years_profile(read_achievements(project), read_profile(project), args.today)
    years["as_of"] = args.today.isoformat()
    years["seniority_margin"] = _margin(read_profile(project))
    return years


def company_cache(project: Path, company: str, today) -> dict:
    """companies/<slug>.md: reused while its `fetched` date is under 30 days old."""
    slug = jc.slugify(company, limit=60)
    if not slug:
        raise AnalysisError("company name gives no file name")
    path = project / "companies" / f"{slug}.md"
    meta = jc.read_front_matter(path) if path.is_file() else {}
    fetched = ss.parse_day(meta.get("fetched"))
    age = (today - fetched).days if fetched else None
    return {
        "path": str(path),
        "exists": path.is_file(),
        "fetched": fetched.isoformat() if fetched else None,
        "age_days": age,
        "reuse": age is not None and 0 <= age < CACHE_DAYS,
        "note": f"reuse under {CACHE_DAYS} days; older or undated profiles are rebuilt and rewritten",
    }


def cmd_cache(args) -> dict:
    project = jc.project_dir(args.project)
    return company_cache(project, args.company, args.today)


def cmd_screen(args) -> dict:
    project = jc.project_dir(args.project)
    profile = read_profile(project)
    text_path = Path(args.text)
    if not text_path.is_file():
        raise AnalysisError(f"{text_path} not found")
    body = text_path.read_text(encoding="utf-8", errors="ignore")
    analysis = {"company": {"name": args.company or "", "sector": ""}}
    hits = deal_breaker_hits(profile, body, analysis)
    gate, note = eligibility_gate(profile, {}, body)
    return {
        "deal_breakers_hit": hits,
        "eligibility": {"gate": gate, "note": note},
        "note": "triage screen: deterministic phrase checks only; language and location need the opening",
    }


def record_in_seen(project: Path, document: dict) -> bool:
    """Copy the decision onto the opening's seen.json entry, so triage does not score it again. Additive only."""
    path = ss.state_path(project)
    if not path.is_file():
        return False
    doc = ss.load_state(path)
    for entry in doc["seen"].values():
        if isinstance(entry, dict) and entry.get("opening_id") == document["id"]:
            entry["analysis_decision"] = document["fit"]["decision"]
            entry["analysis_score"] = document["fit"]["score"]
            entry["analysis_date"] = date.today().isoformat()
            ss.save_state(path, doc)
            return True
    return False


def cmd_check_or_finalize(args, write: bool) -> dict:
    project = jc.project_dir(args.project)
    folder = Path(args.opening_dir).resolve()
    if not folder.is_dir():
        raise AnalysisError(f"{folder} is not a folder")
    document, problems, warnings = build(folder, project, args.today)
    out = {"problems": problems, "warnings": warnings, "written": False, "seen_updated": False}
    if problems:
        out["summary"] = None
        return out
    out["summary"] = summary(document)
    if write:
        jc.write_json(folder / "analysis.json", document)
        out["written"] = True
        out["seen_updated"] = record_in_seen(project, document)
    return out


def _day(text: str):
    parsed = ss.parse_day(text)
    if parsed is None:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Personalised fit for one saved opening.")
    sub = ap.add_subparsers(dest="command", required=True)

    rubric = sub.add_parser("rubric", help="scoring rubric and candidate summary for batch triage")
    rubric.add_argument("--project", help="project folder (default: $JOBS_PROJECT or the current folder)")

    years = sub.add_parser("years", help="total and per-title years from the dated experiences")
    years.add_argument("--project", help="project folder (default: $JOBS_PROJECT or the current folder)")
    years.add_argument("--today", type=_day, default=None, help="date to count to (default: today)")

    cache = sub.add_parser("cache", help="is companies/<slug>.md fresh enough to reuse (under 30 days)?")
    cache.add_argument("--project", help="project folder (default: $JOBS_PROJECT or the current folder)")
    cache.add_argument("--company", required=True, help="company name")
    cache.add_argument("--today", type=_day, default=None, help="date to use (default: today)")

    screen = sub.add_parser("screen", help="deal-breaker and eligibility hits in cleaned posting text")
    screen.add_argument("--project", help="project folder")
    screen.add_argument("--text", required=True, help="cleaned posting text file")
    screen.add_argument("--company", help="company name, for the avoid list")

    for name, text in (("check", "validate analysis.json and print the summary; writes nothing"),
                       ("finalize", "validate, compute derived fields and write analysis.json")):
        cmd = sub.add_parser(name, help=text)
        cmd.add_argument("opening_dir", help="openings/<ID> folder")
        cmd.add_argument("--project", help="project folder (default: $JOBS_PROJECT or the current folder)")
        cmd.add_argument("--today", type=_day, default=None, help="date to count experience to (default: today)")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if args.command in ("cache", "years", "check", "finalize") and args.today is None:
        args.today = date.today()
    try:
        if args.command == "rubric":
            payload = cmd_rubric(args)
        elif args.command == "years":
            payload = cmd_years(args)
        elif args.command == "cache":
            payload = cmd_cache(args)
        elif args.command == "screen":
            payload = cmd_screen(args)
        else:
            payload = cmd_check_or_finalize(args, write=args.command == "finalize")
            if payload["problems"]:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
                print("error: analysis.json has problems; nothing was written", file=sys.stderr)
                return 1
    except (AnalysisError, ValueError, SystemExit) as exc:
        if isinstance(exc, SystemExit) and exc.code in (0, None):
            raise
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
