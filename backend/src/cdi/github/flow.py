"""The two GitHub flows.

baseline: runs ONLY for the base branch (a push event on it). It is the only code that writes a baseline.
pr:       runs on pull_request events of the SAME repository. It restores the baseline (read-only), classifies it against the PR's merge-base,
          analyses the PR, upserts one comment and sets one commit status. It never writes the baseline: a missing, wrong-schema or
          unmatched baseline is replaced by a full build held in memory for this run only, and the comment says so.
Both are advisory: they exit 0 on every problem with GitHub or with the baseline; only a tool failure of the baseline job exits non-zero."""
from __future__ import annotations
import argparse, dataclasses, json, os, pathlib, subprocess, sys
from cdi import store as S
from cdi.ci import adapters
from cdi.impact import diff as D
from cdi.linker.graphio import load_config
from cdi.paths import BACKEND_ROOT
from cdi.pipeline import baseline as B, run_pr
from cdi.pipeline.scanrun import ScanRunner
from . import event as E
from .adapter import GitHubAdapter
from .client import Client
from .summary import Summary


# ---------------------------------------------------------------- baseline classification (PR side)
@dataclasses.dataclass
class RepoBaseline:
    repo: str
    status: str                      # current | behind | ahead | unmatched
    baseline: str | None
    expected: str | None             # the repo folder's last commit at the PR's merge-base
    commits: int = 0                 # behind / ahead distance in commits that touched the folder

    def message(self):
        b, e = (self.baseline or "?")[:8], (self.expected or "?")[:8]
        if self.status == "behind":
            return f"baseline for '{self.repo}' is {self.commits} commit(s) behind the PR's merge-base ({b} vs {e})"
        if self.status == "ahead":
            return (f"baseline for '{self.repo}' is {self.commits} commit(s) AHEAD of the PR's merge-base ({b} vs {e}): the PR branched earlier "
                    f"than the baseline; results describe the newer base and may differ from the merge result of an older base")
        return f"baseline for '{self.repo}' (commit {b}) cannot be matched to the PR's merge-base ({e})"


def _git_ok(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True).returncode == 0


def _is_commit(root, sha):
    return bool(sha) and _git_ok(root, "cat-file", "-e", f"{sha}^{{commit}}")


def _ancestor(root, a, b):
    return _git_ok(root, "merge-base", "--is-ancestor", a, b)


def classify(root, fresh, merge_base, repos) -> list[RepoBaseline]:
    out = []
    for r in repos:
        rec = (fresh.get("commits") or {}).get(r["name"])
        exp = D.folder_commit(root, merge_base, r["path"]) or None
        if not rec or not exp or not _is_commit(root, rec):
            out.append(RepoBaseline(r["name"], "unmatched", rec, exp)); continue
        if rec == exp:
            out.append(RepoBaseline(r["name"], "current", rec, exp)); continue
        if _ancestor(root, rec, exp):
            n = int(D.git(root, "rev-list", "--count", f"{rec}..{exp}", "--", r["path"]) or 0)
            out.append(RepoBaseline(r["name"], "behind", rec, exp, n)); continue
        if _ancestor(root, exp, rec):
            n = int(D.git(root, "rev-list", "--count", f"{exp}..{rec}", "--", r["path"]) or 0)
            out.append(RepoBaseline(r["name"], "ahead", rec, exp, n)); continue
        out.append(RepoBaseline(r["name"], "unmatched", rec, exp))
    return out


def resolve_target_rev(root, base_ref):
    """The PR's base ref as a revision in this checkout (a detached checkout has no local branch, so try the remote-tracking one)."""
    for cand in (base_ref, f"origin/{base_ref}", f"refs/remotes/origin/{base_ref}"):
        try:
            D.resolve(root, cand)
            return cand
        except RuntimeError:
            continue
    raise RuntimeError(f"base ref '{base_ref}' is not available in this checkout (fetch it, e.g. actions/checkout with fetch-depth: 0)")


