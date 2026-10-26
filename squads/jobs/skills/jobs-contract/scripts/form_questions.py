#!/usr/bin/env python3
"""Read the questions of an employer ATS application form from the ATS's public API, before any text is written.

  form_questions.py <apply_url> [--out <P>/openings/<ID>/application/form_questions.json] [--json]
  form_questions.py --from-file RAW.json --ats greenhouse|ashby|lever [--out FILE] [--json]

The writer runs it before drafting answers.md and the reviewer reads the file it writes: every required free-text
question needs its own [FIELD] in answers.md, so a kit never passes review and then meets questions nobody answered
at the submit. Plain HTTPS GET/POST to the public, unauthenticated job-board endpoints the ATS documents for career
sites; no browser, no account, nothing is submitted:

  greenhouse  https://boards-api.greenhouse.io/v1/boards/<board>/jobs/<id>?questions=true
  ashby       https://jobs.ashbyhq.com/api/non-user-graphql (operation ApiJobPosting, the hosted page's own query)
  lever       https://api.lever.co/v0/postings/<site>/<id> (Lever's public posting API has no custom questions: the
              file says `questions_known: false` and the applier still reads the form)

Output (`form_questions.json`): {"url", "ats", "title", "questions_known", "fetched", "questions": [{"label",
"required", "kind", "options"}]} where kind is `text` (free text the writer must answer), `choice` (options listed),
`file`, or `contact` (name, e-mail, phone, links, location: contact.yaml fills them). An ATS this tool cannot read, or
a network failure, exits 1 with the reason and writes nothing: the writer then lists the questions from the form page.
Exit 0 written, 1 not readable, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jobs_common as jc  # noqa: E402

TIMEOUT = 30
CONTACT = re.compile(r"^(first name|last name|preferred (first )?name|full name|name|e-?mail|phone( number)?:?|"
                     r"linkedin( profile| url)?|github|website|portfolio|location|city)$", re.I)
ASHBY_QUERY = ("query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) { "
               "jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName, jobPostingId: "
               "$jobPostingId) { id title applicationForm { sections { title fieldEntries { ... on FormFieldEntry "
               "{ id isRequired field } } } } } }")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


class Unreadable(Exception):
    """The form cannot be read through an API: the writer lists the questions from the page instead."""


def http(url: str, body: dict | None = None) -> dict:
    """GET (or POST JSON) through curl, the squad's one HTTP client; a failure is Unreadable, never an empty form."""
    argv = ["curl", "-sS", "--fail", "--max-time", str(TIMEOUT), "-H", "accept: application/json"]
    if body is not None:
        argv += ["-H", "content-type: application/json", "--data", json.dumps(body)]
    try:
        done = subprocess.run([*argv, url], capture_output=True, text=True, timeout=TIMEOUT + 5)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Unreadable(f"{urlsplit(url).netloc}: {exc}") from None
    if done.returncode != 0:
        raise Unreadable(f"{urlsplit(url).netloc}: {(done.stderr or '').strip()[:200] or 'request failed'}")
    try:
        return json.loads(done.stdout)
    except ValueError:
        raise Unreadable(f"{urlsplit(url).netloc} did not answer JSON") from None


def kind_of(label: str, field_type: str, options: list) -> str:
    t = (field_type or "").lower()
    if "file" in t:
        return "file"
    if CONTACT.match(label.strip()) or t in ("email", "phone", "location"):
        return "contact"
    if options or "select" in t or t in ("boolean", "valueselect", "multivalueselect"):
        return "choice"
    return "text"


def question(label, required, field_type, options=()) -> dict:
    label = re.sub(r"\s+", " ", str(label or "")).strip()
    options = [str(o) for o in options if str(o).strip()]
    return {"label": label, "required": bool(required), "kind": kind_of(label, field_type, options),
            "options": options[:50]}


def parse_greenhouse(raw: dict) -> tuple[str, list]:
    out = []
    for q in raw.get("questions") or []:
        fields = q.get("fields") or [{}]
        types = [str(f.get("type") or "") for f in fields]
        # Resume/CV is a file input with a paste-text alternative: the file decides.
        field_type = "input_file" if any("file" in t for t in types) else types[0]
        options = [v.get("label") for f in fields for v in (f.get("values") or []) if isinstance(v, dict)]
        out.append(question(q.get("label"), q.get("required"), field_type, options))
    return str(raw.get("title") or ""), out


