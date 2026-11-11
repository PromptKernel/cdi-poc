#!/usr/bin/env python3
"""End-to-end smoke test of the two-terminal setup, on free ports, in a temporary directory.

  1. a throw-away git repository: a copy of the pinned test fixture, or (CDI_SAMPLE_REPO=path) a local clone of the sample repository
  2. `cdi baseline full` there (JSON store), then one local PR analysis (`cdi pr`) on a synthetic scenario branch
  3. `cdi serve` (token required) and the frontend dev server, each on a free port, started by this script
  4. checks: /api/health, the token is enforced, the "analyze" data (/api/meta: schema version, per-repo commits), a trace, the report of the PR run,
     the frontend page, and that the page's runtime config points at the API
  5. shutdown: only the processes started here are stopped (their own process groups); the temporary directory is listed, then removed

Usage: backend/scripts/smoke.py [--keep]   (run with the project's venv python; `make smoke`). Needs `make setup` first.
Environment: CDI_SMOKE_HOST (default 127.0.0.1), CDI_SAMPLE_REPO, VENV (default .venv)."""
from __future__ import annotations
import argparse, contextlib, json, os, pathlib, secrets, shutil, signal, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FIXTURE = BACKEND / "tests" / "fixtures" / "sample"
TMP_PREFIX = "cdi-smoke-"


def free_port(host="127.0.0.1") -> int:
    with socket.socket() as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def http(url, token=None, timeout=10):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def wait_for(url, what, proc, seconds=60, token=None):
    end = time.time() + seconds
    while time.time() < end:
        if proc.poll() is not None:
            raise RuntimeError(f"{what} exited early with code {proc.returncode}")
        try:
            if http(url, token, 2)[0] < 500:
                return
        except OSError:
            pass
        time.sleep(0.4)
    raise RuntimeError(f"{what} did not answer on {url} within {seconds}s")


def safe_to_remove(path: pathlib.Path) -> bool:
    """Only a directory this script created: inside the system temp dir and named with our prefix."""
    p = path.resolve()
    return p.is_dir() and p.name.startswith(TMP_PREFIX) and p.parent == pathlib.Path(tempfile.gettempdir()).resolve()


def list_tree(path: pathlib.Path, everything=False):
    """Exact paths that will be removed: the directory, its children and (with everything=True) every file. Counts include .git."""
    if everything:
        return sorted(str(p) for p in [path, *path.rglob("*")])
    out = [f"{path}  ({sum(1 for _ in path.rglob('*'))} entries in total)"]
    for child in sorted(path.iterdir()):
        n = sum(1 for _ in child.rglob("*")) if child.is_dir() else 0
        out.append(f"{child}{'/  (' + str(n) + ' entries)' if child.is_dir() else ''}")
    return out


