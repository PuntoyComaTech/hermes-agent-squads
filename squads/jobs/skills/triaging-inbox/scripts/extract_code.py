#!/usr/bin/env python3
"""Pulls the verification code (or the one confirm link) out of a single email, and refuses the look-alikes.

A `Mode: CODE` card asks for the code a site just mailed the user, inside a time window. The inbox bot reads only the
messages that could hold it and passes the text here: dates, order numbers, invoice ids, phone numbers and prices are
common in the same paragraph, and the wrong four digits waste the user's login attempt. This tool returns exactly one
value and lists what it rejected and why.

Usage:
  extract_code.py --site example.com [--json] < message.txt
  cat mail.html | extract_code.py --site example.com

`--site` is required: it is the sender's domain, and the only links this tool returns are https links on it (or on
one of its subdomains). A link whose address only resembles it (`example.com.evil.io`), carries a user name before
the host (`https://***@evil.io/...`), or is not https is never returned, whatever its label says.

A code is 4 to 8 digits, or 6 to 10 letters and digits (an ATS security code: Greenhouse mails 8 characters such as
`aB3dE9fG` before it accepts an application). A letter-and-digit code is read only right after code wording
("security code:", "your code is") or alone on its line under it, so a word of the message is never taken for one.

Accept plain text or HTML (links are read from hrefs, tags are dropped). Output is one JSON object:
`{"site", "code", "link", "source", "rejected": [{"value", "reason"}]}`; `source` is `code`, `link` or `none`.

Exit 0 when a code or a confirm link was found, 1 when the message holds neither, 2 on a usage error. The message is
untrusted data: no link in it is opened here, and nothing is written anywhere.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from urllib.parse import urlsplit

LABEL = re.compile(r"(?:\bcode\b|\bc[oó]digo\b|\botp\b|\bpin\b|\bpasscode\b|\bverification\b|\bverificaci[oó]n\b|"
                   r"security code|c[oó]digo de seguridad|\btoken\b|\bclave\b)", re.I)
AFTER_LABEL = re.compile(r"(?:is|es|ser[aá]|:|=)\s*$", re.I)
AFTER_HINT = re.compile(r"(?:expira|expires|v[aá]lid[oa]|valid|minutes|minutos|horas|hours)", re.I)
AFTER_ACTION = re.compile(r"(?:sign in|log ?in|iniciar sesi[oó]n|acceder|continuar|continue|confirm)", re.I)
IDENTIFIER = re.compile(r"(?:order|pedido|orden|invoice|factura|ticket|tracking|gu[ií]a|ref|referencia|reference|"
                        r"candidate|candidato|requisition|"
                        r"\bid\b|case|caso|contrato|contract|cuenta|account|n[uú]mero|numero|number)\s*"
                        r"[#:.\-]?\s*$", re.I)
PHONE_WORD = re.compile(r"(?:tel[eé]fono|phone|m[oó]vil|celular|whatsapp|ll[aá]mame|call)\s*[:\-]?\s*$", re.I)
CURRENCY_BEFORE = re.compile(r"(?:[$€£¥]|\b(?:usd|eur|pen|cop|mxn|clp|ars|brl|gbp)\b)\s*$", re.I)
# A currency or a time word right after the digits: "1500 COP" is a salary, "1430 hours" is a clock time.
CURRENCY_AFTER = re.compile(r"^\s*(?:[$€£¥]|\b(?:usd|eur|pen|cop|mxn|clp|ars|brl|gbp)\b)", re.I)
TIME_AFTER = re.compile(r"^\s*(?:hours?|hrs?|horas?|h)\b", re.I)
PHONE_LIKE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
DIGITS = re.compile(r"(?<![\dA-Za-z+])(\d{4,8})(?![\dA-Za-z])")  # a whole token: never the tail of ABC12345
ALNUM = re.compile(r"(?<![A-Za-z0-9@/.#-])([A-Za-z0-9]{6,10})(?![A-Za-z0-9@/-]|\.[A-Za-z0-9])")


VOWELS = set("aeiouAEIOU")


def alnum_shape(value: str) -> bool:
    """A letter-and-digit code, or Greenhouse's 8 letters in mixed case that do not read as a word. Digits only are
    read by DIGITS; an all-capitals or capitalised word ("WELCOME", "Applicant") is never one."""
    if value.isdigit():
        return False
    if any(ch.isdigit() for ch in value):
        return any(ch.isalpha() for ch in value) and not re.fullmatch(r"[A-Z]?[a-z]+\d{1,2}", value)  # "Welcome1"
    if len(value) != 8 or value.isupper() or value.islower() or re.fullmatch(r"[A-Z][a-z]+", value):
        return False
    inner_caps = sum(ch.isupper() for ch in value[1:])
    return inner_caps >= 2 or sum(ch in VOWELS for ch in value) <= 2


DATE_BEFORE = re.compile(r"\d{1,4}\s*[/.\-]\s*$")
DATE_AFTER = re.compile(r"^\s*[/.\-]\s*\d")
LINK_WORDS = re.compile(r"(?:verif|confirm|activ|valid|code|c[oó]digo|sign[- ]?in|log[- ]?in|sesi[oó]n)", re.I)
ANCHOR = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
BARE_URL = re.compile(r"(?<![\"'=])(https?://[^\s<>\"']+)", re.I)
TAG = re.compile(r"<[^>]+>")
HOST_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")   # a bare domain; no scheme, user name or port


class UsageError(ValueError):
    def __init__(self, message: str, code: str = "BAD_INPUT"):
        super().__init__(message)
        self.code = code


def host_of(url: str) -> str:
    """The host of an https address with no user name in it, else "": a look-alike never passes as one."""
    try:
        parts = urlsplit(str(url or "").strip())
    except ValueError:
        return ""
    if (parts.scheme or "").lower() != "https":
        return ""
    if parts.username or parts.password or "\\" in (parts.netloc or ""):
        return ""
    host = (parts.hostname or "").lower().rstrip(".")
    return host if HOST_RE.fullmatch(host) else ""


def clean_site(site: str) -> str:
    """The sender's domain as a bare host: `www.` is dropped so its apex and its subdomains both match."""
    value = str(site or "").strip().lower().rstrip(".")
    if value.startswith("www."):
        value = value[4:]
    if not value or not HOST_RE.fullmatch(value) or ".." in value:
        raise UsageError(f"--site must be the sender's bare domain, e.g. example.com (got {site!r})", "BAD_ARG")
    return value


