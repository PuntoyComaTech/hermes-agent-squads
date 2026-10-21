"""check_site.py against a local build: the repo it scans follows site.yaml -> repo.path."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "squads" / "web" / "skills" / "site-contract" / "scripts" / "check_site.py"
LEAK = "sk_live_" + "a1B2c3D4e5F6g7H8i9J0k1L2"


def site(tmp: Path, repo_path: str | None) -> tuple[Path, Path]:
    """A site folder with a built `dist/` and a source file that leaks a secret, inside `<root>/<repo_path>`."""
    root = tmp / "My sites" / "acme"
    repo = root if repo_path == "." else root / (repo_path or "repo")
    (repo / "dist").mkdir(parents=True)
    (repo / "dist" / "index.html").write_text("<html lang=en><head><title>Acme</title>"
                                             "<meta name=description content=x></head><body>hi</body></html>")
    (repo / "src").mkdir()
    (repo / "src" / "pay.ts").write_text(f'const key = "{LEAK}";\n')
    lines = ["name: Acme", "slug: acme", "type: static"]
    if repo_path is not None:
        lines += ["repo:", f"  path: {repo_path}"]
    (root / "site.yaml").write_text("\n".join(lines) + "\n")
    return root, repo


def check(root: Path, repo: Path, *extra: str) -> dict:
    p = subprocess.run([sys.executable, "-I", str(SCRIPT), "--site", "acme", "--id", "acme-20261021-build-01",
                        "--dir", str(repo / "dist"), "--root", str(root), "--json", *extra],
                       capture_output=True, text=True, timeout=120, cwd=root)
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout)


def repo_secrets(result: dict) -> dict:
    (row,) = [c for c in result["checks"] if c["name"] == "repo-secrets"]
    return row


def test_a_project_folder_that_is_the_repo_gets_its_secret_scan(tmp_path):
    """An existing repo opened as the project (repo.path: .) has no repo/ subfolder: the scan must still find a leak."""
    root, repo = site(tmp_path, ".")
    result = check(root, repo, "--repo", str(repo))
    assert repo_secrets(result)["ok"] is False and "pay.ts" in repo_secrets(result)["detail"]
    assert (root / "reviews" / "acme-20261021-build-01-r0" / "checks.json").is_file()


def test_the_repo_defaults_to_site_yaml_repo_path(tmp_path):
    root, repo = site(tmp_path, ".")
    p = subprocess.run([sys.executable, "-I", "-c",
                        "import argparse, importlib.util, sys; s = importlib.util.spec_from_file_location('c', sys.argv[1]);"
                        " m = importlib.util.module_from_spec(s); s.loader.exec_module(m);"
                        " a = argparse.Namespace(root=sys.argv[2], repo=None, url='', thresholds_json=None);"
                        " print(m.Checker(a).repo)", str(SCRIPT), str(root)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert Path(p.stdout.strip()) == root.resolve()


def test_a_new_site_keeps_the_repo_subfolder(tmp_path):
    root, repo = site(tmp_path, None)
    p = subprocess.run([sys.executable, "-I", "-c",
                        "import argparse, importlib.util, sys; s = importlib.util.spec_from_file_location('c', sys.argv[1]);"
                        " m = importlib.util.module_from_spec(s); s.loader.exec_module(m);"
                        " a = argparse.Namespace(root=sys.argv[2], repo=None, url='', thresholds_json=None);"
                        " print(m.Checker(a).repo)", str(SCRIPT), str(root)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert Path(p.stdout.strip()) == (root / "repo").resolve() == repo.resolve()
