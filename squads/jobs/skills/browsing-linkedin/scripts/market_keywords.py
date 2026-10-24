#!/usr/bin/env python3
"""Counts what the market asks for in a set of posting texts and marks which terms the user can truthfully claim.

Input is what the scout already holds: portal `detail` output, saved `opening.md` text, or plain text files. The
output is `reports/market-YYYY-MM-DD.json`, read by jobs-writer (profile optimisation) and the manager.

Usage:
  market_keywords.py --input FILE [--input FILE ...] [--project P] [--leads FILE] [--min-docs 2] [--top 40]
                     [--country CC] [--window TEXT] [--date YYYY-MM-DD] [--output FILE]

An input is a .json file (an object with `description`, a list of such objects, or a portal output with `results`)
or any text file (one posting). A term counts once per posting. With --project, each term is checked against
`profile.md` (key_skills, search_keywords, target_roles) and `achievements.yaml` (skills, tags, achievement text,
education, certifications): `in_profile: true` means the user may write it; false means it is a gap, never a claim. A longer term the profile holds
only in part carries `profile_part` (the part that may be written).
`role_families` groups the posting titles by the work they name (jobs-contract role_families.json): each family says
how many postings used it, whether the candidate is recognised in it (`recognised`: named in profile.md, or enough of
its signals in their own evidence), whether it is `emerging`, and the titles seen. `offer` lists the recognised
families the profile does not name yet: the manager asks the user once whether to position under them.
Exit 0 on success, 1 when fewer than 3 postings were readable (a market read from two postings is anecdote: the
warning goes to stdout and no `--output` file is written, so the writer has no market file to read), 2 on a usage
error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
MIN_POSTINGS = 3

STOP = frozenset("""
a an and or the of to in on for with at by from as is are be been being this that these those it its we you your our
their they he she will can may must should would could have has had do does did not no yes if then than so such
also all any more most other some into over under about across per via within without up out new
el la los las un una unos unas y o de del en con por para a al que se su sus es son ser como mas más pero sin sobre
entre ya muy nuestro nuestra nuestros nuestras tu tus lo le les este esta estos estas ese esa
o os as um uma uns umas e de do da dos das em no na nos nas com por para que se seu sua seus suas é são ser como mais
mas sem sobre entre já muito nosso nossa
""".split())
GENERIC = frozenset("""
experience experiences work working team teams years year ability skills skill strong knowledge company role job
position candidate candidates responsibilities requirements including include etc good excellent great
looking join opportunity benefits salary employment equal employer apply application required preferred plus
degree bachelor related field environment business using use used ensure support high level well
experiencia trabajo equipo años año habilidades conocimiento empresa puesto cargo candidato requisitos
responsabilidades ofrecemos buscamos oferta beneficios salario nivel
experiência trabalho equipe anos ano habilidades conhecimento empresa vaga cargo candidato requisitos
responsabilidades oferecemos buscamos benefícios
""".split())
TOKEN = re.compile(r"[^\W_](?:[\w+#.\-]*[\w+#])?", re.U)
SKIP_KEYS = frozenset({"id", "verified", "source", "evidence", "experience", "url", "proficiency", "from", "to",
                       "year", "years", "achievements", "metric"})


class UsageError(ValueError):
    pass


def jc_module():
    sibling = str(HERE.parents[1] / "jobs-contract" / "scripts")
    if sibling not in sys.path:
        sys.path.insert(0, sibling)
    import jobs_common  # noqa: E402 - the sibling path is added just above
    return jobs_common


def fold(text: str) -> str:
    return jc_module().ascii_fold(str(text or "")).lower()


def runs(text: str) -> list[list[str]]:
    """Runs of consecutive significant tokens: a stop word or punctuation ends a run."""
    out, current = [], []
    for part in re.split(r"[.;:!?]+(?=\s|$)|[\n()\[\]{}•·|/\\\"“”,]+", str(text or "").lower()):
        for match in TOKEN.finditer(part):
            token = match.group(0).strip(".-")
            if not token or token in STOP or token.isdigit() or len(token) < 2 and token not in ("r", "c"):
                if current:
                    out.append(current)
                    current = []
                continue
            current.append(token)
        if current:
            out.append(current)
            current = []
    return out


def terms_of(text: str) -> set[str]:
    found = set()
    for run in runs(text):
        for n in (1, 2, 3):
            for i in range(len(run) - n + 1):
                gram = run[i:i + n]
                if n == 1 and gram[0] in GENERIC:
                    continue
                if all(t in GENERIC for t in gram):
                    continue
                if gram[0] in GENERIC or gram[-1] in GENERIC:
                    continue
                found.add(" ".join(gram))
    return found


def read_postings(paths) -> list[dict]:
    postings = []
    for path in paths:
        p = Path(path)
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError as exc:
            raise UsageError(f"cannot read {path}: {exc}") from exc
        if p.suffix.lower() == ".json":
            try:
                data = json.loads(raw)
            except ValueError as exc:
                raise UsageError(f"{path} is not JSON: {exc}") from exc
            items = data.get("results") if isinstance(data, dict) and "results" in data else data
            items = items if isinstance(items, list) else [items]
            for item in items:
                if isinstance(item, dict) and str(item.get("description") or "").strip():
                    postings.append({"title": str(item.get("title") or "").strip(), "text": str(item["description"]),
                                     "source": str(item.get("url") or path)})
        else:
            postings.append({"title": "", "text": raw, "source": str(path)})
    return postings


def profile_corpus(project: Path) -> str:
    jc = jc_module()
    chunks = []
    try:
        meta = jc.read_front_matter(project / "profile.md")
    except Exception:  # noqa: BLE001 - a missing or damaged profile means every term is a gap, which is safe
        meta = {}
    for key in ("key_skills", "search_keywords", "target_roles", "acceptable_roles", "occupation"):
        chunks.append(json.dumps(meta.get(key), ensure_ascii=False))
    try:
        data = jc.read_data(project / "achievements.yaml")
    except Exception:  # noqa: BLE001
        data = {}

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k not in SKIP_KEYS:
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            chunks.append(node)
    walk(data)
    return fold(" ".join(chunks))


def in_profile(term: str, corpus: str) -> bool:
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(fold(term))}(?![a-z0-9])", corpus))


def profile_part(term: str, corpus: str):
    """The longest contiguous part of a longer term that the profile holds, else None: 'power bi' for 'power bi dashboards'."""
    words = term.split()
    for size in range(len(words) - 1, 0, -1):
        for i in range(len(words) - size + 1):
            part = " ".join(words[i:i + size])
            if part not in GENERIC and in_profile(part, corpus):
                return part
    return None


def analyse(postings, min_docs, top, corpus=None) -> dict:
    total = len(postings)
    docs = Counter()
    for posting in postings:
        docs.update(terms_of(posting["text"] + "\n" + posting["title"]))
    kept = {t: n for t, n in docs.items() if n >= min_docs}
    for term in list(kept):  # a shorter term inside a longer one with the same count says nothing new
        if any(term != other and f" {term} " in f" {other} " and kept[other] >= kept[term] for other in kept):
            del kept[term]
    ranked = sorted(kept.items(), key=lambda kv: (-kv[1], -len(kv[0].split()), kv[0]))[:top]
    terms = []
    for term, n in ranked:
        row = {"term": term, "postings": n, "share": round(n / total, 2)}
        if corpus is not None:
            row["in_profile"] = in_profile(term, corpus)
            if not row["in_profile"] and " " in term:
                row["profile_part"] = profile_part(term, corpus)
        terms.append(row)
    titles = Counter(re.sub(r"\s+", " ", p["title"]).strip().lower() for p in postings if p["title"])
    return {"postings_read": total, "terms": terms,
            "titles": [{"title": t, "count": c} for t, c in titles.most_common(15)]}


def title_families(postings, meta, evidence) -> tuple[list, list]:
    jc = jc_module()
    recognised = {r["id"]: r for r in jc.recognised_roles(meta, evidence)}
    seen = {}
    for p in postings:
        fam = jc.family_of(p["title"])
        if fam:
            row = seen.setdefault(fam["id"], {"id": fam["id"], "label": fam["label"], "emerging": bool(fam.get("emerging")),
                                              "postings": 0, "titles": []})
            row["postings"] += 1
            t = re.sub(r"\s+", " ", p["title"]).strip()
            if t not in row["titles"]:
                row["titles"].append(t)
    for fam in jc.role_families():
        if fam["id"] in recognised and fam["id"] not in seen:
            seen[fam["id"]] = {"id": fam["id"], "label": fam["label"], "emerging": bool(fam.get("emerging")),
                               "postings": 0, "titles": []}
    rows = []
    for fid, row in seen.items():
        rec = recognised.get(fid)
        row["recognised"] = rec is not None
        row["by"] = rec["by"] if rec else None
        row["signals"] = rec["signals"] if rec else []
        rows.append(row)
    rows.sort(key=lambda r: (-r["postings"], r["label"]))
    offer = [r["label"] for r in rows if r["recognised"] and r["by"] == "evidence"]
    return rows, offer


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input", action="append", required=True)
    p.add_argument("--project")
    p.add_argument("--leads")
    p.add_argument("--min-docs", type=int, default=2)
    p.add_argument("--top", type=int, default=40)
    p.add_argument("--country")
    p.add_argument("--window")
    p.add_argument("--date")
    p.add_argument("--output")
    ns = p.parse_args(argv)
    try:
        if ns.min_docs < 1 or not 1 <= ns.top <= 200:
            raise UsageError("--min-docs is at least 1 and --top is between 1 and 200")
        postings = read_postings(ns.input)
        corpus = profile_corpus(Path(ns.project)) if ns.project else None
        out = {"date": ns.date or dt.date.today().isoformat(), "country": ns.country, "window": ns.window,
               "profile_checked": corpus is not None, **analyse(postings, ns.min_docs, ns.top, corpus)}
        if ns.project:
            try:
                meta = jc_module().read_front_matter(Path(ns.project) / "profile.md")
            except Exception:  # noqa: BLE001
                meta = {}
            try:
                evidence = json.dumps(jc_module().read_data(Path(ns.project) / "achievements.yaml"), ensure_ascii=False)
            except Exception:  # noqa: BLE001
                evidence = ""
            evidence += " " + json.dumps(meta, ensure_ascii=False)
            out["role_families"], out["offer_positioning"] = title_families(postings, meta, evidence)
        if ns.leads:
            try:
                leads = json.loads(Path(ns.leads).read_text(encoding="utf-8")).get("leads", [])
            except (OSError, ValueError, AttributeError) as exc:
                raise UsageError(f"cannot read leads from {ns.leads}: {exc}") from exc
            out["leads"] = leads
    except UsageError as exc:
        sys.stderr.write(json.dumps({"error": str(exc), "code": "BAD_ARG"}) + "\n")
        return 2
    if len(postings) < MIN_POSTINGS:
        out["warning"] = f"only {len(postings)} postings readable: too few to call this a market read"
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if ns.output and len(postings) >= MIN_POSTINGS:
        Path(ns.output).parent.mkdir(parents=True, exist_ok=True)
        Path(ns.output).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if len(postings) >= MIN_POSTINGS else 1


if __name__ == "__main__":
    sys.exit(main())
