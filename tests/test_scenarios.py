"""End-to-end impact analysis on the synthetic scenarios (tmp git copy of the sample; baseline built in memory, no Neo4j)."""
import pathlib, re
import pytest
from conftest import ROOT, Project, sh, make_branch
from scenarios import SCENARIOS
from impact import engine, report
from linker.graphio import load_config
from pipeline import baseline as B
from pipeline.scanrun import ScanRunner


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    p = Project(tmp_path_factory.mktemp("scen"))
    cfg = load_config(p.path / "config")
    runner = ScanRunner(ROOT, p.path / "config", p.path / "out/work")
    _, _, g, meta = B.full(runner, p.path, cfg)
    fresh = {"commits": meta["commits"], "loaded_at": "test", "mode": "full"}
    for name, edits in SCENARIOS.items():
        make_branch(p, name, edits)
    return p, runner, g, fresh


def run(world, branch, **kw):
    p, runner, g, fresh = world
    n_before = (len(g.nodes), len(g.edges))
    res = engine.analyze(p.path, ROOT, p.path / "config", "main", branch, g, kw.get("fresh", fresh), name=branch, runner=runner)
    assert (len(g.nodes), len(g.edges)) == n_before, "the baseline graph object must not be modified by a PR run"
    return res


def obj(res, name_part):
    (o,) = [o for o in res["objects"] if name_part in o["name"]]
    return o


def consumer_names(o, group):
    return {c["name"] for c in o["consumers"].get(group, [])}


def test_a_stored_procedure_body_change(world):
    res = run(world, "pr-a-sp-body")
    o = obj(res, "dbo.spGetAllEmployees")
    assert (o["kind"], o["change"], o["repo"]) == ("SQL_PROC", "modified", "db") and o["synthetic"]
    assert "FetchEmployeeComponent" in consumer_names(o, "screen")
    assert "ASPCoreWithAngular.Controllers.EmployeeController.Index()" in consumer_names(o, "api_endpoint")
    # the screen is reached only through the inferred DI-dispatch hop => never CONFIRMED
    fe = [c for c in o["consumers"]["screen"] if c["name"] == "FetchEmployeeComponent"][0]
    assert fe["confidence"] == "INFERRED" and any(h["type"] == "DISPATCHES_TO" and h["confidence"] == "INFERRED" for h in fe["path"])
    assert o["risk"]["rule_id"] == "R5-inferred-path-to-screen" and o["risk"]["label"] == "Medium"
    assert res["meta"]["warnings"] == [] and res["new_unresolved"] == []
    # every hop cites file:line, method and commit
    assert all(h["file"] and h["line"] and h["method"] and len(h["commit"]) == 40 for c in o["consumers"]["screen"] for h in c["path"])


def test_b_view_change_reaches_procedure_endpoint_and_screen(world):
    res = run(world, "pr-b-view")
    o = obj(res, "dbo.vwEmployeeDepartment")
    assert o["kind"] == "SQL_VIEW" and "dbo.spGetEmployeesByDepartment" in consumer_names(o, "sql")
    assert any("DepartmentController.EmployeesIn" in n for n in consumer_names(o, "api_endpoint"))
    assert "DepartmentReportComponent" in consumer_names(o, "screen")
    assert o["risk"]["label"] == "Medium"
    # the view's own dependencies are the two tables
    assert {"dbo.tblEmployee", "dbo.tblDepartment"} <= {d["name"] for d in o["dependencies"]}


def test_c_ts_service_change_has_a_confirmed_screen(world):
    res = run(world, "pr-c-ts-service")
    o = obj(res, "EmployeeService.getEmployees")
    assert o["kind"] == "UI_SERVICE_METHOD" and not o["synthetic"]
    (s,) = o["consumers"]["screen"]
    assert s["name"] == "FetchEmployeeComponent" and s["confidence"] == "CONFIRMED_STATIC"
    assert o["risk"]["rule_id"] == "R4-confirmed-path-to-screen" and o["risk"]["label"] == "High"
    # upstream (what it depends on): the API endpoint, business methods and SQL, down to the table
    assert "dbo.tblEmployee" in {d["name"] for d in o["dependencies"]}
    # the HTTP request node is not reported as a changed object
    assert not [x for x in res["objects"] if x["kind"] == "HTTP_REQUEST"]


