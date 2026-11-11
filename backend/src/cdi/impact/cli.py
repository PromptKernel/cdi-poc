"""PR impact analysis.
usage: python -m cdi.impact.cli --target main --pr <branch> [--name pr-a] [--baseline neo4j|files] [--out out]
Reads the baseline graph read-only (Neo4j or out/graph files), never writes to it. Output: out/report-<name>.md and .json."""
from __future__ import annotations
import argparse, json, pathlib, sys
from cdi.linker.graphio import Graph, load_config
from . import engine, report

from cdi.paths import BACKEND_ROOT as TOOL_ROOT


def load_baseline(cfg, source, graph_dir):
    if source == "neo4j":
        from cdi.graph.load_neo4j import connect
        from cdi.graph import store
        driver, db = connect(cfg)
        g, fresh = store.read_graph(driver, db)
        driver.close()
        return g, fresh
    gd = pathlib.Path(graph_dir)
    frags = [json.loads((gd / f"{r['name']}.json").read_text()) for r in cfg["repos"]["repos"]] + [json.loads((gd / "linked.json").read_text())]
    meta = json.loads((gd / "baseline.meta.json").read_text())
    return Graph.from_fragments(frags), {"commits": meta["commits"], "loaded_at": meta.get("loaded_at"), "mode": meta["mode"], "counts": meta["counts"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default="main"); ap.add_argument("--pr", required=True); ap.add_argument("--name")
    ap.add_argument("--baseline", default="neo4j", choices=["neo4j", "files"]); ap.add_argument("--graph", default="out/graph")
    ap.add_argument("--config", default="config"); ap.add_argument("--out", default="out")
    a = ap.parse_args(argv)
    root = pathlib.Path(".").resolve()
    cfg = load_config(a.config)
    base, fresh = load_baseline(cfg, a.baseline, a.graph)
    if fresh:
        base.commits = dict(fresh["commits"])
    res = engine.analyze(root, TOOL_ROOT, a.config, a.target, a.pr, base, fresh, name=a.name or a.pr)
    out = pathlib.Path(a.out); out.mkdir(parents=True, exist_ok=True)
    slug = (a.name or a.pr).replace("/", "_")
    (out / f"report-{slug}.md").write_text(report.render(res))
    (out / f"report-{slug}.json").write_text(report.to_json(res))
    print(f"[impact] {out / f'report-{slug}.md'}  objects={len(res['objects'])}  PR run {res['meta']['timing_s']['total_pr_run']} s")
    for w in res["meta"]["warnings"]:
        print("WARNING:", w)


if __name__ == "__main__":
    main()
