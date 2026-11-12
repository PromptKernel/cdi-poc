"""End-to-end impact analysis on the synthetic scenarios (tmp git copy of the sample; baseline built in memory, no Neo4j)."""
import pathlib, re
import pytest
from conftest import ROOT, BACKEND, Project, sh, make_branch
from cdi.eval.scenarios import load_scenarios
from conftest import FIXTURE_SCENARIOS
SCENARIOS = load_scenarios(FIXTURE_SCENARIOS)
from cdi.impact import engine, report
from cdi.linker.graphio import load_config
from cdi.pipeline import baseline as B
from cdi.pipeline.scanrun import ScanRunner


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    p = Project(tmp_path_factory.mktemp("scen"))
    cfg = load_config(p.path / ".cdi/config.yml")
    runner = ScanRunner(BACKEND, p.path / ".cdi/config.yml", p.path / "out/work")
    _, _, g, meta = B.full(runner, p.path, cfg)
    fresh = {"commits": meta["commits"], "loaded_at": "test", "mode": "full"}
    for name, edits in SCENARIOS.items():
        make_branch(p, name, edits)
    return p, runner, g, fresh


def run(world, branch, **kw):
    p, runner, g, fresh = world
    n_before = (len(g.nodes), len(g.edges))
    res = engine.analyze(p.path, BACKEND, p.path / ".cdi/config.yml", "main", branch, g, kw.get("fresh", fresh), name=branch, runner=runner)
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
    # the SQL test is tied to the removed proc by BOTH an annotation and a static reference: ranked as annotation-based, path flagged as broken
    (t,) = [t for t in res["tests"] if t["name"].endswith("counts employees per department")]
    assert t["mapping"] == "annotation" and set(t["mapped_by"]) == {"annotation", "static-reference"} and t["broken_by_pr"]
    # introduced items are in C1 only, not repeated as "pre-existing" in C2
    assert o["unresolved_own"] == []
    md = report.render(res)
    c2 = md[md.index("### C2."):md.index("### C3.")]
    assert "_None._" in c2
    # hops read in stored edge direction with node kinds, so a caller is never shown as being called by the callee
    assert "DATA_ACCESS_METHOD `ASPCoreWithAngular.Synthetic.DataAccess.DepartmentDataAccess.ReadHeadcount()` → SQL_REF `dbo.spGetDepartmentHeadcount`" in md
    assert "BROKEN BY THIS PR" in md
    # C3 names the screen above the unresolved (config-built) request
    assert "screen(s) that call it: DepartmentReportComponent" in md
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
    assert o["attr_changes"] == [{"attr": "route_normalized", "before": "api/Employee/Index", "after": "api/Employee/List"},
                                 {"attr": "route_template", "before": "api/Employee/Index", "after": "api/Employee/List"}]
    assert "Declared attributes changed" in report.render(res)


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
        f = path / ".cdi/config.yml"
        f.write_text(f.read_text() + "limits: {max_depth_downstream: 3}\n")
    p = Project(tmp_path_factory.mktemp("depth"), tweak)
    cfg = load_config(p.path / ".cdi/config.yml")
    runner = ScanRunner(BACKEND, p.path / ".cdi/config.yml", p.path / "out/work")
    _, _, g, meta = B.full(runner, p.path, cfg)
    make_branch(p, "pr-a-sp-body", SCENARIOS["pr-a-sp-body"])
    res = engine.analyze(p.path, BACKEND, p.path / ".cdi/config.yml", "main", "pr-a-sp-body", g, {"commits": meta["commits"], "loaded_at": "t", "mode": "full"}, runner=runner)
    o = obj(res, "dbo.spGetAllEmployees")
    assert o["depth"]["downstream_limit"] == 3 and o["depth"]["downstream_truncated"] and o["depth"]["downstream_stopped_at"]
    assert "FetchEmployeeComponent" not in {c["name"] for c in o["consumers"].get("screen", [])}, "the screen is beyond depth 3"
    md = report.render(res)
    assert "stopped at the depth limit (3)" in md and "NOT listed" in md


def test_report_wording_follows_the_synthetic_flag_not_a_fixed_claim(world):
    p, runner, g, fresh = world
    res = run(world, "pr-a-sp-body", fresh=fresh)
    md = report.render(res)
    for phrase in ("small synthetic", "synthetic-extended", "this small synthetic sample"):
        assert phrase not in md
    assert res["meta"]["synthetic_notice"] is True and "flagged synthetic by this repository's configuration" in md
    res["meta"]["synthetic_notice"] = False
    md2 = report.render(res)
    assert "flagged synthetic" not in md2 and "Static-analysis evidence only" in md2 and "(measured on this repository and machine only)" in md2


def test_older_target_warning_only_when_relevant_files_moved_on_the_target(world):
    p, runner, g, fresh = world
    # a README-only commit on main after the branch point must not produce the warning (the earlier test already moved a scanned file; use a fresh branch point)
    make_branch(p, "pr-h-before-docs", {"samples/db/synthetic/procedures/spGetCityList.sql": lambda t: t + "-- pr change\n"}, base="main")
    (p.path / "README.md").write_text("docs only\n")
    p.commit_all("docs only on main")
    res = run(world, "pr-h-before-docs", fresh={**fresh, "commits": {r: p.head_for(f"samples/{r}") for r in ("web", "api", "db")}})
    assert not any("OLDER target" in w for w in res["meta"]["warnings"]), res["meta"]["warnings"]
    (p.path / "samples/web/src/app/services/employee.service.ts").write_text((p.path / "samples/web/src/app/services/employee.service.ts").read_text() + "\n// moved\n")
    p.commit_all("a scanned file moves on main")
    res = run(world, "pr-h-before-docs", fresh=fresh)
    w = [x for x in res["meta"]["warnings"] if "OLDER target" in x]
    assert len(w) == 1 and "samples/web/src/app/services/employee.service.ts" in w[0]


def test_pr_touching_no_analysed_file_gets_one_neutral_line_instead_of_both_staleness_warnings(world):
    p, runner, g, fresh = world
    make_branch(p, "pr-i-readme", {"README.md": lambda t: (t or "") + "note\n"}, base="main")
    make_branch(p, "pr-j-moves-main", {"samples/db/synthetic/procedures/spGetCityList.sql": lambda t: t + "-- later\n"}, base="main")
    sh(["git", "merge", "--ff-only", "pr-j-moves-main"], cwd=p.path)
    stale = {**fresh, "commits": {**fresh["commits"], "db": "0" * 40}}
    res = run(world, "pr-i-readme", fresh=stale)
    assert res["meta"]["warnings"] == [], res["meta"]["warnings"]
    assert res["meta"]["notes"] == ["main has moved since this branch; this PR does not touch analysed files."]
    md = report.render(res)
    assert "## ⚠ Warnings" not in md and "_main has moved since this branch; this PR does not touch analysed files._" in md
    assert "STALE" not in md and "OLDER" not in md
    # a PR that does touch a scanned file keeps both full warnings and no note
    res2 = run(world, "pr-a-sp-body", fresh=stale)
    assert any("STALE" in w for w in res2["meta"]["warnings"]) and any("OLDER target" in w for w in res2["meta"]["warnings"])
    assert res2["meta"]["notes"] == []
