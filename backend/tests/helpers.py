"""Tiny graph builders for unit tests (no scanners involved)."""
from cdi.linker.graphio import Graph


def node(repo, kind, name, file="f.x", line=1, attrs=None, synthetic=False):
    n = {"id": f"{repo}:{kind.lower()}:{name}", "kind": kind, "name": name, "repo": repo, "file": file,
         "location": {"line": line, "end_line": line + 1}, "synthetic": synthetic}
    if attrs:
        n["attrs"] = attrs
    return n


def edge(typ, src, tgt, conf="CONFIRMED_STATIC", repo="web", file="f.x", line=1, reason=None, evidence="", attrs=None):
    e = {"id": f"{typ}|{src['id']}|{tgt['id']}|{file}:{line}:1", "type": typ, "source": src["id"], "target": tgt["id"], "source_file": file,
         "location": {"line": line, "column": 1}, "analysis_method": "test:manual", "confidence": conf, "commit_id": "a" * 40,
         "repo": repo, "synthetic": False, "evidence": evidence}
    if conf != "CONFIRMED_STATIC":
        e["reason"] = reason or "test reason"
    if attrs:
        e["attrs"] = attrs
    return e


def graph(nodes, edges, commits=None):
    g = Graph()
    for n in nodes:
        g.nodes[n["id"]] = n
    for e in edges:
        g.add_edge(e)
    g.commits = commits or {r: "a" * 40 for r in {n["repo"] for n in nodes}}
    return g
