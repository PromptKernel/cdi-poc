import pathlib, pytest
from cdi.impact import traverse as T
from cdi.linker.graphio import Graph
from cdi.linker.link import Linker
from cdi.linker.graphio import load_config
from helpers import node, edge, graph

ROOT = pathlib.Path(__file__).resolve().parents[2]
A, B, C, D = (node("r", "METHOD", n) for n in "ABCD")


def chain_graph(c1="CONFIRMED_STATIC", c2="CONFIRMED_STATIC", c3="CONFIRMED_STATIC"):
    return graph([A, B, C, D], [edge("CALLS", A, B, c1, line=1), edge("CALLS", B, C, c2, line=2), edge("CALLS", C, D, c3, line=3)])


def names(path):
    return [h["to_name"] for h in path]


def test_forward_follows_edge_direction_and_reverse_goes_back():
    g = chain_graph()
    (fw,) = T.paths(g, A["id"], "forward")
    assert names(fw) == ["B", "C", "D"]
    (rv,) = T.paths(g, D["id"], "reverse")
    assert names(rv) == ["C", "B", "A"]


def test_hops_carry_file_line_evidence_and_commit():
    g = graph([A, B], [edge("CALLS", A, B, file="x.cs", line=42, evidence="b();")])
    (p,) = T.paths(g, A["id"], "forward")
    h = p[0]
    assert (h["file"], h["line"], h["evidence"], h["commit"], h["repo"]) == ("x.cs", 42, "b();", "a" * 40, "web")


def test_path_confidence_is_the_weakest_hop_never_upgraded():
    (p,) = T.paths(chain_graph(c2="INFERRED"), A["id"], "forward")
    assert T.path_confidence(p) == "INFERRED"
    (p,) = T.paths(chain_graph(), A["id"], "forward")
    assert T.path_confidence(p) == "CONFIRMED_STATIC"
    assert T.path_confidence([]) == "CONFIRMED_STATIC"


def test_unresolved_edges_are_not_traversed_but_reported_with_reason():
    g = chain_graph(c2="UNRESOLVED")
    (p,) = T.paths(g, A["id"], "forward")
    assert names(p) == ["B"], "traversal stops at the unresolved link"
    un = T.unresolved_in_scope(g, {A["id"], B["id"]})
    assert len(un) == 1 and un[0]["source"] == B["id"] and un[0]["reason"]
    assert T.unresolved_in_scope(g, {A["id"]}) == []   # only edges whose source is in scope


def test_cycles_do_not_loop_forever():
    g = graph([A, B, C], [edge("CALLS", A, B, line=1), edge("CALLS", B, C, line=2), edge("CALLS", C, A, line=3)])
    ps = T.paths(g, A["id"], "forward")
    assert len(ps) == 1 and names(ps[0]) == ["B", "C"]


def test_branching_gives_one_path_per_leaf():
    E = node("r", "METHOD", "E")
    g = graph([A, B, C, E], [edge("CALLS", A, B, line=1), edge("CALLS", A, C, line=2), edge("CALLS", C, E, line=3)])
    got = sorted(tuple(names(p)) for p in T.paths(g, A["id"], "forward"))
    assert got == [("B",), ("C", "E")]


def test_exclude_types_and_max_depth():
    g = graph([A, B, C], [edge("USES_TYPE", A, B, line=1), edge("CALLS", A, C, line=2)])
    assert [tuple(names(p)) for p in T.paths(g, A["id"], "forward", exclude_types=("USES_TYPE",))] == [("C",)]
    assert len(T.paths(chain_graph(), A["id"], "forward", max_depth=2)[0]) == 2


def test_reach_prefers_the_stronger_path_even_if_longer():
    # A->D direct but INFERRED; A->B->C->D all confirmed
    g = graph([A, B, C, D], [edge("CALLS", A, D, "INFERRED", line=9), edge("CALLS", A, B, line=1), edge("CALLS", B, C, line=2), edge("CALLS", C, D, line=3)])
    conf, path = T.reach(g, A["id"], "forward")[D["id"]]
    assert conf == "CONFIRMED_STATIC" and len(path) == 3


def test_reach_marks_inferred_when_only_inferred_path_exists():
    conf, path = T.reach(chain_graph(c2="INFERRED"), A["id"], "forward")[D["id"]]
    assert conf == "INFERRED"


