"""The read-only API over a JSON-store baseline: endpoints, errors, auth on/off, localhost default, read-only guarantee, OpenAPI."""
import json
import pytest
from fastapi.testclient import TestClient
from helpers import edge, graph, node
from conftest import FIXTURE_CONFIG
from cdi import store as S
from cdi.api import create_app, serve
from cdi.linker.graphio import load_config
from cdi.store.json_store import JsonStore

TOKEN = "t0ken-for-tests-only"


def sample_graph():
    a, b, c = node("web", "UI_COMPONENT", "ListScreen", "a.ts"), node("api", "API_ENDPOINT", "ItemController.Index()", "b.cs"), node("db", "SQL_PROC", "dbo.spList", "c.sql")
    return graph([a, b, c], [edge("CALLS", a, b, repo="web", file="a.ts", line=3), edge("CALLS_PROCEDURE", b, c, conf="INFERRED", repo="api", file="b.cs", line=4, reason="runtime DI")],
                 commits={"web": "1" * 40, "api": "2" * 40, "db": "3" * 40})


@pytest.fixture()
def baseline(tmp_path):
    g = sample_graph()
    f = tmp_path / "baseline.json"
    JsonStore(f).write_full(g, S.make_freshness(g, g.commits, "full", to_commit="9" * 40))
    return f


@pytest.fixture()
def reports(tmp_path):
    d = tmp_path / "reports"; d.mkdir()
    (d / "report-pr-x.md").write_text("# Impact report: pr-x\n")
    (d / "report-pr-x.json").write_text(json.dumps({"meta": {"pr": "pr-x", "warnings": []}, "objects": [{"risk": {"label": "High"}}]}))
    (d / "report-orphan.md").write_text("# no json\n")
    (d / "pr-comment.md").write_text("<!-- m -->\nhello"); (d / "pr-status.json").write_text(json.dumps({"simulated": True}))
    return d


def client(baseline, reports=None, token=None, **kw):
    cfg = load_config(FIXTURE_CONFIG, environ={})
    env = {"CDI_API_TOKEN": token} if token else {}
    app = create_app(cfg, lambda: JsonStore(baseline), reports_dir=reports or baseline.parent, environ=env, **kw)
    return TestClient(app)


AUTH = {"Authorization": f"Bearer {TOKEN}"}


# ---------------------------------------------------------------- endpoints
def test_meta_reports_the_data_source_and_the_baseline_facts(baseline):
    d = client(baseline).get("/api/meta").json()
    assert d["source"] == "live-api" and d["store"] == "json" and d["counts"] == {"nodes": 3, "edges": 2}
    b = d["baseline"]
    assert b["schema_version"] == S.SCHEMA_VERSION and b["commits"] == {"web": "1" * 40, "api": "2" * 40, "db": "3" * 40} and b["loaded_at"] and b["mode"] == "full"
    assert set(d["repos"]) == {"web", "api", "db"}


def test_graph_has_the_explorer_format(baseline):
    d = client(baseline).get("/api/graph").json()
    assert set(d) == {"meta", "nodes", "edges"} and d["meta"]["source"] == "live-api" and d["meta"]["baseline"]["schema_version"] == S.SCHEMA_VERSION
    assert set(d["nodes"][0]) >= {"id", "kind", "name", "repo", "file", "line", "synthetic", "attrs"}
    assert {e["confidence"] for e in d["edges"]} == {"CONFIRMED_STATIC", "INFERRED"} and all(e["commit_id"] and e["line"] for e in d["edges"])


def test_node_search_filters_and_limits(baseline):
    c = client(baseline)
    assert [n["name"] for n in c.get("/api/nodes", params={"q": "item"}).json()] == ["ItemController.Index()"]
    assert [n["kind"] for n in c.get("/api/nodes", params={"kind": "SQL_PROC"}).json()] == ["SQL_PROC"]
    assert len(c.get("/api/nodes", params={"repo": "web"}).json()) == 1 and len(c.get("/api/nodes", params={"limit": 2}).json()) == 2
    assert c.get("/api/nodes", params={"limit": 0}).status_code == 422 and c.get("/api/nodes", params={"limit": 501}).status_code == 422


def test_node_detail_lists_both_edge_directions_and_404s(baseline):
    c = client(baseline)
    d = c.get("/api/nodes/api:api_endpoint:ItemController.Index()").json()
    assert [e["type"] for e in d["depends_on"]] == ["CALLS_PROCEDURE"] and [e["type"] for e in d["depended_on_by"]] == ["CALLS"]
    assert c.get("/api/nodes/nope").status_code == 404