def make_loader(root, cfg, store, event_pr, notes, tool_root=BACKEND_ROOT, work=None):
    """Return load_baseline(cfg, kind, path) for run_pr.run: read the store, classify, or fall back to an in-memory full build. NEVER writes."""
    def loader(_cfg, _kind=None, _path=None):
        reason = None
        try:
            g, fresh = store.read()
        except S.BaselineMissing as e:
            reason = f"no baseline was found in the cache ({e})"
        except S.BaselineSchemaMismatch as e:
            reason = f"the cached baseline was rejected: {e}"
        except S.StoreError as e:
            reason = f"the cached baseline is unusable: {e}"
        mb = D.merge_base(root, D.resolve(root, resolve_target_rev(root, event_pr.base_ref)), D.resolve(root, event_pr.head_sha))
        if reason is None:
            cls = classify(root, fresh, mb, cfg["repos"]["repos"])
            bad = [c for c in cls if c.status == "unmatched"]
            if not bad:
                for c in cls:
                    if c.status in ("behind", "ahead"):
                        notes.append(c.message())
                fresh = dict(fresh, notes=list(notes), classification=[dataclasses.asdict(c) for c in cls])
                return g, fresh
            reason = "; ".join(c.message() for c in bad)
        notes.append(f"Fell back to a FULL build of the base revision (merge-base {mb[:8]}) for this run because {reason}. "
                     f"The stored baseline was not modified.")
        runner = ScanRunner(tool_root, cfg["dir"], pathlib.Path(work or root / "out") / "work")
        _, _, g2, meta = B.full(runner, root, cfg, mb)
        fresh2 = S.make_freshness(g2, meta["commits"], "full-fallback", to_commit=mb)
        fresh2["notes"] = list(notes)
        return g2, fresh2
    return loader


# ---------------------------------------------------------------- PR flow
def run_pr_flow(root=".", config=None, store_path=None, out=None, environ=None, tool_root=BACKEND_ROOT, summary=None, client_factory=None):
    """Returns the exit code (always 0 unless blocking is enabled in config and a deterministic policy hit)."""
    env = os.environ if environ is None else environ
    root = pathlib.Path(root).resolve()
    sm = summary or Summary(env)
    sm.add("## Dependency impact (advisory)")
    try:
        pr = E.parse_pull_request(E.load_event(env))
    except E.EventError as e:
        sm.warning(f"not a pull_request run: {e}. Nothing was analysed.", "cdi")
        sm.write(); return 0
    if pr.is_fork:
        sm.add(f"**Skipped:** pull request #{pr.number} comes from a fork (`{pr.head_repo or 'deleted fork'}`). Fork runs get a read-only token and no secrets, "
               f"so the tool neither comments nor sets a status there.")
        sm.write(); return 0
    config = str(pathlib.Path(config) if config else root / ".cdi/config.yml")
    cfg = load_config(config, env)
    out = pathlib.Path(out or root / "out")
    store = S.open_store(cfg, "json", store_path, root=root)            # the PR flow only ever reads a JSON file restored from the cache
    notes: list[str] = []
    token = env.get("GITHUB_TOKEN")
    run_url = f"{env.get('GITHUB_SERVER_URL', 'https://github.com')}/{pr.base_repo}/actions/runs/{env['GITHUB_RUN_ID']}" if env.get("GITHUB_RUN_ID") else None
    if token:
        factory = client_factory or (lambda t, api: Client(t, api))
        adapter = GitHubAdapter(factory(token, env.get("GITHUB_API_URL")), pr.base_repo, pr.number, pr.head_sha,
                                cfg["ci"].get("github", {}).get("comment_author", "github-actions[bot]"), run_url)
    else:
        sm.warning("GITHUB_TOKEN is not set: the report is written to files only, nothing is posted.", "cdi")
        adapter = adapters.FileSink(out)
    try:
        target_rev = resolve_target_rev(root, pr.base_ref)
    except RuntimeError as e:
        sm.warning(f"{e}. Nothing was analysed.", "cdi")
        sm.write(); return 0
    ns = argparse.Namespace(target=target_rev, pr=pr.head_sha, name=f"pr-{pr.number}", store="json", store_path=None,
                            config=config, out=str(out), adapter=None, enable_azure_adapter=False, pull_request_id=None, blocking=False)
    summary_d, code = run_pr.run(ns, root=root, tool_root=tool_root, load_baseline=make_loader(root, cfg, store, pr, notes, tool_root, out), adapter=adapter)
    sm.add(f"**State:** `{summary_d['state']}` · target `{pr.base_ref}` (from the PR event) · PR head `{pr.head_sha[:8]}` · mode {summary_d['mode']}")
    for n in notes:
        sm.add(f"- {n}")
    post = summary_d.get("post") or {}
    if post.get("comment"):
        sm.add(f"- Comment {post['comment']['action']}: {post['comment'].get('url') or post['comment']['id']}")
    if post.get("status"):
        sm.add(f"- Commit status `{post['status']['context']}` set to `{post['status']['state']}`")
    for e in post.get("errors", []) + ([post["error"]] if post.get("error") else []):
        sm.warning(f"could not post to GitHub: {e}. The run stays advisory (exit 0).", "cdi")
    if summary_d.get("error"):
        sm.warning(f"analysis failed: {summary_d['error']}", "cdi")
    if summary_d.get("skipped"):
        sm.add(f"- Analysis skipped: {summary_d.get('skip_reason')}")
    sm.write()
    return code


