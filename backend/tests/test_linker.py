import json, pathlib
import pytest
from linker.link import Linker, build_fragment
from linker.graphio import Graph, load_config
from helpers import node, edge, graph

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG = load_config(ROOT / "config")


def run(nodes, edges):
    return Linker(graph(nodes, edges), CFG).run()


def req(verb, tpl, repo="web"):
    return node(repo, "HTTP_REQUEST", f"{verb} {tpl}", attrs={"verb": verb, "url_template": tpl})


def ep(name, verb, route, repo="api"):
    return node(repo, "API_ENDPOINT", name, attrs={"http_method": verb, "route_template": route})


def site(r, line=7):
    caller = node("web", "UI_SERVICE_METHOD", "Svc.m", file="svc.ts", line=line)
    return caller, edge("MAKES_REQUEST", caller, r, file="svc.ts", line=line, evidence="return this._http.get(x)")


def only(lk, typ):
    return [e for e in lk.edges_out if e["type"] == typ]


# ---------- routes ----------
def test_unique_route_match_is_confirmed_with_evidence_of_the_request_site():
    r = req("GET", "api/E/Details/{}"); e1 = ep("C.Details(int)", "GET", "api/E/Details/{id}")
    caller, mk = site(r)
    (e,) = only(run([r, e1, caller], [mk]), "ROUTES_TO")
    assert (e["confidence"], e["target"], e["source_file"], e["location"]["line"], e["repo"]) == ("CONFIRMED_STATIC", e1["id"], "svc.ts", 7, "web")
    assert e["evidence"] == "return this._http.get(x)" and "reason" not in e


def test_verb_must_match():
    r = req("POST", "api/E/Create"); get_ep = ep("C.Get()", "GET", "api/E/Create"); post_ep = ep("C.Post()", "POST", "api/E/Create")
    caller, mk = site(r)
    (e,) = only(run([r, get_ep, post_ep, caller], [mk]), "ROUTES_TO")
    assert e["target"] == post_ep["id"] and e["confidence"] == "CONFIRMED_STATIC"


def test_ambiguous_exact_match_is_inferred_not_confirmed():
    r = req("GET", "api/E/x"); a = ep("A.x()", "GET", "api/E/x"); b = ep("B.x()", "GET", "api/E/x")
    caller, mk = site(r)
    es = only(run([r, a, b, caller], [mk]), "ROUTES_TO")
    assert len(es) == 2 and {e["confidence"] for e in es} == {"INFERRED"} and all("ambiguous" in e["reason"] for e in es)


def test_runtime_segment_matching_a_literal_is_inferred():
    r = req("GET", "api/E/{}"); a = ep("C.Index()", "GET", "api/E/Index")
    caller, mk = site(r)
    (e,) = only(run([r, a, caller], [mk]), "ROUTES_TO")
    assert e["confidence"] == "INFERRED" and "runtime-valued segment" in e["reason"]


def test_exact_candidates_win_over_partial_ones():
    r = req("GET", "api/E/{}"); exact = ep("C.ById(int)", "GET", "api/E/{id}"); partial = ep("C.Index()", "GET", "api/E/Index")
    caller, mk = site(r)
    (e,) = only(run([r, exact, partial, caller], [mk]), "ROUTES_TO")
    assert e["target"] == exact["id"] and e["confidence"] == "CONFIRMED_STATIC"


def test_no_matching_route_is_unresolved_with_reason_and_placeholder_node():
    r = req("GET", "api/Nope/x"); a = ep("C.Index()", "GET", "api/E/Index")
    caller, mk = site(r)
    lk = run([r, a, caller], [mk])
    (e,) = only(lk, "ROUTES_TO")
    assert e["confidence"] == "UNRESOLVED" and "no API endpoint" in e["reason"]
    (ph,) = lk.nodes_out.values()
    assert ph["kind"] == "UNRESOLVED" and ph["attrs"]["cause"] == "no_matching_route" and e["target"] == ph["id"]


def test_route_matching_reads_config():
    r = req("GET", "api/e/index"); a = ep("C.Index()", "GET", "api/E/Index")
    caller, mk = site(r)
    cfg = {**CFG, "routes": {"matching": {**CFG["routes"]["matching"], "case_sensitive": True}}}
    lk = Linker(graph([r, a, caller], [mk]), cfg).run()
    assert only(lk, "ROUTES_TO")[0]["confidence"] == "UNRESOLVED"


