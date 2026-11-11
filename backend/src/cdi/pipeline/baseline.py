"""Baseline runner.
  full:        scan all logical repos from a committed revision, link, and REPLACE the graph in Neo4j.
  incremental: given a commit range, re-scan only the changed files (plus files that depend on changed definitions) with --only,
               merge into the baseline, RE-LINK the whole graph (ROUTES_TO / RESOLVES_TO / TESTS are fully recomputed), and sync Neo4j.
A full rebuild of the same commit must produce an identical graph (same node and edge ids); tests/test_baseline.py checks that.
usage: python -m cdi.pipeline.baseline full [--rev HEAD]
       python -m cdi.pipeline.baseline incremental --from <rev> --to <rev>"""
from __future__ import annotations
import argparse, contextlib, json, pathlib, subprocess, sys, time, uuid
from cdi.impact import diff as D
from cdi.linker import merge as M
from cdi.linker.graphio import Graph, load_config
from .scanrun import ScanRunner

from cdi.paths import BACKEND_ROOT as TOOL_ROOT


@contextlib.contextmanager
def checkout(project_root, rev, scratch, label="wt"):
    """Yield a directory holding `rev`. The main working tree is used when `rev` is HEAD and the tree is clean; otherwise a git worktree is
    created at an exact named path and removed afterwards with `git worktree remove` on that path only."""
    project_root = pathlib.Path(project_root)
    sha = D.resolve(project_root, rev)
    if sha == D.resolve(project_root, "HEAD") and not D.git(project_root, "status", "--porcelain"):
        yield project_root
        return
    path = pathlib.Path(scratch) / f"{label}-{sha[:8]}-{uuid.uuid4().hex[:6]}"
    D.git(project_root, "worktree", "add", "--detach", str(path), sha)
    try:
        yield path
    finally:
        D.git(project_root, "worktree", "remove", "--force", str(path))


def repo_entries(cfg):
    return cfg["repos"]["repos"]


def full(runner, project_root, cfg, rev="HEAD", scratch=None):
    t0 = time.perf_counter()
    scratch = scratch or runner.work / "worktrees"
    frags = {}
    with checkout(project_root, rev, scratch, "full") as root:
        for r in repo_entries(cfg):
            frags[r["name"]] = runner.scan(r, pathlib.Path(root) / r["path"])
    linked = M.relink(frags, cfg)
    g = M.full_graph(frags, linked)
    meta = {"mode": "full", "rev": D.resolve(project_root, rev), "commits": {r: f["commit_id"] for r, f in frags.items()},
            "duration_s": round(time.perf_counter() - t0, 2), "counts": {"nodes": len(g.nodes), "edges": len(g.edges)}}
    return frags, linked, g, meta


def incremental(runner, project_root, cfg, baseline: Graph, baseline_commits, from_rev, to_rev, scratch=None):
    """Returns (frags, linked, graph, meta). `baseline` is the full stored graph (scanner + linker content) at `from_rev`."""
    t0 = time.perf_counter()
    scratch = scratch or runner.work / "worktrees"
    names = [r["name"] for r in repo_entries(cfg)]
    frags = M.split_scanner_fragments(baseline, names, baseline_commits)
    base_g = Graph.from_fragments(list(frags.values()))
    plan = {}
    with checkout(project_root, to_rev, scratch, "inc") as root:
        for r in repo_entries(cfg):
            ch = D.changes(project_root, from_rev, to_rev, r["path"])
            scanned = [c for c in ch if D.is_scanned(c.path, r.get("include", []), r.get("exclude", []))]
            deleted = {c.path for c in scanned if c.status == "D"}
            am = {c.path for c in scanned if c.status in ("A", "M")}
            new_commit = D.folder_commit(project_root, to_rev, r["path"])
            overlay = None
            touched = am | deleted
            if touched:
                folder = pathlib.Path(root) / r["path"]
                scan_files = set(am)
                if am:
                    overlay = runner.scan(r, folder, only_files=am)
                defs = [n["name"] for n in (overlay or {"nodes": []})["nodes"] if n["kind"] in M.DEFINITION_KINDS]
                extra = M.dependents(base_g, r["name"], touched, defs) - touched
                if extra:                      # files whose edges depend on changed definitions are re-emitted too
                    scan_files |= extra
                    overlay = runner.scan(r, folder, only_files=scan_files)
                    touched = touched | extra
                frags[r["name"]] = M.apply_overlay(frags[r["name"]], overlay, touched, new_commit)
            else:
                frags[r["name"]] = M.apply_overlay(frags[r["name"]], None, set(), new_commit)
            plan[r["name"]] = {"changed": sorted(am), "deleted": sorted(deleted), "dependents_rescanned": sorted(touched - am - deleted)}
    linked = M.relink(frags, cfg)
    g = M.full_graph(frags, linked)
    meta = {"mode": "incremental", "from": D.resolve(project_root, from_rev), "to": D.resolve(project_root, to_rev),
            "commits": {r: f["commit_id"] for r, f in frags.items()}, "plan": plan,
            "duration_s": round(time.perf_counter() - t0, 2), "counts": {"nodes": len(g.nodes), "edges": len(g.edges)}}
    return frags, linked, g, meta


