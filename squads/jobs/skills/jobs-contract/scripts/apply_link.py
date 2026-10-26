#!/usr/bin/env python3
"""Set an opening's apply_url to the employer's own posting, found after intake.

  apply_link.py <opening_dir> <url> --by BOT [--source TEXT] [--json]

The applier submits only on `apply_url` in opening.md. The intake link (often a portal page such as a LinkedIn listing)
stays in `url`; when the scout or the reviewer later locates the employer's own ATS posting, this tool writes it as
`apply_url`, so the applier never stops on a portal link the squad already replaced. The link must be an employer ATS
page by link_check.py (kind `ats`, verdict `verified` or `official_ats`); a portal, a job board or an unverified host is
refused and nothing is written. The front matter keeps every other line as it was, and `status.json` gets one history
line through status.py (the status itself does not change).

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
import link_check as lc  # noqa: E402
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
    return {"changed": True, "apply_url": url, "previous": before}


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
    return 0


if __name__ == "__main__":
    sys.exit(main())
