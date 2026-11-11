"""Neo4j-dependent baseline tests. Skipped cleanly when NEO4J_PASSWORD is unset. NOTE: they REPLACE the graph in the local database."""
import os, pathlib
import pytest
from conftest import ROOT, Project, sh, make_branch
from scenarios import SCENARIOS
from linker.graphio import load_config
from pipeline import baseline as B
from pipeline.scanrun import ScanRunner

pytestmark = pytest.mark.skipif(not os.environ.get("NEO4J_PASSWORD"), reason="NEO4J_PASSWORD not set")


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    from graph.load_neo4j import connect
    from graph import store
    p = Project(tmp_path_factory.mktemp("n4j"))
    cfg = load_config(p.path / "config")
    try:
        drv, db = connect(cfg, wait=10)
    except Exception as e:
        pytest.skip(f"neo4j not reachable: {e}")
    runner = ScanRunner(ROOT, p.path / "config", p.path / "out/work")
    yield p, cfg, runner, drv, db, store
    drv.close()


def test_full_replace_then_incremental_sync_equals_full_rebuild_in_neo4j(env):
    p, cfg, runner, drv, db, store = env
    c0 = sh(["git", "rev-parse", "HEAD"], cwd=p.path).stdout.strip()
    _, _, g0, meta0 = B.full(runner, p.path, cfg)
    store.write_full(drv, db, g0, store.make_freshness(g0, meta0["commits"], "full", to_commit=c0))
    stored, fresh = store.read_graph(drv, db)
    assert not B.compare_graphs(stored, g0)["nodes_only_in_a"] and stored.commits == g0.commits
    assert fresh["mode"] == "full" and fresh["loaded_at"] and fresh["commits"] == meta0["commits"]

    f = p.path / "samples/db/synthetic/procedures/spGetAllEmployees.sql"
    f.write_text(f.read_text().replace("ORDER BY EmployeeID;", "WHERE Name <> ''\n    ORDER BY EmployeeID;"))
    sh(["git", "rm", "-q", "samples/db/synthetic/procedures/spGetDepartmentHeadcount.sql"], cwd=p.path)
    p.commit_all("c1")
    c1 = sh(["git", "rev-parse", "HEAD"], cwd=p.path).stdout.strip()
    _, _, g1, meta1 = B.incremental(runner, p.path, cfg, stored, fresh["commits"], c0, c1)
    st = store.sync(drv, db, g1, store.make_freshness(g1, meta1["commits"], "incremental", c0, c1))
    assert st["nodes_deleted"] >= 1 and st["edges_deleted"] >= 1
    stored1, fresh1 = store.read_graph(drv, db)
    _, _, gfull, mfull = B.full(runner, p.path, cfg)
    d = B.compare_graphs(stored1, gfull)
    assert not any(d[k] for k in ("nodes_only_in_a", "nodes_only_in_b", "edges_only_in_a", "edges_only_in_b")), d
    assert fresh1["mode"] == "incremental" and fresh1["from_commit"] == c0 and fresh1["to_commit"] == c1 and fresh1["commits"] == mfull["commits"]
    with drv.session(database=db) as s:
        assert s.run("MATCH (n:Node) RETURN count(n) AS c").single()["c"] == len(gfull.nodes)
        assert s.run("MATCH ()-[x]->() RETURN count(x) AS c").single()["c"] == len(gfull.edges)


def test_pr_run_never_writes_to_the_baseline_graph(env):
    from impact import engine
    p, cfg, runner, drv, db, store = env
    base, fresh = store.read_graph(drv, db)
    before = store.snapshot(drv, db)
    with drv.session(database=db) as s:
        before_fresh = s.run("MATCH (f:Freshness) RETURN f.loaded_at AS t, f.commits AS c").data()
    for name in ("pr-a-sp-body", "pr-f-route"):   # (the proc deleted by the previous test is already gone on main)
        make_branch(p, name, SCENARIOS[name], base="main")
        res = engine.analyze(p.path, ROOT, p.path / "config", "main", name, base, fresh, name=name, runner=runner)
        assert res["graph_counts"]["after_pr"] != res["graph_counts"]["baseline"], "the PR changes the in-memory graph..."
    after = store.snapshot(drv, db)
    assert after == before, "...but the stored baseline (node ids and edge ids) is identical before and after PR runs"
    with drv.session(database=db) as s:
        assert s.run("MATCH (f:Freshness) RETURN f.loaded_at AS t, f.commits AS c").data() == before_fresh


def test_baseline_reads_use_a_read_only_session(env):
    """The server itself rejects writes in the session type used for PR runs."""
    import neo4j
    p, cfg, runner, drv, db, store = env
    with drv.session(database=db, default_access_mode=neo4j.READ_ACCESS) as s:
        with pytest.raises(Exception):
            s.run("CREATE (:Node {id: 'should-not-exist'})").consume()
    assert "should-not-exist" not in {i for i in store.snapshot(drv, db)[0]}