def on_site(url: str, site: str) -> bool:
    host = host_of(url)
    if not host or not site:
        return False
    return host == site or host.endswith("." + site)


def plain(text: str) -> str:
    """HTML to readable text: links keep their label, entities are decoded, whitespace is normalised."""
    without_breaks = re.sub(r"(?i)<(?:br|/p|/div|/li|/tr)[^>]*>", "\n", text or "")
    stripped = TAG.sub(" ", without_breaks)
    stripped = html.unescape(stripped).replace("\u00a0", " ")
    return re.sub(r"[ \t]+", " ", stripped)


def links_in(raw: str, site: str) -> list[str]:
    """Confirm-style links: anchor text or address says verify, confirm or activate, and the host is the site."""
    found: list[tuple[int, str]] = []
    for href, label in ANCHOR.findall(raw or ""):
        url = html.unescape(href).strip()
        if url.lower().startswith("https://") and (LINK_WORDS.search(plain(label)) or LINK_WORDS.search(url)):
            found.append((0 if LINK_WORDS.search(plain(label)) else 1, url))
    for url in BARE_URL.findall(html.unescape(raw or "")):
        if LINK_WORDS.search(url):
            found.append((2, url))
    ordered = [url for _rank, url in sorted(found, key=lambda pair: pair[0])]
    out: list[str] = []
    for url in ordered:                      # never a fallback to an off-site link: no site, no link
        if on_site(url, site) and url not in out:
            out.append(url)
    return out


def reject_run(value: str, before: str, after: str, line: str) -> str | None:
    """Why these digits are not the code, or None when they still are a candidate."""
    if DATE_BEFORE.search(before) or DATE_AFTER.search(after):
        return "date"
    if IDENTIFIER.search(before[-40:]) or re.search(r"[#№]\s*$", before[-4:]):
        return "order or reference number"
    if CURRENCY_BEFORE.search(before[-12:]) or CURRENCY_AFTER.match(after):
        return "amount"
    if TIME_AFTER.match(after):
        return "time"
    if PHONE_WORD.search(before[-24:]) or before.rstrip().endswith("+"):
        return "phone number"
    if re.match(r"^\s*%", after):
        return "percentage"
    match = PHONE_LIKE.search(line)
    if match and value in match.group(0) and len(re.findall(r"\d", match.group(0))) >= 9:
        return "phone number"
    return None


