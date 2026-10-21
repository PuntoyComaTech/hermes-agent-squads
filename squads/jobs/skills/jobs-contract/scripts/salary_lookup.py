#!/usr/bin/env python3
"""Benchmark a company's pay against the user's own salary data file.

The data file is the user's: a JSON document or a wide CSV they keep themselves. Its path is `salary_data` in
profile.md (relative to the project folder), or --data FILE. With no file configured, the lookup is skipped:
exit 0 and `available: false`. Nothing here fetches anything.

JSON format (canonical; --convert writes it):
  {"metadata": {"source": "...", "index_baseline": 100, "index_label": "Index",
                "baseline_description": "Index 100 = median pay"},
   "companies": [{"company": "Example Co", "city": "Lima",
                  "categories": {"all_employees": {"count": 500, "index": 108.5}}}]}

Wide CSV format: columns `company` (required), `city` (optional), then for each category either `<name>_count`
and `<name>_index`, or a bare `count` / `index` column (category `all_employees`). Decimal point is `.`; a comma is
a decimal separator unless it groups thousands (1,234 or 1,234,567). Unknown columns are reported and ignored.

Company matching ignores case, accents and punctuation, and drops common legal-form words (inc, ltd, gmbh, sa...).
Scores: 100 identical, 80-90 one name contains the other, lower for partial word overlap; below 50 is no match.

Usage:
  salary_lookup.py "Example Co" --project P [--city C] [--json]
  salary_lookup.py "Example Co" --data FILE [--json]
  salary_lookup.py --list-all --project P
  salary_lookup.py --convert FILE.csv [--out FILE.json] [--source S] [--baseline 100] [--baseline-desc D]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs_common as jc  # noqa: E402

MIN_SCORE = 50
DEFAULT_CATEGORY = "all_employees"
LEGAL_WORDS = frozenset({
    "inc", "llc", "ltd", "limited", "corp", "corporation", "co", "company", "plc", "group", "holding", "holdings",
})
THOUSANDS = re.compile(r"[-+]?\d{1,3}(,\d{3})+(\.\d+)?$")


class SalaryError(Exception):
    """The data file is malformed or a conversion input is unusable. Reported on stderr with exit 1."""


# --- text ---------------------------------------------------------------------------------------------------------

def fold(text) -> str:
    flat = unicodedata.normalize("NFKD", str(text or "").casefold())
    flat = "".join(ch for ch in flat if not unicodedata.combining(ch))
    return " ".join("".join(ch if ch.isalnum() else " " for ch in flat).split())


def tokens(name) -> list:
    words = fold(name).split()
    core = [word for word in words if word not in LEGAL_WORDS]
    return core or words


def match_score(query_tokens: list, name) -> int:
    name_tokens = tokens(name)
    if not query_tokens or not name_tokens:
        return 0
    qj, nj = "".join(query_tokens), "".join(name_tokens)
    if qj == nj:
        return 100
    qs, ns = set(query_tokens), set(name_tokens)
    common = qs & ns
    small, big = sorted((len(qj), len(nj)))
    if (qs <= ns or ns <= qs) and common and small >= 3:
        return 80 + int(10 * small / big)
    if small >= 5 and (qj in nj or nj in qj):
        return 70 + int(10 * small / big)
    jaccard = len(common) / len(qs | ns)
    return int(100 * jaccard) if jaccard >= 0.5 else 0


# --- loading ------------------------------------------------------------------------------------------------------

def _number(text, where: str):
    raw = str(text or "").strip().replace("\u00a0", "").replace(" ", "")
    if not raw:
        return None
    if THOUSANDS.match(raw):
        raw = raw.replace(",", "")
    elif "," in raw and "." not in raw:
        raw = raw.replace(",", ".")
    elif "," in raw:
        raise SalaryError(f"{where}: ambiguous number {text!r}; use '.' for decimals")
    try:
        value = float(raw)
    except ValueError:
        raise SalaryError(f"{where}: not a number: {text!r}")
    if not math.isfinite(value):
        raise SalaryError(f"{where}: number must be finite")
    return value


def parse_csv(text: str, source_name: str = "csv"):
    """Wide CSV -> (companies, warnings). Raises SalaryError on a malformed numeric cell."""
    reader = csv.reader(text.splitlines())
    try:
        header = [cell.strip() for cell in next(reader)]
    except StopIteration:
        raise SalaryError("CSV is empty")
    lowered = [cell.lower() for cell in header]
    if "company" not in lowered:
        raise SalaryError("CSV needs a 'company' column")
    company_at = lowered.index("company")
    city_at = lowered.index("city") if "city" in lowered else None

    fields = []  # (column index, category, field)
    warnings = []
    for index, name in enumerate(lowered):
        if index in (company_at, city_at) or not name:
            continue
        if name in ("count", "index"):
            fields.append((index, DEFAULT_CATEGORY, name))
        elif name.endswith("_count") and len(name) > 6:
            fields.append((index, name[:-6], "count"))
        elif name.endswith("_index") and len(name) > 6:
            fields.append((index, name[:-6], "index"))
        else:
            warnings.append(f"column {header[index]!r} is not <name>_count, <name>_index, count or index; ignored")

    companies = []
    for line_no, row in enumerate(reader, start=2):
        if not any(cell.strip() for cell in row):
            continue
        name = row[company_at].strip() if company_at < len(row) else ""
        if not name:
            continue
        entry = {"company": name, "city": (row[city_at].strip() if city_at is not None and city_at < len(row) else ""),
                 "categories": {}}
        for index, category, field in fields:
            cell = row[index] if index < len(row) else ""
            value = _number(cell, f"line {line_no}, {header[index]}")
            if value is None:
                continue
            slot = entry["categories"].setdefault(category, {"count": None, "index": None})
            slot[field] = int(round(value)) if field == "count" else value
        companies.append(entry)
    return companies, warnings


def validate_document(doc) -> dict:
    if not isinstance(doc, dict):
        raise SalaryError("top-level JSON value must be an object")
    meta = doc.get("metadata") or {}
    if not isinstance(meta, dict):
        raise SalaryError("'metadata' must be an object")
    baseline = meta.get("index_baseline", 100)
    if isinstance(baseline, bool) or not isinstance(baseline, (int, float)) or not math.isfinite(baseline):
        raise SalaryError("'metadata.index_baseline' must be a finite number")
    companies = doc.get("companies")
    if not isinstance(companies, list):
        raise SalaryError("'companies' must be a list")
    for number, entry in enumerate(companies, start=1):
        if not isinstance(entry, dict) or not str(entry.get("company") or "").strip():
            raise SalaryError(f"companies[{number}] needs a non-empty 'company'")
        categories = entry.get("categories") or {}
        if not isinstance(categories, dict):
            raise SalaryError(f"companies[{number}].categories must be an object")
        for name, slot in categories.items():
            if not isinstance(slot, dict):
                raise SalaryError(f"companies[{number}].categories.{name} must be an object")
            for field in ("count", "index"):
                value = slot.get(field)
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                    raise SalaryError(f"companies[{number}].categories.{name}.{field} must be a number or null")
    return {
        "metadata": {
            "source": str(meta.get("source") or ""),
            "index_baseline": float(baseline),
            "index_label": str(meta.get("index_label") or "Index"),
            "baseline_description": str(meta.get("baseline_description") or ""),
        },
        "companies": [
            {
                "company": str(entry["company"]).strip(),
                "city": str(entry.get("city") or "").strip(),
                "categories": entry.get("categories") or {},
            }
            for entry in companies
        ],
    }


def load_file(path: Path) -> dict:
    if not path.is_file():
        raise SalaryError(f"salary data file not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".csv":
        companies, _ = parse_csv(text)
        return validate_document({"metadata": {"source": path.name}, "companies": companies})
    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise SalaryError(f"{path} is not valid JSON: {exc}")
    return validate_document(doc)


def configured_path(project: Path | None, override: str | None):
    """(path or None, reason). The override wins; otherwise profile.md salary_data, relative to the project."""
    if override:
        return Path(override).expanduser(), None
    if project is None:
        return None, "no project folder given and no --data file"
    value = jc.read_front_matter(project / "profile.md").get("salary_data")
    if value in (None, ""):
        return None, "salary_data is not set in profile.md"
    path = Path(str(value)).expanduser()
    return (path if path.is_absolute() else project / path), None


# --- lookup -------------------------------------------------------------------------------------------------------

def search(data: dict, query: str, city: str | None = None) -> list:
    query_tokens = tokens(query)
    found = []
    for entry in data["companies"]:
        if city and fold(city) not in fold(entry.get("city")):
            continue
        score = match_score(query_tokens, entry["company"])
        if score >= MIN_SCORE:
            found.append((score, entry))
    found.sort(key=lambda pair: (-pair[0], pair[1]["company"].casefold()))
    return found


def vs_baseline(index, baseline: float):
    if not isinstance(index, (int, float)) or baseline == 0:
        return None
    return round((index - baseline) / baseline * 100, 1)


def describe(entry: dict, baseline: float) -> dict:
    categories = {}
    for name, slot in (entry.get("categories") or {}).items():
        index = slot.get("index")
        categories[name] = {
            "count": slot.get("count"),
            "index": index,
            "vs_baseline_pct": vs_baseline(index, baseline),
        }
    return {"company": entry["company"], "city": entry.get("city") or "", "categories": categories}


def benchmark_for(data: dict, company: str, city: str | None = None):
    """The compact benchmark analysis.json stores as salary_benchmark, or None when nothing matches."""
    found = search(data, company, city)
    if not found:
        return None
    score, entry = found[0]
    meta = data["metadata"]
    summary = describe(entry, meta["index_baseline"])
    summary.update({
        "source": meta["source"],
        "score": score,
        "baseline": meta["index_baseline"],
        "index_label": meta["index_label"],
        "other_matches": len(found) - 1,
    })
    return summary


def project_benchmark(project: Path, company: str, city: str | None = None):
    """analysis.json helper: the benchmark for a company, or None when there is no file or no match."""
    path, _ = configured_path(project, None)
    if path is None or not path.is_file():
        return None
    return benchmark_for(load_file(path), company, city)


# --- output -------------------------------------------------------------------------------------------------------

def render_text(query: str, city, matches: list, meta: dict) -> str:
    if not matches:
        hint = f" (city {city})" if city else ""
        return f"No match for {query!r}{hint}. Try a shorter name; legal suffixes are ignored."
    lines = [f"{len(matches)} match(es) for {query!r}:"]
    for summary in matches:
        place = f" ({summary['city']})" if summary["city"] else ""
        lines.append("")
        lines.append(f"{summary['company']}{place}")
        lines.append(f"  {'Category':<20} {'Count':>7} {meta['index_label']:>8} {'vs baseline':>12}")
        for name, slot in summary["categories"].items():
            count = "-" if slot["count"] is None else str(slot["count"])
            index = "-" if slot["index"] is None else f"{slot['index']:.1f}"
            pct = "" if slot["vs_baseline_pct"] is None else f"{slot['vs_baseline_pct']:+.1f}%"
            lines.append(f"  {name.replace('_', ' '):<20} {count:>7} {index:>8} {pct:>12}")
        lines.append(f"  Baseline: {meta['baseline_description'] or meta['index_label'] + ' ' + format(meta['index_baseline'], 'g')}")
    return "\n".join(lines)


def _force_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8")


def cmd_convert(args) -> int:
    source = Path(args.convert)
    if not source.is_file():
        raise SalaryError(f"not found: {source}")
    companies, warnings = parse_csv(source.read_text(encoding="utf-8-sig"))
    document = validate_document({
        "metadata": {
            "source": args.source or source.stem,
            "index_baseline": args.baseline,
            "index_label": "Index",
            "baseline_description": args.baseline_desc or f"Index {format(args.baseline, 'g')} = baseline",
        },
        "companies": companies,
    })
    out = Path(args.out) if args.out else source.with_suffix(".json")
    jc.write_json(out, document)
    for note in warnings:
        print(f"warning: {note}", file=sys.stderr)
    print(json.dumps({"written": str(out), "companies": len(companies)}, indent=2))
    return 0


def default_project(explicit):
    """--project, else $JOBS_PROJECT, else the current folder when it holds profile.md, else None (no profile)."""
    if explicit or os.environ.get("JOBS_PROJECT") or (Path.cwd() / "profile.md").is_file():
        return jc.project_dir(explicit)
    return None


def cmd_lookup(args) -> int:
    project = default_project(args.project)
    path, reason = configured_path(project, args.data)
    if path is None or not path.is_file():
        note = reason or f"salary data file not found: {path}"
        if args.json:
            print(json.dumps({"available": False, "reason": note}, indent=2, ensure_ascii=False))
        else:
            print(f"Salary benchmark skipped: {note}.")
        return 0
    data = load_file(path)
    meta = data["metadata"]

    if args.list_all:
        rows = [{"company": e["company"], "city": e["city"]} for e in data["companies"]]
        print(json.dumps(rows, indent=2, ensure_ascii=False) if args.json
              else "\n".join(f"{r['company']}" + (f" ({r['city']})" if r["city"] else "") for r in rows))
        return 0

    found = search(data, args.company, args.city)
    matches = [dict(describe(entry, meta["index_baseline"]), score=score) for score, entry in found]
    if args.json:
        payload = {"available": True, "query": args.company, "city": args.city, "source": meta["source"],
                   "baseline": meta["index_baseline"], "index_label": meta["index_label"], "matches": matches}
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(render_text(args.company, args.city, matches, meta))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Benchmark a company's pay against the user's own salary data file.")
    ap.add_argument("company", nargs="?", help="company name to look up")
    ap.add_argument("--project", help="project folder whose profile.md names the salary file")
    ap.add_argument("--data", help="salary file to read (overrides profile.md)")
    ap.add_argument("--city", help="only companies whose city contains this text")
    ap.add_argument("--json", action="store_true", help="print JSON")
    ap.add_argument("--list-all", action="store_true", help="list every company in the file")
    ap.add_argument("--convert", metavar="FILE.csv", help="convert a wide CSV to the JSON format and exit")
    ap.add_argument("--out", help="with --convert: output path (default: the CSV path with .json)")
    ap.add_argument("--source", help="with --convert: source label stored in metadata")
    ap.add_argument("--baseline", type=float, default=100.0, help="with --convert: baseline index (default 100)")
    ap.add_argument("--baseline-desc", help="with --convert: what the baseline means")
    return ap


def main(argv=None) -> int:
    _force_utf8_output()
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.convert and not args.company and not args.list_all:
        ap.error("give a company name, --list-all or --convert")
    try:
        return cmd_convert(args) if args.convert else cmd_lookup(args)
    except SalaryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
