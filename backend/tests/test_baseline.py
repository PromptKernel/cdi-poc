"""Incremental baseline update must equal a full rebuild of the same commit (same node ids, same edge ids), linker edges included."""
import pathlib, pytest
from conftest import ROOT, BACKEND, Project, sh, GIT_ID
from cdi.linker.graphio import load_config
from cdi.pipeline import baseline as B
from cdi.pipeline.scanrun import ScanRunner


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    p = Project(tmp_path_factory.mktemp("inc"))
    cfg = load_config(p.path / "config")
    runner = ScanRunner(BACKEND, p.path / "config", p.path / "out/work")
    c0 = sh(["git", "rev-parse", "HEAD"], cwd=p.path).stdout.strip()
    frags0, linked0, g0, meta0 = B.full(runner, p.path, cfg)
    return p, cfg, runner, c0, g0, meta0


def edit(p, rel, fn):
    f = p.path / rel
    if fn is None:
        sh(["git", "rm", "-q", rel], cwd=p.path)
    else:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(fn(f.read_text() if f.exists() else ""))


def test_incremental_equals_full_after_modify_add_delete_in_all_three_repos(world):
    p, cfg, runner, c0, g0, _ = world
    edit(p, "samples/db/synthetic/procedures/spGetAllEmployees.sql", lambda t: t.replace("ORDER BY EmployeeID;", "WHERE Name <> ''\n    ORDER BY EmployeeID;"))
    edit(p, "samples/db/synthetic/procedures/spGetDepartmentHeadcount.sql", None)                       # deleted definition
    edit(p, "samples/db/synthetic/procedures/spNewReport.sql", lambda t: "CREATE PROCEDURE dbo.spNewReport\nAS\nBEGIN\n    SELECT Name FROM dbo.tblEmployee;\n    EXEC dbo.spGetCityList;\nEND\n")
    edit(p, "samples/api/Controllers/EmployeeController.cs", lambda t: t.replace('[Route("Index")]', '[Route("List")]', 1))   # breaks a frontend route
    edit(p, "samples/web/src/app/services/employee.service.ts", lambda t: t.replace("  getEmployeeById(id: number) {", "  getCount() {\n    return this._http.get(this.myAppUrl + 'Count');\n  }\n\n  getEmployeeById(id: number) {"))
    edit(p, "samples/web/src/synthetic/department-report.service.spec.ts", None)                          # deleted test file
    p.commit_all("c1")
    c1 = sh(["git", "rev-parse", "HEAD"], cwd=p.path).stdout.strip()

    base_commits = {r: f for r, f in g0.commits.items()}
    _, _, g_inc, meta = B.incremental(runner, p.path, cfg, g0, base_commits, c0, c1)
    _, _, g_full, meta_full = B.full(runner, p.path, cfg)

    diff = B.compare_graphs(g_inc, g_full)
    assert not diff["nodes_only_in_a"] and not diff["nodes_only_in_b"], diff
    assert not diff["edges_only_in_a"] and not diff["edges_only_in_b"], diff
    assert diff["counts_a"] == diff["counts_b"] and diff["counts_a"] != (len(g0.nodes), len(g0.edges))
    # per-edge commit ids are re-stamped to the folder's commit at the new revision, so they match a full build too
    assert {e["commit_id"] for e in g_inc.edges.values() if e["repo"] == "db"} == {meta_full["commits"]["db"]}
    assert g_inc.commits == g_full.commits
    # dependents of the deleted definition were re-scanned (the SQL test that referenced it)
    assert "synthetic/tests/test_spGetDepartmentHeadcount.sql" in meta["plan"]["db"]["dependents_rescanned"]


def test_linker_edges_are_fully_recomputed_not_carried_over(world):
    p, cfg, runner, c0, g0, _ = world
    c1 = sh(["git", "rev-parse", "HEAD"], cwd=p.path).stdout.strip()
    if c1 == c0:
        pytest.skip("depends on the previous test's commit")
    _, _, g_inc, _ = B.incremental(runner, p.path, cfg, g0, dict(g0.commits), c0, c1)
    ro = {e["target"]: e for e in g_inc.edges.values() if e["type"] == "ROUTES_TO" and "Index" in e["source"]}
    assert ro and all(e["confidence"] == "UNRESOLVED" for e in ro.values()), "route no longer matches after the controller route change"
    base_ro = [e for e in g0.edges.values() if e["type"] == "ROUTES_TO" and "Index" in e["source"]]
    assert base_ro and base_ro[0]["confidence"] == "CONFIRMED_STATIC"
    # SQL reference to the deleted procedure becomes 'not found'
    rs = [e for e in g_inc.edges.values() if e["type"] == "RESOLVES_TO" and e["source"].endswith("spGetDepartmentHeadcount")]
    assert rs and all(e["confidence"] == "UNRESOLVED" for e in rs)
    # the file-convention TESTS edges of the deleted spec file are gone
    assert not [n for n in g_inc.nodes.values() if n["kind"] == "TEST" and (n.get("file") or "").endswith("department-report.service.spec.ts")]
    # the new request has no endpoint
    assert any(e["type"] == "ROUTES_TO" and e["confidence"] == "UNRESOLVED" and "Count" in e["source"] for e in g_inc.edges.values())


def test_incremental_with_no_changes_equals_the_baseline(world):
    p, cfg, runner, c0, g0, _ = world
    c1 = sh(["git", "rev-parse", "HEAD"], cwd=p.path).stdout.strip()
    _, _, g_full, _ = B.full(runner, p.path, cfg)
    _, _, g_same, meta = B.incremental(runner, p.path, cfg, g_full, dict(g_full.commits), c1, c1)
    assert B.compare_graphs(g_same, g_full)["nodes_only_in_a"] == [] and B.compare_graphs(g_same, g_full)["edges_only_in_b"] == []
    assert all(not v["changed"] and not v["deleted"] for v in meta["plan"].values())


def test_freshness_metadata_records_commit_per_repo(world):
    p, cfg, runner, c0, g0, meta0 = world
    assert set(meta0["commits"]) == {"web", "api", "db"}
    for r in cfg["repos"]["repos"]:
        assert meta0["commits"][r["name"]] == sh(["git", "log", "-1", "--format=%H", "c0".replace("c0", c0), "--", r["path"]], cwd=p.path).stdout.strip()
    assert meta0["mode"] == "full" and meta0["duration_s"] >= 0


def test_equality_check_has_teeth_dependents_rescan_is_required(world, monkeypatch):
    """Mutation check: if files depending on a deleted definition are NOT re-scanned, incremental no longer equals full."""
    p, cfg, runner, c0, g0, _ = world
    c1 = sh(["git", "rev-parse", "HEAD"], cwd=p.path).stdout.strip()
    if c1 == c0:
        pytest.skip("depends on the first test's commit")
    monkeypatch.setattr(B.M, "dependents", lambda *a, **k: set())
    _, _, g_bad, _ = B.incremental(runner, p.path, cfg, g0, dict(g0.commits), c0, c1)
    _, _, g_full, _ = B.full(runner, p.path, cfg)
    d = B.compare_graphs(g_bad, g_full)
    assert d["nodes_only_in_a"] or d["nodes_only_in_b"] or d["edges_only_in_a"] or d["edges_only_in_b"]
