"""Runs only when NEO4J_PASSWORD is set and the container from graph/docker-compose.yml is reachable."""
import os, pathlib, pytest
from cdi.linker.graphio import Graph, load_config
from cdi.linker.link import Linker, build_fragment
from cdi.impact import traverse as T

ROOT = pathlib.Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(not os.environ.get("NEO4J_PASSWORD"), reason="NEO4J_PASSWORD not set")


@pytest.fixture(scope="module")
def db(full):
    from cdi.graph.load_neo4j import connect, load
    cfg = load_config(ROOT / "config")
    try:
        drv, name = connect(cfg, wait=10)
    except Exception as e:
        pytest.skip(f"neo4j not reachable: {e}")
    g = Graph.from_fragments([full["web"], full["api"], full["db"]])
    lk = Linker(g, cfg).run()
    g = Graph.from_fragments([full["web"], full["api"], full["db"], build_fragment(lk)])
    stats = load(g, drv, name, reset=True)
    yield g, drv, name, stats
    drv.close()


def test_everything_loaded_and_nothing_dropped(db):
    g, drv, name, stats = db
    assert stats["edges_skipped_missing_endpoint"] == 0
    with drv.session(database=name) as s:
        assert s.run("MATCH (n:Node) RETURN count(n) AS c").single()["c"] == len(g.nodes)
        assert s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"] == len(g.edges)


def test_loading_twice_is_idempotent(db):
    from cdi.graph.load_neo4j import load
    g, drv, name, _ = db
    load(g, drv, name)
    with drv.session(database=name) as s:
        assert s.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"] == len(g.edges)


@pytest.mark.parametrize("name_,kind,direction", [("FetchEmployeeComponent", "UI_COMPONENT", "forward"), ("dbo.tblEmployee", "SQL_TABLE", "reverse"),
                                                  ("dbo.tblDepartment", "SQL_TABLE", "reverse")])
def test_cypher_paths_equal_in_memory_paths(db, name_, kind, direction):
    from cdi.graph import neo4j_query as NQ
    g, drv, name, _ = db
    n = T.find_nodes(g, name_, [kind])[0]
    mem = {tuple(h["edge_id"] for h in p) for p in T.paths(g, n["id"], direction, 25, ("USES_TYPE",))}
    neo = {tuple(h["edge_id"] for h in p) for p in NQ.paths(drv, name, n["id"], direction, 25, ("USES_TYPE",))}
    assert mem and mem == neo
