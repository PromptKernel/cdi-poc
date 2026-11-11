#!/usr/bin/env python3
"""Export the graph for the local explorer: out/explorer/graph.json, plus copies of the impact reports and the latest simulated PR comment/status.
Source: the baseline in the configured store (JSON file by default; Neo4j via a READ-ONLY session when configured), read-only.
Generated data stays under out/ (git-ignored). Nothing is deleted: files are overwritten, never removed.
usage: python -m cdi.export [--source auto|json|neo4j] [--out out/explorer] [--store-path FILE] [--config .cdi/config.yml] [--reports-dir out]"""
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


def load_graph(source, cfg, store_path=None):
    """Return (graph, freshness, actual_source). source: auto | json | neo4j. `auto` uses Neo4j when configured and reachable, else the JSON baseline."""
    from cdi import store as S
    order = {"auto": [cfg["store"], "json"], "json": ["json"], "files": ["json"], "neo4j": ["neo4j"]}[source]
    last = None
    for kind in dict.fromkeys(order):
        try:
            with S.open_store(cfg, kind, store_path, **({"wait": 5} if kind == "neo4j" else {})) as st:
                g, fresh = st.read()
            return g, fresh, kind
        except (S.StoreError, SystemExit, OSError, RuntimeError, ImportError) as e:
            last = e
            if source != "auto":
                raise
            print(f"[export] {kind} store not usable ({type(e).__name__}: {e}); trying the next", file=sys.stderr)
    raise SystemExit(f"no usable baseline store: {last}")


def graph_document(g, fresh, cfg, source):
    """The explorer's graph.json shape (also served by the API): {meta, nodes, edges}."""
    return {"meta": {"generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "source": source,
                     "baseline": fresh, "notice": NOTICE,
                     "repos": {r["name"]: {"path": r["path"], "kind": r["kind"]} for r in cfg["repos"]["repos"]},
                     "counts": {"nodes": len(g.nodes), "edges": len(g.edges)}},
            "nodes": sorted((node_json(n) for n in g.nodes.values()), key=lambda n: n["id"]),
            "edges": sorted((edge_json(e) for e in g.edges.values()), key=lambda e: e["id"])}


def report_summary(js_text):
    d = json.loads(js_text)
    return {"objects": len(d.get("objects", [])), "pr": d.get("meta", {}).get("pr"),
            "labels": sorted({o["risk"]["label"] for o in d.get("objects", []) if o.get("risk")}),
            "warnings": len(d.get("meta", {}).get("warnings", []))}


def export(source="auto", out="out/explorer", store_path=None, config=None, reports_dir="out"):
    cfg = load_config(config)
    g, fresh, actual = load_graph(source, cfg, store_path)
    out = pathlib.Path(out)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    (out / "pr").mkdir(parents=True, exist_ok=True)
    data = graph_document(g, fresh, cfg, actual)
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
    ap.add_argument("--source", default="auto", choices=["auto", "json", "neo4j"]); ap.add_argument("--out", default="out/explorer")
    ap.add_argument("--store-path", default=None); ap.add_argument("--config", default=None); ap.add_argument("--reports-dir", default="out")
    a = ap.parse_args(argv)
    print(json.dumps(export(a.source, a.out, a.store_path, a.config, a.reports_dir)))


if __name__ == "__main__":
    main()
