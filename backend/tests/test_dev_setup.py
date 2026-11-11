"""The Docker-free two-terminal setup: Makefile, setup script, smoke script. Ports/URLs come from the environment; nothing is hardcoded."""
import importlib.util, os, pathlib, re, shutil, subprocess, tempfile
import pytest
from conftest import BACKEND, ROOT

MAKE = shutil.which("make")
needs_make = pytest.mark.skipif(not MAKE, reason="make not installed")
TARGETS = ["setup", "test", "audit", "baseline", "serve", "web", "smoke"]
spec = importlib.util.spec_from_file_location("smoke", BACKEND / "scripts" / "smoke.py")
smoke = importlib.util.module_from_spec(spec); spec.loader.exec_module(smoke)


def make(*args, cwd=ROOT, env=None):
    return subprocess.run([MAKE, *args], cwd=cwd, capture_output=True, text=True, env={**os.environ, **(env or {})})


@pytest.fixture()
def target_repo(tmp_path):
    (tmp_path / ".cdi").mkdir()
    (tmp_path / ".cdi/config.yml").write_text("version: 1\n")
    return tmp_path


@needs_make
@pytest.mark.parametrize("target", TARGETS + ["pr", "web-preview", "e2e", "test-backend", "test-web", "help"])
def test_every_documented_target_exists_and_never_mentions_docker(target, target_repo):
    r = make("-n", target, f"CDI_TARGET={target_repo}", "PR=x")
    assert r.returncode == 0, r.stderr
    assert "docker" not in r.stdout.lower()


@needs_make
def test_help_lists_the_targets():
    out = make("help").stdout
    for t in TARGETS:
        assert f"make {t}" in out


@needs_make
def test_ports_and_urls_are_taken_from_variables_with_documented_defaults(target_repo):
    d = make("-n", "serve", f"CDI_TARGET={target_repo}").stdout
    assert "--port 8000" in d and "--host 127.0.0.1" in d and "--cors-origin http://127.0.0.1:5173" in d
    o = make("-n", "serve", f"CDI_TARGET={target_repo}", "CDI_API_PORT=9123", "CDI_WEB_PORT=6001", "CDI_WEB_HOST=127.0.0.1").stdout
    assert "--port 9123" in o and "--cors-origin http://127.0.0.1:6001" in o and "8000" not in o
    w = make("-n", "web", "CDI_API_PORT=9123", "CDI_API_HOST=127.0.0.1").stdout
    assert "CDI_API_BASE_URL=http://127.0.0.1:9123" in w


def test_no_port_or_url_literal_outside_a_documented_default():
    text = (ROOT / "Makefile").read_text()
    for n, line in enumerate(text.splitlines(), 1):
        if re.search(r"\b(8000|5173|4173|localhost)\b|https?://\d", line):
            assert "?=" in line, f"Makefile:{n} hardcodes a port or URL outside a `?=` default: {line}"
    assert "*" not in "".join(l for l in text.splitlines() if "cors" in l.lower() and not l.lstrip().startswith("#")), "no wildcard origin"


@needs_make
def test_baseline_and_pr_targets_explain_what_is_missing(tmp_path):
    r = make("baseline", f"CDI_TARGET={tmp_path}")
    assert r.returncode == 2 and ".cdi/config.yml" in (r.stdout + r.stderr)
    r = make("pr", f"CDI_TARGET={tmp_path}")
    assert r.returncode == 2 and "PR=" in (r.stdout + r.stderr)
    r = make("serve", f"CDI_TARGET={tmp_path}")
    assert r.returncode == 2 and ".cdi/config.yml" in (r.stdout + r.stderr)


def test_setup_script_does_what_the_readme_says():
    s = (BACKEND / "scripts/setup.sh").read_text()
    assert subprocess.run(["bash", "-n", str(BACKEND / "scripts/setup.sh")]).returncode == 0
    for needle in ("-m venv", "pip install --quiet --disable-pip-version-check -e backend", "requirements.txt", "dotnet build", "npm ci", "scanners/ts-morph", "(cd frontend"):
        assert needle in s or needle.replace("--quiet --disable-pip-version-check ", "") in s, needle
    assert "docker" not in s.lower()
    assert os.access(BACKEND / "scripts/setup.sh", os.X_OK)


