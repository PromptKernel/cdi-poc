"""Evaluation harness: run the impact engine on the scenario branches and compare the affected workflows it reports with the GROUND TRUTH.

Rules enforced here:
  * eval/ground_truth.yml must be COMMITTED and UNMODIFIED, otherwise the run is refused (the ground truth is fixed before any run, never edited to fit output).
  * The run happens in a temporary local clone of the repository (scenario branches are created there, never in the real repo) and, by default, with an in-memory
    baseline built from that clone, so nothing is written to Neo4j and no branch of yours is touched.
ALL numbers are 'measured on synthetic data' (the synthetic-extended sample). They are not compared with any outside target in this repository.
usage: python -m cdi.eval.run_eval [--source .] [--gt eval/ground_truth.yml] [--out out/eval] [--baseline memory|neo4j]"""
from __future__ import annotations
import argparse, copy, datetime, json, pathlib, subprocess, sys, tempfile, time
from cdi.paths import BACKEND_ROOT as ROOT           # noqa: E402  (the directory holding scanners/)
from cdi.eval import ground_truth as G, metrics as M          # noqa: E402
from cdi.impact import diff as D, engine                       # noqa: E402
from cdi.impact import traverse as T                           # noqa: E402
from cdi.linker.graphio import load_config                     # noqa: E402

LABEL = "Measured on synthetic data (the synthetic-extended sample). Not a statement about real code bases."
NOT_FOUND_CAUSES = {"referenced_not_found", "no_matching_route", "annotation_target_not_found"}
GIT_ID = ["-c", "user.name=eval-harness", "-c", "user.email=eval@example.invalid", "-c", "commit.gpgsign=false"]


class GroundTruthNotCommitted(RuntimeError):
    pass


def ground_truth_commit(repo, gt_path):
    """Return {'commit', 'committed_at'} of the ground-truth file, or raise unless it is tracked, committed and unmodified."""
    repo, gt_path = pathlib.Path(repo).resolve(), pathlib.Path(gt_path).resolve()
    rel = str(gt_path.relative_to(repo))
    if subprocess.run(["git", "-C", str(repo), "ls-files", "--error-unmatch", rel], capture_output=True).returncode != 0:
        raise GroundTruthNotCommitted(f"{rel} is not tracked by git: commit the ground truth BEFORE running an evaluation")
    if D.git(repo, "status", "--porcelain", "--", rel):
        raise GroundTruthNotCommitted(f"{rel} has uncommitted changes: the ground truth is never edited to match tool output; commit it as written or restore it")
    sha, ct = D.git(repo, "log", "-1", "--format=%H %ct", "--", rel).split()
    return {"file": rel, "commit": sha, "committed_at": datetime.datetime.fromtimestamp(int(ct), datetime.timezone.utc).isoformat(timespec="seconds")}


def reported_workflows(result, kinds):
    """(all, confirmed_only): workflow-kind nodes the tool reports as affected: consumers of every changed object, plus a changed object that is itself a workflow."""
    allw, conf = set(), set()
    for o in result["objects"]:
        if o["kind"] in kinds:
            allw.add(o["name"]); conf.add(o["name"])
        for grp in o["consumers"].values():
            for c in grp:
                if c["kind"] in kinds:
                    allw.add(c["name"])
                    if c["confidence"] == "CONFIRMED_STATIC":
                        conf.add(c["name"])
    return allw, conf


def unresolved_counts(result):
    ids = {u["edge_id"]: u for u in result["new_unresolved"]}
    for o in result["objects"]:
        for u in o["unresolved_own"] + o["unresolved_in_scope"]:
            ids.setdefault(u["edge_id"], u)
    nf = [u for u in ids.values() if u.get("target_cause") in NOT_FOUND_CAUSES or (u["confidence"] == "UNRESOLVED" and u.get("target_kind") == "SQL_REF")]
    return {"unresolved_items": len(ids), "not_found_items": len(nf), "introduced_by_the_pr": len(result["new_unresolved"])}