# ---------------------------------------------------------------- baseline flow
def run_baseline_flow(root=".", config=None, store_path=None, out=None, environ=None, tool_root=BACKEND_ROOT, summary=None):
    """Build the full baseline of the checked-out base branch and write the JSON store. Refuses to run for anything but a push to the base branch."""
    env = os.environ if environ is None else environ
    root = pathlib.Path(root).resolve()
    sm = summary or Summary(env)
    config = str(pathlib.Path(config) if config else root / ".cdi/config.yml")
    cfg = load_config(config, env)
    base = cfg["branches"]["base"]
    name, ref = env.get("GITHUB_EVENT_NAME"), env.get("GITHUB_REF")
    if name is not None and not (name == "push" and ref == f"refs/heads/{base}"):
        msg = (f"refusing to build a baseline for event '{name}' on '{ref}': baselines are produced only by a push to the base branch "
               f"'{base}' (branches.base).")
        sm.add(f"**Baseline not built.** {msg}"); sm.write()
        print(msg, file=sys.stderr)
        return 2
    out = pathlib.Path(out or root / "out")
    runner = ScanRunner(tool_root, cfg["dir"], out / "work")
    _, _, g, meta = B.full(runner, root, cfg, "HEAD")
    fresh = S.make_freshness(g, meta["commits"], "full", to_commit=meta["rev"])
    st = S.open_store(cfg, "json", store_path, root=root)
    res = st.write_full(g, fresh)
    size = pathlib.Path(res["path"]).stat().st_size
    limit = cfg["limits"]["baseline_max_bytes"]
    sm.add("## Dependency baseline",
           f"Built from `{base}` @ `{meta['rev'][:8]}`: {len(g.nodes)} nodes, {len(g.edges)} edges, schema version {S.SCHEMA_VERSION}.",
           f"Per-repo commits: " + ", ".join(f"{r} `{c[:8]}`" for r, c in sorted(meta["commits"].items())),
           f"**Baseline size:** {size:,} bytes (limit {limit:,}; `limits.baseline_max_bytes`, a placeholder of ours).")
    if size > limit:
        sm.warning(f"the baseline is {size:,} bytes, over the configured limit of {limit:,} (limits.baseline_max_bytes). "
                   f"It is still saved; large caches are evicted sooner and slow every PR run.", "cdi baseline size")
    sm.write()
    print(json.dumps({"store": st.describe(), "bytes": size, "over_limit": size > limit, **res}))
    return 0