# ---------- sql ----------
def sqlref(name, expected="procedure"):
    return node("api", "SQL_REF", name, file=None, attrs={"expected": expected})


def test_sql_ref_resolves_case_insensitively_across_repos():
    ref = sqlref("dbo.spGetAll"); proc = node("db", "SQL_PROC", "dbo.SPGETALL", file="p.sql", line=3)
    m = node("api", "DATA_ACCESS_METHOD", "D.Get()", file="D.cs", line=30)
    call = edge("CALLS_PROCEDURE", m, ref, repo="api", file="D.cs", line=30, evidence='new SqlCommand("spGetAll", con)')
    (e,) = only(run([ref, proc, m], [call]), "RESOLVES_TO")
    assert (e["confidence"], e["target"], e["source_file"], e["location"]["line"]) == ("CONFIRMED_STATIC", proc["id"], "D.cs", 30)
    assert e["attrs"]["target_location"] == "p.sql:3" and e["attrs"]["referenced_from"] == ["api:D.cs:30"]


def test_referenced_but_not_defined_is_unresolved_not_found():
    ref = sqlref("dbo.spMissing"); m = node("api", "DATA_ACCESS_METHOD", "D.Arch()", file="D.cs", line=64)
    call = edge("CALLS_PROCEDURE", m, ref, repo="api", file="D.cs", line=64)
    lk = run([ref, m], [call])
    (e,) = only(lk, "RESOLVES_TO")
    assert e["confidence"] == "UNRESOLVED" and "no definition was found" in e["reason"] and e["source_file"] == "D.cs" and e["location"]["line"] == 64
    (ph,) = lk.nodes_out.values()
    assert ph["attrs"]["cause"] == "referenced_not_found"


def test_sql_ref_kind_must_be_compatible():
    ref = sqlref("dbo.thing", "procedure"); table = node("db", "SQL_TABLE", "dbo.thing")
    m = node("api", "METHOD", "M.x()"); call = edge("CALLS_PROCEDURE", m, ref, repo="api")
    assert only(run([ref, table, m], [call]), "RESOLVES_TO")[0]["confidence"] == "UNRESOLVED"


def test_sql_ref_with_two_definitions_is_inferred_ambiguous():
    ref = sqlref("dbo.p"); p1 = node("db", "SQL_PROC", "dbo.p", file="a.sql"); p2 = node("db2", "SQL_PROC", "dbo.p", file="b.sql")
    m = node("api", "METHOD", "M.x()"); call = edge("CALLS_PROCEDURE", m, ref, repo="api")
    es = only(run([ref, p1, p2, m], [call]), "RESOLVES_TO")
    assert len(es) == 2 and all(e["confidence"] == "INFERRED" and "ambiguous" in e["reason"] for e in es)


# ---------- tests mapping ----------
def test_annotation_is_confirmed_and_records_method():
    target = node("web", "UI_SERVICE_METHOD", "Svc.archive"); t = node("web", "TEST", "T > a", file="s.spec.ts", attrs={"test_layer": "UNIT", "covers_annotation": ["Svc.archive"]})
    (e,) = only(run([target, t], []), "TESTS")
    assert (e["confidence"], e["attrs"]["mapping_method"], e["target"]) == ("CONFIRMED_STATIC", "annotation", target["id"])


def test_annotation_pointing_nowhere_is_unresolved():
    t = node("web", "TEST", "T > a", attrs={"covers_annotation": ["Nope.x"]})
    (e,) = only(run([t], []), "TESTS")
    assert e["confidence"] == "UNRESOLVED" and "matches no scanned node" in e["reason"]