def test_reach_excludes_unresolved_targets():
    r = T.reach(chain_graph(c2="UNRESOLVED"), A["id"], "forward")
    assert set(r) == {A["id"], B["id"]}


def test_find_nodes_exact_name_then_substring():
    g = chain_graph()
    assert [n["name"] for n in T.find_nodes(g, "A")] == ["A"]
    assert T.find_nodes(g, "r:method:C")[0]["name"] == "C"
    assert T.find_nodes(g, "zzz") == []


# ---------- on the real (synthetic) sample ----------
@pytest.fixture(scope="module")
def real(full):
    cfg = load_config(ROOT / "config")
    g = Graph.from_fragments([full["web"], full["api"], full["db"]])
    lk = Linker(g, cfg).run()
    for n in lk.nodes_out.values():
        g.nodes[n["id"]] = n
    for e in lk.edges_out:
        g.add_edge(e)
    return g


def test_real_ui_to_sql_forward_path_in_order_with_inferred_dispatch(real):
    start = T.find_nodes(real, "FetchEmployeeComponent", ["UI_COMPONENT"])[0]
    paths = T.paths(real, start["id"], "forward", exclude_types=("USES_TYPE",))
    idx = [p for p in paths if p[-1]["to_name"] == "dbo.tblEmployee" and any(h["to_name"] == "GET api/Employee/Index" for h in p)]
    assert len(idx) == 1
    assert [h["type"] for h in idx[0]] == ["CALLS", "MAKES_REQUEST", "ROUTES_TO", "CALLS", "DISPATCHES_TO", "CALLS_PROCEDURE", "RESOLVES_TO", "READS_TABLE"]
    assert T.path_confidence(idx[0]) == "INFERRED"
    assert [h["confidence"] for h in idx[0]].count("INFERRED") == 1


def test_real_reverse_from_table_reaches_the_ui_screen(real):
    tbl = T.find_nodes(real, "dbo.tblEmployee", ["SQL_TABLE"])[0]
    r = T.reach(real, tbl["id"], "reverse", exclude_types=("USES_TYPE",))
    ui = {real.nodes[i]["name"]: c for i, (c, _) in r.items() if real.nodes[i]["kind"] == "UI_COMPONENT"}
    assert {"FetchEmployeeComponent", "AddEmployeeComponent", "DepartmentReportComponent"} <= set(ui)


def test_real_forward_and_reverse_are_consistent(real):
    """If X reaches Y forwards, Y reaches X in reverse."""
    comp = T.find_nodes(real, "FetchEmployeeComponent", ["UI_COMPONENT"])[0]
    fwd = T.reach(real, comp["id"], "forward", exclude_types=("USES_TYPE",))
    for tid in (i for i in fwd if real.nodes[i]["kind"] == "SQL_TABLE"):
        assert comp["id"] in T.reach(real, tid, "reverse", exclude_types=("USES_TYPE",))


def test_real_unresolved_links_stop_traversal(real):
    # config-built route: the service method has no ROUTES_TO path to the API
    hc = T.find_nodes(real, "DepartmentReportService.getHeadcount", ["UI_SERVICE_METHOD"])[0]
    r = T.reach(real, hc["id"], "forward", exclude_types=("USES_TYPE",))
    assert not [i for i in r if real.nodes[i]["kind"] in ("API_ENDPOINT", "SQL_PROC", "SQL_TABLE")]
    assert T.unresolved_in_scope(real, r)[0]["reason"].startswith("URL part comes from runtime configuration")
    # dynamic SQL: no table reachable from GetEmployeeData
    gd = T.find_nodes(real, "ASPCoreWithAngular.DataAccess.EmployeeDataAccessLayer.GetEmployeeData(int)")[0]
    assert not [i for i in T.reach(real, gd["id"], "forward") if real.nodes[i]["kind"] in ("SQL_PROC", "SQL_TABLE")]
    # referenced but undefined proc: reaches the SQL_REF only
    ar = T.find_nodes(real, "ASPCoreWithAngular.Synthetic.DataAccess.DepartmentDataAccess.Archive(int)")[0]
    kinds = {real.nodes[i]["kind"] for i in T.reach(real, ar["id"], "forward")}
    assert "SQL_PROC" not in kinds and "SQL_REF" in kinds
