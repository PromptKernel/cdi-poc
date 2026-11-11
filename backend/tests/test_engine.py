import pytest
from impact import engine, traverse as T
from helpers import node, edge, graph


def chain(n=6, conf="CONFIRMED_STATIC"):
    ns = [node("r", "METHOD", f"N{i}") for i in range(n)]
    return ns, graph(ns, [edge("CALLS", ns[i], ns[i + 1], conf, line=i + 1) for i in range(n - 1)])


def test_downstream_is_reverse_and_upstream_is_forward():
    ns, g = chain(4)
    cons, _, _ = T.reach_ex(g, ns[3]["id"], "reverse", 10)       # consumers of N3 are N2, N1, N0
    deps, _, _ = T.reach_ex(g, ns[0]["id"], "forward", 10)       # N0 depends on N1, N2, N3
    assert {g.nodes[i]["name"] for i in cons} == {"N0", "N1", "N2", "N3"}
    assert {g.nodes[i]["name"] for i in deps} == {"N0", "N1", "N2", "N3"}
    assert "N0" not in {g.nodes[i]["name"] for i in T.reach_ex(g, ns[0]["id"], "reverse", 10)[0] if i != ns[0]["id"]}


def test_depth_limit_stops_traversal_and_says_so():
    ns, g = chain(6)
    best, truncated, cut = T.reach_ex(g, ns[5]["id"], "reverse", 2)
    assert {g.nodes[i]["name"] for i in best} == {"N5", "N4", "N3"} and truncated and cut == [ns[3]["id"]]
    best, truncated, cut = T.reach_ex(g, ns[5]["id"], "reverse", 5)
    assert len(best) == 6 and not truncated and cut == []
    assert not T.reach_ex(g, ns[5]["id"], "reverse", 10)[1]


def test_depth_exactly_at_chain_length_is_not_truncated():
    ns, g = chain(4)
    assert T.reach_ex(g, ns[0]["id"], "forward", 3)[1] is False
    assert T.reach_ex(g, ns[0]["id"], "forward", 2)[1] is True


def test_paths_are_returned_not_only_nodes():
    ns, g = chain(3)
    best, _, _ = T.reach_ex(g, ns[2]["id"], "reverse", 5)
    conf, path = best[ns[0]["id"]]
    assert [h["to_name"] for h in path] == ["N1", "N0"] and all(h["file"] and h["line"] for h in path)


def test_test_ranking_annotation_over_static_reference_over_convention():
    mk = lambda name, mapping, conf="CONFIRMED_STATIC", n=1: {"name": name, "mapping": mapping, "confidence": conf, "path": [0] * n}
    ts = [mk("conv", "convention", "INFERRED"), mk("static", "static-reference"), mk("annot-long-inferred", "annotation", "INFERRED", 5), mk("annot", "annotation")]
    assert [t["name"] for t in sorted(ts, key=engine.test_sort_key)] == ["annot", "annot-long-inferred", "static", "conv"]
    # an annotation mapping outranks a convention mapping even when the annotation path is the weaker one
    assert engine.test_sort_key(mk("a", "annotation", "INFERRED")) < engine.test_sort_key(mk("c", "convention", "CONFIRMED_STATIC"))


# ---------- baseline freshness ----------
TC = {"web": "aaaa1111", "api": "bbbb2222"}


def test_fresh_baseline_and_up_to_date_branch_give_no_warning():
    assert engine.freshness_warnings({"commits": dict(TC)}, TC, "t" * 40, "t" * 40) == []


def test_stale_baseline_warns_per_repo():
    w = engine.freshness_warnings({"commits": {"web": "old00000", "api": "bbbb2222"}}, TC, "m" * 40, "m" * 40)
    assert len(w) == 1 and "STALE" in w[0] and "'web'" in w[0] and "old00000"[:8] in w[0] and "aaaa1111" in w[0]


def test_pr_based_on_older_target_warns():
    w = engine.freshness_warnings({"commits": dict(TC)}, TC, "1" * 40, "2" * 40)
    assert len(w) == 1 and "OLDER target" in w[0] and "11111111" in w[0] and "22222222" in w[0]


def test_missing_freshness_record_warns():
    assert "No baseline freshness record" in engine.freshness_warnings(None, TC, "m", "m")[0]


# ---------- graph delta ----------
def test_graph_delta_classifies_added_removed_moved_changed():
    a, b, c = (node("r", "METHOD", x) for x in "abc")
    e_same = edge("CALLS", a, b, line=1); e_gone = edge("CALLS", a, c, line=2)
    e_moved_old = edge("CALLS", b, c, line=10); e_moved_new = edge("CALLS", b, c, line=12)
    e_conf_old = edge("CALLS", c, a, line=3); e_conf_new = {**e_conf_old, "confidence": "INFERRED", "reason": "now inferred"}
    d_node = node("r", "METHOD", "d"); e_new = edge("CALLS", a, d_node, line=5)
    base = graph([a, b, c], [e_same, e_gone, e_moved_old, e_conf_old])
    head = graph([a, b, c, d_node], [e_same, e_moved_new, e_conf_new, e_new])
    d = engine.graph_delta(base, head)
    assert d["nodes_added"] == [d_node["id"]] and d["nodes_removed"] == []
    assert d["edges_removed"] == [e_gone["id"]] and d["edges_added"] == [e_new["id"]]
    assert d["edges_moved"] == [{"from": [e_moved_old["id"]], "to": [e_moved_new["id"]]}]
    assert d["edges_changed"] == [e_conf_old["id"]]
