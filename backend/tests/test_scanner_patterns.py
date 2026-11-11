"""SqlCommand patterns (Roslyn), placeholder-only URLs and per-test @covers (ts-morph)."""
import pytest

PATTERNS = {
    "ConstantField": "dbo.spGetCityList",
    "ConstantConcatenation": "dbo.spGetAllEmployees",
    "ObjectInitializer": "dbo.spGetDepartmentHeadcount",
    "CommandTextAssignment": "dbo.spGetEmployeesByDepartment",
    "TargetTypedNew": "dbo.spDeleteEmployee",
    "CtorWithInitializer": "dbo.spAddEmployee",
}


def edges_of(frag, method):
    nodes = {n["id"]: n for n in frag["nodes"]}
    return [(e, nodes[e["target"]]) for e in frag["edges"]
            if nodes[e["source"]]["name"].endswith(f"SqlPatternsDataAccess.{method}") or f"SqlPatternsDataAccess.{method}(" in nodes[e["source"]]["name"]]


@pytest.mark.parametrize("method,proc", PATTERNS.items())
def test_sqlcommand_pattern_resolves_to_procedure(full, method, proc):
    ((e, t),) = edges_of(full["api"], method)
    assert (e["type"], t["name"], e["confidence"]) == ("CALLS_PROCEDURE", proc, "CONFIRMED_STATIC")


def test_text_source_is_recorded(full):
    src = {m: edges_of(full["api"], m)[0][0]["attrs"]["text_source"] for m in PATTERNS}
    assert src["ObjectInitializer"] == "object-initializer"
    assert src["CommandTextAssignment"] == "commandtext-assignment"
    assert src["ConstantField"] == "constructor-argument"


@pytest.mark.parametrize("method,cause", [("InterpolatedSql", "dynamic_sql"), ("InlineLiteralSql", "inline_sql_not_parsed")])
def test_non_resolvable_sql_is_unresolved_with_reason(full, method, cause):
    ((e, t),) = edges_of(full["api"], method)
    assert e["type"] == "EXECUTES_DYNAMIC_SQL" and e["confidence"] == "UNRESOLVED" and e["reason"]
    assert t["kind"] == "UNRESOLVED" and t["attrs"]["cause"] == cause


def test_whole_url_placeholder_is_unresolved(full):
    nodes = {n["id"]: n for n in full["web"]["nodes"]}
    (e,) = [e for e in full["web"]["edges"]
            if e["type"] == "MAKES_REQUEST" and nodes[e["source"]]["name"] == "DepartmentReportService.exportReport"]
    assert e["confidence"] == "UNRESOLVED" and "entirely a runtime value" in e["reason"]
    assert nodes[e["target"]]["kind"] == "UNRESOLVED"


def test_no_http_request_node_consists_only_of_placeholders(full):
    for n in full["web"]["nodes"]:
        if n["kind"] == "HTTP_REQUEST":
            assert n["attrs"]["url_template"].replace("{}", "").replace("/", ""), n["name"]


def test_covers_annotations_are_per_test_not_per_file(full):
    cov = {n["name"]: n["attrs"]["covers_annotation"] for n in full["web"]["nodes"] if n["kind"] == "TEST"}
    assert cov["DepartmentReportService > should be created"] == []
    assert cov["DepartmentReportService > archive posts to the Department API"] == ["DepartmentReportService.archive"]
    assert cov["DepartmentReportComponent > is declared"] == ["DepartmentReportComponent"]   # inherited from its describe only
    # other spec files have no annotations at all
    assert all(v == [] for k, v in cov.items() if not k.startswith("DepartmentReport"))
