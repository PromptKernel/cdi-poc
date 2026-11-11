"""Read-only HTTP API over the baseline graph (FastAPI; OpenAPI at /openapi.json, docs at /docs).

* Graph data is read ONLY through `cdi.store.GraphStore.read()`; the API has no code path that writes a store.
* Every operation is GET (a test enumerates the routes). Report and PR files are read from one configured folder, by validated names only.
* Optional bearer-token auth: when the environment variable named by `token_env` (default CDI_API_TOKEN) is set, every /api route except /api/health needs
  `Authorization: Bearer <token>`. The token is compared in constant time and never logged or returned.
* `cdi serve` binds to 127.0.0.1 by default and refuses another host unless a token is set."""
from __future__ import annotations
import contextlib, datetime, json, os, pathlib, re, secrets, threading, time
from typing import Any, Callable, Optional
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from cdi import export as X, store as S
from cdi.impact import traverse as T
from cdi.linker.graphio import Graph
from . import models as M

DEFAULT_TOKEN_ENV = "CDI_API_TOKEN"
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
MAX_PATHS = 200


class StoreHolder:
    """Keeps the last baseline read from the store; re-reads when the store's fingerprint changes (JSON file) or after `ttl` seconds (stores without one)."""
    def __init__(self, open_store: Callable[[], S.GraphStore], ttl: float = 5.0, clock=time.monotonic):
        self._open, self.ttl, self._clock = open_store, ttl, clock
        self._store: Optional[S.GraphStore] = None
        self._lock = threading.Lock()
        self._cache: Optional[tuple] = None          # (graph, fresh, fingerprint, loaded_at_clock)

    def get(self):
        with self._lock:
            if self._store is None:
                self._store = self._open()
            fp = self._store.fingerprint()
            c = self._cache
            if c and ((fp is not None and fp == c[2]) or (fp is None and self._clock() - c[3] < self.ttl)):
                return c[0], c[1]
            g, fresh = self._store.read()
            self._cache = (g, fresh, fp, self._clock())
            return g, fresh

    @property
    def kind(self):
        return self._store.kind if self._store else "unknown"

    def close(self):
        with self._lock:
            if self._store:
                self._store.close()
                self._store = None


