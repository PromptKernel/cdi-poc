"""Load scanner + linker fragments into Neo4j. Config: config/graph.yml (+ NEO4J_PASSWORD env var). Idempotent (MERGE by id).
usage: python -m cdi.graph.load_neo4j [--config config] [--graph out/graph] [--reset]"""
from __future__ import annotations
import argparse, json, os, pathlib, sys, time
from neo4j import GraphDatabase
from cdi.linker.graphio import Graph, load_config, load_fragments

EDGE_TYPES = {"CALLS", "DISPATCHES_TO", "USES_TYPE", "MAKES_REQUEST", "ROUTES_TO", "CALLS_PROCEDURE", "RESOLVES_TO",
              "READS_TABLE", "WRITES_TABLE", "READS_VIEW", "EXECUTES_DYNAMIC_SQL", "TESTS"}
NODE_KINDS = {"UI_COMPONENT", "UI_SERVICE_METHOD", "UI_MODEL", "HTTP_REQUEST", "API_ENDPOINT", "SERVICE_METHOD", "DATA_ACCESS_METHOD",
              "METHOD", "INTERFACE_METHOD", "SQL_REF", "SQL_PROC", "SQL_VIEW", "SQL_TABLE", "SQL_COLUMN", "TEST", "UNRESOLVED"}


def connect(cfg, wait=90):
    n = cfg["graph"]["neo4j"]
    pw = os.environ.get(n["password_env"])
    if not pw:
        sys.exit(f"set the {n['password_env']} environment variable (see graph/docker-compose.yml)")
    driver = GraphDatabase.driver(n["uri"], auth=(n["user"], pw))
    deadline = time.time() + wait
    while True:
        try:
            driver.verify_connectivity()
            return driver, n.get("database", "neo4j")
        except Exception as ex:   # server still starting
            if time.time() > deadline:
                raise
            time.sleep(2)


def node_row(n):
    loc = n.get("location") or {}
    return {"id": n["id"], "p": {"id": n["id"], "kind": n["kind"], "name": n["name"], "repo": n["repo"], "file": n.get("file"),
            "line": loc.get("line"), "end_line": loc.get("end_line"), "synthetic": n["synthetic"], "attrs": json.dumps(n.get("attrs") or {})}}


def edge_row(e):
    loc = e["location"]
    return {"id": e["id"], "s": e["source"], "t": e["target"],
            "p": {"id": e["id"], "type": e["type"], "confidence": e["confidence"], "source_file": e["source_file"], "line": loc["line"],
                  "column": loc.get("column"), "end_line": loc.get("end_line"), "analysis_method": e["analysis_method"],
                  "commit_id": e["commit_id"], "repo": e["repo"], "synthetic": e["synthetic"], "reason": e.get("reason"),
                  "evidence": e.get("evidence"), "attrs": json.dumps(e.get("attrs") or {})}}


def load(graph: Graph, driver, db, batch=500, reset=False):
    stats = {"nodes": 0, "edges": 0, "edges_skipped_missing_endpoint": 0}
    with driver.session(database=db) as s:
        s.run("CREATE CONSTRAINT node_id IF NOT EXISTS FOR (n:Node) REQUIRE n.id IS UNIQUE").consume()
        if reset:
            s.run("MATCH (n:Node) DETACH DELETE n").consume()
        by_kind = {}
        for n in graph.nodes.values():
            assert n["kind"] in NODE_KINDS, n["kind"]
            by_kind.setdefault(n["kind"], []).append(node_row(n))
        for kind, rows in by_kind.items():
            for i in range(0, len(rows), batch):
                s.run(f"UNWIND $rows AS r MERGE (n:Node {{id: r.id}}) SET n:{kind}, n += r.p", rows=rows[i:i + batch]).consume()
                stats["nodes"] += len(rows[i:i + batch])
        by_type = {}
        for e in graph.edges.values():
            assert e["type"] in EDGE_TYPES, e["type"]
            by_type.setdefault(e["type"], []).append(edge_row(e))
        for typ, rows in by_type.items():
            for i in range(0, len(rows), batch):
                chunk = rows[i:i + batch]
                made = s.run(f"UNWIND $rows AS r MATCH (a:Node {{id: r.s}}), (b:Node {{id: r.t}}) "
                             f"MERGE (a)-[x:{typ} {{id: r.id}}]->(b) SET x += r.p RETURN count(x) AS c", rows=chunk).single()["c"]
                stats["edges"] += made
                stats["edges_skipped_missing_endpoint"] += len(chunk) - made
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config"); ap.add_argument("--graph", default="out/graph"); ap.add_argument("--reset", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    g = Graph.from_fragments(load_fragments(a.graph, [r["name"] for r in cfg["repos"]["repos"]], include_linked=True))
    driver, db = connect(cfg)
    st = load(g, driver, db, cfg["graph"]["load"]["batch_size"], a.reset)
    with driver.session(database=db) as s:
        counts = {"nodes": s.run("MATCH (n:Node) RETURN count(n) AS c").single()["c"], "relationships": s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]}
    print(f"[load] commits={g.commits}")
    print(f"[load] merged: {st}")
    print(f"[load] database now holds: {counts}")
    driver.close()


if __name__ == "__main__":
    main()
