"""Graph traversal used by the trace CLI and (later) the impact engine. Pure functions over linker.graphio.Graph.

Edges mean "source depends on target".
  forward  (dependencies / root-cause tracing): follow edges source -> target
  reverse  (consumers / impact):                follow edges target -> source
UNRESOLVED edges are never traversed (their target is not a real node); they are reported separately with their reason.
A path's confidence is its WEAKEST hop (CONFIRMED_STATIC < INFERRED); it is never upgraded.
"""
from __future__ import annotations
from cdi.linker.graphio import RANK, Graph

TRAVERSABLE = ("CONFIRMED_STATIC", "INFERRED")


def hop(g: Graph, e: dict, direction: str) -> dict:
    frm, to = (e["source"], e["target"]) if direction == "forward" else (e["target"], e["source"])
    n = lambda i: g.nodes.get(i, {"name": i, "repo": "?", "kind": "?"})
    return {"edge_id": e["id"], "type": e["type"], "confidence": e["confidence"], "from": frm, "to": to,
            "from_name": n(frm)["name"], "to_name": n(to)["name"], "from_kind": n(frm)["kind"], "to_kind": n(to)["kind"],
            "repo": e["repo"], "file": e["source_file"], "line": e["location"]["line"], "evidence": e.get("evidence", ""),
            "reason": e.get("reason"), "commit": e["commit_id"], "synthetic": e["synthetic"], "method": e["analysis_method"],
            "attrs": e.get("attrs") or {}}


def path_confidence(hops) -> str:
    return max((h["confidence"] for h in hops), key=lambda c: RANK[c]) if hops else "CONFIRMED_STATIC"


def neighbours(g: Graph, node_id: str, direction: str, exclude_types=()):
    adj = g.out if direction == "forward" else g.inn
    for e in adj.get(node_id, []):
        if e["confidence"] in TRAVERSABLE and e["type"] not in exclude_types:
            yield e


def paths(g: Graph, start: str, direction: str, max_depth: int = 25, exclude_types=()):
    """All maximal simple paths from `start` (each a list of hop dicts). A path ends where no further traversable edge leads to an unvisited node."""
    out = []

    def dfs(node, visited, acc):
        nxt = [e for e in neighbours(g, node, direction, exclude_types)
               if (e["target"] if direction == "forward" else e["source"]) not in visited]
        if not nxt or len(acc) >= max_depth:
            if acc:
                out.append(list(acc))
            return
        for e in sorted(nxt, key=lambda e: e["id"]):
            h = hop(g, e, direction)
            acc.append(h)
            dfs(h["to"], visited | {h["to"]}, acc)
            acc.pop()

    dfs(start, {start}, [])
    return out


def reach(g: Graph, start: str, direction: str, max_depth: int = 25, exclude_types=()):
    """Every node reachable from `start` with the strongest available path to it: {node_id: (confidence, path)}.
    'Strongest' = lowest weakest-hop rank, then fewest hops. Never upgrades a confidence."""
    best = {start: ("CONFIRMED_STATIC", [])}
    frontier = [start]
    for _ in range(max_depth):
        nxt = []
        for n in frontier:
            conf0, p0 = best[n]
            for e in neighbours(g, n, direction, exclude_types):
                h = hop(g, e, direction)
                conf = max(conf0, h["confidence"], key=lambda c: RANK[c])
                cand = (RANK[conf], len(p0) + 1)
                cur = best.get(h["to"])
                if cur is None or cand < (RANK[cur[0]], len(cur[1])):
                    best[h["to"]] = (conf, p0 + [h])
                    nxt.append(h["to"])
        frontier = nxt
        if not frontier:
            break
    return best


def unresolved_in_scope(g: Graph, node_ids) -> list[dict]:
    """UNRESOLVED edges whose source is one of the given nodes: places where the graph is known to be incomplete."""
    ids = set(node_ids)
    return [e for e in g.edges.values() if e["confidence"] == "UNRESOLVED" and e["source"] in ids]


def find_nodes(g: Graph, text: str, kinds=None):
    """Exact id, exact name, then case-insensitive substring of name/id."""
    if text in g.nodes:
        return [g.nodes[text]]
    ex = [n for n in g.nodes.values() if n["name"] == text and (kinds is None or n["kind"] in kinds)]
    if ex:
        return ex
    t = text.lower()
    return [n for n in g.nodes.values() if (t in n["name"].lower() or t in n["id"].lower()) and (kinds is None or n["kind"] in kinds)]


def reach_ex(g: Graph, start: str, direction: str, max_depth: int = 25, exclude_types=()):
    """Like reach(), plus whether the traversal was cut off by the depth limit: returns (best, truncated, frontier_node_ids)."""
    best = reach(g, start, direction, max_depth, exclude_types)
    deepest = {n for n, (_, p) in best.items() if len(p) >= max_depth}
    cut = {n for n in deepest if any((e["target"] if direction == "forward" else e["source"]) not in best
                                     for e in neighbours(g, n, direction, exclude_types))}
    return best, bool(cut), sorted(cut)