def test_d_dynamic_sql_change_reports_unresolved_and_no_consumers(world):
    res = run(world, "pr-d-dynamic-sql")
    o = obj(res, "dbo.spSearchEmployees")
    assert o["synthetic"] and not any(o["consumers"].values())
    assert len(o["unresolved_own"]) == 1 and o["unresolved_own"][0]["type"] == "EXECUTES_DYNAMIC_SQL"
    assert o["risk"]["rule_id"] == "R7-own-unresolved"
    md = report.render(res)
    assert "dynamic SQL" in md and "C2." in md


def test_e_deleted_procedure_shows_the_broken_callers_and_what_is_above_them(world):
    res = run(world, "pr-e-delete-proc")
    o = obj(res, "dbo.spGetDepartmentHeadcount")
    assert o["change"] == "removed" and o["risk"]["rule_id"] == "R2-removed-with-consumers"
    # the C# call site is reported as referenced-not-found, with file:line
    nfs = [u for u in res["new_unresolved"] if u["type"] == "RESOLVES_TO"]
    assert len(nfs) == 2, "one reference node on the C# side and one on the SQL-test side"
    (nf,) = [u for u in nfs if u["repo"] == "api"]
    assert nf["file"] == "Synthetic/DataAccess/DepartmentDataAccess.cs" and nf["line"] == 24
    assert "api:Synthetic/DataAccess/DepartmentDataAccess.cs:24" in nf["attrs"]["referenced_from"]      # every referencing site is recorded
    assert "spGetDepartmentHeadcount" in nf["reason"] and "no definition was found" in nf["reason"]
    # ...and the callers / endpoints above that reference are listed
    above = {x["name"] for x in nf["consumers_above"]}
    assert any("DepartmentController.Headcount" in n for n in above) and any("DepartmentDataAccess.ReadHeadcount" in n for n in above)
    # SQL-side reference (the SQL test that executes the proc) now unresolved as well
    assert any(u["type"] == "CALLS_PROCEDURE" and u["source_kind"] == "TEST" for u in res["new_unresolved"])
    # consumer paths of the removed object are flagged as broken by this PR
    assert any(c["broken_by_pr"] for g in o["consumers"].values() for c in g)
    md = report.render(res)
    assert "referenced" in md and "no definition was found" in md and "no longer holds after this PR" in md


def test_f_route_change_leaves_the_request_unmatched_and_names_the_screen(world):
    res = run(world, "pr-f-route")
    o = obj(res, "EmployeeController.Index()")
    assert o["change"] == "modified" and not o["synthetic"] and o["risk"]["rule_id"] == "R3-introduces-unresolved"
    un = [u for u in res["new_unresolved"] if u["type"] == "ROUTES_TO"]
    assert len(un) == 1 and "GET api/Employee/Index" in un[0]["source_node"] and "no API endpoint" in un[0]["reason"]
    assert un[0]["file"] == "src/app/services/employee.service.ts" and un[0]["line"] == 26
    screens = [c for c in o["consumers"]["screen"]]
    assert [c["name"] for c in screens] == ["FetchEmployeeComponent"] and screens[0]["broken_by_pr"]
    broken = [h for h in screens[0]["path"] if h.get("broken_by_pr")]
    assert broken and broken[0]["type"] == "ROUTES_TO" and broken[0]["replacement"]["confidence"] == "UNRESOLVED"


def test_tests_are_ranked_and_convention_group_is_separate(world):
    res = run(world, "pr-e-delete-proc")
    ranks = [t["rank"] for t in res["tests"]]
    assert ranks == sorted(ranks)
    names = {t["name"]: t for t in res["tests"]}
    sql_test = [t for t in res["tests"] if t["name"].endswith("counts employees per department")][0]
    assert sql_test["mapping"] in ("annotation", "static-reference") and sql_test["confidence"] == "CONFIRMED_STATIC"
    md = report.render(res)
    assert "grouped separately" in md and "over-selects" in md
    assert md.index("1. Annotation-based") < md.index("3. Naming / file-convention")


