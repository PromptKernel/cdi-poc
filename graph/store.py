"""Neo4j graph store operations used by the baseline runner (writes) and the impact engine (read-only)."""
from __future__ import annotations
import datetime, json
import neo4j
from linker.graphio import Graph
from .load_neo4j import load


def _read_session(driver, db):
    return driver.session(database=db, default_access_mode=neo4j.READ_ACCESS)   # PR runs must never write: enforced by the server


def read_graph(driver, db):
    """Return (Graph, freshness dict or None) exactly as stored."""
    g = Graph()
    with _read_session(driver, db) as s:
        for r in s.run("MATCH (n:Node) RETURN n"):
            n = r["n"]
            node = {"id": n["id"], "kind": n["kind"], "name": n["name"], "repo": n["repo"], "synthetic": bool(n["synthetic"])}
            if n.get("file") is not None:
                node["file"] = n["file"]
                node["location"] = {"line": n["line"], "end_line": n["end_line"]}
            attrs = json.loads(n.get("attrs") or "{}")
            if attrs:
                node["attrs"] = attrs
            g.nodes[node["id"]] = node
        for r in s.run("MATCH (a:Node)-[x]->(b:Node) RETURN a.id AS s, b.id AS t, x"):
            x = r["x"]
            e = {"id": x["id"], "type": x["type"], "source": r["s"], "target": r["t"], "source_file": x["source_file"],
                 "location": {k: v for k, v in (("line", x["line"]), ("column", x.get("column")), ("end_line", x.get("end_line"))) if v is not None},
                 "analysis_method": x["analysis_method"], "confidence": x["confidence"], "commit_id": x["commit_id"], "repo": x["repo"],
                 "synthetic": bool(x["synthetic"])}
            for k in ("reason", "evidence"):
                if x.get(k) is not None:
                    e[k] = x[k]
            a = json.loads(x.get("attrs") or "{}")
            if a:
                e["attrs"] = a
            g.add_edge(e)
        f = s.run("MATCH (f:Freshness {id:'baseline'}) RETURN f").single()
    fresh = None
    if f:
        f = f["f"]
        fresh = {"commits": json.loads(f["commits"]), "loaded_at": f["loaded_at"], "mode": f["mode"], "from_commit": f.get("from_commit"),
                 "to_commit": f.get("to_commit"), "counts": json.loads(f["counts"])}
        g.commits = dict(fresh["commits"])
    return g, fresh


def _write_freshness(s, fresh):
    s.run("MERGE (f:Freshness {id:'baseline'}) SET f.commits=$c, f.loaded_at=$t, f.mode=$m, f.from_commit=$fc, f.to_commit=$tc, f.counts=$n",
          c=json.dumps(fresh["commits"]), t=fresh["loaded_at"], m=fresh["mode"], fc=fresh.get("from_commit"), tc=fresh.get("to_commit"),
          n=json.dumps(fresh["counts"])).consume()


def make_freshness(graph, commits, mode, from_commit=None, to_commit=None):
    return {"commits": dict(commits), "loaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "mode": mode,
            "from_commit": from_commit, "to_commit": to_commit, "counts": {"nodes": len(graph.nodes), "edges": len(graph.edges)}}


def write_full(driver, db, graph, fresh, batch=500):
    """Replace the whole graph for this commit set."""
    stats = load(graph, driver, db, batch, reset=True)
    with driver.session(database=db) as s:
        _write_freshness(s, fresh)
    return stats


def sync(driver, db, graph, fresh, batch=500):
    """Make the stored graph equal to `graph`: delete nodes/edges that are no longer present, merge the rest."""
    with driver.session(database=db) as s:
        old_edges = {r["i"] for r in s.run("MATCH ()-[x]->() RETURN x.id AS i")}
        old_nodes = {r["i"] for r in s.run("MATCH (n:Node) RETURN n.id AS i")}
        del_e, del_n = sorted(old_edges - set(graph.edges)), sorted(old_nodes - set(graph.nodes))
        for i in range(0, len(del_e), batch):
            s.run("UNWIND $ids AS i MATCH ()-[x {id: i}]->() DELETE x", ids=del_e[i:i + batch]).consume()
        for i in range(0, len(del_n), batch):
            s.run("UNWIND $ids AS i MATCH (n:Node {id: i}) DETACH DELETE n", ids=del_n[i:i + batch]).consume()
    stats = load(graph, driver, db, batch, reset=False)
    with driver.session(database=db) as s:
        _write_freshness(s, fresh)
    return {**stats, "edges_deleted": len(del_e), "nodes_deleted": len(del_n)}


def snapshot(driver, db):
    """(node ids, edge ids) currently stored; used to prove a PR run did not change the baseline."""
    with _read_session(driver, db) as s:
        return ({r["i"] for r in s.run("MATCH (n:Node) RETURN n.id AS i")}, {r["i"] for r in s.run("MATCH ()-[x]->() RETURN x.id AS i")})
