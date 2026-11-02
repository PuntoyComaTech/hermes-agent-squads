#!/usr/bin/env python3
"""Set an opening's apply_url to the employer's own posting, found after intake.

  apply_link.py <opening_dir> <url> --by BOT [--source TEXT] [--json]

The applier submits only on `apply_url` in opening.md. The intake link (often a portal page such as a LinkedIn listing)
stays in `url`; when the scout or the reviewer later locates the employer's own ATS posting, this tool writes it as
`apply_url`, so the applier never stops on a portal link the squad already replaced. The link must be an employer ATS
page by link_check.py (kind `ats`, verdict `verified` or `official_ats`); a portal, a job board or an unverified host is
refused and nothing is written. The front matter keeps every other line as it was, and `status.json` gets one history
line through status.py (the status itself does not change).

One employer posting is one opening. When an earlier opening (by id) or a tracker.csv row already holds the same
canonical employer URL (job_key.employer_url), this opening is a re-listing under another portal title: it is set
`discarded` naming the earlier one, the earlier opening gets a history line naming this listing, its seen.json entry
becomes an alias of the earlier entry, and the output says `duplicate_of`.

Exit 0 written (or already set), 1 refused (the reason on stderr), 2 usage error or an opening without opening.md.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jobs_common as jc  # noqa: E402
import job_key as jk  # noqa: E402
import link_check as lc  # noqa: E402
import seen_state as ss  # noqa: E402
import status as st  # noqa: E402

FRONT = re.compile(r"\A(\ufeff?---[ \t]*\n)(.*?)(\n---[ \t]*(?:\n|\Z))", re.S)
APPLY_LINE = re.compile(r"^apply_url:.*$", re.M)
URL_LINE = re.compile(r"^url:.*$", re.M)


def refusal(url: str) -> str | None:
    """Why this link may not become apply_url, or None when it is an employer ATS posting."""
    try:
        data = lc.load_data(lc.DATA_FILE)
    except lc.DataError as exc:
        return f"official_hosts.json unreadable: {exc}"
    result = lc.classify(url, data)
    if result["verdict"] == "new_platform":
        return None  # an employer site or an ATS not listed yet, with no sign of fraud
    if result["verdict"] not in ("verified", "official_ats") or result["kind"] != "ats":
        return (f"link_check.py says verdict '{result['verdict']}', kind '{result['kind']}': only an employer ATS "
                "posting replaces apply_url")
    return None


def set_apply_url(opening_dir: Path, url: str, by: str, source: str = "") -> dict:
    """Write apply_url into opening.md. Raises ValueError with the reason when refused."""
    url = url.strip()
    path = opening_dir / "opening.md"
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist")
    text = path.read_text(encoding="utf-8")
    match = FRONT.match(text)
    if not match:
        raise ValueError(f"{path} has no front matter")
    reason = refusal(url)
    if reason:
        raise ValueError(reason)
    before = str(jc.split_front_matter(text)[0].get("apply_url") or "")
    if before == url:
        return {"changed": False, "apply_url": url, "previous": before}
    head = match.group(2)
    line = f"apply_url: {url}"
    if APPLY_LINE.search(head):
        head = APPLY_LINE.sub(lambda _m: line, head, count=1)
    elif URL_LINE.search(head):
        head = URL_LINE.sub(lambda m: m.group(0) + "\n" + line, head, count=1)
    else:
        head = head + "\n" + line
    jc.atomic_write(path, match.group(1) + head + match.group(3) + text[match.end():])
    if jc.split_front_matter(path.read_text(encoding="utf-8"))[0].get("apply_url") != url:
        path.write_text(text, encoding="utf-8")
        raise RuntimeError("opening.md did not read back with the new apply_url; restored")
    current = st._load(opening_dir / "status.json", opening_dir.name).get("status")
    if current:
        note = f"apply_url -> employer posting {url}" + (f" ({source})" if source else "")
        st.append(opening_dir, current, by, note)
    return {"changed": True, "apply_url": url, "previous": before, **relisting(opening_dir, url, by)}


def relisting(opening_dir: Path, url: str, by: str) -> dict:
    """When an earlier opening or a tracker.csv row already holds this employer posting, this opening is a re-listing:
    it is set `discarded` naming the owner, the owner's history names this listing, and its seen.json entry becomes
    an alias of the owner's. {} when this opening is the first one of the posting."""
    project = opening_dir.resolve().parent.parent
    owners = jk.posting_owners(project, url, exclude=opening_dir.name, earlier_only=True)
    if not owners:
        return {}
    owner = owners[0]
    if st._load(opening_dir / "status.json", opening_dir.name).get("status") != "discarded":
        st.append(opening_dir, "discarded", by, f"same employer posting as {owner['opening_id']} "
                                                 f"({owner['status'] or owner['via']}): {url}; not a new opening")
    meta = jc.read_front_matter(opening_dir / "opening.md")
    owner_dir = project / "openings" / str(owner["opening_id"])
    if owner["via"] == "opening":
        ss.note_relisting(project, owner["opening_id"], f"re-listed as '{meta.get('role') or opening_dir.name}' "
                                                         f"({meta.get('source') or 'listing'} {meta.get('url')}, "
                                                         f"{opening_dir.name}); same employer posting")
    merged = None
    state = ss.state_path(project)
    if state.is_file():
        with jc.locked(state):
            doc = ss.load_state(state)
            seen = doc["seen"]
            mine = next((k for k, e in seen.items() if isinstance(e, dict) and e.get("opening_id") == opening_dir.name),
                        None)
            theirs = next((k for k, e in seen.items() if isinstance(e, dict) and e.get("opening_id") == owner["opening_id"]
                           and owner_dir.is_dir()), None)
            if mine and theirs and mine != theirs:
                seen[theirs].setdefault("employer_url", jk.employer_url(url))
                entry = seen[theirs]
                old = seen.pop(mine)
                alias = {k: v for k, v in {"key": mine, "title": old.get("title"), "url": old.get("url"),
                                           "portal": old.get("portal"), "first_seen": old.get("first_seen"),
                                           "opening_id": opening_dir.name}.items() if v}
                entry["aliases"] = [a for a in entry.get("aliases") or [] if a.get("key") != mine] + [alias]
                ss.save_state(state, doc)
                merged = theirs
    return {"duplicate_of": owner["opening_id"], "duplicate_status": owner["status"], "seen_alias_of": merged}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Set an opening's apply_url to the employer's own ATS posting.")
    p.add_argument("opening_dir", type=Path, help="<P>/openings/<ID>")
    p.add_argument("url", help="the employer's own posting (an ATS page link_check.py clears)")
    p.add_argument("--by", required=True, help="the bot recording it, e.g. jobs-reviewer")
    p.add_argument("--source", default="", help="where it was found, e.g. 'review-5 truthfulness'")
    p.add_argument("--json", action="store_true", help="print the result as JSON")
    args = p.parse_args(argv)
    try:
        result = set_apply_url(args.opening_dir, args.url, args.by, args.source)
    except FileNotFoundError as exc:
        print(f"apply_link: {exc}", file=sys.stderr)
        return 2
    except (ValueError, RuntimeError) as exc:
        print(f"apply_link: refused: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(("apply_url set: " if result["changed"] else "apply_url already set: ") + result["apply_url"])
        if result.get("duplicate_of"):
            print(f"duplicate: same employer posting as {result['duplicate_of']} ({result['duplicate_status']}); "
                  "this opening is discarded: no analysis, writer or applier card")
    return 0


if __name__ == "__main__":
    sys.exit(main())