def test_report_has_the_three_sections_and_cites_evidence(world):
    md = report.render(run(world, "pr-f-route"))
    for h in ("## A. CONFIRMED paths", "## B. INFERRED paths", "## C. UNRESOLVED / not found", "## Tests to run", "## Changed files"):
        assert h in md
    assert re.search(r"via `roslyn:[a-z-]+` @[0-9a-f]{8}", md) and re.search(r"employee\.service\.ts:26", md)
    assert "PR run duration" in md and "synthetic" in md.lower()
    assert "NO risk label" not in md or "no rule fired" in md


def test_changed_file_without_a_graph_node_is_reported(world):
    p, runner, g, fresh = world
    make_branch(p, "pr-noop-comment", {"samples/api/Controllers/EmployeeController.cs": lambda t: t.replace("// For more information", "// For more info", 1)})
    res = run(world, "pr-noop-comment")
    assert res["objects"] == []
    (f,) = [f for f in res["files"] if f["path"] == "Controllers/EmployeeController.cs"]
    assert f["no_graph_node"] and "no graph node" in f["result"]
    md = report.render(res)
    assert "NO GRAPH NODE" in md


def test_unscanned_file_is_reported_as_not_scanned(world):
    p, runner, g, fresh = world
    make_branch(p, "pr-readme", {"samples/db/README.md": lambda t: t + "\nnote\n"})
    res = run(world, "pr-readme")
    (f,) = res["files"]
    assert f["scanned"] is False and "not scanned" in f["result"] and res["objects"] == []


def test_stale_baseline_and_older_target_warnings_appear_at_the_top_of_the_report(world):
    p, runner, g, fresh = world
    stale = {**fresh, "commits": {**fresh["commits"], "db": "0" * 40}}
    res = run(world, "pr-a-sp-body", fresh=stale)
    assert any("STALE" in w and "'db'" in w for w in res["meta"]["warnings"])
    md = report.render(res)
    assert md.index("## ⚠ Warnings") < md.index("## Run") < md.index("## Summary")
    # advance main after branching: the PR branch is now based on an older target
    make_branch(p, "pr-g-moves-main", {"samples/db/synthetic/procedures/spGetCityList.sql": lambda t: t + "-- later\n"}, base="main")
    sh(["git", "merge", "--ff-only", "pr-g-moves-main"], cwd=p.path)
    res2 = run(world, "pr-a-sp-body", fresh=fresh)
    assert any("OLDER target" in w for w in res2["meta"]["warnings"])
    assert any("STALE" in w and "'db'" in w for w in res2["meta"]["warnings"]), "main's db folder moved past the baseline"


def test_depth_limit_is_reported_when_a_traversal_is_cut_off(tmp_path_factory):
    def tweak(path):
        f = path / "config/graph.yml"
        f.write_text(f.read_text().replace("max_depth_downstream: 12", "max_depth_downstream: 3"))
    p = Project(tmp_path_factory.mktemp("depth"), tweak)
    cfg = load_config(p.path / "config")
    runner = ScanRunner(ROOT, p.path / "config", p.path / "out/work")
    _, _, g, meta = B.full(runner, p.path, cfg)
    make_branch(p, "pr-a-sp-body", SCENARIOS["pr-a-sp-body"])
    res = engine.analyze(p.path, ROOT, p.path / "config", "main", "pr-a-sp-body", g, {"commits": meta["commits"], "loaded_at": "t", "mode": "full"}, runner=runner)
    o = obj(res, "dbo.spGetAllEmployees")
    assert o["depth"]["downstream_limit"] == 3 and o["depth"]["downstream_truncated"] and o["depth"]["downstream_stopped_at"]
    assert "FetchEmployeeComponent" not in {c["name"] for c in o["consumers"].get("screen", [])}, "the screen is beyond depth 3"
    md = report.render(res)
    assert "stopped at the depth limit (3)" in md and "NOT listed" in md
