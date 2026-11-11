#!/usr/bin/env python3
"""Export the graph for the local explorer: out/explorer/graph.json, plus copies of the impact reports and the latest simulated PR comment/status.
Source: the baseline in Neo4j via a READ-ONLY session when NEO4J_PASSWORD is set (and the store has a baseline), else the scan/linker files in out/graph.
Generated data stays under out/ (git-ignored). Nothing is deleted: files are overwritten, never removed.
usage: python -m cdi.export [--source auto|neo4j|files] [--out out/explorer] [--graph out/graph] [--config config] [--reports-dir out]"""
from __future__ import annotations
import argparse, datetime, json, os, pathlib, shutil, sys

from cdi.linker.graphio import Graph, load_config, load_fragments          # noqa: E402

NOTICE = ("Structure only: static-analysis evidence from a small SYNTHETIC-extended sample (upstream sample code plus clearly marked synthetic additions). "
          "It says nothing about real code bases.")


def node_json(n):
    loc = n.get("location") or {}
    return {"id": n["id"], "kind": n["kind"], "name": n["name"], "repo": n["repo"], "file": n.get("file"), "line": loc.get("line"),
            "end_line": loc.get("end_line"), "synthetic": bool(n.get("synthetic")), "attrs": n.get("attrs") or {}}


def edge_json(e):
    loc = e["location"]
    return {"id": e["id"], "type": e["type"], "source": e["source"], "target": e["target"], "confidence": e["confidence"], "source_file": e["source_file"],
            "line": loc["line"], "column": loc.get("column"), "commit_id": e["commit_id"], "repo": e["repo"], "synthetic": bool(e["synthetic"]),
            "reason": e.get("reason"), "evidence": e.get("evidence") or "", "analysis_method": e["analysis_method"], "attrs": e.get("attrs") or {}}


def load_graph(source, cfg, graph_dir):
    """Return (graph, baseline_info|None, actual_source)."""
    if source in ("auto", "neo4j") and os.environ.get(cfg["graph"]["neo4j"]["password_env"]):
        try:
            from cdi.graph.load_neo4j import connect
            from cdi.graph import store
            driver, db = connect(cfg, wait=5)
            try:
                g, fresh = store.read_graph(driver, db)          # read-only session
            finally:
                driver.close()
            if fresh and g.nodes:
                return g, fresh, "neo4j"
            if source == "neo4j":
                raise RuntimeError("Neo4j has no baseline")
        except Exception as e:
            if source == "neo4j":
                raise
            print(f"[export] Neo4j not usable ({type(e).__name__}); falling back to files", file=sys.stderr)
    elif source == "neo4j":
        raise SystemExit("source=neo4j needs the NEO4J_PASSWORD environment variable")
    names = [r["name"] for r in cfg["repos"]["repos"]]
    frags = load_fragments(graph_dir, names, include_linked=True)
    if not frags:
        raise SystemExit(f"no scan/linker files in {graph_dir}; run pipeline/scan_all.sh and pipeline/link_and_load.sh first")
    g = Graph.from_fragments(frags)
    meta_file = pathlib.Path(graph_dir) / "baseline.meta.json"
    fresh = None
    if meta_file.exists():
        m = json.loads(meta_file.read_text())
        fresh = {"commits": m.get("commits"), "loaded_at": m.get("loaded_at"), "mode": m.get("mode")}
    elif g.commits:
        fresh = {"commits": dict(g.commits), "loaded_at": None, "mode": "files"}
    return g, fresh, "files"


def export(source="auto", out="out/explorer", graph_dir="out/graph", config="config", reports_dir="out"):
    cfg = load_config(config)
    g, fresh, actual = load_graph(source, cfg, graph_dir)
    out = pathlib.Path(out)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "pr").mkdir(parents=True, exist_ok=True)
    data = {"meta": {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "source": actual,
                     "baseline": fresh, "notice": NOTICE,
                     "repos": {r["name"]: {"path": r["path"], "kind": r["kind"]} for r in cfg["repos"]["repos"]},
                     "counts": {"nodes": len(g.nodes), "edges": len(g.edges)}},
            "nodes": sorted((node_json(n) for n in g.nodes.values()), key=lambda n: n["id"]),
            "edges": sorted((edge_json(e) for e in g.edges.values()), key=lambda e: e["id"])}
    (out / "graph.json").write_text(json.dumps(data, indent=1))
    rd = pathlib.Path(reports_dir)
    reports = []
    for md in sorted(rd.glob("report-*.md")):
        js = md.with_suffix(".json")
        name = md.stem[len("report-"):]
        shutil.copyfile(md, out / "reports" / md.name)
        entry = {"name": name, "md": f"reports/{md.name}", "json": None, "modified": datetime.datetime.fromtimestamp(md.stat().st_mtime, datetime.timezone.utc).isoformat(timespec="seconds")}
        if js.exists():
            shutil.copyfile(js, out / "reports" / js.name)
            entry["json"] = f"reports/{js.name}"
            try:
                d = json.loads(js.read_text())
                entry["summary"] = {"objects": len(d.get("objects", [])), "pr": d.get("meta", {}).get("pr"),
                                    "labels": sorted({o["risk"]["label"] for o in d.get("objects", []) if o.get("risk")}),
                                    "warnings": len(d.get("meta", {}).get("warnings", []))}
            except Exception:
                pass
        reports.append(entry)
    (out / "reports" / "index.json").write_text(json.dumps({"reports": reports}, indent=1))
    pr = {"comment": None, "status": None}
    for key, fname in (("comment", "pr-comment.md"), ("status", "pr-status.json")):
        if (rd / fname).exists():
            shutil.copyfile(rd / fname, out / "pr" / fname)
            pr[key] = f"pr/{fname}"
    (out / "pr" / "index.json").write_text(json.dumps(pr, indent=1))
    return {"out": str(out), "source": actual, "nodes": len(g.nodes), "edges": len(g.edges), "reports": len(reports), "pr_comment": bool(pr["comment"])}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="auto", choices=["auto", "neo4j", "files"]); ap.add_argument("--out", default="out/explorer")
    ap.add_argument("--graph", default="out/graph"); ap.add_argument("--config", default="config"); ap.add_argument("--reports-dir", default="out")
    a = ap.parse_args(argv)
    print(json.dumps(export(a.source, a.out, a.graph, a.config, a.reports_dir)))


if __name__ == "__main__":
    main()
