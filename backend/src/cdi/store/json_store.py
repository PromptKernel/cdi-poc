"""JSON baseline store: one file, written atomically. Layout:
{"schema_version": 1, "freshness": {commits per repo, loaded_at, mode, ...}, "nodes": [...], "edges": [...]}"""
from __future__ import annotations
import json, os, pathlib, tempfile
from cdi.linker.graphio import Graph
from . import SCHEMA_VERSION, BaselineMissing, BaselineSchemaMismatch, GraphStore, StoreError


class JsonStore(GraphStore):
    kind = "json"

    def __init__(self, path):
        self.path = pathlib.Path(path)

    def describe(self):
        return f"json:{self.path}"

    def _load(self):
        try:
            text = self.path.read_text()
        except FileNotFoundError as e:
            raise BaselineMissing(f"baseline file not found: {self.path}") from e
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as e:
            raise StoreError(f"baseline file {self.path} is not valid JSON ({e}); rebuild the baseline") from e
        if not isinstance(doc, dict) or doc.get("schema_version") != SCHEMA_VERSION:
            raise BaselineSchemaMismatch(doc.get("schema_version") if isinstance(doc, dict) else None, where=str(self.path))
        for k in ("freshness", "nodes", "edges"):
            if k not in doc:
                raise StoreError(f"baseline file {self.path} lacks '{k}'; rebuild the baseline")
        if not isinstance(doc["freshness"].get("commits"), dict) or not doc["freshness"]["commits"]:
            raise StoreError(f"baseline file {self.path} carries no per-repo commit ids; rebuild the baseline")
        return doc

    def read(self):
        doc = self._load()
        g = Graph()
        for n in doc["nodes"]:
            g.nodes[n["id"]] = n
        for e in doc["edges"]:
            g.add_edge(e)
        fresh = dict(doc["freshness"], schema_version=doc["schema_version"])
        g.commits = dict(fresh["commits"])
        if not g.nodes:
            raise BaselineMissing(f"baseline file {self.path} holds an empty graph")
        return g, fresh

    def write_full(self, graph, fresh):
        doc = {"schema_version": SCHEMA_VERSION, "freshness": {k: v for k, v in fresh.items() if k != "schema_version"},
               "nodes": sorted(graph.nodes.values(), key=lambda n: n["id"]), "edges": sorted(graph.edges.values(), key=lambda e: e["id"])}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(doc, f, indent=1)
            os.chmod(tmp, 0o644)                        # mkstemp creates 0600; a baseline is an ordinary build artefact
            os.replace(tmp, self.path)                  # readers see the old or the new file, never a partial one
        except BaseException:
            pathlib.Path(tmp).unlink(missing_ok=True)   # our own temp file
            raise
        return {"nodes": len(graph.nodes), "edges": len(graph.edges), "path": str(self.path)}

    def sync(self, graph, fresh):
        try:
            old, _ = self.read()
            on, oe = set(old.nodes), set(old.edges)
        except BaselineMissing:
            on = oe = set()
        stats = self.write_full(graph, fresh)
        return {**stats, "nodes_deleted": len(on - set(graph.nodes)), "edges_deleted": len(oe - set(graph.edges))}

    def snapshot(self):
        doc = self._load()
        return {n["id"] for n in doc["nodes"]}, {e["id"] for e in doc["edges"]}
