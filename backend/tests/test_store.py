"""GraphStore contract (JSON store always; Neo4j store when NEO4J_PASSWORD is set), schema-version and per-repo-commit rules, factory."""
import json, os, pathlib
import pytest
from helpers import edge, graph, node
from conftest import FIXTURE_CONFIG
from cdi import store as S
from cdi.linker.graphio import load_config
from cdi.store.json_store import JsonStore

NEO = bool(os.environ.get("NEO4J_PASSWORD"))


def sample_graph():
    a, b, c = node("web", "UI_COMPONENT", "A", "a.ts"), node("api", "API_ENDPOINT", "B", "b.cs"), node("db", "SQL_PROC", "dbo.C", "c.sql")
    g = graph([a, b, c], [edge("CALLS", a, b, repo="web", file="a.ts"), edge("CALLS_PROCEDURE", b, c, repo="api", file="b.cs", line=4)],
              commits={"web": "1" * 40, "api": "2" * 40, "db": "3" * 40})
    return g


@pytest.fixture(params=["json"] + (["neo4j"] if NEO else []))
def st(request, tmp_path):
    if request.param == "json":
        yield JsonStore(tmp_path / "base.json")
        return
    cfg = load_config(FIXTURE_CONFIG)
    s = S.open_store(cfg, "neo4j", wait=20)
    s.write_full(graph([node("x", "METHOD", "tmp", "x.cs")], [], commits={"x": "0" * 40}), S.make_freshness(sample_graph(), {"x": "0" * 40}, "full"))
    yield s
    s.close()


def test_read_of_an_empty_store_is_baseline_missing(tmp_path):
    with pytest.raises(S.BaselineMissing):
        JsonStore(tmp_path / "none.json").read()


def test_write_full_then_read_roundtrips_graph_and_freshness(st):
    g = sample_graph()
    fresh = S.make_freshness(g, g.commits, "full", to_commit="f" * 40)
    st.write_full(g, fresh)
    g2, f2 = st.read()
    assert set(g2.nodes) == set(g.nodes) and set(g2.edges) == set(g.edges)
    assert f2["commits"] == {"web": "1" * 40, "api": "2" * 40, "db": "3" * 40}      # per-repo commit ids
    assert f2["schema_version"] == S.SCHEMA_VERSION and f2["mode"] == "full" and f2["counts"] == {"nodes": 3, "edges": 2}
    assert g2.commits == f2["commits"]
    assert {k: g2.edges[k] for k in g.edges} == g.edges


def test_sync_removes_what_is_gone_and_reports_it(st):
    g = sample_graph()
    st.write_full(g, S.make_freshness(g, g.commits, "full"))
    g.nodes.pop("db:sql_proc:dbo.C")
    for eid in [i for i, e in g.edges.items() if e["target"] == "db:sql_proc:dbo.C"]:
        g.edges.pop(eid)
    res = st.sync(g, S.make_freshness(g, g.commits, "incremental", "a" * 40, "b" * 40))
    assert res["nodes_deleted"] == 1 and res["edges_deleted"] == 1
    g2, f2 = st.read()
    assert set(g2.nodes) == set(g.nodes) and f2["mode"] == "incremental" and f2["from_commit"] == "a" * 40


def test_snapshot_lists_ids_and_read_does_not_change_the_store(st):
    g = sample_graph()
    st.write_full(g, S.make_freshness(g, g.commits, "full"))
    before = st.snapshot()
    st.read(); st.read()
    assert st.snapshot() == before and before == (set(g.nodes), set(g.edges))


# ---- JSON store specifics ------------------------------------------------------------------------------------------------------------

def test_json_file_layout_has_schema_version_and_per_repo_commits(tmp_path):
    g = sample_graph()
    s = JsonStore(tmp_path / "out" / "b.json")
    s.write_full(g, S.make_freshness(g, g.commits, "full"))
    doc = json.loads((tmp_path / "out" / "b.json").read_text())
    assert doc["schema_version"] == S.SCHEMA_VERSION and doc["freshness"]["commits"] == g.commits
    assert [n["id"] for n in doc["nodes"]] == sorted(n["id"] for n in doc["nodes"])               # stable, diff-friendly order
    assert not list((tmp_path / "out").glob("*.tmp")), "no temp file is left behind"


def test_reading_never_writes(tmp_path):
    g = sample_graph()
    s = JsonStore(tmp_path / "b.json")
    s.write_full(g, S.make_freshness(g, g.commits, "full"))
    raw, mtime = s.path.read_bytes(), s.path.stat().st_mtime_ns
    s.read(); s.snapshot()
    assert s.path.read_bytes() == raw and s.path.stat().st_mtime_ns == mtime


@pytest.mark.parametrize("version", [0, 2, None, "1"])
def test_other_schema_versions_are_rejected(tmp_path, version):
    g = sample_graph()
    s = JsonStore(tmp_path / "b.json")
    s.write_full(g, S.make_freshness(g, g.commits, "full"))
    doc = json.loads(s.path.read_text())
    doc["schema_version"] = version
    if version is None:
        doc.pop("schema_version")
    s.path.write_text(json.dumps(doc))
    with pytest.raises(S.BaselineSchemaMismatch, match="rebuild the baseline") as ei:
        s.read()
    assert ei.value.found == version and ei.value.expected == S.SCHEMA_VERSION


