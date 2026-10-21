#!/usr/bin/env python3
"""Pipeline dashboard of one job-search project: one offline HTML file, reports/dashboard.html.

  build_dashboard.py --project P [--today YYYY-MM-DD] [--out FILE]

The page has inline CSS, no script, no external requests, and every value HTML-escaped. Sections: summary counts,
the funnel by status, the fit score distribution, deadlines (soon, passed, unreadable), follow-ups due, the shortlist
of ranked openings from searches/seen.json, and one timeline per application from openings/<ID>/status.json.
URLs are shown as text, never as links. Data comes from tracker.csv and the opening folders; nothing is written
except the one report file.

Output: a JSON summary on stdout. Exit 0 on success, 1 on unusable data (the reason on stderr), 2 on usage errors.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs_common as jc  # noqa: E402
import tracker as tk  # noqa: E402

STATUS_ORDER = ("found", "analyzed", "in_preparation", "in_review", "not_approved", "ready", "delivered", "applying",
                "manual_application", "applied", "followed_up", "screening", "interview", "waiting", "offer", "hired",
                "rejected", "no_response", "withdrawn", "closed", "skipped", "discarded")
BUCKET_LABELS = (("not_sent", "Not sent"), ("active", "Active"), ("interview", "Interview"), ("offer", "Offer"),
                 ("hired", "Hired"), ("closed", "Closed"), ("unrecognised", "Unrecognised"))
BAND_ORDER = ("strong", "good", "moderate", "weak", "poor", "unscored")
SHORTLIST_MAX = 15

CSS = """
:root { --ink:#1f2933; --muted:#616e7c; --line:#d9e2ec; --accent:#2b8a3e; --bg:#f5f7fa; }
* { box-sizing: border-box; }
body { margin:0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; color:var(--ink); background:var(--bg); }
main { max-width: 1100px; margin: 0 auto; padding: 24px; }
h1 { margin: 0 0 4px; font-size: 26px; }
h2 { font-size: 18px; margin: 28px 0 10px; }
h3 { font-size: 15px; margin: 16px 0 6px; }
.meta { color: var(--muted); font-size: 13px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-top: 16px; }
.card { background:#fff; border:1px solid var(--line); border-left:4px solid var(--accent); border-radius:6px; padding:10px 12px; }
.card .num { font-size: 24px; font-weight: 700; }
.card .label { font-size: 12px; color: var(--muted); }
table { width: 100%; border-collapse: collapse; background:#fff; border:1px solid var(--line); }
th, td { text-align: left; padding: 7px 9px; border-bottom: 1px solid var(--line); font-size: 14px; vertical-align: top; }
th { background: #eef2f6; font-weight: 600; }
tr:nth-child(even) td { background: #fafbfc; }
.bar { display:inline-block; height: 10px; background: var(--accent); border-radius: 3px; min-width: 0; }
.bar-cell { width: 40%; }
ol.timeline { margin: 6px 0 0; padding-left: 20px; font-size: 14px; }
ol.timeline li { margin-bottom: 4px; }
.empty { color: var(--muted); font-size: 14px; }
footer { margin-top: 32px; color: var(--muted); font-size: 12px; }
@media (max-width: 700px) { main { padding: 12px; } th, td { font-size: 13px; } }
"""


def esc(value) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def bar(count: int, top: int) -> str:
    pct = 0 if top <= 0 else round(100 * count / top)
    return f'<span class="bar" style="width:{pct}%"></span>'


def table(headers, rows) -> str:
    """rows hold HTML cells that are already escaped by the caller."""
    if not rows:
        return '<p class="empty">Nothing to show yet.</p>'
    head = "".join(f"<th>{esc(name)}</th>" for name in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def shortlist(project: Path, cfg: dict) -> list:
    """Ranked openings from searches/seen.json, best score first."""
    path = project / "searches" / "seen.json"
    if not path.is_file():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise tk.DataError(f"{path}: {exc}")
    seen = doc.get("seen") if isinstance(doc, dict) else None
    if not isinstance(seen, dict):
        raise tk.DataError(f"{path}: expected an object with a seen map")
    items = []
    for entry in seen.values():
        if not isinstance(entry, dict) or entry.get("status") != "ranked":
            continue
        score = entry.get("score")
        if isinstance(score, dict):
            score = score.get("score")
        score = number(score)
        items.append({
            "company": str(entry.get("company") or ""), "title": str(entry.get("title") or ""),
            "score": score, "band": tk.fit_band(score, cfg["bands"]) if score is not None else "unscored",
        })
    items.sort(key=lambda i: (-(i["score"] if i["score"] is not None else -1), i["company"].casefold(),
                              i["title"].casefold()))
    return items[:SHORTLIST_MAX]


def timelines(project: Path) -> list:
    folder = project / "openings"
    out = []
    for item in sorted(folder.glob("*")) if folder.is_dir() else []:
        path = item / "status.json"
        if not item.is_dir() or not path.is_file():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise tk.DataError(f"{path}: {exc}")
        history = doc.get("history") if isinstance(doc, dict) else None
        out.append({"id": item.name, "status": doc.get("status") if isinstance(doc, dict) else None,
                    "history": [h for h in history or [] if isinstance(h, dict)]})
    return out


def flag_text(row: dict) -> str:
    if row["deadline_flag"] == "invalid":
        return "date not readable"
    days = row["days_to_deadline"]
    if row["deadline_flag"] == "passed":
        return f"passed {-days} days ago"
    return f"in {days} days" if days is not None else ""


def build(project: Path, today: date):
    tracker = tk.Tracker(project / tk.FILE_NAME).load()
    cfg = tk.settings(project)
    rows = [tk.describe(tracker.record(i), today) for i in range(len(tracker.rows))]
    due, at_cap, _ = tk.due_items(tracker, today, cfg["follow_up_days"], cap=True)
    shortlist_items = shortlist(project, cfg)
    timeline_items = timelines(project)

    buckets = Counter(row["bucket"] for row in rows)
    cards = (f'<div class="card"><div class="num">{len(rows)}</div><div class="label">Tracked</div></div>'
             + "".join(
                 f'<div class="card"><div class="num">{buckets.get(key, 0)}</div>'
                 f'<div class="label">{esc(label)}</div></div>'
                 for key, label in BUCKET_LABELS if key in ("not_sent", "active", "interview", "offer", "hired", "closed")))

    counts = Counter(row["status"] for row in rows)
    funnel_keys = [s for s in STATUS_ORDER if counts.get(s)] + sorted(
        s for s in counts if s not in STATUS_ORDER)
    top = max(counts.values()) if counts else 0
    funnel = table(["Status", "Applications", ""],
                   [[esc(s), esc(counts[s]), f'<div class="bar-cell">{bar(counts[s], top)}</div>']
                    for s in funnel_keys])

    scores = Counter(tk.fit_band(row.get("fit_score"), cfg["bands"]) for row in rows)
    top_band = max(scores.values()) if scores else 0
    score_rows = [[esc(b), esc(scores[b]), f'<div class="bar-cell">{bar(scores[b], top_band)}</div>']
                  for b in BAND_ORDER if scores.get(b)]
    fit = table(["Fit band", "Applications", ""], score_rows)

    deadlines = sorted((r for r in rows if r["deadline_flag"] in ("soon", "passed", "invalid")),
                       key=lambda r: (r["days_to_deadline"] is None, r["days_to_deadline"] or 0, r["id"]))
    deadline_table = table(["Company", "Role", "Status", "Deadline", "When"],
                           [[esc(r["company"]), esc(r["role"]), esc(r["status"]), esc(r["deadline"]),
                             esc(flag_text(r))] for r in deadlines])

    followups = table(["Company", "Role", "Quiet days", "Follow-ups sent", "Draft to write"],
                      [[esc(i["company"]), esc(i["role"]), esc(i["quiet_days"]), esc(i["follow_ups_sent"]),
                        esc(i["draft_path"])] for i in due])

    shortlist_table = table(["Company", "Role", "Score", "Band"],
                            [[esc(i["company"]), esc(i["title"]), esc(i["score"] if i["score"] is not None else "-"),
                              esc(i["band"])] for i in shortlist_items])

    timeline_html = []
    for item in timeline_items:
        steps = "".join(
            f"<li>{esc(h.get('date', ''))} - <strong>{esc(h.get('status', ''))}</strong> by "
            f"{esc(h.get('by', ''))}{(' - ' + esc(h.get('note'))) if h.get('note') else ''}</li>"
            for h in item["history"])
        timeline_html.append(
            f"<h3>{esc(item['id'])} <span class=\"meta\">current: {esc(item['status'] or 'unknown')}</span></h3>"
            f'<ol class="timeline">{steps or "<li>No history yet.</li>"}</ol>')
    timelines_block = "".join(timeline_html) or '<p class="empty">No opening folders yet.</p>'

    body = f"""
<h1>Pipeline</h1>
<div class="meta">As of {esc(today.isoformat())} - {len(rows)} tracked application(s). Offline report, generated from
tracker.csv and the opening folders.</div>
<div class="cards">{cards}</div>
<h2>Funnel by status</h2>{funnel}
<h2>Fit score bands</h2>{fit}
<h2>Deadlines</h2>{deadline_table}
<h2>Follow-ups due</h2>
<div class="meta">{len(due)} due; {len(at_cap)} at the follow-up cap of {tk.FOLLOW_UP_CAP}.</div>
{followups}
<h2>Shortlist (ranked openings)</h2>{shortlist_table}
<h2>Timelines</h2>{timelines_block}
<footer>Offline report: no scripts, no external requests. Values are escaped on output.</footer>
"""
    page = ("<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            "<title>Pipeline dashboard</title>\n<style>" + CSS + "</style>\n</head>\n<body>\n<main>"
            + body + "</main>\n</body>\n</html>\n")
    summary = {"tracked": len(rows), "by_bucket": dict(sorted(buckets.items())), "follow_ups_due": len(due),
               "deadlines_flagged": len(deadlines), "shortlist": len(shortlist_items),
               "timelines": len(timeline_items)}
    return page, summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Build reports/dashboard.html, one offline page for the pipeline.")
    parser.add_argument("--project", help="project folder holding profile.md (default: $JOBS_PROJECT, else the "
                                          "current folder)")
    parser.add_argument("--today", help="YYYY-MM-DD in place of the local date (tests and replays)")
    parser.add_argument("--out", help="output file (default <P>/reports/dashboard.html)")
    args = parser.parse_args(argv)
    try:
        today = tk.date_arg(args.today) if args.today else date.fromisoformat(jc.today())
        project = jc.project_dir(args.project or os.environ.get("JOBS_PROJECT"))
        page, summary = build(project, today)
        out = Path(args.out) if args.out else project / "reports" / "dashboard.html"
        jc.atomic_write(out, page)
    except tk.DataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"written": str(out), **summary}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