def write_files(out_dir, frags, linked, meta):
    out = pathlib.Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for r, f in frags.items():
        (out / f"{r}.json").write_text(json.dumps(f, indent=2))
    (out / "linked.json").write_text(json.dumps(linked, indent=2))
    (out / "baseline.meta.json").write_text(json.dumps(meta, indent=2))


def graph_ids(g: Graph):
    return set(g.nodes), set(g.edges)


def compare_graphs(a: Graph, b: Graph):
    """Differences between two graphs by node/edge ids (the incremental-equals-full check)."""
    an, ae, bn, be = set(a.nodes), set(a.edges), set(b.nodes), set(b.edges)
    return {"nodes_only_in_a": sorted(an - bn), "nodes_only_in_b": sorted(bn - an), "edges_only_in_a": sorted(ae - be), "edges_only_in_b": sorted(be - ae),
            "counts_a": (len(an), len(ae)), "counts_b": (len(bn), len(be))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["full", "incremental"])
    ap.add_argument("--rev", default="HEAD"); ap.add_argument("--from", dest="frm"); ap.add_argument("--to", default="HEAD")
    ap.add_argument("--config", default=None, help="path to .cdi/config.yml (default: $CDI_CONFIG or .cdi/config.yml)"); ap.add_argument("--out", default="out/graph"); ap.add_argument("--no-neo4j", action="store_true")
    a = ap.parse_args(argv)
    root = pathlib.Path(".").resolve()
    cfg = load_config(a.config)
    runner = ScanRunner(TOOL_ROOT, cfg["dir"], root / "out/work")
    driver = db = None
    if not a.no_neo4j:
        from cdi.graph.load_neo4j import connect
        driver, db = connect(cfg)
    from cdi.graph import store
    if a.mode == "full":
        frags, linked, g, meta = full(runner, root, cfg, a.rev)
        fresh = store.make_freshness(g, meta["commits"], "full", to_commit=meta["rev"])
        if driver:
            meta["neo4j"] = store.write_full(driver, db, g, fresh)
    else:
        if not a.frm:
            sys.exit("incremental needs --from <rev>")
        if not driver:
            sys.exit("incremental reads the stored baseline from Neo4j; set NEO4J_PASSWORD")
        base, fresh0 = store.read_graph(driver, db)
        if not fresh0:
            sys.exit("no baseline in Neo4j: run `full` first")
        frags, linked, g, meta = incremental(runner, root, cfg, base, fresh0["commits"], a.frm, a.to)
        fresh = store.make_freshness(g, meta["commits"], "incremental", meta["from"], meta["to"])
        meta["neo4j"] = store.sync(driver, db, g, fresh)
    meta["loaded_at"] = (fresh or {}).get("loaded_at")
    write_files(a.out, frags, linked, meta)
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
