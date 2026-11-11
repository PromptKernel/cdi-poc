"""Load scanner fragments into an in-memory graph; shared by the linker, loader and impact engine."""
from __future__ import annotations
import json, pathlib
import yaml

RANK = {"CONFIRMED_STATIC": 0, "INFERRED": 1, "UNRESOLVED": 2}


def load_config(config=None, environ=None):
    """Load and validate `.cdi/config.yml` (see cdi.config) and return the dict the tool reads (repos, routes, naming, graph, risk-rules, ci, ...)."""
    from cdi import config as C
    return C.as_legacy(C.load(config, environ))


def load_fragments(graph_dir, repo_names, include_linked=False):
    gd = pathlib.Path(graph_dir)
    frags = []
    for r in repo_names:
        p = gd / f"{r}.json"
        if p.exists():
            frags.append(json.loads(p.read_text()))
    if include_linked and (gd / "linked.json").exists():
        frags.append(json.loads((gd / "linked.json").read_text()))
    return frags


class Graph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}
        self.out: dict[str, list] = {}
        self.inn: dict[str, list] = {}
        self.commits: dict[str, str] = {}

    @classmethod
    def from_fragments(cls, frags):
        g = cls()
        for f in frags:
            if f["repo"] in ("linked",):
                for r, c in (f.get("inputs") or {}).items():
                    g.commits.setdefault(r, c)
            else:
                g.commits[f["repo"]] = f["commit_id"]
            for n in f["nodes"]:
                g.nodes.setdefault(n["id"], n)
            for e in f["edges"]:
                g.add_edge(e)
        return g

    def add_edge(self, e):
        if e["id"] in self.edges:
            return
        self.edges[e["id"]] = e
        self.out.setdefault(e["source"], []).append(e)
        self.inn.setdefault(e["target"], []).append(e)

    def by_name(self, name, kinds=None):
        return [n for n in self.nodes.values() if n["name"] == name and (kinds is None or n["kind"] in kinds)]

    def dangling(self):
        return [e["id"] for e in self.edges.values() if e["source"] not in self.nodes or e["target"] not in self.nodes]