def test_setup_script_fails_clearly_without_its_prerequisites(tmp_path):
    r = subprocess.run(["bash", str(BACKEND / "scripts/setup.sh")], capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "PYTHON": "definitely-not-python"}, cwd=tmp_path)
    assert r.returncode == 1 and "definitely-not-python" in r.stderr and "Python" in r.stderr


def test_prerequisite_versions_in_the_docs_match_the_project_files():
    readme = (ROOT / "README.md").read_text().replace("*", "")
    import tomllib
    py = tomllib.loads((BACKEND / "pyproject.toml").read_text())["project"]["requires-python"]
    assert py == ">=3.10" and "3.10 or newer" in readme
    assert "22.12 or newer" in readme and ".NET 10" in readme and "git" in readme.lower()
    assert "net10.0" in (BACKEND / "scanners/dotnet-roslyn/CsScanner.csproj").read_text()
    eng = __import__("json").loads((ROOT / "frontend/node_modules/vitest/package.json").read_text())["engines"]["node"] if (ROOT / "frontend/node_modules/vitest").is_dir() else "^22.12.0"
    assert "22.12" in eng


def test_dockerfile_is_kept_but_documented_as_optional_and_unused():
    assert (BACKEND / "Dockerfile").is_file()
    readme = (ROOT / "README.md").read_text()
    assert re.search(r"Dockerfile[^\n]*(optional|unused)", readme, re.I) or re.search(r"(optional|unused)[^\n]*Dockerfile", readme, re.I)
    assert not [p for p in ROOT.rglob("docker-compose*.y*ml") if "node_modules" not in p.parts and ".venv" not in p.parts]


# ---------------------------------------------------------------- smoke script helpers
def test_free_ports_are_free_and_distinct_enough():
    a, b = smoke.free_port(), smoke.free_port()
    import socket
    for p in (a, b):
        with socket.socket() as s:
            s.bind(("127.0.0.1", p))


def test_only_directories_this_script_created_may_be_removed(tmp_path):
    mine = pathlib.Path(tempfile.mkdtemp(prefix=smoke.TMP_PREFIX))
    try:
        assert smoke.safe_to_remove(mine)
        assert not smoke.safe_to_remove(tmp_path), "wrong prefix"
        assert not smoke.safe_to_remove(ROOT) and not smoke.safe_to_remove(pathlib.Path.home()) and not smoke.safe_to_remove(pathlib.Path(tempfile.gettempdir()))
        nested = mine / (smoke.TMP_PREFIX + "inner"); nested.mkdir()
        assert not smoke.safe_to_remove(nested), "a prefixed directory that is not directly under the temp dir"
        f = mine / "file"; f.write_text("x")
        assert not smoke.safe_to_remove(f), "files are never removed"
        link = pathlib.Path(tempfile.gettempdir()) / (smoke.TMP_PREFIX + "link-test")
        link.symlink_to(ROOT)
        try:
            assert not smoke.safe_to_remove(link), "a symlink to somewhere else must not pass (resolves outside the temp dir)"
        finally:
            link.unlink()
    finally:
        shutil.rmtree(mine)


def test_listing_names_exact_paths(tmp_path):
    (tmp_path / "a").mkdir(); (tmp_path / "a/f.txt").write_text("x"); (tmp_path / "b.txt").write_text("y")
    short = smoke.list_tree(tmp_path)
    assert short[0].startswith(str(tmp_path)) and any(l.startswith(str(tmp_path / "a")) and "1 entries" in l for l in short) and any(l == str(tmp_path / "b.txt") for l in short)
    assert str(tmp_path / "a" / "f.txt") in smoke.list_tree(tmp_path, everything=True)


@pytest.mark.skipif(not (ROOT / "frontend/node_modules").is_dir() or not shutil.which("npm"), reason="frontend dependencies not installed (make setup)")
def test_smoke_script_end_to_end(capfd):
    before = set(pathlib.Path(tempfile.gettempdir()).glob(smoke.TMP_PREFIX + "*"))
    code = smoke.main([])
    out = capfd.readouterr().out
    assert code == 0 and "PASSED" in out and "stopped cdi serve" in out and "stopped frontend dev server" in out
    assert "removing exactly this temporary directory" in out
    assert set(pathlib.Path(tempfile.gettempdir()).glob(smoke.TMP_PREFIX + "*")) == before, "the smoke run left no temporary directory behind"
