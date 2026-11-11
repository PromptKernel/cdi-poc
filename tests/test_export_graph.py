"""tools/export_graph.py: shape of graph.json, files fallback, read-only Neo4j source (skipped without NEO4J_PASSWORD), copied reports and PR files."""
import json, os, pathlib, shutil
import pytest
import export_graph as X

ROOT = pathlib.Path(__file__).resolve().parents[1]
CFG = ROOT / "config"


@pytest.fixture()
def files_env(full, tmp_path):
    """A temp 'out' layout built from the real scanners' output (the `full` fixture): out/graph, a report and PR files."""
    from linker.graphio import Graph, load_config
    from linker.link import Linker, build_fragment
    cfg = load_config(CFG)
    g = Graph.from_fragments([full["web"], full["api"], full["db"]])
    linked = build_fragment(Linker(g, cfg).run())
    gd = tmp_path / "graph"; gd.mkdir()
    for r, f in full.items():
        (gd / f"{r}.json").write_text(json.dumps(f))
    (gd / "linked.json").write_text(json.dumps(linked))
    (gd / "baseline.meta.json").write_text(json.dumps({"mode": "full", "commits": {r: f["commit_id"] for r, f in full.items()}, "loaded_at": "2026-01-01T00:00:00+00:00"}))
    rep = tmp_path / "reports"; rep.mkdir()
    (rep / "report-pr-x.md").write_text("# Impact report: pr-x\n"); (rep / "report-pr-x.json").write_text(json.dumps({"meta": {"pr": "pr-x", "warnings": []}, "objects": [{"risk": {"label": "High"}}, {"risk": None}]}))
    (rep / "report-orphan.md").write_text("# no json\n")
    (rep / "pr-comment.md").write_text("<!-- m -->\nhello"); (rep / "pr-status.json").write_text(json.dumps({"simulated": True}))
    return gd, rep, tmp_path / "explorer"


def run_export(files_env, **kw):
    gd, rep, out = files_env
    return X.export(source=kw.get("source", "files"), out=str(out), graph_dir=str(gd), config=str(CFG), reports_dir=str(rep)), out


def test_graph_json_has_the_fields_the_explorer_needs(files_env, full):
    res, out = run_export(files_env)
    d = json.loads((out / "graph.json").read_text())
    assert res["source"] == "files" and d["meta"]["source"] == "files" and "SYNTHETIC" in d["meta"]["notice"]
    assert d["meta"]["counts"] == {"nodes": len(d["nodes"]), "edges": len(d["edges"])} and d["meta"]["repos"]["api"] == {"path": "samples/api", "kind": "api"}
    assert d["meta"]["baseline"]["commits"].keys() == {"web", "api", "db"}
    assert set(d["nodes"][0]) == {"id", "kind", "name", "repo", "file", "line", "end_line", "synthetic", "attrs"}
    e = d["edges"][0]
    assert set(e) == {"id", "type", "source", "target", "confidence", "source_file", "line", "column", "commit_id", "repo", "synthetic", "reason", "evidence", "analysis_method", "attrs"}
    assert all(len(x["commit_id"]) == 40 and x["line"] >= 1 for x in d["edges"])
    ids = {n["id"] for n in d["nodes"]}
    assert all(x["source"] in ids and x["target"] in ids for x in d["edges"]), "no dangling edges in the export"


def test_every_unresolved_edge_exports_its_reason_and_synthetic_flag_is_a_boolean(files_env):
    _, out = run_export(files_env)
    d = json.loads((out / "graph.json").read_text())
    unres = [e for e in d["edges"] if e["confidence"] == "UNRESOLVED"]
    assert unres and all(e["reason"] for e in unres)
    assert all(isinstance(e["synthetic"], bool) for e in d["edges"]) and all(isinstance(n["synthetic"], bool) for n in d["nodes"])
    assert {e["confidence"] for e in d["edges"]} == {"CONFIRMED_STATIC", "INFERRED", "UNRESOLVED"}
    assert any(n["kind"] == "UNRESOLVED" for n in d["nodes"]) and any(e["synthetic"] for e in d["edges"])


def test_export_is_deterministic_apart_from_the_timestamp(files_env):
    _, out = run_export(files_env)
    a = json.loads((out / "graph.json").read_text()); a["meta"].pop("generated_at")
    _, out2 = run_export(files_env)
    b = json.loads((out2 / "graph.json").read_text()); b["meta"].pop("generated_at")
    assert a == b


def test_reports_and_pr_files_are_copied_and_indexed(files_env):
    res, out = run_export(files_env)
    idx = json.loads((out / "reports/index.json").read_text())["reports"]
    assert [r["name"] for r in idx] == ["orphan", "pr-x"] and res["reports"] == 2
    pr = {r["name"]: r for r in idx}["pr-x"]
    assert pr["summary"] == {"objects": 2, "pr": "pr-x", "labels": ["High"], "warnings": 0} and (out / pr["md"]).read_text().startswith("# Impact report")
    assert {r["name"]: r for r in idx}["orphan"]["json"] is None
    prx = json.loads((out / "pr/index.json").read_text())
    assert prx == {"comment": "pr/pr-comment.md", "status": "pr/pr-status.json"} and (out / "pr/pr-comment.md").read_text().endswith("hello")


def test_missing_pr_files_and_reports_are_tolerated(files_env):
    gd, rep, out = files_env
    for f in list(rep.iterdir()):
        f.unlink()                                       # temp dir created by this test only
    res, out = run_export(files_env)
    assert res["reports"] == 0 and res["pr_comment"] is False
    assert json.loads((out / "pr/index.json").read_text()) == {"comment": None, "status": None}


def test_export_never_deletes_existing_files(files_env):
    gd, rep, out = files_env
    run_export(files_env)
    stale = out / "reports" / "report-old.md"; stale.write_text("old")
    run_export(files_env)
    assert stale.exists(), "the exporter overwrites but never removes files"
    assert "old" not in [r["name"] for r in json.loads((out / "reports/index.json").read_text())["reports"]], "the index lists only what this run copied"


def test_no_scan_files_is_a_clear_error(tmp_path):
    with pytest.raises(SystemExit, match="no scan/linker files"):
        X.export(source="files", out=str(tmp_path / "o"), graph_dir=str(tmp_path / "none"), config=str(CFG), reports_dir=str(tmp_path))


def test_auto_falls_back_to_files_when_no_password(files_env, monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    res, _ = run_export(files_env, source="auto")
    assert res["source"] == "files"
    with pytest.raises(SystemExit, match="NEO4J_PASSWORD"):
        run_export(files_env, source="neo4j")


@pytest.mark.skipif(not os.environ.get("NEO4J_PASSWORD"), reason="NEO4J_PASSWORD not set")
def test_neo4j_source_is_read_only_and_matches_the_stored_graph(files_env):
    from graph.load_neo4j import connect
    from graph import store
    from linker.graphio import load_config
    drv, db = connect(load_config(CFG), wait=10)
    before = store.snapshot(drv, db)
    res, out = run_export(files_env, source="neo4j")
    after = store.snapshot(drv, db)
    drv.close()
    d = json.loads((out / "graph.json").read_text())
    assert res["source"] == "neo4j" and before == after, "the export must not modify the store"
    assert {n["id"] for n in d["nodes"]} == before[0] and {e["id"] for e in d["edges"]} == before[1]
    assert d["meta"]["baseline"]["mode"] in ("full", "incremental") and d["meta"]["baseline"]["loaded_at"]