def explain_miss(name, result, base, head, kinds, depth=12):
    """Why was a ground-truth workflow not reported? Uses the graphs; every reason names the evidence."""
    def find(g):
        return [n for n in g.nodes.values() if n["name"] == name and n["kind"] in kinds]
    nodes = find(head) or find(base)
    if not nodes:
        return {"code": "not_in_graph", "reason": f"no {'/'.join(kinds)} node named '{name}' exists in the baseline or the after-PR graph (the name may be wrong, or the scanner does not model it)"}
    if not result["objects"]:
        return {"code": "no_changed_object", "reason": "the tool mapped no changed object for this PR, so nothing could be traced to any workflow"}
    changed = {o["id"] for o in result["objects"]}
    for label, g in (("baseline", base), ("after-PR", head)):
        n = next((x for x in nodes if x["id"] in g.nodes), None)
        if not n:
            continue
        best, trunc, _ = T.reach_ex(g, n["id"], "forward", depth, engine.EXCL)
        if changed & set(best):
            return {"code": "reached_but_not_reported", "reason": f"the {label} graph does reach a changed object from this workflow; it was not reported (unexpected: investigate the report filters)"}
        unres = [e for e in g.edges.values() if e["confidence"] == "UNRESOLVED" and e["source"] in best]
        if unres:
            u = sorted(unres, key=lambda e: e["id"])[0]
            return {"code": "unresolved_link_on_path", "reason": f"its dependency path contains an UNRESOLVED link ({u['type']} at {u['repo']}:{u['source_file']}:{u['location']['line']}: {u.get('reason')}); "
                                                                 f"the tool never traverses unresolved links, so a relationship through it cannot be reported ({len(unres)} unresolved link(s) on its path)"}
        if trunc:
            return {"code": "depth_limit", "reason": f"the {label} graph traversal from this workflow stopped at the configured depth limit ({depth})"}
        return {"code": "no_path", "reason": f"no path (confirmed, inferred or unresolved) leads from this workflow to any changed object in the {label} graph: the effect is not visible to static analysis "
                                              f"(for example runtime configuration or behaviour that is not an edge), or the ground truth expects something the graph does not model"}
    return {"code": "not_in_graph", "reason": "the workflow node exists in neither graph"}


def unexpected_detail(name, result, kinds):
    out = []
    for o in result["objects"]:
        if o["kind"] in kinds and o["name"] == name:
            out.append({"via": "the changed object itself", "confidence": "CONFIRMED_STATIC"})
        for grp in o["consumers"].values():
            for c in grp:
                if c["name"] == name:
                    out.append({"via": o["name"], "confidence": c["confidence"], "evidence": f"{c['path'][-1]['repo']}:{c['path'][-1]['file']}:{c['path'][-1]['line']}" if c["path"] else None})
    return out


def evaluate_scenario(name, gt_entry, result, base, head, kinds, universe):
    gt = set(gt_entry["affected_workflows"])
    rep_all, rep_conf = reported_workflows(result, kinds)
    m_all, m_conf = M.workflow_metrics(gt, rep_all, universe), M.workflow_metrics(gt, rep_conf, universe)
    return {
        "scenario": name, "synthetic": True, "description": gt_entry.get("description", ""),
        "changed_objects": [{"name": o["name"], "kind": o["kind"], "change": o["change"], "risk": (o["risk"] or {}).get("label")} for o in result["objects"]],
        "ground_truth": sorted(gt), "reported_any_confidence": sorted(rep_all), "reported_confirmed_only": sorted(rep_conf),
        "metrics_any_confidence": m_all, "metrics_confirmed_only": m_conf,
        "found_only_through_inferred_links": sorted((gt & rep_all) - rep_conf),
        "misses": [{"workflow": w, **explain_miss(w, result, base, head, kinds)} for w in m_all["misses"]],
        "unexpected": [{"workflow": w, "detail": unexpected_detail(w, result, kinds)} for w in m_all["unexpected"]],
        "unresolved_and_not_found": unresolved_counts(result),
        "pr_run_duration_s": result["meta"]["timing_s"]["total_pr_run"],
        "baseline_freshness": {"status": "stale" if any("STALE" in w for w in result["meta"]["warnings"]) else "fresh",
                               "commits": result["meta"]["baseline_commits"], "loaded_at": result["meta"]["baseline_loaded_at"],
                               "mode": result["meta"]["baseline_mode"], "warnings": result["meta"]["warnings"]},
    }