def test_trace_forward_and_reverse_follow_the_edge_direction(baseline):
    c = client(baseline)
    fwd = c.get("/api/trace", params={"id": "web:ui_component:ListScreen", "direction": "forward"}).json()
    assert [h["to_name"] for h in fwd["paths"][0]] == ["ItemController.Index()", "dbo.spList"] and fwd["paths"][0][1]["confidence"] == "INFERRED"
    assert fwd["paths"][0][0]["from"] == "web:ui_component:ListScreen"        # the alias "from" is what clients see
    rev = c.get("/api/trace", params={"id": "db:sql_proc:dbo.spList", "direction": "reverse"}).json()
    assert [h["to_name"] for h in rev["paths"][0]] == ["ItemController.Index()", "ListScreen"] and not rev["truncated"]
    assert c.get("/api/trace", params={"id": "x"}).status_code == 404
    assert c.get("/api/trace", params={"id": "web:ui_component:ListScreen", "direction": "sideways"}).status_code == 422
    assert c.get("/api/trace", params={"id": "web:ui_component:ListScreen", "max_depth": 99}).status_code == 422


def test_reports_and_pr_files(baseline, reports):
    c = client(baseline, reports)
    idx = c.get("/api/reports").json()["reports"]
    assert [r["name"] for r in idx] == ["orphan", "pr-x"]
    x = idx[1]
    assert x["md"] == "/api/reports/pr-x?format=md" and x["summary"] == {"objects": 1, "pr": "pr-x", "labels": ["High"], "warnings": 0} and idx[0]["json"] is None
    assert c.get(x["md"]).text.startswith("# Impact report") and c.get(x["json"]).json()["meta"]["pr"] == "pr-x"
    assert c.get("/api/pr").json() == {"comment": "<!-- m -->\nhello", "status": {"simulated": True}}


@pytest.mark.parametrize("name", ["..%2F..%2Fetc%2Fpasswd", "a%2Fb", ".hidden", "x" * 200, "%2E%2E"])
def test_report_names_are_validated_so_no_other_file_can_be_read(baseline, reports, name):
    r = client(baseline, reports).get(f"/api/reports/{name}")
    assert r.status_code in (400, 404, 422) and "root:" not in r.text
    assert client(baseline, reports).get("/api/reports/missing").status_code == 404


def test_missing_reports_folder_gives_an_empty_list(baseline, tmp_path):
    c = client(baseline, tmp_path / "nowhere")
    assert c.get("/api/reports").json() == {"reports": []} and c.get("/api/pr").json() == {"comment": None, "status": None}


# ---------------------------------------------------------------- baseline problems
def test_no_baseline_is_503_with_a_clear_message(tmp_path):
    c = client(tmp_path / "absent.json")
    r = c.get("/api/meta")
    assert r.status_code == 503 and "no baseline available" in r.json()["detail"]
    assert c.get("/api/health").json()["status"] == "ok"


def test_other_schema_version_is_503_and_says_rebuild(baseline):
    doc = json.loads(baseline.read_text()); doc["schema_version"] = S.SCHEMA_VERSION + 3
    baseline.write_text(json.dumps(doc))
    r = client(baseline).get("/api/graph")
    assert r.status_code == 503 and "rebuild" in r.json()["detail"]


def test_a_changed_baseline_file_is_picked_up_without_a_restart(baseline):
    c = client(baseline)
    assert c.get("/api/meta").json()["counts"]["nodes"] == 3
    g = sample_graph(); g.nodes["db:sql_proc:extra"] = node("db", "SQL_PROC", "extra", "d.sql")
    JsonStore(baseline).write_full(g, S.make_freshness(g, g.commits, "incremental"))
    d = c.get("/api/meta").json()
    assert d["counts"]["nodes"] == 4 and d["baseline"]["mode"] == "incremental"


# ---------------------------------------------------------------- auth
def test_without_a_configured_token_the_api_is_open(baseline):
    c = client(baseline)
    assert c.get("/api/meta").status_code == 200 and c.get("/api/health").json()["auth_required"] is False


def test_with_a_token_every_data_route_needs_it(baseline, reports):
    c = client(baseline, reports, token=TOKEN)
    assert c.get("/api/health").status_code == 200 and c.get("/api/health").json()["auth_required"] is True
    paths = ["/api/meta", "/api/graph", "/api/nodes", "/api/nodes/x", "/api/trace?id=x", "/api/reports", "/api/reports/pr-x", "/api/pr"]
    for p in paths:
        r = c.get(p)
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer", p
        assert c.get(p, headers={"Authorization": "Bearer wrong"}).status_code == 401, p
        assert c.get(p, headers={"Authorization": f"Basic {TOKEN}"}).status_code == 401, p
    assert c.get("/api/meta", headers=AUTH).status_code == 200 and c.get("/api/graph", headers=AUTH).status_code == 200
    assert c.get("/api/nodes/api:api_endpoint:ItemController.Index()", headers=AUTH).status_code == 200


def test_the_token_never_appears_in_any_response(baseline):
    c = client(baseline, token=TOKEN)
    for r in (c.get("/api/meta"), c.get("/api/meta", headers=AUTH), c.get("/api/health"), c.get("/openapi.json")):
        assert TOKEN not in r.text and TOKEN not in str(r.headers)


# ---------------------------------------------------------------- read-only, localhost default, CORS, OpenAPI
def test_every_route_is_get_only_and_writes_are_405(baseline):
    app = client(baseline).app
    methods = {m for r in app.routes if hasattr(r, "methods") for m in r.methods}
    assert methods <= {"GET", "HEAD", "OPTIONS"}, methods
    c = TestClient(app)
    for m in ("post", "put", "patch", "delete"):
        assert getattr(c, m)("/api/graph").status_code == 405