def test_ts_file_convention_is_inferred_and_skips_annotated_duplicates():
    m1 = node("web", "UI_SERVICE_METHOD", "S.a", file="src/s.ts"); m2 = node("web", "UI_SERVICE_METHOD", "S.b", file="src/s.ts")
    other = node("web", "UI_SERVICE_METHOD", "O.z", file="src/o.ts")
    t = node("web", "TEST", "T > t", file="src/s.spec.ts", attrs={"covers_annotation": ["S.b"], "convention_target_file": "src/s.ts"})
    es = only(run([m1, m2, other, t], []), "TESTS")
    by = {e["target"]: e for e in es}
    assert set(by) == {m1["id"], m2["id"]}, "file convention maps to the file's nodes only"
    assert by[m2["id"]]["attrs"]["mapping_method"] == "annotation" and by[m2["id"]]["confidence"] == "CONFIRMED_STATIC"
    assert by[m1["id"]]["attrs"]["mapping_method"] == "naming-convention" and by[m1["id"]]["confidence"] == "INFERRED"


def test_csharp_naming_convention():
    ctrl = node("api", "API_ENDPOINT", "App.Controllers.DepartmentController.Headcount()", file="C.cs")
    wrong = node("api", "API_ENDPOINT", "App.Controllers.OtherController.Headcount()", file="O.cs")
    t = node("api", "TEST", "X.DepartmentController_Headcount_ReturnsRows()", file="T.cs",
             attrs={"test_layer": "csharp", "method_name": "DepartmentController_Headcount_ReturnsRows", "covers_annotation": []})
    (e,) = only(run([ctrl, wrong, t], []), "TESTS")
    assert e["target"] == ctrl["id"] and e["confidence"] == "INFERRED" and e["attrs"]["mapping_method"] == "naming-convention"


def test_linker_never_confirms_without_a_reason_free_basis():
    """Property over a mixed graph: every non-CONFIRMED edge has a reason; convention edges are never CONFIRMED."""
    r = req("GET", "api/E/{}"); a = ep("C.Index()", "GET", "api/E/Index"); t = node("web", "TEST", "T > t", attrs={"convention_target_file": "f.x", "covers_annotation": ["Zzz"]})
    s = node("web", "UI_SERVICE_METHOD", "S.a", file="f.x"); caller, mk = site(r)
    for e in run([r, a, t, s, caller], [mk]).edges_out:
        assert e["confidence"] == "CONFIRMED_STATIC" or e["reason"]
        if (e.get("attrs") or {}).get("mapping_method") == "naming-convention":
            assert e["confidence"] == "INFERRED"


# ---------- integration on real scanner output ----------
@pytest.fixture(scope="module")
def real(full):
    g = Graph.from_fragments([full["web"], full["api"], full["db"]])
    return Linker(g, CFG).run(), g


def test_real_sample_routes_all_resolved_except_scanner_unresolved(real):
    lk, g = real
    ro = only(lk, "ROUTES_TO")
    assert len(ro) == 9 and all(e["confidence"] == "CONFIRMED_STATIC" for e in ro)
    assert not [n for n in g.nodes.values() if n["kind"] == "HTTP_REQUEST" and n["id"] not in {e["source"] for e in ro}]


def test_real_sample_archive_proc_is_not_found(real):
    lk, _ = real
    un = [e for e in only(lk, "RESOLVES_TO") if e["confidence"] == "UNRESOLVED"]
    assert [e["source"] for e in un] == ["api:sql_ref:dbo.spArchiveEmployee"]
    assert "spArchiveEmployee" in un[0]["reason"] and un[0]["source_file"] == "Synthetic/DataAccess/DepartmentDataAccess.cs" and un[0]["location"]["line"] == 64
    assert sum(e["confidence"] == "CONFIRMED_STATIC" for e in only(lk, "RESOLVES_TO")) == 7


def test_real_sample_unresolved_scanner_edges_are_not_linked(real):
    lk, g = real
    unresolved_targets = {e["target"] for e in g.edges.values() if e["confidence"] == "UNRESOLVED"}
    assert unresolved_targets and not ({e["source"] for e in lk.edges_out} & unresolved_targets)


def test_linker_output_validates_and_is_deterministic(real, full, tmp_path):
    from jsonschema import Draft202012Validator
    lk, g = real
    frag = build_fragment(lk)
    assert not list(Draft202012Validator(json.loads((ROOT / "schema/graph.schema.json").read_text())).iter_errors(frag))
    again = build_fragment(Linker(Graph.from_fragments([full["web"], full["api"], full["db"]]), CFG).run())
    assert json.dumps(frag, sort_keys=True) == json.dumps(again, sort_keys=True)
