#!/usr/bin/env python3
"""The value to enter in a salary or notice-period form field, from application-data.yaml: never a question mid-submit.

  form_answer.py salary --project P [--range "MIN-MAX CUR"] [--period month|year|hour|week|day]
                        [--currency CUR] [--json]
  form_answer.py notice --project P [--options "Immediately|10 days|20 days|1 month"] [--json]

application-data.yaml holds the user's answers once (profiling-candidates asks for them at onboarding):

  salary_answer: {amount: 4500, currency: USD, period: month}   # what to type when the posting gives no range;
                                                                 # a list of rows gives the user's own figure per period
  notice_period_days: 7                                          # days from offer to start; default: start_availability

salary: with --range (the posting's own range) the answer is its midpoint, never below the floor in
`salary_expectation` for that currency; without a range it is `salary_answer`. The amount is converted to the period
the form asks (--period: 12 months a year, 52 weeks, 260 working days, 2080 working hours). A currency the stored
answer does not use and no floor covers is refused: the applier blocks with that one question.
notice: --options lists the form's choices as shown. The answer is the shortest option of at least
`notice_period_days` (an "Immediately" option counts as 0 days); when none is that long, the longest offered. Without
--options it prints the days as text ("7 days").

Exit 0 an answer, 1 the stored data cannot answer (the reason names the key to add), 2 usage error.
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

PER_YEAR = {"year": 1, "month": 12, "week": 52, "day": 260, "hour": 2080}
PERIOD_ALIASES = {"yearly": "year", "annual": "year", "annually": "year", "monthly": "month", "weekly": "week",
                  "daily": "day", "hourly": "hour", "mes": "month", "mensual": "month", "año": "year",
                  "anual": "year", "hora": "hour", "semana": "week", "dia": "day", "día": "day"}
UNIT_DAYS = {"day": 1, "días": 1, "dias": 1, "día": 1, "dia": 1, "week": 7, "semana": 7, "semanas": 7,
             "month": 30, "mes": 30, "meses": 30}
IMMEDIATE = re.compile(r"immediate|inmediat|right away|asap|de inmediato", re.I)


class NoAnswer(Exception):
    """application-data.yaml cannot answer this field: the reason names the key to add."""


def period_of(text: str) -> str:
    key = str(text or "").strip().lower().rstrip("s")
    key = PERIOD_ALIASES.get(key, key)
    if key not in PER_YEAR:
        raise ValueError(f"unknown period {text!r}: use year, month, week, day or hour")
    return key


def convert(amount: float, src: str, dst: str) -> float:
    return amount * PER_YEAR[src] / PER_YEAR[dst]


def load(project: Path) -> dict:
    path = project / "application-data.yaml"
    if not path.is_file():
        raise NoAnswer(f"{path} is missing")
    data = jc.load_yaml(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def parse_range(text: str):
    """"3000-4000 USD", "USD 3,000 - 4,000" -> (3000.0, 4000.0, 'USD')."""
    cur = re.search(r"\b([A-Z]{3})\b", text or "")
    nums = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text or "")]
    if len(nums) < 2 or not cur:
        raise ValueError(f"--range needs two amounts and a currency code, got {text!r}")
    return min(nums[:2]), max(nums[:2]), cur.group(1)


def floor_for(data: dict, currency: str, period: str):
    for row in data.get("salary_expectation") or []:
        if isinstance(row, dict) and str(row.get("currency") or "").upper() == currency and row.get("amount"):
            return convert(float(row["amount"]), period_of(row.get("period") or "month"), period)
    return None


def salary(data: dict, period: str, currency: str = "", posted: str = "") -> dict:
    if posted:
        low, high, cur = parse_range(posted)
        amount, why = (low + high) / 2, "the posting's range midpoint"
        floor = floor_for(data, cur, period)
        if floor is not None and amount < floor:
            amount, why = floor, "the user's floor (the posting's midpoint is below it)"
        return {"amount": round(amount), "currency": cur, "period": period, "why": why}
    stored = data.get("salary_answer")
    rows = [r for r in (stored if isinstance(stored, list) else [stored]) if isinstance(r, dict)]
    # The user may give the figure per period himself ("4,500 a month, 28 an hour"): his own figure wins over a
    # conversion, so the row for the asked period (and currency) is used as it is.
    exact = [r for r in rows if str(r.get("period") or "month").lower() == period and r.get("amount")
             and (not currency or str(r.get("currency") or "").upper() == currency.upper())]
    stored = exact[0] if exact else (rows[0] if rows else None)
    if not isinstance(stored, dict) or not stored.get("amount") or not stored.get("currency"):
        raise NoAnswer("application-data.yaml has no salary_answer {amount, currency, period}: the salary to type "
                       "when a posting gives no range. Ask the user once and save it there")
    cur = str(stored["currency"]).upper()
    if currency and currency.upper() != cur:
        floor = floor_for(data, currency.upper(), period)
        if floor is None:
            raise NoAnswer(f"the form asks {currency.upper()} and salary_answer is in {cur}, with no "
                           f"salary_expectation floor in {currency.upper()}")
        return {"amount": round(floor), "currency": currency.upper(), "period": period,
                "why": f"the user's {currency.upper()} floor (salary_answer is in {cur})"}
    amount = convert(float(stored["amount"]), period_of(stored.get("period") or "month"), period)
    return {"amount": round(amount), "currency": cur, "period": period, "why": "salary_answer (no posted range)"}


def option_days(option: str):
    if IMMEDIATE.search(option):
        return 0
    match = re.search(r"(\d+)\s*([A-Za-zíá]+)", option)
    if not match:
        return None
    unit = match.group(2).lower().rstrip("s") if match.group(2).lower() not in UNIT_DAYS else match.group(2).lower()
    for name, days in UNIT_DAYS.items():
        if unit.startswith(name.rstrip("s")):
            return int(match.group(1)) * days
    return None


def notice(data: dict, options: list) -> dict:
    days = data.get("notice_period_days")
    if days is None and isinstance(data.get("start_availability"), str):
        days = option_days(data["start_availability"])  # "1 week", "2 weeks", "immediately"
    if isinstance(days, bool) or not isinstance(days, int) or days < 0:
        raise NoAnswer("application-data.yaml has no notice_period_days and its start_availability does not read as "
                       "a duration (\"1 week\"): ask the user once and save it")
    if not options:
        return {"answer": f"{days} days", "days": days, "why": "notice_period_days"}
    known = [(option_days(o), o) for o in options]
    known = [(d, o) for d, o in known if d is not None]
    if not known:
        raise NoAnswer(f"none of the options reads as a duration: {options}")
    at_least = sorted((d, o) for d, o in known if d >= days)
    pick = at_least[0] if at_least else max(known)
    why = (f"the shortest option of at least {days} days" if at_least
           else f"no option reaches {days} days: the longest offered")
    return {"answer": pick[1], "days": pick[0], "why": why}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="The salary or notice-period answer, from application-data.yaml.")
    p.add_argument("field", choices=("salary", "notice"))
    p.add_argument("--project", required=True, help="the project folder that holds application-data.yaml")
    p.add_argument("--range", default="", help="salary: the posting's own range, e.g. '3000-4000 USD'")
    p.add_argument("--period", default="month", help="salary: the period the form asks (year, month, week, day, hour)")
    p.add_argument("--currency", default="", help="salary: the currency the form asks, when it fixes one")
    p.add_argument("--options", default="", help="notice: the form's choices, separated by |")
    p.add_argument("--json", action="store_true", help="print JSON")
    args = p.parse_args(argv)
    try:
        data = load(Path(args.project).expanduser())
        if args.field == "salary":
            out = salary(data, period_of(args.period), args.currency, args.range)
        else:
            out = notice(data, [o.strip() for o in args.options.split("|") if o.strip()])
    except NoAnswer as exc:
        print(f"form_answer: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"form_answer: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    elif args.field == "salary":
        print(f"{out['amount']} {out['currency']} per {out['period']} ({out['why']})")
    else:
        print(f"{out['answer']} ({out['why']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
