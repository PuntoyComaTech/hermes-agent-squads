#!/usr/bin/env python3
"""Competencies the candidate has not declared yet: one de-duplicated candidate list from public evidence and documents.

  expand_candidates.py --project P [--evidence FILE] [--text FILE ...]

Inputs, all read-only:
  - achievements.yaml: declared skills, certifications and projects (public_evidence URLs count as projects).
  - --evidence FILE: the jobs-scout's reports/evidence-YYYY-MM-DD.json, {"sources": [{url, fetched, technologies,
    project_summary, title?}]}.
  - documents/**: text files (.txt .md .csv .json .yaml .yml) are read here; every other file is listed only.
  - --text FILE (repeatable): text the manager extracted from a PDF or a DOCX.

Rules (deterministic; the manager only judges the output):
  - A technology a source lists, or a vocabulary term a document names, is "stated".
  - A vocabulary term that only a project summary names is "inferred".
  - "Certificate: NAME" or "Certification: NAME" lines are certification candidates (stated).
  - A declared skill (same name after canonical naming), project (name or URL) or certification is skipped.
  - A source with fetched not true, or with neither technologies nor a project summary, is skipped as an empty stub.
  - Each candidate appears once. Each group is keyed by the first source that names the item.
  - Symbolic links under documents/ are listed and never followed.

Output: JSON on stdout. Exit 0 on success, 1 on unreadable input, 2 on usage errors. Writes nothing.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jobs_common as jc  # noqa: E402

SCHEMA = 1
LIMIT = 80
TEXT_SUFFIXES = (".txt", ".md", ".csv", ".json", ".yaml", ".yml")
MAX_TEXT_BYTES = 2_000_000
CERT_HINT = re.compile(r"cert|credential", re.I)
CERT_LINE = re.compile(r"^\s*(?:[-*]\s*)?(?:certificate|certification|certified)\s*[:\-]\s*(.+?)\s*$", re.I | re.M)
EMPTY_STUB = "empty stub: no technologies and no project summary"

# Canonical name, then the aliases that name it. Matched as whole words on lower-cased, ASCII-folded text.
VOCABULARY = (
    ("Python", ("python", "python3")),
    ("SQL", ("sql",)),
    ("pandas", ("pandas",)),
    ("NumPy", ("numpy",)),
    ("Excel", ("excel", "microsoft excel")),
    ("Power BI", ("power bi", "powerbi")),
    ("Tableau", ("tableau",)),
    ("scikit-learn", ("scikit-learn", "sklearn")),
    ("TensorFlow", ("tensorflow",)),
    ("PyTorch", ("pytorch",)),
    ("Docker", ("docker",)),
    ("Kubernetes", ("kubernetes",)),
    ("Git", ("git",)),
    ("AWS", ("aws", "amazon web services")),
    ("Azure", ("azure", "microsoft azure")),
    ("Google Cloud", ("gcp", "google cloud")),
    ("Apache Spark", ("spark", "pyspark", "apache spark")),
    ("Apache Airflow", ("airflow", "apache airflow")),
    ("dbt", ("dbt",)),
    ("PostgreSQL", ("postgresql", "postgres")),
    ("MySQL", ("mysql",)),
    ("MongoDB", ("mongodb",)),
    ("BigQuery", ("bigquery",)),
    ("Snowflake", ("snowflake",)),
    ("JavaScript", ("javascript",)),
    ("TypeScript", ("typescript",)),
    ("React", ("react",)),
    ("Java", ("java",)),
    ("Bash", ("bash",)),
    ("Linux", ("linux",)),
    ("ETL", ("etl", "extract transform load")),
    ("Machine learning", ("machine learning",)),
    ("Statistics", ("statistics", "statistical analysis")),
    ("Data visualization", ("data visualization",)),
    ("Jupyter", ("jupyter", "jupyter notebook")),
    ("Matplotlib", ("matplotlib",)),
    ("Streamlit", ("streamlit",)),
    ("Looker", ("looker",)),
)


def _pattern(alias: str):
    parts = [re.escape(p) for p in re.split(r"[\s\-]+", alias.lower()) if p]
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-]*".join(parts) + r"(?![a-z0-9])")


TERMS = tuple((name, tuple(_pattern(a) for a in (name,) + aliases)) for name, aliases in VOCABULARY)
ALIASES = {jc.slugify(a, LIMIT): name for name, aliases in VOCABULARY for a in (name,) + aliases}


class DataError(Exception):
    """An unreadable input; the reason goes to stderr and the exit code is 1."""


def as_list(value) -> list:
    return value if isinstance(value, list) else []


def canonical(name: str) -> str:
    clean = " ".join(str(name).split())
    return ALIASES.get(jc.slugify(clean, LIMIT), clean)


def slug(name: str) -> str:
    return jc.slugify(canonical(name), LIMIT)


def terms_in(text: str) -> list:
    folded = jc.ascii_fold(text).lower()
    return [name for name, patterns in TERMS if any(p.search(folded) for p in patterns)]


def url_key(url) -> str:
    text = re.sub(r"^https?://(www\.)?", "", str(url or "").strip().lower()).rstrip("/")
    return text[:-4] if text.endswith(".git") else text


def repo_name(url: str) -> str:
    return url.rstrip("/").rsplit("/", 1)[-1] or "project"


def declared(data: dict) -> dict:
    skills, certs, projects, urls = set(), set(), set(), set()
    for item in as_list(data.get("skills")):
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and slug(name):
            skills.add(slug(name))
    for item in as_list(data.get("certifications")):
        name = item.get("name") if isinstance(item, dict) else item
        if isinstance(name, str) and jc.slugify(name, LIMIT):
            certs.add(jc.slugify(name, LIMIT))
    for item in as_list(data.get("projects")):
        if isinstance(item, dict):
            if isinstance(item.get("name"), str):
                projects.add(jc.slugify(item["name"], LIMIT))
            urls.add(url_key(item.get("url")))
        elif isinstance(item, str):
            projects.add(jc.slugify(item, LIMIT))
    for item in as_list(data.get("public_evidence")):
        if isinstance(item, dict):
            urls.add(url_key(item.get("url")))
    urls.discard("")
    return {"skills": skills, "certifications": certs, "projects": projects, "urls": urls}


class Collector:
    """Gathers candidates; each key appears once, with every source that named it."""

    def __init__(self, known: dict):
        self.known = known
        self.skills, self.projects, self.certs = {}, {}, {}
        self._skipped = {}

    @staticmethod
    def _add(store: dict, key: str, entry: dict, source: str, tag: str) -> None:
        item = store.get(key)
        if item is None:
            store[key] = {**entry, "tag": tag, "sources": [source]}
            return
        if source not in item["sources"]:
            item["sources"].append(source)
        if tag == "stated":
            item["tag"] = "stated"

    def _skip(self, kind: str, name: str, source: str, reason: str) -> None:
        key = (kind, name.casefold(), reason)
        entry = self._skipped.get(key)
        if entry is None:
            self._skipped[key] = {"kind": kind, "name": name, "reason": reason, "sources": [source]}
        elif source not in entry["sources"]:
            entry["sources"].append(source)

    def skill(self, name: str, source: str, tag: str) -> None:
        name = canonical(name)
        key = jc.slugify(name, LIMIT)
        if not key:
            return
        if key in self.known["skills"]:
            self._skip("skill", name, source, "already declared in achievements.yaml")
            return
        self._add(self.skills, key, {"name": name}, source, tag)

    def certification(self, name: str, source: str, tag: str = "stated") -> None:
        key = jc.slugify(name, LIMIT)
        if not key:
            return
        if key in self.known["certifications"]:
            self._skip("certification", name, source, "already declared in achievements.yaml")
            return
        self._add(self.certs, key, {"name": name}, source, tag)

    def project(self, name: str, url: str, summary: str, source: str) -> None:
        key = jc.slugify(name, LIMIT)
        if key in self.known["projects"] or url_key(url) in self.known["urls"]:
            self._skip("project", name, source, "already declared in achievements.yaml")
            return
        self._add(self.projects, key, {"name": name, "url": url, "summary": summary}, source, "stated")

    def skip_source(self, source: str, reason: str) -> None:
        self._skipped.setdefault(("source", source, reason),
                                 {"kind": "source", "name": source, "reason": reason, "sources": [source]})

    def evidence(self, index: int, src) -> None:
        if not isinstance(src, dict):
            self.skip_source(f"sources[{index}]", "not an object")
            return
        url = str(src.get("url") or "").strip()
        source = url or f"sources[{index}]"
        if src.get("fetched") is not True:
            self.skip_source(source, "not fetched")
            return
        techs = [t.strip() for t in as_list(src.get("technologies")) if isinstance(t, str) and t.strip()]
        raw = src.get("project_summary")
        summary = raw.strip() if isinstance(raw, str) else ""
        if not techs and not summary:
            self.skip_source(source, EMPTY_STUB)
            return
        listed = {slug(t) for t in techs}
        for tech in techs:
            self.skill(tech, source, "stated")
        for name in terms_in(summary):
            if slug(name) not in listed:
                self.skill(name, source, "inferred")
        if summary:
            title = str(src.get("title") or "").strip() or repo_name(url)
            self.project(title, url, summary, source)

    def text(self, source: str, text: str) -> None:
        for name in terms_in(text):
            self.skill(name, source, "stated")
        for match in CERT_LINE.finditer(text):
            self.certification(match.group(1)[:120], source)

    def skipped(self) -> list:
        return sorted(self._skipped.values(), key=lambda e: (e["kind"], e["name"].casefold()))


def load_sources(path: str) -> list:
    try:
        data = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DataError(f"evidence {path}: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("sources"), list):
        raise DataError(f"evidence {path}: expected an object with a 'sources' list")
    return data["sources"]


def scan_documents(root: Path) -> tuple:
    """(listing, texts): every entry under documents/, and the text of each readable file as (path, text)."""
    docs = root / "documents"
    if docs.is_symlink():
        return [{"path": "documents", "kind": "link", "bytes": 0, "readable": False, "hint": None,
                 "note": "symbolic link: not followed"}], []
    if not docs.is_dir():
        return [], []
    listing, texts = [], []
    for rel, kind, size in jc.tree_entries(docs):
        if kind == "dir":
            continue
        path = f"documents/{rel}"
        name = rel.rsplit("/", 1)[-1]
        entry = {"path": path, "kind": kind, "bytes": size, "readable": False,
                 "hint": "certificate" if CERT_HINT.search(name) else None, "note": ""}
        if kind == "link":
            entry["note"] = "symbolic link: not followed"
        elif not name.lower().endswith(TEXT_SUFFIXES):
            entry["note"] = "not a text file: pass its extracted text with --text"
        elif size > MAX_TEXT_BYTES:
            entry["note"] = "text file over 2 MB: not read"
        else:
            entry["readable"] = True
            texts.append((path, (docs / rel).read_text(encoding="utf-8", errors="ignore")))
        listing.append(entry)
    return listing, texts


def read_extra(arg: str) -> tuple:
    path = Path(arg).expanduser()
    try:
        return f"text:{path.name}", path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise DataError(f"--text {path}: {exc}")


def expand(root: Path, evidence, text_args: list) -> dict:
    try:
        achievements = jc.read_data(root / "achievements.yaml")
    except ValueError as exc:
        raise DataError(f"achievements.yaml: {exc}")
    if not isinstance(achievements, dict):
        raise DataError("achievements.yaml: expected a mapping")
    collector = Collector(declared(achievements))
    sources = load_sources(evidence) if evidence else []
    for index, src in enumerate(sources):
        collector.evidence(index, src)
    listing, doc_texts = scan_documents(root)
    for entry in listing:
        if entry["hint"] == "certificate" and entry["kind"] == "file":
            stem = entry["path"].rsplit("/", 1)[-1].rsplit(".", 1)[0]
            name = " ".join(re.split(r"[\s_\-.]+", stem)).strip()
            name = re.sub(r"^certificate\s+", "", name, flags=re.I) or name
            collector.certification(name, entry["path"], tag="inferred")
    for path, text in doc_texts:
        collector.text(path, text)
    extra = [read_extra(arg) for arg in text_args]
    for name, text in extra:
        collector.text(name, text)
    return report(root, evidence, listing, collector, [name for name, _ in extra])


def clean(item: dict, keys: tuple) -> dict:
    return {k: item[k] for k in keys if k in item}


def report(root: Path, evidence, listing: list, collector: Collector, text_inputs: list) -> dict:
    skills = sorted(collector.skills.values(), key=lambda i: i["name"].casefold())
    projects = sorted(collector.projects.values(), key=lambda i: i["name"].casefold())
    certs = sorted(collector.certs.values(), key=lambda i: i["name"].casefold())
    groups, order = {}, []
    for kind, items in (("skill", skills), ("project", projects), ("certification", certs)):
        for item in items:
            first = item["sources"][0]
            if first not in groups:
                groups[first] = []
                order.append(first)
            groups[first].append({"kind": kind, "name": item["name"], "tag": item["tag"]})
    skipped = collector.skipped()
    return {
        "schema": SCHEMA,
        "project": str(root),
        "evidence": str(Path(evidence).expanduser()) if evidence else None,
        "text_inputs": text_inputs,
        "documents": listing,
        "candidates": {
            "skills": [clean(i, ("name", "tag", "sources")) for i in skills],
            "projects": [clean(i, ("name", "url", "summary", "tag", "sources")) for i in projects],
            "certifications": [clean(i, ("name", "tag", "sources")) for i in certs],
        },
        "groups": [{"source": s, "items": groups[s]} for s in order],
        "skipped": skipped,
        "counts": {"skills": len(skills), "projects": len(projects), "certifications": len(certs),
                   "skipped": len(skipped), "documents": len(listing)},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Merge public evidence and documents into a de-duplicated list of "
                                                 "undeclared skills, projects and certifications (JSON).")
    parser.add_argument("--project", required=True, help="the project folder (holds profile.md)")
    parser.add_argument("--evidence", help="the scout's reports/evidence-YYYY-MM-DD.json")
    parser.add_argument("--text", action="append", default=[],
                        help="a text file the manager extracted from a PDF or DOCX (repeatable)")
    args = parser.parse_args(argv)
    try:
        root = jc.project_dir(args.project)
        result = expand(root, args.evidence, args.text)
    except DataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