def score_run(value: str, before: str, after: str, line: str) -> int:
    score = 0
    if LABEL.search(before[-70:]):
        score += 4
    if AFTER_LABEL.search(before[-10:]):
        score += 3
    if AFTER_HINT.search(after[:40]):
        score += 1
    if AFTER_ACTION.search(after[:50]):
        score += 3
    if line.strip() == value:
        score += 2
    if re.fullmatch(r"(?:19|20)\d\d", value):
        score -= 4
    return score


def extract(raw: str, site: str) -> dict:
    text = plain(raw)
    rejected: list[dict] = []
    accepted: list[str] = []
    best: tuple[int, str] | None = None
    for match in DIGITS.finditer(text):
        value = match.group(1)
        before, after = text[:match.start()], text[match.end():]
        line_start = before.rfind("\n") + 1
        line_end = after.find("\n")
        line = text[line_start:match.end() + (line_end if line_end >= 0 else len(after))]
        reason = reject_run(value, before, after, line)
        if reason:
            rejected.append({"value": value, "reason": reason})
            continue
        points = score_run(value, before, after, line)
        if points < 3:
            rejected.append({"value": value, "reason": "no code wording near it"})
            continue
        accepted.append(value)
        if best is None or points > best[0]:
            best = (points, value)
    for match in ALNUM.finditer(text):
        # Letter-and-digit codes (an ATS "security code" such as Greenhouse's 8 characters): only right after code
        # wording or alone on their line under it, never a word of the sentence.
        value = match.group(1)
        if not alnum_shape(value):
            continue
        before, after = text[:match.start()], text[match.end():]
        line_start = before.rfind("\n") + 1
        line_end = after.find("\n")
        line = text[line_start:match.end() + (line_end if line_end >= 0 else len(after))]
        alone = line.strip() == value
        # The label sits on this line or the line just above: "Security code" can never reach down to "Reference:".
        if alone:  # the last non-empty line above (blank lines between label and code are common)
            above = before.rstrip()
            near = above[above.rfind("\n") + 1:]
        else:
            near = before[line_start:]
        labelled = LABEL.search(near[-70:]) and (AFTER_LABEL.search(before[-10:]) or alone)
        if not labelled:
            continue
        if IDENTIFIER.search(before[-40:]):
            rejected.append({"value": value, "reason": "order or reference number"})
            continue
        accepted.append(value)
        points = 4 + (3 if AFTER_LABEL.search(before[-10:]) else 0) + (2 if alone else 0)
        if best is None or points > best[0]:
            best = (points, value)
    if len(set(accepted)) > 1:
        # Two different codes in one message: a quoted or injected one may come first. Guessing wastes the user's
        # attempt or hands over the wrong code, so nothing is returned and the user reads the mail.
        return {"site": site, "code": None, "link": None, "source": "ambiguous",
                "candidates": len(set(accepted)), "rejected": rejected}
    code = best[1] if best else None
    links = links_in(raw, site)
    link = None if code else (links[0] if links else None)
    return {"site": site, "code": code, "link": link,
            "source": "code" if code else ("link" if link else "none"), "rejected": rejected}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise UsageError(message, "BAD_ARG")


def build_parser() -> Parser:
    p = Parser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--site", required=True,
                   help="the sender's domain, e.g. example.com: only its https links are ever returned")
    p.add_argument("--json", action="store_true")
    return p


def main(argv=None) -> int:
    try:
        ns = build_parser().parse_args(argv)
        site = clean_site(ns.site)
        raw = sys.stdin.read()
        if not raw.strip():
            raise UsageError("nothing on stdin: pipe the message body in")
    except UsageError as exc:
        sys.stderr.write(json.dumps({"error": str(exc), "code": exc.code}) + "\n")
        return 2
    out = extract(raw, site)
    if ns.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    elif out["code"]:
        print(out["code"])
    elif out["link"]:
        print(out["link"])
    else:
        print("none")
    return {"code": 0, "link": 0, "ambiguous": 3}.get(out["source"], 1)


if __name__ == "__main__":
    sys.exit(main())