def parse_ashby(raw: dict) -> tuple[str, list]:
    posting = ((raw.get("data") or {}).get("jobPosting")) or {}
    if not posting:
        raise Unreadable("ashby: no such posting (closed, or the link is not a posting)")
    out = []
    for section in (posting.get("applicationForm") or {}).get("sections") or []:
        for entry in section.get("fieldEntries") or []:
            field = entry.get("field") or {}
            options = [v.get("label") for v in field.get("selectableValues") or [] if isinstance(v, dict)]
            out.append(question(field.get("title"), entry.get("isRequired"), field.get("type"), options))
    return str(posting.get("title") or ""), out


def parse_lever(raw: dict) -> tuple[str, list]:
    if not isinstance(raw, dict) or not raw.get("id"):
        raise Unreadable("lever: no such posting")
    return str(raw.get("text") or ""), []


def fetch(url: str) -> dict:
    parts = urlsplit(url.strip())
    host, segs = parts.netloc.lower(), [s for s in parts.path.split("/") if s]
    if parts.scheme != "https":
        raise Unreadable("only an https posting link is read")
    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io") and len(segs) >= 3 and segs[1] == "jobs":
        raw = http(f"https://boards-api.greenhouse.io/v1/boards/{segs[0]}/jobs/{segs[2]}?questions=true")
        return {"ats": "greenhouse", "known": True, "parsed": parse_greenhouse(raw)}
    if host == "jobs.ashbyhq.com" and len(segs) >= 2 and UUID.fullmatch(segs[1]):
        raw = http("https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting",
                   {"operationName": "ApiJobPosting", "query": ASHBY_QUERY,
                    "variables": {"organizationHostedJobsPageName": segs[0], "jobPostingId": segs[1]}})
        return {"ats": "ashby", "known": True, "parsed": parse_ashby(raw)}
    if host == "jobs.lever.co" and len(segs) >= 2 and UUID.fullmatch(segs[1]):
        raw = http(f"https://api.lever.co/v0/postings/{segs[0]}/{segs[1]}")
        return {"ats": "lever", "known": False, "parsed": parse_lever(raw)}
    raise Unreadable(f"{host or url}: no public form API this tool reads (greenhouse, ashby, lever); list the "
                     "questions from the form page")


def document(url: str, ats: str, known: bool, parsed: tuple[str, list]) -> dict:
    title, questions = parsed
    return {"url": url, "ats": ats, "title": title, "questions_known": known, "fetched": date.today().isoformat(),
            "questions": questions,
            "required_text": [q["label"] for q in questions if q["required"] and q["kind"] == "text"]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Read an ATS application form's questions from its public API.")
    p.add_argument("url", nargs="?", help="the employer ATS posting (opening.md apply_url)")
    p.add_argument("--out", help="write the JSON here (application/form_questions.json)")
    p.add_argument("--json", action="store_true", help="print the JSON")
    p.add_argument("--from-file", help="parse a saved API answer instead of fetching (tests, replays)")
    p.add_argument("--ats", choices=("greenhouse", "ashby", "lever"), help="the ATS of --from-file")
    args = p.parse_args(argv)
    if bool(args.from_file) == bool(args.url) or (args.from_file and not args.ats):
        p.error("give a posting URL, or --from-file with --ats")
    try:
        if args.from_file:
            raw = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
            parser = {"greenhouse": parse_greenhouse, "ashby": parse_ashby, "lever": parse_lever}[args.ats]
            doc = document(args.url or "", args.ats, args.ats != "lever", parser(raw))
        else:
            got = fetch(args.url)
            doc = document(args.url.strip(), got["ats"], got["known"], got["parsed"])
    except Unreadable as exc:
        print(f"form_questions: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"form_questions: cannot read {args.from_file}: {exc}", file=sys.stderr)
        return 2
    if args.out:
        jc.write_json(Path(args.out), doc)
    if args.json or not args.out:
        print(json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        print(f"{len(doc['questions'])} questions ({len(doc['required_text'])} required free text) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
