"""jobs_common: the built-in YAML subset reader must agree with PyYAML on every shape the squad writes."""
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
PATH = REPO / "squads" / "jobs" / "skills" / "jobs-contract" / "scripts" / "jobs_common.py"
spec = importlib.util.spec_from_file_location("jobs_common", PATH)
jc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(jc)

PROFILE = """\
updated: 2026-09-25
search: active                      # active | paused
occupation: "Data analyst, business reporting and automation"
target_roles: ["Data analyst", "BI analyst"]
years_experience: {total: 4, in_role: 3}
search_keywords: {en: ["data analyst", "BI analyst"], es: ["analista de datos"]}
max_required_language: {english: B2}
min_salary: {amount: 6000, currency: PEN, period: month, type: gross}
avoid_sectors: []
candidate:
  stage: mid
  age: null
  include_age_in_cv: false
market:
  country: PE
  conventions: {photo: false, age: false}
eligibility:
  - {country: PE, status: citizen}
  - country: US
    status: needs_sponsorship
    notes: "needs a visa"
scoring:
  weights: {technical: 30, experience: 25, behavioral: 15, career: 30}
deal_breakers:
  - on-call weekends
  - "relocation: required"
writing_style: {tone: "warm_direct", avoid_phrases: []}
salary_data: null
nested:
  list_of_maps:
    - id: A1
      tags: [x, y]
      more:
        deep: 1.5
    - id: A2
      tags: []
"""


def same(a, b):
    # PyYAML turns ISO dates into date objects; the subset reader keeps them as strings on purpose
    return json.loads(json.dumps(a, default=str)) == json.loads(json.dumps(b, default=str))


def test_mini_yaml_matches_pyyaml_on_a_full_profile():
    assert same(jc.mini_yaml(PROFILE), yaml.safe_load(PROFILE))


@pytest.mark.parametrize("text", [
    "a: 1\nb: [1, 2, {c: d}]\n",
    "k: 'it''s'\nj: \"a: b # not a comment\"\n",
    "- 1\n- two\n- {a: 1}\n",
    "x:\n  - a\n  - b\ny: true\nz: ~\n",
    "url: https://example.com/a?b=c#frag\n",
    "when: 2026-09-25\nrate: 0.5\nneg: -3\n",
])
def test_mini_yaml_small_shapes(text):
    assert same(jc.mini_yaml(text), yaml.safe_load(text))


@pytest.mark.parametrize("text", ["a: &x 1\n", "a: |\n  text\n", "a: !!str 1\n"])
def test_unsupported_constructs_raise(text):
    with pytest.raises(jc.YamlError):
        jc.mini_yaml(text)


def test_front_matter_split_and_body():
    meta, body = jc.split_front_matter("---\nsearch: paused\ncities: [Lima]\n---\nNotes here\n")
    assert meta == {"search": "paused", "cities": ["Lima"]} and body == "Notes here\n"


def test_front_matter_missing_or_broken_never_raises():
    assert jc.split_front_matter("no front matter")[0] == {}
    meta, body = jc.split_front_matter("---\na: [unclosed\n---\nbody")
    assert meta == {} and body == "body"
    with pytest.raises(jc.YamlError):
        jc.mini_yaml("a: [unclosed\n")


def test_read_front_matter_missing_file(tmp_path):
    assert jc.read_front_matter(tmp_path / "nope.md") == {}


def test_atomic_write_replaces_without_leftovers(tmp_path):
    target = tmp_path / "sub" / "f.json"
    jc.write_json(target, {"a": 1})
    jc.write_json(target, {"a": 2})
    assert json.loads(target.read_text()) == {"a": 2}
    assert [p.name for p in target.parent.iterdir()] == ["f.json"]


def test_slugify_and_cefr():
    assert jc.slugify("Peña & Hijos, S.A. — Analista") == "pena-hijos-s-a-analista"
    assert jc.cefr_index("b2") == 3 and jc.cefr_index("fluent") is None


def test_project_dir_requires_profile(tmp_path):
    with pytest.raises(SystemExit):
        jc.project_dir(str(tmp_path))
    (tmp_path / "profile.md").write_text("---\n---\n")
    assert jc.project_dir(str(tmp_path)) == tmp_path.resolve()


def test_cli_prints_json(tmp_path, capsys):
    f = tmp_path / "p.md"
    f.write_text("---\nsearch: active\n---\nx\n")
    assert jc.main([str(f)]) == 0
    assert json.loads(capsys.readouterr().out) == {"search": "active"}