def stop(proc: subprocess.Popen, what: str):
    """Terminate the process group this script started (start_new_session=True), nothing else."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.wait(timeout=5)
    print(f"[smoke] stopped {what} (pid {proc.pid})")


def run(cmd, cwd, env, what):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{what} failed (exit {r.returncode}):\n{r.stdout[-1500:]}\n{r.stderr[-1500:]}")
    return r.stdout


def make_repo(work: pathlib.Path) -> pathlib.Path:
    repo = work / "target"
    sample = os.environ.get("CDI_SAMPLE_REPO")
    ident = ["-c", "user.name=smoke", "-c", "user.email=smoke@example.invalid", "-c", "commit.gpgsign=false"]
    if sample:
        subprocess.run(["git", "clone", "-q", "--local", sample, str(repo)], check=True)
        print(f"[smoke] target: local clone of CDI_SAMPLE_REPO ({sample}); your checkout is not touched")
        return repo
    shutil.copytree(FIXTURE / ".cdi", repo / ".cdi")
    shutil.copytree(FIXTURE / "samples", repo / "samples", ignore=shutil.ignore_patterns("bin", "obj", "node_modules"))
    for cmd in (["init", "-q", "-b", "main"], ["add", "-A"], [*ident, "commit", "-q", "-m", "fixture"]):
        subprocess.run(["git", *cmd] if cmd[0] != "-c" else ["git", *cmd], cwd=repo, check=True)
    print("[smoke] target: a copy of the pinned test fixture in a temporary git repository")
    return repo


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", action="store_true", help="do not remove the temporary directory")
    ap.add_argument("--list-all", action="store_true", help="list every file before removing (default: the directory and its children with entry counts)")
    a = ap.parse_args(argv)
    host = os.environ.get("CDI_SMOKE_HOST", "127.0.0.1")
    venv = pathlib.Path(os.environ.get("VENV", ROOT / ".venv")).resolve()
    cdi = venv / "bin" / "cdi"
    if not cdi.exists():
        print(f"smoke: {cdi} not found; run `make setup` first", file=sys.stderr)
        return 2
    if not (ROOT / "frontend" / "node_modules").is_dir():
        print("smoke: frontend/node_modules missing; run `make setup` first", file=sys.stderr)
        return 2
    work = pathlib.Path(tempfile.mkdtemp(prefix=TMP_PREFIX))
    procs: list[tuple[subprocess.Popen, str]] = []
    token = secrets.token_hex(16)
    api_port, web_port = free_port(host), free_port(host)
    env = {**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1", "PATH": f"{venv / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    if "DOTNET_ROOT" not in env and pathlib.Path("/opt/homebrew/opt/dotnet/libexec").is_dir():
        env["DOTNET_ROOT"] = "/opt/homebrew/opt/dotnet/libexec"
    results: list[str] = []
    ok = False

    def check(cond, msg):
        if not cond:
            raise RuntimeError(f"check failed: {msg}")
        results.append(msg)
        print(f"[smoke] ok: {msg}")

    try:
        print(f"[smoke] temporary directory: {work}\n[smoke] ports: api {host}:{api_port}, web {host}:{web_port}")
        repo = make_repo(work)
        print("[smoke] cdi baseline full ...")
        run([str(cdi), "baseline", "full"], repo, env, "baseline")
        check((repo / "out/baseline.json").is_file(), "baseline written to out/baseline.json")
        if (repo / ".cdi/scenarios.yml").is_file():
            run([str(cdi.parent / "python"), "-m", "cdi.eval.scenarios", "--names", "pr-f-route"], repo, env, "scenario branch")
            print("[smoke] cdi pr --pr pr-f-route ...")
            run([str(cdi), "pr", "--pr", "pr-f-route"], repo, env, "pr")
            check((repo / "out/pr-comment.md").is_file() and (repo / "out/report-pr-f-route.md").is_file(), "local PR run wrote the report and the comment")

        serve_env = {**env, "CDI_API_TOKEN": token}
        serve = subprocess.Popen([str(cdi), "serve", "--host", host, "--port", str(api_port), "--cors-origin", f"http://{host}:{web_port}"],
                                 cwd=repo, env=serve_env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
        procs.append((serve, "cdi serve"))
        api = f"http://{host}:{api_port}"
        wait_for(f"{api}/api/health", "cdi serve", serve)
        check(json.loads(http(f"{api}/api/health")[1]) == {"status": "ok", "auth_required": True}, "/api/health answers and says a token is required")
        check(http(f"{api}/api/meta")[0] == 401, "a data route without the token is refused (401)")
        code, body = http(f"{api}/api/meta", token)
        meta = json.loads(body)
        check(code == 200 and meta["baseline"]["schema_version"] == 1 and set(meta["baseline"]["commits"]) == set(meta["repos"]),
              "analyze data (/api/meta): schema version and a commit id for every logical repo")
        nodes = json.loads(http(f"{api}/api/nodes?limit=1", token)[1])
        check(len(nodes) == 1, "a node search returns data")
        tr = json.loads(http(f"{api}/api/trace?id={urllib.request.quote(nodes[0]['id'], safe='')}&direction=forward", token)[1])
        check(tr["start"] == nodes[0]["id"], "a trace call answers for that node")
        if (repo / "out/report-pr-f-route.md").is_file():
            reports = json.loads(http(f"{api}/api/reports", token)[1])["reports"]
            check(any(r["name"] == "pr-f-route" for r in reports), "the PR run's report is listed by the API")

        web_env = {**env, "CDI_WEB_HOST": host, "CDI_WEB_PORT": str(web_port), "CDI_API_BASE_URL": api}
        web = subprocess.Popen(["npm", "run", "dev"], cwd=ROOT / "frontend", env=web_env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
        procs.append((web, "frontend dev server"))
        page = f"http://{host}:{web_port}"
        wait_for(f"{page}/", "frontend dev server", web)
        code, html = http(f"{page}/")
        check(code == 200 and '<div id="root">' in html, "the frontend page is served")
        cfg = json.loads(http(f"{page}/config.json")[1])
        check(cfg == {"apiBaseUrl": api}, "the page's runtime config.json points at the API (from CDI_API_BASE_URL)")
        req = urllib.request.Request(f"{api}/api/health", headers={"Origin": page})
        with urllib.request.urlopen(req, timeout=5) as r:
            check(r.headers.get("access-control-allow-origin") == page, "the API allows exactly the frontend's origin (no wildcard)")
        ok = True
    except Exception as e:                           # report, then fall through to the cleanup
        print(f"[smoke] FAILED: {e}", file=sys.stderr)
        for proc, name in procs:
            if proc.poll() is not None and proc.stderr:
                print(f"[smoke] {name} stderr: {proc.stderr.read().decode()[-800:]}", file=sys.stderr)
    finally:
        for proc, name in reversed(procs):
            stop(proc, name)
        if a.keep:
            print(f"[smoke] --keep: leaving {work}")
        elif safe_to_remove(work):
            files = list_tree(work, a.list_all)
            print("[smoke] removing exactly this temporary directory (created by this run) and nothing else:")
            for f in files:
                print(f"[smoke]   {f}")
            shutil.rmtree(work)
            print(f"[smoke] removed {work}")
        else:
            print(f"[smoke] NOT removing {work}: it is not a directory created by this script", file=sys.stderr)
    print(f"[smoke] {'PASSED' if ok else 'FAILED'} ({len(results)} checks)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
