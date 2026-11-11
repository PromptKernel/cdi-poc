"""Baseline graph stores. One interface, two implementations: a JSON file (default, no server) and Neo4j (optional).

A stored baseline is the linked graph plus a freshness record: the commit id of every logical repo it was built from, when and how it was
built, and the store SCHEMA VERSION. A reader that finds a different schema version refuses the baseline (BaselineSchemaMismatch) so the
caller rebuilds it instead of analysing against a graph it may misread.

Pull-request runs only call `read`/`snapshot`; they never write."""
from __future__ import annotations
import abc, datetime, pathlib
from cdi.linker.graphio import Graph

SCHEMA_VERSION = 1        # bump when the stored graph or freshness layout changes incompatibly


class StoreError(Exception):
    pass


class BaselineMissing(StoreError):
    """No baseline exists in the store (nothing written yet, file absent, or an empty graph)."""


class BaselineSchemaMismatch(StoreError):
    """A baseline exists but was written with another schema version; rebuild it with the baseline pipeline."""
    def __init__(self, found, expected=SCHEMA_VERSION, where=""):
        self.found, self.expected = found, expected
        super().__init__(f"baseline{' ' + where if where else ''} has schema version {found!r}, this tool reads version {expected}; rebuild the baseline")


def make_freshness(graph: Graph, commits, mode, from_commit=None, to_commit=None):
    return {"schema_version": SCHEMA_VERSION, "commits": dict(commits),
            "loaded_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"), "mode": mode,
            "from_commit": from_commit, "to_commit": to_commit, "counts": {"nodes": len(graph.nodes), "edges": len(graph.edges)}}


class GraphStore(abc.ABC):
    """read() -> (Graph, freshness); write_full replaces everything; sync makes the store equal to a graph; snapshot() -> (node ids, edge ids)."""
    kind: str = ""

    @abc.abstractmethod
    def read(self) -> tuple[Graph, dict]:
        """Raises BaselineMissing or BaselineSchemaMismatch. Never writes."""

    @abc.abstractmethod
    def write_full(self, graph: Graph, fresh: dict) -> dict: ...

    @abc.abstractmethod
    def sync(self, graph: Graph, fresh: dict) -> dict: ...

    @abc.abstractmethod
    def snapshot(self) -> tuple[set, set]: ...

    def describe(self) -> str:
        return self.kind

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


DEFAULT_JSON_PATH = "out/baseline.json"


def open_store(cfg, kind=None, path=None, root=None, **kw) -> GraphStore:
    """kind: 'json' | 'neo4j' (default: cfg['store']); path: JSON file override (relative paths resolve against the repository root)."""
    kind = {"files": "json"}.get(kind, kind) or cfg["store"]
    if kind == "json":
        from .json_store import JsonStore
        p = pathlib.Path(path or cfg["graph"].get("json", {}).get("path") or DEFAULT_JSON_PATH)
        base = pathlib.Path(root or cfg.get("root") or ".")
        return JsonStore(p if p.is_absolute() else base / p)
    if kind == "neo4j":
        from .neo4j_store import Neo4jStore
        return Neo4jStore.from_config(cfg, **kw)
    raise StoreError(f"unknown store {kind!r} (json | neo4j)")
