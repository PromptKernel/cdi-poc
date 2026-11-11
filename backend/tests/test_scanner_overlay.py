"""--only overlays: nodes are emitted only for the changed files, but edges from them to symbols in UNCHANGED files are still emitted."""

def ids(frag):
    return {n["id"] for n in frag["nodes"]}


def test_roslyn_overlay_keeps_edges_to_unchanged_files(project, full):
    _, ov = project.scan("api", "ov_api.json", only=["Controllers/EmployeeController.cs"])
    assert ov["overlay"] is True and ov["overlay_files"] == ["Controllers/EmployeeController.cs"]
    assert {n["file"] for n in ov["nodes"] if n.get("file")} == {"Controllers/EmployeeController.cs"}
    assert {e["source_file"] for e in ov["edges"]} == {"Controllers/EmployeeController.cs"}
    calls = [e for e in ov["edges"] if e["type"] == "CALLS"]
    assert len(calls) == 6, "controller -> IEmployee edges (6 actions) must be emitted"
    target_ids = {e["target"] for e in calls}
    assert target_ids.isdisjoint(ids(ov)), "targets live in Interfaces/IEmployee.cs, which is unchanged and not emitted"
    # ...and every one of those target ids resolves in the baseline
    assert target_ids <= ids(full["api"])
    # edges evidenced in unchanged files are NOT re-emitted
    assert not any(e["source_file"].startswith("DataAccess/") for e in ov["edges"])


def test_roslyn_overlay_edge_ids_match_baseline(project, full):
    _, ov = project.scan("api", "ov_api2.json", only=["Synthetic/Services/DepartmentReportService.cs"])
    base_edges = {e["id"] for e in full["api"]["edges"]}
    assert ov["edges"] and {e["id"] for e in ov["edges"]} <= base_edges


def test_tsmorph_overlay_keeps_edges_to_unchanged_files(project, full):
    f = "src/app/fetch-employee/fetch-employee.component.ts"
    _, ov = project.scan("web", "ov_web.json", only=[f])
    assert ov["overlay"] is True
    assert {n["file"] for n in ov["nodes"] if n.get("file")} == {f}
    calls = [e for e in ov["edges"] if e["type"] == "CALLS"]
    assert {e["target"].split(":", 2)[2] for e in calls} == {"EmployeeService.getEmployees", "EmployeeService.deleteEmployee"}
    assert not ({e["target"] for e in calls} & ids(ov)), "service methods are in an unchanged file"
    assert {e["target"] for e in ov["edges"]} - ids(ov) <= ids(full["web"])
    # the model type lives in src/models/employee.ts (unchanged): USES_TYPE edge present, node not emitted
    uses = [e for e in ov["edges"] if e["type"] == "USES_TYPE"]
    assert uses and all(e["target"] not in ids(ov) and e["target"] in ids(full["web"]) for e in uses)


def test_sql_overlay_resolves_against_unchanged_definitions(project, full):
    _, ov = project.scan("db", "ov_db.json", only=["synthetic/procedures/spGetEmployeesByDepartment.sql"])
    (e,) = [e for e in ov["edges"] if e["type"] == "READS_VIEW"]
    assert e["confidence"] == "CONFIRMED_STATIC", "view is defined in an unchanged file; must not degrade to 'not defined'"
    assert e["target"] in ids(full["db"]) and e["target"] not in ids(ov)