def run(source=".", gt_path="eval/ground_truth.yml", out="out/eval", baseline="memory", tool_root=ROOT, scenarios_only=None):
    started = time.perf_counter()
    source = pathlib.Path(source).resolve()
    gt_file = pathlib.Path(gt_path)
    gt_file = gt_file if gt_file.is_absolute() else source / gt_file
    gtc = ground_truth_commit(source, gt_file)                     # refuses to run unless committed and unmodified
    gt = G.load(gt_file)
    from cdi.eval import scenarios as S
    from cdi.pipeline import baseline as B
    from cdi.pipeline.scanrun import ScanRunner
    names = [n for n in gt["scenarios"] if not scenarios_only or n in scenarios_only]
    unknown = [n for n in names if n not in S.SCENARIOS]
    if unknown:
        raise SystemExit(f"ground truth names scenarios that cdi/eval/scenarios.py does not define: {unknown}")
    kinds = gt["workflow_kinds"]
    with tempfile.TemporaryDirectory(prefix="cdi-eval-") as td:
        td = pathlib.Path(td)
        clone = td / "clone"
        subprocess.run(["git", "clone", "-q", "--local", "--branch", "main", str(source), str(clone)], check=True, capture_output=True)
        cfg = load_config(clone / ".cdi/config.yml")
        runner = ScanRunner(tool_root, load_config(clone / ".cdi/config.yml")["dir"], clone / "out/work")
        if baseline == "neo4j":
            from cdi.graph import store
            from cdi.graph.load_neo4j import connect
            drv, db = connect(load_config(source / ".cdi/config.yml"))
            base, fresh = store.read_graph(drv, db); drv.close()
            if not fresh:
                raise SystemExit("no baseline in Neo4j")
            base.commits = dict(fresh["commits"]); baseline_build_s = None
        else:
            _, _, base, meta = B.full(runner, clone, cfg)
            fresh = {"commits": meta["commits"], "loaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                     "mode": "full (in-memory, built from the clone for this run)"}
            baseline_build_s = meta["duration_s"]
        universe = set(G.workflow_names(base, kinds))
        per = []
        for n in names:
            S.make_branch(clone, n, S.SCENARIOS[n], base="main", workdir=td, ident=GIT_ID)
            keep = {}
            res = engine.analyze(clone, tool_root, clone / ".cdi/config.yml", "main", n, base, fresh, name=n, runner=runner, keep=keep)
            per.append(evaluate_scenario(n, gt["scenarios"][n], res, keep["base"], keep["head"], kinds, universe))
    durs = [p["pr_run_duration_s"] for p in per]
    summary = {
        "label": LABEL,
        "meta": {"run_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "ground_truth": gtc, "source_head": D.git(source, "rev-parse", "HEAD"),
                 "workflow_kinds": kinds, "universe_workflows": len(universe), "baseline": baseline, "baseline_commits": fresh["commits"],
                 "scenarios_run": names, "wall_clock_s": round(time.perf_counter() - started, 1)},
        "scenarios": per,
        "overall_any_confidence": M.aggregate([p["metrics_any_confidence"] for p in per]),
        "overall_confirmed_only": M.aggregate([p["metrics_confirmed_only"] for p in per]),
        "timing": {"baseline_build_s": baseline_build_s, "pr_run_s": durs, "pr_run_mean_s": round(sum(durs) / len(durs), 3) if durs else None, "pr_run_max_s": max(durs) if durs else None},
    }
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    from cdi.eval import report
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=list))
    (out / "summary.md").write_text(report.render(summary))
    return summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="."); ap.add_argument("--gt", default="eval/ground_truth.yml"); ap.add_argument("--out", default="out/eval")
    ap.add_argument("--baseline", default="memory", choices=["memory", "neo4j"]); ap.add_argument("--only", nargs="*")
    a = ap.parse_args(argv)
    try:
        s = run(a.source, a.gt, a.out, a.baseline, scenarios_only=a.only)
    except GroundTruthNotCommitted as e:
        sys.exit(f"REFUSED: {e}")
    o = s["overall_any_confidence"]
    print(f"[eval] {len(s['scenarios'])} scenario(s), {o['ground_truth']} ground-truth workflow(s): micro recall {M.pct(o['micro_recall'])}, "
          f"false-positive share {M.pct(o['micro_false_positive_share'])} -- {LABEL}\n[eval] wrote {a.out}/summary.md and summary.json")


if __name__ == "__main__":
    main()
