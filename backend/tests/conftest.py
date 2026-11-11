"""Shared fixtures. Scanner tests run the real scanners on a throw-away git repo that contains a copy of config/ and samples/,
so they can exercise commit_id, the dirty-tree check and --only overlays without touching the real working tree."""
import json, os, pathlib, shutil, subprocess, sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]    # repository root (config/, samples/ still live here until the fixture switch)
BACKEND = ROOT / "backend"
sys.path.insert(0, str(ROOT / "tools"))
ENV = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1"}
if "DOTNET_ROOT" not in ENV and pathlib.Path("/opt/homebrew/opt/dotnet/libexec").is_dir():
    ENV["DOTNET_ROOT"] = "/opt/homebrew/opt/dotnet/libexec"
GIT_ID = ["-c", "user.name=test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false"]


def sh(cmd, cwd=None, check=True):
    return subprocess.run(cmd, cwd=cwd, env=ENV, capture_output=True, text=True, check=check)


@pytest.fixture(scope="session", autouse=True)
def built_scanners():
    for proj in ("sql-scriptdom", "dotnet-roslyn"):
        sh(["dotnet", "build", "-nologo", "-v", "q", str(BACKEND / "scanners" / proj)])


def scan_cmd(project, repo, out, only=None):
    kind = {"web": "ts", "api": "cs", "db": "sql"}[repo]
    base = ["--config", str(project / "config"), "--repo", repo, "--out", str(out)]
    if only is not None:
        base += ["--only", str(only)]
    if kind == "ts":
        return ["node", str(BACKEND / "scanners/ts-morph/scan.mjs")] + base
    dll = {"cs": "dotnet-roslyn/bin/Debug/net10.0/CsScanner.dll", "sql": "sql-scriptdom/bin/Debug/net10.0/SqlScanner.dll"}[kind]
    return ["dotnet", str(BACKEND / "scanners" / dll)] + base


class Project:
    """A copy of config/ + samples/ in a temp dir, committed to its own git repo."""
    def __init__(self, path, tweak=None):
        self.path = path
        shutil.copytree(ROOT / "config", path / "config")
        if tweak:
            tweak(path)
        shutil.copytree(ROOT / "samples", path / "samples", ignore=shutil.ignore_patterns("bin", "obj", "node_modules"))
        sh(["git", "init", "-q", "-b", "main"], cwd=path)
        sh(["git", "add", "-A"], cwd=path)
        sh(["git", *GIT_ID, "commit", "-q", "-m", "fixture"], cwd=path)

    def scan(self, repo, out_name=None, only=None, check=True):
        out = self.path / "out" / (out_name or f"{repo}.json")
        only_file = None
        if only is not None:
            only_file = self.path / f"only_{repo}.txt"
            only_file.write_text("\n".join(only))
        r = sh(scan_cmd(self.path, repo, out, only_file), cwd=self.path, check=False)
        if check and r.returncode != 0:
            raise AssertionError(f"scan {repo} failed:\n{r.stdout}\n{r.stderr}")
        return r, (json.loads(out.read_text()) if out.exists() and r.returncode == 0 else None)

    def commit_all(self, msg="change"):
        sh(["git", "add", "-A"], cwd=self.path)
        sh(["git", *GIT_ID, "commit", "-q", "-m", msg], cwd=self.path)

    def head_for(self, folder):
        return sh(["git", "log", "-1", "--format=%H", "--", folder], cwd=self.path).stdout.strip()


@pytest.fixture(scope="session")
def project(tmp_path_factory):
    return Project(tmp_path_factory.mktemp("proj"))


@pytest.fixture(scope="session")
def full(project):
    """Full baseline scans of all three logical repos from the committed fixture."""
    return {r: project.scan(r, f"full_{r}.json")[1] for r in ("web", "api", "db")}


def names(frag):
    return {n["id"]: n for n in frag["nodes"]}


def make_branch(project, branch, edits, base="main"):
    from cdi.eval.scenarios import make_branch as mb
    return mb(project.path, branch, edits, base, workdir=project.path.parent, ident=GIT_ID)
