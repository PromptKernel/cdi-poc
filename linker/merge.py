"""Merge an overlay scan into a baseline of scanner fragments, so that  baseline + overlay  ==  a full scan of the new commit.

Rules (so incremental and full graphs have identical node/edge ids):
  * edges whose evidencing file was changed/deleted are replaced by the overlay's edges;
  * nodes declared in changed/deleted files are replaced by the overlay's nodes (a deleted symbol disappears);
  * 'derived' nodes (HTTP_REQUEST, UI_MODEL, SQL_REF, UNRESOLVED) exist only while some edge references them, in any file;
  * edges left pointing at a removed node are dropped (a full scan could not resolve them either);
  * every edge and the fragment are re-stamped with the folder's commit at the new revision.
Files that depend on changed definitions must be re-emitted too: see dependents().
"""
from __future__ import annotations
from .graphio import Graph
from .link import Linker, build_fragment

LINKER_TYPES = {"ROUTES_TO", "RESOLVES_TO", "TESTS"}
DERIVED_KINDS = {"HTTP_REQUEST", "UI_MODEL", "SQL_REF", "UNRESOLVED"}
DEFINITION_KINDS = {"SQL_PROC", "SQL_TABLE", "SQL_VIEW"}


def split_scanner_fragments(graph: Graph, repo_names, commits):
    frags = {r: {"schema_version": "1.0", "repo": r, "commit_id": commits[r], "scanner": {"name": "merged", "version": "1"}, "nodes": [], "edges": []}
             for r in repo_names}
    for n in graph.nodes.values():
        if n["repo"] in frags:
            frags[n["repo"]]["nodes"].append(n)
    for e in graph.edges.values():
        if e["type"] not in LINKER_TYPES and e["repo"] in frags:
            frags[e["repo"]]["edges"].append(e)
    return frags


def apply_overlay(frag, overlay, touched, new_commit=None):
    touched = set(touched)
    nodes = {n["id"]: n for n in frag["nodes"] if not (n.get("file") in touched and n["kind"] not in DERIVED_KINDS)}
    edges = {e["id"]: e for e in frag["edges"] if e["source_file"] not in touched}
    if overlay:
        nodes.update({n["id"]: n for n in overlay["nodes"]})
        edges.update({e["id"]: e for e in overlay["edges"]})
    edges = {i: e for i, e in edges.items() if e["source"] in nodes and e["target"] in nodes}
    used = {x for e in edges.values() for x in (e["source"], e["target"])}
    nodes = {i: n for i, n in nodes.items() if n["kind"] not in DERIVED_KINDS or i in used}
    if new_commit:
        edges = {i: {**e, "commit_id": new_commit} for i, e in edges.items()}
    out = {k: v for k, v in frag.items() if k not in ("nodes", "edges")}
    if new_commit:
        out["commit_id"] = new_commit
    out["nodes"], out["edges"] = list(nodes.values()), list(edges.values())
    return out


def dependents(graph: Graph, repo, touched, new_definition_names=()):
    """Files (in `repo`, not themselves touched) whose edges depend on definitions in touched files, or that reference a name that the
    overlay now defines (an unresolved reference may become resolved)."""
    touched = set(touched)
    names = {x.lower() for x in new_definition_names}
    out = set()
    for e in graph.edges.values():
        if e["type"] in LINKER_TYPES or e["repo"] != repo or e["source_file"] in touched:
            continue
        t = graph.nodes.get(e["target"])
        if not t:
            continue
        if t.get("file") in touched and t["kind"] not in DERIVED_KINDS:
            out.add(e["source_file"])
        elif t["kind"] == "SQL_REF" and t["repo"] == repo and t["name"].lower() in names:
            out.add(e["source_file"])
    return out


def relink(frags: dict, cfg):
    g = Graph.from_fragments(list(frags.values()))
    return build_fragment(Linker(g, cfg).run())


def full_graph(frags: dict, linked) -> Graph:
    return Graph.from_fragments(list(frags.values()) + [linked])
