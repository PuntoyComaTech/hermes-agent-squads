"""merge3: the three-way merge that keeps local skill edits across updates."""
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import merge3  # noqa: E402

BASE = "a\nb\nc\nd\ne\nf\ng\n"


def test_one_side_changed_takes_that_side():
    assert merge3.merge(BASE, BASE, "a\nX\nc\nd\ne\nf\ng\n") == ("a\nX\nc\nd\ne\nf\ng\n", True)
    assert merge3.merge(BASE, "a\nX\nc\nd\ne\nf\ng\n", BASE) == ("a\nX\nc\nd\ne\nf\ng\n", True)


def test_separate_changes_are_combined():
    ours = BASE + "LEARNED\n"
    theirs = "UPSTREAM\n" + BASE[2:]
    assert merge3.merge(BASE, ours, theirs) == ("UPSTREAM\nb\nc\nd\ne\nf\ng\nLEARNED\n", True)


def test_the_same_change_on_both_sides_lands_once():
    both = "a\nb\nNEW\nc\nd\ne\nf\ng\n"
    assert merge3.merge(BASE, both, both) == (both, True)
    theirs = "a\nb\nNEW\nc\nd\ne\nf\nTAIL\n"
    assert merge3.merge(BASE, both, theirs) == (theirs, True)


def test_overlapping_or_adjacent_changes_conflict_and_return_theirs():
    theirs = "a\nY\nc\nd\ne\nf\ng\n"
    assert merge3.merge(BASE, "a\nX\nc\nd\ne\nf\ng\n", theirs) == (theirs, False)
    assert merge3.merge(BASE, "a\nb\nX\nd\ne\nf\ng\n", "a\nY\nc\nd\ne\nf\ng\n")[1] is False  # touching lines


def test_trees_keep_local_only_files_and_flag_add_delete_clashes(tmp_path):
    def tree(name, files):
        root = tmp_path / name
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text)
        return root
    base = tree("base", {"SKILL.md": BASE, "references/a.md": "ref\n"})
    ours = tree("ours", {"SKILL.md": BASE + "LEARNED\n", "references/a.md": "ref edited\n", "notes.md": "mine\n"})
    theirs = tree("theirs", {"SKILL.md": "UP\n" + BASE[2:], "references/b.md": "new\n"})
    files, conflicts = merge3.merge_trees(base, ours, theirs)
    assert files["SKILL.md"] == b"UP\nb\nc\nd\ne\nf\ng\nLEARNED\n"
    assert files["notes.md"] == b"mine\n" and files["references/b.md"] == b"new\n"
    assert conflicts == ["references/a.md"]  # edited here, deleted upstream


def test_cli_exit_codes(tmp_path):
    for name, text in {"b": BASE, "o": "a\nX\nc\nd\ne\nf\ng\n", "t": "a\nY\nc\nd\ne\nf\ng\n", "c": BASE + "z\n"}.items():
        (tmp_path / name).write_text(text)
    run = lambda *f: subprocess.run([sys.executable, str(REPO / "scripts" / "merge3.py"), *[str(tmp_path / x) for x in f]],
                                    capture_output=True, text=True)
    assert run("b", "o", "c").returncode == 0
    assert run("b", "o", "t").returncode == 1
    assert run("b", "o", "missing").returncode == 2