def test_the_api_never_writes_the_store(baseline, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the API tried to write the store")
    monkeypatch.setattr(JsonStore, "write_full", boom); monkeypatch.setattr(JsonStore, "sync", boom)
    before = baseline.read_bytes()
    c = client(baseline)
    for p in ("/api/meta", "/api/graph", "/api/nodes", "/api/trace?id=web:ui_component:ListScreen"):
        c.get(p)
    assert baseline.read_bytes() == before


def test_serve_binds_to_localhost_by_default_and_refuses_open_binding_without_a_token(monkeypatch):
    for v in ("CDI_API_HOST", "CDI_API_PORT", "CDI_CORS_ORIGINS"):
        monkeypatch.delenv(v, raising=False)
    a = serve.build_parser().parse_args([])
    assert a.host == "127.0.0.1" and a.port == 8000 and a.token_env == "CDI_API_TOKEN" and a.cors_origin is None
    serve.check_bind("127.0.0.1", False); serve.check_bind("localhost", False); serve.check_bind("::1", False)
    for host in ("0.0.0.0", "192.168.1.5", "example.com", "::"):
        with pytest.raises(SystemExit, match="without authentication"):
            serve.check_bind(host, False)
        serve.check_bind(host, True)                                  # allowed once a token is configured


def test_cors_allows_only_configured_origins(baseline):
    none = client(baseline)
    assert "access-control-allow-origin" not in none.get("/api/health", headers={"Origin": "http://evil.example"}).headers
    c = client(baseline, cors_origins=["http://127.0.0.1:4173"])
    ok = c.get("/api/health", headers={"Origin": "http://127.0.0.1:4173"})
    assert ok.headers["access-control-allow-origin"] == "http://127.0.0.1:4173"
    assert "access-control-allow-origin" not in c.get("/api/health", headers={"Origin": "http://evil.example"}).headers
    pre = c.options("/api/meta", headers={"Origin": "http://127.0.0.1:4173", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"})
    assert pre.status_code == 200 and "authorization" in pre.headers["access-control-allow-headers"].lower()
    assert c.options("/api/meta", headers={"Origin": "http://127.0.0.1:4173", "Access-Control-Request-Method": "DELETE"}).status_code == 400


def test_openapi_document_describes_every_operation(baseline):
    doc = client(baseline, token=TOKEN).get("/openapi.json").json()
    assert doc["openapi"].startswith("3.") and doc["info"]["title"].startswith("cdi")
    ops = [(p, m, o) for p, item in doc["paths"].items() for m, o in item.items()]
    assert {p for p, _, _ in ops} >= {"/api/health", "/api/meta", "/api/graph", "/api/nodes", "/api/nodes/{node_id}", "/api/trace", "/api/reports", "/api/reports/{name}", "/api/pr"}
    assert all(m == "get" and o.get("summary") for _, m, o in ops)
    assert "HTTPBearer" in doc["components"]["securitySchemes"]
    assert "/api/health" in doc["paths"] and "security" not in doc["paths"]["/api/health"]["get"]
    assert "Hop" in doc["components"]["schemas"] and "from" in doc["components"]["schemas"]["Hop"]["properties"]


# ---------------------------------------------------------------- environment-driven defaults, no wildcard CORS
def test_host_port_and_origins_come_from_the_environment_with_documented_defaults(monkeypatch):
    monkeypatch.setenv("CDI_API_PORT", "8123"); monkeypatch.setenv("CDI_API_HOST", "127.0.0.1"); monkeypatch.setenv("CDI_CORS_ORIGINS", "http://127.0.0.1:5999, https://ui.example.invalid")
    a = serve.build_parser().parse_args([])
    assert (a.host, a.port) == ("127.0.0.1", 8123)
    assert serve.cors_origins(a) == ["http://127.0.0.1:5999", "https://ui.example.invalid"]
    a = serve.build_parser().parse_args(["--port", "9", "--cors-origin", "http://x.example:1"])
    assert a.port == 9 and serve.cors_origins(a) == ["http://x.example:1"], "an explicit option beats the environment"
    monkeypatch.delenv("CDI_API_PORT"); monkeypatch.delenv("CDI_API_HOST"); monkeypatch.delenv("CDI_CORS_ORIGINS")
    a = serve.build_parser().parse_args([])
    assert (a.host, a.port) == ("127.0.0.1", 8000) and serve.cors_origins(a) == []


@pytest.mark.parametrize("bad", ["*", "http://*.example.com", "null", "127.0.0.1:5173", "file://x"])
def test_wildcard_and_malformed_cors_origins_are_refused(bad):
    a = serve.build_parser().parse_args(["--cors-origin", bad])
    with pytest.raises(SystemExit, match="no wildcards"):
        serve.cors_origins(a)
    with pytest.raises(SystemExit, match="no wildcards"):
        serve.cors_origins(serve.build_parser().parse_args([]), {"CDI_CORS_ORIGINS": bad})
