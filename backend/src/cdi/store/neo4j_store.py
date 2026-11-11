"""Neo4j baseline store (optional). Wraps cdi.graph (Cypher load/query); `neo4j` is imported only when this store is opened."""
from __future__ import annotations
from . import SCHEMA_VERSION, BaselineMissing, BaselineSchemaMismatch, GraphStore


class Neo4jStore(GraphStore):
    kind = "neo4j"

    def __init__(self, driver, db, batch=500, uri=""):
        self.driver, self.db, self.batch, self.uri = driver, db, batch, uri

    @classmethod
    def from_config(cls, cfg, wait=90):
        from cdi.graph.load_neo4j import connect
        driver, db = connect(cfg, wait=wait)
        return cls(driver, db, cfg["graph"]["load"]["batch_size"], cfg["graph"]["neo4j"]["uri"])

    def describe(self):
        return f"neo4j:{self.uri}/{self.db}"

    def read(self):
        from cdi.graph import store as S
        g, fresh = S.read_graph(self.driver, self.db)
        if not fresh or not g.nodes:
            raise BaselineMissing("Neo4j holds no baseline graph")
        if fresh.get("schema_version") != SCHEMA_VERSION:
            raise BaselineSchemaMismatch(fresh.get("schema_version"), where="in Neo4j")
        return g, fresh

    def write_full(self, graph, fresh):
        from cdi.graph import store as S
        return S.write_full(self.driver, self.db, graph, fresh, self.batch)

    def sync(self, graph, fresh):
        from cdi.graph import store as S
        return S.sync(self.driver, self.db, graph, fresh, self.batch)

    def snapshot(self):
        from cdi.graph import store as S
        return S.snapshot(self.driver, self.db)

    def close(self):
        self.driver.close()
