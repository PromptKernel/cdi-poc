"""Trace a node through the graph in one or both directions, with file:line evidence for every hop.
usage: python -m cdi.impact.trace <node id|name|substring> [--direction forward|reverse|both] [--backend memory|neo4j]
                              [--include-types USES_TYPE,...] [--graph out/graph] [--config config]
forward = what the node depends on (UI -> API -> SQL);  reverse = what depends on the node (SQL -> API -> UI, plus tests)."""
from __future__ import annotations
import argparse, collections, sys
from cdi.linker.graphio import Graph, load_config, load_fragments
from . import traverse as T


def fmt_hop(h):
    loc = f"{h['repo']}:{h['file']}:{h['line']}"
    extra = ""
    a = h["attrs"]
    if a.get("target_location"):
        extra = f"  [target defined at {a['target_location']}]"
    s = f"    --{h['type']} [{h['confidence']}]--> {h['to_name']}\n        evidence: {loc}  via {h['method']}{'  (synthetic)' if h['synthetic'] else ''}{extra}"
    if h["evidence"]:
        s += f"\n        source:   {h['evidence'][:110]}"
    if h["reason"]:
        s += f"\n        reason:   {h['reason']}"
    return s


def print_paths(start_name, direction, paths, label):
    arrow = "depends on" if direction == "forward" else "is depended on by"
    print(f"\n=== {label}: {start_name} {arrow} ... ({len(paths)} maximal paths; UNRESOLVED links are never traversed) ===")
    summary = collections.Counter()
    for i, p in enumerate(sorted(paths, key=lambda p: (len(p), [h['edge_id'] for h in p])), 1):
        conf = T.path_confidence(p)
        weakest = next((h for h in p if h["confidence"] == conf and conf != "CONFIRMED_STATIC"), None)
        summary[conf] += 1
        print(f"\n  path {i}: {len(p)} hops, path confidence = {conf}" + (f" (weakest hop: {weakest['type']} {weakest['from_name'].split('.')[-1]} -> {weakest['to_name'].split('.')[-1]})" if weakest else ""))
        print(f"    {start_name}")
        for h in p:
            print(fmt_hop(h))
    print(f"\n  summary: {dict(summary)}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("node"); ap.add_argument("--direction", default="both", choices=["forward", "reverse", "both"])
    ap.add_argument("--backend", default="memory", choices=["memory", "neo4j"])
    ap.add_argument("--include-types", default=""); ap.add_argument("--max-depth", type=int, default=25)
    ap.add_argument("--graph", default="out/graph"); ap.add_argument("--config", default="config")
    ap.add_argument("--kind", default=None)
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    g = Graph.from_fragments(load_fragments(a.graph, [r["name"] for r in cfg["repos"]["repos"]], include_linked=True))
    excl = [t for t in ((cfg.get("graph") or {}).get("trace", {}).get("default_exclude_types", [])) if t not in a.include_types.split(",")]
    hits = T.find_nodes(g, a.node, [a.kind] if a.kind else None)
    if len(hits) != 1:
        sys.exit(f"'{a.node}' matched {len(hits)} nodes: " + "; ".join(n["id"] for n in hits[:8]) + ("" if hits else " (none)"))
    start = hits[0]
    print(f"start node: {start['id']}  ({start['kind']}, {start.get('file','-')}:{(start.get('location') or {}).get('line','-')})  backend={a.backend}  excluded edge types: {excl}")
    dirs = ["forward", "reverse"] if a.direction == "both" else [a.direction]
    reached = {start["id"]}
    driver = db = None
    if a.backend == "neo4j":
        from cdi.graph.load_neo4j import connect
        from cdi.graph import neo4j_query as NQ
        driver, db = connect(cfg)
    for d in dirs:
        paths = T.paths(g, start["id"], d, a.max_depth, excl) if a.backend == "memory" else NQ.paths(driver, db, start["id"], d, a.max_depth, excl)
        label = "DEPENDENCIES (forward: what it depends on)" if d == "forward" else "CONSUMERS (reverse: what depends on it, incl. tests)"
        print_paths(start["name"], d, paths, label)
        for p in paths:
            reached.update(h["to"] for h in p)
    un = T.unresolved_in_scope(g, reached) if a.backend == "memory" else NQ.unresolved_from(driver, db, reached)
    print(f"\n=== UNRESOLVED links at nodes in this trace ({len(un)}) ===")
    for u in un:
        if a.backend == "memory":
            print(f"  {g.nodes[u['source']]['name']}\n    {u['type']} @ {u['repo']}:{u['source_file']}:{u['location']['line']}  -> {g.nodes.get(u['target'],{}).get('kind','?')}\n    reason: {u['reason']}")
        else:
            print(f"  {u['source']}\n    {u['type']} @ {u['file']}:{u['line']}  -> {u['target_kind']}\n    reason: {u['reason']}")


if __name__ == "__main__":
    main()