def test_a_baseline_without_commit_ids_or_with_garbage_is_refused(tmp_path):
    g = sample_graph()
    s = JsonStore(tmp_path / "b.json")
    s.write_full(g, S.make_freshness(g, g.commits, "full"))
    doc = json.loads(s.path.read_text()); doc["freshness"]["commits"] = {}
    s.path.write_text(json.dumps(doc))
    with pytest.raises(S.StoreError, match="no per-repo commit ids"):
        s.read()
    s.path.write_text("{not json")
    with pytest.raises(S.StoreError, match="not valid JSON"):
        s.read()


def test_failed_write_keeps_the_previous_baseline(tmp_path, monkeypatch):
    g = sample_graph()
    s = JsonStore(tmp_path / "b.json")
    s.write_full(g, S.make_freshness(g, g.commits, "full"))
    before = s.path.read_bytes()
    monkeypatch.setattr(json, "dump", lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        s.write_full(g, S.make_freshness(g, g.commits, "full"))
    assert s.path.read_bytes() == before and not list(tmp_path.glob("*.tmp"))


def test_sync_on_an_empty_store_behaves_like_write_full(tmp_path):
    g = sample_graph()
    s = JsonStore(tmp_path / "b.json")
    res = s.sync(g, S.make_freshness(g, g.commits, "incremental"))
    assert res["nodes_deleted"] == 0 and set(s.read()[0].nodes) == set(g.nodes)


# ---- factory -------------------------------------------------------------------------------------------------------------------------------

def test_json_is_the_default_store_and_path_resolves_against_the_repo_root(tmp_path):
    cfg = load_config(FIXTURE_CONFIG, environ={})
    s = S.open_store(cfg)
    assert s.kind == "json" and s.path == pathlib.Path(cfg["root"]) / "out/baseline.json"
    assert S.open_store(cfg, path="rel/x.json", root=tmp_path).path == tmp_path / "rel/x.json"
    assert S.open_store(cfg, "files").kind == "json"                                   # legacy alias
    assert S.open_store(cfg, path=str(tmp_path / "abs.json")).path == tmp_path / "abs.json"


def test_config_selects_the_store_and_the_path(tmp_path):
    cfg = load_config(FIXTURE_CONFIG, environ={"CDI__graph__json__path": "elsewhere/b.json"})
    assert S.open_store(cfg).path == pathlib.Path(cfg["root"]) / "elsewhere/b.json"
    cfg = load_config(FIXTURE_CONFIG, environ={"CDI__graph__store": "neo4j"})
    assert cfg["store"] == "neo4j"
    with pytest.raises(S.StoreError, match="unknown store"):
        S.open_store(cfg, "sqlite")


def test_the_json_store_needs_no_neo4j_driver(monkeypatch):
    import builtins, sys
    real = builtins.__import__
    def deny(name, *a, **k):
        if name.split(".")[0] == "neo4j":
            raise ImportError("neo4j not installed")
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", deny)
    for m in [m for m in sys.modules if m.startswith("cdi.store.json_store")]:
        monkeypatch.delitem(sys.modules, m)
    cfg = load_config(FIXTURE_CONFIG, environ={})
    assert S.open_store(cfg).kind == "json"


def test_baseline_cli_full_then_incremental_on_the_json_store_equals_a_full_rebuild(tmp_path_factory, monkeypatch):
    """No Neo4j anywhere: `baseline full` writes the JSON store, `baseline incremental` syncs it, and the result equals a fresh full build."""
    from conftest import Project
    from cdi.pipeline import baseline as B
    p = Project(tmp_path_factory.mktemp("jsoninc"))
    monkeypatch.chdir(p.path)
    cfgf = str(p.path / ".cdi/config.yml")
    B.main(["full", "--config", cfgf, "--out", "out/g1"])
    st = JsonStore(p.path / "out/baseline.json")
    base_commits = st.read()[1]["commits"]
    f = p.path / "samples/db/synthetic/procedures/spGetAllEmployees.sql"
    f.write_text(f.read_text().replace("ORDER BY EmployeeID;", "WHERE Name <> ''\n    ORDER BY EmployeeID;"))
    p.commit_all("edit proc")
    B.main(["incremental", "--from", "HEAD~1", "--to", "HEAD", "--config", cfgf, "--out", "out/g2"])
    g_inc, f_inc = st.read()
    assert f_inc["mode"] == "incremental" and f_inc["commits"]["db"] != base_commits["db"] and f_inc["commits"]["web"] == base_commits["web"]
    B.main(["full", "--config", cfgf, "--out", "out/g3", "--store-path", "out/rebuild.json"])
    g_full, _ = JsonStore(p.path / "out/rebuild.json").read()
    assert B.compare_graphs(g_inc, g_full)["nodes_only_in_a"] == [] and set(g_inc.edges) == set(g_full.edges) and set(g_inc.nodes) == set(g_full.nodes)
    with pytest.raises(SystemExit, match="no baseline"):
        B.main(["incremental", "--from", "HEAD~1", "--config", cfgf, "--store-path", "out/absent.json"])


@pytest.mark.skipif(not NEO, reason="NEO4J_PASSWORD not set")
def test_neo4j_store_rejects_another_schema_version():
    from cdi.graph import store as GS
    cfg = load_config(FIXTURE_CONFIG)
    with S.open_store(cfg, "neo4j", wait=20) as s:
        g = sample_graph()
        fresh = S.make_freshness(g, g.commits, "full")
        s.write_full(g, {**fresh, "schema_version": S.SCHEMA_VERSION + 1})
        with pytest.raises(S.BaselineSchemaMismatch):
            s.read()
        s.write_full(g, fresh)
        assert s.read()[1]["schema_version"] == S.SCHEMA_VERSION
