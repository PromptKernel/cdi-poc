"""Trace queries executed IN Neo4j (Cypher). Returns hop dicts shaped like impact.traverse.hop so one formatter serves both backends."""
from __future__ import annotations


def _hop(r):
    return {"edge_id": r["id"], "type": r["type"], "confidence": r["confidence"], "from": r["from"], "to": r["to"],
            "from_name": r["from_name"], "to_name": r["to_name"], "repo": r["repo"], "file": r["file"], "line": r["line"],
            "evidence": r["evidence"] or "", "reason": r["reason"], "commit": r["commit"], "synthetic": r["synthetic"], "method": r["method"],
            "attrs": __import__("json").loads(r["attrs"] or "{}")}


def paths(driver, db, start_id, direction, max_depth=25, exclude_types=()):
    d = int(max_depth)
    if direction == "forward":
        pat, anchor, end = "(s:Node {id:$id})-[rs*1..%d]->(t:Node)" % d, "s", "t"
        nxt = "(t)-[r2]->(x:Node)"
    else:
        pat, anchor, end = "(t:Node)-[rs*1..%d]->(s:Node {id:$id})" % d, "s", "t"
        nxt = "(x:Node)-[r2]->(t)"
    # Plain Cypher (no APOC): simple paths via a pairwise node-inequality check; maximal paths via the NOT EXISTS clause.
    q = f"""
    MATCH p = {pat}
    WHERE ALL(r IN rs WHERE r.confidence IN ['CONFIRMED_STATIC','INFERRED'] AND NOT type(r) IN $excl)
      AND ALL(i IN range(0, size(nodes(p))-2) WHERE ALL(j IN range(i+1, size(nodes(p))-1) WHERE nodes(p)[i] <> nodes(p)[j]))
      AND NOT EXISTS {{ MATCH {nxt} WHERE r2.confidence IN ['CONFIRMED_STATIC','INFERRED'] AND NOT type(r2) IN $excl AND NOT x IN nodes(p) }}
    WITH rs, relationships(p) AS rels
    RETURN [r IN rels | {{id: r.id, type: type(r), confidence: r.confidence, repo: r.repo, file: r.source_file, line: r.line,
                          evidence: r.evidence, reason: r.reason, commit: r.commit_id, synthetic: r.synthetic, method: r.analysis_method,
                          attrs: r.attrs, `from`: CASE WHEN $fwd THEN startNode(r).id ELSE endNode(r).id END,
                          `to`: CASE WHEN $fwd THEN endNode(r).id ELSE startNode(r).id END,
                          from_name: CASE WHEN $fwd THEN startNode(r).name ELSE endNode(r).name END,
                          to_name: CASE WHEN $fwd THEN endNode(r).name ELSE startNode(r).name END}}] AS hops"""
    with driver.session(database=db) as s:
        rows = s.run(q, id=start_id, excl=list(exclude_types), fwd=(direction == "forward")).data()
    out = []
    for row in rows:
        hops = [_hop(h) for h in row["hops"]]
        if direction != "forward":
            hops = list(reversed(hops))      # Cypher lists the chain in edge direction; present it outward from the start node
        out.append(hops)
    return out


def unresolved_from(driver, db, node_ids):
    q = """MATCH (a:Node)-[r]->(b:Node) WHERE r.confidence = 'UNRESOLVED' AND a.id IN $ids
           RETURN a.name AS source, type(r) AS type, r.source_file AS file, r.line AS line, r.reason AS reason, b.kind AS target_kind ORDER BY file, line"""
    with driver.session(database=db) as s:
        return s.run(q, ids=list(node_ids)).data()