def create_app(cfg: dict, open_store: Callable[[], S.GraphStore], reports_dir="out", token_env: str = DEFAULT_TOKEN_ENV,
               cors_origins=(), environ=None, ttl: float = 5.0) -> FastAPI:
    env = os.environ if environ is None else environ
    token = env.get(token_env) or None
    holder = StoreHolder(open_store, ttl)
    rdir = pathlib.Path(reports_dir)
    @contextlib.asynccontextmanager
    async def lifespan(_app):
        yield
        holder.close()

    app = FastAPI(lifespan=lifespan, title="cdi dependency graph API", version="1",
                  description="Read-only access to the baseline dependency graph. Every claim carries file:line, method, confidence and commit. "
                              "Edges mean 'source depends on target'. Auth: optional bearer token (see the server's token environment variable).")
    app.state.holder, app.state.token_required = holder, bool(token)
    if cors_origins:
        app.add_middleware(CORSMiddleware, allow_origins=list(cors_origins), allow_methods=["GET"], allow_headers=["Authorization"], allow_credentials=False)
    bearer = HTTPBearer(auto_error=False, description="Only needed when the server was started with a token.")

    def auth(cred: Optional[HTTPAuthorizationCredentials] = Depends(bearer)):
        if token is None:
            return
        if cred is None or cred.scheme.lower() != "bearer" or not secrets.compare_digest(cred.credentials.encode(), token.encode()):
            raise HTTPException(401, "missing or invalid bearer token", headers={"WWW-Authenticate": "Bearer"})

    def baseline():
        try:
            return holder.get()
        except S.BaselineMissing as e:
            raise HTTPException(503, f"no baseline available: {e}")
        except S.BaselineSchemaMismatch as e:
            raise HTTPException(503, f"baseline unusable: {e}")
        except S.StoreError as e:
            raise HTTPException(503, f"baseline unusable: {e}")

    open_router = APIRouter(prefix="/api", tags=["service"])
    api = APIRouter(prefix="/api", dependencies=[Depends(auth)])

    @open_router.get("/health", response_model=M.Health, summary="Liveness and whether a token is required (no graph data)")
    def health():
        return {"status": "ok", "auth_required": bool(token)}

    @api.get("/meta", response_model=M.Meta, tags=["graph"], summary="Data source and baseline: per-repo commit ids, load time, schema version")
    def meta():
        g, fresh = baseline()
        return {"source": "live-api", "store": holder.kind, "baseline": fresh, "counts": {"nodes": len(g.nodes), "edges": len(g.edges)},
                "repos": {r["name"]: {"path": r["path"], "kind": r["kind"]} for r in cfg["repos"]["repos"]}, "notice": X.notice_for(g)}

    @api.get("/graph", response_model=M.GraphDoc, tags=["graph"], summary="The whole graph in the explorer's format")
    def graph():
        g, fresh = baseline()
        return X.graph_document(g, fresh, cfg, "live-api")

    @api.get("/nodes", response_model=list[M.Node], tags=["graph"], summary="Search nodes by name or id")
    def nodes(q: str = Query("", description="case-insensitive substring of the name or id"), kind: Optional[str] = None, repo: Optional[str] = None,
              limit: int = Query(50, ge=1, le=500)):
        g, _ = baseline()
        ql = q.lower()
        hits = [n for n in g.nodes.values() if (not ql or ql in n["name"].lower() or ql in n["id"].lower()) and (not kind or n["kind"] == kind) and (not repo or n["repo"] == repo)]
        return [X.node_json(n) for n in sorted(hits, key=lambda n: (n["name"], n["id"]))[:limit]]

    @api.get("/nodes/{node_id:path}", response_model=M.NodeDetail, tags=["graph"], summary="One node with its outgoing and incoming edges")
    def node(node_id: str):
        g, _ = baseline()
        n = g.nodes.get(node_id)
        if n is None:
            raise HTTPException(404, f"no node with id {node_id!r}")
        return {"node": X.node_json(n), "depends_on": [X.edge_json(e) for e in g.out.get(node_id, [])], "depended_on_by": [X.edge_json(e) for e in g.inn.get(node_id, [])]}

    @api.get("/trace", response_model=M.Trace, tags=["graph"], summary="Maximal dependency paths from a node (forward = dependencies, reverse = consumers)")
    def trace(id: str = Query(..., description="node id"), direction: str = Query("forward", pattern="^(forward|reverse)$"),
              max_depth: int = Query(12, ge=1, le=25), exclude_types: str = Query("USES_TYPE", description="comma separated edge types to skip")):
        g, _ = baseline()
        if id not in g.nodes:
            raise HTTPException(404, f"no node with id {id!r}")
        ps = T.paths(g, id, direction, max_depth, [t for t in exclude_types.split(",") if t])
        return {"start": id, "direction": direction, "max_depth": max_depth, "truncated": len(ps) > MAX_PATHS, "paths": ps[:MAX_PATHS]}

    def safe(name: str):
        if not NAME_RE.match(name):
            raise HTTPException(400, "invalid report name")
        return name

    @api.get("/reports", response_model=M.Reports, tags=["reports"], summary="Impact reports found in the configured reports folder")
    def reports():
        out = []
        for md in sorted(rdir.glob("report-*.md")) if rdir.is_dir() else []:
            name = md.stem[len("report-"):]
            js = md.with_suffix(".json")
            e = {"name": name, "md": f"/api/reports/{name}?format=md", "json": f"/api/reports/{name}?format=json" if js.exists() else None,
                 "modified": datetime.datetime.fromtimestamp(md.stat().st_mtime, datetime.timezone.utc).isoformat(timespec="seconds")}
            if js.exists():
                try:
                    e["summary"] = X.report_summary(js.read_text())
                except Exception:
                    pass
            out.append(e)
        return {"reports": out}

    @api.get("/reports/{name}", tags=["reports"], summary="One impact report (format=md or json)", responses={200: {"content": {"text/markdown": {}, "application/json": {}}}})
    def report(name: str, format: str = Query("md", pattern="^(md|json)$")):
        f = rdir / f"report-{safe(name)}.{format}"
        if not f.is_file():
            raise HTTPException(404, "report not found")
        return PlainTextResponse(f.read_text(), media_type="text/markdown; charset=utf-8" if format == "md" else "application/json")

    @api.get("/pr", response_model=M.PrFiles, tags=["reports"], summary="The latest local PR comment and status files, if present")
    def pr():
        c, s = rdir / "pr-comment.md", rdir / "pr-status.json"
        return {"comment": c.read_text() if c.is_file() else None, "status": json.loads(s.read_text()) if s.is_file() else None}

    app.include_router(open_router)
    app.include_router(api)
    return app
